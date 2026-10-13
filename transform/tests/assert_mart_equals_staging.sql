{{ config(tags=['fx_rate']) }}
-- The mart is a copy of staging today: any difference (including duplicates) in either direction fails.
(select * from {{ ref('stg_fx_rate') }} except all select * from {{ ref('fct_fx_rate_daily') }})
union all
(select * from {{ ref('fct_fx_rate_daily') }} except all select * from {{ ref('stg_fx_rate') }})
