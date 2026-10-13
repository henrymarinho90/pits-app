{{ config(tags=['vehicle_fleet', 'divipola']) }}
-- D126: an exception must point to a code that exists in DIVIPOLA (a typo or a code retired by DANE
-- fails the build; the previous mapping stays).
select e.department_name_norm, e.municipality_name_norm, e.dane_municipality_code
from {{ ref('runt_municipality_dane_exception') }} as e
left join {{ ref('dim_municipality') }} as d
    on d.dane_municipality_code = e.dane_municipality_code
where nullif(btrim(e.dane_municipality_code), '') is not null
  and d.dane_municipality_code is null
