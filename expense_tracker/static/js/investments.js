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
    buyRemove: root.dataset.labelBuyRemove || "Remove",
    buyOverBudget: root.dataset.labelBuyOverBudget || "Allocated percentages total {percent}%, which is over 100%.",
    buyOverBudgetCost: root.dataset.labelBuyOverBudgetCost || "Share costs total ${amount}, which is over the budget.",
    buyBudgetUsd: root.dataset.labelBuyBudgetUsd || "Budget in USD: ${amount}",
    buySelectStock: root.dataset.labelBuySelectStock || "Select a stock",
    buyModePercent: root.dataset.labelBuyModePercent || "Budget %",
    buyModeShares: root.dataset.labelBuyModeShares || "Shares",
    buyModeHint: root.dataset.labelBuyModeHint || "Click to enter by budget % or by number of shares",
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
  let buyCurrency = "ILS";
  let buyInputMode = "shares";
  const buyStockCatalog = new Map();

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

  function formatPlannerMoney(amountUsd, showIls = false) {
    const n = Number(amountUsd) || 0;
    let html = `<span class="money money-usd"><span class="money-sym">${usdSym}</span><span class="money-num">${formatNum(n)}</span></span>`;
    if (showIls && usdIls > 0) {
      html += `<span class="money-ils muted-note">≈ ${formatNum(n * usdIls)} ${ilsSym}</span>`;
    }
    return html;
  }

  function currentStockPrice(symbol) {
    const rows = document.querySelectorAll(".holding-row[data-symbol]");
    for (const row of rows) {
      if ((row.dataset.symbol || "").toUpperCase() === symbol) {
        const price = Number(row.dataset.price) || 0;
        if (price > 0) return price;
      }
    }
    return 0;
  }

  function populateBuyStockCatalog() {
    document.querySelectorAll(".holding-row[data-symbol]").forEach((row) => {
      const symbol = (row.dataset.symbol || "").toUpperCase();
      if (!symbol || buyStockCatalog.has(symbol)) return;
      const name = row.querySelector(".holding-name")?.textContent?.trim() || symbol;
      buyStockCatalog.set(symbol, { symbol, name });
    });
  }

  function getBuyBudgetUsd() {
    const budgetInput = document.getElementById("buy-budget-input");
    const amount = Math.max(0, Number(budgetInput?.value) || 0);
    const needsRate = buyCurrency === "ILS";
    const hasRate = usdIls > 0;
    return {
      amount,
      needsRate,
      hasRate,
      budgetUsd: needsRate ? (hasRate ? amount / usdIls : 0) : amount,
    };
  }

  function isFractionalShares() {
    return document.getElementById("buy-fractional")?.checked || false;
  }

  function normalizeShareCount(raw, fractional = isFractionalShares()) {
    const n = Math.max(0, Number(raw) || 0);
    if (fractional) return Math.floor((n + Number.EPSILON) * 10000) / 10000;
    return Math.floor(n + Number.EPSILON);
  }

  function sharesFromAllocation(allocated, price, fractional = isFractionalShares()) {
    if (!(price > 0)) return 0;
    return normalizeShareCount(allocated / price, fractional);
  }

  function syncBuyPlannerModeUI() {
    const table = document.getElementById("buy-planner-table");
    if (table) table.dataset.inputMode = buyInputMode;
    document.querySelectorAll(".buy-mode-toggle").forEach((btn) => {
      const active = btn.dataset.mode === buyInputMode;
      btn.classList.toggle("buy-mode-active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const fractional = isFractionalShares();
    document.querySelectorAll("#buy-planner-body tr[data-symbol]").forEach((row) => {
      const pctInput = row.querySelector(".buy-percent-input");
      const pctDisplay = row.querySelector(".buy-row-percent");
      const sharesInput = row.querySelector(".buy-shares-input");
      const sharesDisplay = row.querySelector(".buy-row-shares");
      const percentMode = buyInputMode === "percent";
      if (pctInput) pctInput.hidden = !percentMode;
      if (pctDisplay) pctDisplay.hidden = percentMode;
      if (sharesInput) {
        sharesInput.hidden = percentMode;
        sharesInput.step = fractional ? "0.0001" : "1";
      }
      if (sharesDisplay) sharesDisplay.hidden = !percentMode;
    });
  }

  function setBuyInputMode(mode) {
    if (mode !== "percent" && mode !== "shares") return;
    if (mode === buyInputMode) {
      syncBuyPlannerModeUI();
      return;
    }

    const { budgetUsd } = getBuyBudgetUsd();
    const fractional = isFractionalShares();
    document.querySelectorAll("#buy-planner-body tr[data-symbol]").forEach((row) => {
      const symbol = row.dataset.symbol || "";
      const price = currentStockPrice(symbol);
      const pctInput = row.querySelector(".buy-percent-input");
      const sharesInput = row.querySelector(".buy-shares-input");
      if (buyInputMode === "percent") {
        const pct = Math.max(0, Number(pctInput?.value) || 0);
        const allocated = budgetUsd * (pct / 100);
        const shares = sharesFromAllocation(allocated, price, fractional);
        if (sharesInput) sharesInput.value = fractional ? shares.toFixed(4) : String(shares);
      } else {
        const shares = normalizeShareCount(sharesInput?.value, fractional);
        const cost = shares * price;
        const pct = budgetUsd > 0 ? (cost / budgetUsd) * 100 : 0;
        if (pctInput) pctInput.value = pct.toFixed(2);
      }
    });

    buyInputMode = mode;
    syncBuyPlannerModeUI();
    updateBuyPlanner();
  }

  function refreshBuyStockSelect() {
    const select = document.getElementById("buy-stock-select");
    const addBtn = document.getElementById("buy-stock-add");
    const body = document.getElementById("buy-planner-body");
    if (!select || !body) return;

    const selected = new Set(
      [...body.querySelectorAll("tr[data-symbol]")].map((row) => row.dataset.symbol)
    );
    select.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = labels.buySelectStock;
    select.appendChild(placeholder);

    [...buyStockCatalog.values()]
      .sort((a, b) => a.symbol.localeCompare(b.symbol))
      .forEach((stock) => {
        if (selected.has(stock.symbol)) return;
        const option = document.createElement("option");
        option.value = stock.symbol;
        option.textContent = stock.name === stock.symbol
          ? stock.symbol
          : `${stock.symbol} — ${stock.name}`;
        select.appendChild(option);
      });

    select.disabled = select.options.length <= 1;
    if (addBtn) addBtn.disabled = select.disabled;
  }

  function updateBuyPlanner() {
    const body = document.getElementById("buy-planner-body");
    if (!body) return;

    const { needsRate, hasRate, budgetUsd } = getBuyBudgetUsd();
    const fractional = isFractionalShares();
    const convertedEl = document.getElementById("buy-budget-usd");
    const rateEl = document.getElementById("buy-fx-rate");
    const rateError = document.getElementById("buy-fx-error");

    if (convertedEl) {
      convertedEl.hidden = !needsRate || !hasRate;
      convertedEl.textContent = labels.buyBudgetUsd.replace("{amount}", formatNum(budgetUsd));
    }
    if (rateEl) {
      rateEl.hidden = !hasRate;
      rateEl.textContent = hasRate
        ? fxLabelTemplate.replace("{rate}", usdIls.toFixed(4))
        : "";
    }
    if (rateError) rateError.hidden = !needsRate || hasRate;

    let usedPercent = 0;
    let totalCost = 0;
    body.querySelectorAll("tr[data-symbol]").forEach((row) => {
      const symbol = row.dataset.symbol || "";
      const price = currentStockPrice(symbol);
      const pctInput = row.querySelector(".buy-percent-input");
      const sharesInput = row.querySelector(".buy-shares-input");
      let pct = 0;
      let shares = 0;
      let allocated = 0;
      let cost = 0;
      let leftover = 0;

      if (buyInputMode === "shares") {
        shares = normalizeShareCount(sharesInput?.value, fractional);
        if (sharesInput && !fractional) sharesInput.value = String(shares);
        cost = shares * price;
        pct = budgetUsd > 0 ? (cost / budgetUsd) * 100 : 0;
        allocated = cost;
        leftover = 0;
      } else {
        pct = Math.max(0, Number(pctInput?.value) || 0);
        allocated = budgetUsd * (pct / 100);
        shares = sharesFromAllocation(allocated, price, fractional);
        cost = shares * price;
        leftover = allocated - cost;
      }

      usedPercent += pct;
      totalCost += cost;
      const priceEl = row.querySelector(".buy-row-price");
      const allocatedEl = row.querySelector(".buy-row-allocated");
      const percentDisplay = row.querySelector(".buy-row-percent");
      const sharesDisplay = row.querySelector(".buy-row-shares");
      const costEl = row.querySelector(".buy-row-cost");
      const leftoverEl = row.querySelector(".buy-row-leftover");
      if (priceEl) priceEl.innerHTML = formatPlannerMoney(price, usdIls > 0);
      if (allocatedEl) allocatedEl.textContent = `${usdSym}${formatNum(allocated)}`;
      if (percentDisplay) percentDisplay.textContent = `${pct.toFixed(2)}%`;
      if (sharesDisplay) {
        sharesDisplay.textContent = fractional ? shares.toFixed(4) : String(shares);
      }
      if (costEl) costEl.textContent = `${usdSym}${formatNum(cost)}`;
      if (leftoverEl) leftoverEl.textContent = `${usdSym}${formatNum(leftover)}`;
    });

    const leftoverPercent = 100 - usedPercent;
    const totalLeftover = budgetUsd - totalCost;
    const usedEl = document.getElementById("buy-used-percent");
    const leftoverPctEl = document.getElementById("buy-leftover-percent");
    const leftoverEl = document.getElementById("buy-total-leftover");
    const warningEl = document.getElementById("buy-percent-warning");
    if (usedEl) usedEl.textContent = `${usedPercent.toFixed(2)}%`;
    if (leftoverPctEl) leftoverPctEl.textContent = `${leftoverPercent.toFixed(2)}%`;
    if (leftoverEl) leftoverEl.innerHTML = formatPlannerMoney(totalLeftover, needsRate);
    if (warningEl) {
      const overPercent = buyInputMode === "percent" && usedPercent > 100;
      const overCost = buyInputMode === "shares" && budgetUsd > 0 && totalCost > budgetUsd + 0.005;
      warningEl.hidden = !overPercent && !overCost;
      if (overPercent) {
        warningEl.textContent = labels.buyOverBudget.replace("{percent}", usedPercent.toFixed(2));
      } else if (overCost) {
        warningEl.textContent = labels.buyOverBudgetCost.replace("{amount}", formatNum(totalCost));
      }
    }
  }

  function addBuyPlannerStock(symbol) {
    const body = document.getElementById("buy-planner-body");
    const stock = buyStockCatalog.get(symbol);
    if (!body || !stock || body.querySelector(`tr[data-symbol="${CSS.escape(symbol)}"]`)) return;

    const row = document.createElement("tr");
    row.dataset.symbol = symbol;
    const fractional = isFractionalShares();

    const symbolCell = document.createElement("td");
    const symbolStrong = document.createElement("strong");
    symbolStrong.textContent = symbol;
    symbolCell.appendChild(symbolStrong);
    if (stock.name !== symbol) {
      const name = document.createElement("span");
      name.className = "buy-stock-name muted-note";
      name.textContent = stock.name;
      symbolCell.appendChild(name);
    }

    const priceCell = document.createElement("td");
    priceCell.className = "tx-amt buy-row-price";

    const percentCell = document.createElement("td");
    percentCell.className = "tx-amt buy-col-percent";
    const percentInput = document.createElement("input");
    percentInput.type = "number";
    percentInput.className = "buy-percent-input";
    percentInput.min = "0";
    percentInput.max = "100";
    percentInput.step = "0.01";
    percentInput.value = "0";
    percentInput.setAttribute("aria-label", labels.buyModePercent);
    percentInput.hidden = true;
    const percentDisplay = document.createElement("span");
    percentDisplay.className = "buy-row-percent";
    percentCell.append(percentInput, percentDisplay);

    const allocatedCell = document.createElement("td");
    allocatedCell.className = "tx-amt buy-row-allocated";

    const sharesCell = document.createElement("td");
    sharesCell.className = "tx-amt buy-col-shares";
    const sharesInput = document.createElement("input");
    sharesInput.type = "number";
    sharesInput.className = "buy-shares-input";
    sharesInput.min = "0";
    sharesInput.step = fractional ? "0.0001" : "1";
    sharesInput.value = "0";
    sharesInput.setAttribute("aria-label", labels.buyModeShares);
    const sharesDisplay = document.createElement("span");
    sharesDisplay.className = "buy-row-shares";
    sharesDisplay.hidden = true;
    sharesCell.append(sharesInput, sharesDisplay);

    const costCell = document.createElement("td");
    costCell.className = "tx-amt buy-row-cost";
    const leftoverCell = document.createElement("td");
    leftoverCell.className = "tx-amt buy-row-leftover";

    const actionCell = document.createElement("td");
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "buy-remove";
    removeBtn.textContent = labels.buyRemove;
    actionCell.appendChild(removeBtn);

    row.append(
      symbolCell,
      priceCell,
      percentCell,
      allocatedCell,
      sharesCell,
      costCell,
      leftoverCell,
      actionCell
    );
    body.appendChild(row);
    percentInput.addEventListener("input", updateBuyPlanner);
    sharesInput.addEventListener("input", updateBuyPlanner);
    removeBtn.addEventListener("click", () => {
      row.remove();
      refreshBuyStockSelect();
      updateBuyPlannerVisibility();
      updateBuyPlanner();
    });

    syncBuyPlannerModeUI();
    refreshBuyStockSelect();
    updateBuyPlannerVisibility();
    updateBuyPlanner();
  }

  function updateBuyPlannerVisibility() {
    const body = document.getElementById("buy-planner-body");
    const empty = document.getElementById("buy-planner-empty");
    const tableWrap = document.getElementById("buy-planner-table-wrap");
    const hasRows = !!body?.querySelector("tr");
    if (empty) empty.hidden = hasRows;
    if (tableWrap) tableWrap.hidden = !hasRows;
  }

  function splitBuyPlannerEqually() {
    const rows = [...document.querySelectorAll("#buy-planner-body tr[data-symbol]")];
    if (!rows.length) return;
    const { budgetUsd } = getBuyBudgetUsd();
    const fractional = isFractionalShares();
    const equal = Math.floor((100 / rows.length) * 100) / 100;
    rows.forEach((row, index) => {
      const pct = index === rows.length - 1
        ? 100 - equal * (rows.length - 1)
        : equal;
      const pctInput = row.querySelector(".buy-percent-input");
      const sharesInput = row.querySelector(".buy-shares-input");
      if (pctInput) pctInput.value = pct.toFixed(2);
      if (buyInputMode === "shares" && sharesInput) {
        const price = currentStockPrice(row.dataset.symbol || "");
        const shares = sharesFromAllocation(budgetUsd * (pct / 100), price, fractional);
        sharesInput.value = fractional ? shares.toFixed(4) : String(shares);
      }
    });
    updateBuyPlanner();
  }

  function bindBuyPlanner() {
    populateBuyStockCatalog();
    refreshBuyStockSelect();
    updateBuyPlannerVisibility();
    syncBuyPlannerModeUI();

    document.getElementById("buy-budget-input")?.addEventListener("input", updateBuyPlanner);
    document.getElementById("buy-fractional")?.addEventListener("change", () => {
      syncBuyPlannerModeUI();
      updateBuyPlanner();
    });
    document.getElementById("buy-stock-add")?.addEventListener("click", () => {
      const select = document.getElementById("buy-stock-select");
      if (select?.value) addBuyPlannerStock(select.value);
    });
    document.getElementById("buy-split-equally")?.addEventListener("click", splitBuyPlannerEqually);
    document.querySelectorAll(".buy-mode-toggle").forEach((btn) => {
      btn.addEventListener("click", () => setBuyInputMode(btn.dataset.mode || "percent"));
    });
    document.querySelectorAll("#buy-currency-tabs [data-currency]").forEach((btn) => {
      btn.addEventListener("click", () => {
        buyCurrency = btn.dataset.currency || "USD";
        document.querySelectorAll("#buy-currency-tabs [data-currency]").forEach((other) => {
          other.classList.toggle("active", other === btn);
        });
        updateBuyPlanner();
      });
    });
    updateBuyPlanner();
  }

  function calculateFxSavings() {
    const amountInput = document.getElementById("fx-savings-amount");
    const oneZeroInput = document.getElementById("fx-onezero-rate");
    const panel = document.getElementById("fx-savings-panel");
    if (!amountInput || !oneZeroInput || !panel) return;

    const amount = Math.max(0, Number(amountInput.value) || 0);
    const oneZeroRate = Math.max(0, Number(oneZeroInput.value) || 0);
    const oneZeroCost = amount * (oneZeroRate / 100);
    const baselineCost = panel.querySelector(".fx-savings-baseline .fx-fee-cost");
    if (baselineCost) baselineCost.textContent = `${formatNum(oneZeroCost)} ${ilsSym}`;

    panel.querySelectorAll(".fx-savings-row:not(.fx-savings-baseline)").forEach((row) => {
      const rateInput = row.querySelector(".fx-fee-rate");
      const costEl = row.querySelector(".fx-fee-cost");
      const savedEl = row.querySelector(".fx-fee-saved");
      const rawRate = rateInput?.value?.trim() || "";
      if (!rawRate || amount <= 0) {
        if (costEl) costEl.textContent = "—";
        if (savedEl) {
          savedEl.textContent = "—";
          savedEl.classList.remove("chg-up", "chg-down");
        }
        return;
      }

      const rate = Math.max(0, Number(rawRate) || 0);
      const cost = amount * (rate / 100);
      const saved = cost - oneZeroCost;
      if (costEl) costEl.textContent = `${formatNum(cost)} ${ilsSym}`;
      if (savedEl) {
        savedEl.textContent = `${saved >= 0 ? "+" : ""}${formatNum(saved)} ${ilsSym}`;
        savedEl.classList.toggle("chg-up", saved > 0);
        savedEl.classList.toggle("chg-down", saved < 0);
      }
    });
  }

  function bindFxSavings() {
    const form = document.getElementById("fx-savings-form");
    const panel = document.getElementById("fx-savings-panel");
    if (!form || !panel) return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      calculateFxSavings();
    });
    panel.querySelectorAll(".fx-fee-rate").forEach((input) => {
      input.addEventListener("input", () => {
        if (document.getElementById("fx-savings-amount")?.value) calculateFxSavings();
      });
    });
  }

  function renderSavedFxConversion(conversion, savedTotal) {
    const body = document.getElementById("fx-conversion-history-body");
    const wrap = document.getElementById("fx-conversion-history-wrap");
    const empty = document.getElementById("fx-conversion-no-history");
    if (!body) return;

    const row = document.createElement("tr");
    const values = [
      conversion.conversion_date,
      `${formatNum(conversion.nis_amount)} ${ilsSym}`,
      Number(conversion.usd_ils_rate).toFixed(4),
      `${usdSym}${formatNum(conversion.usd_amount)}`,
      `${formatNum(conversion.saved_nis)} ${ilsSym}`,
    ];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (index > 0) cell.classList.add("tx-amt");
      if (index === 4) cell.classList.add("chg-up");
      row.appendChild(cell);
    });
    body.prepend(row);
    if (wrap) wrap.hidden = false;
    if (empty) empty.hidden = true;

    const total = document.getElementById("onezero-saved-total");
    if (total) total.textContent = `${formatNum(savedTotal)} ${ilsSym}`;
  }

  function bindFxConversionRecords() {
    const form = document.getElementById("fx-conversion-record-form");
    const status = document.getElementById("fx-conversion-status");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submit = form.querySelector('button[type="submit"]');
      if (submit) submit.disabled = true;
      if (status) status.hidden = true;
      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: {
            Accept: "application/json",
            "X-Requested-With": "XMLHttpRequest",
          },
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || `HTTP ${response.status}`);
        }
        renderSavedFxConversion(payload.conversion, payload.onezero_saved_total);
        form.reset();
        if (status) {
          status.textContent = payload.message;
          status.className = "fx-conversion-status success";
          status.hidden = false;
        }
      } catch (error) {
        if (status) {
          status.textContent = error.message || String(error);
          status.className = "fx-conversion-status error";
          status.hidden = false;
        }
      } finally {
        if (submit) submit.disabled = false;
      }
    });
  }

  function bindCollapsiblePanels() {
    document.querySelectorAll(".collapsible-chart-panel").forEach((panel) => {
      const toggle = panel.querySelector(".panel-collapse-toggle");
      const body = panel.querySelector(".collapsible-panel-body");
      if (!toggle || !body) return;
      toggle.addEventListener("click", () => {
        const open = !panel.classList.contains("open");
        panel.classList.toggle("open", open);
        body.classList.toggle("hidden", !open);
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        if (open && panel.classList.contains("investments-sector-panel") && sectorChart) {
          requestAnimationFrame(() => sectorChart.resize());
        }
      });
    });
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
    updateBuyPlanner();

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
  bindCollapsiblePanels();
  bindBuyPlanner();
  bindFxSavings();
  bindFxConversionRecords();
  loadHistory();
  loadSectors();
  tick();
})();
