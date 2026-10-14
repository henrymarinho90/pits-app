-- D132: active vehicle fleet (stock, rule 5) by registration municipality, service, class and
-- registration year: the demand base for spare parts. It is NOT a count of parts.
-- Filters, only these two: vehicle_status = 'ACTIVO' (D59) and service PARTICULAR/PÚBLICO (D54,
-- D56). No class filter: every class enters and vehicle_group (D133 seed) only classifies; a class
-- missing from the seed gets 'unmapped' (the unmapped test warns).
-- Grain sums vehicle_count because the D100 normalization merges CAMION and CAMIÓN into one key.
-- A pair without DANE code keeps its row with NULL codes (D128). registration_year is kept as is
-- (the RUNT sentinels 1900 and 1901 included). All publications are kept.
-- max(load_id): one load_id per publication (D99); a singular test asserts it.
select
    f.publication_year,
    f.publication_month,
    f.department_name_norm,
    f.municipality_name_norm,
    f.service_name,
    f.vehicle_class_norm,
    f.registration_year,
    f.dane_department_code,
    f.dane_municipality_code,
    f.dane_match_method,
    case f.service_name
        when 'PARTICULAR' then 'particular'
        when 'PÚBLICO' then 'fleet'
    end as demand_segment,
    coalesce(c.vehicle_group, 'unmapped') as vehicle_group,
    sum(f.vehicle_count)::bigint as active_vehicle_count,
    max(f.load_id) as load_id
from {{ ref('fct_vehicle_fleet_snapshot_dane') }} as f
left join {{ ref('vehicle_class_demand_scope') }} as c
    on c.vehicle_class_norm = f.vehicle_class_norm
where f.vehicle_status = 'ACTIVO'
  and f.service_name in ('PARTICULAR', 'PÚBLICO')
group by
    f.publication_year,
    f.publication_month,
    f.department_name_norm,
    f.municipality_name_norm,
    f.service_name,
    f.vehicle_class_norm,
    f.registration_year,
    f.dane_department_code,
    f.dane_municipality_code,
    f.dane_match_method,
    c.vehicle_group
