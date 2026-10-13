{{ config(tags=['vehicle_fleet', 'divipola']) }}
-- D126/D128: an exception row has a 5-digit code, except not_in_divipola rows, which have none
-- (and are the only ones that may be empty). Keys must already be in normalized form, otherwise
-- they would never match the (normalized) RUNT names and the exception would silently do nothing.
select
    department_name_norm, municipality_name_norm, dane_municipality_code, reason
from {{ ref('runt_municipality_dane_exception') }}
where (reason = 'not_in_divipola') <> (nullif(btrim(dane_municipality_code), '') is null)
   or (nullif(btrim(dane_municipality_code), '') is not null
       and dane_municipality_code !~ '^[0-9]{5}$')
   or department_name_norm <> {{ normalize_text('department_name_norm') }}
   or municipality_name_norm <> {{ normalize_text('municipality_name_norm') }}
