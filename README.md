# NESO Dispatch Readiness and Operating Margin Intelligence Dashboard

This project collects and analyses NESO System Operating Plan data to monitor dispatch readiness, operating margin, reserve sufficiency, imbalance pressure and system readiness conditions for Great Britain.

## Project workflow

NESO System Operating Plan API  
↓  
Python collector  
↓  
Supabase PostgreSQL database  
↓  
GitHub Actions automation  
↓  
Dash dashboard and Render deployment

## Current features

- Collects latest NESO SOP records from the NESO open data API
- Cleans demand, reserve, margin, imbalance and dispatch availability fields
- Calculates derived readiness indicators
- Stores results in Supabase PostgreSQL
- Updates existing records without duplication
- Supports scheduled automation through GitHub Actions

## Main derived indicators

- Reserve coverage ratio
- Reserve gap MW
- Dispatch headroom MW
- Margin versus trigger level
- Absolute imbalance MW
- System readiness score
- Readiness status: Comfortable, Watch, Tight or Critical
- Operational attention flags

## Tech stack

- Python
- Pandas
- NumPy
- Requests
- PostgreSQL
- Supabase
- GitHub Actions
- Dash and Render planned for deployment