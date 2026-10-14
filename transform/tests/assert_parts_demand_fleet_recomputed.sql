{{ config(tags=['vehicle_fleet', 'divipola', 'parts_demand']) }}
-- D132: fct_parts_demand_fleet equals an independent recomputation from staging + class seed +
-- DANE map (EXCEPT ALL in both directions): any difference in rows or counts fails.
with recomputed as (
    select
        s.publication_year,
        s.publication_month,
        s.department_name_norm,
        s.municipality_name_norm,
        s.service_name,
        s.vehicle_class_norm,
        s.registration_year,
        m.dane_department_code,
        m.dane_municipality_code,
        m.match_method as dane_match_method,
        case when s.service_name = 'PARTICULAR' then 'particular' else 'fleet' end as demand_segment,
        coalesce(c.vehicle_group, 'unmapped') as vehicle_group,
        sum(s.vehicle_count)::bigint as active_vehicle_count,
        max(s.load_id) as load_id
    from {{ ref('stg_vehicle_fleet_snapshot') }} as s
    left join {{ ref('map_runt_municipality_dane') }} as m
        on m.department_name_norm = s.department_name_norm
        and m.municipality_name_norm = s.municipality_name_norm
    left join {{ ref('vehicle_class_demand_scope') }} as c
        on c.vehicle_class_norm = s.vehicle_class_norm
    where s.vehicle_status = 'ACTIVO'
      and s.service_name in ('PARTICULAR', 'PÚBLICO')
    group by
        s.publication_year, s.publication_month, s.department_name_norm,
        s.municipality_name_norm, s.service_name, s.vehicle_class_norm, s.registration_year,
        m.dane_department_code, m.dane_municipality_code, m.match_method, c.vehicle_group
),

mart as (
    select
        publication_year, publication_month, department_name_norm, municipality_name_norm,
        service_name, vehicle_class_norm, registration_year, dane_department_code,
        dane_municipality_code, dane_match_method, demand_segment, vehicle_group,
        active_vehicle_count, load_id
    from {{ ref('fct_parts_demand_fleet') }}
)

(select * from recomputed except all select * from mart)
union all
(select * from mart except all select * from recomputed)
