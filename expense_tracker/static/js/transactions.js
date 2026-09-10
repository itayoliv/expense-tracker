/* Transactions: shared helpers used by edit / split / banner scripts */

(function () {
  const APP = (window.APP = window.APP || {});
  const ui = (APP.ui = APP.ui || {});
  const openModal = ui.openModal || function () {};
  const escapeHtml = ui.escapeHtml || ((t) => String(t || ""));
  const str = (key, fallback) =>
    (ui.str && ui.str(key, fallback)) ||
    (APP.strings && APP.strings[key]) ||
    fallback;

  const txn = (APP.transactions = APP.transactions || {});

  function allTags() {
    return Array.isArray(APP.tags) ? APP.tags : [];
  }

  function selectedTagIds(picker) {
    if (!picker) return [];
    return String(picker.dataset.selected || "")
      .split(",")
      .map((s) => Number(s.trim()))
      .filter((id) => Number.isFinite(id) && id > 0);
  }

  function renderTagPickerChips(picker) {
    if (!picker) return;
    const wrap = picker.querySelector(".tag-picker-chips");
    if (!wrap) return;

    const selected = new Set(selectedTagIds(picker).map(String));
    const tags = allTags();
    const chosen = tags.filter((tag) => selected.has(String(tag.id)));
    const remaining = tags.filter((tag) => !selected.has(String(tag.id)));

    const chipsHtml = chosen
      .map(
        (tag) => `
      <span class="tag-chip tag-chip-selected" data-tag-id="${tag.id}" style="--tag-color: ${escapeHtml(tag.color || "#6B7280")}">
        ${escapeHtml(tag.name || "")}
        <button type="button" class="tag-chip-remove" data-tag-id="${tag.id}" title="${escapeHtml(str("remove_tag", "Remove tag"))}" aria-label="${escapeHtml(str("remove_tag", "Remove tag"))}">×</button>
      </span>`
      )
      .join("");

    const addHtml = remaining.length
      ? `<div class="tag-add-wrap">
           <button type="button" class="tag-add-btn" title="${escapeHtml(str("add_tag_choice", "Add tag"))}" aria-label="${escapeHtml(str("add_tag_choice", "Add tag"))}">+</button>
           <select class="tag-add-select" hidden>
             <option value="">${escapeHtml(str("choose_tag", "Choose tag"))}</option>
             ${remaining
               .map(
                 (tag) =>
                   `<option value="${tag.id}">${escapeHtml(tag.name || "")}</option>`
               )
               .join("")}
           </select>
         </div>`
      : tags.length
        ? ""
        : `<span class="tag-sum-empty">${escapeHtml(str("no_tags", "No tags yet."))}</span>`;

    wrap.innerHTML = chipsHtml + addHtml;
    bindTagPickerControls(picker);
  }

  function setTagPickerSelection(picker, tagIds) {
    if (!picker) return;
    const ids = [
      ...new Set(
        (tagIds || [])
          .map((id) => Number(id))
          .filter((id) => Number.isFinite(id) && id > 0)
          .map(String)
      ),
    ];
    picker.dataset.selected = ids.join(",");
    renderTagPickerChips(picker);
  }

  function bindTagPickerControls(picker) {
    if (!picker) return;
    picker.querySelectorAll(".tag-chip-remove").forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const removeId = String(btn.dataset.tagId || "");
        const next = selectedTagIds(picker).filter(
          (id) => String(id) !== removeId
        );
        setTagPickerSelection(picker, next);
        picker.dispatchEvent(new Event("change", { bubbles: true }));
      });
    });

    const addBtn = picker.querySelector(".tag-add-btn");
    const select = picker.querySelector(".tag-add-select");
    if (addBtn && select && addBtn.dataset.bound !== "1") {
      addBtn.dataset.bound = "1";
      select.dataset.bound = "1";
      addBtn.addEventListener("click", (e) => {
        e.preventDefault();
        addBtn.hidden = true;
        select.hidden = false;
        select.focus();
      });
      select.addEventListener("change", () => {
        const id = Number(select.value);
        if (!Number.isFinite(id) || id <= 0) return;
        const next = [...selectedTagIds(picker), id];
        setTagPickerSelection(picker, next);
        picker.dispatchEvent(new Event("change", { bubbles: true }));
      });
      select.addEventListener("blur", () => {
        window.setTimeout(() => {
          if (!select.value) {
            select.hidden = true;
            addBtn.hidden = false;
          }
        }, 120);
      });
    }
  }

  function bindTagPickers(root) {
    const scope = root || document;
    const pickers = scope.classList?.contains("tag-picker")
      ? [scope]
      : Array.from(scope.querySelectorAll(".tag-picker"));
    pickers.forEach((picker) => {
      // Re-render from data-selected (or keep current selection)
      setTagPickerSelection(picker, selectedTagIds(picker));
    });
  }

  function categoryOptionsHtml(selected) {
    const unsorted = str("unsorted", "Unsorted");
    const cats = Array.isArray(APP.categories) ? APP.categories : [];
    const opts = [`<option value="">${unsorted}</option>`];
    cats.forEach((cat) => {
      const name =
        APP.lang === "he"
          ? cat.name_he || cat.name || cat.name_en
          : cat.name_en || cat.name || cat.name_he;
      const sel = String(cat.id) === String(selected || "") ? " selected" : "";
      opts.push(`<option value="${cat.id}"${sel}>${name}</option>`);
    });
    return opts.join("");
  }

  function round2(n) {
    return Math.round((Number(n) || 0) * 100) / 100;
  }

  txn.str = str;
  txn.openModal = openModal;
  txn.selectedTagIds = selectedTagIds;
  txn.setTagPickerSelection = setTagPickerSelection;
  txn.bindTagPickers = bindTagPickers;
  txn.renderTagPickerChips = renderTagPickerChips;
  txn.categoryOptionsHtml = categoryOptionsHtml;
  txn.round2 = round2;
  txn.txnModal = document.getElementById("txn-modal");
  txn.txnForm = document.getElementById("txn-form");
  txn.btnSplitToggle = document.getElementById("btn-split-toggle");

  ui.bindTagPickers = bindTagPickers;
  bindTagPickers();
})();
