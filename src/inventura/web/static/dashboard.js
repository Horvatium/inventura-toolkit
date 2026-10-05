// Dashboard charts (Chart.js). The data comes from the JSON block in the page, the colours
// from CSS custom properties, so light and dark mode share one code path. The tables on the
// page hold the same numbers for readers who do not use the charts.
(() => {
  "use strict";

  const charts = new Map();
  // Group thousands always (1.234), as the server does; sl-SI alone skips four-digit numbers.
  const number = new Intl.NumberFormat("sl-SI", { useGrouping: "always" });
  const euro = new Intl.NumberFormat("sl-SI", {
    style: "currency",
    currency: "EUR",
    useGrouping: "always",
  });
  const euroShort = new Intl.NumberFormat("sl-SI", {
    style: "currency",
    currency: "EUR",
    notation: "compact",
    maximumFractionDigits: 1,
  });

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const signed = (value) => (value > 0 ? "+" : "") + euro.format(value);

  // Formatters for the labels at the bar tips, by canvas. They are kept out of the chart
  // options because Chart.js would call any function there as a scriptable option.
  const tipFormats = new WeakMap();

  // Draws each bar's value just past its tip, in muted ink (labels never wear the data colour).
  const tipLabels = {
    id: "tipLabels",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      const tip = tipFormats.get(chart.canvas);
      if (!tip) return;
      const datasetIndex = 0;
      const meta = chart.getDatasetMeta(datasetIndex);
      // A meter puts its label past the end of the track, not on it.
      const anchor = chart.getDatasetMeta(tip.anchorDataset ?? datasetIndex);
      ctx.save();
      ctx.font = `12px ${Chart.defaults.font.family}`;
      ctx.fillStyle = css("--chart-label");
      ctx.textBaseline = "middle";
      meta.data.forEach((bar, index) => {
        const value = chart.data.datasets[datasetIndex].data[index];
        const end = anchor.data[index] ?? bar;
        const negative = value < 0;
        ctx.textAlign = negative ? "right" : "left";
        ctx.fillText(tip.format(value), end.x + (negative ? -6 : 6), bar.y);
      });
      ctx.restore();
    },
  };

  function axes(extra) {
    const grid = css("--chart-grid");
    return {
      x: {
        grid: { color: grid, drawTicks: false },
        border: { display: false },
        ticks: { color: css("--chart-label"), padding: 6 },
        ...extra.x,
      },
      y: {
        grid: { display: false },
        border: { color: css("--chart-axis") },
        ticks: { color: css("--chart-ink"), font: { weight: "600" } },
      },
    };
  }

  function progressChart(canvas, racks) {
    const percent = racks.map((r) => (r.postavk ? (100 * r.presteto) / r.postavk : 0));
    tipFormats.set(canvas, { format: (value) => `${Math.round(value)} %`, anchorDataset: 1 });
    return new Chart(canvas, {
      type: "bar",
      data: {
        labels: racks.map((r) => r.regal),
        datasets: [
          {
            label: "Prešteto",
            data: percent,
            backgroundColor: css("--chart-pos"),
            borderRadius: 4,
            borderSkipped: "start",
            maxBarThickness: 16,
            grouped: false,
            order: 1,
          },
          {
            // The track: the rest of the bar in a lighter step of the same hue.
            label: "Neprešteto",
            data: racks.map(() => 100),
            backgroundColor: css("--chart-track"),
            borderRadius: 4,
            borderSkipped: "start",
            maxBarThickness: 16,
            grouped: false,
            order: 2,
          },
        ],
      },
      options: {
        indexAxis: "y",
        maintainAspectRatio: false,
        animation: false,
        layout: { padding: { right: 44 } },
        scales: axes({ x: { min: 0, max: 100, ticks: { callback: (v) => `${v} %` } } }),
        plugins: {
          legend: { display: false },
          tooltip: {
            filter: (item) => item.datasetIndex === 0,
            callbacks: {
              label: (item) => {
                const rack = racks[item.dataIndex];
                return ` ${number.format(rack.presteto)} od ${number.format(rack.postavk)} postavk`;
              },
            },
          },
        },
      },
      plugins: [tipLabels],
    });
  }

  // Widen a symmetric axis until the longest tip label fits between bar end and chart edge.
  function fitLabels(chart, values, format) {
    const { ctx, chartArea } = chart;
    ctx.save();
    ctx.font = `12px ${Chart.defaults.font.family}`;
    const label = Math.max(0, ...values.map((v) => ctx.measureText(format(v)).width));
    ctx.restore();
    const span = Math.max(1, ...values.map(Math.abs));
    const free = Math.max(0.2, 1 - (2 * (label + 10)) / chartArea.width);
    chart.options.scales.x.min = -span / free;
    chart.options.scales.x.max = span / free;
    chart.update("none");
  }

  function netChart(canvas, racks) {
    const values = racks.map((r) => Number.parseFloat(r.neto));
    const span = Math.max(1, ...values.map(Math.abs));
    const format = (value) => (value === 0 ? "" : signed(value));
    tipFormats.set(canvas, { format });
    const chart = new Chart(canvas, {
      type: "bar",
      data: {
        labels: racks.map((r) => r.regal),
        datasets: [
          {
            label: "Neto razlika",
            data: values,
            backgroundColor: values.map((v) => (v < 0 ? css("--chart-neg") : css("--chart-pos"))),
            borderRadius: 4,
            borderSkipped: "start",
            maxBarThickness: 16,
          },
        ],
      },
      options: {
        indexAxis: "y",
        maintainAspectRatio: false,
        animation: false,
        layout: { padding: { left: 8, right: 8 } },
        scales: axes({
          x: {
            // Symmetric around zero, with room for the labels at both ends.
            min: -span,
            max: span,
            ticks: { callback: (v) => euroShort.format(v), maxTicksLimit: 7 },
            grid: {
              color: (c) => (c.tick?.value === 0 ? css("--chart-axis") : css("--chart-grid")),
              drawTicks: false,
            },
          },
        }),
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (item) => ` ${signed(item.raw)}` } },
        },
      },
      plugins: [tipLabels],
    });
    fitLabels(chart, values, format);
    return chart;
  }

  function render() {
    const source = document.getElementById("dashboard-data");
    if (!source || typeof Chart === "undefined") return;
    const data = JSON.parse(source.textContent);
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    for (const chart of charts.values()) chart.destroy();
    charts.clear();
    const builders = { "chart-progress": progressChart, "chart-net": netChart };
    for (const [id, build] of Object.entries(builders)) {
      const canvas = document.getElementById(id);
      if (canvas) charts.set(id, build(canvas, data.regali));
    }
  }

  document.addEventListener("DOMContentLoaded", render);
  // The only swap on this page is the dashboard refreshing itself.
  document.addEventListener("htmx:afterSettle", render);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
})();
