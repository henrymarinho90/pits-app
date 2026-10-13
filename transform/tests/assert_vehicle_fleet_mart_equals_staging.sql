{{ config(tags=['vehicle_fleet']) }}
-- The mart is a copy of staging today: any difference (including duplicates) in either direction fails.
(select * from {{ ref('stg_vehicle_fleet_snapshot') }} except all select * from {{ ref('fct_vehicle_fleet_snapshot') }})
union all
(select * from {{ ref('fct_vehicle_fleet_snapshot') }} except all select * from {{ ref('stg_vehicle_fleet_snapshot') }})
