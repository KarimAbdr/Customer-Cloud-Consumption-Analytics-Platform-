---
title: Customer 360 Analytics
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Customer 360 & Cloud Consumption Analytics

Live demo of a data and ML platform on **synthetic** B2B SaaS data: bronze/silver/gold layers
built with dbt on DuckDB, a LightGBM churn model tracked with MLflow, a FastAPI service and this
Streamlit dashboard.

The dashboard talks only to the API. Customer data is generated, there is no real customer
information.

Source code, architecture and tests: https://github.com/KarimAbdr/Customer-Cloud-Consumption-Analytics-Platform-
