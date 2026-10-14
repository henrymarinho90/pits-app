-- D140: line share inside each (vehicle class, brand), per region and pooled.
-- Same rules as fct_regional_brand_share, one level deeper. Grain: (source_system,
-- vehicle_class_norm, brand_norm, line_norm) for every region that has the class (a line absent
-- from a region has vehicle_count 0 there). Only rows in the calibration scope.
--   regional_share           = vehicle_count / region_class_total                 (p_r(b,l|c))
--   pooled_share             = sum_r w_r(c) * regional_share_r / sum_r w_r(c)     (p(b,l|c))
--   pooled_brand_share       = sum over the lines of the brand of pooled_share    (p(b|c))
--   pooled_line_share_in_brand = pooled_share / pooled_brand_share                (p(l|b,c))
-- If the sum of weights is 0 the pooled values are NULL with pooling_status = no_runt_weight
-- (no fallback weight). sample_size_ok: at least 1,000 pooled vehicles in the line (P6).
with included as (
    select
        source_system,
        calibration_class_norm as vehicle_class_norm,
        brand_norm,
        line_norm,
        sum(vehicle_count)::bigint as vehicle_count,
        max(rows_updated) as rows_updated
    from {{ ref('stg_regional_fleet_brand') }}
    where scope_status = 'included'
    group by source_system, calibration_class_norm, brand_norm, line_norm
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

lines as (
    select distinct vehicle_class_norm, brand_norm, line_norm from included
),

grid as (
    select
        rc.source_system,
        rc.vehicle_class_norm,
        l.brand_norm,
        l.line_norm,
        rc.region_class_total,
        rc.rows_updated,
        coalesce(i.vehicle_count, 0) as vehicle_count,
        coalesce(w.weight_vehicle_count, 0) as weight_vehicle_count,
        w.weight_publication_year,
        w.weight_publication_month
    from region_class as rc
    inner join lines as l
        on l.vehicle_class_norm = rc.vehicle_class_norm
    left join included as i
        on i.source_system = rc.source_system
        and i.vehicle_class_norm = rc.vehicle_class_norm
        and i.brand_norm = l.brand_norm
        and i.line_norm = l.line_norm
    left join {{ ref('fct_regional_brand_weight') }} as w
        on w.source_system = rc.source_system
        and w.vehicle_class_norm = rc.vehicle_class_norm
),

pooled_line as (
    select
        vehicle_class_norm,
        brand_norm,
        line_norm,
        sum(weight_vehicle_count) as pooled_weight,
        sum(vehicle_count) as pooled_vehicle_count,
        sum(weight_vehicle_count * vehicle_count::numeric / region_class_total)
            / nullif(sum(weight_vehicle_count), 0) as pooled_share,
        string_agg(source_system, ',' order by source_system) as source_systems,
        min(rows_updated) as rows_updated_min,
        max(rows_updated) as rows_updated_max,
        max(weight_publication_year * 100 + weight_publication_month) as weight_key
    from grid
    group by vehicle_class_norm, brand_norm, line_norm
),

pooled_brand as (
    select
        vehicle_class_norm,
        brand_norm,
        sum(pooled_share) as pooled_brand_share
    from pooled_line
    group by vehicle_class_norm, brand_norm
)

select
    g.source_system,
    g.vehicle_class_norm,
    g.brand_norm,
    g.line_norm,
    g.vehicle_count,
    g.region_class_total,
    g.vehicle_count::numeric / g.region_class_total as regional_share,
    g.weight_vehicle_count as region_weight,
    p.pooled_weight,
    p.pooled_vehicle_count,
    p.pooled_share,
    b.pooled_brand_share,
    p.pooled_share / nullif(b.pooled_brand_share, 0) as pooled_line_share_in_brand,
    case when p.pooled_weight = 0 then 'no_runt_weight' else 'ok' end as pooling_status,
    p.pooled_vehicle_count >= 1000 as sample_size_ok,
    'regional' as calibration_scope,
    p.source_systems,
    p.rows_updated_min,
    p.rows_updated_max,
    p.weight_key / 100 as weight_publication_year,
    mod(p.weight_key, 100) as weight_publication_month
from grid as g
inner join pooled_line as p
    on p.vehicle_class_norm = g.vehicle_class_norm
    and p.brand_norm = g.brand_norm
    and p.line_norm = g.line_norm
inner join pooled_brand as b
    on b.vehicle_class_norm = g.vehicle_class_norm
    and b.brand_norm = g.brand_norm
