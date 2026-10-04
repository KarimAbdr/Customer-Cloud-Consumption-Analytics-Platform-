-- One row per customer: ML features over the observation window plus the churn target.
with usage_bounds as (
    select
        customer_id,
        min(usage_date) as first_date,
        max(usage_date) as last_date
    from {{ ref('stg_daily_usage') }}
    group by customer_id
),

usage_features as (
    select
        u.customer_id,
        avg(case when u.usage_date < b.first_date + 30 then u.daily_usage end)
            as usage_first_30d_avg,
        avg(case when u.usage_date > b.last_date - 30 then u.daily_usage end)
            as usage_last_30d_avg,
        -- DuckDB dayofweek: Sunday = 0, Saturday = 6
        sum(case when dayofweek(u.usage_date) in (0, 6) then u.daily_usage else 0 end)
        / sum(u.daily_usage) as weekend_usage_share,
        max(u.daily_usage) / avg(u.daily_usage) as usage_peak_ratio
    from {{ ref('stg_daily_usage') }} as u
    inner join usage_bounds as b on u.customer_id = b.customer_id
    group by u.customer_id
),

ticket_features as (
    select
        customer_id,
        sum(ticket_count) as total_tickets,
        avg(ticket_count) as avg_monthly_tickets
    from {{ ref('stg_support_tickets') }}
    group by customer_id
)

select
    c.customer_id,
    c.segment,
    c.employees,
    c.industry,
    k.term_months,
    k.monthly_fee,
    f.usage_first_30d_avg,
    f.usage_last_30d_avg,
    f.usage_last_30d_avg / f.usage_first_30d_avg as usage_trend_ratio,
    f.weekend_usage_share,
    f.usage_peak_ratio,
    coalesce(t.total_tickets, 0) as total_tickets,
    coalesce(t.avg_monthly_tickets, 0) as avg_monthly_tickets,
    l.is_churned
from {{ ref('stg_customers') }} as c
inner join {{ ref('stg_contracts') }} as k on c.customer_id = k.customer_id
inner join usage_features as f on c.customer_id = f.customer_id
left join ticket_features as t on c.customer_id = t.customer_id
inner join {{ ref('stg_churn_labels') }} as l on c.customer_id = l.customer_id
