{{ config(tags=['vehicle_fleet', 'divipola'], severity='warn') }}
-- D126: the DIVIPOLA name written in the seed (for the reviewer) must still be the name of that
-- code in the dimension, so a typo in the code, or a rename by DANE, does not go unnoticed.
select
    e.department_name_norm, e.municipality_name_norm, e.dane_municipality_code,
    e.dane_municipality_name as seed_name, d.municipality_name as dimension_name
from {{ ref('runt_municipality_dane_exception') }} as e
inner join {{ ref('dim_municipality') }} as d
    on d.dane_municipality_code = e.dane_municipality_code
where {{ normalize_text('e.dane_municipality_name') }} <> d.municipality_name_norm
