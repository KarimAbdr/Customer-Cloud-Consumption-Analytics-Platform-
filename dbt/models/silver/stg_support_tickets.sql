select
    customer_id,
    cast(month as date) as ticket_month,
    ticket_count
from {{ source('bronze', 'support_tickets') }}
