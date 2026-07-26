
import os
import requests
import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values


RESOURCE_ID = "e51f2721-00ab-4182-9cae-3c973e854aa8"
API_URL = "https://api.neso.energy/api/3/action/datastore_search"
TABLE_NAME = "neso_sop_readiness_snapshots"


def fetch_latest_sop_records(limit=500):
    params = {
        "resource_id": RESOURCE_ID,
        "limit": limit,
        "sort": "sop_datetime desc"
    }

    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    if not data.get("success"):
        raise RuntimeError("NESO API returned success=False")

    records = data["result"]["records"]
    return pd.DataFrame(records)


def clean_sop_data(df_raw):
    df = df_raw.copy()

    date_columns = [
        "sop_datetime",
        "report_date",
        "sop_report_creation_time_gmt",
        "sop_d_and_c_time_gmt"
    ]

    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    numeric_columns = [
        col for col in df.columns
        if col not in ["latest_status", "cardinal_point"]
        and col not in date_columns
    ]

    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def robust_score_higher_is_better(series):
    lower = series.quantile(0.05)
    upper = series.quantile(0.95)

    if pd.isna(lower) or pd.isna(upper) or lower == upper:
        return pd.Series(50, index=series.index)

    score = 100 * (series - lower) / (upper - lower)
    return score.clip(lower=0, upper=100)


def robust_score_lower_is_better(series):
    higher_score = robust_score_higher_is_better(series)
    return 100 - higher_score


def classify_readiness(score):
    if pd.isna(score):
        return "Unknown"
    if score >= 75:
        return "Comfortable"
    if score >= 55:
        return "Watch"
    if score >= 35:
        return "Tight"
    return "Critical"


def build_attention_summary(row):
    if row["severe_flag_count"] > 0:
        return f"{int(row['severe_flag_count'])} severe flag(s)"
    if row["watch_flag_count"] > 0:
        return f"{int(row['watch_flag_count'])} watch flag(s)"
    return "No major flag"


def build_kpi_dataframe(df_latest):
    kpi_columns = [
        "_id",
        "sop_datetime",
        "report_date",
        "latest_version",
        "latest_status",
        "cardinal_point",
        "customer_demand_forcast",
        "total_sop_demand",
        "standing_reserve_requirement",
        "standing_reserve_availability",
        "standing_reserve_shortfall",
        "standing_reserve_excess",
        "percentage_of_standing_reserve_excess",
        "total_positive_reserve",
        "total_negative_reserve",
        "positive_residual",
        "negative_residual",
        "imbalance",
        "contingency_requirement",
        "operating_margin_surplus",
        "trigger_level",
        "total_temx",
        "total_teol",
        "total_temi",
        "BAT_temx",
        "BAT_teol",
        "BAT_temi",
        "SLR_temx",
        "SLR_teol",
        "SLR_temi",
        "ps_temx",
        "ps_teol",
        "ps_temi"
    ]

    available_columns = [col for col in kpi_columns if col in df_latest.columns]
    df_kpi = df_latest[available_columns].copy()

    df_kpi["reserve_coverage_ratio"] = np.where(
        df_kpi["standing_reserve_requirement"] > 0,
        df_kpi["standing_reserve_availability"] / df_kpi["standing_reserve_requirement"],
        np.nan
    )

    df_kpi["reserve_gap_mw"] = (
        df_kpi["standing_reserve_requirement"] -
        df_kpi["standing_reserve_availability"]
    )

    df_kpi["dispatch_headroom_mw"] = (
        df_kpi["total_temx"] -
        df_kpi["total_teol"]
    )

    df_kpi["margin_vs_trigger_mw"] = (
        df_kpi["operating_margin_surplus"] -
        df_kpi["trigger_level"]
    )

    df_kpi["absolute_imbalance_mw"] = df_kpi["imbalance"].abs()

    df_kpi["margin_score_v2"] = robust_score_higher_is_better(
        df_kpi["operating_margin_surplus"]
    )

    df_kpi["reserve_score_v2"] = robust_score_higher_is_better(
        df_kpi["reserve_coverage_ratio"]
    )

    df_kpi["dispatch_headroom_score_v2"] = robust_score_higher_is_better(
        df_kpi["dispatch_headroom_mw"]
    )

    df_kpi["imbalance_score_v2"] = robust_score_lower_is_better(
        df_kpi["absolute_imbalance_mw"]
    )

    df_kpi["system_readiness_score_v2"] = (
        0.35 * df_kpi["margin_score_v2"] +
        0.30 * df_kpi["reserve_score_v2"] +
        0.20 * df_kpi["imbalance_score_v2"] +
        0.15 * df_kpi["dispatch_headroom_score_v2"]
    ).round(1)

    df_kpi["system_readiness_status_v2"] = df_kpi["system_readiness_score_v2"].apply(
        classify_readiness
    )

    df_kpi["margin_watch_flag"] = df_kpi["operating_margin_surplus"] < 1000
    df_kpi["reserve_watch_flag"] = df_kpi["reserve_coverage_ratio"] < 0.90
    df_kpi["headroom_watch_flag"] = df_kpi["dispatch_headroom_mw"] < 1500
    df_kpi["imbalance_watch_flag"] = df_kpi["absolute_imbalance_mw"] > 1000

    df_kpi["margin_severe_flag"] = df_kpi["operating_margin_surplus"] < 500
    df_kpi["reserve_severe_flag"] = df_kpi["reserve_coverage_ratio"] < 0.80
    df_kpi["headroom_severe_flag"] = df_kpi["dispatch_headroom_mw"] < 500
    df_kpi["imbalance_severe_flag"] = df_kpi["absolute_imbalance_mw"] > 2000

    df_kpi["watch_flag_count"] = (
        df_kpi["margin_watch_flag"].astype(int) +
        df_kpi["reserve_watch_flag"].astype(int) +
        df_kpi["headroom_watch_flag"].astype(int) +
        df_kpi["imbalance_watch_flag"].astype(int)
    )

    df_kpi["severe_flag_count"] = (
        df_kpi["margin_severe_flag"].astype(int) +
        df_kpi["reserve_severe_flag"].astype(int) +
        df_kpi["headroom_severe_flag"].astype(int) +
        df_kpi["imbalance_severe_flag"].astype(int)
    )

    df_kpi["operational_attention_summary"] = df_kpi.apply(
        build_attention_summary,
        axis=1
    )

    return df_kpi


def prepare_for_database(df_kpi):
    df_insert = df_kpi.copy()

    rename_map = {
        "_id": "neso_record_id",
        "customer_demand_forcast": "customer_demand_forecast",

        "BAT_temx": "bat_temx",
        "BAT_teol": "bat_teol",
        "BAT_temi": "bat_temi",

        "SLR_temx": "slr_temx",
        "SLR_teol": "slr_teol",
        "SLR_temi": "slr_temi"
    }

    df_insert = df_insert.rename(columns=rename_map)

    supabase_columns = [
        "neso_record_id",
        "sop_datetime",
        "report_date",
        "latest_version",
        "latest_status",
        "cardinal_point",
        "customer_demand_forecast",
        "total_sop_demand",
        "standing_reserve_requirement",
        "standing_reserve_availability",
        "standing_reserve_shortfall",
        "standing_reserve_excess",
        "percentage_of_standing_reserve_excess",
        "total_positive_reserve",
        "total_negative_reserve",
        "positive_residual",
        "negative_residual",
        "imbalance",
        "contingency_requirement",
        "operating_margin_surplus",
        "trigger_level",
        "total_temx",
        "total_teol",
        "total_temi",
        "bat_temx",
        "bat_teol",
        "bat_temi",
        "slr_temx",
        "slr_teol",
        "slr_temi",
        "ps_temx",
        "ps_teol",
        "ps_temi",
        "reserve_coverage_ratio",
        "reserve_gap_mw",
        "dispatch_headroom_mw",
        "margin_vs_trigger_mw",
        "absolute_imbalance_mw",
        "margin_score_v2",
        "reserve_score_v2",
        "imbalance_score_v2",
        "dispatch_headroom_score_v2",
        "system_readiness_score_v2",
        "system_readiness_status_v2",
        "margin_watch_flag",
        "reserve_watch_flag",
        "headroom_watch_flag",
        "imbalance_watch_flag",
        "margin_severe_flag",
        "reserve_severe_flag",
        "headroom_severe_flag",
        "imbalance_severe_flag",
        "watch_flag_count",
        "severe_flag_count",
        "operational_attention_summary"
    ]

    df_insert = df_insert[supabase_columns].copy()
    df_insert = df_insert.replace([np.inf, -np.inf], np.nan)

    return df_insert


def clean_value(value):
    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    if isinstance(value, np.generic):
        return value.item()

    return value


def upsert_to_supabase(df_insert):
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is missing")

    columns = list(df_insert.columns)

    update_columns = [col for col in columns if col != "neso_record_id"]

    update_sql = ", ".join([
        f"{col} = EXCLUDED.{col}" for col in update_columns
    ])

    insert_sql = f"""
    INSERT INTO {TABLE_NAME} ({", ".join(columns)})
    VALUES %s
    ON CONFLICT (neso_record_id)
    DO UPDATE SET
        {update_sql},
        collected_at = NOW();
    """

    records = [
        tuple(clean_value(value) for value in row)
        for row in df_insert.to_numpy()
    ]

    conn = psycopg2.connect(database_url, sslmode="require")
    cur = conn.cursor()

    execute_values(cur, insert_sql, records, page_size=100)

    conn.commit()

    cur.execute(f"""
        SELECT
            COUNT(*) AS total_rows,
            MAX(sop_datetime) AS latest_sop_datetime
        FROM {TABLE_NAME};
    """)

    total_rows, latest_sop_datetime = cur.fetchone()

    cur.close()
    conn.close()

    print("SOP collector completed successfully.")
    print("Rows processed:", len(records))
    print("Total rows in Supabase:", total_rows)
    print("Latest SOP datetime:", latest_sop_datetime)


def main():
    print("Fetching latest NESO SOP records...")
    df_raw = fetch_latest_sop_records(limit=500)

    print("Cleaning raw SOP data...")
    df_latest = clean_sop_data(df_raw)

    print("Building readiness KPI dataframe...")
    df_kpi = build_kpi_dataframe(df_latest)

    print("Preparing records for Supabase...")
    df_insert = prepare_for_database(df_kpi)

    print("Upserting records into Supabase...")
    upsert_to_supabase(df_insert)


if __name__ == "__main__":
    main()
