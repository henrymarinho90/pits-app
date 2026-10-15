{{ config(tags=['fleet_brand', 'brand_synthetic']) }}
-- D143/D145: the synthetic brand rows of each cell add up exactly to the real active_vehicle_count
-- of fct_synthetic_fleet_cell (both fleet_brand nodes: no vehicle_fleet/parts_demand node here,
-- D139). A cell without any synthetic row (N > 0) also fails.
select
    c.publication_year,
    c.publication_month,
    c.department_name_norm,
    c.municipality_name_norm,
    c.vehicle_class_norm,
    c.active_vehicle_count,
    coalesce(s.synthetic_total, 0) as synthetic_total
from {{ ref('fct_synthetic_fleet_cell') }} as c
left join (
    select
        publication_year,
        publication_month,
        department_name_norm,
        municipality_name_norm,
        vehicle_class_norm,
        sum(synthetic_vehicle_count) as synthetic_total
    from {{ ref('fct_synthetic_brand_fleet') }}
    group by
        publication_year,
        publication_month,
        department_name_norm,
        municipality_name_norm,
        vehicle_class_norm
) as s
    on s.publication_year = c.publication_year
    and s.publication_month = c.publication_month
    and s.department_name_norm = c.department_name_norm
    and s.municipality_name_norm = c.municipality_name_norm
    and s.vehicle_class_norm = c.vehicle_class_norm
where coalesce(s.synthetic_total, 0) <> c.active_vehicle_count
