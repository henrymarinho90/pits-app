{{ config(tags=['fleet_brand']) }}
-- D140: the brand shares of a class add up to 1, both per region and pooled (tolerance 1e-9).
-- Pooled: one value per (class, brand), so the rows are made distinct before adding them up.
-- Classes without RUNT weight are NULL by design (pooling_status = no_runt_weight, warn test).
with regional as (
    select
        'regional' as kind,
        source_system,
        vehicle_class_norm,
        sum(regional_share) as total
    from {{ ref('fct_regional_brand_share') }}
    group by source_system, vehicle_class_norm
),

pooled as (
    select
        'pooled' as kind,
        null::text as source_system,
        vehicle_class_norm,
        sum(pooled_share) as total
    from (
        select distinct vehicle_class_norm, brand_norm, pooled_share
        from {{ ref('fct_regional_brand_share') }}
        where pooling_status = 'ok'
    ) as d
    group by vehicle_class_norm
)

select * from regional where abs(total - 1) > 1e-9
union all
select * from pooled where abs(total - 1) > 1e-9
