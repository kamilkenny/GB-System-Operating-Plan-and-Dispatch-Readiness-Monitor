import os

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

import dash
from dash import Input, Output, dcc, html, dash_table
import plotly.graph_objects as go


TABLE_NAME = "neso_sop_readiness_snapshots"

STATUS_ORDER = ["Comfortable", "Watch", "Tight", "Critical", "Unknown"]

STATUS_COLOURS = {
    "Comfortable": "#16a34a",
    "Watch": "#f59e0b",
    "Tight": "#f97316",
    "Critical": "#dc2626",
    "Unknown": "#64748b",
}

MARGIN_LEVELS = {
    "Critical": 1,
    "Watch": 2,
    "Adequate": 3,
    "Strong": 4,
}

MARGIN_COLOURS = {
    "Critical": "#dc2626",
    "Watch": "#f59e0b",
    "Adequate": "#2563eb",
    "Strong": "#16a34a",
}


_DATABASE_ENGINE = None


def get_database_engine():
    """Create one lightweight SQLAlchemy engine without a local connection pool."""
    global _DATABASE_ENGINE

    if _DATABASE_ENGINE is not None:
        return _DATABASE_ENGINE

    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is missing."
        )

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg2://",
            1,
        )

    _DATABASE_ENGINE = create_engine(
        database_url,
        poolclass=NullPool,
        connect_args={
            "sslmode": "require",
            "connect_timeout": 10,
        },
    )

    return _DATABASE_ENGINE


def classify_margin(value):
    if pd.isna(value):
        return "Unknown"
    if value < 500:
        return "Critical"
    if value < 1000:
        return "Watch"
    if value < 3000:
        return "Adequate"
    return "Strong"


def classify_reserve(value):
    if pd.isna(value):
        return "Unknown"
    if value < 0.80:
        return "Critical"
    if value < 0.90:
        return "Watch"
    if value < 1.00:
        return "Adequate"
    return "Comfortable"


def load_data():
    query = text(
        f"""
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
    )

    engine = get_database_engine()

    try:
        with engine.connect() as connection:
            df = pd.read_sql_query(query, connection)
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Unable to load SOP data: {exc}") from exc

    for column in ["sop_datetime", "report_date", "collected_at"]:
        df[column] = pd.to_datetime(df[column], errors="coerce", utc=True)

    numeric_columns = [
        "customer_demand_forecast",
        "total_sop_demand",
        "standing_reserve_requirement",
        "standing_reserve_availability",
        "reserve_coverage_ratio",
        "reserve_gap_mw",
        "absolute_imbalance_mw",
        "contingency_requirement",
        "operating_margin_surplus",
        "trigger_level",
        "margin_vs_trigger_mw",
        "dispatch_headroom_mw",
        "system_readiness_score_v2",
        "watch_flag_count",
        "severe_flag_count",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    df["margin_status"] = df["operating_margin_surplus"].apply(classify_margin)
    df["margin_level"] = df["margin_status"].map(MARGIN_LEVELS)
    df["reserve_status"] = df["reserve_coverage_ratio"].apply(classify_reserve)

    return (
        df.dropna(subset=["sop_datetime"])
        .sort_values("sop_datetime")
        .reset_index(drop=True)
    )


def format_number(value, decimals=0):
    if pd.isna(value):
        return "N/A"
    return f"{value:,.{decimals}f}"


def kpi_card(title, value, subtitle, accent="#2563eb"):
    return html.Div(
        className="kpi-card",
        style={"borderTop": f"5px solid {accent}"},
        children=[
            html.Div(title, className="kpi-title"),
            html.Div(value, className="kpi-value"),
            html.Div(subtitle, className="kpi-subtitle"),
        ],
    )


def insight_card(title, body, action, tone="neutral"):
    tone_class = {
        "positive": "insight-positive",
        "warning": "insight-warning",
        "critical": "insight-critical",
        "neutral": "insight-neutral",
    }.get(tone, "insight-neutral")

    return html.Div(
        className=f"insight-card {tone_class}",
        children=[
            html.H3(title),
            html.P(body),
            html.Div(
                [
                    html.Strong("Recommended action: "),
                    action,
                ],
                className="action-text",
            ),
        ],
    )


def chart_card(graph_id, what_is_it, why_it_matters, how_to_read, action):
    return html.Div(
        className="chart-card",
        children=[
            dcc.Loading(
                dcc.Graph(
                    id=graph_id,
                    config={
                        "displaylogo": False,
                        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                    },
                ),
                type="circle",
            ),
            html.Div(
                className="chart-explainer",
                children=[
                    html.Div([html.Strong("What is this?"), html.P(what_is_it)]),
                    html.Div([html.Strong("Why is it important?"), html.P(why_it_matters)]),
                    html.Div([html.Strong("How do I read it?"), html.P(how_to_read)]),
                    html.Div([html.Strong("What action should I take?"), html.P(action)]),
                ],
            ),
        ],
    )


def apply_layout(fig, title, y_title=None, height=430):
    fig.update_layout(
        title={
            "text": title,
            "x": 0.02,
            "xanchor": "left",
            "font": {"size": 20},
        },
        template="plotly_white",
        height=height,
        margin=dict(l=60, r=30, t=80, b=60),
        font=dict(
            family="Arial, Helvetica, sans-serif",
            size=13,
            color="#1f2937",
        ),
        paper_bgcolor="white",
        plot_bgcolor="white",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
    )

    fig.update_xaxes(
        title_text="SOP datetime",
        showgrid=True,
        gridcolor="#eef2f7",
        zeroline=False,
    )

    if y_title:
        fig.update_yaxes(
            title_text=y_title,
            showgrid=True,
            gridcolor="#eef2f7",
            zeroline=False,
        )

    return fig


def empty_figure(title, message="No data available for the selected filters"):
    fig = go.Figure()

    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=16, color="#64748b"),
    )

    return apply_layout(fig, title)


def gauge_figure(value, title, suffix="", max_value=100, thresholds=None):
    if pd.isna(value):
        value = 0

    if thresholds is None:
        thresholds = [
            (0, 35, "#fee2e2"),
            (35, 55, "#ffedd5"),
            (55, 75, "#fef3c7"),
            (75, max_value, "#dcfce7"),
        ]

    steps = [
        {"range": [lower, upper], "color": colour}
        for lower, upper, colour in thresholds
    ]

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=float(value),
            number={
                "suffix": suffix,
                "font": {"size": 42, "color": "#111827"},
            },
            title={
                "text": title,
                "font": {"size": 18},
            },
            gauge={
                "axis": {
                    "range": [0, max_value],
                    "tickwidth": 1,
                    "tickcolor": "#64748b",
                },
                "bar": {
                    "color": "#1e3a8a",
                    "thickness": 0.24,
                },
                "bgcolor": "white",
                "borderwidth": 0,
                "steps": steps,
                "threshold": {
                    "line": {"color": "#111827", "width": 4},
                    "thickness": 0.75,
                    "value": float(value),
                },
            },
        )
    )

    fig.update_layout(
        height=300,
        margin=dict(l=35, r=35, t=65, b=20),
        paper_bgcolor="white",
        font=dict(family="Arial, Helvetica, sans-serif"),
    )

    return fig


def build_readiness_trend(df):
    fig = go.Figure()

    for lower, upper, colour in [
        (0, 35, "rgba(220, 38, 38, 0.11)"),
        (35, 55, "rgba(249, 115, 22, 0.11)"),
        (55, 75, "rgba(245, 158, 11, 0.11)"),
        (75, 100, "rgba(22, 163, 74, 0.10)"),
    ]:
        fig.add_hrect(y0=lower, y1=upper, fillcolor=colour, line_width=0)

    fig.add_trace(
        go.Scatter(
            x=df["sop_datetime"],
            y=df["system_readiness_score_v2"],
            mode="lines",
            name="Readiness score",
            line=dict(color="#334155", width=2),
            hovertemplate=(
                "SOP time: %{x}<br>"
                "Readiness score: %{y:.1f}"
                "<extra></extra>"
            ),
        )
    )

    for status in STATUS_ORDER:
        subset = df[df["system_readiness_status_v2"] == status]

        if subset.empty:
            continue

        fig.add_trace(
            go.Scatter(
                x=subset["sop_datetime"],
                y=subset["system_readiness_score_v2"],
                mode="markers",
                name=status,
                marker=dict(
                    color=STATUS_COLOURS[status],
                    size=8,
                    line=dict(color="white", width=1),
                ),
                customdata=subset[
                    [
                        "cardinal_point",
                        "operating_margin_surplus",
                        "reserve_coverage_ratio",
                    ]
                ],
                hovertemplate=(
                    "SOP time: %{x}<br>"
                    "Readiness score: %{y:.1f}<br>"
                    "Cardinal point: %{customdata[0]}<br>"
                    "Operating margin: %{customdata[1]:,.0f} MW<br>"
                    "Reserve coverage: %{customdata[2]:.2f}"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_yaxes(range=[0, 100])

    return apply_layout(
        fig,
        "System readiness trend",
        "Readiness score, 0 to 100",
        height=470,
    )


def build_margin_status_figure(df):
    fig = go.Figure()

    for lower, upper, colour in [
        (0.5, 1.5, "rgba(220, 38, 38, 0.12)"),
        (1.5, 2.5, "rgba(245, 158, 11, 0.12)"),
        (2.5, 3.5, "rgba(37, 99, 235, 0.10)"),
        (3.5, 4.5, "rgba(22, 163, 74, 0.10)"),
    ]:
        fig.add_hrect(y0=lower, y1=upper, fillcolor=colour, line_width=0)

    fig.add_trace(
        go.Scatter(
            x=df["sop_datetime"],
            y=df["margin_level"],
            mode="lines",
            line=dict(color="#64748b", width=2),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    for status in ["Critical", "Watch", "Adequate", "Strong"]:
        subset = df[df["margin_status"] == status]

        if subset.empty:
            continue

        fig.add_trace(
            go.Scatter(
                x=subset["sop_datetime"],
                y=subset["margin_level"],
                mode="markers",
                name=status,
                marker=dict(
                    color=MARGIN_COLOURS[status],
                    size=10,
                    line=dict(color="white", width=1),
                ),
                customdata=subset[
                    [
                        "operating_margin_surplus",
                        "trigger_level",
                        "margin_vs_trigger_mw",
                        "cardinal_point",
                    ]
                ],
                hovertemplate=(
                    "SOP time: %{x}<br>"
                    f"Safety classification: {status}<br>"
                    "Operating margin: %{customdata[0]:,.0f} MW<br>"
                    "Trigger level: %{customdata[1]:,.0f} MW<br>"
                    "Margin versus trigger: %{customdata[2]:,.0f} MW<br>"
                    "Cardinal point: %{customdata[3]}"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_yaxes(
        tickmode="array",
        tickvals=[1, 2, 3, 4],
        ticktext=["Critical", "Watch", "Adequate", "Strong"],
        range=[0.5, 4.5],
    )

    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.01,
        y=1.13,
        showarrow=False,
        align="left",
        text=(
            "Critical: below 500 MW | Watch: 500–999 MW | "
            "Adequate: 1,000–2,999 MW | Strong: 3,000 MW or more"
        ),
        font=dict(size=12, color="#475569"),
    )

    return apply_layout(
        fig,
        "Operating margin safety classification",
        "Operational safety level",
    )


def build_reserve_figure(df):
    fig = go.Figure()

    reserve_max = df["reserve_coverage_ratio"].max(skipna=True)
    max_ratio = 1.25 if pd.isna(reserve_max) else max(1.25, float(reserve_max) * 1.05)

    for lower, upper, colour in [
        (0, 0.80, "rgba(220, 38, 38, 0.12)"),
        (0.80, 0.90, "rgba(245, 158, 11, 0.12)"),
        (0.90, 1.00, "rgba(37, 99, 235, 0.08)"),
        (1.00, max_ratio, "rgba(22, 163, 74, 0.10)"),
    ]:
        fig.add_hrect(y0=lower, y1=upper, fillcolor=colour, line_width=0)

    fig.add_trace(
        go.Scatter(
            x=df["sop_datetime"],
            y=df["reserve_coverage_ratio"],
            mode="lines+markers",
            name="Reserve coverage",
            line=dict(color="#0f766e", width=2),
            marker=dict(
                size=7,
                color="#0f766e",
                line=dict(color="white", width=1),
            ),
            customdata=df[
                [
                    "standing_reserve_availability",
                    "standing_reserve_requirement",
                    "reserve_gap_mw",
                    "reserve_status",
                ]
            ],
            hovertemplate=(
                "SOP time: %{x}<br>"
                "Coverage ratio: %{y:.2f}<br>"
                "Availability: %{customdata[0]:,.0f} MW<br>"
                "Requirement: %{customdata[1]:,.0f} MW<br>"
                "Reserve gap: %{customdata[2]:,.0f} MW<br>"
                "Status: %{customdata[3]}"
                "<extra></extra>"
            ),
        )
    )

    fig.add_hline(
        y=1.0,
        line_color="#334155",
        line_width=2,
        annotation_text="Requirement fully covered",
        annotation_position="top left",
    )

    fig.update_yaxes(range=[0, max_ratio])

    return apply_layout(
        fig,
        "Standing reserve coverage",
        "Available reserve divided by reserve requirement",
    )


def build_cardinal_figure(df):
    summary = (
        df.groupby("cardinal_point", as_index=False)
        .agg(
            average_readiness=("system_readiness_score_v2", "mean"),
            minimum_readiness=("system_readiness_score_v2", "min"),
            average_margin=("operating_margin_surplus", "mean"),
            average_reserve=("reserve_coverage_ratio", "mean"),
            watch_flags=("watch_flag_count", "sum"),
            severe_flags=("severe_flag_count", "sum"),
            records=("cardinal_point", "count"),
        )
        .sort_values("average_readiness", ascending=True)
    )

    if summary.empty:
        return empty_figure("Cardinal-point readiness comparison")

    fig = go.Figure(
        go.Bar(
            y=summary["cardinal_point"],
            x=summary["average_readiness"],
            orientation="h",
            marker=dict(
                color=summary["average_readiness"],
                colorscale=[
                    [0.00, "#dc2626"],
                    [0.35, "#f97316"],
                    [0.55, "#f59e0b"],
                    [0.75, "#16a34a"],
                    [1.00, "#16a34a"],
                ],
                cmin=0,
                cmax=100,
                colorbar=dict(title="Average score"),
            ),
            text=[f"{value:.1f}" for value in summary["average_readiness"]],
            textposition="auto",
            customdata=summary[
                [
                    "minimum_readiness",
                    "average_margin",
                    "average_reserve",
                    "watch_flags",
                    "severe_flags",
                    "records",
                ]
            ],
            hovertemplate=(
                "Cardinal point: %{y}<br>"
                "Average readiness: %{x:.1f}<br>"
                "Minimum readiness: %{customdata[0]:.1f}<br>"
                "Average margin: %{customdata[1]:,.0f} MW<br>"
                "Average reserve coverage: %{customdata[2]:.2f}<br>"
                "Watch flags: %{customdata[3]:.0f}<br>"
                "Severe flags: %{customdata[4]:.0f}<br>"
                "Records: %{customdata[5]:.0f}"
                "<extra></extra>"
            ),
        )
    )

    for lower, upper, colour in [
        (0, 35, "rgba(220, 38, 38, 0.07)"),
        (35, 55, "rgba(249, 115, 22, 0.07)"),
        (55, 75, "rgba(245, 158, 11, 0.07)"),
        (75, 100, "rgba(22, 163, 74, 0.06)"),
    ]:
        fig.add_vrect(x0=lower, x1=upper, fillcolor=colour, line_width=0)

    fig.update_layout(
        title={
            "text": "Which operating periods require the most attention?",
            "x": 0.02,
            "xanchor": "left",
            "font": {"size": 20},
        },
        template="plotly_white",
        height=440,
        margin=dict(l=105, r=35, t=80, b=60),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="Arial, Helvetica, sans-serif", size=13),
    )

    fig.update_xaxes(
        title_text="Average readiness score",
        range=[0, 100],
        showgrid=True,
        gridcolor="#eef2f7",
    )
    fig.update_yaxes(title_text="Cardinal point")

    return fig


def build_attention_figure(df):
    summary = pd.DataFrame(
        {
            "Indicator": [
                "Margin",
                "Reserve",
                "Dispatch headroom",
                "Imbalance",
            ],
            "Watch": [
                df["margin_watch_flag"].fillna(False).astype(int).sum(),
                df["reserve_watch_flag"].fillna(False).astype(int).sum(),
                df["headroom_watch_flag"].fillna(False).astype(int).sum(),
                df["imbalance_watch_flag"].fillna(False).astype(int).sum(),
            ],
            "Severe": [
                df["margin_severe_flag"].fillna(False).astype(int).sum(),
                df["reserve_severe_flag"].fillna(False).astype(int).sum(),
                df["headroom_severe_flag"].fillna(False).astype(int).sum(),
                df["imbalance_severe_flag"].fillna(False).astype(int).sum(),
            ],
        }
    )

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=summary["Indicator"],
            y=summary["Watch"],
            name="Watch flags",
            marker_color="#f59e0b",
            text=summary["Watch"],
            textposition="outside",
        )
    )

    fig.add_trace(
        go.Bar(
            x=summary["Indicator"],
            y=summary["Severe"],
            name="Severe flags",
            marker_color="#dc2626",
            text=summary["Severe"],
            textposition="outside",
        )
    )

    fig.update_layout(barmode="group")

    return apply_layout(
        fig,
        "Where is operational attention accumulating?",
        "Number of flagged SOP records",
    )


def build_status_mix(df):
    counts = (
        df["system_readiness_status_v2"]
        .fillna("Unknown")
        .value_counts()
        .reindex(STATUS_ORDER)
        .fillna(0)
        .astype(int)
    )

    labels = [status for status in STATUS_ORDER if counts[status] > 0]
    values = [counts[status] for status in labels]
    colours = [STATUS_COLOURS[status] for status in labels]

    if not labels:
        return empty_figure("Readiness status distribution")

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.58,
            marker=dict(colors=colours),
            textinfo="label+percent",
            hovertemplate=(
                "Status: %{label}<br>"
                "Records: %{value}<br>"
                "Share: %{percent}"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title={
            "text": "Readiness status distribution",
            "x": 0.02,
            "xanchor": "left",
            "font": {"size": 20},
        },
        template="plotly_white",
        height=430,
        margin=dict(l=40, r=40, t=80, b=40),
        paper_bgcolor="white",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.05,
            xanchor="center",
            x=0.5,
        ),
        font=dict(family="Arial, Helvetica, sans-serif", size=13),
    )

    return fig


def build_executive_insights(df):
    latest = df.iloc[-1]
    insights = []

    readiness_status = str(latest["system_readiness_status_v2"])
    readiness_score = latest["system_readiness_score_v2"]

    if readiness_status == "Comfortable":
        insights.append(
            insight_card(
                "Overall system position",
                f"The latest readiness score is {format_number(readiness_score, 1)}, "
                "which places the system in the Comfortable category.",
                "Continue routine monitoring and watch for any downward movement.",
                "positive",
            )
        )
    elif readiness_status in ["Watch", "Tight"]:
        insights.append(
            insight_card(
                "Overall system position",
                f"The latest readiness score is {format_number(readiness_score, 1)} "
                f"and the current classification is {readiness_status}.",
                "Review the weaker indicators and pay closer attention to the next SOP updates.",
                "warning",
            )
        )
    else:
        insights.append(
            insight_card(
                "Overall system position",
                f"The latest readiness score is {format_number(readiness_score, 1)} "
                "and the current position requires urgent attention.",
                "Escalate the operational review and examine margin, reserve and headroom immediately.",
                "critical",
            )
        )

    margin_status = latest["margin_status"]
    margin_value = latest["operating_margin_surplus"]

    if margin_status in ["Strong", "Adequate"]:
        margin_tone = "positive"
        margin_action = "Maintain routine surveillance for sudden deterioration."
    elif margin_status == "Watch":
        margin_tone = "warning"
        margin_action = "Review reserve and headroom to confirm that system flexibility remains adequate."
    else:
        margin_tone = "critical"
        margin_action = "Prioritise an immediate review of available balancing and reserve options."

    insights.append(
        insight_card(
            "Operating margin",
            f"The latest operating margin is {format_number(margin_value, 0)} MW, "
            f"classified as {margin_status}.",
            margin_action,
            margin_tone,
        )
    )

    reserve_status = latest["reserve_status"]
    reserve_value = latest["reserve_coverage_ratio"]

    if reserve_status == "Comfortable":
        reserve_tone = "positive"
        reserve_action = "Continue routine monitoring."
    elif reserve_status in ["Adequate", "Watch"]:
        reserve_tone = "warning"
        reserve_action = "Track whether the ratio moves below 0.90 or continues to weaken."
    else:
        reserve_tone = "critical"
        reserve_action = "Review reserve availability against requirement immediately."

    insights.append(
        insight_card(
            "Standing reserve",
            f"The latest reserve coverage ratio is {format_number(reserve_value, 2)}, "
            f"classified as {reserve_status}.",
            reserve_action,
            reserve_tone,
        )
    )

    return insights


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
                        html.Div("GB POWER SYSTEM OPERATIONS", className="eyebrow"),
                        html.H1("NESO Dispatch Readiness Intelligence Dashboard"),
                        html.P(
                            "Executive monitoring of system readiness, operating margin, "
                            "standing reserve, imbalance and dispatch headroom using "
                            "NESO System Operating Plan data."
                        ),
                    ]
                ),
                html.Div(
                    className="hero-badge",
                    children=[
                        html.Div("LIVE CLOUD PIPELINE", className="badge-title"),
                        html.Div("NESO • Supabase • GitHub Actions • Dash"),
                    ],
                ),
            ],
        ),

        html.Div(
            className="summary-strip",
            children=[
                html.Div(
                    [
                        html.Strong("Purpose: "),
                        "Translate technical SOP data into clear operational signals.",
                    ]
                ),
                html.Div(
                    [
                        html.Strong("Decision question: "),
                        "Is the system comfortable, under pressure, or requiring intervention?",
                    ]
                ),
                html.Div(
                    [
                        html.Strong("Important: "),
                        "The readiness score is an analytical dashboard indicator, not an official NESO metric.",
                    ]
                ),
            ],
        ),

        html.Div(
            className="controls",
            children=[
                html.Div(
                    [
                        html.Label("Cardinal point"),
                        dcc.Dropdown(
                            id="cardinal-filter",
                            options=[],
                            value="All",
                            clearable=False,
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.Label("Readiness status"),
                        dcc.Dropdown(
                            id="status-filter",
                            options=[],
                            value="All",
                            clearable=False,
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.Label("Records shown"),
                        dcc.Dropdown(
                            id="record-window",
                            options=[
                                {"label": "Latest 50 records", "value": "50"},
                                {"label": "Latest 100 records", "value": "100"},
                                {"label": "Latest 200 records", "value": "200"},
                                {"label": "All records", "value": "All"},
                            ],
                            value="100",
                            clearable=False,
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.Label("Refresh data"),
                        html.Button(
                            "Refresh now",
                            id="refresh-button",
                            n_clicks=0,
                        ),
                    ]
                ),
            ],
        ),

        dcc.Interval(
            id="auto-refresh",
            interval=5 * 60 * 1000,
            n_intervals=0,
        ),

        html.Div(id="data-message"),

        html.Div(id="kpi-row", className="kpi-grid"),

        html.Div(
            className="section-heading",
            children=[
                html.H2("Latest operational position"),
                html.P(
                    "These gauges show the most recent filtered SOP record. "
                    "Use them as the first executive check before reviewing detailed trends."
                ),
            ],
        ),

        html.Div(
            className="gauge-grid",
            children=[
                html.Div(dcc.Graph(id="readiness-gauge"), className="gauge-card"),
                html.Div(dcc.Graph(id="margin-gauge"), className="gauge-card"),
                html.Div(dcc.Graph(id="reserve-gauge"), className="gauge-card"),
            ],
        ),

        html.Div(
            className="section-heading",
            children=[
                html.H2("Executive interpretation"),
                html.P(
                    "Plain-English interpretation of the latest position and the action it suggests."
                ),
            ],
        ),

        html.Div(id="insight-row", className="insight-grid"),

        html.Div(
            className="chart-grid",
            children=[
                html.Div(
                    className="full-width",
                    children=[
                        chart_card(
                            "readiness-trend",
                            "A combined view of margin, reserve, imbalance and dispatch headroom.",
                            "It provides the quickest overall indication of whether operational conditions are improving or weakening.",
                            "Higher is better. Green is Comfortable, amber is Watch, orange is Tight and red is Critical.",
                            "Investigate repeated or sustained movement into Tight or Critical zones.",
                        )
                    ],
                ),
                chart_card(
                    "margin-status",
                    "A simple classification of operating margin rather than a compressed MW chart.",
                    "Operating margin represents the spare room available to manage unexpected changes in demand or generation.",
                    "Strong is best, followed by Adequate, Watch and Critical. Hover over any point to see the actual MW value.",
                    "Repeated Watch or Critical periods should trigger closer review of reserve and balancing flexibility.",
                ),
                chart_card(
                    "reserve-trend",
                    "The ratio of available standing reserve to the reserve requirement.",
                    "Reserve supports the system when unexpected losses or demand changes occur.",
                    "A value of 1.00 means reserve availability fully meets the requirement. Below 1.00 indicates a shortfall.",
                    "Track deterioration below 0.90 and treat values below 0.80 as critical in this dashboard.",
                ),
                chart_card(
                    "cardinal-chart",
                    "Average readiness by cardinal point.",
                    "It identifies operating periods that repeatedly show weaker system conditions.",
                    "Bars further left have lower readiness and require more attention.",
                    "Prioritise review of cardinal points with the lowest scores and repeated severe flags.",
                ),
                chart_card(
                    "attention-chart",
                    "A count of Watch and Severe flags across the four operational indicators.",
                    "It shows which source of pressure is appearing most frequently.",
                    "Taller bars mean that indicator is causing more operational concern in the selected period.",
                    "Focus investigation on the indicator with the largest Severe count.",
                ),
                chart_card(
                    "status-mix",
                    "The share of selected SOP records in each readiness category.",
                    "It shows whether difficult conditions are isolated or becoming common.",
                    "A larger Comfortable share is healthier. Rising Tight or Critical shares indicate increasing pressure.",
                    "Compare the status mix after changing filters or time windows to identify emerging deterioration.",
                ),
            ],
        ),

        html.Div(
            className="table-section",
            children=[
                html.Div(
                    className="section-heading table-heading",
                    children=[
                        html.H2("Latest SOP readiness records"),
                        html.P(
                            "Detailed records behind the dashboard. Rows are coloured by readiness status."
                        ),
                    ],
                ),
                dash_table.DataTable(
                    id="latest-table",
                    page_size=10,
                    sort_action="native",
                    filter_action="native",
                    style_table={"overflowX": "auto"},
                    style_cell={
                        "fontFamily": "Arial",
                        "fontSize": "13px",
                        "padding": "9px",
                        "textAlign": "left",
                        "whiteSpace": "normal",
                        "height": "auto",
                        "minWidth": "110px",
                    },
                    style_header={
                        "fontWeight": "bold",
                        "backgroundColor": "#e8eef8",
                        "color": "#0f172a",
                        "border": "1px solid #dbe3ef",
                    },
                    style_data_conditional=[
                        {
                            "if": {
                                "filter_query": '{system_readiness_status_v2} = "Critical"'
                            },
                            "backgroundColor": "#fee2e2",
                            "color": "#7f1d1d",
                        },
                        {
                            "if": {
                                "filter_query": '{system_readiness_status_v2} = "Tight"'
                            },
                            "backgroundColor": "#ffedd5",
                            "color": "#7c2d12",
                        },
                        {
                            "if": {
                                "filter_query": '{system_readiness_status_v2} = "Watch"'
                            },
                            "backgroundColor": "#fef3c7",
                            "color": "#78350f",
                        },
                        {
                            "if": {
                                "filter_query": '{system_readiness_status_v2} = "Comfortable"'
                            },
                            "backgroundColor": "#dcfce7",
                            "color": "#14532d",
                        },
                    ],
                ),
            ],
        ),

        html.Div(
            className="footer",
            children=[
                "Data source: NESO System Operating Plan open data. ",
                "Dashboard created by Kamil Ridwan Kehinde.",
            ],
        ),
    ],
)


@app.callback(
    Output("cardinal-filter", "options"),
    Output("status-filter", "options"),
    Input("auto-refresh", "n_intervals"),
    Input("refresh-button", "n_clicks"),
)
def update_filter_options(_, __):
    try:
        df = load_data()
    except RuntimeError:
        return [{"label": "All", "value": "All"}], [{"label": "All", "value": "All"}]

    cardinal_options = [{"label": "All", "value": "All"}]
    status_options = [{"label": "All", "value": "All"}]

    if not df.empty:
        cardinal_options += [
            {"label": str(value), "value": str(value)}
            for value in sorted(
                df["cardinal_point"].dropna().astype(str).unique()
            )
        ]

        available_statuses = set(
            df["system_readiness_status_v2"]
            .dropna()
            .astype(str)
            .unique()
        )

        status_options += [
            {"label": status, "value": status}
            for status in STATUS_ORDER
            if status in available_statuses
        ]

    return cardinal_options, status_options


@app.callback(
    Output("data-message", "children"),
    Output("kpi-row", "children"),
    Output("readiness-gauge", "figure"),
    Output("margin-gauge", "figure"),
    Output("reserve-gauge", "figure"),
    Output("insight-row", "children"),
    Output("readiness-trend", "figure"),
    Output("margin-status", "figure"),
    Output("reserve-trend", "figure"),
    Output("cardinal-chart", "figure"),
    Output("attention-chart", "figure"),
    Output("status-mix", "figure"),
    Output("latest-table", "data"),
    Output("latest-table", "columns"),
    Input("cardinal-filter", "value"),
    Input("status-filter", "value"),
    Input("record-window", "value"),
    Input("auto-refresh", "n_intervals"),
    Input("refresh-button", "n_clicks"),
)
def update_dashboard(
    selected_cardinal,
    selected_status,
    selected_window,
    _,
    __,
):
    try:
        df = load_data()
        data_message = ""
    except RuntimeError as exc:
        message = html.Div(
            f"Data connection error: {exc}",
            className="error-message",
        )

        blank_kpis = [
            kpi_card("Records shown", "0", "No data"),
            kpi_card("Latest SOP time", "N/A", "No data"),
            kpi_card("Readiness score", "N/A", "No data"),
            kpi_card("Operating margin", "N/A", "No data"),
            kpi_card("Reserve coverage", "N/A", "No data"),
            kpi_card("Dispatch headroom", "N/A", "No data"),
        ]

        blank = empty_figure("No data")

        return (
            message,
            blank_kpis,
            blank,
            blank,
            blank,
            [],
            blank,
            blank,
            blank,
            blank,
            blank,
            blank,
            [],
            [],
        )

    filtered_df = df.copy()

    if selected_cardinal and selected_cardinal != "All":
        filtered_df = filtered_df[
            filtered_df["cardinal_point"].astype(str) == selected_cardinal
        ]

    if selected_status and selected_status != "All":
        filtered_df = filtered_df[
            filtered_df["system_readiness_status_v2"].astype(str)
            == selected_status
        ]

    filtered_df = filtered_df.sort_values("sop_datetime")

    if selected_window and selected_window != "All":
        filtered_df = filtered_df.tail(int(selected_window))

    if filtered_df.empty:
        blank_kpis = [
            kpi_card("Records shown", "0", "No matching records"),
            kpi_card("Latest SOP time", "N/A", "No matching records"),
            kpi_card("Readiness score", "N/A", "No matching records"),
            kpi_card("Operating margin", "N/A", "No matching records"),
            kpi_card("Reserve coverage", "N/A", "No matching records"),
            kpi_card("Dispatch headroom", "N/A", "No matching records"),
        ]

        blank = empty_figure("No matching data")

        return (
            html.Div(
                "No records match the selected filters.",
                className="warning-message",
            ),
            blank_kpis,
            blank,
            blank,
            blank,
            [],
            blank,
            blank,
            blank,
            blank,
            blank,
            blank,
            [],
            [],
        )

    latest = filtered_df.iloc[-1]

    latest_status = str(latest["system_readiness_status_v2"])
    readiness_colour = STATUS_COLOURS.get(
        latest_status,
        STATUS_COLOURS["Unknown"],
    )
    margin_status = latest["margin_status"]
    margin_colour = MARGIN_COLOURS.get(margin_status, "#64748b")
    reserve_status = latest["reserve_status"]
    reserve_colour = STATUS_COLOURS.get(reserve_status, "#64748b")

    latest_time = latest["sop_datetime"].strftime("%d %b %Y %H:%M UTC")

    kpis = [
        kpi_card(
            "Records shown",
            f"{len(filtered_df):,}",
            f"{len(df):,} total records in database",
            "#475569",
        ),
        kpi_card(
            "Latest SOP time",
            latest_time,
            f"Cardinal point: {latest['cardinal_point']}",
            "#1e3a8a",
        ),
        kpi_card(
            "Readiness score",
            format_number(latest["system_readiness_score_v2"], 1),
            latest_status,
            readiness_colour,
        ),
        kpi_card(
            "Operating margin",
            f"{format_number(latest['operating_margin_surplus'], 0)} MW",
            margin_status,
            margin_colour,
        ),
        kpi_card(
            "Reserve coverage",
            format_number(latest["reserve_coverage_ratio"], 2),
            reserve_status,
            reserve_colour,
        ),
        kpi_card(
            "Dispatch headroom",
            f"{format_number(latest['dispatch_headroom_mw'], 0)} MW",
            "TEMX minus TEOL",
            "#7c3aed",
        ),
    ]

    readiness_gauge = gauge_figure(
        latest["system_readiness_score_v2"],
        "System readiness",
        max_value=100,
    )

    margin_value = latest["operating_margin_surplus"]
    margin_gauge_max = max(
        5000,
        float(filtered_df["operating_margin_surplus"].max(skipna=True) or 5000),
    )

    margin_gauge = gauge_figure(
        margin_value,
        "Operating margin",
        suffix=" MW",
        max_value=margin_gauge_max,
        thresholds=[
            (0, 500, "#fee2e2"),
            (500, 1000, "#fef3c7"),
            (1000, 3000, "#dbeafe"),
            (3000, margin_gauge_max, "#dcfce7"),
        ],
    )

    reserve_value = latest["reserve_coverage_ratio"]
    reserve_gauge_max = max(
        1.25,
        float(filtered_df["reserve_coverage_ratio"].max(skipna=True) or 1.25),
    )

    reserve_gauge = gauge_figure(
        reserve_value,
        "Reserve coverage",
        max_value=reserve_gauge_max,
        thresholds=[
            (0, 0.80, "#fee2e2"),
            (0.80, 0.90, "#fef3c7"),
            (0.90, 1.00, "#dbeafe"),
            (1.00, reserve_gauge_max, "#dcfce7"),
        ],
    )

    latest_table = (
        filtered_df.sort_values("sop_datetime", ascending=False)
        .head(20)
        [
            [
                "sop_datetime",
                "cardinal_point",
                "total_sop_demand",
                "operating_margin_surplus",
                "margin_status",
                "reserve_coverage_ratio",
                "reserve_status",
                "dispatch_headroom_mw",
                "absolute_imbalance_mw",
                "system_readiness_score_v2",
                "system_readiness_status_v2",
                "operational_attention_summary",
                "collected_at",
            ]
        ]
        .copy()
    )

    latest_table["sop_datetime"] = latest_table[
        "sop_datetime"
    ].dt.strftime("%d %b %Y %H:%M")

    latest_table["collected_at"] = latest_table[
        "collected_at"
    ].dt.strftime("%d %b %Y %H:%M")

    for column in [
        "total_sop_demand",
        "operating_margin_surplus",
        "dispatch_headroom_mw",
        "absolute_imbalance_mw",
    ]:
        latest_table[column] = latest_table[column].map(
            lambda value: format_number(value, 0)
        )

    latest_table["reserve_coverage_ratio"] = latest_table[
        "reserve_coverage_ratio"
    ].map(lambda value: format_number(value, 2))

    latest_table["system_readiness_score_v2"] = latest_table[
        "system_readiness_score_v2"
    ].map(lambda value: format_number(value, 1))

    columns = [
        {"name": "SOP datetime", "id": "sop_datetime"},
        {"name": "Cardinal point", "id": "cardinal_point"},
        {"name": "Demand MW", "id": "total_sop_demand"},
        {"name": "Margin MW", "id": "operating_margin_surplus"},
        {"name": "Margin status", "id": "margin_status"},
        {"name": "Reserve coverage", "id": "reserve_coverage_ratio"},
        {"name": "Reserve status", "id": "reserve_status"},
        {"name": "Headroom MW", "id": "dispatch_headroom_mw"},
        {"name": "Absolute imbalance MW", "id": "absolute_imbalance_mw"},
        {"name": "Readiness score", "id": "system_readiness_score_v2"},
        {"name": "Readiness status", "id": "system_readiness_status_v2"},
        {"name": "Operational attention", "id": "operational_attention_summary"},
        {"name": "Collected at", "id": "collected_at"},
    ]

    return (
        data_message,
        kpis,
        readiness_gauge,
        margin_gauge,
        reserve_gauge,
        build_executive_insights(filtered_df),
        build_readiness_trend(filtered_df),
        build_margin_status_figure(filtered_df),
        build_reserve_figure(filtered_df),
        build_cardinal_figure(filtered_df),
        build_attention_figure(filtered_df),
        build_status_mix(filtered_df),
        latest_table.to_dict("records"),
        columns,
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
            * {
                box-sizing: border-box;
            }

            body {
                margin: 0;
                font-family: Arial, Helvetica, sans-serif;
                background: #f4f7fb;
                color: #111827;
            }

            .page {
                max-width: 1500px;
                margin: 0 auto;
                padding: 28px;
            }

            .hero {
                background: linear-gradient(135deg, #0f172a, #1d4ed8);
                color: white;
                padding: 36px;
                border-radius: 28px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 24px;
                box-shadow: 0 18px 45px rgba(15, 23, 42, 0.20);
            }

            .eyebrow {
                font-size: 12px;
                letter-spacing: 0.18em;
                font-weight: 800;
                color: #bfdbfe;
                margin-bottom: 10px;
            }

            .hero h1 {
                margin: 0 0 12px 0;
                font-size: 36px;
                line-height: 1.15;
            }

            .hero p {
                margin: 0;
                color: #dbeafe;
                font-size: 16px;
                line-height: 1.55;
                max-width: 900px;
            }

            .hero-badge {
                background: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.20);
                padding: 16px 20px;
                border-radius: 18px;
                min-width: 260px;
                color: #e0f2fe;
                text-align: center;
            }

            .badge-title {
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 0.12em;
                margin-bottom: 7px;
                color: white;
            }

            .summary-strip {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 14px;
                margin: 22px 0;
            }

            .summary-strip > div {
                background: white;
                border: 1px solid #dfe7f1;
                border-radius: 15px;
                padding: 15px;
                color: #475569;
                line-height: 1.45;
                box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
            }

            .summary-strip strong {
                color: #0f172a;
            }

            .controls {
                display: grid;
                grid-template-columns: 1fr 1fr 1fr 180px;
                gap: 18px;
                background: white;
                padding: 20px;
                border-radius: 18px;
                margin-bottom: 24px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
                border: 1px solid #e2e8f0;
            }

            .controls label {
                display: block;
                font-weight: 700;
                margin-bottom: 8px;
                color: #334155;
            }

            button {
                width: 100%;
                height: 38px;
                border: 0;
                border-radius: 9px;
                background: #2563eb;
                color: white;
                font-weight: 700;
                cursor: pointer;
            }

            button:hover {
                background: #1d4ed8;
            }

            .kpi-grid {
                display: grid;
                grid-template-columns: repeat(6, 1fr);
                gap: 16px;
                margin-bottom: 28px;
            }

            .kpi-card {
                background: white;
                border-radius: 18px;
                padding: 18px;
                border: 1px solid #e2e8f0;
                box-shadow: 0 10px 26px rgba(15, 23, 42, 0.07);
            }

            .kpi-title {
                color: #64748b;
                text-transform: uppercase;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 0.05em;
            }

            .kpi-value {
                font-size: 24px;
                font-weight: 800;
                margin-top: 8px;
                color: #0f172a;
            }

            .kpi-subtitle {
                font-size: 13px;
                color: #64748b;
                margin-top: 7px;
            }

            .section-heading {
                margin: 30px 0 14px 0;
            }

            .section-heading h2 {
                margin: 0 0 6px 0;
                font-size: 24px;
                color: #0f172a;
            }

            .section-heading p {
                margin: 0;
                color: #64748b;
                line-height: 1.5;
            }

            .gauge-grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 18px;
            }

            .gauge-card {
                background: white;
                border-radius: 20px;
                border: 1px solid #e2e8f0;
                padding: 8px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
            }

            .insight-grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 18px;
                margin-bottom: 28px;
            }

            .insight-card {
                background: white;
                border-radius: 18px;
                border: 1px solid #e2e8f0;
                padding: 20px;
                box-shadow: 0 10px 26px rgba(15, 23, 42, 0.07);
            }

            .insight-card h3 {
                margin: 0 0 10px 0;
                color: #0f172a;
            }

            .insight-card p {
                margin: 0 0 14px 0;
                color: #475569;
                line-height: 1.5;
            }

            .action-text {
                font-size: 14px;
                line-height: 1.45;
            }

            .insight-positive {
                border-left: 6px solid #16a34a;
            }

            .insight-warning {
                border-left: 6px solid #f59e0b;
            }

            .insight-critical {
                border-left: 6px solid #dc2626;
            }

            .insight-neutral {
                border-left: 6px solid #64748b;
            }

            .chart-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 18px;
                margin-top: 28px;
            }

            .full-width {
                grid-column: span 2;
            }

            .chart-card {
                background: white;
                border-radius: 20px;
                border: 1px solid #e2e8f0;
                padding: 12px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
            }

            .chart-explainer {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 12px;
                margin: 0 8px 8px 8px;
            }

            .chart-explainer > div {
                background: #f8fafc;
                border-radius: 12px;
                padding: 12px;
                border: 1px solid #e2e8f0;
            }

            .chart-explainer strong {
                color: #0f172a;
                font-size: 13px;
            }

            .chart-explainer p {
                margin: 6px 0 0 0;
                color: #475569;
                font-size: 13px;
                line-height: 1.45;
            }

            .table-section {
                background: white;
                border-radius: 20px;
                border: 1px solid #e2e8f0;
                padding: 20px;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
                margin-top: 28px;
            }

            .table-heading {
                margin-top: 0;
            }

            .error-message {
                background: #fee2e2;
                color: #991b1b;
                border-left: 5px solid #dc2626;
                padding: 14px;
                border-radius: 12px;
                margin-bottom: 18px;
            }

            .warning-message {
                background: #fef3c7;
                color: #92400e;
                border-left: 5px solid #f59e0b;
                padding: 14px;
                border-radius: 12px;
                margin-bottom: 18px;
            }

            .footer {
                text-align: center;
                color: #64748b;
                font-size: 13px;
                padding: 26px 10px;
            }

            @media (max-width: 1200px) {
                .kpi-grid {
                    grid-template-columns: repeat(3, 1fr);
                }

                .summary-strip {
                    grid-template-columns: 1fr;
                }

                .gauge-grid {
                    grid-template-columns: 1fr;
                }

                .insight-grid {
                    grid-template-columns: 1fr;
                }

                .chart-grid {
                    grid-template-columns: 1fr;
                }

                .full-width {
                    grid-column: span 1;
                }

                .controls {
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

                .hero {
                    padding: 24px;
                }

                .hero h1 {
                    font-size: 27px;
                }

                .hero-badge {
                    width: 100%;
                    min-width: 0;
                }

                .controls {
                    grid-template-columns: 1fr;
                }

                .kpi-grid {
                    grid-template-columns: 1fr;
                }

                .chart-explainer {
                    grid-template-columns: 1fr;
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
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8050)),
        debug=False,
    )
