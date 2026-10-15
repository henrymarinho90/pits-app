{{ config(tags=['fleet_brand', 'brand_synthetic'], severity='warn') }}
-- D144 a: cells of a vehicle class without pooled_share (no regional data or no RUNT weight).
-- They are not dropped: they get one SIN CALIBRACION row with the whole N, so the sum stays
-- equal to the RUNT. Warn only; it lists the classes and the vehicles left uncalibrated.
select
    vehicle_class_norm,
    count(*) as cells,
    sum(active_vehicle_count) as uncalibrated_vehicles
from {{ ref('fct_synthetic_fleet_cell') }}
where calibration_status = 'no_calibration'
group by vehicle_class_norm
