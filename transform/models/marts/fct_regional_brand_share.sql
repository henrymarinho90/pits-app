-- D140: brand share inside each vehicle class, per region and pooled.
-- Grain: (source_system, vehicle_class_norm, brand_norm) for every region that has the class
-- (a brand absent from a region has vehicle_count 0 there). Only rows in the calibration scope
-- (stg scope_status = included); SIN ASIGNAR is a brand like any other and stays visible.
-- regional_share = vehicle_count / region_class_total.
-- pooled_share(b|c) = sum_r w_r(c) * regional_share_r(b|c) / sum_r w_r(c), over the regions that
-- have the class; w_r(c) comes from fct_regional_brand_weight (RUNT, D140). If the sum of weights
-- is 0 the pooled values are NULL with pooling_status = no_runt_weight (a warn test lists them):
-- there is no fallback weight. sample_size_ok: at least 1,000 pooled vehicles (P6).
with included as (
    select
        source_system,
        calibration_class_norm as vehicle_class_norm,
        brand_norm,
        sum(vehicle_count)::bigint as vehicle_count,
        max(rows_updated) as rows_updated
    from {{ ref('stg_regional_fleet_brand') }}
    where scope_status = 'included'
    group by source_system, calibration_class_norm, brand_norm
),

region_class as (
    select
        source_system,
        vehicle_class_norm,
        sum(vehicle_count)::bigint as region_class_total,
        max(rows_updated) as rows_updated
    from included
    group by source_system, vehicle_class_norm
),

brands as (
    select distinct vehicle_class_norm, brand_norm from included
),

grid as (
    select
        rc.source_system,
        rc.vehicle_class_norm,
        b.brand_norm,
        rc.region_class_total,
        rc.rows_updated,
        coalesce(i.vehicle_count, 0) as vehicle_count,
        coalesce(w.weight_vehicle_count, 0) as weight_vehicle_count,
        w.weight_publication_year,
        w.weight_publication_month
    from region_class as rc
    inner join brands as b
        on b.vehicle_class_norm = rc.vehicle_class_norm
    left join included as i
        on i.source_system = rc.source_system
        and i.vehicle_class_norm = rc.vehicle_class_norm
        and i.brand_norm = b.brand_norm
    left join {{ ref('fct_regional_brand_weight') }} as w
        on w.source_system = rc.source_system
        and w.vehicle_class_norm = rc.vehicle_class_norm
),

pooled as (
    select
        g.*,
        g.vehicle_count::numeric / g.region_class_total as regional_share,
        sum(g.weight_vehicle_count) over (w) as pooled_weight,
        sum(g.vehicle_count) over (w) as pooled_vehicle_count,
        sum(g.weight_vehicle_count * g.vehicle_count::numeric / g.region_class_total) over (w)
            / nullif(sum(g.weight_vehicle_count) over (w), 0) as pooled_share,
        min(g.rows_updated) over (w) as rows_updated_min,
        max(g.rows_updated) over (w) as rows_updated_max,
        max(g.weight_publication_year * 100 + g.weight_publication_month) over (w) as weight_key
    from grid as g
    window w as (partition by g.vehicle_class_norm, g.brand_norm)
),

region_list as (
    select
        vehicle_class_norm,
        string_agg(source_system, ',' order by source_system) as source_systems
    from region_class
    group by vehicle_class_norm
)

select
    p.source_system,
    p.vehicle_class_norm,
    p.brand_norm,
    p.vehicle_count,
    p.region_class_total,
    p.regional_share,
    p.weight_vehicle_count as region_weight,
    pooled_weight,
    pooled_vehicle_count,
    pooled_share,
    case when pooled_weight = 0 then 'no_runt_weight' else 'ok' end as pooling_status,
    pooled_vehicle_count >= 1000 as sample_size_ok,
    'regional' as calibration_scope,
    l.source_systems,
    rows_updated_min,
    rows_updated_max,
    weight_key / 100 as weight_publication_year,
    mod(weight_key, 100) as weight_publication_month
from pooled as p
inner join region_list as l
    on l.vehicle_class_norm = p.vehicle_class_norm
