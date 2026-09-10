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
  ui.bindCategoryRows = bindCategoryRows;

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

  function bindCategoryRows() {
    document.querySelectorAll(".cat-row").forEach((row) => {
      const btn = row.querySelector(".cat-toggle");
      if (!btn || btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => {
        setOpen(row, !row.classList.contains("open"));
      });
    });
  }

  bindCategoryRows();

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

  // From / To = month pickers; To cannot be before From
  const dateFrom = document.getElementById("date_from");
  const dateTo = document.getElementById("date_to");
  function syncDateToMin() {
    if (!dateFrom || !dateTo) return;
    const fromMonth = dateFrom.value; // YYYY-MM
    if (!fromMonth || fromMonth.length < 7) {
      dateTo.removeAttribute("min");
      return;
    }
    dateTo.min = fromMonth;
    if (dateTo.value && dateTo.value < fromMonth) {
      dateTo.value = fromMonth;
    }
  }
  if (dateFrom && dateTo) {
    syncDateToMin();
    dateFrom.addEventListener("change", () => {
      const fromMonth = dateFrom.value;
      if (fromMonth && fromMonth.length >= 7) {
        // Keep To in sync with From when From changes (same month by default)
        dateTo.value = fromMonth;
      }
      syncDateToMin();
    });
  }

})();
