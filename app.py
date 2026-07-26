
import os
import pandas as pd
from sqlalchemy import create_engine

import dash
from dash import dcc, html, dash_table, Input, Output
import plotly.express as px
import plotly.graph_objects as go


TABLE_NAME = "neso_sop_readiness_snapshots"


def get_database_engine():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is missing.")

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg2://",
            1
        )

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"sslmode": "require"}
    )

    return engine


def load_data():
    engine = get_database_engine()

    query = f"""
    SELECT
        sop_datetime,
        report_date,
        latest_version,
        latest_status,
        cardinal_point,
        customer_demand_forecast,
        total_sop_demand,
        standing_reserve_requirement,
        standing_reserve_availability,
        reserve_coverage_ratio,
        reserve_gap_mw,
        total_positive_reserve,
        total_negative_reserve,
        positive_residual,
        negative_residual,
        imbalance,
        absolute_imbalance_mw,
        contingency_requirement,
        operating_margin_surplus,
        trigger_level,
        margin_vs_trigger_mw,
        total_temx,
        total_teol,
        total_temi,
        dispatch_headroom_mw,
        margin_score_v2,
        reserve_score_v2,
        imbalance_score_v2,
        dispatch_headroom_score_v2,
        system_readiness_score_v2,
        system_readiness_status_v2,
        margin_watch_flag,
        reserve_watch_flag,
        headroom_watch_flag,
        imbalance_watch_flag,
        margin_severe_flag,
        reserve_severe_flag,
        headroom_severe_flag,
        imbalance_severe_flag,
        watch_flag_count,
        severe_flag_count,
        operational_attention_summary,
        collected_at
    FROM {TABLE_NAME}
    ORDER BY sop_datetime ASC;
    """

    df = pd.read_sql_query(query, engine)

    df["sop_datetime"] = pd.to_datetime(df["sop_datetime"], errors="coerce", utc=True)
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce", utc=True)
    df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce", utc=True)

    return df


def empty_figure(title):
    fig = go.Figure()
    fig.update_layout(
        title=title,
        template="plotly_white",
        height=420,
        annotations=[
            dict(
                text="No data available",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=18)
            )
        ]
    )
    return fig


def kpi_card(title, value, subtitle=""):
    return html.Div(
        className="kpi-card",
        children=[
            html.Div(title, className="kpi-title"),
            html.Div(value, className="kpi-value"),
            html.Div(subtitle, className="kpi-subtitle")
        ]
    )


app = dash.Dash(__name__)
app.title = "NESO Dispatch Readiness Monitor"
server = app.server


app.layout = html.Div(
    className="page",
    children=[
        html.Div(
            className="hero",
            children=[
                html.Div(
                    children=[
                        html.H1("NESO Dispatch Readiness and Operating Margin Intelligence Dashboard"),
                        html.P(
                            "A cloud-based dashboard for monitoring Great Britain system readiness using NESO System Operating Plan data."
                        )
                    ]
                ),
                html.Div(
                    className="hero-badge",
                    children="NESO SOP • Supabase • GitHub Actions • Dash"
                )
            ]
        ),

        html.Div(
            className="controls",
            children=[
                html.Div(
                    children=[
                        html.Label("Cardinal point"),
                        dcc.Dropdown(
                            id="cardinal-filter",
                            options=[],
                            value="All",
                            clearable=False
                        )
                    ]
                ),
                html.Div(
                    children=[
                        html.Label("Readiness status"),
                        dcc.Dropdown(
                            id="status-filter",
                            options=[],
                            value="All",
                            clearable=False
                        )
                    ]
                ),
                html.Div(
                    children=[
                        html.Label("Refresh data"),
                        html.Button("Refresh now", id="refresh-button", n_clicks=0)
                    ]
                )
            ]
        ),

        dcc.Interval(
            id="auto-refresh",
            interval=5 * 60 * 1000,
            n_intervals=0
        ),

        html.Div(id="kpi-row", className="kpi-grid"),

        html.Div(
            className="chart-grid",
            children=[
                dcc.Graph(id="readiness-trend"),
                dcc.Graph(id="margin-trend"),
                dcc.Graph(id="reserve-trend"),
                dcc.Graph(id="cardinal-risk")
            ]
        ),

        html.Div(
            className="section",
            children=[
                html.H2("Latest SOP readiness records"),
                dash_table.DataTable(
                    id="latest-table",
                    page_size=10,
                    style_table={"overflowX": "auto"},
                    style_cell={
                        "fontFamily": "Arial",
                        "fontSize": "13px",
                        "padding": "8px",
                        "textAlign": "left"
                    },
                    style_header={
                        "fontWeight": "bold",
                        "backgroundColor": "#f3f4f6"
                    },
                    style_data_conditional=[
                        {
                            "if": {"filter_query": "{system_readiness_status_v2} = Critical"},
                            "backgroundColor": "#fee2e2",
                            "color": "#7f1d1d"
                        },
                        {
                            "if": {"filter_query": "{system_readiness_status_v2} = Tight"},
                            "backgroundColor": "#ffedd5",
                            "color": "#7c2d12"
                        },
                        {
                            "if": {"filter_query": "{system_readiness_status_v2} = Watch"},
                            "backgroundColor": "#fef9c3",
                            "color": "#713f12"
                        },
                        {
                            "if": {"filter_query": "{system_readiness_status_v2} = Comfortable"},
                            "backgroundColor": "#dcfce7",
                            "color": "#14532d"
                        }
                    ]
                )
            ]
        ),

        html.Div(
            className="footer",
            children=[
                "Data source: NESO System Operating Plan open data. ",
                "Dashboard created by Kamil Ridwan Kehinde."
            ]
        )
    ]
)


@app.callback(
    Output("cardinal-filter", "options"),
    Output("status-filter", "options"),
    Output("cardinal-filter", "value"),
    Output("status-filter", "value"),
    Input("auto-refresh", "n_intervals"),
    Input("refresh-button", "n_clicks")
)
def update_filter_options(_, __):
    df = load_data()

    cardinal_options = [{"label": "All", "value": "All"}]
    status_options = [{"label": "All", "value": "All"}]

    if not df.empty:
        cardinal_options += [
            {"label": str(x), "value": str(x)}
            for x in sorted(df["cardinal_point"].dropna().unique())
        ]

        status_order = ["Comfortable", "Watch", "Tight", "Critical", "Unknown"]
        statuses = [s for s in status_order if s in set(df["system_readiness_status_v2"].dropna())]

        status_options += [
            {"label": str(x), "value": str(x)}
            for x in statuses
        ]

    return cardinal_options, status_options, "All", "All"


@app.callback(
    Output("kpi-row", "children"),
    Output("readiness-trend", "figure"),
    Output("margin-trend", "figure"),
    Output("reserve-trend", "figure"),
    Output("cardinal-risk", "figure"),
    Output("latest-table", "data"),
    Output("latest-table", "columns"),
    Input("cardinal-filter", "value"),
    Input("status-filter", "value"),
    Input("auto-refresh", "n_intervals"),
    Input("refresh-button", "n_clicks")
)
def update_dashboard(selected_cardinal, selected_status, _, __):
    df = load_data()

    if df.empty:
        return (
            [
                kpi_card("Total records", "0"),
                kpi_card("Latest SOP time", "N/A"),
                kpi_card("Latest readiness", "N/A"),
                kpi_card("Latest margin", "N/A")
            ],
            empty_figure("System readiness trend"),
            empty_figure("Operating margin trend"),
            empty_figure("Reserve coverage trend"),
            empty_figure("Average readiness by cardinal point"),
            [],
            []
        )

    filtered_df = df.copy()

    if selected_cardinal and selected_cardinal != "All":
        filtered_df = filtered_df[filtered_df["cardinal_point"].astype(str) == selected_cardinal]

    if selected_status and selected_status != "All":
        filtered_df = filtered_df[filtered_df["system_readiness_status_v2"].astype(str) == selected_status]

    if filtered_df.empty:
        return (
            [
                kpi_card("Filtered records", "0"),
                kpi_card("Latest SOP time", "N/A"),
                kpi_card("Latest readiness", "N/A"),
                kpi_card("Latest margin", "N/A")
            ],
            empty_figure("System readiness trend"),
            empty_figure("Operating margin trend"),
            empty_figure("Reserve coverage trend"),
            empty_figure("Average readiness by cardinal point"),
            [],
            []
        )

    latest = filtered_df.sort_values("sop_datetime").iloc[-1]

    latest_time = latest["sop_datetime"].strftime("%d %b %Y %H:%M UTC")
    latest_score = f"{latest['system_readiness_score_v2']:.1f}"
    latest_status = latest["system_readiness_status_v2"]
    latest_margin = f"{latest['operating_margin_surplus']:,.0f} MW"
    latest_reserve = f"{latest['reserve_coverage_ratio']:.2f}"
    latest_headroom = f"{latest['dispatch_headroom_mw']:,.0f} MW"

    kpis = [
        kpi_card("Total records", f"{len(filtered_df):,}", "Filtered SOP records"),
        kpi_card("Latest SOP time", latest_time, f"Cardinal point: {latest['cardinal_point']}"),
        kpi_card("Readiness score", latest_score, latest_status),
        kpi_card("Operating margin", latest_margin, "Surplus against requirement"),
        kpi_card("Reserve coverage", latest_reserve, "Availability / requirement"),
        kpi_card("Dispatch headroom", latest_headroom, "TEMX minus TEOL")
    ]

    readiness_fig = px.line(
        filtered_df,
        x="sop_datetime",
        y="system_readiness_score_v2",
        color="system_readiness_status_v2",
        markers=True,
        title="System readiness score over time",
        labels={
            "sop_datetime": "SOP datetime",
            "system_readiness_score_v2": "Readiness score",
            "system_readiness_status_v2": "Status"
        }
    )

    for y, label in [(75, "Comfortable"), (55, "Watch"), (35, "Tight")]:
        readiness_fig.add_hline(
            y=y,
            line_dash="dash",
            annotation_text=label,
            annotation_position="top left"
        )

    readiness_fig.update_layout(template="plotly_white", height=430)

    margin_fig = go.Figure()
    margin_fig.add_trace(
        go.Scatter(
            x=filtered_df["sop_datetime"],
            y=filtered_df["operating_margin_surplus"],
            mode="lines+markers",
            name="Operating margin surplus"
        )
    )
    margin_fig.add_trace(
        go.Scatter(
            x=filtered_df["sop_datetime"],
            y=filtered_df["trigger_level"],
            mode="lines",
            name="Trigger level"
        )
    )
    margin_fig.update_layout(
        title="Operating margin surplus versus trigger level",
        xaxis_title="SOP datetime",
        yaxis_title="MW",
        template="plotly_white",
        height=430
    )

    reserve_fig = go.Figure()
    reserve_fig.add_trace(
        go.Scatter(
            x=filtered_df["sop_datetime"],
            y=filtered_df["standing_reserve_requirement"],
            mode="lines",
            name="Reserve requirement"
        )
    )
    reserve_fig.add_trace(
        go.Scatter(
            x=filtered_df["sop_datetime"],
            y=filtered_df["standing_reserve_availability"],
            mode="lines+markers",
            name="Reserve availability"
        )
    )
    reserve_fig.update_layout(
        title="Standing reserve availability versus requirement",
        xaxis_title="SOP datetime",
        yaxis_title="MW",
        template="plotly_white",
        height=430
    )

    cardinal_summary = (
        filtered_df
        .groupby("cardinal_point", as_index=False)
        .agg(
            average_readiness=("system_readiness_score_v2", "mean"),
            average_margin=("operating_margin_surplus", "mean"),
            severe_flags=("severe_flag_count", "sum")
        )
        .sort_values("average_readiness")
    )

    cardinal_fig = px.bar(
        cardinal_summary,
        x="cardinal_point",
        y="average_readiness",
        color="average_readiness",
        title="Average readiness score by cardinal point",
        labels={
            "cardinal_point": "Cardinal point",
            "average_readiness": "Average readiness score"
        }
    )
    cardinal_fig.update_layout(template="plotly_white", height=430)

    latest_table = (
        filtered_df
        .sort_values("sop_datetime", ascending=False)
        .head(20)
        [[
            "sop_datetime",
            "cardinal_point",
            "total_sop_demand",
            "operating_margin_surplus",
            "reserve_coverage_ratio",
            "dispatch_headroom_mw",
            "absolute_imbalance_mw",
            "system_readiness_score_v2",
            "system_readiness_status_v2",
            "operational_attention_summary",
            "collected_at"
        ]]
        .copy()
    )

    latest_table["sop_datetime"] = latest_table["sop_datetime"].dt.strftime("%d %b %Y %H:%M")
    latest_table["collected_at"] = latest_table["collected_at"].dt.strftime("%d %b %Y %H:%M")

    columns = [
        {"name": "SOP datetime", "id": "sop_datetime"},
        {"name": "Cardinal point", "id": "cardinal_point"},
        {"name": "Demand MW", "id": "total_sop_demand"},
        {"name": "Margin MW", "id": "operating_margin_surplus"},
        {"name": "Reserve coverage", "id": "reserve_coverage_ratio"},
        {"name": "Headroom MW", "id": "dispatch_headroom_mw"},
        {"name": "Abs imbalance MW", "id": "absolute_imbalance_mw"},
        {"name": "Readiness score", "id": "system_readiness_score_v2"},
        {"name": "Status", "id": "system_readiness_status_v2"},
        {"name": "Attention", "id": "operational_attention_summary"},
        {"name": "Collected at", "id": "collected_at"}
    ]

    return (
        kpis,
        readiness_fig,
        margin_fig,
        reserve_fig,
        cardinal_fig,
        latest_table.to_dict("records"),
        columns
    )


app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body {
                margin: 0;
                font-family: Arial, Helvetica, sans-serif;
                background: #f5f7fb;
                color: #111827;
            }

            .page {
                max-width: 1400px;
                margin: 0 auto;
                padding: 28px;
            }

            .hero {
                background: linear-gradient(135deg, #0f172a, #1e3a8a);
                color: white;
                padding: 32px;
                border-radius: 24px;
                display: flex;
                justify-content: space-between;
                gap: 24px;
                align-items: center;
                box-shadow: 0 16px 40px rgba(15, 23, 42, 0.18);
            }

            .hero h1 {
                margin: 0 0 12px 0;
                font-size: 34px;
                line-height: 1.2;
            }

            .hero p {
                margin: 0;
                font-size: 16px;
                color: #dbeafe;
                max-width: 850px;
            }

            .hero-badge {
                background: rgba(255, 255, 255, 0.12);
                padding: 14px 18px;
                border-radius: 999px;
                white-space: nowrap;
                font-size: 14px;
                color: #e0f2fe;
            }

            .controls {
                display: grid;
                grid-template-columns: 1fr 1fr 180px;
                gap: 18px;
                background: white;
                margin: 24px 0;
                padding: 20px;
                border-radius: 18px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
            }

            .controls label {
                display: block;
                font-weight: 700;
                margin-bottom: 8px;
                color: #374151;
            }

            button {
                width: 100%;
                height: 38px;
                border: 0;
                border-radius: 8px;
                background: #2563eb;
                color: white;
                font-weight: 700;
                cursor: pointer;
            }

            .kpi-grid {
                display: grid;
                grid-template-columns: repeat(6, 1fr);
                gap: 16px;
                margin-bottom: 24px;
            }

            .kpi-card {
                background: white;
                padding: 18px;
                border-radius: 18px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
                border: 1px solid #e5e7eb;
            }

            .kpi-title {
                font-size: 13px;
                color: #6b7280;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .kpi-value {
                font-size: 25px;
                font-weight: 800;
                margin-top: 8px;
                color: #111827;
            }

            .kpi-subtitle {
                font-size: 13px;
                margin-top: 6px;
                color: #6b7280;
            }

            .chart-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 18px;
                margin-bottom: 24px;
            }

            .chart-grid .dash-graph {
                background: white;
                border-radius: 18px;
                padding: 12px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
            }

            .section {
                background: white;
                padding: 22px;
                border-radius: 18px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
                margin-bottom: 24px;
            }

            .section h2 {
                margin-top: 0;
            }

            .footer {
                color: #6b7280;
                font-size: 13px;
                text-align: center;
                padding: 20px;
            }

            @media (max-width: 1100px) {
                .kpi-grid {
                    grid-template-columns: repeat(3, 1fr);
                }

                .chart-grid {
                    grid-template-columns: 1fr;
                }

                .controls {
                    grid-template-columns: 1fr;
                }

                .hero {
                    flex-direction: column;
                    align-items: flex-start;
                }
            }

            @media (max-width: 700px) {
                .page {
                    padding: 14px;
                }

                .kpi-grid {
                    grid-template-columns: 1fr;
                }

                .hero h1 {
                    font-size: 24px;
                }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""


if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=int(os.environ.get("PORT", 8050)), debug=False)
