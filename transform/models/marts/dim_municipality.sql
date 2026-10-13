-- D125: DANE municipality dimension, one row per 5-digit DIVIPOLA code (current snapshot only).
-- Reads staging on purpose: a failed staging test leaves the previous dimension intact.
-- Longitude/latitude are stored typed for the future workshop/marketplace; no demand mart uses
-- them (the RUNT municipality is the registration office seat, an inference, not where a vehicle
-- circulates).
select
    municipality_code as dane_municipality_code,
    department_code as dane_department_code,
    department_name,
    municipality_name,
    department_name_norm,
    municipality_name_norm,
    municipality_type,
    longitude,
    latitude,
    load_id
from {{ ref('stg_divipola_municipality') }}
