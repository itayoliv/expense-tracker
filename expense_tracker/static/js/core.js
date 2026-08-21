/* Shared UI helpers — load first */

(function () {
  const APP = (window.APP = window.APP || {});
  const ui = (APP.ui = APP.ui || {});

  function str(key, fallback) {
    return (APP.strings && APP.strings[key]) || fallback;
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function openModal(el) {
    if (el && el.showModal) el.showModal();
  }

  function closeModal(el) {
    if (el && el.open) el.close();
  }

  function displayName(cat) {
    if (!cat) return "";
    if (APP.lang === "he") return cat.name_he || cat.name || cat.name_en;
    return cat.name_en || cat.name || cat.name_he;
  }

  ui.str = str;
  ui.escapeHtml = escapeHtml;
  ui.openModal = openModal;
  ui.closeModal = closeModal;
  ui.displayName = displayName;

  // Flash auto-dismiss
  const flash = document.getElementById("flash-wrap");
  if (flash) {
    setTimeout(() => flash.remove(), 5000);
  }

  document.querySelectorAll("[data-close]").forEach((btn) => {
    btn.addEventListener("click", () => {
      closeModal(btn.closest("dialog"));
    });
  });

  // Expand / collapse categories
  function setOpen(row, open) {
    const key = row.dataset.cat;
    const detail = document.querySelector(`[data-cat-detail="${CSS.escape(key)}"]`);
    row.classList.toggle("open", open);
    const btn = row.querySelector(".cat-toggle");
    if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (detail) detail.classList.toggle("hidden", !open);
  }

  document.querySelectorAll(".cat-row").forEach((row) => {
    const btn = row.querySelector(".cat-toggle");
    if (!btn) return;
    btn.addEventListener("click", () => {
      setOpen(row, !row.classList.contains("open"));
    });
  });

  const openAll = document.getElementById("btn-open-all");
  const closeAll = document.getElementById("btn-close-all");
  if (openAll) {
    openAll.addEventListener("click", () => {
      document.querySelectorAll(".cat-row").forEach((r) => setOpen(r, true));
    });
  }
  if (closeAll) {
    closeAll.addEventListener("click", () => {
      document.querySelectorAll(".cat-row").forEach((r) => setOpen(r, false));
    });
  }

  // Period filter: month clears dates; applying dates keeps the selected month ignored server-side
  const periodForm = document.getElementById("period-form");
  const monthSelect = document.getElementById("month");
  const dateFrom = document.getElementById("date_from");
  const dateTo = document.getElementById("date_to");
  if (periodForm && monthSelect) {
    monthSelect.addEventListener("change", () => {
      if (dateFrom) dateFrom.value = "";
      if (dateTo) dateTo.value = "";
      periodForm.submit();
    });
  }
})();
