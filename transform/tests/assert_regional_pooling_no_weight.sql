{{ config(tags=['fleet_brand'], severity='warn') }}
-- D140: a regional class whose regions have no RUNT weight for it (sum of weights = 0): its
-- pooled shares are NULL (pooling_status = no_runt_weight) and there is no fallback. Warn only;
-- the regional shares of the class are still published.
select
    vehicle_class_norm,
    max(source_systems) as source_systems,
    sum(vehicle_count) as regional_vehicles
from {{ ref('fct_regional_brand_share') }}
where pooling_status = 'no_runt_weight'
group by vehicle_class_norm
