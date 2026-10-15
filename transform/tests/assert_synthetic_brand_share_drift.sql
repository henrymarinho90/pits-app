{{ config(tags=['fleet_brand', 'brand_synthetic'], severity='warn') }}
-- D144 f: national synthetic share of each brand inside its calibrated class versus the pooled
-- regional share. Small cells are allocated with the same rule (no threshold) and Hamilton favours
-- the big brands, so this warns when |synthetic share - pooled_share| exceeds
-- var('synthetic_brand_drift_max') (0.005, inference, revisable). SIN CALIBRACION is excluded.
with synthetic as (
    select
        vehicle_class_norm,
        brand_norm,
        sum(synthetic_vehicle_count) as brand_vehicles
    from {{ ref('fct_synthetic_brand_fleet') }}
    where brand_norm <> 'SIN CALIBRACION'
    group by vehicle_class_norm, brand_norm
),

shares as (
    select
        s.vehicle_class_norm,
        s.brand_norm,
        s.brand_vehicles::numeric / sum(s.brand_vehicles) over (partition by s.vehicle_class_norm)
            as synthetic_share
    from synthetic as s
),

pooled as (
    select distinct
        vehicle_class_norm,
        brand_norm,
        pooled_share
    from {{ ref('fct_regional_brand_share') }}
    where pooled_share is not null
)

select
    p.vehicle_class_norm,
    p.brand_norm,
    p.pooled_share,
    coalesce(s.synthetic_share, 0) as synthetic_share,
    abs(coalesce(s.synthetic_share, 0) - p.pooled_share) as drift
from pooled as p
left join shares as s
    on s.vehicle_class_norm = p.vehicle_class_norm
    and s.brand_norm = p.brand_norm
where abs(coalesce(s.synthetic_share, 0) - p.pooled_share) > {{ var('synthetic_brand_drift_max') }}
