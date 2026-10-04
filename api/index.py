"""FastAPI endpoints for the static Vercel Market Lens dashboard."""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import numpy as np
import pandas as pd
import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from analysis import (
    calculate_metrics,
    clean_stock_data,
    convert_price_values,
    enrich_stock_data,
    make_demo_data,
    monthly_returns,
)

app = FastAPI(title="Market Lens API", version="1.0.0")
_FX_TTL_SECONDS = 3600
_fx_lock = Lock()
_fx_cache: tuple[float, str, float] | None = None


class AnalysisRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=20_000)
    short_window: int = Field(default=20, ge=2, le=200)
    long_window: int = Field(default=50, ge=3, le=500)
    start_date: date | None = None
    end_date: date | None = None
    currency: Literal["USD", "INR"] = "USD"
    refresh_rate: bool = False


def get_usd_inr_rate(force_refresh: bool = False) -> tuple[float, str]:
    """Return the cached latest reference rate, refreshing at most hourly."""
    global _fx_cache

    with _fx_lock:
        if not force_refresh and _fx_cache and time.monotonic() - _fx_cache[2] < _FX_TTL_SECONDS:
            return _fx_cache[0], _fx_cache[1]

        try:
            response = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as error:
            raise HTTPException(status_code=502, detail=f"Could not retrieve the live USD/INR rate: {error}") from error
        except ValueError as error:
            raise HTTPException(status_code=502, detail="The exchange-rate service returned invalid JSON.") from error

        if not isinstance(payload, dict) or payload.get("result") != "success" or payload.get("base_code") != "USD":
            raise HTTPException(status_code=502, detail="The exchange-rate service did not return a valid USD quote.")
        rates = payload.get("rates")
        if not isinstance(rates, dict):
            raise HTTPException(status_code=502, detail="The exchange-rate response did not include currency rates.")
        try:
            rate = float(rates["INR"])
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=502, detail="The exchange-rate response did not include a valid INR rate.") from error
        if not np.isfinite(rate) or rate <= 0:
            raise HTTPException(status_code=502, detail="The exchange-rate service returned an invalid USD/INR rate.")

        updated_at = payload.get("time_last_update_utc")
        if not isinstance(updated_at, str) or not updated_at.strip():
            raise HTTPException(status_code=502, detail="The exchange-rate response did not include its update time.")
        _fx_cache = (rate, updated_at, time.monotonic())
        return rate, updated_at


def _json_records(data: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to JSON-safe records with ISO dates and null NaNs."""
    return json.loads(data.to_json(orient="records", date_format="iso"))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "market-lens"}


@app.get("/api/demo")
def demo() -> dict[str, list[dict[str, Any]]]:
    return {"rows": _json_records(make_demo_data())}


@app.post("/api/analyze")
def analyze(request: AnalysisRequest) -> dict[str, Any]:
    if request.short_window >= request.long_window:
        raise HTTPException(status_code=422, detail="Short moving-average window must be less than the long window.")

    try:
        clean = clean_stock_data(pd.DataFrame(request.rows))
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if request.start_date:
        clean = clean.loc[clean["Date"].dt.date >= request.start_date]
    if request.end_date:
        clean = clean.loc[clean["Date"].dt.date <= request.end_date]
    clean = clean.reset_index(drop=True)
    if clean.empty:
        raise HTTPException(status_code=422, detail="No valid trading observations fall within the selected dates.")

    try:
        analyzed = enrich_stock_data(clean, (request.short_window, request.long_window))
        metrics = calculate_metrics(analyzed)
        if request.currency == "USD":
            rate, rate_updated_at = get_usd_inr_rate(request.refresh_rate)
        else:
            rate, rate_updated_at = 1.0, "Not applicable: prices supplied in INR"
        display_data = convert_price_values(analyzed, rate)
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    metrics["latest_close"] *= rate
    month_table = monthly_returns(clean)
    month_rows = json.loads(
        month_table.rename_axis("year").reset_index().to_json(orient="records")
    ) if not month_table.empty else []
    return {
        "rows": _json_records(display_data),
        "metrics": metrics,
        "monthly_returns": month_rows,
        "currency": "INR",
        "source_currency": request.currency,
        "usd_inr_rate": rate,
        "rate_updated_at": rate_updated_at,
        "source_rows": len(request.rows),
        "clean_rows": len(clean),
    }


PUBLIC_DIRECTORY = Path(__file__).resolve().parents[1] / "public"
if os.environ.get("VERCEL") != "1":
    app.mount("/", StaticFiles(directory=PUBLIC_DIRECTORY, html=True), name="frontend")
