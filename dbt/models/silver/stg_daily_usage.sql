select
    customer_id,
    cast(usage_date as date) as usage_date,
    daily_usage
from {{ source('bronze', 'daily_usage') }}
