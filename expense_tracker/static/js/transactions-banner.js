/* Transactions: uncategorized orange banner rows + GPT sort */

(function () {
  const APP = window.APP || {};
  const ui = APP.ui || {};
  const txn = APP.transactions || {};
  const selectedTagIds = txn.selectedTagIds || (() => []);
  const bindTagPickers = txn.bindTagPickers || function () {};

  function bindUnsortedItems() {
    document.querySelectorAll(".unsorted-item").forEach((item) => {
      if (item.dataset.bound === "1") return;
      item.dataset.bound = "1";
      const sel = item.querySelector(".u-cat-select");
      const rememberBox = item.querySelector(".u-remember");
      const applyBox = item.querySelector(".u-apply-categorized");
      const customInput = item.querySelector(".u-custom-desc-input");
      const tagPicker = item.querySelector(".u-tag-picker");
      const updateBtn = item.querySelector(".u-update-btn");
      if (!sel || !updateBtn) return;

      bindTagPickers(item);

      const initial = {
        category: sel.value || "",
        remember: Boolean(rememberBox?.checked),
        applyAll: Boolean(applyBox?.checked),
        customDescription: customInput ? customInput.value.trim() : "",
        tagIds: selectedTagIds(tagPicker).join(","),
      };

      const syncUpdateBtn = () => {
        const customDescription = customInput ? customInput.value.trim() : "";
        const dirty =
          (sel.value || "") !== initial.category ||
          Boolean(rememberBox?.checked) !== initial.remember ||
          Boolean(applyBox?.checked) !== initial.applyAll ||
          customDescription !== initial.customDescription ||
          selectedTagIds(tagPicker).join(",") !== initial.tagIds;
        updateBtn.hidden = !dirty;
      };

      sel.addEventListener("change", syncUpdateBtn);
      rememberBox?.addEventListener("change", syncUpdateBtn);
      applyBox?.addEventListener("change", syncUpdateBtn);
      customInput?.addEventListener("input", syncUpdateBtn);
      tagPicker?.addEventListener("change", syncUpdateBtn);

      updateBtn.addEventListener("click", async () => {
        const id = sel.dataset.txnId;
        const category_id = sel.value || null;
        const custom_description = customInput ? customInput.value.trim() : "";
        const customChanged = custom_description !== initial.customDescription;
        const tagsChanged = selectedTagIds(tagPicker).join(",") !== initial.tagIds;
        if (!category_id && !customChanged && !tagsChanged) return;
        updateBtn.disabled = true;
        const body = {
          custom_description,
          tag_ids: selectedTagIds(tagPicker),
          remember_rule: Boolean(rememberBox?.checked),
          apply_to_categorized: Boolean(applyBox?.checked),
        };
        if (category_id) body.category_id = category_id;
        const res = await fetch(`/transactions/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (res.ok) {
          if (ui.refreshDashboardBackground) {
            const ok = await ui.refreshDashboardBackground();
            if (ok) return;
          }
          location.reload();
          return;
        }
        updateBtn.disabled = false;
      });
    });
  }

  function bindUnsortedSearch() {
    const unsortedSearch = document.getElementById("unsorted-search");
    if (!unsortedSearch || unsortedSearch.dataset.bound === "1") return;
    unsortedSearch.dataset.bound = "1";
    unsortedSearch.addEventListener("input", () => {
      const q = unsortedSearch.value.trim().toLowerCase().replace(/,/g, "");
      document.querySelectorAll(".unsorted-item").forEach((item) => {
        const customInput = item.querySelector(".u-custom-desc-input");
        const hay = [
          item.dataset.date,
          item.dataset.desc,
          item.dataset.details,
          item.dataset.customDesc,
          customInput ? customInput.value : "",
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

  bindUnsortedItems();
  bindUnsortedSearch();

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

  APP.ui = APP.ui || ui;
  APP.ui.bindUnsortedItems = bindUnsortedItems;
  APP.ui.bindUnsortedSearch = bindUnsortedSearch;
})();
