{{ config(tags=['fleet_brand'], severity='warn') }}
-- D139 (P4 = a): an AUTECO line without a row in auteco_line_brand_map resolves to SIN ASIGNAR.
-- Warn only, and only for lines the seed does not know (the lines the seed lists as SIN ASIGNAR
-- are explicit decisions and do not warn). Add the line to the seed in a PR.
select source_system, line_norm, sum(vehicle_count) as vehicle_count
from {{ ref('stg_regional_fleet_brand') }}
where brand_resolution = 'auteco_unmapped'
group by source_system, line_norm
