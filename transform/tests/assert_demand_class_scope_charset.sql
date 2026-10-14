{{ config(tags=['vehicle_fleet', 'divipola']) }}
-- D133: seed keys must already be in normalized form (same charset as D100), otherwise they would
-- never match the normalized RUNT class and the group would silently fall to 'unmapped'.
select vehicle_class_norm
from {{ ref('vehicle_class_demand_scope') }}
where vehicle_class_norm !~ '^[A-Z0-9 ,.()-]+$'
   or vehicle_class_norm <> {{ normalize_text('vehicle_class_norm') }}
