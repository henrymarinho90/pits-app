-- D142: cell of the synthetic brand breakdown (hito B). One row per (publication, department,
-- municipality, vehicle class) of the LATEST publication of fct_parts_demand_fleet, PARTICULAR
-- segment only (D54, D140; the fleet segment is not split). active_vehicle_count is REAL: the sum
-- over registration_year (P1 = a: the shares do not depend on the year). It is the N that
-- fct_synthetic_brand_fleet must conserve exactly (03 section 30).
-- calibration_status (D144 a): 'calibrated' if the class has a non-NULL pooled_share in
-- fct_regional_brand_share, else 'no_calibration' (the brand mart gives it one SIN CALIBRACION row).
-- Together with fct_regional_brand_weight this is a fleet_brand node that reads a vehicle_fleet
-- node (D145); the dbt tests never reference it from a vehicle_fleet/divipola/parts_demand node.
with latest as (
    select max(publication_year * 100 + publication_month) as publication_key
    from {{ ref('fct_parts_demand_fleet') }}
),

calibrated as (
    select distinct vehicle_class_norm
    from {{ ref('fct_regional_brand_share') }}
    where pooled_share is not null
)

select
    f.publication_year,
    f.publication_month,
    f.department_name_norm,
    f.municipality_name_norm,
    f.vehicle_class_norm,
    f.dane_department_code,
    f.dane_municipality_code,
    f.vehicle_group,
    sum(f.active_vehicle_count)::bigint as active_vehicle_count,
    case when c.vehicle_class_norm is null then 'no_calibration' else 'calibrated' end
        as calibration_status
from {{ ref('fct_parts_demand_fleet') }} as f
inner join latest as l
    on f.publication_year * 100 + f.publication_month = l.publication_key
left join calibrated as c
    on c.vehicle_class_norm = f.vehicle_class_norm
where f.demand_segment = 'particular'
group by
    f.publication_year,
    f.publication_month,
    f.department_name_norm,
    f.municipality_name_norm,
    f.vehicle_class_norm,
    f.dane_department_code,
    f.dane_municipality_code,
    f.vehicle_group,
    c.vehicle_class_norm
