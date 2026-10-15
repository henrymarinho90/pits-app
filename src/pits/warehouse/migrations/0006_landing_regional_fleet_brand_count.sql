-- landing.regional_fleet_brand_count: regional (departmental) vehicle counts by class, brand and
-- line, exactly as normalized (D135-D138). One snapshot per source_system (Boyaca, Risaralda): a
-- load replaces ONLY that source_system's rows (DELETE + INSERT) in ONE transaction; history
-- stays in raw and normalized (write-once). Values are as published (no case folding or
-- trimming): staging normalizes them. service_name and vehicle_status are NULL for sources that
-- do not publish them (Risaralda). No UPDATE grant: a corrected snapshot is replaced, never
-- patched. The plate is never stored here: the normalizer drops it before this layer.

CREATE TABLE landing.regional_fleet_brand_count (
    source_system    text    NOT NULL,
    rows_updated     date    NOT NULL,
    vehicle_class    text    NOT NULL,
    brand            text    NOT NULL,
    line             text    NOT NULL,
    service_name     text,
    vehicle_status   text,
    vehicle_count    integer NOT NULL,
    source_reference text    NOT NULL,
    load_id          bigint  NOT NULL REFERENCES ops.load_run (load_id),

    -- NULLS NOT DISTINCT: two rows with NULL service/status and the same other keys collide
    -- (a plain UNIQUE would treat the NULLs as different and allow duplicates).
    CONSTRAINT regional_fleet_brand_count_uq UNIQUE NULLS NOT DISTINCT (
        source_system, vehicle_class, brand, line, service_name, vehicle_status
    ),
    CONSTRAINT regional_fleet_brand_count_count_ck CHECK (vehicle_count > 0),
    CONSTRAINT regional_fleet_brand_count_text_ck CHECK (
        btrim(vehicle_class) <> '' AND btrim(brand) <> '' AND btrim(line) <> ''
        AND (service_name IS NULL OR btrim(service_name) <> '')
        AND (vehicle_status IS NULL OR btrim(vehicle_status) <> '')
    ),
    CONSTRAINT regional_fleet_brand_count_source_system_ck CHECK (
        source_system ~ '^[a-z][a-z0-9_]*$'
    ),
    CONSTRAINT regional_fleet_brand_count_source_reference_ck CHECK (btrim(source_reference) <> '')
);

COMMENT ON TABLE landing.regional_fleet_brand_count IS
    'Vehicles per class, brand and line from departmental datasets (Boyaca em3d-hmim, Risaralda '
    'x9pp-pcn5, CC BY-SA 4.0), current snapshot per source_system (D135-D138). A stock (rule 5).';
COMMENT ON COLUMN landing.regional_fleet_brand_count.rows_updated IS
    'UTC date of the rowsUpdatedAt of the source dataset snapshot.';
COMMENT ON COLUMN landing.regional_fleet_brand_count.service_name IS
    'As published; NULL when the source does not publish it (Risaralda).';
COMMENT ON COLUMN landing.regional_fleet_brand_count.vehicle_status IS
    'As published; NULL when the source does not publish it (Risaralda).';
COMMENT ON COLUMN landing.regional_fleet_brand_count.source_reference IS
    'Key of the raw manifest the counts were aggregated from (lineage to raw).';
COMMENT ON COLUMN landing.regional_fleet_brand_count.load_id IS
    'ops.load_run row that wrote this snapshot; carries fingerprint and loaded_at.';

GRANT SELECT, INSERT, DELETE ON landing.regional_fleet_brand_count TO {{loader_role}};
GRANT SELECT ON landing.regional_fleet_brand_count TO {{reader_role}}, {{transformer_role}};
