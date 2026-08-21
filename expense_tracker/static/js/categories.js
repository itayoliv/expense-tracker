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
