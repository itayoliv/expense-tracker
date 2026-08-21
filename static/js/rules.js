/* Rules manager modal */

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
      btn.addEventListener("click", () => {
        const rule = managedRules.find((r) => String(r.id) === btn.dataset.id);
        if (rule) openRuleEditor(rule);
      });
    });
    rulesList.querySelectorAll(".btn-rule-delete").forEach((btn) => {
      btn.addEventListener("click", () => deleteRule(btn.dataset.id));
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

  function renderRulesList() {
    if (!rulesList) return;
    const rows = filteredRules();
    if (!managedRules.length) {
      rulesList.innerHTML = `<div class="categories-empty">${
        (APP.strings && APP.strings.no_rules) || "No rules yet."
      }</div>`;
      return;
    }
    if (!rows.length) {
      rulesList.innerHTML = `<div class="categories-empty">${
        (APP.strings && APP.strings.no_rules) || "No rules yet."
      }</div>`;
      return;
    }
    rulesList.innerHTML = rows
      .map((rule) => {
        const title = rule.display_name || rule.pattern || "";
        const extra =
          rule.pattern && title !== rule.pattern
            ? ` · ${escapeHtml(rule.pattern)}`
            : "";
        return `
      <div class="cat-manage-row" data-id="${rule.id}">
        <span class="cat-manage-swatch" style="background:${rule.category_color || "#9CA3AF"}"></span>
        <div class="cat-manage-meta">
          <span class="cat-manage-name">${escapeHtml(title)}</span>
          <span class="cat-manage-kind">${escapeHtml(rule.category_name || "")}${extra}</span>
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

  bindRuleRowActions();

  if (btnManageRules) {
    btnManageRules.addEventListener("click", () => {
      managedRules = Array.isArray(APP.rules) ? [...APP.rules] : [];
      ruleFilter = "";
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
    btnRuleFormCancel.addEventListener("click", () => showRuleList());
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
