# Great Britain Dispatch Readiness and Operating Margin Intelligence Dashboard

<img width="1232" height="882" alt="neso" src="https://github.com/user-attachments/assets/dae490ea-5068-4343-a33e-1e222dd0b6b3" />


<img width="1536" height="855" alt="dispatch monitoring" src="https://github.com/user-attachments/assets/76c62332-97c3-49db-89e3-e7a7e0cdaaff" />

A cloud-based electricity-system monitoring application built using publicly available National Energy System Operator System Operating Plan data for Great Britain.

The project collects, processes and stores System Operating Plan records, calculates operational readiness indicators and presents them through an interactive Plotly Dash dashboard.

## Live application

[gb-dispatch-readiness-dashboard](https://neso-gb-dispatch-readiness-kamil-hpaqe7d2eucebfa2.germanywestcentral-01.azurewebsites.net)

> The application is hosted on the Azure App Service.
📖 Read the full Medium article
https://lnkd.in/dqvsp8Gb 
---

## Project scope

The dashboard provides an analytical view of:

- electricity-system demand
- operating-margin conditions
- standing-reserve sufficiency
- reserve shortfall or surplus
- system imbalance
- dispatch headroom
- Cardinal Point performance
- operational Watch and Severe conditions
- overall system-readiness status

The application is designed as an independent analytical and decision-support prototype. It is not an official NESO operational platform.

---

## Data pipeline

```text
NESO System Operating Plan API
                ↓
Python data collector
                ↓
Data cleaning and transformation
                ↓
Operational indicator calculation
                ↓
Supabase PostgreSQL database
                ↓
Plotly Dash dashboard
                ↓
GitHub Actions CI/CD
                ↓
Microsoft Azure App Service
