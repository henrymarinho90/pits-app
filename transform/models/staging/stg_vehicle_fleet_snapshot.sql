-- D100: every landing column as published, plus normalized grouping keys (_norm).
-- Service and status are NOT normalized: they are closed lists guarded by accepted_values.
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
    {{ normalize_text('department_name') }} as department_name_norm,
    {{ normalize_text('municipality_name') }} as municipality_name_norm,
    {{ normalize_text('vehicle_class') }} as vehicle_class_norm
from {{ source('landing', 'vehicle_fleet_snapshot') }}
