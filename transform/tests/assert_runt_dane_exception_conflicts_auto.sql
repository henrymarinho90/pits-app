{{ config(tags=['vehicle_fleet', 'divipola']) }}
-- D126: an exception that disagrees with the automatic match is a contradiction, not a refinement:
-- either another code than the automatic one, or "not_in_divipola" for a pair that does exist.
select
    e.department_name_norm, e.municipality_name_norm,
    e.dane_municipality_code as exception_code, d.dane_municipality_code as automatic_code
from {{ ref('runt_municipality_dane_exception') }} as e
inner join {{ ref('dim_municipality') }} as d
    on d.department_name_norm = e.department_name_norm
    and d.municipality_name_norm = e.municipality_name_norm
where nullif(btrim(e.dane_municipality_code), '') is distinct from d.dane_municipality_code
