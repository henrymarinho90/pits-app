"""Load the committed normalized fx_rate artifact into `landing.fx_rate` (D82).

Layers:
- Pure logic: `plan_step` (decision table), `reconstruct_digest` and `load_fx_rate`, which only
  talk to the `FxRateWarehouse` / `FxRateSession` protocols.
- `PsycopgFxRateWarehouse`: the psycopg implementation (one transaction per load).

Flow of `load_fx_rate` (all warehouse work inside ONE transaction guarded by an advisory lock):
1. select the artifact (manifest only) with `pits.normalized.reader`;
2. lock (busy -> transient), read the latest `ops.load_run` of the dataset;
3. same fingerprint as the latest run -> verify the warehouse against the manifest; ok ->
   `already_loaded` (no writes); not ok -> drift (permanent) unless `repair`;
4. artifact older than the loaded one -> regression (permanent) unless forced by fingerprint;
5. GET + verify the CSV, COPY into a TEMP table, insert `ops.load_run`, MERGE, update counters;
6. verify again (count, coverage, contiguity, and the CSV rebuilt from the table must have the
   manifest's sha256 and size); any failure rolls everything back.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

import psycopg

from pits.ingestion.raw_store import RawStore
from pits.normalized.fx_rate_csv import (
    CURRENCY_FROM,
    CURRENCY_TO,
    HEADER,
    FxRateCsvError,
    format_rate,
)
from pits.normalized.reader import (
    DATASET,
    CommitOrder,
    FxRateArtifact,
    NormalizedReadPermanentError,
    NormalizedReadTransientError,
    SelectedArtifact,
    read_artifact,
    select_artifact,
)
from pits.sources.trm.contract import SOURCE_SYSTEM
from pits.warehouse.connection import connect
from pits.warehouse.errors import (
    WarehouseError,
    WarehousePermanentError,
    WarehouseTransientError,
    to_warehouse_error,
)
from pits.warehouse.settings import Profile, WarehouseSettings

LOAD_LOCK_KEY = 0x5049545303  # transaction advisory lock inside the warehouse database
LOCK_TIMEOUT = "10s"
STATEMENT_TIMEOUT = "5min"
COPY_CHUNK_BYTES = 64 * 1024
FETCH_BATCH = 5000


class Outcome(StrEnum):
    LOADED = "loaded"
    ALREADY_LOADED = "already_loaded"


class Step(StrEnum):
    LOAD = "load"
    VERIFY = "verify"
    REGRESSION = "regression"


@dataclass(frozen=True)
class LastRun:
    """Latest `ops.load_run` of the dataset."""

    load_id: int
    input_fingerprint: str
    last_input_batch_id: str
    last_input_extraction_date: date
    last_input_finished_at: datetime

    @property
    def commit_order(self) -> CommitOrder:
        return (
            self.last_input_extraction_date,
            self.last_input_finished_at,
            self.last_input_batch_id,
        )


@dataclass(frozen=True)
class ApplyResult:
    load_id: int
    inserted: int
    updated: int
    deleted: int


@dataclass(frozen=True)
class LoadResult:
    outcome: Outcome
    load_id: int
    fingerprint: str
    rows: int
    inserted: int
    updated: int
    deleted: int
    coverage_from: date
    coverage_to: date
    manifest_key: str


class FxRateSession(Protocol):
    """Operations inside one warehouse transaction."""

    def try_lock(self) -> bool: ...

    def last_run(self) -> LastRun | None: ...

    def verify(self, selected: SelectedArtifact) -> list[str]:
        """Problems found comparing the warehouse with the manifest (empty list = consistent)."""
        ...

    def apply(self, artifact: FxRateArtifact, loader_version: str) -> ApplyResult: ...


class FxRateWarehouse(Protocol):
    def transaction(self) -> AbstractContextManager[FxRateSession]:
        """Commit on normal exit, roll back if the body raises."""
        ...


# ---------------------------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------------------------


def plan_step(selected: SelectedArtifact, last: LastRun | None, *, forced: bool) -> Step:
    """Decision table, given the latest load_run (None = never loaded).

    - never loaded                              -> LOAD
    - same fingerprint as the latest run        -> VERIFY (idempotent re-run, or drift)
    - older than the loaded artifact, not forced -> REGRESSION (permanent error)
    - otherwise (newer, equal order, or forced)  -> LOAD
    """
    if last is None:
        return Step.LOAD
    if last.input_fingerprint == selected.manifest.input_fingerprint:
        return Step.VERIFY
    if not forced and selected.commit_order < last.commit_order:
        return Step.REGRESSION
    return Step.LOAD


def reconstruct_digest(
    rows: Iterable[tuple[date, str, str, Decimal, str]],
) -> tuple[str, int]:
    """sha256 and size of the CSV the artifact would have, rebuilt from table rows.

    `rows` must come ordered by (rate_date, currency_from, currency_to). Uses the real
    `format_rate` and `HEADER`, so it equals sha256(serialize_fx_rate(days)) for the same data.
    Raises FxRateCsvError on a row the normalized format cannot represent.
    """
    digest = hashlib.sha256()
    size = 0
    previous: date | None = None

    def feed(line: str) -> None:
        nonlocal size
        data = (line + "\n").encode("utf-8")
        digest.update(data)
        size += len(data)

    feed(HEADER)
    for rate_date, currency_from, currency_to, rate, source_reference in rows:
        if (currency_from, currency_to) != (CURRENCY_FROM, CURRENCY_TO):
            raise FxRateCsvError(f"unexpected currency pair on {rate_date}")
        if previous is not None and rate_date <= previous:
            raise FxRateCsvError(f"rows not strictly ascending at {rate_date}")
        previous = rate_date
        feed(
            ",".join(
                (
                    rate_date.isoformat(),
                    currency_from,
                    currency_to,
                    format_rate(rate),
                    source_reference,
                )
            )
        )
    return digest.hexdigest(), size


def check_summary(
    selected: SelectedArtifact,
    *,
    count: int,
    min_date: date | None,
    max_date: date | None,
) -> list[str]:
    """Cheap consistency checks (count, coverage, one row per day)."""
    manifest = selected.manifest
    problems: list[str] = []
    if count != manifest.row_count:
        problems.append(f"row count {count} != manifest {manifest.row_count}")
    if min_date != manifest.coverage.from_date:
        problems.append("min(rate_date) differs from manifest coverage.from")
    if max_date != manifest.coverage.to_date:
        problems.append("max(rate_date) differs from manifest coverage.to")
    if min_date is not None and max_date is not None and (max_date - min_date).days + 1 != count:
        problems.append("rate_date is not one row per day between min and max")
    return problems


def check_digest(selected: SelectedArtifact, sha256: str, size: int) -> list[str]:
    output = selected.manifest.output
    problems: list[str] = []
    if size != output.size_bytes:
        problems.append("rebuilt CSV size differs from manifest")
    if sha256 != output.sha256:
        problems.append("rebuilt CSV sha256 differs from manifest")
    return problems


def _read(store: RawStore, selected: SelectedArtifact) -> FxRateArtifact:
    try:
        return read_artifact(store, selected)
    except NormalizedReadTransientError as exc:
        raise WarehouseTransientError(str(exc)) from None
    except NormalizedReadPermanentError as exc:
        raise WarehousePermanentError(str(exc)) from None


def load_fx_rate(
    store: RawStore,
    warehouse: FxRateWarehouse,
    raw_bucket: str,
    *,
    loader_version: str,
    fingerprint: str | None = None,
    repair: bool = False,
) -> LoadResult:
    """Run the whole flow; raises WarehouseTransientError / WarehousePermanentError."""
    try:
        selected = select_artifact(store, raw_bucket, fingerprint)
    except NormalizedReadTransientError as exc:
        raise WarehouseTransientError(str(exc)) from None
    except NormalizedReadPermanentError as exc:
        raise WarehousePermanentError(str(exc)) from None

    manifest = selected.manifest
    with warehouse.transaction() as session:
        if not session.try_lock():
            raise WarehouseTransientError("Another fx_rate load holds the advisory lock")
        last = session.last_run()
        step = plan_step(selected, last, forced=fingerprint is not None)
        if step is Step.REGRESSION:
            raise WarehousePermanentError(
                "The selected artifact is older than the loaded one (use --fingerprint to force it)"
            )
        if step is Step.VERIFY and last is not None:
            problems = session.verify(selected)
            if not problems:
                return LoadResult(
                    Outcome.ALREADY_LOADED,
                    last.load_id,
                    manifest.input_fingerprint,
                    manifest.row_count,
                    0,
                    0,
                    0,
                    manifest.coverage.from_date,
                    manifest.coverage.to_date,
                    selected.manifest_key,
                )
            if not repair:
                raise WarehousePermanentError(
                    "Warehouse drifted from the loaded artifact (use --repair): "
                    + "; ".join(problems)
                )
        artifact = _read(store, selected)
        applied = session.apply(artifact, loader_version)
        problems = session.verify(selected)
        if problems:
            raise WarehousePermanentError("Verification failed after load: " + "; ".join(problems))
        return LoadResult(
            Outcome.LOADED,
            applied.load_id,
            manifest.input_fingerprint,
            manifest.row_count,
            applied.inserted,
            applied.updated,
            applied.deleted,
            manifest.coverage.from_date,
            manifest.coverage.to_date,
            selected.manifest_key,
        )


# ---------------------------------------------------------------------------------------------
# psycopg implementation
# ---------------------------------------------------------------------------------------------

_CREATE_STAGING = """
CREATE TEMP TABLE fx_rate_incoming (
    rate_date        date    NOT NULL,
    currency_from    text    NOT NULL,
    currency_to      text    NOT NULL,
    rate             numeric NOT NULL,
    source_reference text    NOT NULL,
    PRIMARY KEY (rate_date, currency_from, currency_to)
) ON COMMIT DROP
"""

_COPY = "COPY fx_rate_incoming FROM STDIN (FORMAT csv, HEADER MATCH)"

_OTHER_SOURCE = """
SELECT count(*) FROM landing.fx_rate t
JOIN fx_rate_incoming s USING (rate_date, currency_from, currency_to)
WHERE t.source_system <> %s
"""

_INSERT_LOAD_RUN = """
INSERT INTO ops.load_run (
    dataset, source_system, input_fingerprint, transform_name, rules_version,
    manifest_key, manifest_sha256, csv_key, csv_sha256, csv_size_bytes, row_count,
    coverage_from, coverage_to, last_input_batch_id, last_input_extraction_date,
    last_input_finished_at, normalized_manifest, loader_version
) VALUES (
    %(dataset)s, %(source_system)s, %(fingerprint)s, %(transform_name)s, %(rules_version)s,
    %(manifest_key)s, %(manifest_sha256)s, %(csv_key)s, %(csv_sha256)s, %(csv_size)s,
    %(row_count)s, %(coverage_from)s, %(coverage_to)s, %(batch_id)s, %(extraction_date)s,
    %(finished_at)s, %(manifest_json)s::jsonb, %(loader_version)s
) RETURNING load_id
"""

_MERGE = """
MERGE INTO landing.fx_rate AS t
USING fx_rate_incoming AS s
  ON (t.rate_date, t.currency_from, t.currency_to) = (s.rate_date, s.currency_from, s.currency_to)
WHEN MATCHED AND (t.rate, t.source_reference) IS DISTINCT FROM (s.rate, s.source_reference) THEN
  UPDATE SET rate = s.rate, source_reference = s.source_reference, load_id = %(load_id)s::bigint
WHEN NOT MATCHED BY TARGET THEN
  INSERT (rate_date, currency_from, currency_to, rate, source_system, source_reference, load_id)
  VALUES (s.rate_date, s.currency_from, s.currency_to, s.rate, %(source_system)s::text,
          s.source_reference, %(load_id)s::bigint)
WHEN NOT MATCHED BY SOURCE AND t.source_system = %(source_system)s::text THEN
  DELETE
RETURNING merge_action()
"""

_UPDATE_COUNTERS = """
UPDATE ops.load_run
SET rows_inserted = %s, rows_updated = %s, rows_deleted = %s
WHERE load_id = %s
"""

_SUMMARY = """
SELECT count(*), min(rate_date), max(rate_date) FROM landing.fx_rate WHERE source_system = %s
"""

_ROWS = """
SELECT rate_date, currency_from, currency_to, rate, source_reference
FROM landing.fx_rate WHERE source_system = %s
ORDER BY rate_date, currency_from, currency_to
"""

_LAST_RUN = """
SELECT load_id, input_fingerprint, last_input_batch_id, last_input_extraction_date,
       last_input_finished_at
FROM ops.load_run WHERE dataset = %s ORDER BY load_id DESC LIMIT 1
"""


class _PsycopgSession:
    def __init__(
        self, conn: psycopg.Connection, after_merge: Callable[[psycopg.Connection], None] | None
    ) -> None:
        self._conn = conn
        self._after_merge = after_merge

    def try_lock(self) -> bool:
        self._conn.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        self._conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
        row = self._conn.execute("SELECT pg_try_advisory_xact_lock(%s)", (LOAD_LOCK_KEY,))
        locked = row.fetchone()
        return bool(locked and locked[0])

    def last_run(self) -> LastRun | None:
        row = self._conn.execute(_LAST_RUN, (DATASET,)).fetchone()
        if row is None:
            return None
        return LastRun(row[0], row[1], str(row[2]), row[3], row[4])

    def verify(self, selected: SelectedArtifact) -> list[str]:
        row = self._conn.execute(_SUMMARY, (SOURCE_SYSTEM,)).fetchone()
        if row is None:  # unreachable: an aggregate always returns one row
            raise WarehousePermanentError("Summary query returned no row")
        count, min_date, max_date = row
        problems = check_summary(selected, count=count, min_date=min_date, max_date=max_date)
        if count == 0:
            return problems
        # Server-side cursor: rows stream in batches, memory stays bounded.
        try:
            with self._conn.cursor(name="fx_rate_verify") as cursor:
                cursor.itersize = FETCH_BATCH
                cursor.execute(_ROWS, (SOURCE_SYSTEM,))
                sha256, size = reconstruct_digest(cursor)
        except FxRateCsvError as exc:
            return [*problems, f"table content cannot be serialized: {exc}"]
        return [*problems, *check_digest(selected, sha256, size)]

    def apply(self, artifact: FxRateArtifact, loader_version: str) -> ApplyResult:
        conn = self._conn
        conn.execute(_CREATE_STAGING)
        with conn.cursor() as cursor:
            with cursor.copy(_COPY) as copy:
                data = artifact.csv_bytes
                for offset in range(0, len(data), COPY_CHUNK_BYTES):
                    copy.write(data[offset : offset + COPY_CHUNK_BYTES])
            staged = cursor.rowcount
        if staged != artifact.row_count:
            raise WarehousePermanentError(
                f"COPY staged {staged} rows, manifest says {artifact.row_count}"
            )
        clash = conn.execute(_OTHER_SOURCE, (SOURCE_SYSTEM,)).fetchone()
        if clash is not None and clash[0]:
            raise WarehousePermanentError(
                f"{clash[0]} incoming rows already exist in landing.fx_rate from another source"
            )
        load_id = conn.execute(
            _INSERT_LOAD_RUN,
            {
                "dataset": DATASET,
                "source_system": SOURCE_SYSTEM,
                "fingerprint": artifact.fingerprint,
                "transform_name": artifact.transform_name,
                "rules_version": artifact.rules_version,
                "manifest_key": artifact.manifest_key,
                "manifest_sha256": artifact.manifest_sha256,
                "csv_key": artifact.csv_key,
                "csv_sha256": artifact.csv_sha256,
                "csv_size": artifact.csv_size_bytes,
                "row_count": artifact.row_count,
                "coverage_from": artifact.coverage_from,
                "coverage_to": artifact.coverage_to,
                "batch_id": artifact.last_input_batch_id,
                "extraction_date": artifact.last_input_extraction_date,
                "finished_at": artifact.last_input_finished_at,
                "manifest_json": artifact.selected.manifest_bytes.decode("utf-8"),
                "loader_version": loader_version,
            },
        ).fetchone()
        if load_id is None:  # unreachable: INSERT ... RETURNING always yields the row
            raise WarehousePermanentError("INSERT into ops.load_run returned no load_id")
        new_id = load_id[0]
        actions = Counter(
            row[0]
            for row in conn.execute(
                _MERGE, {"load_id": new_id, "source_system": SOURCE_SYSTEM}
            ).fetchall()
        )
        if self._after_merge is not None:
            self._after_merge(conn)
        inserted, updated, deleted = actions["INSERT"], actions["UPDATE"], actions["DELETE"]
        conn.execute(_UPDATE_COUNTERS, (inserted, updated, deleted, new_id))
        return ApplyResult(new_id, inserted, updated, deleted)


class PsycopgFxRateWarehouse:
    """FxRateWarehouse over a non-autocommit loader connection (one transaction per call)."""

    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        after_merge: Callable[[psycopg.Connection], None] | None = None,
    ) -> None:
        self._conn = conn
        self._after_merge = after_merge  # test seam: failure injection right after the MERGE

    @contextmanager
    def transaction(self) -> Iterator[FxRateSession]:
        failure: WarehouseError | None = None
        try:
            yield _PsycopgSession(self._conn, self._after_merge)
            self._conn.commit()
        except psycopg.Error as exc:
            failure = to_warehouse_error(exc, "fx_rate load")
        except BaseException:
            self._rollback()
            raise
        if failure is not None:  # raised outside `except` so __context__ stays None
            self._rollback()
            raise failure

    def _rollback(self) -> None:
        try:
            self._conn.rollback()
        except psycopg.Error:
            pass  # connection already gone (e.g. terminated backend); nothing left to undo


@contextmanager
def open_warehouse(
    settings: WarehouseSettings,
    *,
    after_merge: Callable[[psycopg.Connection], None] | None = None,
) -> Iterator[PsycopgFxRateWarehouse]:
    """Connect with the loader profile (verified Postgres 17 / expected database)."""
    conn = connect(settings, Profile.LOADER, autocommit=False, application_name="pits-load")
    try:
        yield PsycopgFxRateWarehouse(conn, after_merge=after_merge)
    finally:
        conn.close()
