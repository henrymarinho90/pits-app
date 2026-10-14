"""Shared fixtures and synthetic data for the regional brand-share dbt tests (not a test module).

`warehouse` migrates a fresh database, loads a synthetic DIVIPOLA (the standard rows plus TUNJA in
BOYACA 15 and PEREIRA in RISARALDA 66), one RUNT publication with PARTICULAR vehicles in both
departments (the weights) and the two synthetic regional snapshots (landing). `transform` is the
fixture of divipola_dbt_support (the real `pits transform` CLI and the real dbt on a copy of the
project). All brands, lines and counts are synthetic; only the seeds of the repository are real.
"""

from __future__ import annotations

import csv
import json
import unicodedata
import uuid
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import divipola_dbt_support as ds
import pytest

from pits.warehouse.connection import connect
from pits.warehouse.migrate import run_migrate
from pits.warehouse.settings import Profile

BOYACA = "gobernacion_boyaca_parque_automotor"
RISARALDA = "gobernacion_risaralda_parque_automotor"
SEEDS = Path(__file__).resolve().parents[2] / "transform" / "seeds"

EXTRA_DIVIPOLA = [
    ("15", "BOYACÁ", "15001", "TUNJA", "Municipio", "-73,36", "5,53"),
    ("66", "RISARALDA", "66001", "PEREIRA", "Municipio", "-75,69", "4,81"),
]

# RUNT publication 2026-10 (department, municipality, service, status, class, year, count). Only
# ACTIVO + PARTICULAR counts for the weights; the rest must not.
RUNT = [
    ("BOYACA", "TUNJA", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2020, 2000),
    ("BOYACA", "TUNJA", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2015, 1000),
    ("BOYACA", "TUNJA", "PARTICULAR", "ACTIVO", "MOTOCICLETA", 2020, 1000),
    ("BOYACA", "TUNJA", "PÚBLICO", "ACTIVO", "AUTOMOVIL", 2020, 500),
    ("BOYACA", "TUNJA", "PARTICULAR", "INCONSISTENTE", "AUTOMOVIL", 2020, 7),
    ("RISARALDA", "PEREIRA", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2020, 1000),
    ("RISARALDA", "PEREIRA", "PARTICULAR", "ACTIVO", "MOTOCICLETA", 2020, 3000),
    ("RISARALDA", "PEREIRA", "PÚBLICO", "ACTIVO", "MOTOCICLETA", 2020, 9),
]
# An older publication must not weigh: only the latest one does.
RUNT_OLD = [("BOYACA", "TUNJA", "PARTICULAR", "ACTIVO", "AUTOMOVIL", 2010, 99999)]

# (class, brand, line, service, status, count) as the region publishes them.
BOYACA_ROWS = [
    ("AUTOMOVIL", "MARCA A", "L1", "PARTICULAR", "ACTIVO", 60),
    ("AUTOMOVIL", "marca a", "L1", "PARTICULAR", "ACTIVO", 10),  # same key after normalization
    ("AUTOMOVIL", "MARCA A", "L2", "PARTICULAR", "ACTIVO", 20),
    ("AUTOMOVIL", "MARCA B", "L1", "PARTICULAR", "ACTIVO", 20),
    ("AUTOMOVIL", "MARCA A", "L1", "PUBLICO", "ACTIVO", 15),  # excluded_service
    ("AUTOMOVIL", "MARCA A", "L1", "PARTICULAR", "INACTIVO", 5),  # excluded_status
    ("MOTOCICLETA", "AUTECO", "AGILITY", "PARTICULAR", "ACTIVO", 25),  # map: KYMCO (inferencia)
    ("MOTOCICLETA", "AUTECO BAJAJ", "LINEA Q", "PARTICULAR", "ACTIVO", 30),  # alias: BAJAJ
    ("MOTOCICLETA", "AUTECO", "ACTIVE 110", "PARTICULAR", "ACTIVO", 5),  # explicit SIN ASIGNAR
    ("MOTOCICLETA", "AUTECO", "LINEA NUEVA XYZ", "PARTICULAR", "ACTIVO", 2),  # unmapped, warns
    ("CAMPERO", "MARCA C", "C1", "PARTICULAR", "ACTIVO", 12),  # no RUNT weight in the region
    ("AMBULANCIA", "MARCA D", "D1", "PARTICULAR", "ACTIVO", 8),  # excluded_class (map)
    ("NUEVA CLASE", "MARCA D", "D1", "PARTICULAR", "ACTIVO", 4),  # unmapped class, warns
]
RISARALDA_ROWS = [
    ("AUTOMOVIL", "MARCA A", "L1", None, None, 30),
    ("AUTOMOVIL", "MARCA A", "L2", None, None, 10),
    ("AUTOMOVIL", "MARCA C", "C9", None, None, 60),
    ("AUTOMOVIL ELECTRICO", "MARCA E", "E1", None, None, 5),  # mapped to AUTOMOVIL
    ("MOTOCICLETA", "VICTORY", "ONE", None, None, 100),
    ("MOTOCICLETA", "AUTECO VICTORY", "ONE", None, None, 20),  # alias: VICTORY
    ("MOTOCICLETA", "AUTECO", "ACTIVE 110", None, None, 10),  # explicit SIN ASIGNAR
    ("SIN CLASE", "MARCA Z", "Z1", None, None, 3),  # excluded_class
]

_RUN_SQL = (
    "INSERT INTO ops.load_run (dataset, source_system, input_fingerprint, transform_name, "
    "rules_version, manifest_key, manifest_sha256, csv_key, csv_sha256, csv_size_bytes, "
    "row_count, coverage_from, coverage_to, last_input_batch_id, last_input_extraction_date, "
    "last_input_finished_at, normalized_manifest, loader_version) VALUES "
    "(%s, %s, %s, 't', '1', 'k', %s, 'c', %s, 1, %s, %s, %s, %s, '2026-10-14', now(), "
    "%s::jsonb, '0.1') RETURNING load_id"
)
_RUNT_ROW_SQL = (
    "INSERT INTO landing.vehicle_fleet_snapshot VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
    "'mintransporte_runt_parque', %s, %s)"
)
_BRAND_ROW_SQL = (
    "INSERT INTO landing.regional_fleet_brand_count (source_system, rows_updated, vehicle_class, "
    "brand, line, service_name, vehicle_status, vehicle_count, source_reference, load_id) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
)


def load_runt(loader, rows, year=2026, month=10) -> int:
    digest = uuid.uuid4().hex * 2
    start = f"{year}-{month:02d}-01"
    load_id = loader.execute(
        _RUN_SQL,
        (
            "vehicle_fleet_snapshot",
            "mintransporte_runt_parque",
            digest,
            digest,
            digest,
            len(rows),
            start,
            start,
            str(uuid.uuid4()),
            "{}",
        ),
    ).fetchone()[0]
    for i, row in enumerate(rows):
        loader.execute(_RUNT_ROW_SQL, (year, month, *row, f"raw/runt-{year}-{month}#{i}", load_id))
    return load_id


def load_regional(loader, source_system, rows, rows_updated="2026-07-06") -> int:
    digest = uuid.uuid4().hex * 2
    manifest = json.dumps({"vehicle_total": sum(r[-1] for r in rows)})
    load_id = loader.execute(
        _RUN_SQL,
        (
            "regional_fleet_brand_count",
            source_system,
            digest,
            digest,
            digest,
            len(rows),
            rows_updated,
            rows_updated,
            str(uuid.uuid4()),
            manifest,
        ),
    ).fetchone()[0]
    for i, row in enumerate(rows):
        loader.execute(
            _BRAND_ROW_SQL, (source_system, rows_updated, *row[:5], row[5], f"raw/{i}", load_id)
        )
    return load_id


@pytest.fixture
def warehouse(pg_settings):
    """Migrated database with DIVIPOLA, RUNT and regional snapshots: (settings, loader, admin)."""
    run_migrate(pg_settings)
    loader = connect(pg_settings, Profile.LOADER, autocommit=True)
    admin = connect(pg_settings, Profile.ADMIN, autocommit=True)
    ds.load_divipola_landing(loader, [*ds.divipola_rows(), *EXTRA_DIVIPOLA])
    load_runt(loader, RUNT_OLD, month=9)
    load_runt(loader, RUNT)
    load_regional(loader, BOYACA, BOYACA_ROWS)
    load_regional(loader, RISARALDA, RISARALDA_ROWS)
    yield pg_settings, loader, admin
    loader.close()
    admin.close()


transform = ds.transform
build_divipola = ds.build_divipola
reader_rows = ds.reader_rows


# --- independent recomputation (plain Python, no SQL) ------------------------------------------


def norm(text: str) -> str:
    """D100 in Python: accents removed, upper case, collapsed spaces."""
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    return " ".join(plain.upper().split())


def _seed(name):
    with open(SEEDS / f"{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def resolve_brand(brand: str, line: str) -> str:
    alias = {r["source_brand_norm"]: r["brand_norm"] for r in _seed("brand_alias")}
    auteco = {r["line_norm"]: r["real_brand"] for r in _seed("auteco_line_brand_map")}
    b = alias.get(norm(brand), norm(brand))
    return auteco.get(norm(line), "SIN ASIGNAR") if b == "AUTECO" else b


def expected_shares():
    """Independent model of D140: returns (weights, brand_rows, line_rows).

    weights[(source, class)] = sum of ACTIVO PARTICULAR RUNT vehicles of the latest publication;
    brand_rows[(source, class, brand)] and line_rows[(source, class, brand, line)] carry
    (count, regional_share, pooled_share).
    """
    dept = {BOYACA: "BOYACA", RISARALDA: "RISARALDA"}
    weights: dict[tuple[str, str], int] = defaultdict(int)
    for d, _, service, status, cls, _, n in RUNT:
        if service == "PARTICULAR" and status == "ACTIVO":
            for source, name in dept.items():
                if d == name:
                    weights[(source, norm(cls))] += n
    cmap = {(r["source_system"], r["source_class_norm"]): r["vehicle_class_norm"]
            for r in _seed("regional_vehicle_class_map")}  # fmt: skip
    counts: dict[tuple, int] = defaultdict(int)
    for source, rows in ((BOYACA, BOYACA_ROWS), (RISARALDA, RISARALDA_ROWS)):
        for cls, brand, line, service, status, n in rows:
            target = cmap.get((source, norm(cls)), "unmapped")
            if target in ("excluded", "unmapped"):
                continue
            if status is not None and norm(status) != "ACTIVO":
                continue
            if service is not None and norm(service) != "PARTICULAR":
                continue
            counts[(source, target, resolve_brand(brand, line), norm(line))] += n
    return weights, counts


def pooled(counts, weights, level):
    """Pooled share per (class, brand[, line]) from the independent model; None without weight."""
    key = (lambda k: k[:3]) if level == "brand" else (lambda k: k)
    cell: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for k, n in counts.items():
        cell[key(k)[1:]][k[0]] += n
        totals[(k[0], k[1])] += n
    out = {}
    for ck, per_source in cell.items():
        cls = ck[0]
        regions = {s for (s, c) in totals if c == cls}
        w_sum = sum(weights.get((s, cls), 0) for s in regions)
        if w_sum == 0:
            out[ck] = None
            continue
        out[ck] = sum(
            Decimal(weights.get((s, cls), 0)) * Decimal(per_source.get(s, 0)) / totals[(s, cls)]
            for s in regions
        ) / Decimal(w_sum)
    return out
