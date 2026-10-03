"""Data cleaning and analysis helpers for the stock dashboard."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def make_demo_data(start_date: str = "2021-01-01") -> pd.DataFrame:
    """Create deterministic synthetic daily OHLCV history through today."""
    dates = pd.bdate_range(start=start_date, end=pd.Timestamp.today().normalize())
    if dates.empty:
        raise ValueError("The demo start date must not be in the future.")

    rng = np.random.default_rng(17)
    daily_returns = rng.normal(loc=0.00035, scale=0.015, size=len(dates))
    close = 120 * np.cumprod(1 + daily_returns)
    open_price = close * (1 + rng.normal(loc=0.0, scale=0.004, size=len(dates)))
    high = np.maximum(open_price, close) * (1 + rng.uniform(0.001, 0.018, len(dates)))
    low = np.minimum(open_price, close) * (1 - rng.uniform(0.001, 0.018, len(dates)))
    volume = rng.lognormal(mean=15.2, sigma=0.35, size=len(dates)).astype(np.int64)
    return pd.DataFrame(
        {"Date": dates, "Open": open_price, "High": high, "Low": low, "Close": close, "Volume": volume}
    )


def clean_stock_data(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize stock-history columns and return clean, date-sorted observations."""
    if raw.empty:
        raise ValueError("The uploaded file contains no rows.")

    aliases = {
        "date": ("date", "datetime", "timestamp"),
        "open": ("open",),
        "high": ("high",),
        "low": ("low",),
        "close": ("close", "adj close", "adjusted close", "price"),
        "volume": ("volume", "vol"),
    }
    source_columns = {
        str(column).strip().lower().replace("_", " "): column
        for column in raw.columns
    }
    selected: dict[str, str] = {}
    for standard_name, accepted_names in aliases.items():
        for accepted_name in accepted_names:
            source_name = source_columns.get(accepted_name)
            if source_name is not None:
                selected[standard_name] = source_name
                break

    missing = {"date", "close"} - selected.keys()
    if missing:
        missing_names = ", ".join(sorted(name.title() for name in missing))
        raise ValueError(f"Required column(s) not found: {missing_names}.")

    data = pd.DataFrame(index=raw.index)
    for standard_name, source_name in selected.items():
        data[standard_name.title()] = raw[source_name]

    data["Date"] = pd.to_datetime(data["Date"], errors="coerce", utc=True).dt.tz_convert(None)
    for column in ("Open", "High", "Low", "Close", "Volume"):
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    for column in ("Open", "High", "Low", "Close", "Volume"):
        if column in data:
            data[column] = data[column].where(np.isfinite(data[column]))

    data = data.dropna(subset=["Date", "Close"])
    data = data.loc[data["Close"] > 0].copy()
    if data.empty:
        raise ValueError("No valid rows remain after parsing dates and positive closing prices.")

    for column in ("Open", "High", "Low"):
        if column not in data:
            data[column] = data["Close"]
        else:
            data[column] = data[column].where(data[column] > 0, data["Close"])
    if "Volume" not in data:
        data["Volume"] = np.nan
    else:
        data["Volume"] = data["Volume"].where(data["Volume"] >= 0)

    data = (
        data.sort_values("Date", kind="stable")
        .drop_duplicates(subset="Date", keep="last")
        .reset_index(drop=True)
    )
    return data[["Date", "Open", "High", "Low", "Close", "Volume"]]


def enrich_stock_data(data: pd.DataFrame, moving_averages: tuple[int, ...] = (20, 50)) -> pd.DataFrame:
    """Add daily returns, cumulative performance, moving averages, volatility, and drawdown."""
    enriched = data.copy()
    daily_returns = enriched["Close"].pct_change(fill_method=None)
    enriched["Daily Return"] = daily_returns
    enriched["Cumulative Return"] = (1 + daily_returns.fillna(0)).cumprod() - 1
    for window in moving_averages:
        enriched[f"MA {window}"] = enriched["Close"].rolling(window=window, min_periods=1).mean()
    enriched["Rolling Volatility"] = (
        daily_returns.rolling(window=20, min_periods=5).std()
        * np.sqrt(TRADING_DAYS_PER_YEAR)
    )
    enriched["Drawdown"] = enriched["Close"] / enriched["Close"].cummax() - 1
    price_changes = enriched["Close"].diff()
    average_gains = price_changes.clip(lower=0).rolling(window=14, min_periods=14).mean()
    average_losses = -price_changes.clip(upper=0).rolling(window=14, min_periods=14).mean()
    relative_strength = average_gains / average_losses.replace(0, np.nan)
    enriched["RSI 14"] = 100 - (100 / (1 + relative_strength))
    enriched.loc[average_losses.eq(0) & average_gains.gt(0), "RSI 14"] = 100.0
    enriched.loc[average_losses.eq(0) & average_gains.eq(0), "RSI 14"] = 50.0
    return enriched


def convert_price_values(data: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    """Scale price-valued columns without changing returns, indicators, or volume."""
    if not np.isfinite(multiplier) or multiplier <= 0:
        raise ValueError("The currency conversion multiplier must be a finite positive number.")

    converted = data.copy()
    price_columns = [
        column
        for column in converted.columns
        if column in {"Open", "High", "Low", "Close"} or column.startswith("MA ")
    ]
    if price_columns:
        for column in price_columns:
            converted[column] = converted[column].astype(float) * multiplier
        if not np.isfinite(converted[price_columns].to_numpy(dtype=float)).all():
            raise ValueError("Currency conversion produced a non-finite price.")
    return converted


def calculate_metrics(data: pd.DataFrame) -> dict[str, float]:
    """Calculate key performance statistics over the supplied date range."""
    if data.empty:
        raise ValueError("Cannot calculate metrics for an empty date range.")

    close = data["Close"]
    returns = close.pct_change(fill_method=None).dropna()
    volatility = returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR) if len(returns) > 1 else 0.0
    period_return = close.iloc[-1] / close.iloc[0] - 1 if len(close) > 1 else 0.0
    return {
        "latest_close": float(close.iloc[-1]),
        "period_return": float(period_return),
        "annualized_volatility": float(volatility),
        "max_drawdown": float((close / close.cummax() - 1).min()),
        "average_volume": float(data["Volume"].mean()) if data["Volume"].notna().any() else 0.0,
        "observations": float(len(data)),
    }


def monthly_returns(data: pd.DataFrame) -> pd.DataFrame:
    """Return a year-by-month table of close-to-close monthly returns."""
    if data.empty:
        return pd.DataFrame()

    monthly_close = (
        data.assign(Month=data["Date"].dt.to_period("M"))
        .groupby("Month", sort=True)["Close"]
        .last()
    )
    returns = monthly_close.pct_change(fill_method=None).dropna()
    if returns.empty:
        return pd.DataFrame()

    table = returns.rename("Return").to_frame()
    table["Year"] = table.index.year
    table["Month Number"] = table.index.month
    return table.pivot(index="Year", columns="Month Number", values="Return").reindex(columns=range(1, 13))
