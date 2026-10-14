{{ config(tags=['vehicle_fleet', 'divipola'], severity='warn') }}
-- D133: a class published by the RUNT that is not in the seed. Warn only (no error gate): its
-- vehicles stay in the demand mart with vehicle_group 'unmapped' and the totals do not change.
-- Add the class to the seed in a PR.
select s.vehicle_class_norm, sum(s.vehicle_count) as vehicle_count
from {{ ref('stg_vehicle_fleet_snapshot') }} as s
left join {{ ref('vehicle_class_demand_scope') }} as c
    on c.vehicle_class_norm = s.vehicle_class_norm
where c.vehicle_class_norm is null
group by s.vehicle_class_norm
