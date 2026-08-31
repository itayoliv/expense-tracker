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
  const expandedGroups = new Set();
  const loadedTxns = new Map();

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

  function txnRowHtml(tx) {
    const desc = escapeHtml(tx.custom_description || tx.description || "");
    return `
      <div class="tag-txn-row">
        <span class="tag-txn-desc">${desc}</span>
        <span class="tag-txn-date">${escapeHtml(tx.date || "")}</span>
        <span class="tag-txn-amt">${escapeHtml(formatMoney(tx.amount))}</span>
      </div>`;
  }

  async function loadTagTransactions(tagId, bodyEl) {
    if (!bodyEl) return;
    if (loadedTxns.has(tagId)) {
      bodyEl.innerHTML = loadedTxns.get(tagId).map(txnRowHtml).join("") ||
        `<div class="categories-empty">${escapeHtml(str("no_tags", "No tags yet."))}</div>`;
      return;
    }
    bodyEl.innerHTML = `<div class="categories-empty">…</div>`;
    try {
      const res = await fetch(`/api/tags/${tagId}/transactions`);
      const data = await res.json().catch(() => ({}));
      if (res.ok && Array.isArray(data.transactions)) {
        loadedTxns.set(tagId, data.transactions);
        bodyEl.innerHTML =
          data.transactions.map(txnRowHtml).join("") ||
          `<div class="categories-empty">${escapeHtml(str("no_tags", "No tags yet."))}</div>`;
      } else {
        bodyEl.innerHTML = `<div class="categories-empty">${escapeHtml(data.error || "Error")}</div>`;
      }
    } catch {
      bodyEl.innerHTML = `<div class="categories-empty">Error</div>`;
    }
  }

  function bindTagRowActions() {
    if (!tagsList) return;
    tagsList.querySelectorAll(".btn-tag-edit").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const tag = managedTags.find((t) => String(t.id) === btn.dataset.id);
        if (tag) openTagEditor(tag);
      });
    });
    tagsList.querySelectorAll(".btn-tag-delete").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteTag(btn.dataset.id);
      });
    });
    tagsList.querySelectorAll(".tag-group-header").forEach((btn) => {
      btn.addEventListener("click", () => {
        const groupKey = btn.dataset.groupKey || "";
        const group = btn.closest(".rule-group");
        if (!group) return;
        const open = !group.classList.contains("open");
        group.classList.toggle("open", open);
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) {
          expandedGroups.add(groupKey);
          loadTagTransactions(groupKey, group.querySelector(".rule-group-body"));
        } else {
          expandedGroups.delete(groupKey);
        }
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

    const countLabel = str("tags_count", "{n} transactions");
    tagsList.innerHTML = managedTags
      .map((tag) => {
        const key = String(tag.id);
        const forceOpen = expandedGroups.has(key);
        const countText = countLabel.replace("{n}", String(tag.txn_count || 0));
        const totalText = formatMoney(tag.total || 0);
        return `
      <div class="rule-group${forceOpen ? " open" : ""}" data-group-key="${escapeHtml(key)}">
        <div class="tag-group-top">
          <button type="button" class="rule-group-header tag-group-header" data-group-key="${escapeHtml(key)}" aria-expanded="${forceOpen ? "true" : "false"}">
            <span class="chevron">▸</span>
            <span class="cat-manage-swatch" style="background:${escapeHtml(tag.color || "#6B7280")}"></span>
            <span class="rule-group-name">${escapeHtml(tag.name || "")}</span>
            <span class="rule-group-count">${escapeHtml(countText)}</span>
            <span class="tag-group-total">${escapeHtml(totalText)}</span>
          </button>
          <div class="tag-group-actions">
            <button type="button" class="btn ghost btn-tag-edit" data-id="${tag.id}">${escapeHtml(str("edit", "Edit"))}</button>
            <button type="button" class="btn ghost danger btn-tag-delete" data-id="${tag.id}">${escapeHtml(str("delete", "Delete"))}</button>
          </div>
        </div>
        <div class="rule-group-body"></div>
      </div>`;
      })
      .join("");
    bindTagRowActions();
    expandedGroups.forEach((key) => {
      const group = tagsList.querySelector(`.rule-group[data-group-key="${CSS.escape(key)}"]`);
      if (group) loadTagTransactions(key, group.querySelector(".rule-group-body"));
    });
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
        loadedTxns.clear();
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
      loadedTxns.delete(String(id));
      expandedGroups.delete(String(id));
      renderTagsList();
      refreshTagPickers();
      initTagSumWidgets();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Error");
    }
  }

  function refreshTagPickers() {
    document.querySelectorAll(".tag-picker-chips").forEach((wrap) => {
      const picker = wrap.closest(".tag-picker");
      const selected = new Set(
        String((picker && picker.dataset.selected) || "")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      );
      // Preserve selection for txn modal picker via selected class
      const currentSelected = new Set(
        Array.from(wrap.querySelectorAll(".tag-chip-toggle.selected")).map(
          (b) => b.dataset.tagId
        )
      );
      const useSelected = currentSelected.size ? currentSelected : selected;
      wrap.innerHTML = managedTags
        .map((tag) => {
          const sel = useSelected.has(String(tag.id)) ? " selected" : "";
          return `<button type="button" class="tag-chip tag-chip-toggle${sel}" data-tag-id="${tag.id}" style="--tag-color: ${escapeHtml(tag.color || "#6B7280")}">${escapeHtml(tag.name || "")}</button>`;
        })
        .join("");
    });
    if (ui.bindTagPickers) ui.bindTagPickers();
  }

  if (btnManageTags) {
    btnManageTags.addEventListener("click", () => {
      managedTags = Array.isArray(APP.tags) ? [...APP.tags] : [];
      expandedGroups.clear();
      loadedTxns.clear();
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
          expandedGroups.add(String(data.tag.id));
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
    return managedTags.filter((t) => present.has(String(t.id)));
  }

  function sumForSelected(rows, selectedIds) {
    if (selectedIds.size < 2) return 0;
    let total = 0;
    rows.forEach((row) => {
      const ids = parseTagIds(row.dataset.tags);
      if (ids.some((id) => selectedIds.has(id))) {
        total += Number(row.dataset.amount) || 0;
      }
    });
    return total;
  }

  function updateTagSumWidget(widget) {
    const chipsWrap = widget.querySelector(".tag-sum-chips");
    const resultEl = widget.querySelector(".tag-sum-result");
    if (!chipsWrap || !resultEl) return;

    const scope = widget.dataset.scope;
    const catKey = widget.dataset.cat;
    let rows;
    if (scope === "category" && catKey) {
      const detail = document.querySelector(
        `.detail-row[data-cat-detail="${CSS.escape(catKey)}"]`
      );
      rows = collectRows(detail);
    } else {
      rows = collectRows(null);
    }

    const available = tagsPresentInRows(rows);
    const selected = new Set(
      Array.from(chipsWrap.querySelectorAll(".tag-chip-toggle.selected")).map(
        (b) => b.dataset.tagId
      )
    );

    if (!available.length) {
      chipsWrap.innerHTML = `<span class="tag-sum-empty">${escapeHtml(
        str("sum_tags_hint", "Select two or more tags")
      )}</span>`;
      resultEl.hidden = true;
      resultEl.textContent = "";
      return;
    }

    chipsWrap.innerHTML = available
      .map((tag) => {
        const sel = selected.has(String(tag.id)) ? " selected" : "";
        return `<button type="button" class="tag-chip tag-chip-toggle${sel}" data-tag-id="${tag.id}" style="--tag-color: ${escapeHtml(tag.color || "#6B7280")}">${escapeHtml(tag.name || "")}</button>`;
      })
      .join("");

    chipsWrap.querySelectorAll(".tag-chip-toggle").forEach((btn) => {
      btn.addEventListener("click", () => {
        btn.classList.toggle("selected");
        refreshResult();
      });
    });

    function refreshResult() {
      const chosen = Array.from(
        chipsWrap.querySelectorAll(".tag-chip-toggle.selected")
      );
      const ids = new Set(chosen.map((b) => b.dataset.tagId));
      if (ids.size < 2) {
        resultEl.hidden = true;
        resultEl.textContent = str("sum_tags_hint", "Select two or more tags");
        resultEl.hidden = false;
        return;
      }
      const labels = chosen.map((b) => b.textContent.trim()).join(" + ");
      const total = sumForSelected(rows, ids);
      const template = str("sum_tags_result", "{labels} = {amount}");
      resultEl.textContent = template
        .replace("{labels}", labels)
        .replace("{amount}", formatMoney(total));
      resultEl.hidden = false;
    }

    refreshResult();
  }

  function initTagSumWidgets() {
    managedTags = Array.isArray(APP.tags) ? [...APP.tags] : managedTags;
    document.querySelectorAll(".tag-sum").forEach(updateTagSumWidget);
  }

  // Rebuild category sum chips when a category row is opened
  document.addEventListener("click", (e) => {
    const toggle = e.target.closest(".cat-toggle");
    if (!toggle) return;
    const row = toggle.closest(".cat-row");
    if (!row) return;
    const key = row.dataset.cat;
    requestAnimationFrame(() => {
      const widget = document.querySelector(
        `.tag-sum[data-scope="category"][data-cat="${CSS.escape(key || "")}"]`
      );
      if (widget) updateTagSumWidget(widget);
    });
  });

  initTagSumWidgets();

  APP.ui = APP.ui || ui;
  APP.ui.refreshTagPickers = refreshTagPickers;
  APP.ui.initTagSumWidgets = initTagSumWidgets;
})();
