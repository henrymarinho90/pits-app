-- Reads staging on purpose: a failure blocks the mart build, keeping the previous mart intact.
-- D76: one row per calendar day per pair; any gap makes count(*) < max - min + 1.
select
    currency_from,
    currency_to,
    min(rate_date) as first_date,
    max(rate_date) as last_date,
    count(*) as n_rows
from {{ ref('stg_fx_rate') }}
group by currency_from, currency_to
having count(*) <> max(rate_date) - min(rate_date) + 1
