(() => {
  const root = document.getElementById("investments-live-root");
  if (!root) return;

  const quotesUrl = root.dataset.quotesUrl;
  const historyUrl = root.dataset.historyUrl;
  const sectorsUrl = root.dataset.sectorsUrl;
  const usdSym = root.dataset.currencyUsd || "$";
  const ilsSym = root.dataset.currencyIls || "₪";
  const fxLabelTemplate = root.dataset.labelFx || "1 USD = {rate} ILS";
  let usdIls = Number(root.dataset.usdIls) || 0;

  const labels = {
    live: root.dataset.labelLive || "Live",
    pre: root.dataset.labelPre || "Pre-market",
    post: root.dataset.labelPost || "After hours",
    closed: root.dataset.labelClosed || "Market closed",
    updated: root.dataset.labelUpdated || "Last updated",
    holdingsValue: root.dataset.labelHoldingsValue || "Holdings value",
    sectorAllocation: root.dataset.labelSectorAllocation || "Sector allocation",
    sectorUnclassified: root.dataset.labelSectorUnclassified || "Unclassified symbols",
    sectorUnclassifiedHint: root.dataset.labelSectorUnclassifiedHint || "",
    sectorNoData: root.dataset.labelSectorNoData || "No sector data for this portfolio.",
  };

  const LIVE_MS = 15000;
  const CLOSED_MS = 120000;
  let timer = null;
  let inFlight = false;
  let historyChart = null;
  let sectorChart = null;
  let sectorCatalog = {};
  let sectorAssignments = {};
  let selectedPortfolio = "all";
  let selectedRange = "6mo";

  function formatNum(amount) {
    return (Number(amount) || 0).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function formatMoneyPair(amountUsd) {
    const n = Number(amountUsd) || 0;
    let html = `<span class="money-pair" data-usd="${n}">`;
    html += `<span class="money money-usd"><span class="money-sym">${usdSym}</span><span class="money-num">${formatNum(n)}</span></span>`;
    if (usdIls > 0) {
      html += `<span class="money-ils muted-note">≈ ${formatNum(n * usdIls)} ${ilsSym}</span>`;
    }
    html += `</span>`;
    return html;
  }

  function updateFxRateLabel() {
    const el = document.getElementById("fx-rate");
    if (!el) return;
    if (!(usdIls > 0)) {
      el.hidden = true;
      return;
    }
    el.hidden = false;
    el.textContent = fxLabelTemplate.replace("{rate}", usdIls.toFixed(4));
  }

  function setChgClass(el, changePct) {
    el.classList.remove("chg-up", "chg-down", "price-flash");
    if (changePct > 0) el.classList.add("chg-up");
    else if (changePct < 0) el.classList.add("chg-down");
  }

  function flash(el) {
    el.classList.remove("price-flash");
    void el.offsetWidth;
    el.classList.add("price-flash");
  }

  function formatUpdated(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return iso;
      const pad = (n) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    } catch {
      return iso;
    }
  }

  function sessionLabel(quotes) {
    const states = new Set(
      Object.values(quotes || {}).map((q) => String(q.market_state || "").toUpperCase())
    );
    if (states.has("REGULAR")) return labels.live;
    if (states.has("PRE") || states.has("PREPRE")) return labels.pre;
    if (states.has("POST") || states.has("POSTPOST")) return labels.post;
    return labels.closed;
  }

  function applyPortfolioFilter() {
    document.querySelectorAll(".portfolio-block, .portfolio-detail").forEach((row) => {
      const id = row.dataset.portfolioId || "";
      const show = selectedPortfolio === "all" || id === selectedPortfolio;
      row.classList.toggle("is-filtered-out", !show);
    });
    const title = document.getElementById("holdings-chart-title");
    const select = document.getElementById("portfolio-filter");
    if (title && select) {
      const opt = select.options[select.selectedIndex];
      title.textContent = opt ? opt.textContent : "";
    }
  }

  function applyQuotes(payload) {
    if (payload.usd_ils && Number(payload.usd_ils) > 0) {
      usdIls = Number(payload.usd_ils);
      updateFxRateLabel();
    }

    const quotes = payload.quotes || {};
    const rows = document.querySelectorAll(".holding-row[data-symbol]");
    const portfolioTotals = {};

    rows.forEach((row) => {
      const symbol = (row.dataset.symbol || "").toUpperCase();
      const qty = Number(row.dataset.quantity) || 0;
      const pf = row.dataset.portfolioId || "";
      const q = quotes[symbol];
      let price = Number(row.dataset.price) || 0;
      let changePct = null;

      if (q && q.price) {
        price = Number(q.price) || price;
        changePct = Number(q.change_pct) || 0;
        row.dataset.price = String(price);
      }

      const value = qty * price;
      if (pf) portfolioTotals[pf] = (portfolioTotals[pf] || 0) + value;
      if (changePct === null) return;

      const priceEl = row.querySelector(".holding-price");
      const chgEl = row.querySelector(".holding-chg");
      const nameEl = row.querySelector(".holding-name");

      if (priceEl) {
        const next = `${usdSym}${price.toFixed(2)}`;
        if (priceEl.textContent.trim() !== next) {
          priceEl.textContent = next;
          flash(priceEl);
        }
        setChgClass(priceEl, changePct);
      }
      if (chgEl) {
        chgEl.textContent = `${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}%`;
        setChgClass(chgEl, changePct);
      }
      if (nameEl && q.name && nameEl.textContent.trim() === symbol) {
        nameEl.textContent = q.name;
      }
    });

    let grand = 0;
    let filteredTotal = 0;
    Object.keys(portfolioTotals).forEach((pfId) => {
      const total = portfolioTotals[pfId];
      grand += total;
      if (selectedPortfolio === "all" || selectedPortfolio === pfId) {
        filteredTotal += total;
      }
      const cell = document.querySelector(`[data-portfolio-total="${CSS.escape(pfId)}"]`);
      if (cell) cell.innerHTML = formatMoneyPair(total);
    });

    const grandEl = document.getElementById("investments-grand-total");
    const tableTotal = document.getElementById("investments-table-total");
    if (grandEl) grandEl.innerHTML = formatMoneyPair(grand);
    if (tableTotal) tableTotal.innerHTML = formatMoneyPair(grand);

    const chartTotal = document.getElementById("holdings-chart-total");
    if (chartTotal) chartTotal.innerHTML = formatMoneyPair(filteredTotal || grand);

    const updatedEl = document.getElementById("investments-updated");
    if (updatedEl) {
      updatedEl.hidden = false;
      updatedEl.textContent = `${labels.updated}: ${formatUpdated(payload.updated_at)}`;
    }

    const statusEl = document.getElementById("live-status");
    if (statusEl) {
      statusEl.hidden = false;
      statusEl.textContent = sessionLabel(quotes);
      statusEl.classList.toggle("is-live", !!payload.live);
      statusEl.classList.toggle("is-closed", !payload.live);
    }

    updateSectorFromLivePrices();

    return !!payload.live;
  }

  async function tick() {
    if (inFlight || document.hidden) {
      schedule(CLOSED_MS);
      return;
    }
    inFlight = true;
    try {
      const resp = await fetch(quotesUrl, { headers: { Accept: "application/json" } });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const live = applyQuotes(data);
      schedule(live ? LIVE_MS : CLOSED_MS);
    } catch {
      schedule(CLOSED_MS);
    } finally {
      inFlight = false;
    }
  }

  function schedule(ms) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(tick, ms);
  }

  function renderHistoryChart(payload) {
    const canvas = document.getElementById("holdings-history-chart");
    if (!canvas || typeof Chart === "undefined") return;

    const chartLabels = payload.labels || [];
    const chartValues = payload.values || [];
    const totalEl = document.getElementById("holdings-chart-total");
    if (totalEl && payload.current_total != null) {
      totalEl.innerHTML = formatMoneyPair(payload.current_total);
    }

    const data = {
      labels: chartLabels,
      datasets: [
        {
          label: labels.holdingsValue,
          data: chartValues,
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.18)",
          fill: true,
          tension: 0.25,
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    };

    if (historyChart) {
      historyChart.data = data;
      historyChart.update("none");
      return;
    }

    historyChart = new Chart(canvas, {
      type: "line",
      data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(ctx) {
                const v = Number(ctx.parsed.y) || 0;
                let text = `${labels.holdingsValue}: ${usdSym}${formatNum(v)}`;
                if (usdIls > 0) text += ` (≈ ${formatNum(v * usdIls)} ${ilsSym})`;
                return text;
              },
            },
          },
        },
        scales: {
          x: {
            ticks: {
              maxTicksLimit: 8,
              color: "#64748b",
            },
            grid: { display: false },
          },
          y: {
            ticks: {
              color: "#64748b",
              callback(v) {
                return `${usdSym}${Number(v).toLocaleString()}`;
              },
            },
            grid: { color: "rgba(148, 163, 184, 0.25)" },
          },
        },
      },
    });
  }

  async function loadHistory() {
    if (!historyUrl) return;
    const loading = document.getElementById("holdings-chart-loading");
    if (loading) loading.hidden = false;
    try {
      const url = `${historyUrl}?portfolio=${encodeURIComponent(selectedPortfolio)}&range=${encodeURIComponent(selectedRange)}`;
      const resp = await fetch(url, { headers: { Accept: "application/json" } });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      renderHistoryChart(data);
    } catch {
      /* keep previous chart */
    } finally {
      if (loading) loading.hidden = true;
    }
  }

  function renderSectorLegend(sectors) {
    const legend = document.getElementById("sector-legend");
    if (!legend) return;
    legend.innerHTML = "";
    sectors.forEach((sector) => {
      const row = document.createElement("div");
      row.className = "sector-legend-row";
      row.dataset.sectorId = sector.id;
      row.innerHTML = `
        <span class="sector-swatch" style="background:${sector.color}"></span>
        <span class="sector-legend-label">${sector.label}</span>
        <span class="sector-legend-value">${usdSym}${formatNum(sector.value)}</span>
        <span class="sector-legend-pct">${sector.pct.toFixed(1)}%</span>
      `;
      legend.appendChild(row);
    });
  }

  function renderUnclassified(items) {
    const wrap = document.getElementById("sector-unclassified");
    const list = document.getElementById("sector-unclassified-list");
    if (!wrap || !list) return;
    list.innerHTML = "";
    if (!items || !items.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    items.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item.name && item.name !== item.symbol
        ? `${item.symbol} — ${item.name}`
        : item.symbol;
      list.appendChild(li);
    });
  }

  function sectorTotalsFromHoldings() {
    const totals = {};
    document.querySelectorAll(".holding-row[data-symbol]").forEach((row) => {
      const pf = row.dataset.portfolioId || "";
      if (selectedPortfolio !== "all" && pf !== selectedPortfolio) return;
      const symbol = (row.dataset.symbol || "").toUpperCase();
      const qty = Number(row.dataset.quantity) || 0;
      const price = Number(row.dataset.price) || 0;
      const sectorId = sectorAssignments[symbol] || "unknown";
      totals[sectorId] = (totals[sectorId] || 0) + qty * price;
    });
    return totals;
  }

  function applySectorValues(valuesById) {
    const entries = Object.keys(valuesById)
      .map((id) => {
        const base = sectorCatalog[id] || { id, label: id, color: "#94a3b8" };
        return {
          ...base,
          value: Number(valuesById[id]) || 0,
        };
      })
      .filter((sector) => sector.value > 0)
      .sort((a, b) => b.value - a.value);
    const total = entries.reduce((sum, sector) => sum + sector.value, 0) || 0;
    entries.forEach((sector) => {
      sector.pct = total > 0 ? (sector.value / total) * 100 : 0;
    });

    const emptyEl = document.getElementById("sector-empty");
    const canvas = document.getElementById("sector-allocation-chart");
    if (emptyEl) emptyEl.hidden = entries.length > 0;
    if (canvas) canvas.hidden = entries.length === 0;

    if (!entries.length) {
      if (sectorChart) {
        sectorChart.destroy();
        sectorChart = null;
      }
      renderSectorLegend([]);
      return;
    }

    const chartData = {
      labels: entries.map((sector) => sector.label),
      datasets: [
        {
          data: entries.map((sector) => sector.value),
          backgroundColor: entries.map((sector) => sector.color),
          borderWidth: 1,
          borderColor: "#fff",
        },
      ],
    };

    if (sectorChart) {
      sectorChart.data = chartData;
      sectorChart.update("none");
    } else if (typeof Chart !== "undefined" && canvas) {
      sectorChart = new Chart(canvas, {
        type: "pie",
        data: chartData,
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label(ctx) {
                  const v = Number(ctx.parsed) || 0;
                  const sum = ctx.dataset.data.reduce((a, b) => a + b, 0) || 1;
                  const pct = ((v / sum) * 100).toFixed(1);
                  let text = `${ctx.label}: ${usdSym}${formatNum(v)} (${pct}%)`;
                  if (usdIls > 0) text += ` ≈ ${formatNum(v * usdIls)} ${ilsSym}`;
                  return text;
                },
              },
            },
          },
        },
      });
    }
    renderSectorLegend(entries);
  }

  function updateSectorFromLivePrices() {
    if (!Object.keys(sectorCatalog).length) return;
    applySectorValues(sectorTotalsFromHoldings());
  }

  function renderSectorPayload(payload) {
    sectorCatalog = Object.fromEntries(
      (payload.catalog || payload.sectors || []).map((sector) => [sector.id, sector])
    );
    sectorAssignments = payload.assignments || {};
    renderUnclassified(payload.unclassified || []);
    updateSectorFromLivePrices();
  }

  async function loadSectors() {
    if (!sectorsUrl) return;
    try {
      const url = `${sectorsUrl}?portfolio=${encodeURIComponent(selectedPortfolio)}`;
      const resp = await fetch(url, { headers: { Accept: "application/json" } });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      renderSectorPayload(data);
    } catch {
      /* keep previous sector chart */
    }
  }

  const filter = document.getElementById("portfolio-filter");
  if (filter) {
    filter.addEventListener("change", () => {
      selectedPortfolio = filter.value || "all";
      applyPortfolioFilter();
      loadHistory();
      loadSectors();
    });
  }

  document.querySelectorAll("#history-range-tabs .range-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#history-range-tabs .range-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      selectedRange = btn.dataset.range || "6mo";
      loadHistory();
    });
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) tick();
  });

  updateFxRateLabel();
  applyPortfolioFilter();
  loadHistory();
  loadSectors();
  tick();
})();
