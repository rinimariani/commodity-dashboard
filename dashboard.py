"""
Commodity Exchange Dashboard - Streamlit App
==============================================
Reads directly from commodity_dashboard.db (SQLite) built by
generate_data.py. Dark theme (black background), Plotly charts.

Run: streamlit run dashboard.py
"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DB_PATH = Path(__file__).parent / "commodity_dashboard.db"

# ------------------------------------------------------------
# Palet warna - dark theme
# ------------------------------------------------------------
BG = "#0e0e12"
PANEL = "#17171d"
GRID = "#2a2a33"
TEXT = "#e8e8ec"
MUTED = "#9a9aa5"
ACCENT = "#22d3ee"      # cyan
ACCENT2 = "#f59e0b"     # amber
UP = "#34d399"          # green
DOWN = "#f87171"        # red
SERIES_COLORS = ["#22d3ee", "#f59e0b", "#a78bfa", "#34d399", "#f87171", "#60a5fa"]

st.set_page_config(
    page_title="Commodity Exchange Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {BG}; color: {TEXT}; }}
    section[data-testid="stSidebar"] {{ background-color: {PANEL}; }}
    div[data-testid="stMetric"] {{
        background-color: {PANEL};
        border: 1px solid {GRID};
        border-radius: 10px;
        padding: 14px 16px;
    }}
    div[data-testid="stMetric"] label {{ color: {MUTED}; }}
    h1, h2, h3, h4 {{ color: {TEXT}; }}
    hr {{ border-color: {GRID}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=600)
def load_tables():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    commodity = pd.read_sql("SELECT * FROM dim_commodity", conn)
    broker = pd.read_sql("SELECT * FROM dim_broker", conn)
    market = pd.read_sql(
        """
        SELECT f.*, d.full_date, c.commodity_name, c.category, c.unit, c.exchange
        FROM fact_market_daily f
        JOIN dim_date d ON f.date_key = d.date_key
        JOIN dim_commodity c ON f.commodity_id = c.commodity_id
        """,
        conn,
        parse_dates=["full_date"],
    )
    tx = pd.read_sql(
        """
        SELECT t.*, d.full_date, c.commodity_name, b.broker_name, b.broker_tier
        FROM fact_broker_transaction t
        JOIN dim_date d ON t.date_key = d.date_key
        JOIN dim_commodity c ON t.commodity_id = c.commodity_id
        JOIN dim_broker b ON t.broker_id = b.broker_id
        """,
        conn,
        parse_dates=["full_date"],
    )
    conn.close()
    return commodity, broker, market, tx


def dark_layout(fig, height=420, title=None):
    fig.update_layout(
        height=height,
        title=title,
        paper_bgcolor=BG,
        plot_bgcolor=PANEL,
        font=dict(color=TEXT),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=10, r=10, t=50 if title else 20, b=10),
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
        hovermode="x unified",
    )
    return fig


data = load_tables()
if data is None:
    st.error(
        f"Database not found at `{DB_PATH}`. "
        "Run `python generate_data.py` first to create it."
    )
    st.stop()

commodity_df, broker_df, market_df, tx_df = data

# ------------------------------------------------------------
# Sidebar - filters
# ------------------------------------------------------------
st.sidebar.title("📊 Filters")

commodities = sorted(market_df["commodity_name"].unique())
selected_commodities = st.sidebar.multiselect(
    "Commodity", commodities, default=commodities
)

min_date = market_df["full_date"].min().date()
max_date = market_df["full_date"].max().date()
date_range = st.sidebar.date_input(
    "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

ma_window = st.sidebar.selectbox("Moving average", [7, 14, 30], index=2)

if not selected_commodities:
    st.warning("Select at least one commodity in the sidebar.")
    st.stop()

mask_m = (
    market_df["commodity_name"].isin(selected_commodities)
    & (market_df["full_date"].dt.date >= start_date)
    & (market_df["full_date"].dt.date <= end_date)
)
mkt = market_df.loc[mask_m].sort_values(["commodity_name", "full_date"]).copy()

mask_t = (
    tx_df["commodity_name"].isin(selected_commodities)
    & (tx_df["full_date"].dt.date >= start_date)
    & (tx_df["full_date"].dt.date <= end_date)
)
tx = tx_df.loc[mask_t].copy()

# ------------------------------------------------------------
# Header + KPI
# ------------------------------------------------------------
st.title("Commodity Exchange Dashboard")
st.caption(
    "Price & volume from yfinance (real data) · broker transactions are "
    "**simulated data** for dashboard demo purposes."
)

kpi_cols = st.columns(4)
latest = mkt.sort_values("full_date").groupby("commodity_name").tail(1)
prev = (
    mkt.sort_values("full_date")
    .groupby("commodity_name")
    .nth(-2)
    if len(mkt) else mkt
)

total_volume = int(mkt["total_volume"].sum())
total_tx_value = float(tx["transaction_value"].sum())
n_days = mkt["full_date"].nunique()
avg_close = mkt.groupby("commodity_name")["close_price"].last().mean()

kpi_cols[0].metric("Total volume (period)", f"{total_volume:,}")
kpi_cols[1].metric("Total transaction value (USD proxy)", f"{total_tx_value:,.0f}")
kpi_cols[2].metric("Trading days covered", f"{n_days:,}")
kpi_cols[3].metric("Avg. latest close price", f"{avg_close:,.2f}")

st.divider()

# ------------------------------------------------------------
# 1. Price trend + moving average
# ------------------------------------------------------------
st.subheader("Price Trend & Moving Average")

fig = go.Figure()
for i, name in enumerate(selected_commodities):
    sub = mkt[mkt["commodity_name"] == name].sort_values("full_date")
    color = SERIES_COLORS[i % len(SERIES_COLORS)]
    fig.add_trace(
        go.Scatter(
            x=sub["full_date"], y=sub["close_price"],
            name=f"{name} (close)", line=dict(color=color, width=1.4),
            opacity=0.55,
        )
    )
    ma = sub["close_price"].rolling(ma_window, min_periods=1).mean()
    fig.add_trace(
        go.Scatter(
            x=sub["full_date"], y=ma,
            name=f"{name} MA{ma_window}", line=dict(color=color, width=2.4),
        )
    )
dark_layout(fig, height=460)
st.plotly_chart(fig, width='stretch')

# ------------------------------------------------------------
# 2. Daily volume
# ------------------------------------------------------------
vcol, rcol = st.columns([3, 2])

with vcol:
    st.subheader("Daily Trading Volume")
    fig_v = go.Figure()
    for i, name in enumerate(selected_commodities):
        sub = mkt[mkt["commodity_name"] == name].sort_values("full_date")
        fig_v.add_trace(
            go.Bar(
                x=sub["full_date"], y=sub["total_volume"], name=name,
                marker_color=SERIES_COLORS[i % len(SERIES_COLORS)],
            )
        )
    fig_v.update_layout(barmode="overlay")
    dark_layout(fig_v, height=380)
    st.plotly_chart(fig_v, width='stretch')

# ------------------------------------------------------------
# 3. Broker ranking
# ------------------------------------------------------------
with rcol:
    st.subheader("Broker Ranking (volume)")
    broker_rank = (
        tx.groupby(["broker_name", "broker_tier"])["transaction_volume"]
        .sum()
        .reset_index()
        .sort_values("transaction_volume", ascending=True)
    )
    fig_b = go.Figure(
        go.Bar(
            x=broker_rank["transaction_volume"],
            y=broker_rank["broker_name"],
            orientation="h",
            marker_color=ACCENT,
            text=broker_rank["broker_tier"],
            textposition="outside",
            textfont=dict(color=MUTED),
        )
    )
    dark_layout(fig_b, height=380)
    st.plotly_chart(fig_b, width='stretch')

st.divider()

# ------------------------------------------------------------
# 4. Market concentration (HHI) per month
# ------------------------------------------------------------
st.subheader("Market Concentration (HHI) by Month")

tx["year_month"] = tx["full_date"].dt.to_period("M").astype(str)
monthly = (
    tx.groupby(["commodity_name", "year_month", "broker_id"])["transaction_volume"]
    .sum()
    .reset_index()
)
monthly["total"] = monthly.groupby(["commodity_name", "year_month"])[
    "transaction_volume"
].transform("sum")
monthly["share_sq"] = (monthly["transaction_volume"] / monthly["total"] * 100) ** 2
hhi = (
    monthly.groupby(["commodity_name", "year_month"])["share_sq"]
    .sum()
    .reset_index()
    .rename(columns={"share_sq": "hhi"})
    .sort_values("year_month")
)

fig_h = go.Figure()
for i, name in enumerate(selected_commodities):
    sub = hhi[hhi["commodity_name"] == name]
    fig_h.add_trace(
        go.Scatter(
            x=sub["year_month"], y=sub["hhi"], name=name, mode="lines+markers",
            line=dict(color=SERIES_COLORS[i % len(SERIES_COLORS)], width=2),
        )
    )
fig_h.add_hline(y=2500, line_dash="dot", line_color=DOWN,
                 annotation_text="high concentration threshold (2500)",
                 annotation_font_color=MUTED)
dark_layout(fig_h, height=380)
st.plotly_chart(fig_h, width='stretch')

st.divider()

# ------------------------------------------------------------
# 5. Anomaly: volume spike, stagnant price
# ------------------------------------------------------------
st.subheader("Anomaly: Volume Spike vs. Price")

anomalies = []
for name in selected_commodities:
    sub = mkt[mkt["commodity_name"] == name].sort_values("full_date").copy()
    sub["avg_volume_30d"] = sub["total_volume"].rolling(30, min_periods=5).mean()
    sub["volume_ratio"] = sub["total_volume"] / sub["avg_volume_30d"]
    hits = sub[sub["volume_ratio"] > 1.5].copy()
    anomalies.append(hits)

anomaly_df = pd.concat(anomalies) if anomalies else pd.DataFrame()
if not anomaly_df.empty:
    show = anomaly_df.sort_values("volume_ratio", ascending=False).head(20)[
        ["commodity_name", "full_date", "total_volume", "avg_volume_30d", "volume_ratio", "close_price"]
    ]
    show["full_date"] = show["full_date"].dt.date
    show = show.rename(columns={
        "commodity_name": "Commodity", "full_date": "Date", "total_volume": "Volume",
        "avg_volume_30d": "Avg. 30d Volume", "volume_ratio": "Volume Ratio", "close_price": "Close Price",
    })
    st.dataframe(
        show.style.format({
            "Volume": "{:,.0f}", "Avg. 30d Volume": "{:,.0f}",
            "Volume Ratio": "{:.2f}x", "Close Price": "{:,.2f}",
        }),
        width='stretch',
        hide_index=True,
    )
else:
    st.info("No volume anomalies (>1.5x the 30-day average) in this range/filter.")

st.caption(
    "Built with Streamlit + Plotly + pandas + SQLite. "
    "Price data: Yahoo Finance (yfinance). Broker transaction data: simulated."
)
