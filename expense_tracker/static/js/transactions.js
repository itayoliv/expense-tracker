/* Transactions: add/edit/delete, split, unsorted quick-categorize, GPT sort */

(function () {
  const APP = window.APP || {};
  const ui = APP.ui || {};
  const openModal = ui.openModal || function () {};
  const str = (key, fallback) =>
    (ui.str && ui.str(key, fallback)) ||
    (APP.strings && APP.strings[key]) ||
    fallback;

  const txnModal = document.getElementById("txn-modal");
  const txnForm = document.getElementById("txn-form");
  const singleFields = document.getElementById("txn-single-fields");
  const splitPanel = document.getElementById("txn-split-panel");
  const splitRows = document.getElementById("txn-split-rows");
  const btnSplitToggle = document.getElementById("btn-split-toggle");
  const btnSplitAdd = document.getElementById("btn-split-add");
  const splitTotalEl = document.getElementById("txn-split-total");
  const splitRemainingEl = document.getElementById("txn-split-remaining");
  const splitDateEl = document.getElementById("txn-split-date");

  let splitMode = false;
  let splitTargetTotal = 0;

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

  function updateSplitRemaining() {
    if (!splitRemainingEl || !splitRows) return;
    const amounts = Array.from(splitRows.querySelectorAll(".split-amount")).map(
      (el) => round2(el.value)
    );
    const used = round2(amounts.reduce((a, b) => a + b, 0));
    const remaining = round2(splitTargetTotal - used);
    const currency = str("currency", "₪");
    if (splitTotalEl) {
      splitTotalEl.textContent = `${currency}${splitTargetTotal.toFixed(2)}`;
    }
    const tmpl =
      str("split_remaining", "Remaining: {amount}") || "Remaining: {amount}";
    splitRemainingEl.textContent = tmpl.replace(
      "{amount}",
      `${currency}${remaining.toFixed(2)}`
    );
    splitRemainingEl.classList.toggle("is-ok", Math.abs(remaining) < 0.005);
    splitRemainingEl.classList.toggle("is-bad", Math.abs(remaining) >= 0.005);
  }

  function addSplitRow(initial) {
    if (!splitRows) return;
    const data = initial || {};
    const row = document.createElement("div");
    row.className = "txn-split-row";
    row.innerHTML = `
      <label>
        ${str("description", "Description")}
        <input type="text" class="split-description" required value="">
      </label>
      <label>
        ${str("amount", "Amount")}
        <input type="number" class="split-amount" min="0.01" step="0.01" required value="">
      </label>
      <label>
        ${str("category", "Category")}
        <select class="split-category">${categoryOptionsHtml(data.category_id)}</select>
      </label>
      <button type="button" class="btn ghost danger split-remove">${str(
        "split_remove_part",
        "Remove"
      )}</button>
    `;
    const desc = row.querySelector(".split-description");
    const amount = row.querySelector(".split-amount");
    if (desc) desc.value = data.description || "";
    if (amount) amount.value = data.amount != null ? data.amount : "";
    amount.addEventListener("input", updateSplitRemaining);
    row.querySelector(".split-remove").addEventListener("click", () => {
      if (splitRows.children.length <= 2) return;
      row.remove();
      updateSplitRemaining();
    });
    splitRows.appendChild(row);
    updateSplitRemaining();
  }

  function setSplitMode(on, seed) {
    splitMode = Boolean(on);
    if (singleFields) singleFields.classList.toggle("hidden", splitMode);
    if (splitPanel) splitPanel.classList.toggle("hidden", !splitMode);
    if (btnSplitToggle) {
      btnSplitToggle.textContent = splitMode
        ? str("split_unsplit", "Cancel split")
        : str("split_transaction", "Split transaction");
    }

    const descInput = document.getElementById("txn-description");
    const amountInput = document.getElementById("txn-amount");
    const dateInput = document.getElementById("txn-date");
    if (descInput) descInput.required = !splitMode;
    if (amountInput) amountInput.required = !splitMode;
    if (dateInput) dateInput.required = !splitMode;
    if (splitDateEl) splitDateEl.required = splitMode;

    if (!splitMode) {
      if (splitRows) splitRows.innerHTML = "";
      return;
    }

    splitTargetTotal = round2(
      (seed && seed.amount) ||
        document.getElementById("txn-amount").value ||
        0
    );
    if (splitDateEl) {
      splitDateEl.value =
        (seed && seed.date) ||
        document.getElementById("txn-date").value ||
        "";
    }
    if (splitRows) splitRows.innerHTML = "";
    const half = round2(splitTargetTotal / 2);
    const rest = round2(splitTargetTotal - half);
    const parentCategory = (seed && seed.category_id) || "";
    addSplitRow({
      description: (seed && seed.description) || "",
      amount: half || "",
      category_id: parentCategory,
    });
    addSplitRow({
      description: "",
      amount: rest || "",
      category_id: parentCategory,
    });
  }

  function collectSplits() {
    return Array.from(splitRows.querySelectorAll(".txn-split-row")).map((row) => ({
      description: row.querySelector(".split-description").value.trim(),
      amount: row.querySelector(".split-amount").value,
      category_id: row.querySelector(".split-category").value || null,
    }));
  }

  // Unsorted quick categorize
  document.querySelectorAll(".u-cat-select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const id = sel.dataset.txnId;
      const category_id = sel.value || null;
      if (!category_id) return;
      const res = await fetch(`/transactions/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category_id, remember_rule: true }),
      });
      if (res.ok) location.reload();
    });
  });

  const unsortedSearch = document.getElementById("unsorted-search");
  if (unsortedSearch) {
    const items = Array.from(document.querySelectorAll(".unsorted-item"));
    unsortedSearch.addEventListener("input", () => {
      const q = unsortedSearch.value.trim().toLowerCase().replace(/,/g, "");
      items.forEach((item) => {
        const hay = [
          item.dataset.date,
          item.dataset.desc,
          item.dataset.details,
          item.dataset.amount,
          item.textContent,
        ]
          .join(" ")
          .toLowerCase()
          .replace(/,/g, "");
        item.classList.toggle("hidden", Boolean(q) && !hay.includes(q));
      });
    });
  }

  const btnGptSort = document.getElementById("btn-gpt-sort");
  if (btnGptSort) {
    btnGptSort.addEventListener("click", async () => {
      const label = btnGptSort.textContent;
      btnGptSort.disabled = true;
      btnGptSort.textContent =
        (APP.strings && APP.strings.gpt_sorting) || "Sorting with ChatGPT…";
      try {
        const res = await fetch("/api/gpt/sort", { method: "POST" });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          alert(data.error || "Error");
          return;
        }
        location.reload();
      } finally {
        btnGptSort.disabled = false;
        btnGptSort.textContent = label;
      }
    });
  }

  function resetTxnForm() {
    if (txnForm) txnForm.reset();
    const idEl = document.getElementById("txn-id");
    if (idEl) idEl.value = "";
    setSplitMode(false);
    if (btnSplitToggle) btnSplitToggle.classList.add("hidden");
  }

  // Add transaction
  const btnAdd = document.getElementById("btn-add");
  if (btnAdd) {
    btnAdd.addEventListener("click", () => {
      resetTxnForm();
      const title = document.getElementById("txn-modal-title");
      if (title) title.textContent = btnAdd.textContent.trim();
      document.getElementById("remember-wrap").classList.add("hidden");
      const applyWrap = document.getElementById("apply-categorized-wrap");
      if (applyWrap) applyWrap.classList.add("hidden");
      const rememberBox = document.getElementById("txn-remember");
      if (rememberBox) rememberBox.checked = false;
      const applyBox = document.getElementById("txn-apply-categorized");
      if (applyBox) applyBox.checked = false;
      const categoryWrap = document.getElementById("txn-category-wrap");
      if (categoryWrap) categoryWrap.classList.add("hidden");
      document.getElementById("txn-category").value = "";
      document.getElementById("btn-delete").classList.add("hidden");
      const today = new Date().toISOString().slice(0, 10);
      document.getElementById("txn-date").value = today;
      document.getElementById("txn-direction").value =
        APP.view === "income" ? "credit" : "debit";
      openModal(txnModal);
    });
  }

  // Edit transaction
  document.querySelectorAll(".btn-edit").forEach((btn) => {
    btn.addEventListener("click", () => {
      let data;
      try {
        data = JSON.parse(btn.getAttribute("data-txn"));
      } catch {
        return;
      }
      setSplitMode(false);
      document.getElementById("txn-id").value = data.id;
      document.getElementById("txn-description").value = data.description || "";
      document.getElementById("txn-details").value = data.details || "";
      document.getElementById("txn-amount").value = data.amount;
      document.getElementById("txn-direction").value = data.direction || "debit";
      document.getElementById("txn-category").value = data.category_id || "";
      // Convert DD/MM/YY to YYYY-MM-DD
      let isoDate = "";
      const parts = (data.date || "").split("/");
      if (parts.length === 3) {
        let y = parseInt(parts[2], 10);
        if (y < 100) y += 2000;
        const m = parts[1].padStart(2, "0");
        const d = parts[0].padStart(2, "0");
        isoDate = `${y}-${m}-${d}`;
        document.getElementById("txn-date").value = isoDate;
      }
      document.getElementById("remember-wrap").classList.remove("hidden");
      const applyWrap = document.getElementById("apply-categorized-wrap");
      if (applyWrap) applyWrap.classList.remove("hidden");
      const rememberBox = document.getElementById("txn-remember");
      if (rememberBox) rememberBox.checked = false;
      const applyBox = document.getElementById("txn-apply-categorized");
      if (applyBox) applyBox.checked = false;
      const categoryWrap = document.getElementById("txn-category-wrap");
      if (categoryWrap) categoryWrap.classList.remove("hidden");
      document.getElementById("btn-delete").classList.remove("hidden");
      if (btnSplitToggle) {
        btnSplitToggle.classList.remove("hidden");
        btnSplitToggle.dataset.seed = JSON.stringify({
          description: data.description || "",
          amount: data.amount,
          category_id: data.category_id || "",
          date: isoDate,
        });
      }
      const title = document.getElementById("txn-modal-title");
      if (title) title.textContent = (APP.strings && APP.strings.save) || "Save";
      openModal(txnModal);
    });
  });

  if (btnSplitToggle) {
    btnSplitToggle.addEventListener("click", () => {
      if (splitMode) {
        setSplitMode(false);
        return;
      }
      let seed = {};
      try {
        seed = JSON.parse(btnSplitToggle.dataset.seed || "{}");
      } catch {
        seed = {};
      }
      seed.description =
        document.getElementById("txn-description").value || seed.description;
      seed.amount =
        document.getElementById("txn-amount").value || seed.amount;
      seed.category_id =
        document.getElementById("txn-category").value || seed.category_id;
      seed.date = document.getElementById("txn-date").value || seed.date;
      setSplitMode(true, seed);
    });
  }

  if (btnSplitAdd) {
    btnSplitAdd.addEventListener("click", () => {
      const parentCategory =
        document.getElementById("txn-category")?.value ||
        (splitRows.querySelector(".split-category") || {}).value ||
        "";
      addSplitRow({ amount: "", category_id: parentCategory });
    });
  }

  // Save add/edit/split
  if (txnForm) {
    txnForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = document.getElementById("txn-id").value;
      const remember = document.getElementById("txn-remember").checked;
      const applyAll = document.getElementById("txn-apply-categorized")
        ? document.getElementById("txn-apply-categorized").checked
        : false;

      let body;
      if (id && splitMode) {
        const splits = collectSplits();
        const used = round2(
          splits.reduce((a, s) => a + round2(s.amount), 0)
        );
        if (Math.abs(used - splitTargetTotal) >= 0.005) {
          alert(
            str("split_hint", "Split amounts must add up to the total.")
          );
          return;
        }
        body = {
          splits,
          date: splitDateEl ? splitDateEl.value : undefined,
          remember_rule: remember,
          apply_to_categorized: applyAll,
        };
      } else {
        body = {
          description: document.getElementById("txn-description").value,
          details: document.getElementById("txn-details").value,
          date: document.getElementById("txn-date").value,
          amount: document.getElementById("txn-amount").value,
          direction: document.getElementById("txn-direction").value,
          category_id: document.getElementById("txn-category").value || null,
          remember_rule: remember,
          apply_to_categorized: applyAll,
        };
      }

      let res;
      if (id) {
        res = await fetch(`/transactions/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } else {
        res = await fetch("/transactions", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
          },
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

  const btnDelete = document.getElementById("btn-delete");
  if (btnDelete) {
    btnDelete.addEventListener("click", async () => {
      const id = document.getElementById("txn-id").value;
      if (!id) return;
      const msg =
        (APP.strings && APP.strings.confirm_delete) ||
        "Delete this transaction?";
      if (!confirm(msg)) return;
      const res = await fetch(`/transactions/${id}`, { method: "DELETE" });
      if (res.ok) location.reload();
    });
  }
})();
