{{ config(tags=['fleet_brand', 'brand_synthetic']) }}
-- D143/D145: the synthetic lines of each (publication, department, class, brand) add up exactly to
-- the brand total of fct_synthetic_brand_fleet (SIN CALIBRACION included as its own brand). A brand
-- group without any line row (for example a calibrated brand without line share) also fails, and
-- so does a line group without a brand group. Last, the grand total of lines must equal the grand
-- total of brands. Both nodes are fleet_brand: no vehicle_fleet/parts_demand node here (D139).
with brand_totals as (
    select
        publication_year,
        publication_month,
        department_name_norm,
        vehicle_class_norm,
        brand_norm,
        sum(synthetic_vehicle_count) as total
    from {{ ref('fct_synthetic_brand_fleet') }}
    group by publication_year, publication_month, department_name_norm, vehicle_class_norm, brand_norm
),

line_totals as (
    select
        publication_year,
        publication_month,
        department_name_norm,
        vehicle_class_norm,
        brand_norm,
        sum(synthetic_vehicle_count) as total
    from {{ ref('fct_synthetic_line_fleet') }}
    group by publication_year, publication_month, department_name_norm, vehicle_class_norm, brand_norm
),

per_group as (
    select
        coalesce(b.publication_year, l.publication_year) as publication_year,
        coalesce(b.publication_month, l.publication_month) as publication_month,
        coalesce(b.department_name_norm, l.department_name_norm) as department_name_norm,
        coalesce(b.vehicle_class_norm, l.vehicle_class_norm) as vehicle_class_norm,
        coalesce(b.brand_norm, l.brand_norm) as brand_norm,
        coalesce(b.total, 0) as brand_total,
        coalesce(l.total, 0) as line_total
    from brand_totals as b
    full outer join line_totals as l
        on l.publication_year = b.publication_year
        and l.publication_month = b.publication_month
        and l.department_name_norm = b.department_name_norm
        and l.vehicle_class_norm = b.vehicle_class_norm
        and l.brand_norm = b.brand_norm
),

grand as (
    select
        coalesce((select sum(synthetic_vehicle_count) from {{ ref('fct_synthetic_brand_fleet') }}), 0)
            as brand_total,
        coalesce((select sum(synthetic_vehicle_count) from {{ ref('fct_synthetic_line_fleet') }}), 0)
            as line_total
)

select
    publication_year,
    publication_month,
    department_name_norm,
    vehicle_class_norm,
    brand_norm,
    brand_total,
    line_total
from per_group
where brand_total <> line_total

union all

select
    null::int as publication_year,
    null::int as publication_month,
    'GRAND TOTAL' as department_name_norm,
    null::text as vehicle_class_norm,
    null::text as brand_norm,
    brand_total,
    line_total
from grand
where brand_total <> line_total
