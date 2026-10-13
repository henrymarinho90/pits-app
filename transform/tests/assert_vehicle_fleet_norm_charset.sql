{{ config(tags=['vehicle_fleet']) }}
-- D100: normalized keys hold only A-Z 0-9 space , . ( ) - (checked on real data: department has
-- A-Z space , . ; municipality A-Z space; class A-Z space . ( )). Anything else (an accent the
-- translate list misses, a new symbol, empty text) fails loudly instead of splitting a group.
select
    department_name, municipality_name, vehicle_class,
    department_name_norm, municipality_name_norm, vehicle_class_norm
from {{ ref('stg_vehicle_fleet_snapshot') }}
where department_name_norm !~ '^[A-Z0-9 ,.()-]+$'
   or municipality_name_norm !~ '^[A-Z0-9 ,.()-]+$'
   or vehicle_class_norm !~ '^[A-Z0-9 ,.()-]+$'
