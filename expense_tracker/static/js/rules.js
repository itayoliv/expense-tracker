/* Rules manager modal — grouped by category */

(function () {
  const APP = window.APP || {};
  const ui = APP.ui || {};
  const openModal = ui.openModal || function () {};
  const escapeHtml = ui.escapeHtml || ((t) => String(t || ""));
  const displayName = ui.displayName || ((c) => (c && (c.name || c.name_en)) || "");

  const rulesModal = document.getElementById("rules-modal");
  const ruleListPanel = document.getElementById("rule-list-panel");
  const ruleForm = document.getElementById("rule-form");
  const rulesList = document.getElementById("rules-list");
  const btnManageRules = document.getElementById("btn-manage-rules");
  const btnAddRule = document.getElementById("btn-add-rule");
  const btnRuleFormCancel = document.getElementById("btn-rule-form-cancel");
  const rulesSearch = document.getElementById("rules-search");
  const ruleCategorySelect = document.getElementById("rule-category");
  let managedRules = Array.isArray(APP.rules) ? [...APP.rules] : [];
  let ruleFilter = "";
  const expandedGroups = new Set();

  function showRuleList() {
    if (ruleListPanel) ruleListPanel.classList.remove("hidden");
    if (ruleForm) ruleForm.classList.add("hidden");
  }

  function showRuleForm() {
    if (ruleListPanel) ruleListPanel.classList.add("hidden");
    if (ruleForm) ruleForm.classList.remove("hidden");
  }

  function populateRuleCategories() {
    if (!ruleCategorySelect) return;
    const cats = Array.isArray(APP.categories) ? APP.categories : [];
    const current = ruleCategorySelect.value;
    ruleCategorySelect.innerHTML = `<option value="">${
      (APP.strings && APP.strings.choose_category) || "Choose category"
    }</option>`;
    cats.forEach((cat) => {
      const opt = document.createElement("option");
      opt.value = String(cat.id);
      opt.textContent = displayName(cat);
      ruleCategorySelect.appendChild(opt);
    });
    if (current) ruleCategorySelect.value = current;
  }

  function bindRuleRowActions() {
    if (!rulesList) return;
    rulesList.querySelectorAll(".btn-rule-edit").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const rule = managedRules.find((r) => String(r.id) === btn.dataset.id);
        if (rule) openRuleEditor(rule);
      });
    });
    rulesList.querySelectorAll(".btn-rule-delete").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteRule(btn.dataset.id);
      });
    });
    rulesList.querySelectorAll(".rule-group-header").forEach((btn) => {
      btn.addEventListener("click", () => {
        const groupKey = btn.dataset.groupKey || "";
        const group = btn.closest(".rule-group");
        if (!group) return;
        const open = !group.classList.contains("open");
        group.classList.toggle("open", open);
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) expandedGroups.add(groupKey);
        else expandedGroups.delete(groupKey);
      });
    });
  }

  function filteredRules() {
    const q = ruleFilter.trim().toLowerCase();
    if (!q) return managedRules;
    return managedRules.filter((r) => {
      const hay = [r.display_name, r.name, r.pattern, r.category_name]
        .map((v) => String(v || "").toLowerCase())
        .join(" ");
      return hay.includes(q);
    });
  }

  function groupRules(rows) {
    const groups = new Map();
    rows.forEach((rule) => {
      const key = rule.category_id != null ? String(rule.category_id) : "__none__";
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          name:
            rule.category_name ||
            (APP.strings && APP.strings.unsorted) ||
            "Unsorted",
          color: rule.category_color || "#9CA3AF",
          rules: [],
        });
      }
      groups.get(key).rules.push(rule);
    });

    const list = Array.from(groups.values());
    list.forEach((g) => {
      g.rules.sort((a, b) => {
        const pa = Number(b.priority) || 0;
        const pb = Number(a.priority) || 0;
        if (pa !== pb) return pa - pb;
        return String(a.display_name || a.pattern || "").localeCompare(
          String(b.display_name || b.pattern || ""),
          undefined,
          { sensitivity: "base" }
        );
      });
    });
    list.sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: "base" })
    );
    return list;
  }

  function ruleRowHtml(rule) {
    const title = rule.display_name || rule.pattern || "";
    const extra =
      rule.pattern && title !== rule.pattern
        ? `<span class="cat-manage-kind">${escapeHtml(rule.pattern)}</span>`
        : "";
    return `
      <div class="cat-manage-row rule-row" data-id="${rule.id}">
        <div class="cat-manage-meta">
          <span class="cat-manage-name">${escapeHtml(title)}</span>
          ${extra}
        </div>
        <div class="cat-manage-actions">
          <button type="button" class="btn ghost btn-rule-edit" data-id="${rule.id}">${
            (APP.strings && APP.strings.edit) || "Edit"
          }</button>
          <button type="button" class="btn ghost danger btn-rule-delete" data-id="${rule.id}">${
            (APP.strings && APP.strings.delete) || "Delete"
          }</button>
        </div>
      </div>`;
  }

  function renderRulesList() {
    if (!rulesList) return;
    if (!managedRules.length) {
      rulesList.innerHTML = `<div class="categories-empty">${
        (APP.strings && APP.strings.no_rules) || "No rules yet."
      }</div>`;
      return;
    }
    const rows = filteredRules();
    if (!rows.length) {
      rulesList.innerHTML = `<div class="categories-empty">${
        (APP.strings && APP.strings.no_rules) || "No rules yet."
      }</div>`;
      return;
    }

    const searching = Boolean(ruleFilter.trim());
    const groups = groupRules(rows);
    const countLabel =
      (APP.strings && APP.strings.rules_count) || "{n} rules";

    rulesList.innerHTML = groups
      .map((group) => {
        const forceOpen = searching || expandedGroups.has(group.key);
        const countText = countLabel.replace("{n}", String(group.rules.length));
        return `
      <div class="rule-group${forceOpen ? " open" : ""}" data-group-key="${escapeHtml(group.key)}">
        <button type="button" class="rule-group-header" data-group-key="${escapeHtml(group.key)}" aria-expanded="${forceOpen ? "true" : "false"}">
          <span class="chevron">▸</span>
          <span class="cat-manage-swatch" style="background:${group.color}"></span>
          <span class="rule-group-name">${escapeHtml(group.name)}</span>
          <span class="rule-group-count">${escapeHtml(countText)}</span>
        </button>
        <div class="rule-group-body">
          ${group.rules.map(ruleRowHtml).join("")}
        </div>
      </div>`;
      })
      .join("");
    bindRuleRowActions();
  }

  function openRuleEditor(rule) {
    const title = document.getElementById("rule-modal-title");
    populateRuleCategories();
    if (rule) {
      if (title) {
        title.textContent = (APP.strings && APP.strings.edit_rule) || "Edit rule";
      }
      document.getElementById("rule-id").value = rule.id;
      document.getElementById("rule-name").value = rule.name || "";
      document.getElementById("rule-pattern").value = rule.pattern || "";
      document.getElementById("rule-category").value = String(rule.category_id || "");
      document.getElementById("rule-priority").value =
        rule.priority != null ? rule.priority : 100;
    } else {
      if (title) {
        title.textContent = (APP.strings && APP.strings.add_rule) || "Add rule";
      }
      if (ruleForm) ruleForm.reset();
      document.getElementById("rule-id").value = "";
      document.getElementById("rule-priority").value = 100;
    }
    showRuleForm();
  }

  async function refreshManagedRules() {
    try {
      const res = await fetch("/api/rules");
      const data = await res.json().catch(() => ({}));
      if (res.ok && Array.isArray(data.rules)) {
        managedRules = data.rules;
        APP.rules = managedRules;
        renderRulesList();
      }
    } catch {
      // Keep the already-rendered list if the API is unavailable.
    }
  }

  async function deleteRule(id) {
    const msg =
      (APP.strings && APP.strings.confirm_delete_rule) || "Delete this rule?";
    if (!confirm(msg)) return;
    const res = await fetch(`/api/rules/${id}`, { method: "DELETE" });
    if (res.ok) {
      managedRules = managedRules.filter((r) => String(r.id) !== String(id));
      APP.rules = managedRules;
      renderRulesList();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(err.error || "Error");
    }
  }

  if (btnManageRules) {
    btnManageRules.addEventListener("click", () => {
      managedRules = Array.isArray(APP.rules) ? [...APP.rules] : [];
      ruleFilter = "";
      expandedGroups.clear();
      if (rulesSearch) rulesSearch.value = "";
      showRuleList();
      renderRulesList();
      openModal(rulesModal);
      refreshManagedRules();
    });
  }

  if (btnAddRule) {
    btnAddRule.addEventListener("click", () => openRuleEditor(null));
  }

  if (btnRuleFormCancel) {
    btnRuleFormCancel.addEventListener("click", () => {
      showRuleList();
      renderRulesList();
    });
  }

  if (rulesSearch) {
    rulesSearch.addEventListener("input", () => {
      ruleFilter = rulesSearch.value || "";
      renderRulesList();
    });
  }

  if (ruleForm) {
    ruleForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("rule-id").value;
      const body = {
        name: document.getElementById("rule-name").value.trim(),
        pattern: document.getElementById("rule-pattern").value.trim(),
        category_id: document.getElementById("rule-category").value,
        priority: document.getElementById("rule-priority").value,
      };
      let res;
      if (id) {
        res = await fetch(`/api/rules/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } else {
        res = await fetch("/api/rules", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      }
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        if (data.rule) {
          const idx = managedRules.findIndex((r) => r.id === data.rule.id);
          if (idx >= 0) managedRules[idx] = data.rule;
          else managedRules.unshift(data.rule);
          APP.rules = managedRules;
          if (data.rule.category_id != null) {
            expandedGroups.add(String(data.rule.category_id));
          }
        } else {
          await refreshManagedRules();
        }
        showRuleList();
        renderRulesList();
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.error || "Error");
      }
    });
  }
})();
