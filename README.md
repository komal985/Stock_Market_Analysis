# Market Lens

An interactive stock-history dashboard built with Streamlit, Pandas, NumPy, Matplotlib, and Plotly. Explore price trends, returns, volatility, drawdowns, monthly performance, and trading volume using a CSV of historical prices or the built-in reproducible synthetic demo series, which spans January 2021 through today by default. Plotly charts support hover details, zoom, pan, and trace toggling.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Run the Vercel-ready dashboard locally

The same Python analysis functions are also exposed through a FastAPI service with a static interactive frontend:

```powershell
python -m uvicorn api.index:app --reload
```

Open `http://127.0.0.1:8000`. The Vercel entrypoint is configured in `pyproject.toml`; deploy the repository root from the Vercel dashboard. `/api/health`, `/api/demo`, and `/api/analyze` are the JSON endpoints. The browser dashboard supports hover/zoom charts, line/candlestick views, range and custom-date filters, RSI and moving-average toggles, CSV upload, searchable/paginated history, and INR CSV export.

## CSV format

Upload a CSV containing `Date` and `Close` columns. Column names are case-insensitive. `Date` may also be named `Datetime` or `Timestamp`; `Close` may be `Adj Close`, `Adjusted Close`, or `Price` when a regular `Close` column is not present. When both regular and adjusted close columns are present, `Close` takes priority. `Open`, `High`, `Low`, and `Volume` are optional.

The dashboard parses dates and numeric values, removes invalid dates/prices, sorts observations chronologically, and keeps the last row for duplicate dates. Missing OHLC values use the close price; invalid or missing volume remains unavailable. The selected date range drives the displayed metrics and charts. The processed history can be exported from the **Data & insights** tab.

USD-denominated prices are displayed in INR using the latest published USD/INR reference rate from the public ExchangeRate-API endpoint. The rate is cached for one hour and can be refreshed from the sidebar. It is applied uniformly to the selected historical price series; returns and volume are unchanged. Uploaded data can be marked as already denominated in INR to skip conversion.

## Metrics

- Period return and daily return
- Annualized volatility (daily return standard deviation × √252)
- Maximum peak-to-trough drawdown
- Configurable simple moving averages
- 20-session rolling annualized volatility
- 14-session relative strength index (RSI)
- Close-to-close monthly returns and average daily trading volume

Historical data and metrics are for research and education only, not investment advice.
