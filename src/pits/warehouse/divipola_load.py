"""Load the committed normalized divipola_municipality artifact into the warehouse (D124).

Same shape as `pits.warehouse.vehicle_fleet_load` (D99), but the table holds only the CURRENT
snapshot (a small reference dimension), so a load replaces the whole table:
- `plan_step` (decision table), `reconstruct_digest` and `load_divipola` only talk to the
  `DivipolaWarehouse` / `DivipolaSession` protocols;
- `PsycopgDivipolaWarehouse` is the psycopg implementation.

Flow (all warehouse work in ONE transaction guarded by the warehouse advisory lock, D90):
1. select the artifact (manifest only) with `pits.normalized.divipola_reader`;
2. lock (busy -> transient), read the latest `ops.load_run` of the dataset;
3. same fingerprint as that run -> verify the landing rows against the manifest; ok ->
   `already_loaded` (no writes); not ok -> drift (permanent) unless `repair`;
4. artifact older than the loaded one -> regression (permanent) unless forced by fingerprint;
5. GET + verify the CSV, COPY into a TEMP table, insert `ops.load_run`, DELETE the whole table,
   INSERT from the TEMP table;
6. verify again (count, and the logical CSV rebuilt from landing must have the manifest's sha256
   and size); any failure rolls everything back, so the table is never left half replaced.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import psycopg

from pits.ingestion.raw_store import RawStore
from pits.normalized.divipola_csv import HEADER_BYTES, RowWriter
from pits.normalized.divipola_manifest import DATASET
from pits.normalized.divipola_reader import SelectedDivipola, read_csv, select_artifact
from pits.normalized.reader import NormalizedReadPermanentError, NormalizedReadTransientError
from pits.sources.divipola.contract import SOURCE_SYSTEM
from pits.warehouse.connection import connect
from pits.warehouse.errors import (
    WarehouseError,
    WarehousePermanentError,
    WarehouseTransientError,
    to_warehouse_error,
)
from pits.warehouse.fx_rate_load import (
    COPY_CHUNK_BYTES,
    FETCH_BATCH,
    LOCK_TIMEOUT,
    STATEMENT_TIMEOUT,
    LastRun,
    Outcome,
    Step,
)
from pits.warehouse.locks import WAREHOUSE_LOCK_KEY
from pits.warehouse.settings import Profile, WarehouseSettings


@dataclass(frozen=True)
class ApplyResult:
    load_id: int
    inserted: int
    deleted: int


@dataclass(frozen=True)
class DivipolaLoadResult:
    outcome: Outcome
    rows_updated: date
    load_id: int
    fingerprint: str
    rows: int
    inserted: int
    updated: int
    deleted: int
    manifest_key: str


class DivipolaSession(Protocol):
    """Operations inside one warehouse transaction."""

    def try_lock(self) -> bool: ...

    def last_run(self) -> LastRun | None:
        """Latest `ops.load_run` of the dataset."""
        ...

    def verify(self, selected: SelectedDivipola) -> list[str]:
        """Problems found comparing the warehouse with the manifest (empty list = consistent)."""
        ...

    def apply(
        self, selected: SelectedDivipola, csv_bytes: bytes, loader_version: str
    ) -> ApplyResult: ...


class DivipolaWarehouse(Protocol):
    def transaction(self) -> AbstractContextManager[DivipolaSession]:
        """Commit on normal exit, roll back if the body raises."""
        ...


# ---------------------------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------------------------


def plan_step(selected: SelectedDivipola, last: LastRun | None, *, forced: bool) -> Step:
    """Decision table of D82, given the latest load_run of the dataset (None = never).

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


def reconstruct_digest(rows: Iterable[Sequence[object]]) -> tuple[str, int]:
    """sha256 and size of the CSV the artifact would have, rebuilt from landing rows.

    `rows` carry (department_code, department_name, municipality_code, municipality_name,
    municipality_type, longitude, latitude, source_reference) ordered by municipality_code. Each
    row goes through `divipola_csv.RowWriter`, the serializer's own row writer, so the result
    equals the sha256 of `serialize_divipola(...)` for the same data.
    """
    digest = hashlib.sha256(HEADER_BYTES)
    size = len(HEADER_BYTES)
    writer = RowWriter()
    for row in rows:
        data = writer.line(row)
        digest.update(data)
        size += len(data)
    return digest.hexdigest(), size


def check_summary(selected: SelectedDivipola, *, count: int) -> list[str]:
    if count != selected.manifest.row_count:
        return [f"row count {count} != manifest {selected.manifest.row_count}"]
    return []


def check_digest(selected: SelectedDivipola, sha256: str, size: int) -> list[str]:
    output = selected.manifest.output
    problems: list[str] = []
    if size != output.size_bytes:
        problems.append("rebuilt CSV size differs from manifest")
    if sha256 != output.sha256:
        problems.append("rebuilt CSV sha256 differs from manifest")
    return problems


def _warehouse_csv(store: RawStore, selected: SelectedDivipola) -> bytes:
    """Reader CSV with read errors translated to warehouse errors."""
    try:
        return read_csv(store, selected)
    except NormalizedReadTransientError as exc:
        raise WarehouseTransientError(str(exc)) from None
    except NormalizedReadPermanentError as exc:
        raise WarehousePermanentError(str(exc)) from None


def _result(
    outcome: Outcome, selected: SelectedDivipola, load_id: int, applied: ApplyResult | None
) -> DivipolaLoadResult:
    return DivipolaLoadResult(
        outcome,
        selected.rows_updated,
        load_id,
        selected.manifest.input_fingerprint,
        selected.manifest.row_count,
        applied.inserted if applied else 0,
        0,
        applied.deleted if applied else 0,
        selected.manifest_key,
    )


def load_divipola(
    store: RawStore,
    warehouse: DivipolaWarehouse,
    raw_bucket: str,
    *,
    loader_version: str,
    fingerprint: str | None = None,
    repair: bool = False,
) -> DivipolaLoadResult:
    """Load the latest (or the forced) artifact; raises WarehouseTransientError/PermanentError."""
    try:
        selected = select_artifact(store, raw_bucket, fingerprint=fingerprint)
    except NormalizedReadTransientError as exc:
        raise WarehouseTransientError(str(exc)) from None
    except NormalizedReadPermanentError as exc:
        raise WarehousePermanentError(str(exc)) from None
    with warehouse.transaction() as session:
        if not session.try_lock():
            raise WarehouseTransientError("Another warehouse writer holds the advisory lock")
        last = session.last_run()
        step = plan_step(selected, last, forced=fingerprint is not None)
        if step is Step.REGRESSION:
            raise WarehousePermanentError(
                "divipola_municipality: the selected artifact is older than the loaded one "
                "(use --fingerprint to force it)"
            )
        if step is Step.VERIFY and last is not None:
            problems = session.verify(selected)
            if not problems:
                return _result(Outcome.ALREADY_LOADED, selected, last.load_id, None)
            if not repair:
                raise WarehousePermanentError(
                    "divipola_municipality: warehouse drifted from the loaded artifact "
                    "(use --repair): " + "; ".join(problems)
                )
        applied = session.apply(selected, _warehouse_csv(store, selected), loader_version)
        problems = session.verify(selected)
        if problems:
            raise WarehousePermanentError(
                "divipola_municipality: verification failed after load: " + "; ".join(problems)
            )
        return _result(Outcome.LOADED, selected, applied.load_id, applied)


# ---------------------------------------------------------------------------------------------
# psycopg implementation
# ---------------------------------------------------------------------------------------------

# Same column order as the CSV header: COPY maps by position.
_CREATE_STAGING = """
CREATE TEMP TABLE divipola_incoming (
    department_code   text NOT NULL,
    department_name   text NOT NULL,
    municipality_code text NOT NULL PRIMARY KEY,
    municipality_name text NOT NULL,
    municipality_type text NOT NULL,
    longitude         text NOT NULL,
    latitude          text NOT NULL,
    source_reference  text NOT NULL
) ON COMMIT DROP
"""

_COPY = "COPY divipola_incoming FROM STDIN (FORMAT csv, HEADER true)"

_INSERT_LOAD_RUN = """
INSERT INTO ops.load_run (
    dataset, source_system, input_fingerprint, transform_name, rules_version,
    manifest_key, manifest_sha256, csv_key, csv_sha256, csv_size_bytes, row_count,
    coverage_from, coverage_to, last_input_batch_id, last_input_extraction_date,
    last_input_finished_at, normalized_manifest, loader_version
) VALUES (
    %(dataset)s, %(source_system)s, %(fingerprint)s, %(transform_name)s, %(rules_version)s,
    %(manifest_key)s, %(manifest_sha256)s, %(csv_key)s, %(csv_sha256)s, %(csv_size)s,
    %(row_count)s, %(rows_updated)s, %(rows_updated)s, %(batch_id)s, %(extraction_date)s,
    %(finished_at)s, %(manifest_json)s::jsonb, %(loader_version)s
) RETURNING load_id
"""

_DELETE = "DELETE FROM landing.divipola_municipality"

_INSERT = """
INSERT INTO landing.divipola_municipality (
    department_code, department_name, municipality_code, municipality_name, municipality_type,
    longitude, latitude, source_system, source_reference, load_id
)
SELECT department_code, department_name, municipality_code, municipality_name,
       municipality_type, longitude, latitude, %s::text, source_reference, %s::bigint
FROM divipola_incoming
"""

_UPDATE_COUNTERS = """
UPDATE ops.load_run SET rows_inserted = %s, rows_updated = 0, rows_deleted = %s
WHERE load_id = %s
"""

_COUNT = "SELECT count(*) FROM landing.divipola_municipality"

# Codes are digits only: COLLATE "C" pins the order to the normalizer's, whatever the database.
_ROWS = """
SELECT department_code, department_name, municipality_code, municipality_name,
       municipality_type, longitude, latitude, source_reference
FROM landing.divipola_municipality ORDER BY municipality_code COLLATE "C"
"""

_LAST_RUN = """
SELECT load_id, input_fingerprint, last_input_batch_id, last_input_extraction_date,
       last_input_finished_at
FROM ops.load_run WHERE dataset = %s ORDER BY load_id DESC LIMIT 1
"""


class _PsycopgSession:
    def __init__(
        self, conn: psycopg.Connection, after_delete: Callable[[psycopg.Connection], None] | None
    ) -> None:
        self._conn = conn
        self._after_delete = after_delete

    def try_lock(self) -> bool:
        self._conn.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        self._conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
        row = self._conn.execute("SELECT pg_try_advisory_xact_lock(%s)", (WAREHOUSE_LOCK_KEY,))
        locked = row.fetchone()
        return bool(locked and locked[0])

    def last_run(self) -> LastRun | None:
        row = self._conn.execute(_LAST_RUN, (DATASET,)).fetchone()
        if row is None:
            return None
        return LastRun(row[0], row[1], str(row[2]), row[3], row[4])

    def verify(self, selected: SelectedDivipola) -> list[str]:
        row = self._conn.execute(_COUNT).fetchone()
        if row is None:  # unreachable: an aggregate always returns one row
            raise WarehousePermanentError("Count query returned no row")
        problems = check_summary(selected, count=row[0])
        if row[0] == 0:
            return problems
        # Server-side cursor: rows stream in batches, memory stays bounded.
        with self._conn.cursor(name="divipola_verify") as cursor:
            cursor.itersize = FETCH_BATCH
            cursor.execute(_ROWS)
            sha256, size = reconstruct_digest(cursor)
        return [*problems, *check_digest(selected, sha256, size)]

    def apply(
        self, selected: SelectedDivipola, csv_bytes: bytes, loader_version: str
    ) -> ApplyResult:
        conn = self._conn
        manifest = selected.manifest
        conn.execute(_CREATE_STAGING)
        with conn.cursor() as cursor:
            with cursor.copy(_COPY) as copy:
                for offset in range(0, len(csv_bytes), COPY_CHUNK_BYTES):
                    copy.write(csv_bytes[offset : offset + COPY_CHUNK_BYTES])
            staged = cursor.rowcount
        if staged != manifest.row_count:
            raise WarehousePermanentError(
                f"COPY staged {staged} rows, manifest says {manifest.row_count}"
            )
        ref = manifest.inputs[0]
        loaded = conn.execute(
            _INSERT_LOAD_RUN,
            {
                "dataset": DATASET,
                "source_system": SOURCE_SYSTEM,
                "fingerprint": manifest.input_fingerprint,
                "transform_name": manifest.transform.name,
                "rules_version": manifest.transform.rules_version,
                "manifest_key": selected.manifest_key,
                "manifest_sha256": selected.manifest_sha256,
                "csv_key": manifest.output.key,
                "csv_sha256": manifest.output.sha256,
                "csv_size": manifest.output.size_bytes,
                "row_count": manifest.row_count,
                "rows_updated": manifest.rows_updated,
                "batch_id": ref.batch_id,
                "extraction_date": ref.extraction_date,
                "finished_at": ref.finished_at,
                "manifest_json": selected.manifest_bytes.decode("utf-8"),
                "loader_version": loader_version,
            },
        ).fetchone()
        if loaded is None:  # unreachable: INSERT ... RETURNING always yields the row
            raise WarehousePermanentError("INSERT into ops.load_run returned no load_id")
        load_id = loaded[0]
        deleted = conn.execute(_DELETE).rowcount
        if self._after_delete is not None:
            self._after_delete(conn)
        inserted = conn.execute(_INSERT, (SOURCE_SYSTEM, load_id)).rowcount
        conn.execute(_UPDATE_COUNTERS, (inserted, deleted, load_id))
        return ApplyResult(load_id, inserted, deleted)


class PsycopgDivipolaWarehouse:
    """DivipolaWarehouse over a non-autocommit loader connection (one transaction per call)."""

    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        after_delete: Callable[[psycopg.Connection], None] | None = None,
    ) -> None:
        self._conn = conn
        self._after_delete = after_delete  # test seam: failure injection right after the DELETE

    @contextmanager
    def transaction(self) -> Iterator[DivipolaSession]:
        failure: WarehouseError | None = None
        try:
            yield _PsycopgSession(self._conn, self._after_delete)
            self._conn.commit()
        except psycopg.Error as exc:
            failure = to_warehouse_error(exc, "divipola_municipality load")
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
def open_divipola_warehouse(
    settings: WarehouseSettings,
    *,
    after_delete: Callable[[psycopg.Connection], None] | None = None,
) -> Iterator[PsycopgDivipolaWarehouse]:
    """Connect with the loader profile (verified Postgres 17 / expected database)."""
    conn = connect(settings, Profile.LOADER, autocommit=False, application_name="pits-load")
    try:
        yield PsycopgDivipolaWarehouse(conn, after_delete=after_delete)
    finally:
        conn.close()
