/* Transactions: add/edit modal (fields, tags picker, save, delete) */

(function () {
  const APP = window.APP || {};
  const ui = APP.ui || {};
  const txn = APP.transactions || {};
  const openModal = txn.openModal || ui.openModal || function () {};
  const selectedTagIds = txn.selectedTagIds || (() => []);
  const setTagPickerSelection = txn.setTagPickerSelection || function () {};
  const bindTagPickers = txn.bindTagPickers || function () {};
  const round2 = txn.round2 || ((n) => Math.round((Number(n) || 0) * 100) / 100);
  const str = txn.str || ((key, fallback) => fallback);

  const txnModal = txn.txnModal || document.getElementById("txn-modal");
  const txnForm = txn.txnForm || document.getElementById("txn-form");
  const btnSplitToggle = txn.btnSplitToggle || document.getElementById("btn-split-toggle");
  const closeModal = ui.closeModal || function (el) {
    if (el && el.open) el.close();
  };

  async function refreshAfterTxnChange() {
    closeModal(txnModal);
    if (ui.refreshDashboardBackground) {
      const ok = await ui.refreshDashboardBackground();
      if (ok) return;
    }
    location.reload();
  }

  function setTxnOriginalFieldsReadonly(readonly) {
    const descInput = document.getElementById("txn-description");
    const detailsInput = document.getElementById("txn-details");
    const customWrap = document.getElementById("txn-custom-description-wrap");
    const customInput = document.getElementById("txn-custom-description");
    if (descInput) {
      descInput.readOnly = Boolean(readonly);
      descInput.required = !readonly;
    }
    if (detailsInput) detailsInput.readOnly = Boolean(readonly);
    if (customWrap) customWrap.classList.toggle("hidden", !readonly);
    if (customInput && !readonly) customInput.value = "";
  }

  function syncIgnoreReasonVisibility() {
    const ignoredBox = document.getElementById("txn-ignored");
    const reasonWrap = document.getElementById("txn-ignore-reason-wrap");
    const reasonInput = document.getElementById("txn-ignore-reason");
    const checked = Boolean(ignoredBox && ignoredBox.checked);
    if (reasonWrap) reasonWrap.classList.toggle("hidden", !checked);
    if (reasonInput && !checked) reasonInput.value = "";
  }

  function setIgnoreFields(visible, ignored, reason) {
    const ignoreWrap = document.getElementById("txn-ignore-wrap");
    const ignoredBox = document.getElementById("txn-ignored");
    const reasonInput = document.getElementById("txn-ignore-reason");
    if (ignoreWrap) ignoreWrap.classList.toggle("hidden", !visible);
    if (ignoredBox) ignoredBox.checked = Boolean(ignored);
    if (reasonInput) reasonInput.value = reason || "";
    syncIgnoreReasonVisibility();
  }

  function resetTxnForm() {
    if (txnForm) txnForm.reset();
    const idEl = document.getElementById("txn-id");
    if (idEl) idEl.value = "";
    if (txn.setSplitMode) txn.setSplitMode(false);
    if (btnSplitToggle) btnSplitToggle.classList.add("hidden");
    setTxnOriginalFieldsReadonly(false);
    setIgnoreFields(false, false, "");
    setTagPickerSelection(document.getElementById("txn-tag-picker"), []);
  }

  function bindTransactionEdits() {
    document.querySelectorAll(".btn-edit").forEach((btn) => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => {
        let data;
        try {
          data = JSON.parse(btn.getAttribute("data-txn"));
        } catch {
          return;
        }
        if (txn.setSplitMode) txn.setSplitMode(false);
        document.getElementById("txn-id").value = data.id;
        document.getElementById("txn-description").value = data.description || "";
        document.getElementById("txn-details").value = data.details || "";
        const customInput = document.getElementById("txn-custom-description");
        if (customInput) customInput.value = data.custom_description || "";
        setTxnOriginalFieldsReadonly(true);
        document.getElementById("txn-amount").value = data.amount;
        document.getElementById("txn-direction").value = data.direction || "debit";
        document.getElementById("txn-category").value = data.category_id || "";
        setTagPickerSelection(
          document.getElementById("txn-tag-picker"),
          data.tag_ids || []
        );
        bindTagPickers(document.getElementById("txn-tag-picker"));
        setIgnoreFields(true, Boolean(data.ignored), data.ignore_reason || "");
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
          const alreadySplit = Boolean(data.split_group);
          btnSplitToggle.classList.toggle("hidden", alreadySplit);
          btnSplitToggle.dataset.seed = JSON.stringify({
            description: data.description || "",
            custom_description: data.custom_description || "",
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
      bindTagPickers(document.getElementById("txn-tag-picker"));
      openModal(txnModal);
    });
  }

  // Edit transaction
  bindTransactionEdits();

  const ignoredBox = document.getElementById("txn-ignored");
  if (ignoredBox && ignoredBox.dataset.bound !== "1") {
    ignoredBox.dataset.bound = "1";
    ignoredBox.addEventListener("change", syncIgnoreReasonVisibility);
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
      const splitMode = txn.isSplitMode ? txn.isSplitMode() : false;

      let body;
      if (id && splitMode) {
        const splits = txn.collectSplits ? txn.collectSplits() : [];
        const splitTargetTotal = txn.getSplitTargetTotal
          ? txn.getSplitTargetTotal()
          : 0;
        const used = round2(
          splits.reduce((a, s) => a + round2(s.amount), 0)
        );
        if (Math.abs(used - splitTargetTotal) >= 0.005) {
          alert(
            str("split_hint", "Split amounts must add up to the total.")
          );
          return;
        }
        const splitDateEl = txn.getSplitDateEl ? txn.getSplitDateEl() : null;
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
        if (id) {
          const ignored = document.getElementById("txn-ignored")
            ? document.getElementById("txn-ignored").checked
            : false;
          const ignoreReason = document.getElementById("txn-ignore-reason")
            ? document.getElementById("txn-ignore-reason").value.trim()
            : "";
          if (ignored && !ignoreReason) {
            alert(
              str(
                "ignore_reason_required",
                "A reason is required when ignoring a transaction."
              )
            );
            return;
          }
          body = {
            custom_description: document.getElementById("txn-custom-description")
              ? document.getElementById("txn-custom-description").value
              : "",
            date: document.getElementById("txn-date").value,
            amount: document.getElementById("txn-amount").value,
            direction: document.getElementById("txn-direction").value,
            category_id: document.getElementById("txn-category").value || null,
            tag_ids: selectedTagIds(document.getElementById("txn-tag-picker")),
            ignored,
            ignore_reason: ignoreReason,
            remember_rule: remember,
            apply_to_categorized: applyAll,
          };
        }
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
      if (res.ok) await refreshAfterTxnChange();
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
      if (res.ok) await refreshAfterTxnChange();
    });
  }

  APP.ui = APP.ui || ui;
  APP.ui.bindTransactionEdits = bindTransactionEdits;
})();
