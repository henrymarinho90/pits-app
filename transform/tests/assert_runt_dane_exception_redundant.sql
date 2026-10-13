{{ config(tags=['vehicle_fleet', 'divipola'], severity='warn') }}
-- D126: an exception with the same code the automatic match gives is redundant (the RUNT or DANE
-- renamed something so that the names now agree). Warn: delete the row in a PR.
select
    e.department_name_norm, e.municipality_name_norm, e.dane_municipality_code
from {{ ref('runt_municipality_dane_exception') }} as e
inner join {{ ref('dim_municipality') }} as d
    on d.department_name_norm = e.department_name_norm
    and d.municipality_name_norm = e.municipality_name_norm
where nullif(btrim(e.dane_municipality_code), '') = d.dane_municipality_code
