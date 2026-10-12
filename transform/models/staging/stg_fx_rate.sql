select
    rate_date,
    currency_from,
    currency_to,
    rate,
    source_system,
    source_reference,
    load_id
from {{ source('landing', 'fx_rate') }}
