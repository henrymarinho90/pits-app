-- D125: every landing column as published, with the decimal-comma coordinates converted to numeric
-- (landing CHECKs guarantee the format) plus normalized join keys (_norm). The same normalize_text
-- macro as the RUNT staging (D100) makes the match with the RUNT names symmetric.
select
    department_code,
    department_name,
    municipality_code,
    municipality_name,
    municipality_type,
    replace(longitude, ',', '.')::numeric as longitude,
    replace(latitude, ',', '.')::numeric as latitude,
    source_system,
    source_reference,
    load_id,
    {{ normalize_text('department_name') }} as department_name_norm,
    {{ normalize_text('municipality_name') }} as municipality_name_norm
from {{ source('landing', 'divipola_municipality') }}
