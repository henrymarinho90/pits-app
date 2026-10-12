-- Reads staging on purpose (see assert_fx_rate_daily_contiguous).
-- D77: the TRM is quoted as COP per 1 USD; any other pair from that source is a bug.
select rate_date, currency_from, currency_to
from {{ ref('stg_fx_rate') }}
where source_system = 'superfinanciera_trm'
  and (currency_from <> 'USD' or currency_to <> 'COP')
