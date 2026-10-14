-- D139: regional vehicle counts as loaded, plus normalized keys (_norm, D100 macro), the resolved
-- brand and the calibration scope of every row.
-- Brand resolution, in this order:
--   1) brand_alias on the normalized brand (e.g. AUTECO BAJAJ -> BAJAJ);
--   2) if the resulting brand is still AUTECO (the distributor, not a brand), the exact normalized
--      line is looked up in auteco_line_brand_map; a line without a row is SIN ASIGNAR and warns
--      (brand_resolution = auteco_unmapped). Rows listed as SIN ASIGNAR in the seed are explicit.
-- Scope (calibration filter, D52/D59/D139): a class that is excluded or not in the class map
-- is excluded_class; Boyaca keeps ACTIVO (status) and PARTICULAR (service); Risaralda does not
-- publish service or status (NULL), so no filter applies. Status is evaluated before service.
with base as (
    select
        l.source_system,
        l.rows_updated,
        l.vehicle_class,
        l.brand,
        l.line,
        l.service_name,
        l.vehicle_status,
        l.vehicle_count,
        l.source_reference,
        l.load_id,
        {{ normalize_text('l.vehicle_class') }} as vehicle_class_norm,
        {{ normalize_text('l.brand') }} as source_brand_norm,
        {{ normalize_text('l.line') }} as line_norm,
        {{ normalize_text('l.service_name') }} as service_name_norm,
        {{ normalize_text('l.vehicle_status') }} as vehicle_status_norm
    from {{ source('landing', 'regional_fleet_brand_count') }} as l
),

aliased as (
    select
        b.*,
        coalesce(a.brand_norm, b.source_brand_norm) as alias_brand_norm,
        a.brand_norm is not null as alias_applied
    from base as b
    left join {{ ref('brand_alias') }} as a
        on a.source_brand_norm = b.source_brand_norm
),

resolved as (
    select
        x.*,
        case
            when x.alias_brand_norm = 'AUTECO' then coalesce(m.real_brand, 'SIN ASIGNAR')
            else x.alias_brand_norm
        end as brand_norm,
        case
            when x.alias_brand_norm = 'AUTECO' and m.line_norm is not null then 'auteco_map'
            when x.alias_brand_norm = 'AUTECO' then 'auteco_unmapped'
            when x.alias_applied then 'alias'
            else 'as_published'
        end as brand_resolution,
        m.evidence as brand_evidence
    from aliased as x
    left join {{ ref('auteco_line_brand_map') }} as m
        on x.alias_brand_norm = 'AUTECO'
        and m.line_norm = x.line_norm
),

classed as (
    select
        r.*,
        coalesce(c.vehicle_class_norm, 'unmapped') as calibration_class_norm
    from resolved as r
    left join {{ ref('regional_vehicle_class_map') }} as c
        on c.source_system = r.source_system
        and c.source_class_norm = r.vehicle_class_norm
)

select
    source_system,
    rows_updated,
    vehicle_class,
    brand,
    line,
    service_name,
    vehicle_status,
    vehicle_count,
    source_reference,
    load_id,
    vehicle_class_norm,
    source_brand_norm,
    line_norm,
    service_name_norm,
    vehicle_status_norm,
    brand_norm,
    brand_resolution,
    brand_evidence,
    calibration_class_norm,
    case
        when calibration_class_norm in ('excluded', 'unmapped') then 'excluded_class'
        when vehicle_status_norm is not null and vehicle_status_norm <> 'ACTIVO'
            then 'excluded_status'
        when service_name_norm is not null and service_name_norm <> 'PARTICULAR'
            then 'excluded_service'
        else 'included'
    end as scope_status
from classed
