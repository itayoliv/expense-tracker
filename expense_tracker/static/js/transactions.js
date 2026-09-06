/* Transactions: shared helpers used by edit / split / banner scripts */

(function () {
  const APP = (window.APP = window.APP || {});
  const ui = (APP.ui = APP.ui || {});
  const openModal = ui.openModal || function () {};
  const str = (key, fallback) =>
    (ui.str && ui.str(key, fallback)) ||
    (APP.strings && APP.strings[key]) ||
    fallback;

  const txn = (APP.transactions = APP.transactions || {});

  function selectedTagIds(picker) {
    if (!picker) return [];
    return Array.from(picker.querySelectorAll(".tag-chip-toggle.selected"))
      .map((btn) => Number(btn.dataset.tagId))
      .filter((id) => Number.isFinite(id));
  }

  function setTagPickerSelection(picker, tagIds) {
    if (!picker) return;
    const selected = new Set((tagIds || []).map(String));
    picker.querySelectorAll(".tag-chip-toggle").forEach((btn) => {
      btn.classList.toggle("selected", selected.has(String(btn.dataset.tagId)));
    });
    picker.dataset.selected = Array.from(selected).join(",");
  }

  function bindTagPickers(root) {
    const scope = root || document;
    scope.querySelectorAll(".tag-chip-toggle").forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        btn.classList.toggle("selected");
        const picker = btn.closest(".tag-picker");
        if (picker) {
          picker.dataset.selected = selectedTagIds(picker).join(",");
          picker.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
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
  txn.categoryOptionsHtml = categoryOptionsHtml;
  txn.round2 = round2;
  txn.txnModal = document.getElementById("txn-modal");
  txn.txnForm = document.getElementById("txn-form");
  txn.btnSplitToggle = document.getElementById("btn-split-toggle");

  ui.bindTagPickers = bindTagPickers;
  bindTagPickers();
})();
