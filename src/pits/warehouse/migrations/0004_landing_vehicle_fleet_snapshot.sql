-- landing.vehicle_fleet_snapshot: RUNT vehicle fleet (parque automotor) snapshot exactly as
-- normalized (D96-D99). One snapshot per publication (year + month); the grain is the full 8-column
-- primary key. The loader COPYs the artifact parts into a TEMP table and, in ONE transaction per
-- publication, deletes that publication here and inserts the staged rows, adding source_system
-- (constant per loader) and load_id (the ops.load_run row of the same transaction).
-- No UPDATE grant: a corrected publication is replaced (DELETE + INSERT), never patched.

CREATE TABLE landing.vehicle_fleet_snapshot (
    publication_year  smallint NOT NULL,
    publication_month smallint NOT NULL,
    department_name   text     NOT NULL,
    municipality_name text     NOT NULL,
    service_name      text     NOT NULL,
    vehicle_status    text     NOT NULL,
    vehicle_class     text     NOT NULL,
    registration_year smallint NOT NULL,
    vehicle_count     integer  NOT NULL,
    source_system     text     NOT NULL,
    source_reference  text     NOT NULL,
    load_id           bigint   NOT NULL REFERENCES ops.load_run (load_id),

    CONSTRAINT vehicle_fleet_snapshot_pk PRIMARY KEY (
        publication_year, publication_month, department_name, municipality_name,
        service_name, vehicle_status, vehicle_class, registration_year
    ),
    CONSTRAINT vehicle_fleet_snapshot_month_ck CHECK (publication_month BETWEEN 1 AND 12),
    CONSTRAINT vehicle_fleet_snapshot_year_ck CHECK (publication_year BETWEEN 2000 AND 2100),
    CONSTRAINT vehicle_fleet_snapshot_registration_year_ck CHECK (
        registration_year BETWEEN 1900 AND publication_year
    ),
    CONSTRAINT vehicle_fleet_snapshot_count_ck CHECK (vehicle_count > 0),
    -- Text values are usable as published: not empty and no leading/trailing spaces.
    CONSTRAINT vehicle_fleet_snapshot_text_ck CHECK (
        btrim(department_name) <> '' AND department_name = btrim(department_name)
        AND btrim(municipality_name) <> '' AND municipality_name = btrim(municipality_name)
        AND btrim(service_name) <> '' AND service_name = btrim(service_name)
        AND btrim(vehicle_status) <> '' AND vehicle_status = btrim(vehicle_status)
        AND btrim(vehicle_class) <> '' AND vehicle_class = btrim(vehicle_class)
    ),
    CONSTRAINT vehicle_fleet_snapshot_source_system_ck CHECK (source_system ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT vehicle_fleet_snapshot_source_reference_ck CHECK (btrim(source_reference) <> '')
);

COMMENT ON TABLE landing.vehicle_fleet_snapshot IS
    'RUNT vehicle fleet stock per publication month (D96-D99); grain: publication + department + '
    'municipality + service + status + class + registration year. A stock, not a flow (rule 5).';
COMMENT ON COLUMN landing.vehicle_fleet_snapshot.vehicle_count IS
    'Vehicles in that cell at the publication date (cantidad in the source).';
COMMENT ON COLUMN landing.vehicle_fleet_snapshot.source_reference IS
    'Raw payload object and row index the record came from (lineage to raw, 03 section 3).';
COMMENT ON COLUMN landing.vehicle_fleet_snapshot.load_id IS
    'ops.load_run row that wrote this publication; carries fingerprint and loaded_at.';

GRANT SELECT, INSERT, DELETE ON landing.vehicle_fleet_snapshot TO {{loader_role}};
GRANT SELECT ON landing.vehicle_fleet_snapshot TO {{reader_role}}, {{transformer_role}};
