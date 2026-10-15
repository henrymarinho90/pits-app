-- D140: what the regional shares keep and what they leave out, per source_system, so the
-- exclusions are visible and the total reconciles with staging and with ops.load_run.
-- scope_status comes from stg_regional_fleet_brand: included, excluded_class (class out of the
-- calibration or not in the class map), excluded_status (not ACTIVO) or excluded_service (not
-- PARTICULAR); evaluated in that order, the first that applies wins. Risaralda publishes neither
-- service nor status, so it has only included and excluded_class.
select
    source_system,
    scope_status,
    sum(vehicle_count)::bigint as vehicle_count,
    max(rows_updated) as rows_updated,
    max(load_id) as load_id
from {{ ref('stg_regional_fleet_brand') }}
group by source_system, scope_status
