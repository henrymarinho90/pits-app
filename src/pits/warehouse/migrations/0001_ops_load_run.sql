-- ops.load_run: one row per effective load of a dataset into the warehouse (D79, D81).
-- Append-only by privileges: the loader can INSERT and update only the three row counters;
-- nobody but the owner can DELETE/TRUNCATE. Executed as the owner (SET LOCAL ROLE).

CREATE TABLE ops.load_run (
    load_id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset                    text        NOT NULL,
    source_system              text        NOT NULL,
    input_fingerprint          text        NOT NULL,
    transform_name             text        NOT NULL,
    rules_version              text        NOT NULL,
    manifest_key               text        NOT NULL,
    manifest_sha256            text        NOT NULL,
    csv_key                    text        NOT NULL,
    csv_sha256                 text        NOT NULL,
    csv_size_bytes             bigint      NOT NULL,
    row_count                  integer     NOT NULL,
    coverage_from              date        NOT NULL,
    coverage_to                date        NOT NULL,
    last_input_batch_id        uuid        NOT NULL,
    last_input_extraction_date date        NOT NULL,
    last_input_finished_at     timestamptz NOT NULL,
    -- Counters start at 0 and are filled in by the loader after the MERGE (see GRANT below).
    rows_inserted              integer     NOT NULL DEFAULT 0,
    rows_updated               integer     NOT NULL DEFAULT 0,
    rows_deleted               integer     NOT NULL DEFAULT 0,
    normalized_manifest        jsonb       NOT NULL,
    loader_version             text        NOT NULL,
    loaded_at                  timestamptz NOT NULL DEFAULT now(),

    -- Identifier-like fields: same charset as the code uses, so typos fail loudly.
    CONSTRAINT load_run_dataset_ck CHECK (dataset ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT load_run_source_system_ck CHECK (source_system ~ '^[a-z][a-z0-9_]*$'),
    -- Content hashes are lowercase hex sha256 (64 chars), never truncated or uppercase.
    CONSTRAINT load_run_fingerprint_ck CHECK (input_fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT load_run_manifest_sha256_ck CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT load_run_csv_sha256_ck CHECK (csv_sha256 ~ '^[0-9a-f]{64}$'),
    -- Free-text lineage fields must carry something; an empty string is a bug, not a value.
    CONSTRAINT load_run_text_not_blank_ck CHECK (
        btrim(transform_name) <> '' AND btrim(rules_version) <> ''
        AND btrim(manifest_key) <> '' AND btrim(csv_key) <> '' AND btrim(loader_version) <> ''
    ),
    -- An empty artifact is never loaded (loader guard), so a run always has size and rows.
    CONSTRAINT load_run_csv_size_ck CHECK (csv_size_bytes > 0),
    CONSTRAINT load_run_row_count_ck CHECK (row_count > 0),
    CONSTRAINT load_run_coverage_ck CHECK (coverage_from <= coverage_to),
    -- Counters are cardinalities.
    CONSTRAINT load_run_counts_ck CHECK (
        rows_inserted >= 0 AND rows_updated >= 0 AND rows_deleted >= 0
    ),
    -- The stored manifest is the verbatim JSON object of the normalized manifest.
    CONSTRAINT load_run_manifest_json_ck CHECK (jsonb_typeof(normalized_manifest) = 'object')
);

-- "Latest run of a dataset" is the hot lookup of the loader (idempotence check).
CREATE INDEX load_run_dataset_load_id_idx ON ops.load_run (dataset, load_id DESC);

COMMENT ON TABLE ops.load_run IS
    'Audit of effective loads into landing (D81). Append-only except the three counters.';
COMMENT ON COLUMN ops.load_run.input_fingerprint IS
    'Fingerprint of the normalized artifact inputs (key segment fingerprint=...).';
COMMENT ON COLUMN ops.load_run.normalized_manifest IS
    'Verbatim normalized manifest.json; source of per-input lineage (ingested_at, batches).';

GRANT SELECT, INSERT ON ops.load_run TO {{loader_role}};
-- Why UPDATE on counters: the load_run row must exist before the MERGE (landing.fx_rate.load_id
-- references it inside the same transaction); the MERGE then reports the real counts, which
-- the loader writes back. Simpler than a deferred FK plus a post-MERGE insert, and column-level
-- so no other column can be rewritten.
GRANT UPDATE (rows_inserted, rows_updated, rows_deleted) ON ops.load_run TO {{loader_role}};
GRANT SELECT ON ops.load_run TO {{reader_role}};
-- Identity inserts need no USAGE on the backing sequence (checked against the table).
