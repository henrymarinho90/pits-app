{{ config(tags=['fleet_brand']) }}
-- D139: seed keys and values must already be in normalized form (D100 macro), otherwise they
-- would never match the normalized staging columns and a row would silently fall to unmapped or
-- SIN ASIGNAR. 'excluded' (lower case, class map) is the only literal that is not a RUNT class; 'SIN ASIGNAR'
-- (AUTECO map) is already upper case.
select 'regional_vehicle_class_map.source_class_norm' as seed_column, source_class_norm as value
from {{ ref('regional_vehicle_class_map') }}
where source_class_norm = '' or source_class_norm <> {{ normalize_text('source_class_norm') }}

union all

select 'regional_vehicle_class_map.vehicle_class_norm', vehicle_class_norm
from {{ ref('regional_vehicle_class_map') }}
where vehicle_class_norm = ''
   or (
        vehicle_class_norm <> 'excluded'
        and (
            vehicle_class_norm <> {{ normalize_text('vehicle_class_norm') }}
            or vehicle_class_norm !~ '^[A-Z0-9 ,.()-]+$'
        )
   )

union all

select 'brand_alias.source_brand_norm', source_brand_norm
from {{ ref('brand_alias') }}
where source_brand_norm = '' or source_brand_norm <> {{ normalize_text('source_brand_norm') }}

union all

select 'brand_alias.brand_norm', brand_norm
from {{ ref('brand_alias') }}
where brand_norm = '' or brand_norm <> {{ normalize_text('brand_norm') }}

union all

select 'auteco_line_brand_map.line_norm', line_norm
from {{ ref('auteco_line_brand_map') }}
where line_norm = '' or line_norm <> {{ normalize_text('line_norm') }}

union all

select 'auteco_line_brand_map.real_brand', real_brand
from {{ ref('auteco_line_brand_map') }}
where real_brand = '' or real_brand <> {{ normalize_text('real_brand') }}
   or real_brand = 'AUTECO'

union all

select 'regional_brand_source.dane_department_code', dane_department_code
from {{ ref('regional_brand_source') }}
where dane_department_code !~ '^[0-9]{2}$'
