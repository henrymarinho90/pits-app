-- landing.fx_rate: daily exchange rates exactly as normalized (D79, D81). No derived columns.
-- CSV header is rate_date,currency_from,currency_to,rate,source_reference; the loader COPYs it
-- (HEADER MATCH) into a TEMP table with that exact header and MERGEs into this table adding
-- source_system (constant per loader) and load_id (the ops.load_run row of the same transaction).

CREATE TABLE landing.fx_rate (
    rate_date        date    NOT NULL,
    currency_from    text    NOT NULL,
    currency_to      text    NOT NULL,
    -- No precision/scale: the decimal digits are kept as published.
    rate             numeric NOT NULL,
    source_system    text    NOT NULL,
    source_reference text    NOT NULL,
    load_id          bigint  NOT NULL REFERENCES ops.load_run (load_id),

    CONSTRAINT fx_rate_pk PRIMARY KEY (rate_date, currency_from, currency_to),
    CONSTRAINT fx_rate_currency_from_ck CHECK (currency_from ~ '^[A-Z]{3}$'),
    CONSTRAINT fx_rate_currency_to_ck CHECK (currency_to ~ '^[A-Z]{3}$'),
    CONSTRAINT fx_rate_pair_ck CHECK (currency_from <> currency_to),
    -- numeric orders NaN above every number, so rate > 0 alone would accept NaN and Infinity.
    CONSTRAINT fx_rate_rate_ck CHECK (rate > 0 AND rate <> 'NaN' AND rate <> 'Infinity'),
    CONSTRAINT fx_rate_source_system_ck CHECK (source_system ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT fx_rate_source_reference_ck CHECK (btrim(source_reference) <> '')
);

COMMENT ON TABLE landing.fx_rate IS
    'Daily FX rates (rate = units of currency_to per 1 currency_from); grain: date + pair.';
COMMENT ON COLUMN landing.fx_rate.source_reference IS
    'Raw object path/batch the rate came from (lineage to raw, 03 section 3).';
COMMENT ON COLUMN landing.fx_rate.load_id IS
    'ops.load_run row that last wrote this rate; carries fingerprint and loaded_at.';

GRANT SELECT, INSERT, UPDATE, DELETE ON landing.fx_rate TO {{loader_role}};
GRANT SELECT ON landing.fx_rate TO {{reader_role}};
