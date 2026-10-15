{{ config(tags=['fleet_brand'], severity='warn') }}
-- D139: a regional class that is not in regional_vehicle_class_map. Warn only: its vehicles are
-- reported as excluded_class in the scope mart and stay out of the shares; add the class to the
-- seed in a PR (Henry approves the mapping).
select source_system, vehicle_class_norm, sum(vehicle_count) as vehicle_count
from {{ ref('stg_regional_fleet_brand') }}
where calibration_class_norm = 'unmapped'
group by source_system, vehicle_class_norm
