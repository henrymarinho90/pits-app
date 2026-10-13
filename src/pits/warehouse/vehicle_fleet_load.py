"""Load committed normalized vehicle_fleet_snapshot artifacts into the warehouse (D99).

Same shape as `pits.warehouse.fx_rate_load` (D82), with one transaction per publication:
- `plan_step` (decision table), `reconstruct_digest` and `load_vehicle_fleet` only talk to the
  `FleetWarehouse` / `FleetSession` protocols;
- `PsycopgFleetWarehouse` is the psycopg implementation.

Flow for each publication, ascending (all warehouse work in ONE transaction guarded by the
warehouse advisory lock, D90):
1. lock (busy -> transient), read the latest `ops.load_run` of THAT publication;
2. same fingerprint as that run -> verify the landing rows against the manifest; ok ->
   `already_loaded` (no writes); not ok -> drift (permanent) unless `repair`;
3. artifact older than the loaded one -> regression (permanent) unless forced by fingerprint;
4. COPY the parts one by one into a TEMP table (each part verified by the reader), insert
   `ops.load_run`, DELETE the publication from landing, INSERT from the TEMP table;
5. verify again (count, vehicle total, and the logical CSV rebuilt from landing must have the
   manifest's content_sha256 and size); any failure rolls everything back.
A publication is replaced as a whole and the other publications are never touched.
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
from pits.normalized.fleet_csv import HEADER_BYTES, RowWriter
from pits.normalized.fleet_manifest import DATASET, PartEntry
from pits.normalized.fleet_reader import (
    SelectedFleetArtifact,
    iter_parts,
    select_artifacts,
)
from pits.normalized.reader import NormalizedReadPermanentError, NormalizedReadTransientError
from pits.sources.runt.contract import SOURCE_SYSTEM
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
class FleetLoadResult:
    outcome: Outcome
    publication: str
    load_id: int
    fingerprint: str
    rows: int
    inserted: int
    updated: int
    deleted: int
    manifest_key: str


class FleetSession(Protocol):
    """Operations inside one warehouse transaction."""

    def try_lock(self) -> bool: ...

    def last_run(self, first_day: date) -> LastRun | None:
        """Latest `ops.load_run` of the dataset for the publication starting on `first_day`."""
        ...

    def verify(self, selected: SelectedFleetArtifact) -> list[str]:
        """Problems found comparing the warehouse with the manifest (empty list = consistent)."""
        ...

    def apply(
        self,
        selected: SelectedFleetArtifact,
        parts: Iterable[tuple[PartEntry, bytes]],
        loader_version: str,
    ) -> ApplyResult: ...


class FleetWarehouse(Protocol):
    def transaction(self) -> AbstractContextManager[FleetSession]:
        """Commit on normal exit, roll back if the body raises."""
        ...


# ---------------------------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------------------------


def plan_step(selected: SelectedFleetArtifact, last: LastRun | None, *, forced: bool) -> Step:
    """Decision table of D82, given the latest load_run of the publication (None = never).

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
    """sha256 and size of the logical CSV the artifact would have, rebuilt from landing rows.

    `rows` carry (publication_year, publication_month, department_name, municipality_name,
    service_name, vehicle_status, vehicle_class, registration_year, vehicle_count,
    source_reference) ordered by the primary key (code point order). The header is the one of
    `pits.normalized.fleet_csv`; each row goes through `fleet_csv.RowWriter`, the serializer's own
    row writer, so it equals `logical_content(serialize_fleet(...))`.
    """
    digest = hashlib.sha256(HEADER_BYTES)
    size = len(HEADER_BYTES)
    writer = RowWriter()
    for row in rows:
        data = writer.line(row)
        digest.update(data)
        size += len(data)
    return digest.hexdigest(), size


def check_summary(selected: SelectedFleetArtifact, *, count: int, vehicle_total: int) -> list[str]:
    manifest = selected.manifest
    problems: list[str] = []
    if count != manifest.row_count:
        problems.append(f"row count {count} != manifest {manifest.row_count}")
    if vehicle_total != manifest.vehicle_count_total:
        problems.append(
            f"vehicle_count total {vehicle_total} != manifest {manifest.vehicle_count_total}"
        )
    return problems


def check_digest(selected: SelectedFleetArtifact, sha256: str, size: int) -> list[str]:
    manifest = selected.manifest
    problems: list[str] = []
    if size != manifest.content_size_bytes:
        problems.append("rebuilt CSV size differs from manifest")
    if sha256 != manifest.content_sha256:
        problems.append("rebuilt CSV sha256 differs from manifest")
    return problems


def _warehouse_parts(
    store: RawStore, selected: SelectedFleetArtifact
) -> Iterator[tuple[PartEntry, bytes]]:
    """Reader parts with read errors translated to warehouse errors (lazily, part by part)."""
    try:
        yield from iter_parts(store, selected)
    except NormalizedReadTransientError as exc:
        raise WarehouseTransientError(str(exc)) from None
    except NormalizedReadPermanentError as exc:
        raise WarehousePermanentError(str(exc)) from None


def _result(
    outcome: Outcome, selected: SelectedFleetArtifact, load_id: int, applied: ApplyResult | None
) -> FleetLoadResult:
    return FleetLoadResult(
        outcome,
        selected.publication,
        load_id,
        selected.manifest.input_fingerprint,
        selected.manifest.row_count,
        applied.inserted if applied else 0,
        0,
        applied.deleted if applied else 0,
        selected.manifest_key,
    )


def _load_one(
    store: RawStore,
    warehouse: FleetWarehouse,
    selected: SelectedFleetArtifact,
    *,
    loader_version: str,
    forced: bool,
    repair: bool,
) -> FleetLoadResult:
    with warehouse.transaction() as session:
        if not session.try_lock():
            raise WarehouseTransientError("Another warehouse writer holds the advisory lock")
        last = session.last_run(selected.publication_first_day)
        step = plan_step(selected, last, forced=forced)
        if step is Step.REGRESSION:
            raise WarehousePermanentError(
                f"Publication {selected.publication}: the selected artifact is older than the "
                "loaded one (use --fingerprint to force it)"
            )
        if step is Step.VERIFY and last is not None:
            problems = session.verify(selected)
            if not problems:
                return _result(Outcome.ALREADY_LOADED, selected, last.load_id, None)
            if not repair:
                raise WarehousePermanentError(
                    f"Publication {selected.publication}: warehouse drifted from the loaded "
                    "artifact (use --repair): " + "; ".join(problems)
                )
        applied = session.apply(selected, _warehouse_parts(store, selected), loader_version)
        problems = session.verify(selected)
        if problems:
            raise WarehousePermanentError(
                f"Publication {selected.publication}: verification failed after load: "
                + "; ".join(problems)
            )
        return _result(Outcome.LOADED, selected, applied.load_id, applied)


def load_vehicle_fleet(
    store: RawStore,
    warehouse: FleetWarehouse,
    raw_bucket: str,
    *,
    loader_version: str,
    publication: str | None = None,
    fingerprint: str | None = None,
    repair: bool = False,
) -> Iterator[FleetLoadResult]:
    """Yield one result per publication (ascending) as soon as its transaction commits.

    Raises WarehouseTransientError / WarehousePermanentError; earlier publications stay loaded.
    """
    try:
        artifacts = select_artifacts(
            store, raw_bucket, publication=publication, fingerprint=fingerprint
        )
    except NormalizedReadTransientError as exc:
        raise WarehouseTransientError(str(exc)) from None
    except NormalizedReadPermanentError as exc:
        raise WarehousePermanentError(str(exc)) from None
    for selected in artifacts:
        yield _load_one(
            store,
            warehouse,
            selected,
            loader_version=loader_version,
            forced=fingerprint is not None,
            repair=repair,
        )


# ---------------------------------------------------------------------------------------------
# psycopg implementation
# ---------------------------------------------------------------------------------------------

# Same column order as the CSV header: COPY maps by position (the reader checks each header).
_CREATE_STAGING = """
CREATE TEMP TABLE fleet_incoming (
    publication_year  smallint NOT NULL,
    publication_month smallint NOT NULL,
    department_name   text     NOT NULL,
    municipality_name text     NOT NULL,
    service_name      text     NOT NULL,
    vehicle_status    text     NOT NULL,
    vehicle_class     text     NOT NULL,
    registration_year smallint NOT NULL,
    vehicle_count     integer  NOT NULL,
    source_reference  text     NOT NULL,
    PRIMARY KEY (publication_year, publication_month, department_name, municipality_name,
                 service_name, vehicle_status, vehicle_class, registration_year)
) ON COMMIT DROP
"""

_COPY = "COPY fleet_incoming FROM STDIN (FORMAT csv, HEADER true)"

_FOREIGN_PUBLICATION = """
SELECT count(*) FROM fleet_incoming WHERE (publication_year, publication_month) <> (%s, %s)
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
    %(row_count)s, %(first_day)s, %(first_day)s, %(batch_id)s, %(extraction_date)s,
    %(finished_at)s, %(manifest_json)s::jsonb, %(loader_version)s
) RETURNING load_id
"""

_DELETE = """
DELETE FROM landing.vehicle_fleet_snapshot WHERE publication_year = %s AND publication_month = %s
"""

_INSERT = """
INSERT INTO landing.vehicle_fleet_snapshot (
    publication_year, publication_month, department_name, municipality_name, service_name,
    vehicle_status, vehicle_class, registration_year, vehicle_count, source_system,
    source_reference, load_id
)
SELECT publication_year, publication_month, department_name, municipality_name, service_name,
       vehicle_status, vehicle_class, registration_year, vehicle_count, %s::text,
       source_reference, %s::bigint
FROM fleet_incoming
"""

_UPDATE_COUNTERS = """
UPDATE ops.load_run SET rows_inserted = %s, rows_updated = 0, rows_deleted = %s
WHERE load_id = %s
"""

_SUMMARY = """
SELECT count(*), COALESCE(sum(vehicle_count), 0)
FROM landing.vehicle_fleet_snapshot WHERE publication_year = %s AND publication_month = %s
"""

# COLLATE "C" on UTF-8 is code point order: the order the normalizer sorted the artifact in,
# independent of the database collation.
_ROWS = """
SELECT publication_year, publication_month, department_name, municipality_name, service_name,
       vehicle_status, vehicle_class, registration_year, vehicle_count, source_reference
FROM landing.vehicle_fleet_snapshot WHERE publication_year = %s AND publication_month = %s
ORDER BY department_name COLLATE "C", municipality_name COLLATE "C", service_name COLLATE "C",
         vehicle_status COLLATE "C", vehicle_class COLLATE "C", registration_year
"""

_LAST_RUN = """
SELECT load_id, input_fingerprint, last_input_batch_id, last_input_extraction_date,
       last_input_finished_at
FROM ops.load_run WHERE dataset = %s AND coverage_from = %s ORDER BY load_id DESC LIMIT 1
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

    def last_run(self, first_day: date) -> LastRun | None:
        row = self._conn.execute(_LAST_RUN, (DATASET, first_day)).fetchone()
        if row is None:
            return None
        return LastRun(row[0], row[1], str(row[2]), row[3], row[4])

    def verify(self, selected: SelectedFleetArtifact) -> list[str]:
        year_month = (selected.manifest.publication.year, selected.manifest.publication.month)
        row = self._conn.execute(_SUMMARY, year_month).fetchone()
        if row is None:  # unreachable: an aggregate always returns one row
            raise WarehousePermanentError("Summary query returned no row")
        count, vehicle_total = row
        problems = check_summary(selected, count=count, vehicle_total=vehicle_total)
        if count == 0:
            return problems
        # Server-side cursor: rows stream in batches, memory stays bounded.
        with self._conn.cursor(name="fleet_verify") as cursor:
            cursor.itersize = FETCH_BATCH
            cursor.execute(_ROWS, year_month)
            sha256, size = reconstruct_digest(cursor)
        return [*problems, *check_digest(selected, sha256, size)]

    def apply(
        self,
        selected: SelectedFleetArtifact,
        parts: Iterable[tuple[PartEntry, bytes]],
        loader_version: str,
    ) -> ApplyResult:
        conn = self._conn
        manifest = selected.manifest
        year_month = (manifest.publication.year, manifest.publication.month)
        conn.execute(_CREATE_STAGING)
        staged_total = 0
        for entry, data in parts:  # one verified part in memory at a time
            with conn.cursor() as cursor:
                with cursor.copy(_COPY) as copy:
                    for offset in range(0, len(data), COPY_CHUNK_BYTES):
                        copy.write(data[offset : offset + COPY_CHUNK_BYTES])
                staged = cursor.rowcount
            if staged != entry.row_count:
                raise WarehousePermanentError(
                    f"COPY staged {staged} rows from {entry.key}, manifest says {entry.row_count}"
                )
            staged_total += staged
        if staged_total != manifest.row_count:
            raise WarehousePermanentError(
                f"COPY staged {staged_total} rows, manifest says {manifest.row_count}"
            )
        foreign = conn.execute(_FOREIGN_PUBLICATION, year_month).fetchone()
        if foreign is not None and foreign[0]:
            raise WarehousePermanentError(
                f"{foreign[0]} staged rows do not belong to publication {selected.publication}"
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
                "csv_key": selected.prefix,
                "csv_sha256": manifest.content_sha256,
                "csv_size": manifest.content_size_bytes,
                "row_count": manifest.row_count,
                "first_day": selected.publication_first_day,
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
        deleted = conn.execute(_DELETE, year_month).rowcount
        if self._after_delete is not None:
            self._after_delete(conn)
        inserted = conn.execute(_INSERT, (SOURCE_SYSTEM, load_id)).rowcount
        conn.execute(_UPDATE_COUNTERS, (inserted, deleted, load_id))
        return ApplyResult(load_id, inserted, deleted)


class PsycopgFleetWarehouse:
    """FleetWarehouse over a non-autocommit loader connection (one transaction per call)."""

    def __init__(
        self,
        conn: psycopg.Connection,
        *,
        after_delete: Callable[[psycopg.Connection], None] | None = None,
    ) -> None:
        self._conn = conn
        self._after_delete = after_delete  # test seam: failure injection right after the DELETE

    @contextmanager
    def transaction(self) -> Iterator[FleetSession]:
        failure: WarehouseError | None = None
        try:
            yield _PsycopgSession(self._conn, self._after_delete)
            self._conn.commit()
        except psycopg.Error as exc:
            failure = to_warehouse_error(exc, "vehicle_fleet_snapshot load")
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
def open_fleet_warehouse(
    settings: WarehouseSettings,
    *,
    after_delete: Callable[[psycopg.Connection], None] | None = None,
) -> Iterator[PsycopgFleetWarehouse]:
    """Connect with the loader profile (verified Postgres 17 / expected database)."""
    conn = connect(settings, Profile.LOADER, autocommit=False, application_name="pits-load")
    try:
        yield PsycopgFleetWarehouse(conn, after_delete=after_delete)
    finally:
        conn.close()
