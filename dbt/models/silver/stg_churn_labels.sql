select
    customer_id,
    cast(churned as boolean) as is_churned
from {{ source('bronze', 'churn_labels') }}
