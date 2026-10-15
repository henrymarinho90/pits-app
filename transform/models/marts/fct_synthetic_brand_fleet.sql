-- D142/D143: SYNTHETIC brand breakdown of the active PARTICULAR fleet (never real data, 03
-- section 28). Grain: cell (publication, department, municipality, class) x brand_norm, only rows
-- with synthetic_vehicle_count > 0. Algorithm largest_remainder_v1 (Hamilton), brand stage:
--   quota q_b = round(N * pooled_share(b|c), 12)  (numeric: the 12-decimal quantization makes the
--   tie-break reproducible outside Postgres), base f_b = floor(q_b), R = N - sum(f_b); the R first
--   brands by (q_b - f_b) desc, q_b desc, brand_norm asc get +1. Collation "C" is explicit so the
--   order does not depend on the database default (same as the builtin C.UTF-8 of D143).
-- Guarantees: sum per cell = N exactly, |assigned - quota| < 1, same input -> same output.
-- A cell with calibration_status = no_calibration (D144 a) gets one row brand_norm =
-- 'SIN CALIBRACION' carrying all N (no provenance: nothing was calibrated). SIN ASIGNAR is a
-- brand like any other (D144 b). sample_size_ok is inherited from the regional (class, brand) row.
-- Provenance columns come from fct_regional_brand_share, aggregated per class.
with cells as (
    select * from {{ ref('fct_synthetic_fleet_cell') }}
),

brand_share as (
    select distinct
        vehicle_class_norm,
        brand_norm,
        pooled_share,
        sample_size_ok
    from {{ ref('fct_regional_brand_share') }}
    where pooled_share is not null
),

class_provenance as (
    select
        vehicle_class_norm,
        max(source_systems) as source_systems,
        min(rows_updated_min) as rows_updated_min,
        max(rows_updated_max) as rows_updated_max,
        max(weight_publication_year * 100 + weight_publication_month) as weight_key
    from {{ ref('fct_regional_brand_share') }}
    where pooled_share is not null
    group by vehicle_class_norm
),

quota as (
    select
        c.publication_year,
        c.publication_month,
        c.department_name_norm,
        c.municipality_name_norm,
        c.vehicle_class_norm,
        c.dane_department_code,
        c.dane_municipality_code,
        c.vehicle_group,
        c.active_vehicle_count,
        s.brand_norm,
        s.sample_size_ok,
        round(c.active_vehicle_count * s.pooled_share, 12) as allocation_quota
    from cells as c
    inner join brand_share as s
        on s.vehicle_class_norm = c.vehicle_class_norm
    where c.calibration_status = 'calibrated'
),

base as (
    select
        q.*,
        floor(q.allocation_quota) as base_count,
        q.allocation_quota - floor(q.allocation_quota) as remainder,
        q.active_vehicle_count - sum(floor(q.allocation_quota)) over (
            partition by q.publication_year, q.publication_month, q.department_name_norm,
                q.municipality_name_norm, q.vehicle_class_norm
        ) as remaining
    from quota as q
),

ranked as (
    select
        b.*,
        row_number() over (
            partition by b.publication_year, b.publication_month, b.department_name_norm,
                b.municipality_name_norm, b.vehicle_class_norm
            order by b.remainder desc, b.allocation_quota desc, b.brand_norm collate "C" asc
        ) as remainder_rank
    from base as b
),

calibrated as (
    select
        r.publication_year,
        r.publication_month,
        r.department_name_norm,
        r.municipality_name_norm,
        r.vehicle_class_norm,
        r.dane_department_code,
        r.dane_municipality_code,
        r.vehicle_group,
        r.brand_norm,
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
        c.publication_year,
        c.publication_month,
        c.department_name_norm,
        c.municipality_name_norm,
        c.vehicle_class_norm,
        c.dane_department_code,
        c.dane_municipality_code,
        c.vehicle_group,
        'SIN CALIBRACION' as brand_norm,
        c.active_vehicle_count as synthetic_vehicle_count,
        c.active_vehicle_count::numeric as allocation_quota,
        false as sample_size_ok,
        null::text as source_systems,
        null::date as rows_updated_min,
        null::date as rows_updated_max,
        null::int as weight_publication_year,
        null::int as weight_publication_month
    from cells as c
    where c.calibration_status = 'no_calibration'
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
