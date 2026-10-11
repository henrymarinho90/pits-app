select
    rate_date,
    currency_from,
    currency_to,
    rate,
    source_system,
    source_reference,
    load_id
from {{ ref('stg_fx_rate') }}
