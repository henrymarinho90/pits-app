{{ config(tags=['vehicle_fleet', 'divipola'], severity='warn') }}
-- D126: an exception whose pair appears in no publication does nothing (the RUNT renamed or
-- dropped the municipality). Warn: review the row in a PR.
select e.department_name_norm, e.municipality_name_norm, e.dane_municipality_code
from {{ ref('runt_municipality_dane_exception') }} as e
left join (
    select distinct department_name_norm, municipality_name_norm
    from {{ ref('stg_vehicle_fleet_snapshot') }}
) as p
    on p.department_name_norm = e.department_name_norm
    and p.municipality_name_norm = e.municipality_name_norm
where p.department_name_norm is null
