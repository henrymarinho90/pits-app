-- landing.divipola_municipality: DANE DIVIPOLA municipality codes exactly as normalized (D121-D124).
-- Only the CURRENT snapshot lives here: the loader replaces the whole table (DELETE + INSERT) in
-- ONE transaction per load; history stays in raw and normalized (write-once). The grain is one row
-- per municipality code. Coordinates stay as published (text, decimal comma): staging converts
-- them, as D100 does with the text normalization. No UPDATE grant: a corrected snapshot is
-- replaced, never patched.

CREATE TABLE landing.divipola_municipality (
    department_code   text   NOT NULL,
    department_name   text   NOT NULL,
    municipality_code text   NOT NULL,
    municipality_name text   NOT NULL,
    municipality_type text   NOT NULL,
    longitude         text   NOT NULL,
    latitude          text   NOT NULL,
    source_system     text   NOT NULL,
    source_reference  text   NOT NULL,
    load_id           bigint NOT NULL REFERENCES ops.load_run (load_id),

    CONSTRAINT divipola_municipality_pk PRIMARY KEY (municipality_code),
    -- The name is the join key of the RUNT mapping once normalized: unique inside a department.
    CONSTRAINT divipola_municipality_name_uq UNIQUE (department_code, municipality_name),
    CONSTRAINT divipola_municipality_department_code_ck CHECK (department_code ~ '^[0-9]{2}$'),
    CONSTRAINT divipola_municipality_code_ck CHECK (
        municipality_code ~ '^[0-9]{5}$' AND left(municipality_code, 2) = department_code
    ),
    CONSTRAINT divipola_municipality_type_ck CHECK (
        municipality_type IN ('Municipio', 'Isla', U&'\00C1rea no municipalizada')
    ),
    CONSTRAINT divipola_municipality_coordinates_ck CHECK (
        longitude ~ '^-?[0-9]{1,3},[0-9]{1,8}$' AND latitude ~ '^-?[0-9]{1,3},[0-9]{1,8}$'
    ),
    CONSTRAINT divipola_municipality_text_ck CHECK (
        btrim(department_name) <> '' AND department_name = btrim(department_name)
        AND btrim(municipality_name) <> '' AND municipality_name = btrim(municipality_name)
    ),
    CONSTRAINT divipola_municipality_source_system_ck CHECK (source_system ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT divipola_municipality_source_reference_ck CHECK (btrim(source_reference) <> '')
);

COMMENT ON TABLE landing.divipola_municipality IS
    'DANE DIVIPOLA municipality codes (dataset gdxc-w37w, CC BY-SA 4.0), current snapshot only '
    '(D121-D124); one row per 5-digit municipality code.';
COMMENT ON COLUMN landing.divipola_municipality.longitude IS
    'As published: text with decimal comma (e.g. -74,106992); staging converts it to numeric.';
COMMENT ON COLUMN landing.divipola_municipality.source_reference IS
    'Raw payload object and row index the record came from (lineage to raw, 03 section 3).';
COMMENT ON COLUMN landing.divipola_municipality.load_id IS
    'ops.load_run row that wrote this snapshot; carries fingerprint and loaded_at.';

GRANT SELECT, INSERT, DELETE ON landing.divipola_municipality TO {{loader_role}};
GRANT SELECT ON landing.divipola_municipality TO {{reader_role}}, {{transformer_role}};
