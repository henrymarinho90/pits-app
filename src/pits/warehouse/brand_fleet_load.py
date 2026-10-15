"""Load the committed normalized regional_fleet_brand artifact of one source (D138).

Same shape as `pits.warehouse.divipola_load` (D124), with one difference: the table holds one
CURRENT snapshot per source_system, so a load replaces only the rows of that source_system and
the "latest load_run" lookup is per (dataset, source_system). One source never deletes the other.
- `plan_step`, `reconstruct_digest` and `load_brand_fleet` only talk to the `BrandFleetWarehouse`
  / `BrandFleetSession` protocols;
- `PsycopgBrandFleetWarehouse` is the psycopg implementation.

Flow (all warehouse work in ONE transaction guarded by the warehouse advisory lock, D90):
1. select the artifact of the source (manifest only) with `pits.normalized.brand_fleet_reader`;
2. lock (busy -> transient), read the latest `ops.load_run` of the source;
3. same fingerprint as that run -> verify the landing rows against the manifest; ok ->
   `already_loaded` (no writes); not ok -> drift (permanent) unless `repair`;
4. artifact older than the loaded one -> regression (permanent) unless forced by fingerprint;
5. GET + verify the CSV, COPY into a TEMP table, insert `ops.load_run`, DELETE the rows of the
   source_system, INSERT from the TEMP table;
6. verify again (row count, sum of vehicle_count, and the logical CSV rebuilt from landing must
   have the manifest's sha256 and size); any failure rolls everything back, so the source is
   never left half replaced.
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
from pits.normalized.brand_fleet_csv import HEADER_BYTES
from pits.normalized.brand_fleet_reader import SelectedBrandFleet, read_csv, select_artifact
from pits.normalized.divipola_csv import RowWriter
from pits.normalized.reader import NormalizedReadPermanentError, NormalizedReadTransientError
from pits.sources.brand_fleet.contract import BrandFleetSource
from pits.warehouse.connection import connect
from pits.warehouse.divipola_load import ApplyResult
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

# ops.load_run.dataset of this loader; the artifact itself is `regional_fleet_brand`.
DATASET = "regional_fleet_brand_count"
LABEL = "regional_fleet_brand_count"


@dataclass(frozen=True)
class BrandFleetLoadResult:
    outcome: Outcome
    source_system: str
    rows_updated: date
    load_id: int
    fingerprint: str
    rows: int
    vehicles: int
    inserted: int
    deleted: int
    manifest_key: str


class BrandFleetSession(Protocol):
    """Operations inside one warehouse transaction."""

    def try_lock(self) -> bool: ...

    def last_run(self, source_system: str) -> LastRun | None:
        """Latest `ops.load_run` of the dataset for that source_system."""
        ...

    def verify(self, selected: SelectedBrandFleet) -> list[str]:
        """Problems found comparing the warehouse with the manifest (empty list = consistent)."""
        ...

    def apply(
        self, selected: SelectedBrandFleet, csv_bytes: bytes, loader_version: str
    ) -> ApplyResult: ...


class BrandFleetWarehouse(Protocol):
    def transaction(self) -> AbstractContextManager[BrandFleetSession]:
        """Commit on normal exit, roll back if the body raises."""
        ...


# ---------------------------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------------------------


def plan_step(selected: SelectedBrandFleet, last: LastRun | None, *, forced: bool) -> Step:
    """Decision table of D82, given the latest load_run of the source (None = never).

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

    `rows` carry (vehicle_class, brand, line, service_name, vehicle_status, vehicle_count,
    source_reference) ordered by the five keys, NULL service/status as ''. Each row goes through
    `divipola_csv.RowWriter`, the row writer the artifact serializer uses, so the result equals
    the sha256 of `serialize_brand_count(...)` for the same data.
    """
    digest = hashlib.sha256(HEADER_BYTES)
    size = len(HEADER_BYTES)
    writer = RowWriter()
    for row in rows:
        data = writer.line(row)
        digest.update(data)
        size += len(data)
    return digest.hexdigest(), size


def check_summary(
    selected: SelectedBrandFleet, *, count: int, vehicles: int, other_dates: int
) -> list[str]:
    manifest = selected.manifest
    problems: list[str] = []
    if count != manifest.row_count:
        problems.append(f"row count {count} != manifest {manifest.row_count}")
    if vehicles != manifest.vehicle_total:
        problems.append(f"vehicle total {vehicles} != manifest {manifest.vehicle_total}")
    if other_dates:
        problems.append(f"{other_dates} rows have a rows_updated other than the manifest's")
    return problems


def check_digest(selected: SelectedBrandFleet, sha256: str, size: int) -> list[str]:
    output = selected.manifest.output
    problems: list[str] = []
    if size != output.size_bytes:
        problems.append("rebuilt CSV size differs from manifest")
    if sha256 != output.sha256:
        problems.append("rebuilt CSV sha256 differs from manifest")
    return problems


def _warehouse_csv(store: RawStore, selected: SelectedBrandFleet) -> bytes:
    """Reader CSV with read errors translated to warehouse errors."""
    try:
        return read_csv(store, selected)
    except NormalizedReadTransientError as exc:
        raise WarehouseTransientError(str(exc)) from None
    except NormalizedReadPermanentError as exc:
        raise WarehousePermanentError(str(exc)) from None


def _result(
    outcome: Outcome, selected: SelectedBrandFleet, load_id: int, applied: ApplyResult | None
) -> BrandFleetLoadResult:
    manifest = selected.manifest
    return BrandFleetLoadResult(
        outcome,
        manifest.source_system,
        selected.rows_updated,
        load_id,
        manifest.input_fingerprint,
        manifest.row_count,
        manifest.vehicle_total,
        applied.inserted if applied else 0,
        applied.deleted if applied else 0,
        selected.manifest_key,
    )


def load_brand_fleet(
    store: RawStore,
    warehouse: BrandFleetWarehouse,
    raw_bucket: str,
    source: BrandFleetSource,
    *,
    loader_version: str,
    fingerprint: str | None = None,
    repair: bool = False,
) -> BrandFleetLoadResult:
    """Load the latest (or the forced) artifact of `source`; raises WarehouseError subclasses."""
    try:
        selected = select_artifact(store, raw_bucket, source, fingerprint=fingerprint)
    except NormalizedReadTransientError as exc:
        raise WarehouseTransientError(str(exc)) from None
    except NormalizedReadPermanentError as exc:
        raise WarehousePermanentError(str(exc)) from None
    with warehouse.transaction() as session:
        if not session.try_lock():
            raise WarehouseTransientError("Another warehouse writer holds the advisory lock")
        last = session.last_run(source.source_system)
        step = plan_step(selected, last, forced=fingerprint is not None)
        if step is Step.REGRESSION:
            raise WarehousePermanentError(
                f"{LABEL} ({source.source_system}): the selected artifact is older than the "
                "loaded one (use --fingerprint to force it)"
            )
        if step is Step.VERIFY and last is not None:
            problems = session.verify(selected)
            if not problems:
                return _result(Outcome.ALREADY_LOADED, selected, last.load_id, None)
            if not repair:
                raise WarehousePermanentError(
                    f"{LABEL} ({source.source_system}): warehouse drifted from the loaded "
                    "artifact (use --repair): " + "; ".join(problems)
                )
        applied = session.apply(selected, _warehouse_csv(store, selected), loader_version)
        problems = session.verify(selected)
        if problems:
            raise WarehousePermanentError(
                f"{LABEL} ({source.source_system}): verification failed after load: "
                + "; ".join(problems)
            )
        return _result(Outcome.LOADED, selected, applied.load_id, applied)


# ---------------------------------------------------------------------------------------------
# psycopg implementation
# ---------------------------------------------------------------------------------------------

# Same column order as the CSV header: COPY maps by position. An empty unquoted CSV field is NULL.
_CREATE_STAGING = """
CREATE TEMP TABLE brand_fleet_incoming (
    vehicle_class    text    NOT NULL,
    brand            text    NOT NULL,
    line             text    NOT NULL,
    service_name     text,
    vehicle_status   text,
    vehicle_count    integer NOT NULL,
    source_reference text    NOT NULL
) ON COMMIT DROP
"""

_COPY = "COPY brand_fleet_incoming FROM STDIN (FORMAT csv, HEADER true)"

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

_DELETE = "DELETE FROM landing.regional_fleet_brand_count WHERE source_system = %s"

_INSERT = """
INSERT INTO landing.regional_fleet_brand_count (
    source_system, rows_updated, vehicle_class, brand, line, service_name, vehicle_status,
    vehicle_count, source_reference, load_id
)
SELECT %s::text, %s::date, vehicle_class, brand, line, service_name, vehicle_status,
       vehicle_count, source_reference, %s::bigint
FROM brand_fleet_incoming
"""

_UPDATE_COUNTERS = """
UPDATE ops.load_run SET rows_inserted = %s, rows_updated = 0, rows_deleted = %s
WHERE load_id = %s
"""

_SUMMARY = """
SELECT count(*), COALESCE(sum(vehicle_count), 0)::bigint,
       count(*) FILTER (WHERE rows_updated <> %s::date)
FROM landing.regional_fleet_brand_count WHERE source_system = %s
"""

# COLLATE "C" pins the order to the normalizer's (code point order), whatever the database.
_ROWS = """
SELECT vehicle_class, brand, line, COALESCE(service_name, ''), COALESCE(vehicle_status, ''),
       vehicle_count, source_reference
FROM landing.regional_fleet_brand_count WHERE source_system = %s
ORDER BY vehicle_class COLLATE "C", brand COLLATE "C", line COLLATE "C",
         COALESCE(service_name, '') COLLATE "C", COALESCE(vehicle_status, '') COLLATE "C"
"""

_LAST_RUN = """
SELECT load_id, input_fingerprint, last_input_batch_id, last_input_extraction_date,
       last_input_finished_at
FROM ops.load_run WHERE dataset = %s AND source_system = %s ORDER BY load_id DESC LIMIT 1
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

    def last_run(self, source_system: str) -> LastRun | None:
        row = self._conn.execute(_LAST_RUN, (DATASET, source_system)).fetchone()
        if row is None:
            return None
        return LastRun(row[0], row[1], str(row[2]), row[3], row[4])

    def verify(self, selected: SelectedBrandFleet) -> list[str]:
        manifest = selected.manifest
        row = self._conn.execute(
            _SUMMARY, (manifest.rows_updated, manifest.source_system)
        ).fetchone()
        if row is None:  # unreachable: an aggregate always returns one row
            raise WarehousePermanentError("Summary query returned no row")
        problems = check_summary(selected, count=row[0], vehicles=row[1], other_dates=row[2])
        if row[0] == 0:
            return problems
        # Server-side cursor: rows stream in batches, memory stays bounded.
        with self._conn.cursor(name="brand_fleet_verify") as cursor:
            cursor.itersize = FETCH_BATCH
            cursor.execute(_ROWS, (manifest.source_system,))
            sha256, size = reconstruct_digest(cursor)
        return [*problems, *check_digest(selected, sha256, size)]

    def apply(
        self, selected: SelectedBrandFleet, csv_bytes: bytes, loader_version: str
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
                "source_system": manifest.source_system,
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
        deleted = conn.execute(_DELETE, (manifest.source_system,)).rowcount
        if self._after_delete is not None:
            self._after_delete(conn)
        inserted = conn.execute(
            _INSERT, (manifest.source_system, manifest.rows_updated, load_id)
        ).rowcount
        conn.execute(_UPDATE_COUNTERS, (inserted, deleted, load_id))
        return ApplyResult(load_id, inserted, deleted)


class PsycopgBrandFleetWarehouse:
    """BrandFleetWarehouse over a non-autocommit loader connection (one transaction per call)."""

    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        after_delete: Callable[[psycopg.Connection], None] | None = None,
    ) -> None:
        self._conn = conn
        self._after_delete = after_delete  # test seam: failure injection right after the DELETE

    @contextmanager
    def transaction(self) -> Iterator[BrandFleetSession]:
        failure: WarehouseError | None = None
        try:
            yield _PsycopgSession(self._conn, self._after_delete)
            self._conn.commit()
        except psycopg.Error as exc:
            failure = to_warehouse_error(exc, f"{LABEL} load")
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
def open_brand_fleet_warehouse(
    settings: WarehouseSettings,
    *,
    after_delete: Callable[[psycopg.Connection], None] | None = None,
) -> Iterator[PsycopgBrandFleetWarehouse]:
    """Connect with the loader profile (verified Postgres 17 / expected database)."""
    conn = connect(settings, Profile.LOADER, autocommit=False, application_name="pits-load")
    try:
        yield PsycopgBrandFleetWarehouse(conn, after_delete=after_delete)
    finally:
        conn.close()
