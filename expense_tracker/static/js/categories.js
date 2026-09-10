/* Category manager modal */

(function () {
  const APP = window.APP || {};
  const ui = APP.ui || {};
  const openModal = ui.openModal || function () {};
  const escapeHtml = ui.escapeHtml || ((t) => String(t || ""));
  const displayName = ui.displayName || ((c) => (c && (c.name || c.name_en)) || "");

  const categoriesModal = document.getElementById("categories-modal");
  const categoryListPanel = document.getElementById("category-list-panel");
  const categoryForm = document.getElementById("category-form");
  const categoriesList = document.getElementById("categories-list");
  const btnManageCategories = document.getElementById("btn-manage-categories");
  const btnAddCategory = document.getElementById("btn-add-category");
  const btnCatFormCancel = document.getElementById("btn-cat-form-cancel");
  const catColor = document.getElementById("cat-color");
  const catColorHex = document.getElementById("cat-color-hex");
  let managedCategories = Array.isArray(APP.categories) ? [...APP.categories] : [];

  function kindLabel(kind) {
    if (kind === "income") {
      return (APP.strings && APP.strings.kind_income) || "Income";
    }
    return (APP.strings && APP.strings.kind_expense) || "Expense";
  }

  function normalizeHex(value) {
    let v = (value || "").trim();
    if (!v) return "#6B7280";
    if (!v.startsWith("#")) v = `#${v}`;
    if (!/^#[0-9A-Fa-f]{6}$/.test(v)) return null;
    return v.toUpperCase();
  }

  function syncColorInputs(fromColor) {
    const hex = normalizeHex(fromColor) || "#6B7280";
    if (catColor) catColor.value = hex;
    if (catColorHex) catColorHex.value = hex;
  }

  function showCategoryList() {
    if (categoryListPanel) categoryListPanel.classList.remove("hidden");
    if (categoryForm) categoryForm.classList.add("hidden");
  }

  function showCategoryForm() {
    if (categoryListPanel) categoryListPanel.classList.add("hidden");
    if (categoryForm) categoryForm.classList.remove("hidden");
  }

  function currentSortMode() {
    return APP.catSort === "value" ? "value" : "alpha";
  }

  function currentSortDirection() {
    return APP.catSortDirection === "desc" ? "desc" : "asc";
  }

  function sortLabel(mode) {
    if (mode === "value") {
      return (APP.strings && APP.strings.sort_categories_value) || "Value";
    }
    return (APP.strings && APP.strings.sort_categories_alpha) || "A–Z";
  }

  function syncSortButtons() {
    const mode = currentSortMode();
    const direction = currentSortDirection();
    document.querySelectorAll(".btn-cat-sort").forEach((btn) => {
      btn.dataset.mode = mode;
      btn.textContent = sortLabel(mode);
    });
    document.querySelectorAll(".btn-cat-sort-direction").forEach((btn) => {
      btn.dataset.direction = direction;
      btn.textContent = direction === "desc" ? "↓" : "↑";
      const label =
        direction === "desc"
          ? (APP.strings && APP.strings.sort_ascending) || "Sort ascending"
          : (APP.strings && APP.strings.sort_descending) || "Sort descending";
      btn.title = label;
      btn.setAttribute("aria-label", label);
    });
  }

  async function setSortMode(mode, direction) {
    const res = await fetch("/api/categories/sort-mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, direction }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Error");
      return;
    }
    await refreshDashboardBackground();
  }

  function bindSortToggleButtons() {
    document.querySelectorAll(".btn-cat-sort").forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => {
        const current = btn.dataset.mode || currentSortMode();
        setSortMode(
          current === "value" ? "alpha" : "value",
          currentSortDirection()
        );
      });
    });
    document.querySelectorAll(".btn-cat-sort-direction").forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => {
        const current = btn.dataset.direction || currentSortDirection();
        setSortMode(
          currentSortMode(),
          current === "desc" ? "asc" : "desc"
        );
      });
    });
  }

  function parseDashboardAppFields(html) {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const script = Array.from(doc.querySelectorAll("script")).find((node) =>
      (node.textContent || "").includes("window.APP")
    );
    if (!script) return {};
    const text = script.textContent || "";
    const fields = {};
    const pieMatch = text.match(/pie:\s*(\{[\s\S]*?\}),\s*\n\s*strings:/);
    if (pieMatch) {
      try {
        fields.pie = JSON.parse(pieMatch[1]);
      } catch {
        /* ignore malformed pie payload */
      }
    }
    const sortMatch = text.match(/catSort:\s*"([^"]+)"/);
    if (sortMatch) fields.catSort = sortMatch[1];
    const directionMatch = text.match(/catSortDirection:\s*"([^"]+)"/);
    if (directionMatch) fields.catSortDirection = directionMatch[1];
    return fields;
  }

  async function refreshDashboardBackground() {
    try {
      const openKeys = Array.from(document.querySelectorAll(".cat-row.open")).map(
        (row) => row.dataset.cat
      );
      const res = await fetch(window.location.href, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!res.ok) return false;
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, "text/html");

      const newGrid = doc.querySelector(".content-grid");
      const oldGrid = document.querySelector(".content-grid");
      if (newGrid && oldGrid) {
        oldGrid.replaceWith(document.importNode(newGrid, true));
      }

      const newBanner = doc.getElementById("unsorted-banner");
      const oldBanner = document.getElementById("unsorted-banner");
      if (newBanner && oldBanner) {
        oldBanner.replaceWith(document.importNode(newBanner, true));
      } else if (newBanner && !oldBanner) {
        const main = document.querySelector("main.main");
        const topbar = main && main.querySelector(".topbar");
        if (main && topbar) {
          topbar.insertAdjacentElement(
            "afterend",
            document.importNode(newBanner, true)
          );
        }
      } else if (!newBanner && oldBanner) {
        oldBanner.remove();
      }

      const fields = parseDashboardAppFields(html);
      if (fields.pie) APP.pie = fields.pie;
      if (fields.catSort) APP.catSort = fields.catSort;
      if (fields.catSortDirection) {
        APP.catSortDirection = fields.catSortDirection;
      }

      syncSortButtons();
      bindSortToggleButtons();
      if (ui.bindCategoryRows) ui.bindCategoryRows();
      if (ui.bindTransactionEdits) ui.bindTransactionEdits();
      if (ui.bindUnsortedItems) ui.bindUnsortedItems();
      if (ui.bindUnsortedSearch) ui.bindUnsortedSearch();
      if (ui.initTagSumWidgets) ui.initTagSumWidgets();
      if (ui.refreshPie) ui.refreshPie();

      openKeys.forEach((key) => {
        if (!key) return;
        const row = document.querySelector(
          `.cat-row[data-cat="${CSS.escape(key)}"]`
        );
        const btn = row && row.querySelector(".cat-toggle");
        if (btn && row && !row.classList.contains("open")) btn.click();
      });
      return true;
    } catch {
      return false;
    }
  }

  ui.refreshDashboardBackground = refreshDashboardBackground;

  function bindCategoryRowActions() {
    if (!categoriesList) return;
    categoriesList.querySelectorAll(".btn-cat-edit").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cat = managedCategories.find((c) => String(c.id) === btn.dataset.id);
        if (cat) openCategoryEditor(cat);
      });
    });
    categoriesList.querySelectorAll(".btn-cat-delete").forEach((btn) => {
      btn.addEventListener("click", () => deleteCategory(btn.dataset.id));
    });
  }

  function renderCategoriesList() {
    if (!categoriesList) return;
    if (!managedCategories.length) {
      categoriesList.innerHTML = `<div class="categories-empty">${
        (APP.strings && APP.strings.no_categories) || "No categories yet."
      }</div>`;
      return;
    }
    categoriesList.innerHTML = managedCategories
      .map(
        (cat) => `
      <div class="cat-manage-row" data-id="${cat.id}">
        <span class="cat-manage-swatch" style="background:${cat.color}"></span>
        <div class="cat-manage-meta">
          <span class="cat-manage-name">${escapeHtml(displayName(cat))}</span>
          <span class="cat-manage-kind">${escapeHtml(kindLabel(cat.kind))}</span>
        </div>
        <div class="cat-manage-actions">
          <button type="button" class="btn ghost btn-cat-edit" data-id="${cat.id}">${
            (APP.strings && APP.strings.edit) || "Edit"
          }</button>
          <button type="button" class="btn ghost danger btn-cat-delete" data-id="${cat.id}">${
            (APP.strings && APP.strings.delete) || "Delete"
          }</button>
        </div>
      </div>`
      )
      .join("");
    bindCategoryRowActions();
  }

  function openCategoryEditor(cat) {
    const title = document.getElementById("category-modal-title");
    if (cat) {
      if (title) {
        title.textContent =
          (APP.strings && APP.strings.edit_category) || "Edit category";
      }
      document.getElementById("cat-id").value = cat.id;
      document.getElementById("cat-name-en").value = cat.name_en || "";
      document.getElementById("cat-name-he").value = cat.name_he || "";
      document.getElementById("cat-kind").value = cat.kind || "expense";
      syncColorInputs(cat.color || "#6B7280");
    } else {
      if (title) {
        title.textContent =
          (APP.strings && APP.strings.add_category) || "Add category";
      }
      if (categoryForm) categoryForm.reset();
      document.getElementById("cat-id").value = "";
      document.getElementById("cat-kind").value = "expense";
      syncColorInputs("#6B7280");
    }
    showCategoryForm();
  }

  async function refreshManagedCategories() {
    try {
      const res = await fetch("/api/categories");
      const data = await res.json().catch(() => ({}));
      if (res.ok && Array.isArray(data.categories)) {
        managedCategories = data.categories;
        APP.categories = managedCategories;
        if (data.cat_sort) APP.catSort = data.cat_sort;
        if (data.cat_sort_direction) {
          APP.catSortDirection = data.cat_sort_direction;
        }
        syncSortButtons();
        renderCategoriesList();
      }
    } catch {
      // Keep the already-rendered list if the API is unavailable.
    }
  }

  async function deleteCategory(id) {
    const msg =
      (APP.strings && APP.strings.confirm_delete_category) ||
      "Delete this category?";
    if (!confirm(msg)) return;
    const res = await fetch(`/api/categories/${id}`, { method: "DELETE" });
    if (res.ok) location.reload();
    else {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Error");
    }
  }

  bindCategoryRowActions();
  bindSortToggleButtons();
  syncSortButtons();

  if (btnManageCategories) {
    btnManageCategories.addEventListener("click", () => {
      managedCategories = Array.isArray(APP.categories) ? [...APP.categories] : [];
      showCategoryList();
      renderCategoriesList();
      openModal(categoriesModal);
      refreshManagedCategories();
    });
  }

  if (btnAddCategory) {
    btnAddCategory.addEventListener("click", () => openCategoryEditor(null));
  }

  if (btnCatFormCancel) {
    btnCatFormCancel.addEventListener("click", () => showCategoryList());
  }

  if (catColor && catColorHex) {
    catColor.addEventListener("input", () => {
      catColorHex.value = catColor.value.toUpperCase();
    });
    catColorHex.addEventListener("change", () => {
      const hex = normalizeHex(catColorHex.value);
      if (hex) {
        catColor.value = hex;
        catColorHex.value = hex;
      } else {
        syncColorInputs(catColor.value);
      }
    });
  }

  if (categoryForm) {
    categoryForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("cat-id").value;
      const color = normalizeHex(catColorHex ? catColorHex.value : catColor.value);
      if (!color) {
        alert("Color must be a hex value like #22C55E");
        return;
      }
      const body = {
        name_en: document.getElementById("cat-name-en").value.trim(),
        name_he: document.getElementById("cat-name-he").value.trim(),
        kind: document.getElementById("cat-kind").value,
        color,
      };
      let res;
      if (id) {
        res = await fetch(`/api/categories/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } else {
        res = await fetch("/api/categories", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      }
      if (res.ok) location.reload();
      else {
        const err = await res.json().catch(() => ({}));
        alert(err.error || "Error");
      }
    });
  }
})();
