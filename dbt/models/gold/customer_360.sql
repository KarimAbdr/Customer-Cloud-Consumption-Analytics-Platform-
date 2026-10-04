-- Business-facing view of a customer for the dashboard and API.
with usage_overall as (
    select
        customer_id,
        avg(daily_usage) as avg_daily_usage
    from {{ ref('stg_daily_usage') }}
    group by customer_id
)

select
    f.customer_id,
    f.segment,
    f.employees,
    f.industry,
    k.contract_end_date,
    f.monthly_fee * 12 as annual_contract_value,
    u.avg_daily_usage,
    f.usage_trend_ratio,
    f.total_tickets,
    f.usage_trend_ratio < 0.85 as is_at_risk,
    f.is_churned
from {{ ref('customer_features') }} as f
inner join {{ ref('stg_contracts') }} as k on f.customer_id = k.customer_id
inner join usage_overall as u on f.customer_id = u.customer_id
