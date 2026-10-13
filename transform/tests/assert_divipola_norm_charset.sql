{{ config(tags=['divipola']) }}
-- D125: same charset rule as assert_vehicle_fleet_norm_charset (D100): an accent the translate
-- list misses or a new symbol fails loudly instead of silently breaking the RUNT match.
select
    municipality_code, department_name, municipality_name,
    department_name_norm, municipality_name_norm
from {{ ref('stg_divipola_municipality') }}
where department_name_norm !~ '^[A-Z0-9 ,.()-]+$'
   or municipality_name_norm !~ '^[A-Z0-9 ,.()-]+$'
