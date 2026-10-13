{{ config(tags=['divipola']) }}
-- D125: DIVIPOLA lists 1,122 codes (2026-10-13). A snapshot far below that is a truncated load.
select count(*) as n_rows
from {{ ref('stg_divipola_municipality') }}
having count(*) < 1100
