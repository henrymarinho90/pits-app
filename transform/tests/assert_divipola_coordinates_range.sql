{{ config(tags=['divipola']) }}
-- D125: Colombia spans latitude -4.2..13.4 and longitude -81.8..-66.8 (DIVIPOLA 2026-10-13); the
-- bounds leave a small margin. A swapped pair or a lost decimal comma lands outside.
select municipality_code, municipality_name, longitude, latitude
from {{ ref('stg_divipola_municipality') }}
where latitude not between -5 and 14
   or longitude not between -82 and -66
