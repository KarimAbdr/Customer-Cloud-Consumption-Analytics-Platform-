select
    customer_id,
    segment,
    employees,
    coalesce(industry, 'UNKNOWN') as industry
from {{ source('bronze', 'customers') }}
