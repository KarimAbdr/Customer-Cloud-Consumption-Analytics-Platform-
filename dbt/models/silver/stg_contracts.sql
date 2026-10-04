select
    customer_id,
    cast(start_date as date) as contract_start_date,
    cast(end_date as date) as contract_end_date,
    term_months,
    monthly_fee
from {{ source('bronze', 'contracts') }}
