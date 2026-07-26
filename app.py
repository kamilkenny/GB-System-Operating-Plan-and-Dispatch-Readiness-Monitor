
import os
import pandas as pd
from sqlalchemy import create_engine

import dash
from dash import dcc, html, dash_table, Input, Output
import plotly.graph_objects as go


TABLE_NAME = "neso_sop_readiness_snapshots"


STATUS_ORDER = ["Comfortable", "Watch", "Tight", "Critical", "Unknown"]

STATUS_COLOURS = {
    "Comfortable": "#2563eb",
    "Watch": "#f59e0b",
    "Tight": "#10b981",
    "Critical": "#ef4444",
    "Unknown": "#6b7280"
}


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

    return create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"sslmode": "require"}
    )


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


def kpi_card(title, value, subtitle=""):
    return html.Div(
        className="kpi-card",
        children=[
            html.Div(title, className="kpi-title"),
            html.Div(value, className="kpi-value"),
            html.Div(subtitle, className="kpi-subtitle")
        ]
    )


def chart_card(graph_id, note_title, note_text):
    return html.Div(
        className="chart-card",
        children=[
            dcc.Graph(id=graph_id, config={"displaylogo": False}),
            html.Div(
                className="chart-note",
                children=[
                    html.Strong(note_title),
                    html.Span(note_text)
                ]
            )
        ]
    )


def empty_figure(title):
    fig = go.Figure()
    fig.update_layout(
        title=title,
        template="plotly_white",
        height=430,
        annotations=[
            dict(
                text="No data available for the selected filters",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=16, color="#6b7280")
            )
        ]
    )
    return fig


def apply_standard_layout(fig, title, y_title=None):
    fig.update_layout(
        title={
            "text": title,
            "x": 0.02,
            "xanchor": "left"
        },
        template="plotly_white",
        height=430,
        margin=dict(l=55, r=30, t=70, b=55),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        hovermode="x unified",
        font=dict(family="Arial, Helvetica, sans-serif", size=13)
    )

    fig.update_xaxes(
        title_text="SOP datetime",
        showgrid=True,
        gridcolor="#eef2f7"
    )

    if y_title:
        fig.update_yaxes(
            title_text=y_title,
            showgrid=True,
            gridcolor="#eef2f7"
        )

    return fig


def build_readiness_figure(df):
    fig = go.Figure()

    fig.add_hrect(y0=75, y1=100, fillcolor="rgba(37, 99, 235, 0.08)", line_width=0)
    fig.add_hrect(y0=55, y1=75, fillcolor="rgba(245, 158, 11, 0.10)", line_width=0)
    fig.add_hrect(y0=35, y1=55, fillcolor="rgba(16, 185, 129, 0.10)", line_width=0)
    fig.add_hrect(y0=0, y1=35, fillcolor="rgba(239, 68, 68, 0.10)", line_width=0)

    fig.add_trace(
        go.Scatter(
            x=df["sop_datetime"],
            y=df["system_readiness_score_v2"],
            mode="lines",
            name="Readiness score",
            line=dict(color="#334155", width=2),
            hovertemplate="Time: %{x}<br>Score: %{y:.1f}<extra></extra>"
        )
    )

    for status in STATUS_ORDER:
        sub = df[df["system_readiness_status_v2"] == status]
        if not sub.empty:
            fig.add_trace(
                go.Scatter(
                    x=sub["sop_datetime"],
                    y=sub["system_readiness_score_v2"],
                    mode="markers",
                    name=status,
                    marker=dict(
                        color=STATUS_COLOURS.get(status, "#6b7280"),
                        size=8,
                        line=dict(width=1, color="white")
                    ),
                    hovertemplate=(
                        "Time: %{x}<br>"
                        "Score: %{y:.1f}<br>"
                        f"Status: {status}"
                        "<extra></extra>"
                    )
                )
            )

    for y, label in [(75, "Comfortable"), (55, "Watch"), (35, "Tight")]:
        fig.add_hline(
            y=y,
            line_dash="dash",
            line_color="#64748b",
            annotation_text=label,
            annotation_position="top left"
        )

    fig.update_yaxes(range=[0, 100])

    return apply_standard_layout(
        fig,
        "System readiness score with operational risk bands",
        "Readiness score"
    )


def build_margin_figure(df):
    fig = go.Figure()

    fig.add_hrect(y0=0, y1=500, fillcolor="rgba(239, 68, 68, 0.12)", line_width=0)
    fig.add_hrect(y0=500, y1=1000, fillcolor="rgba(245, 158, 11, 0.12)", line_width=0)

    fig.add_trace(
        go.Bar(
            x=df["sop_datetime"],
            y=df["operating_margin_surplus"],
            name="Operating margin surplus",
            marker_color="#2563eb",
            opacity=0.75,
            hovertemplate="Time: %{x}<br>Margin: %{y:,.0f} MW<extra></extra>"
        )
    )

    fig.add_hline(
        y=1000,
        line_dash="dash",
        line_color="#f59e0b",
        annotation_text="Watch below 1,000 MW",
        annotation_position="top left"
    )

    fig.add_hline(
        y=500,
        line_dash="dash",
        line_color="#ef4444",
        annotation_text="Severe below 500 MW",
        annotation_position="bottom left"
    )

    return apply_standard_layout(
        fig,
        "Operating margin surplus, higher is safer",
        "MW"
    )


def build_reserve_figure(df):
    fig = go.Figure()

    fig.add_hrect(y0=0, y1=0.80, fillcolor="rgba(239, 68, 68, 0.12)", line_width=0)
    fig.add_hrect(y0=0.80, y1=0.90, fillcolor="rgba(245, 158, 11, 0.12)", line_width=0)

    fig.add_trace(
        go.Scatter(
            x=df["sop_datetime"],
            y=df["reserve_coverage_ratio"],
            mode="lines+markers",
            name="Reserve coverage ratio",
            line=dict(color="#10b981", width=2),
            marker=dict(size=6),
            hovertemplate="Time: %{x}<br>Reserve coverage: %{y:.2f}<extra></extra>"
        )
    )

    fig.add_hline(
        y=1.0,
        line_dash="solid",
        line_color="#334155",
        annotation_text="1.00 means reserve availability equals requirement",
        annotation_position="top left"
    )

    fig.add_hline(
        y=0.90,
        line_dash="dash",
        line_color="#f59e0b",
        annotation_text="Watch below 0.90",
        annotation_position="bottom left"
    )

    fig.add_hline(
        y=0.80,
        line_dash="dash",
        line_color="#ef4444",
        annotation_text="Severe below 0.80",
        annotation_position="bottom left"
    )

    return apply_standard_layout(
        fig,
        "Standing reserve coverage ratio",
        "Availability / requirement"
    )


def build_status_mix_figure(df):
    counts = (
        df["system_readiness_status_v2"]
        .fillna("Unknown")
        .value_counts()
        .reindex(STATUS_ORDER)
        .dropna()
        .reset_index()
    )

    counts.columns = ["status", "records"]

    colours = [STATUS_COLOURS.get(status, "#6b7280") for status in counts["status"]]

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=counts["status"],
            y=counts["records"],
            marker_color=colours,
            text=counts["records"],
            textposition="outside",
            hovertemplate="Status: %{x}<br>Records: %{y}<extra></extra>"
        )
    )

    fig.update_layout(
        title={
            "text": "Readiness status mix in the selected view",
            "x": 0.02,
            "xanchor": "left"
        },
        template="plotly_white",
        height=430,
        margin=dict(l=55, r=30, t=70, b=55),
        showlegend=False,
        font=dict(family="Arial, Helvetica, sans-serif", size=13)
    )

    fig.update_xaxes(title_text="Readiness status")
    fig.update_yaxes(title_text="Number of SOP records", showgrid=True, gridcolor="#eef2f7")

    return fig


def build_cardinal_risk_figure(df):
    cardinal_summary = (
        df
        .groupby("cardinal_point", as_index=False)
        .agg(
            average_readiness=("system_readiness_score_v2", "mean"),
            average_margin=("operating_margin_surplus", "mean"),
            severe_flags=("severe_flag_count", "sum"),
            watch_flags=("watch_flag_count", "sum"),
            records=("cardinal_point", "count")
        )
        .sort_values("average_readiness", ascending=True)
    )

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            y=cardinal_summary["cardinal_point"],
            x=cardinal_summary["average_readiness"],
            orientation="h",
            marker=dict(
                color=cardinal_summary["average_readiness"],
                colorscale="RdYlGn",
                cmin=0,
                cmax=100,
                colorbar=dict(title="Average score")
            ),
            text=[
                f"{score:.1f} | severe flags: {int(flags)}"
                for score, flags in zip(
                    cardinal_summary["average_readiness"],
                    cardinal_summary["severe_flags"]
                )
            ],
            textposition="auto",
            hovertemplate=(
                "Cardinal point: %{y}<br>"
                "Average readiness: %{x:.1f}<br>"
                "<extra></extra>"
            )
        )
    )

    fig.add_vline(
        x=75,
        line_dash="dash",
        line_color="#2563eb",
        annotation_text="Comfortable threshold",
        annotation_position="top"
    )

    fig.add_vline(
        x=55,
        line_dash="dash",
        line_color="#f59e0b",
        annotation_text="Watch threshold",
        annotation_position="bottom"
    )

    fig.update_layout(
        title={
            "text": "Which cardinal points are riskiest?",
            "x": 0.02,
            "xanchor": "left"
        },
        template="plotly_white",
        height=430,
        margin=dict(l=80, r=30, t=70, b=55),
        font=dict(family="Arial, Helvetica, sans-serif", size=13)
    )

    fig.update_xaxes(title_text="Average readiness score", range=[0, 100])
    fig.update_yaxes(title_text="Cardinal point")

    return fig


def format_number(value, decimals=0):
    if pd.isna(value):
        return "N/A"
    if decimals == 0:
        return f"{value:,.0f}"
    return f"{value:,.{decimals}f}"


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
            className="guide",
            children=[
                html.H2("How to use this dashboard"),
                html.P(
                    "This dashboard helps you understand whether the GB electricity system has enough operational margin, reserve and dispatch headroom for each NESO System Operating Plan period."
                ),
                html.Div(
                    className="guide-grid",
                    children=[
                        html.Div([
                            html.H3("1. Start with the KPI cards"),
                            html.P("Use the cards at the top to see the latest SOP time, readiness score, margin, reserve coverage and dispatch headroom.")
                        ]),
                        html.Div([
                            html.H3("2. Read the readiness score"),
                            html.P("Higher is better. Comfortable means the system has stronger readiness. Watch, Tight and Critical show increasing levels of operational pressure.")
                        ]),
                        html.Div([
                            html.H3("3. Use the filters"),
                            html.P("Filter by cardinal point, readiness status or recent record count to focus on a specific operating condition.")
                        ]),
                        html.Div([
                            html.H3("4. Check the latest table"),
                            html.P("The table shows the most recent SOP records and highlights risk status using simple colours.")
                        ])
                    ]
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
                        html.Label("Records shown"),
                        dcc.Dropdown(
                            id="record-window",
                            options=[
                                {"label": "Latest 50 records", "value": "50"},
                                {"label": "Latest 100 records", "value": "100"},
                                {"label": "Latest 200 records", "value": "200"},
                                {"label": "All records", "value": "All"}
                            ],
                            value="100",
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
                chart_card(
                    "readiness-trend",
                    "How to read this: ",
                    "The line shows readiness from 0 to 100. Blue areas are comfortable, amber means watch, green means tight and red means critical."
                ),
                chart_card(
                    "margin-trend",
                    "How to read this: ",
                    "Operating margin is the spare room available to manage system changes. Higher values are better. Bars below 1,000 MW require attention."
                ),
                chart_card(
                    "reserve-trend",
                    "How to read this: ",
                    "Reserve coverage compares available reserve with required reserve. A value of 1.00 means availability equals requirement."
                ),
                chart_card(
                    "status-mix",
                    "How to read this: ",
                    "This shows how many SOP records in the selected view fall into Comfortable, Watch, Tight or Critical status."
                ),
                chart_card(
                    "cardinal-risk",
                    "How to read this: ",
                    "Lower average readiness means higher risk. This chart helps identify which cardinal points have weaker operating conditions."
                )
            ]
        ),

        html.Div(
            className="section",
            children=[
                html.H2("Latest SOP readiness records"),
                html.P(
                    "Use this table to inspect the latest records behind the charts. Rows are coloured by readiness status so that risk conditions are easier to spot."
                ),
                dash_table.DataTable(
                    id="latest-table",
                    page_size=10,
                    style_table={"overflowX": "auto"},
                    style_cell={
                        "fontFamily": "Arial",
                        "fontSize": "13px",
                        "padding": "8px",
                        "textAlign": "left",
                        "whiteSpace": "normal",
                        "height": "auto"
                    },
                    style_header={
                        "fontWeight": "bold",
                        "backgroundColor": "#f3f4f6"
                    },
                    style_data_conditional=[
                        {
                            "if": {"filter_query": '{system_readiness_status_v2} = "Critical"'},
                            "backgroundColor": "#fee2e2",
                            "color": "#7f1d1d"
                        },
                        {
                            "if": {"filter_query": '{system_readiness_status_v2} = "Tight"'},
                            "backgroundColor": "#dcfce7",
                            "color": "#14532d"
                        },
                        {
                            "if": {"filter_query": '{system_readiness_status_v2} = "Watch"'},
                            "backgroundColor": "#fef9c3",
                            "color": "#713f12"
                        },
                        {
                            "if": {"filter_query": '{system_readiness_status_v2} = "Comfortable"'},
                            "backgroundColor": "#dbeafe",
                            "color": "#1e3a8a"
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
            for x in sorted(df["cardinal_point"].dropna().astype(str).unique())
        ]

        available_statuses = set(df["system_readiness_status_v2"].dropna().astype(str).unique())
        status_options += [
            {"label": status, "value": status}
            for status in STATUS_ORDER
            if status in available_statuses
        ]

    return cardinal_options, status_options


@app.callback(
    Output("kpi-row", "children"),
    Output("readiness-trend", "figure"),
    Output("margin-trend", "figure"),
    Output("reserve-trend", "figure"),
    Output("status-mix", "figure"),
    Output("cardinal-risk", "figure"),
    Output("latest-table", "data"),
    Output("latest-table", "columns"),
    Input("cardinal-filter", "value"),
    Input("status-filter", "value"),
    Input("record-window", "value"),
    Input("auto-refresh", "n_intervals"),
    Input("refresh-button", "n_clicks")
)
def update_dashboard(selected_cardinal, selected_status, selected_window, _, __):
    df = load_data()

    if df.empty:
        return (
            [
                kpi_card("Records shown", "0"),
                kpi_card("Latest SOP time", "N/A"),
                kpi_card("Readiness score", "N/A"),
                kpi_card("Operating margin", "N/A"),
                kpi_card("Reserve coverage", "N/A"),
                kpi_card("Dispatch headroom", "N/A")
            ],
            empty_figure("System readiness score"),
            empty_figure("Operating margin"),
            empty_figure("Reserve coverage"),
            empty_figure("Readiness status mix"),
            empty_figure("Cardinal point risk"),
            [],
            []
        )

    filtered_df = df.copy()

    if selected_cardinal and selected_cardinal != "All":
        filtered_df = filtered_df[filtered_df["cardinal_point"].astype(str) == selected_cardinal]

    if selected_status and selected_status != "All":
        filtered_df = filtered_df[filtered_df["system_readiness_status_v2"].astype(str) == selected_status]

    filtered_df = filtered_df.sort_values("sop_datetime")

    if selected_window and selected_window != "All":
        filtered_df = filtered_df.tail(int(selected_window))

    if filtered_df.empty:
        return (
            [
                kpi_card("Records shown", "0"),
                kpi_card("Latest SOP time", "N/A"),
                kpi_card("Readiness score", "N/A"),
                kpi_card("Operating margin", "N/A"),
                kpi_card("Reserve coverage", "N/A"),
                kpi_card("Dispatch headroom", "N/A")
            ],
            empty_figure("System readiness score"),
            empty_figure("Operating margin"),
            empty_figure("Reserve coverage"),
            empty_figure("Readiness status mix"),
            empty_figure("Cardinal point risk"),
            [],
            []
        )

    latest = filtered_df.iloc[-1]

    latest_time = latest["sop_datetime"].strftime("%d %b %Y %H:%M UTC")
    latest_score = format_number(latest["system_readiness_score_v2"], 1)
    latest_status = latest["system_readiness_status_v2"]
    latest_margin = f"{format_number(latest['operating_margin_surplus'], 0)} MW"
    latest_reserve = format_number(latest["reserve_coverage_ratio"], 2)
    latest_headroom = f"{format_number(latest['dispatch_headroom_mw'], 0)} MW"

    kpis = [
        kpi_card("Records shown", f"{len(filtered_df):,}", f"{len(df):,} total records in database"),
        kpi_card("Latest SOP time", latest_time, f"Cardinal point: {latest['cardinal_point']}"),
        kpi_card("Readiness score", latest_score, latest_status),
        kpi_card("Operating margin", latest_margin, "Higher is safer"),
        kpi_card("Reserve coverage", latest_reserve, "1.00 means enough reserve"),
        kpi_card("Dispatch headroom", latest_headroom, "TEMX minus TEOL")
    ]

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

    latest_table["total_sop_demand"] = latest_table["total_sop_demand"].map(lambda x: format_number(x, 0))
    latest_table["operating_margin_surplus"] = latest_table["operating_margin_surplus"].map(lambda x: format_number(x, 0))
    latest_table["reserve_coverage_ratio"] = latest_table["reserve_coverage_ratio"].map(lambda x: format_number(x, 2))
    latest_table["dispatch_headroom_mw"] = latest_table["dispatch_headroom_mw"].map(lambda x: format_number(x, 0))
    latest_table["absolute_imbalance_mw"] = latest_table["absolute_imbalance_mw"].map(lambda x: format_number(x, 0))
    latest_table["system_readiness_score_v2"] = latest_table["system_readiness_score_v2"].map(lambda x: format_number(x, 1))

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
        build_readiness_figure(filtered_df),
        build_margin_figure(filtered_df),
        build_reserve_figure(filtered_df),
        build_status_mix_figure(filtered_df),
        build_cardinal_risk_figure(filtered_df),
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
                max-width: 1450px;
                margin: 0 auto;
                padding: 28px;
            }

            .hero {
                background: linear-gradient(135deg, #0f172a, #1e3a8a);
                color: white;
                padding: 34px;
                border-radius: 26px;
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

            .guide {
                background: white;
                margin-top: 24px;
                padding: 24px;
                border-radius: 20px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
                border: 1px solid #e5e7eb;
            }

            .guide h2 {
                margin-top: 0;
                margin-bottom: 8px;
            }

            .guide p {
                color: #4b5563;
                line-height: 1.55;
            }

            .guide-grid {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 16px;
                margin-top: 18px;
            }

            .guide-grid div {
                background: #f8fafc;
                border: 1px solid #e5e7eb;
                border-radius: 16px;
                padding: 16px;
            }

            .guide-grid h3 {
                margin-top: 0;
                margin-bottom: 8px;
                font-size: 15px;
            }

            .controls {
                display: grid;
                grid-template-columns: 1fr 1fr 1fr 180px;
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

            .chart-card {
                background: white;
                border-radius: 20px;
                padding: 14px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
                border: 1px solid #e5e7eb;
            }

            .chart-card:first-child {
                grid-column: span 2;
            }

            .chart-note {
                background: #f8fafc;
                border-left: 4px solid #2563eb;
                padding: 12px 14px;
                border-radius: 10px;
                color: #4b5563;
                font-size: 13px;
                line-height: 1.45;
                margin: 0 8px 8px 8px;
            }

            .chart-note strong {
                color: #111827;
            }

            .section {
                background: white;
                padding: 22px;
                border-radius: 18px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
                margin-bottom: 24px;
                border: 1px solid #e5e7eb;
            }

            .section h2 {
                margin-top: 0;
            }

            .section p {
                color: #4b5563;
            }

            .footer {
                color: #6b7280;
                font-size: 13px;
                text-align: center;
                padding: 20px;
            }

            @media (max-width: 1200px) {
                .kpi-grid {
                    grid-template-columns: repeat(3, 1fr);
                }

                .chart-grid {
                    grid-template-columns: 1fr;
                }

                .chart-card:first-child {
                    grid-column: span 1;
                }

                .controls {
                    grid-template-columns: 1fr 1fr;
                }

                .guide-grid {
                    grid-template-columns: 1fr 1fr;
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

                .controls {
                    grid-template-columns: 1fr;
                }

                .guide-grid {
                    grid-template-columns: 1fr;
                }

                .hero h1 {
                    font-size: 24px;
                }

                .hero-badge {
                    white-space: normal;
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
