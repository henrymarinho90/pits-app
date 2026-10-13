{{ config(tags=['vehicle_fleet', 'divipola']) }}
-- D127: the enriched mart has exactly the rows of fct_vehicle_fleet_snapshot (a LEFT JOIN never
-- drops a cell and, with a unique map, never duplicates one): any difference in either direction
-- fails, which also makes the counts and the vehicle sums equal.
with fct as (
    select
        publication_year, publication_month, department_name, municipality_name, service_name,
        vehicle_status, vehicle_class, registration_year, vehicle_count, source_system,
        source_reference, load_id, department_name_norm, municipality_name_norm, vehicle_class_norm
    from {{ ref('fct_vehicle_fleet_snapshot') }}
),

enriched as (
    select
        publication_year, publication_month, department_name, municipality_name, service_name,
        vehicle_status, vehicle_class, registration_year, vehicle_count, source_system,
        source_reference, load_id, department_name_norm, municipality_name_norm, vehicle_class_norm
    from {{ ref('fct_vehicle_fleet_snapshot_dane') }}
)

(select * from fct except all select * from enriched)
union all
(select * from enriched except all select * from fct)
