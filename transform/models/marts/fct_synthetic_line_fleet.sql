-- D142/D143: SYNTHETIC line breakdown of the active PARTICULAR fleet (never real data, 03 section
-- 28). Grain: (publication, department, dane_department_code, class, brand, line), only rows with
-- synthetic_vehicle_count > 0. Algorithm largest_remainder_v1 (Hamilton), line stage:
--   N_b = sum over the municipalities of synthetic_vehicle_count of fct_synthetic_brand_fleet for
--   the (publication, department, class, brand), calibrated brands only;
--   quota q_l = round(N_b * pooled_line_share_in_brand(l|b,c), 12), base f_l = floor(q_l),
--   R = N_b - sum(f_l); the R first lines by (q_l - f_l) desc, q_l desc, line_norm asc (collation
--   "C", explicit so the order does not depend on the database default) get +1.
-- The brand rows 'SIN CALIBRACION' (D144 a) pass through as ONE line 'SIN CALIBRACION' with the
-- whole N_b (brand_norm = line_norm = 'SIN CALIBRACION'), no provenance, sample_size_ok = false.
-- A calibrated (class, brand) with N_b > 0 but without a line share is NOT patched here: the inner
-- join drops it and assert_synthetic_line_conserves fails the build (no invented rule).
-- sample_size_ok is inherited from the regional LINE row (>= 1,000 pooled vehicles in the line).
-- Provenance comes from fct_regional_line_share, aggregated per class.
with brand_totals as (
    select
        publication_year,
        publication_month,
        department_name_norm,
        dane_department_code,
        vehicle_class_norm,
        brand_norm,
        sum(synthetic_vehicle_count)::bigint as brand_vehicle_count
    from {{ ref('fct_synthetic_brand_fleet') }}
    where brand_norm <> 'SIN CALIBRACION'
    group by
        publication_year,
        publication_month,
        department_name_norm,
        dane_department_code,
        vehicle_class_norm,
        brand_norm
),

line_share as (
    select distinct
        vehicle_class_norm,
        brand_norm,
        line_norm,
        pooled_line_share_in_brand,
        sample_size_ok
    from {{ ref('fct_regional_line_share') }}
    where pooled_line_share_in_brand is not null
),

class_provenance as (
    select
        vehicle_class_norm,
        max(source_systems) as source_systems,
        min(rows_updated_min) as rows_updated_min,
        max(rows_updated_max) as rows_updated_max,
        max(weight_publication_year * 100 + weight_publication_month) as weight_key
    from {{ ref('fct_regional_line_share') }}
    where pooled_line_share_in_brand is not null
    group by vehicle_class_norm
),

quota as (
    select
        t.publication_year,
        t.publication_month,
        t.department_name_norm,
        t.dane_department_code,
        t.vehicle_class_norm,
        t.brand_norm,
        t.brand_vehicle_count,
        s.line_norm,
        s.sample_size_ok,
        round(t.brand_vehicle_count * s.pooled_line_share_in_brand, 12) as allocation_quota
    from brand_totals as t
    inner join line_share as s
        on s.vehicle_class_norm = t.vehicle_class_norm
        and s.brand_norm = t.brand_norm
),

base as (
    select
        q.*,
        floor(q.allocation_quota) as base_count,
        q.allocation_quota - floor(q.allocation_quota) as remainder,
        q.brand_vehicle_count - sum(floor(q.allocation_quota)) over (
            partition by q.publication_year, q.publication_month, q.department_name_norm,
                q.dane_department_code, q.vehicle_class_norm, q.brand_norm
        ) as remaining
    from quota as q
),

ranked as (
    select
        b.*,
        row_number() over (
            partition by b.publication_year, b.publication_month, b.department_name_norm,
                b.dane_department_code, b.vehicle_class_norm, b.brand_norm
            order by b.remainder desc, b.allocation_quota desc, b.line_norm collate "C" asc
        ) as remainder_rank
    from base as b
),

calibrated as (
    select
        r.publication_year,
        r.publication_month,
        r.department_name_norm,
        r.dane_department_code,
        r.vehicle_class_norm,
        r.brand_norm,
        r.line_norm,
        (r.base_count + case when r.remainder_rank <= r.remaining then 1 else 0 end)::bigint
            as synthetic_vehicle_count,
        r.allocation_quota,
        r.sample_size_ok,
        p.source_systems,
        p.rows_updated_min,
        p.rows_updated_max,
        p.weight_key / 100 as weight_publication_year,
        mod(p.weight_key, 100) as weight_publication_month
    from ranked as r
    inner join class_provenance as p
        on p.vehicle_class_norm = r.vehicle_class_norm
),

uncalibrated as (
    select
        publication_year,
        publication_month,
        department_name_norm,
        dane_department_code,
        vehicle_class_norm,
        'SIN CALIBRACION' as brand_norm,
        'SIN CALIBRACION' as line_norm,
        sum(synthetic_vehicle_count)::bigint as synthetic_vehicle_count,
        sum(synthetic_vehicle_count)::numeric as allocation_quota,
        false as sample_size_ok,
        null::text as source_systems,
        null::date as rows_updated_min,
        null::date as rows_updated_max,
        null::int as weight_publication_year,
        null::int as weight_publication_month
    from {{ ref('fct_synthetic_brand_fleet') }}
    where brand_norm = 'SIN CALIBRACION'
    group by
        publication_year,
        publication_month,
        department_name_norm,
        dane_department_code,
        vehicle_class_norm
),

unioned as (
    select * from calibrated
    union all
    select * from uncalibrated
)

select
    u.*,
    'synthetic' as data_origin,
    'regional' as calibration_scope,
    'largest_remainder_v1' as allocation_method
from unioned as u
where u.synthetic_vehicle_count > 0
