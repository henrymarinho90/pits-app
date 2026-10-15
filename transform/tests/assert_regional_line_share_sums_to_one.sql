{{ config(tags=['fleet_brand']) }}
-- D140: the line shares add up to 1 (tolerance 1e-9): per region and class, pooled over a class
-- (p(b,l|c) summed over brands and lines), and pooled inside every brand with weight
-- (p(l|b,c) summed over its lines). Classes without RUNT weight are NULL by design.
with regional as (
    select
        'regional' as kind,
        source_system,
        vehicle_class_norm,
        null::text as brand_norm,
        sum(regional_share) as total
    from {{ ref('fct_regional_line_share') }}
    group by source_system, vehicle_class_norm
),

pooled_class as (
    select
        'pooled_class' as kind,
        null::text as source_system,
        vehicle_class_norm,
        null::text as brand_norm,
        sum(pooled_share) as total
    from (
        select distinct vehicle_class_norm, brand_norm, line_norm, pooled_share
        from {{ ref('fct_regional_line_share') }}
        where pooling_status = 'ok'
    ) as d
    group by vehicle_class_norm
),

pooled_brand as (
    select
        'pooled_brand' as kind,
        null::text as source_system,
        vehicle_class_norm,
        brand_norm,
        sum(pooled_line_share_in_brand) as total
    from (
        select distinct vehicle_class_norm, brand_norm, line_norm, pooled_line_share_in_brand
        from {{ ref('fct_regional_line_share') }}
        where pooling_status = 'ok' and pooled_brand_share > 0
    ) as d
    group by vehicle_class_norm, brand_norm
)

select * from regional where abs(total - 1) > 1e-9
union all
select * from pooled_class where abs(total - 1) > 1e-9
union all
select * from pooled_brand where abs(total - 1) > 1e-9
