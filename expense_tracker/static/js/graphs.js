/* Category spending by month */
(function () {
  const node = document.getElementById("graphs-series");
  const canvas = document.getElementById("category-month-chart");
  if (!node || !canvas || typeof Chart === "undefined") return;

  let series;
  try {
    series = JSON.parse(node.textContent || "");
  } catch {
    return;
  }
  const months = series.months || [];
  if (!months.length) return;

  const currency = (window.APP && window.APP.strings && window.APP.strings.currency) || "";
  const color = series.color || "#6B7280";
  const averageLabel = node.dataset.averageLabel || "";
  const totalLabel = node.dataset.totalLabel || "";
  const paymentsLabel = node.dataset.paymentsLabel || "";
  const countLabel = node.dataset.countLabel || "";
  const average = Number(series.average) || 0;
  const hebrew = window.APP && window.APP.lang === "he";

  function formatCounts(point) {
    const counts = `${point.count} / ${point.payment_count}`;
    // Keep transactions/payments left to right. Hebrew would otherwise show 1/7.
    return hebrew ? `\u2066${counts}\u2069` : counts;
  }

  function formatMoney(raw) {
    const value = Number(raw || 0).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return currency ? `${value} ${currency}` : value;
  }

  new Chart(canvas, {
    data: {
      labels: months.map((point) => point.label),
      datasets: [
        {
          type: "bar",
          label: totalLabel,
          data: months.map((point) => point.total),
          backgroundColor: color,
          borderRadius: 6,
          maxBarThickness: 48,
          order: 2,
        },
        {
          type: "bar",
          label: paymentsLabel,
          data: months.map((point) => point.payments_total),
          backgroundColor: `${color}66`,
          borderColor: color,
          borderWidth: 1,
          borderRadius: 6,
          maxBarThickness: 48,
          order: 3,
        },
        {
          type: "line",
          label: averageLabel,
          data: months.map(() => average),
          borderColor: "#111827",
          borderDash: [6, 4],
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 0,
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: true },
        tooltip: {
          callbacks: {
            label(item) {
              const money = formatMoney(item.raw);
              return item.dataset.label ? `${item.dataset.label}: ${money}` : money;
            },
            footer(items) {
              const point = items.length ? months[items[0].dataIndex] : null;
              if (!point) return "";
              const counts = formatCounts(point);
              return countLabel ? `${countLabel}: ${counts}` : counts;
            },
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback(value) {
              return Number(value).toLocaleString();
            },
          },
        },
      },
    },
  });
})();
