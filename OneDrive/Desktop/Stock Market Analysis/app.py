"""Interactive stock market analysis dashboard."""

from __future__ import annotations

from datetime import timedelta

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

from analysis import (
    calculate_metrics,
    clean_stock_data,
    convert_price_values,
    enrich_stock_data,
    monthly_returns,
)

BACKGROUND = "#0b1220"
PANEL = "#111b2e"
TEXT = "#e5edf8"
MUTED = "#91a2bb"
ACCENT = "#53d6a2"
RED = "#ff7185"


st.set_page_config(
    page_title="Market Lens | Stock Analysis",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
      .stApp {{ background: {BACKGROUND}; color: {TEXT}; }}
      [data-testid="stSidebar"] {{ background: #0e1728; border-right: 1px solid #1f2b40; }}
      [data-testid="stMetric"] {{ background: {PANEL}; border: 1px solid #24324a;
        border-radius: 14px; padding: 18px 20px; }}
      [data-testid="stMetricLabel"] {{ color: {MUTED}; }}
      [data-testid="stMetricValue"] {{ color: {TEXT}; }}
      .hero {{ padding: 4px 0 20px; }}
      .eyebrow {{ color: {ACCENT}; font-size: 0.78rem; letter-spacing: .15em;
        text-transform: uppercase; font-weight: 700; }}
      .subtitle {{ color: {MUTED}; margin-top: -10px; }}
      div[data-testid="stTabs"] button {{ color: {MUTED}; }}
      div[data-testid="stDataFrame"] {{ border: 1px solid #24324a; border-radius: 12px; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def make_demo_data() -> pd.DataFrame:
    """Create reproducible sample daily history from 2021 through today."""
    rng = np.random.default_rng(17)
    dates = pd.bdate_range(start="2021-01-01", end=pd.Timestamp.today().normalize())
    daily_returns = rng.normal(loc=0.00035, scale=0.015, size=len(dates))
    close = 120 * np.cumprod(1 + daily_returns)
    overnight = rng.normal(loc=0.0, scale=0.004, size=len(dates))
    open_price = close * (1 + overnight)
    high = np.maximum(open_price, close) * (1 + rng.uniform(0.001, 0.018, len(dates)))
    low = np.minimum(open_price, close) * (1 - rng.uniform(0.001, 0.018, len(dates)))
    volume = rng.lognormal(mean=15.2, sigma=0.35, size=len(dates)).astype(np.int64)
    return pd.DataFrame(
        {"Date": dates, "Open": open_price, "High": high, "Low": low, "Close": close, "Volume": volume}
    )


def show_plot(figure: plt.Figure) -> None:
    figure.tight_layout()
    st.pyplot(figure, width="stretch")
    plt.close(figure)


def format_percent(value: float) -> str:
    return f"{value:+.2%}"


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_usd_inr_rate() -> tuple[float, str]:
    """Fetch and validate the latest published USD/INR reference rate."""
    try:
        response = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        raise RuntimeError(f"Could not retrieve the live USD/INR rate: {error}") from error
    except ValueError as error:
        raise RuntimeError("The exchange-rate service returned invalid JSON.") from error

    if not isinstance(payload, dict) or payload.get("result") != "success" or payload.get("base_code") != "USD":
        raise RuntimeError("The exchange-rate service did not return a valid USD quote.")
    rates = payload.get("rates")
    if not isinstance(rates, dict):
        raise RuntimeError("The exchange-rate response did not include currency rates.")
    try:
        rate = float(rates["INR"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("The exchange-rate response did not include a valid INR rate.") from error
    if not np.isfinite(rate) or rate <= 0:
        raise RuntimeError("The exchange-rate service returned a non-positive USD/INR rate.")

    updated_at = payload.get("time_last_update_utc")
    if not isinstance(updated_at, str) or not updated_at.strip():
        raise RuntimeError("The exchange-rate response did not include its update time.")
    return rate, updated_at


st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Market intelligence · Historical analysis</div>
      <h1>Market Lens</h1>
      <div class="subtitle">Understand price action, performance, and trading activity.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Data & controls")
    source = st.radio("Data source", ("Demo data", "Upload CSV"), horizontal=True)
    if source == "Upload CSV":
        uploaded_file = st.file_uploader("Upload historical prices", type=("csv",))
        symbol = st.text_input("Ticker / label", value="MY STOCK", max_chars=12).strip().upper() or "STOCK"
        price_currency = st.selectbox("Uploaded price currency", ("USD", "INR"), key="price_currency")
    else:
        uploaded_file = None
        symbol = "DEMO"
        price_currency = "USD"
        st.caption("A reproducible synthetic sample series from Jan 2021 to today is shown. Upload a CSV to analyze your own history.")

    st.divider()
    short_window = st.slider("Short moving average (days)", 5, 60, 20)
    long_window = st.slider("Long moving average (days)", 20, 200, 50)
    if st.button("Refresh live USD/INR rate", key="refresh_fx"):
        fetch_usd_inr_rate.clear()
    if short_window >= long_window:
        st.error("The short moving average must be less than the long moving average.")
        st.stop()

try:
    if source == "Upload CSV":
        if uploaded_file is None:
            st.info("Upload a CSV to begin. Required columns: **Date** and **Close**. Open, High, Low, and Volume are optional.")
            st.stop()
        raw_data = pd.read_csv(uploaded_file)
        raw_data = clean_stock_data(raw_data)
    else:
        raw_data = clean_stock_data(make_demo_data())
except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as error:
    st.error(f"Could not read this stock history: {error}")
    st.stop()

if raw_data.empty:
    st.warning("No valid stock data is available.")
    st.stop()

minimum_date = raw_data["Date"].min().date()
maximum_date = raw_data["Date"].max().date()
default_start = max(minimum_date, maximum_date - timedelta(days=365))

with st.sidebar:
    period_options = ("1M", "3M", "6M", "1Y", "3Y", "All time", "Custom")
    period = st.selectbox(
        "Analysis period",
        period_options,
        index=5 if source == "Demo data" else 3,
        key="period",
    )
    if period == "Custom":
        selected_dates = st.date_input(
            "Choose date range",
            value=(default_start, maximum_date),
            min_value=minimum_date,
            max_value=maximum_date,
            key=f"analysis_period_{minimum_date}_{maximum_date}_{len(raw_data)}",
        )
        if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
            start_date, end_date = selected_dates
        else:
            start_date, end_date = minimum_date, maximum_date
    elif period == "All time":
        start_date, end_date = minimum_date, maximum_date
    else:
        months = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36}[period]
        start_date = max(minimum_date, (pd.Timestamp(maximum_date) - pd.DateOffset(months=months)).date())
        end_date = maximum_date

if start_date > end_date:
    st.error("The start date must be on or before the end date.")
    st.stop()

filtered = raw_data.loc[
    raw_data["Date"].dt.date.between(start_date, end_date)
].reset_index(drop=True)
if filtered.empty:
    st.warning("There are no trading observations in the selected period.")
    st.stop()

data = enrich_stock_data(filtered, (short_window, long_window))
if price_currency == "USD":
    try:
        usd_inr_rate, fx_updated_at = fetch_usd_inr_rate()
    except RuntimeError as error:
        st.error(f"{error} Check your internet connection and refresh the rate to retry.")
        st.stop()
    price_multiplier = usd_inr_rate
    st.caption(
        f"Live reference rate: **$1 = ₹{usd_inr_rate:,.4f}** · updated {fx_updated_at}. "
        "This latest rate is applied uniformly to historical prices."
    )
else:
    price_multiplier = 1.0
    st.caption("Uploaded prices are already in Indian rupees; no currency conversion was applied.")
display_data = convert_price_values(data, price_multiplier)
metrics = calculate_metrics(data)
latest_change = float(data["Daily Return"].iloc[-1]) if len(data) > 1 else 0.0
st.caption(
    f"**{symbol}** · {start_date:%b %d, %Y} — {end_date:%b %d, %Y} · "
    f"{int(metrics['observations'])} sessions"
)

kpi_columns = st.columns(5)
kpi_columns[0].metric("Latest close", f"₹{metrics['latest_close'] * price_multiplier:,.2f}", format_percent(latest_change))
kpi_columns[1].metric("Period return", format_percent(metrics["period_return"]))
kpi_columns[2].metric("Annualized volatility", f"{metrics['annualized_volatility']:.2%}")
kpi_columns[3].metric("Maximum drawdown", format_percent(metrics["max_drawdown"]))
kpi_columns[4].metric(
    "Average daily volume",
    f"{metrics['average_volume']:,.0f}" if metrics["average_volume"] else "—",
)

price_tab, returns_tab, activity_tab, data_tab = st.tabs(
    ("Price & trend", "Returns & risk", "Trading activity", "Data & insights")
)

with price_tab:
    controls = st.columns((1, 1, 1, 2))
    chart_style = controls[0].selectbox("Chart type", ("Line", "Candlestick"), key="chart_style")
    show_short_ma = controls[1].checkbox(f"{short_window}-day MA", value=True, key="show_short_ma")
    show_long_ma = controls[2].checkbox(f"{long_window}-day MA", value=True, key="show_long_ma")
    show_rsi = controls[3].checkbox("Show RSI panel", value=False, key="show_rsi")

    rows = 2 if show_rsi else 1
    figure = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.76, 0.24] if show_rsi else [1],
    )
    if chart_style == "Candlestick":
        figure.add_trace(
            go.Candlestick(
                x=display_data["Date"],
                open=display_data["Open"],
                high=display_data["High"],
                low=display_data["Low"],
                close=display_data["Close"],
                name="OHLC",
                increasing_line_color=ACCENT,
                decreasing_line_color=RED,
            ),
            row=1,
            col=1,
        )
    else:
        figure.add_trace(
            go.Scatter(
                x=display_data["Date"], y=display_data["Close"], name="Close", mode="lines",
                line={"color": ACCENT, "width": 2},
            ),
            row=1,
            col=1,
        )
    if show_short_ma:
        figure.add_trace(
            go.Scatter(
                x=display_data["Date"], y=display_data[f"MA {short_window}"], name=f"{short_window}-day MA",
                mode="lines", line={"color": "#78a9ff", "width": 1.4},
            ),
            row=1,
            col=1,
        )
    if show_long_ma:
        figure.add_trace(
            go.Scatter(
                x=display_data["Date"], y=display_data[f"MA {long_window}"], name=f"{long_window}-day MA",
                mode="lines", line={"color": "#c29bff", "width": 1.4},
            ),
            row=1,
            col=1,
        )
    if show_rsi:
        figure.add_trace(
            go.Scatter(
                x=data["Date"], y=data["RSI 14"], name="RSI (14)",
                line={"color": "#ffbc66", "width": 1.5},
            ),
            row=2,
            col=1,
        )
        figure.add_hrect(y0=70, y1=100, fillcolor=RED, opacity=0.08, line_width=0, row=2, col=1)
        figure.add_hrect(y0=0, y1=30, fillcolor=ACCENT, opacity=0.08, line_width=0, row=2, col=1)
        figure.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
    figure.update_layout(
        title={"text": f"{symbol} · {chart_style.lower()} price and trend", "x": 0.02},
        template="plotly_dark",
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=PANEL,
        font={"color": TEXT},
        hovermode="x unified",
        height=570 if show_rsi else 500,
        margin={"l": 16, "r": 16, "t": 58, "b": 16},
        legend={"orientation": "h", "y": 1.04, "x": 1, "xanchor": "right"},
        xaxis_rangeslider_visible=chart_style == "Candlestick",
    )
    figure.update_yaxes(title_text="Price (₹)", tickprefix="₹", gridcolor="#24324a", row=1, col=1)
    figure.update_xaxes(gridcolor="#24324a", rangeslider_visible=False)
    if chart_style == "Candlestick":
        figure.update_xaxes(rangeslider_visible=True, row=1, col=1)
    st.plotly_chart(
        figure,
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True, "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
        key="price_chart",
    )

with returns_tab:
    left, right = st.columns(2)
    figure = go.Figure(
        go.Scatter(
            x=data["Date"], y=data["Cumulative Return"] * 100, name="Cumulative return",
            fill="tozeroy", line={"color": ACCENT, "width": 2},
            hovertemplate="%{x|%b %d, %Y}<br>Return: %{y:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(
        title="Cumulative performance", yaxis_title="Return (%)",
        template="plotly_dark", paper_bgcolor=BACKGROUND, plot_bgcolor=PANEL,
        font={"color": TEXT}, hovermode="x unified", height=360,
        margin={"l": 16, "r": 16, "t": 52, "b": 16},
    )
    figure.update_xaxes(gridcolor="#24324a")
    figure.update_yaxes(gridcolor="#24324a", ticksuffix="%")
    left.plotly_chart(figure, width="stretch", config={"displaylogo": False}, key="cumulative_chart")

    figure = go.Figure(
        go.Scatter(
            x=data["Date"], y=data["Rolling Volatility"] * 100, name="Annualized volatility",
            line={"color": "#ffbc66", "width": 1.8},
            hovertemplate="%{x|%b %d, %Y}<br>Volatility: %{y:.2f}%<extra></extra>",
        )
    )
    figure.update_layout(
        title="20-session annualized volatility", yaxis_title="Volatility (%)",
        template="plotly_dark", paper_bgcolor=BACKGROUND, plot_bgcolor=PANEL,
        font={"color": TEXT}, hovermode="x unified", height=360,
        margin={"l": 16, "r": 16, "t": 52, "b": 16},
    )
    figure.update_xaxes(gridcolor="#24324a")
    figure.update_yaxes(gridcolor="#24324a", ticksuffix="%")
    right.plotly_chart(figure, width="stretch", config={"displaylogo": False}, key="volatility_chart")

    histogram_bins = st.slider("Daily return histogram bins", 10, 80, 35, key="histogram_bins")
    daily_returns = data["Daily Return"].dropna() * 100
    histogram = go.Figure(
        go.Histogram(
            x=daily_returns,
            nbinsx=histogram_bins,
            marker_color="#78a9ff",
            opacity=0.82,
            hovertemplate="Return: %{x:.2f}%<br>Sessions: %{y}<extra></extra>",
        )
    )
    histogram.update_layout(
        title="Daily return distribution", xaxis_title="Daily return (%)", yaxis_title="Sessions",
        template="plotly_dark", paper_bgcolor=BACKGROUND, plot_bgcolor=PANEL,
        font={"color": TEXT}, height=330,
        margin={"l": 16, "r": 16, "t": 52, "b": 16},
    )
    histogram.update_xaxes(gridcolor="#24324a", ticksuffix="%")
    histogram.update_yaxes(gridcolor="#24324a")
    st.plotly_chart(histogram, width="stretch", config={"displaylogo": False}, key="return_histogram")

    month_table = monthly_returns(filtered)
    if not month_table.empty:
        month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        figure, axis = plt.subplots(
            figsize=(12, max(2, 0.55 * len(month_table.index) + 1.5)),
            facecolor=BACKGROUND,
        )
        image = axis.imshow(month_table.to_numpy() * 100, cmap="RdYlGn", aspect="auto", vmin=-10, vmax=10)
        axis.set_xticks(range(12), month_labels)
        axis.set_yticks(range(len(month_table.index)), month_table.index)
        axis.tick_params(colors=MUTED)
        axis.set_title("Monthly returns (%)", color=TEXT, loc="left", fontsize=12, fontweight="bold", pad=12)
        for row in range(month_table.shape[0]):
            for column in range(month_table.shape[1]):
                value = month_table.iloc[row, column]
                if pd.notna(value):
                    axis.text(column, row, f"{value:.1%}", ha="center", va="center", fontsize=8, color=BACKGROUND)
        figure.colorbar(image, ax=axis, fraction=0.02, pad=0.02)
        show_plot(figure)
    else:
        st.info("Monthly returns need data spanning at least two calendar months.")

with activity_tab:
    if data["Volume"].notna().any():
        volume_colors = np.where(data["Daily Return"].fillna(0) >= 0, ACCENT, RED)
        figure = make_subplots(specs=[[{"secondary_y": True}]])
        figure.add_trace(
            go.Bar(
                x=data["Date"], y=data["Volume"], name="Volume",
                marker_color=volume_colors, opacity=0.6,
                hovertemplate="%{x|%b %d, %Y}<br>Volume: %{y:,.0f}<extra></extra>",
            ),
            secondary_y=False,
        )
        figure.add_trace(
            go.Scatter(
                x=display_data["Date"], y=display_data["Close"], name="Close",
                line={"color": ACCENT, "width": 2},
                hovertemplate="%{x|%b %d, %Y}<br>Close: ₹%{y:,.2f}<extra></extra>",
            ),
            secondary_y=True,
        )
        figure.update_layout(
            title="Price and trading activity", template="plotly_dark",
            paper_bgcolor=BACKGROUND, plot_bgcolor=PANEL, font={"color": TEXT},
            hovermode="x unified", height=490,
            margin={"l": 16, "r": 16, "t": 58, "b": 16},
            legend={"orientation": "h", "y": 1.04, "x": 1, "xanchor": "right"},
        )
        figure.update_xaxes(gridcolor="#24324a", rangeslider_visible=True)
        figure.update_yaxes(title_text="Volume", gridcolor="#24324a", secondary_y=False)
        figure.update_yaxes(title_text="Price (₹)", tickprefix="₹", secondary_y=True)
        st.plotly_chart(
            figure, width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="volume_chart",
        )
    else:
        st.info("Volume data was not included. Add a **Volume** column to your CSV to explore trading activity.")

with data_tab:
    tone = "positive" if metrics["period_return"] >= 0 else "negative"
    daily_returns = data["Daily Return"].dropna()
    st.markdown("#### At a glance")
    summary = (
        f"Across the selected period, **{symbol}** delivered a **{tone} {metrics['period_return']:.2%}** return."
    )
    if not daily_returns.empty:
        strongest_day = data.loc[daily_returns.idxmax()]
        weakest_day = data.loc[daily_returns.idxmin()]
        summary += (
            f" There were **{int((daily_returns > 0).sum())} up sessions** and "
            f"**{int((daily_returns < 0).sum())} down sessions**. The strongest session was "
            f"**{strongest_day['Date']:%b %d, %Y}** ({strongest_day['Daily Return']:+.2%}); "
            f"the weakest was **{weakest_day['Date']:%b %d, %Y}** "
            f"({weakest_day['Daily Return']:+.2%})."
        )
        average_return = daily_returns.mean()
        st.caption(
            f"Average daily return: {average_return:+.3%} · "
            f"Peak-to-trough drawdown: {metrics['max_drawdown']:.2%}. "
            "Historical performance does not guarantee future results."
        )
    else:
        st.caption(
            f"Only one trading observation is available. Peak-to-trough drawdown: "
            f"{metrics['max_drawdown']:.2%}. Historical performance does not guarantee future results."
        )
    st.write(summary)
    rsi_value = data["RSI 14"].iloc[-1]
    if pd.notna(rsi_value):
        rsi_description = "overbought zone" if rsi_value >= 70 else "oversold zone" if rsi_value <= 30 else "neutral zone"
        st.metric("Latest RSI (14)", f"{rsi_value:.1f}", rsi_description)
    else:
        st.caption("RSI is shown after at least 15 price observations.")
    return_filter = st.selectbox(
        "Filter sessions",
        ("All sessions", "Up sessions", "Down sessions", "Flat sessions"),
        key="return_filter",
    )
    display_columns = ["Date", "Open", "High", "Low", "Close", "Volume", "Daily Return", "Cumulative Return", "Drawdown"]
    filtered_table = data
    if return_filter == "Up sessions":
        filtered_table = display_data.loc[display_data["Daily Return"] > 0]
    elif return_filter == "Down sessions":
        filtered_table = display_data.loc[display_data["Daily Return"] < 0]
    elif return_filter == "Flat sessions":
        filtered_table = display_data.loc[display_data["Daily Return"] == 0]
    else:
        filtered_table = display_data
    st.markdown("#### Cleaned history")
    st.dataframe(
        filtered_table[display_columns].sort_values("Date", ascending=False),
        width="stretch",
        hide_index=True,
        column_config={
            "Open": st.column_config.NumberColumn("Open (₹)", format="₹%.2f"),
            "High": st.column_config.NumberColumn("High (₹)", format="₹%.2f"),
            "Low": st.column_config.NumberColumn("Low (₹)", format="₹%.2f"),
            "Close": st.column_config.NumberColumn("Close (₹)", format="₹%.2f"),
            "Date": st.column_config.DateColumn("Date", format="MMM DD, YYYY"),
            "Daily Return": st.column_config.NumberColumn("Daily return", format="%.2%"),
            "Cumulative Return": st.column_config.NumberColumn("Cumulative return", format="%.2%"),
            "Drawdown": st.column_config.NumberColumn("Drawdown", format="%.2%"),
            "Volume": st.column_config.NumberColumn("Volume", format="%d"),
        },
    )
    csv_bytes = display_data[display_columns].to_csv(index=False).encode("utf-8")
    st.download_button("Download analyzed CSV (INR prices)", data=csv_bytes, file_name=f"{symbol.lower()}_analysis_inr.csv", mime="text/csv")

st.markdown(
    "<div style='color:#71819a; padding:22px 0 8px; font-size:.8rem'>Market Lens · "
    "For research and education only, not investment advice.</div>",
    unsafe_allow_html=True,
)
