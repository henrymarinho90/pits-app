{{ config(tags=['fleet_brand', 'brand_synthetic']) }}
-- D143: Hamilton keeps every assigned count within 1 of its quota: |synthetic_vehicle_count -
-- allocation_quota| < 1 on every calibrated row. 'SIN CALIBRACION' rows carry the whole N as
-- their quota (difference 0) and are covered by the same rule.
select
    publication_year,
    publication_month,
    department_name_norm,
    municipality_name_norm,
    vehicle_class_norm,
    brand_norm,
    synthetic_vehicle_count,
    allocation_quota
from {{ ref('fct_synthetic_brand_fleet') }}
where abs(synthetic_vehicle_count - allocation_quota) >= 1
