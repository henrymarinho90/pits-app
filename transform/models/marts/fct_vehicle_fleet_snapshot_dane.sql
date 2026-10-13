-- D127: fct_vehicle_fleet_snapshot (D100, untouched) plus the DANE code of its municipality. Same
-- grain and same rows: a LEFT JOIN to a map with one row per normalized pair never drops or
-- duplicates a cell (tests: unique grain, and rows equal to the fct in both directions). A pair
-- without a code keeps its row with NULL dane_* columns.
-- The registration municipality is the RUNT's; the code does not change its meaning (D97, D121).
select
    f.publication_year,
    f.publication_month,
    f.department_name,
    f.municipality_name,
    f.service_name,
    f.vehicle_status,
    f.vehicle_class,
    f.registration_year,
    f.vehicle_count,
    f.source_system,
    f.source_reference,
    f.load_id,
    f.department_name_norm,
    f.municipality_name_norm,
    f.vehicle_class_norm,
    m.dane_municipality_code,
    m.dane_department_code,
    m.match_method as dane_match_method
from {{ ref('fct_vehicle_fleet_snapshot') }} as f
left join {{ ref('map_runt_municipality_dane') }} as m
    on m.department_name_norm = f.department_name_norm
    and m.municipality_name_norm = f.municipality_name_norm
