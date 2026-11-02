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
  const average = Number(series.average) || 0;

  new Chart(canvas, {
    data: {
      labels: months.map((point) => point.label),
      datasets: [
        {
          type: "bar",
          data: months.map((point) => point.total),
          backgroundColor: color,
          borderRadius: 6,
          maxBarThickness: 48,
          order: 2,
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
      plugins: {
        legend: {
          display: true,
          labels: {
            filter(item) {
              return item.datasetIndex === 1;
            },
          },
        },
        tooltip: {
          callbacks: {
            label(item) {
              const value = Number(item.raw || 0).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              });
              return currency ? `${value} ${currency}` : value;
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
