-- D100: all publications, statuses and services (no ACTIVO filter, no DANE, no service/status
-- normalization). Reads staging on purpose: a failed staging test leaves the previous mart intact.
select
    publication_year,
    publication_month,
    department_name,
    municipality_name,
    service_name,
    vehicle_status,
    vehicle_class,
    registration_year,
    vehicle_count,
    source_system,
    source_reference,
    load_id,
    department_name_norm,
    municipality_name_norm,
    vehicle_class_norm
from {{ ref('stg_vehicle_fleet_snapshot') }}
