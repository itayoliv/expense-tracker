/* Tags manager modal + tag-sum calculators */

(function () {
  const APP = window.APP || {};
  const ui = APP.ui || {};
  const openModal = ui.openModal || function () {};
  const escapeHtml = ui.escapeHtml || ((t) => String(t || ""));

  const tagsModal = document.getElementById("tags-modal");
  const tagListPanel = document.getElementById("tag-list-panel");
  const tagForm = document.getElementById("tag-form");
  const tagsList = document.getElementById("tags-list");
  const btnManageTags = document.getElementById("btn-manage-tags");
  const btnAddTag = document.getElementById("btn-add-tag");
  const btnTagFormCancel = document.getElementById("btn-tag-form-cancel");
  const tagColor = document.getElementById("tag-color");
  const tagColorHex = document.getElementById("tag-color-hex");

  let managedTags = Array.isArray(APP.tags) ? [...APP.tags] : [];
  let tagFormulas = Array.isArray(APP.tagFormulas) ? [...APP.tagFormulas] : [];

  function str(key, fallback) {
    return (APP.strings && APP.strings[key]) || fallback;
  }

  function formatMoney(amount) {
    const currency = str("currency", "₪");
    const n = Number(amount) || 0;
    const formatted = n.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return `${currency}${formatted}`;
  }

  function showTagList() {
    if (tagListPanel) tagListPanel.classList.remove("hidden");
    if (tagForm) tagForm.classList.add("hidden");
  }

  function showTagForm() {
    if (tagListPanel) tagListPanel.classList.add("hidden");
    if (tagForm) tagForm.classList.remove("hidden");
  }

  function syncColorInputs(fromColor) {
    if (!tagColor || !tagColorHex) return;
    if (fromColor) {
      const hex = tagColor.value || "#6B7280";
      tagColorHex.value = hex.toUpperCase();
    } else {
      let hex = (tagColorHex.value || "").trim();
      if (!hex.startsWith("#")) hex = `#${hex}`;
      if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
        tagColor.value = hex;
        tagColorHex.value = hex.toUpperCase();
      }
    }
  }

  if (tagColor) tagColor.addEventListener("input", () => syncColorInputs(true));
  if (tagColorHex) tagColorHex.addEventListener("change", () => syncColorInputs(false));

  function bindTagRowActions() {
    if (!tagsList) return;
    tagsList.querySelectorAll(".btn-tag-edit").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tag = managedTags.find((t) => String(t.id) === btn.dataset.id);
        if (tag) openTagEditor(tag);
      });
    });
    tagsList.querySelectorAll(".btn-tag-delete").forEach((btn) => {
      btn.addEventListener("click", () => {
        deleteTag(btn.dataset.id);
      });
    });
  }

  function renderTagsList() {
    if (!tagsList) return;
    if (!managedTags.length) {
      tagsList.innerHTML = `<div class="categories-empty">${escapeHtml(
        str("no_tags", "No tags yet.")
      )}</div>`;
      return;
    }

    tagsList.innerHTML = managedTags
      .map(
        (tag) => `
      <div class="cat-manage-row" data-id="${tag.id}">
        <span class="cat-manage-swatch" style="background:${escapeHtml(tag.color || "#6B7280")}"></span>
        <div class="cat-manage-meta">
          <span class="cat-manage-name">${escapeHtml(tag.name || "")}</span>
        </div>
        <div class="cat-manage-actions">
          <button type="button" class="btn ghost btn-tag-edit" data-id="${tag.id}">${escapeHtml(str("edit", "Edit"))}</button>
          <button type="button" class="btn ghost danger btn-tag-delete" data-id="${tag.id}">${escapeHtml(str("delete", "Delete"))}</button>
        </div>
      </div>`
      )
      .join("");
    bindTagRowActions();
  }

  function openTagEditor(tag) {
    const title = document.getElementById("tag-modal-title");
    if (tag) {
      if (title) title.textContent = str("edit_tag", "Edit tag");
      document.getElementById("tag-id").value = tag.id;
      document.getElementById("tag-name").value = tag.name || "";
      const color = tag.color || "#6B7280";
      if (tagColor) tagColor.value = color;
      if (tagColorHex) tagColorHex.value = color;
    } else {
      if (title) title.textContent = str("add_tag", "Add tag");
      if (tagForm) tagForm.reset();
      document.getElementById("tag-id").value = "";
      if (tagColor) tagColor.value = "#6B7280";
      if (tagColorHex) tagColorHex.value = "#6B7280";
    }
    showTagForm();
  }

  async function refreshManagedTags() {
    try {
      const res = await fetch("/api/tags");
      const data = await res.json().catch(() => ({}));
      if (res.ok && Array.isArray(data.tags)) {
        managedTags = data.tags;
        APP.tags = managedTags;
        renderTagsList();
        refreshTagPickers();
        initTagSumWidgets();
      }
    } catch {
      // Keep existing list.
    }
  }

  async function deleteTag(id) {
    const msg = str("confirm_delete_tag", "Delete this tag?");
    if (!confirm(msg)) return;
    const res = await fetch(`/api/tags/${id}`, { method: "DELETE" });
    if (res.ok) {
      managedTags = managedTags.filter((t) => String(t.id) !== String(id));
      APP.tags = managedTags;
      tagFormulas = tagFormulas.map((formula) => ({
        ...formula,
        tag_ids: (formula.tag_ids || []).filter(
          (tagId) => String(tagId) !== String(id)
        ),
      }));
      APP.tagFormulas = tagFormulas;
      renderTagsList();
      refreshTagPickers();
      initTagSumWidgets();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Error");
    }
  }

  function refreshTagPickers() {
    if (ui.bindTagPickers) ui.bindTagPickers();
  }

  if (btnManageTags) {
    btnManageTags.addEventListener("click", () => {
      managedTags = Array.isArray(APP.tags) ? [...APP.tags] : [];
      showTagList();
      renderTagsList();
      openModal(tagsModal);
      refreshManagedTags();
    });
  }

  if (btnAddTag) {
    btnAddTag.addEventListener("click", () => openTagEditor(null));
  }

  if (btnTagFormCancel) {
    btnTagFormCancel.addEventListener("click", () => {
      showTagList();
      renderTagsList();
    });
  }

  if (tagForm) {
    tagForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("tag-id").value;
      syncColorInputs(false);
      const body = {
        name: document.getElementById("tag-name").value.trim(),
        color: tagColorHex ? tagColorHex.value.trim() : "#6B7280",
      };
      let res;
      if (id) {
        res = await fetch(`/api/tags/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } else {
        res = await fetch("/api/tags", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      }
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        if (data.tag) {
          const idx = managedTags.findIndex((t) => t.id === data.tag.id);
          if (idx >= 0) managedTags[idx] = { ...managedTags[idx], ...data.tag };
          else managedTags.push(data.tag);
          managedTags.sort((a, b) =>
            String(a.name || "").localeCompare(String(b.name || ""), undefined, {
              sensitivity: "base",
            })
          );
          APP.tags = managedTags;
        } else {
          await refreshManagedTags();
        }
        refreshTagPickers();
        initTagSumWidgets();
        showTagList();
        renderTagsList();
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.error || "Error");
      }
    });
  }

  /* ---- Tag sum widgets ---- */

  function parseTagIds(raw) {
    return String(raw || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function collectRows(scopeEl) {
    if (!scopeEl) {
      return Array.from(document.querySelectorAll("#expense-table tr[data-txn-id]"));
    }
    return Array.from(scopeEl.querySelectorAll("tr[data-txn-id]"));
  }

  function tagsPresentInRows(rows) {
    const present = new Set();
    rows.forEach((row) => {
      parseTagIds(row.dataset.tags).forEach((id) => present.add(id));
    });
    return present;
  }

  function sumForSelected(rows, selectedIds) {
    if (!selectedIds.size) return 0;
    let total = 0;
    rows.forEach((row) => {
      if (row.classList.contains("txn-ignored")) return;
      const ids = parseTagIds(row.dataset.tags);
      if (ids.some((id) => selectedIds.has(id))) {
        total += Number(row.dataset.amount) || 0;
      }
    });
    return total;
  }

  function setTagFormulas(formulas) {
    tagFormulas = formulas;
    APP.tagFormulas = tagFormulas;
    document.querySelectorAll(".tag-sum").forEach(updateTagSumWidget);
  }

  async function saveTagFormula(formula, tagIds) {
    const isNew = !formula.id;
    const url = isNew ? "/api/tag-formulas" : `/api/tag-formulas/${formula.id}`;
    const body = { tag_ids: tagIds };
    if (isNew) body.scope = formula.scope || "global";
    try {
      const res = await fetch(url, {
        method: isNew ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.formula) {
        alert(data.error || "Error");
        initTagSumWidgets();
        return;
      }
      if (isNew) {
        setTagFormulas([...tagFormulas, data.formula]);
      } else {
        setTagFormulas(
          tagFormulas.map((item) =>
            String(item.id) === String(formula.id) ? data.formula : item
          )
        );
      }
    } catch {
      alert("Error");
      initTagSumWidgets();
    }
  }

  async function addTagFormula(scope) {
    await saveTagFormula({ id: null, scope, tag_ids: [] }, []);
  }

  function isEmptyFormula(formula) {
    return !Array.isArray(formula.tag_ids) || formula.tag_ids.length === 0;
  }

  async function pruneEmptyFormulas(matchScope) {
    const toRemove = tagFormulas.filter((formula) => {
      if (!isEmptyFormula(formula) || formula.id == null) return false;
      const scope = formula.scope || "global";
      if (matchScope === undefined) return true;
      if (typeof matchScope === "function") return matchScope(scope);
      return scope === matchScope;
    });
    if (!toRemove.length) return false;
    const removeIds = new Set(toRemove.map((formula) => String(formula.id)));
    await Promise.all(
      toRemove.map((formula) =>
        fetch(`/api/tag-formulas/${formula.id}`, { method: "DELETE" }).catch(
          () => null
        )
      )
    );
    setTagFormulas(
      tagFormulas.filter((formula) => !removeIds.has(String(formula.id)))
    );
    return true;
  }

  async function deleteTagFormula(formulaId) {
    try {
      const res = await fetch(`/api/tag-formulas/${formulaId}`, {
        method: "DELETE",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        alert(data.error || "Error");
        return;
      }
      setTagFormulas(
        tagFormulas.filter((item) => String(item.id) !== String(formulaId))
      );
    } catch {
      alert("Error");
    }
  }

  function updateTagSumWidget(widget) {
    const formulasWrap = widget.querySelector(".tag-formulas");
    const addButton = widget.querySelector(".tag-formula-add");
    if (!formulasWrap || !addButton) return;

    const scope = widget.dataset.scope;
    const catKey = widget.dataset.cat;
    const formulaScope =
      scope === "category" && catKey ? `category:${catKey}` : "global";
    let rows;
    if (scope === "category" && catKey) {
      const detail = document.querySelector(
        `.detail-row[data-cat-detail="${CSS.escape(catKey)}"]`
      );
      rows = collectRows(detail);
    } else {
      rows = collectRows(null);
    }

    const presentIds = tagsPresentInRows(rows);
    const formulas = tagFormulas.filter(
      (formula) => (formula.scope || "global") === formulaScope
    );
    const canAddFormula = presentIds.size >= 1;
    addButton.disabled = !canAddFormula;
    addButton.setAttribute("aria-disabled", canAddFormula ? "false" : "true");
    addButton.onclick = canAddFormula
      ? () => addTagFormula(formulaScope)
      : null;

    formulasWrap.innerHTML = formulas
      .map((formula) => {
        const selectedIds = new Set(
          (formula.tag_ids || []).map((id) => String(id))
        );
        const available = managedTags.filter(
          (tag) =>
            presentIds.has(String(tag.id)) || selectedIds.has(String(tag.id))
        );
        const chosenTags = managedTags.filter((tag) =>
          selectedIds.has(String(tag.id))
        );
        const remaining = available.filter(
          (tag) => !selectedIds.has(String(tag.id))
        );
        const chips = chosenTags
          .map(
            (tag) => `
            <span class="tag-chip tag-chip-selected" data-tag-id="${tag.id}" style="--tag-color: ${escapeHtml(tag.color || "#6B7280")}">
              ${escapeHtml(tag.name || "")}
              <button type="button" class="tag-chip-remove" data-tag-id="${tag.id}" title="${escapeHtml(str("remove_tag", "Remove tag"))}" aria-label="${escapeHtml(str("remove_tag", "Remove tag"))}">×</button>
            </span>`
          )
          .join("");
        // New / incomplete rows show the dropdown immediately (no extra +).
        // Rows with tags also get a visible dropdown for any remaining tags.
        const addControl = remaining.length
          ? `<div class="tag-add-wrap">
               <select class="tag-add-select">
                 <option value="">${escapeHtml(str("choose_tag", "Choose tag"))}</option>
                 ${remaining
                   .map(
                     (tag) =>
                       `<option value="${tag.id}">${escapeHtml(tag.name || "")}</option>`
                   )
                   .join("")}
               </select>
             </div>`
          : !chosenTags.length
            ? `<span class="tag-sum-empty">${escapeHtml(
                str("sum_tags_hint", "Add one or more tags with +")
              )}</span>`
            : "";
        let result = "";
        if (selectedIds.size) {
          const labels = chosenTags.map((tag) => tag.name || "").join(" + ");
          const total = sumForSelected(rows, selectedIds);
          result = str("sum_tags_result", "{labels} = {amount}")
            .replace("{labels}", labels)
            .replace("{amount}", formatMoney(total));
        }
        const remove = formula.id
          ? `<button type="button" class="tag-formula-remove" data-formula-id="${formula.id}" title="${escapeHtml(str("remove_tag_formula", "Remove formula"))}" aria-label="${escapeHtml(str("remove_tag_formula", "Remove formula"))}">×</button>`
          : "";
        return `
          <div class="tag-formula-row" data-formula-id="${formula.id || ""}">
            <div class="tag-sum-chips">${chips}${addControl}</div>
            <div class="tag-sum-result">${escapeHtml(result)}</div>
            ${remove}
          </div>`;
      })
      .join("");

    formulasWrap.querySelectorAll(".tag-chip-remove").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const row = btn.closest(".tag-formula-row");
        const formulaId = row && row.dataset.formulaId;
        const formula = formulaId
          ? tagFormulas.find((item) => String(item.id) === formulaId)
          : null;
        if (!formula) return;
        const removeId = String(btn.dataset.tagId || "");
        const ids = (formula.tag_ids || [])
          .map((id) => String(id))
          .filter((id) => id !== removeId)
          .map(Number);
        btn.disabled = true;
        if (!ids.length) {
          await deleteTagFormula(formula.id);
          return;
        }
        await saveTagFormula(formula, ids);
      });
    });

    formulasWrap.querySelectorAll(".tag-add-select").forEach((select) => {
      select.addEventListener("change", async () => {
        const row = select.closest(".tag-formula-row");
        const formulaId = row && row.dataset.formulaId;
        const formula = formulaId
          ? tagFormulas.find((item) => String(item.id) === formulaId)
          : null;
        if (!formula) return;
        const id = Number(select.value);
        if (!Number.isFinite(id) || id <= 0) return;
        const ids = [
          ...new Set([...(formula.tag_ids || []).map(Number), id]),
        ];
        select.disabled = true;
        await saveTagFormula(formula, ids);
      });
    });

    formulasWrap.querySelectorAll(".tag-formula-remove").forEach((btn) => {
      btn.addEventListener("click", () =>
        deleteTagFormula(btn.dataset.formulaId)
      );
    });
  }

  async function initTagSumWidgets() {
    managedTags = Array.isArray(APP.tags) ? [...APP.tags] : managedTags;
    tagFormulas = Array.isArray(APP.tagFormulas)
      ? [...APP.tagFormulas]
      : tagFormulas;
    const pruned = await pruneEmptyFormulas();
    if (!pruned) {
      document.querySelectorAll(".tag-sum").forEach(updateTagSumWidget);
    }
  }

  // Rebuild category sum chips when a category row is opened;
  // drop unfinished (no-tag) formulas when the category is collapsed.
  document.addEventListener("click", (e) => {
    const toggle = e.target.closest(".cat-toggle");
    if (!toggle) return;
    const row = toggle.closest(".cat-row");
    if (!row) return;
    const key = row.dataset.cat;
    requestAnimationFrame(async () => {
      const isOpen = row.classList.contains("open");
      if (!isOpen && key) {
        await pruneEmptyFormulas(`category:${key}`);
        return;
      }
      const widget = document.querySelector(
        `.tag-sum[data-scope="category"][data-cat="${CSS.escape(key || "")}"]`
      );
      if (widget) updateTagSumWidget(widget);
    });
  });

  const btnCloseAll = document.getElementById("btn-close-all");
  if (btnCloseAll) {
    btnCloseAll.addEventListener("click", () => {
      requestAnimationFrame(() => {
        pruneEmptyFormulas((scope) => String(scope).startsWith("category:"));
      });
    });
  }

  initTagSumWidgets();

  APP.ui = APP.ui || ui;
  APP.ui.refreshTagPickers = refreshTagPickers;
  APP.ui.initTagSumWidgets = initTagSumWidgets;
})();
