{{ config(tags=['fleet_brand']) }}
-- D140: every source_system of the regional_brand_source seed that has rows in landing needs a
-- RUNT weight (sum of weight_vehicle_count > 0). Without it the pooled shares of that region
-- would silently count for nothing; the build fails instead (no fallback weight). A source that
-- has not been loaded yet has no rows and does not fail. The usual cause is a department code
-- in the seed that fct_parts_demand_fleet does not have, or a RUNT publication not loaded yet.
select
    s.source_system,
    s.dane_department_code,
    coalesce(w.weight_total, 0) as weight_total
from {{ ref('regional_brand_source') }} as s
left join (
    select source_system, sum(weight_vehicle_count) as weight_total
    from {{ ref('fct_regional_brand_weight') }}
    group by source_system
) as w on w.source_system = s.source_system
where exists (
    select 1 from {{ ref('stg_regional_fleet_brand') }} as r where r.source_system = s.source_system
)
and coalesce(w.weight_total, 0) = 0
