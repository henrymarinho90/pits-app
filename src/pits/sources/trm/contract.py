"""Source contract for the TRM dataset (verified against the live API on 2026-10-10)."""

from __future__ import annotations

import re
from datetime import date

from pits.ingestion.manifest import SchemaColumn

SOURCE_SYSTEM = "superfinanciera_trm"
DATASET_ID = "32sa-8pi3"
SOURCE_URL = "https://www.datos.gov.co/resource/32sa-8pi3.json"
LICENSE = "CC_40_BY_SA"
ATTRIBUTION = "Superintendencia Financiera de Colombia - SUPERFINANCIERA, Bogotá D.C."

# Non-system columns, in the order reported by the metadata endpoint.
EXPECTED_SCHEMA = (
    SchemaColumn("valor", "number"),
    SchemaColumn("unidad", "text"),
    SchemaColumn("vigenciadesde", "calendar_date"),
    SchemaColumn("vigenciahasta", "calendar_date"),
)
EXPECTED_COLUMNS = frozenset(c.name for c in EXPECTED_SCHEMA)

WATERMARK_COLUMN = "vigenciadesde"
ORDER = "vigenciadesde ASC, :id ASC"
PAGE_SIZE = 1000
BACKFILL_FROM = date(1991, 12, 2)  # first vigenciadesde in the dataset
# calendar_date arrives as a floating timestamp at midnight.
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}T00:00:00\.000")
