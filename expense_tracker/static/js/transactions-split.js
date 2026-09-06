/* Transactions: split modal and split-row UI */

(function () {
  const APP = window.APP || {};
  const txn = APP.transactions || {};
  const str = txn.str || ((key, fallback) => fallback);
  const categoryOptionsHtml = txn.categoryOptionsHtml || (() => "");
  const round2 = txn.round2 || ((n) => Math.round((Number(n) || 0) * 100) / 100);

  const singleFields = document.getElementById("txn-single-fields");
  const splitPanel = document.getElementById("txn-split-panel");
  const splitRows = document.getElementById("txn-split-rows");
  const btnSplitToggle = txn.btnSplitToggle || document.getElementById("btn-split-toggle");
  const btnSplitAdd = document.getElementById("btn-split-add");
  const splitTotalEl = document.getElementById("txn-split-total");
  const splitRemainingEl = document.getElementById("txn-split-remaining");
  const splitDateEl = document.getElementById("txn-split-date");
  const txnModal = txn.txnModal || document.getElementById("txn-modal");

  let splitMode = false;
  let splitTargetTotal = 0;
  let splitParentDescription = "";

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
    const parentDesc =
      data.description ||
      splitParentDescription ||
      "";
    const row = document.createElement("div");
    row.className = "txn-split-row";
    row.innerHTML = `
      <label class="split-desc-field">
        ${str("description", "Description")}
        <input type="text" class="split-description" required readonly value="">
      </label>
      <label class="split-custom-field">
        ${str("custom_description", "Custom description")}
        <input type="text" class="split-custom-description" value="">
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
    const customDesc = row.querySelector(".split-custom-description");
    const amount = row.querySelector(".split-amount");
    if (desc) desc.value = parentDesc;
    if (customDesc) customDesc.value = data.custom_description || "";
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
    if (txnModal) txnModal.classList.toggle("modal-split", splitMode);
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
      splitParentDescription = "";
      if (splitRows) splitRows.innerHTML = "";
      return;
    }

    splitParentDescription =
      (seed && seed.description) ||
      (descInput && descInput.value) ||
      "";
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
      description: splitParentDescription,
      custom_description: "",
      amount: half || "",
      category_id: parentCategory,
    });
    addSplitRow({
      description: splitParentDescription,
      custom_description: "",
      amount: rest || "",
      category_id: parentCategory,
    });
  }

  function collectSplits() {
    return Array.from(splitRows.querySelectorAll(".txn-split-row")).map((row) => ({
      description:
        splitParentDescription ||
        row.querySelector(".split-description").value.trim(),
      custom_description: (
        row.querySelector(".split-custom-description") || { value: "" }
      ).value.trim(),
      amount: row.querySelector(".split-amount").value,
      category_id: row.querySelector(".split-category").value || null,
    }));
  }

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
      addSplitRow({
        description: splitParentDescription,
        amount: "",
        category_id: parentCategory,
      });
    });
  }

  txn.setSplitMode = setSplitMode;
  txn.collectSplits = collectSplits;
  txn.isSplitMode = () => splitMode;
  txn.getSplitTargetTotal = () => splitTargetTotal;
  txn.getSplitDateEl = () => splitDateEl;
})();
