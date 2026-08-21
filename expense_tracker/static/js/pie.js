/* Chart.js pie chart */

(function () {
  const APP = window.APP || {};
  const pie = APP.pie || { labels: [], values: [], colors: [] };
  const canvas = document.getElementById("pie-chart");
  if (!canvas || !pie.labels || !pie.labels.length) return;

  new Chart(canvas, {
    type: "pie",
    data: {
      labels: pie.labels,
      datasets: [
        {
          data: pie.values,
          backgroundColor: pie.colors,
          borderWidth: 1,
          borderColor: "#fff",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 12, padding: 12, font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              const v = ctx.parsed || 0;
              const sum = ctx.dataset.data.reduce((a, b) => a + b, 0) || 1;
              const pct = ((v / sum) * 100).toFixed(1);
              const currency =
                (APP.strings && APP.strings.currency) || "₪";
              return `${ctx.label}: ${currency}${v.toFixed(2)} (${pct}%)`;
            },
          },
        },
      },
    },
  });
})();
