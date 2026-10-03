"use strict";

const $ = (id) => document.getElementById(id);
const COLORS = {
  bg: "#07111f", panel: "#0e1a2a", grid: "#1c2b3d", text: "#dbe5ef",
  muted: "#8192a8", green: "#58d6a4", red: "#ff7588", blue: "#77aaff",
  purple: "#be96ff", amber: "#ffc36b",
};
const PAGE_SIZE = 20;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

let rawRows = [];
let analyzedRows = [];
let monthlyReturns = [];
let pageNumber = 0;
let activePeriod = "ALL";
let customPeriod = false;
let requestNumber = 0;
let rateCurrency = "USD";

function formatNumber(value, digits = 2) {
  return Number.isFinite(Number(value))
    ? new Intl.NumberFormat("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Number(value))
    : "—";
}

function formatCompact(value) {
  if (!Number.isFinite(Number(value)) || !value) return "—";
  return new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 2 }).format(Number(value));
}

function formatPercent(value, digits = 2) {
  if (!Number.isFinite(Number(value))) return "—";
  return `${Number(value) > 0 ? "+" : ""}${(Number(value) * 100).toFixed(digits)}%`;
}

function formatDate(value, options = { day: "2-digit", month: "short", year: "numeric" }) {
  return new Intl.DateTimeFormat("en-IN", options).format(new Date(`${String(value).slice(0, 10)}T12:00:00Z`));
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function setError(message) {
  const error = $("error");
  error.textContent = message;
  error.hidden = !message;
}

function setNotice(message) {
  const notice = $("notice");
  notice.textContent = message;
  notice.hidden = !message;
}

function setLoading(loading) {
  document.body.classList.toggle("loading", loading);
  $("analyze-button").disabled = loading;
  $("analyze-button").innerHTML = loading ? "<span>◌</span> Analyzing…" : "<span>↗</span> Analyze data";
}

function isoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function selectedDates() {
  if (customPeriod) {
    return { start_date: $("start-date").value || null, end_date: $("end-date").value || null };
  }
  const last = new Date(`${rawRows[rawRows.length - 1].Date}T00:00:00`);
  const first = new Date(`${rawRows[0].Date}T00:00:00`);
  if (activePeriod !== "ALL") {
    const months = { "1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36 }[activePeriod];
    const start = new Date(last);
    start.setMonth(start.getMonth() - months);
    return { start_date: isoDate(start < first ? first : start), end_date: isoDate(last) };
  }
  return { start_date: isoDate(first), end_date: isoDate(last) };
}

function plotLayout(title, height = 340, extra = {}) {
  return {
    title: { text: title, x: 0.015, font: { family: "Space Grotesk, sans-serif", size: 14, color: COLORS.text } },
    template: "plotly_dark",
    paper_bgcolor: COLORS.panel,
    plot_bgcolor: COLORS.panel,
    font: { family: "DM Sans, sans-serif", color: COLORS.muted, size: 10 },
    hovermode: "x unified",
    height,
    margin: { l: 54, r: 16, t: 47, b: 34 },
    legend: { orientation: "h", y: 1.13, x: 1, xanchor: "right", font: { size: 9 } },
    xaxis: { gridcolor: COLORS.grid, linecolor: COLORS.grid, rangeslider: { visible: false } },
    yaxis: { gridcolor: COLORS.grid, linecolor: COLORS.grid, zerolinecolor: COLORS.grid },
    ...extra,
  };
}

function plotConfig() {
  return { responsive: true, displaylogo: false, scrollZoom: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] };
}

async function loadDemoRows() {
  const response = await fetch("/api/demo");
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "Could not load demo history.");
  rawRows = payload.rows;
  if (!rawRows.length) throw new Error("The demo history did not contain any observations.");
  $("symbol-input").value = "DEMO";
  $("file-name").textContent = "Synthetic sample · Jan 2021 to today";
  $("source-badge").textContent = "SYNTHETIC SAMPLE";
  $("currency-row").hidden = true;
  $("currency-select").value = "INR";
  rateCurrency = "USD";
  $("symbol-input").readOnly = true;
  customPeriod = false;
  activePeriod = "ALL";
  updatePeriodButtons();
  await analyze();
}

async function analyze(forceRate = false) {
  if (!rawRows.length) {
    setError("Load a demo series or choose a valid CSV before analyzing.");
    return;
  }
  const shortWindow = Number($("short-window").value);
  const longWindow = Number($("long-window").value);
  if (shortWindow >= longWindow) {
    setError("The short moving average must be less than the long moving average.");
    return;
  }

  const currentRequest = ++requestNumber;
  setLoading(true);
  setError("");
  try {
    const dates = selectedDates();
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rows: rawRows,
        short_window: shortWindow,
        long_window: longWindow,
        currency: rateCurrency,
        refresh_rate: forceRate,
        ...dates,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Analysis request failed.");
    if (currentRequest !== requestNumber) return;
    analyzedRows = result.rows;
    monthlyReturns = result.monthly_returns;
    pageNumber = 0;
    renderDashboard(result);
  } catch (error) {
    if (currentRequest === requestNumber) setError(error instanceof Error ? error.message : "Unexpected analysis error.");
  } finally {
    if (currentRequest === requestNumber) setLoading(false);
  }
}

function updatePeriodButtons() {
  document.querySelectorAll(".period-button").forEach((button) => {
    button.classList.toggle("active", !customPeriod && button.dataset.period === activePeriod);
  });
  $("heading-period").textContent = `· ${customPeriod ? "CUSTOM" : activePeriod === "ALL" ? "ALL TIME" : activePeriod}`;
}

function renderDashboard(result) {
  const symbol = ($("symbol-input").value.trim().toUpperCase() || "STOCK");
  $("crumb-symbol").textContent = symbol;
  $("company-name").textContent = symbol;
  $("ticker-icon").textContent = symbol.slice(0, 1);
  $("heading-period").textContent = `· ${customPeriod ? "CUSTOM" : activePeriod === "ALL" ? "ALL TIME" : activePeriod}`;
  $("header-date").textContent = formatDate(new Date(), { day: "2-digit", month: "short", year: "numeric" });

  const metrics = result.metrics;
  const last = analyzedRows[analyzedRows.length - 1];
  const latestMove = Number(last["Daily Return"]);
  $("metric-close").textContent = `₹${formatNumber(metrics.latest_close)}`;
  $("metric-day-change").textContent = `Latest session ${formatPercent(latestMove)}`;
  $("metric-day-change").className = `kpi-note ${latestMove >= 0 ? "positive" : "negative"}`;
  $("metric-return").textContent = formatPercent(metrics.period_return);
  $("metric-return").className = `kpi-value ${metrics.period_return >= 0 ? "positive" : "negative"}`;
  $("metric-volatility").textContent = `${(metrics.annualized_volatility * 100).toFixed(2)}%`;
  $("metric-drawdown").textContent = formatPercent(metrics.max_drawdown);
  $("metric-drawdown").className = `kpi-value ${metrics.max_drawdown < 0 ? "negative" : ""}`;
  $("metric-volume").textContent = metrics.average_volume ? formatCompact(metrics.average_volume) : "—";

  const firstDate = analyzedRows[0].Date;
  const lastDate = last.Date;
  $("range-label").textContent = `${formatDate(firstDate)} — ${formatDate(lastDate)} · ${metrics.observations} sessions`;
  if (result.source_currency === "USD") {
    $("rate-label").textContent = `$1 = ₹${formatNumber(result.usd_inr_rate, 4)} · updated ${result.rate_updated_at}`;
    setNotice("USD prices are converted using the latest published USD/INR reference rate, applied uniformly to this historical series.");
  } else {
    $("rate-label").textContent = "Uploaded prices treated as INR";
    setNotice("");
  }

  const rsi = last["RSI 14"];
  if (rsi === null || !Number.isFinite(Number(rsi))) {
    $("rsi-value").textContent = "—";
    $("rsi-status").textContent = "Awaiting 15 sessions";
    $("rsi-meter").style.width = "0%";
  } else {
    const value = Number(rsi);
    $("rsi-value").textContent = value.toFixed(1);
    $("rsi-status").textContent = value >= 70 ? "Overbought zone" : value <= 30 ? "Oversold zone" : "Neutral zone";
    $("rsi-meter").style.width = `${Math.max(0, Math.min(100, value))}%`;
    $("rsi-meter").style.background = value >= 70 ? COLORS.red : value <= 30 ? COLORS.blue : COLORS.green;
  }
  const maColumn = `MA ${$("long-window").value}`;
  const longAverage = Number(last[maColumn]);
  const latestPrice = Number(last.Close);
  const directionUp = latestPrice >= longAverage;
  $("direction-value").textContent = directionUp ? "Above trend" : "Below trend";
  $("direction-value").className = directionUp ? "positive" : "negative";
  $("direction-status").textContent = `${$("long-window").value}-session average`;
  $("direction-copy").textContent = `Latest close is ${formatPercent(latestPrice / longAverage - 1)} versus the long moving average.`;
  $("quality-value").textContent = `${result.clean_rows.toLocaleString("en-IN")}`;
  $("quality-copy").textContent = `${Math.max(0, result.source_rows - result.clean_rows).toLocaleString("en-IN")} invalid or out-of-range rows excluded.`;

  renderPriceChart();
  renderReturns();
  renderActivity();
  renderInsights();
  renderTable();
}

function renderPriceChart() {
  const dates = analyzedRows.map((row) => row.Date);
  const traces = [];
  if ($("chart-style").value === "candle") {
    traces.push({
      type: "candlestick", x: dates, open: analyzedRows.map((row) => row.Open),
      high: analyzedRows.map((row) => row.High), low: analyzedRows.map((row) => row.Low),
      close: analyzedRows.map((row) => row.Close), name: "OHLC",
      increasing: { line: { color: COLORS.green } }, decreasing: { line: { color: COLORS.red } },
    });
  } else {
    traces.push({
      type: "scatter", mode: "lines", x: dates, y: analyzedRows.map((row) => row.Close),
      name: "Close", line: { color: COLORS.green, width: 2 },
      hovertemplate: "%{x|%b %d, %Y}<br>Close: ₹%{y:,.2f}<extra></extra>",
    });
  }
  if ($("show-short-ma").checked) {
    traces.push({
      type: "scatter", mode: "lines", x: dates, y: analyzedRows.map((row) => row[`MA ${$("short-window").value}`]),
      name: `${$("short-window").value}-session MA`, line: { color: COLORS.blue, width: 1.3 },
    });
  }
  if ($("show-long-ma").checked) {
    traces.push({
      type: "scatter", mode: "lines", x: dates, y: analyzedRows.map((row) => row[`MA ${$("long-window").value}`]),
      name: `${$("long-window").value}-session MA`, line: { color: COLORS.purple, width: 1.3 },
    });
  }
  const height = window.innerWidth < 760 ? 335 : 390;
  if ($("show-rsi").checked) {
    traces.push({
      type: "scatter", mode: "lines", x: dates, y: analyzedRows.map((row) => row["RSI 14"]),
      name: "RSI (14)", xaxis: "x2", yaxis: "y2", line: { color: COLORS.amber, width: 1.5 },
    });
    Plotly.newPlot("price-chart", traces, {
      ...plotLayout(`${$("symbol-input").value.toUpperCase()} · PRICE & MOMENTUM`, height + 80, {
        grid: { rows: 2, columns: 1, pattern: "independent", roworder: "top to bottom" },
        xaxis: { ...plotLayout("").xaxis, domain: [0, 1], anchor: "y", rangeslider: { visible: $("chart-style").value === "candle", thickness: 0.08 } },
        yaxis: { ...plotLayout("").yaxis, domain: [0.29, 1], title: "Price (₹)", tickprefix: "₹" },
        xaxis2: { ...plotLayout("").xaxis, domain: [0, 1], anchor: "y2", matches: "x", rangeslider: { visible: false } },
        yaxis2: { ...plotLayout("").yaxis, domain: [0, 0.2], title: "RSI", range: [0, 100], anchor: "x2" },
        shapes: [
          { type: "line", xref: "paper", x0: 0, x1: 1, yref: "y2", y0: 70, y1: 70, line: { color: COLORS.red, dash: "dot" } },
          { type: "line", xref: "paper", x0: 0, x1: 1, yref: "y2", y0: 30, y1: 30, line: { color: COLORS.green, dash: "dot" } },
        ],
      }),
    }, plotConfig());
  } else {
    Plotly.newPlot("price-chart", traces, {
      ...plotLayout(`${$("symbol-input").value.toUpperCase()} · PRICE & TREND`, height, {
        yaxis: { ...plotLayout("").yaxis, title: "Price (₹)", tickprefix: "₹" },
        xaxis: { ...plotLayout("").xaxis, rangeslider: { visible: $("chart-style").value === "candle", thickness: 0.08 } },
      }),
    }, plotConfig());
  }
}

function renderReturns() {
  const dates = analyzedRows.map((row) => row.Date);
  Plotly.newPlot("cumulative-chart", [{
    type: "scatter", mode: "lines", x: dates,
    y: analyzedRows.map((row) => Number(row["Cumulative Return"]) * 100),
    line: { color: COLORS.green, width: 2 }, fill: "tozeroy", name: "Cumulative return",
    hovertemplate: "%{x|%b %d, %Y}<br>Return: %{y:.2f}%<extra></extra>",
  }], plotLayout("CUMULATIVE RETURN", window.innerWidth < 760 ? 280 : 300, {
    yaxis: { ...plotLayout("").yaxis, title: "Return (%)", ticksuffix: "%" },
  }), plotConfig());

  Plotly.newPlot("volatility-chart", [{
    type: "scatter", mode: "lines", x: dates,
    y: analyzedRows.map((row) => row["Rolling Volatility"] === null ? null : Number(row["Rolling Volatility"]) * 100),
    line: { color: COLORS.amber, width: 1.7 }, name: "Annualized volatility",
  }], plotLayout("20-SESSION ANNUALIZED VOLATILITY", window.innerWidth < 760 ? 280 : 300, {
    yaxis: { ...plotLayout("").yaxis, title: "Volatility (%)", ticksuffix: "%" },
  }), plotConfig());

  const returns = analyzedRows.map((row) => Number(row["Daily Return"]) * 100).filter(Number.isFinite);
  Plotly.newPlot("histogram-chart", [{
    type: "histogram", x: returns, nbinsx: Number($("histogram-bins").value),
    marker: { color: COLORS.blue, opacity: 0.82 }, name: "Sessions",
    hovertemplate: "Daily return: %{x:.2f}%<br>Sessions: %{y}<extra></extra>",
  }], plotLayout("DAILY RETURN DISTRIBUTION", 290, {
    xaxis: { ...plotLayout("").xaxis, title: "Daily return (%)", ticksuffix: "%" },
    yaxis: { ...plotLayout("").yaxis, title: "Sessions" },
  }), plotConfig());

  renderHeatmap();
}

function renderHeatmap() {
  if (!monthlyReturns.length) {
    $("heatmap-chart").innerHTML = '<div class="empty-state">Monthly returns need at least two months of price history.</div>';
    return;
  }
  const years = monthlyReturns.map((row) => row.year);
  const z = monthlyReturns.map((row) => MONTHS.map((_, index) => {
    const value = row[String(index + 1)];
    return value === null || value === undefined ? null : Number(value) * 100;
  }));
  Plotly.newPlot("heatmap-chart", [{
    type: "heatmap", x: MONTHS, y: years, z,
    colorscale: [[0, "#bd5363"], [0.5, "#17283a"], [1, "#39aa7d"]],
    zmid: 0, colorbar: { title: "%", ticksuffix: "%" },
    hovertemplate: "%{y} · %{x}<br>Return: %{z:.2f}%<extra></extra>",
  }], plotLayout("MONTHLY CLOSE-TO-CLOSE RETURN", Math.max(250, years.length * 44 + 120), {
    xaxis: { ...plotLayout("").xaxis, side: "top" },
    yaxis: { ...plotLayout("").yaxis, autorange: "reversed" },
    margin: { l: 58, r: 55, t: 45, b: 20 },
  }), plotConfig());
}

function renderActivity() {
  const hasVolume = analyzedRows.some((row) => Number.isFinite(Number(row.Volume)));
  $("volume-chart").hidden = !hasVolume;
  $("volume-empty").hidden = hasVolume;
  if (!hasVolume) return;
  const dates = analyzedRows.map((row) => row.Date);
  const volumeColors = analyzedRows.map((row) => Number(row["Daily Return"]) >= 0 ? COLORS.green : COLORS.red);
  const traces = [
    {
      type: "bar", x: dates, y: analyzedRows.map((row) => row.Volume), marker: { color: volumeColors, opacity: 0.6 },
      name: "Volume", yaxis: "y",
    },
    {
      type: "scatter", mode: "lines", x: dates, y: analyzedRows.map((row) => row.Close),
      name: "Close", line: { color: COLORS.green, width: 2 }, yaxis: "y2",
      hovertemplate: "%{x|%b %d, %Y}<br>Close: ₹%{y:,.2f}<extra></extra>",
    },
  ];
  Plotly.newPlot("volume-chart", traces, {
    ...plotLayout("PRICE & VOLUME", window.innerWidth < 760 ? 335 : 390, {
      yaxis: { ...plotLayout("").yaxis, title: "Volume" },
      yaxis2: { ...plotLayout("").yaxis, title: "Price (₹)", tickprefix: "₹", overlaying: "y", side: "right" },
      xaxis: { ...plotLayout("").xaxis, rangeslider: { visible: true, thickness: 0.08 } },
    }),
  }, plotConfig());
}

function renderInsights() {
  const returns = analyzedRows.map((row) => Number(row["Daily Return"])).filter(Number.isFinite);
  const positive = returns.filter((value) => value > 0).length;
  const negative = returns.filter((value) => value < 0).length;
  const best = analyzedRows.reduce((current, row) => Number(row["Daily Return"]) > Number(current["Daily Return"]) ? row : current);
  const worst = analyzedRows.reduce((current, row) => Number(row["Daily Return"]) < Number(current["Daily Return"]) ? row : current);
  $("up-days").textContent = positive.toLocaleString("en-IN");
  $("down-days").textContent = negative.toLocaleString("en-IN");
  $("best-day").textContent = `${formatDate(best.Date, { day: "2-digit", month: "short" })} · ${formatPercent(best["Daily Return"])}`;
  $("worst-day").textContent = `${formatDate(worst.Date, { day: "2-digit", month: "short" })} · ${formatPercent(worst["Daily Return"])}`;
  $("insight-summary").textContent = `${$("symbol-input").value.toUpperCase()} returned ${formatPercent(analyzedRows[analyzedRows.length - 1]["Cumulative Return"])} across ${analyzedRows.length.toLocaleString("en-IN")} selected sessions, with ${positive.toLocaleString("en-IN")} positive and ${negative.toLocaleString("en-IN")} negative daily moves. Peak-to-trough drawdown was ${formatPercent(analyzedRows.reduce((minimum, row) => Math.min(minimum, Number(row.Drawdown)), 0))}. Historical performance does not guarantee future results.`;
}

function filteredRows() {
  const filter = $("row-filter").value;
  const query = $("table-search").value.trim().toLowerCase();
  return analyzedRows.filter((row) => {
    const change = Number(row["Daily Return"]);
    const directionMatches = filter === "all"
      || (filter === "up" && change > 0)
      || (filter === "down" && change < 0)
      || (filter === "flat" && change === 0);
    const searchMatches = !query || [
      row.Date, row.Open, row.High, row.Low, row.Close, row.Volume, row["Daily Return"],
    ].some((value) => String(value ?? "").toLowerCase().includes(query));
    return directionMatches && searchMatches;
  }).slice().reverse();
}

function renderTable() {
  const rows = filteredRows();
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  pageNumber = Math.min(pageNumber, pageCount - 1);
  const visible = rows.slice(pageNumber * PAGE_SIZE, (pageNumber + 1) * PAGE_SIZE);
  $("data-rows").innerHTML = visible.length ? visible.map((row) => {
    const change = Number(row["Daily Return"]);
    return `<tr><td>${escapeHtml(formatDate(row.Date))}</td>
      <td>₹${formatNumber(row.Open)}</td><td>₹${formatNumber(row.High)}</td>
      <td>₹${formatNumber(row.Low)}</td><td>₹${formatNumber(row.Close)}</td>
      <td>${formatCompact(row.Volume)}</td>
      <td class="${change >= 0 ? "positive" : "negative"}">${formatPercent(change)}</td>
      <td class="${Number(row.Drawdown) < 0 ? "negative" : ""}">${formatPercent(row.Drawdown)}</td></tr>`;
  }).join("") : '<tr><td class="empty-row" colspan="8">No sessions match this filter.</td></tr>';
  $("table-count").textContent = `${rows.length.toLocaleString("en-IN")} matching sessions`;
  $("page-label").textContent = `${pageNumber + 1} / ${pageCount}`;
  $("prev-page").disabled = pageNumber === 0;
  $("next-page").disabled = pageNumber >= pageCount - 1;
}

function updateSliderOutput(id, outputId) {
  $(outputId).textContent = `${$(id).value} sessions`;
}

function bindEvents() {
  $("source-select").addEventListener("change", async (event) => {
    const isUpload = event.target.value === "upload";
    $("upload-button").hidden = !isUpload;
    $("currency-row").hidden = !isUpload;
    $("symbol-input").readOnly = !isUpload;
    if (isUpload) {
      $("symbol-input").value = "MY STOCK";
      $("file-name").textContent = "Choose a CSV with Date and Close columns.";
    } else {
      await loadDemoRows();
    }
  });
  $("upload-button").addEventListener("click", () => $("csv-file").click());
  $("csv-file").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    $("file-name").textContent = file.name;
    if (file.size > 2_000_000) {
      setError("This dashboard accepts CSV files up to 2 MB. Please reduce the file size and retry.");
      return;
    }
    $("analyze-button").disabled = true;
    Papa.parse(file, {
      header: true, dynamicTyping: true, skipEmptyLines: "greedy",
      complete: async ({ data, errors }) => {
        if (data.length > 20_000) {
          setError("This dashboard accepts up to 20,000 CSV rows. Filter the file and try again.");
          $("analyze-button").disabled = false;
          return;
        }
        if (errors.length) setNotice(`CSV parser noted ${errors.length} row warning(s); invalid rows will be cleaned.`);
        rawRows = data;
        rateCurrency = $("currency-select").value;
        $("source-badge").textContent = "UPLOADED HISTORY";
        await analyze();
      },
      error: (error) => {
        setError(`Could not read the selected CSV: ${error.message}`);
        $("analyze-button").disabled = false;
      },
    });
  });
  $("analyze-button").addEventListener("click", () => analyze());
  $("symbol-input").addEventListener("change", () => { if (rawRows.length) analyze(); });
  $("currency-select").addEventListener("change", () => {
    rateCurrency = $("currency-select").value;
    if (rawRows.length) analyze();
  });
  $("short-window").addEventListener("input", () => {
    updateSliderOutput("short-window", "short-output");
    if (Number($("short-window").value) >= Number($("long-window").value)) {
      $("long-window").value = String(Number($("short-window").value) + 1);
      updateSliderOutput("long-window", "long-output");
    }
    analyze();
  });
  $("long-window").addEventListener("input", () => {
    updateSliderOutput("long-window", "long-output");
    if (Number($("long-window").value) <= Number($("short-window").value)) {
      $("short-window").value = String(Number($("long-window").value) - 1);
      updateSliderOutput("short-window", "short-output");
    }
    analyze();
  });
  ["show-short-ma", "show-long-ma", "show-rsi", "chart-style"].forEach((id) => {
    $(id).addEventListener("change", renderPriceChart);
  });
  $("histogram-bins").addEventListener("input", () => {
    $("bins-output").textContent = $("histogram-bins").value;
    renderReturns();
  });
  document.querySelectorAll(".period-button").forEach((button) => {
    button.addEventListener("click", () => {
      customPeriod = false;
      activePeriod = button.dataset.period;
      $("custom-dates").hidden = true;
      updatePeriodButtons();
      analyze();
    });
  });
  $("custom-toggle").addEventListener("click", () => {
    customPeriod = true;
    $("custom-dates").hidden = !$("custom-dates").hidden;
    const first = rawRows[0]?.Date?.slice(0, 10);
    const last = rawRows[rawRows.length - 1]?.Date?.slice(0, 10);
    $("start-date").min = first || "";
    $("start-date").max = last || "";
    $("end-date").min = first || "";
    $("end-date").max = last || "";
    if (!$("start-date").value) $("start-date").value = first || "";
    if (!$("end-date").value) $("end-date").value = last || "";
    updatePeriodButtons();
  });
  ["start-date", "end-date"].forEach((id) => $(id).addEventListener("change", () => analyze()));
  document.querySelectorAll(".view-tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".view-tab").forEach((item) => item.classList.toggle("active", item === button));
      document.querySelectorAll(".view-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `view-${button.dataset.view}`));
      window.dispatchEvent(new Event("resize"));
    });
  });
  $("row-filter").addEventListener("change", () => { pageNumber = 0; renderTable(); });
  $("table-search").addEventListener("input", () => { pageNumber = 0; renderTable(); });
  $("prev-page").addEventListener("click", () => { pageNumber -= 1; renderTable(); });
  $("next-page").addEventListener("click", () => { pageNumber += 1; renderTable(); });
  $("download-button").addEventListener("click", () => {
    if (!analyzedRows.length) return;
    const headers = Object.keys(analyzedRows[0]);
    const csv = [headers.join(","), ...analyzedRows.map((row) => headers.map((header) => {
      const value = row[header] ?? "";
      return `"${String(value).replace(/"/g, '""')}"`;
    }).join(","))].join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${$("symbol-input").value.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "_") || "stock"}_analysis_inr.csv`;
    link.click();
    URL.revokeObjectURL(url);
  });
  $("refresh-rate").addEventListener("click", () => rateCurrency === "USD" ? analyze(true) : setNotice("Your uploaded data is already in INR; no exchange rate is needed."));
  window.addEventListener("resize", () => {
    ["price-chart", "cumulative-chart", "volatility-chart", "histogram-chart", "heatmap-chart", "volume-chart"].forEach((id) => {
      const element = $(id);
      if (element && element.data) Plotly.Plots.resize(element);
    });
  });
}

async function main() {
  $("header-date").textContent = formatDate(new Date(), { day: "2-digit", month: "short", year: "numeric" });
  updateSliderOutput("short-window", "short-output");
  updateSliderOutput("long-window", "long-output");
  bindEvents();
  try {
    await loadDemoRows();
  } catch (error) {
    setError(error instanceof Error ? error.message : "Could not initialize the dashboard.");
  }
}

document.addEventListener("DOMContentLoaded", main);
