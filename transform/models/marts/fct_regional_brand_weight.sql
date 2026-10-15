-- D140: weight of each region per vehicle class, taken from the RUNT: active PARTICULAR vehicles
-- of the department that the regional_brand_source seed assigns to the source_system, in the
-- LATEST publication of fct_parts_demand_fleet (the same demand base as D132). The pooled shares
-- weight each region by this number, so a big region counts more than a small one; it is not
-- a sample size. A source_system whose department has no RUNT rows has no row here, and the
-- assert_regional_brand_weight_present test fails the build instead of inventing a weight.
-- One of the two nodes of the fleet_brand family that read a vehicle_fleet/divipola node (the other
-- is fct_synthetic_fleet_cell, D145).
with latest as (
    select max(publication_year * 100 + publication_month) as publication_key
    from {{ ref('fct_parts_demand_fleet') }}
)

select
    s.source_system,
    s.dane_department_code,
    f.vehicle_class_norm,
    sum(f.active_vehicle_count)::bigint as weight_vehicle_count,
    f.publication_year as weight_publication_year,
    f.publication_month as weight_publication_month
from {{ ref('fct_parts_demand_fleet') }} as f
inner join latest as l
    on f.publication_year * 100 + f.publication_month = l.publication_key
inner join {{ ref('regional_brand_source') }} as s
    on s.dane_department_code = f.dane_department_code
where f.demand_segment = 'particular'
group by
    s.source_system,
    s.dane_department_code,
    f.vehicle_class_norm,
    f.publication_year,
    f.publication_month
