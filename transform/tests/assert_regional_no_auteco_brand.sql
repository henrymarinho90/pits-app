{{ config(tags=['fleet_brand']) }}
-- D139: AUTECO is the distributor, not a brand. After the alias and the line map no resolved
-- brand may be AUTECO (an AUTECO line without a map row is SIN ASIGNAR, never AUTECO).
select 'stg_regional_fleet_brand' as relation, brand_norm
from {{ ref('stg_regional_fleet_brand') }}
where brand_norm = 'AUTECO'

union all

select 'fct_regional_brand_share', brand_norm
from {{ ref('fct_regional_brand_share') }}
where brand_norm = 'AUTECO'

union all

select 'fct_regional_line_share', brand_norm
from {{ ref('fct_regional_line_share') }}
where brand_norm = 'AUTECO'
