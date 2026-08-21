/* Settings modal actions */

(function () {
  const APP = window.APP || {};
  const ui = APP.ui || {};
  const openModal = ui.openModal || function () {};

  const settingsModal = document.getElementById("settings-modal");
  const btnSettings = document.getElementById("btn-settings");
  const btnSeedCategories = document.getElementById("btn-seed-categories");
  const btnClearTransactions = document.getElementById("btn-clear-transactions");
  const btnResetRules = document.getElementById("btn-reset-rules");
  const settingShowPie = document.getElementById("setting-show-pie");

  if (btnSettings) {
    btnSettings.addEventListener("click", () => openModal(settingsModal));
  }

  if (btnSeedCategories) {
    btnSeedCategories.addEventListener("click", async () => {
      btnSeedCategories.disabled = true;
      try {
        const res = await fetch("/api/settings/seed", { method: "POST" });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          alert(data.error || "Error");
          return;
        }
        if (data.categories_added) {
          location.reload();
          return;
        }
        alert(
          data.message ||
            (APP.strings && APP.strings.seed_categories_none) ||
            "Already seeded"
        );
      } finally {
        btnSeedCategories.disabled = false;
      }
    });
  }

  if (btnResetRules) {
    btnResetRules.addEventListener("click", async () => {
      const msg =
        (APP.strings && APP.strings.reset_rules_confirm) ||
        "Delete all learned rules? Future imports will be unsorted until you assign categories again.";
      if (!confirm(msg)) return;
      btnResetRules.disabled = true;
      try {
        const res = await fetch("/api/settings/reset-rules", { method: "POST" });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          alert(data.error || "Error");
          return;
        }
        location.reload();
      } finally {
        btnResetRules.disabled = false;
      }
    });
  }

  if (btnClearTransactions) {
    btnClearTransactions.addEventListener("click", async () => {
      const msg =
        (APP.strings && APP.strings.clear_transactions_confirm) ||
        "Delete all transactions? This cannot be undone.";
      if (!confirm(msg)) return;
      btnClearTransactions.disabled = true;
      try {
        const res = await fetch("/api/settings/clear-transactions", {
          method: "POST",
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          alert(data.error || "Error");
          return;
        }
        location.reload();
      } finally {
        btnClearTransactions.disabled = false;
      }
    });
  }

  const btnSaveOpenaiKey = document.getElementById("btn-save-openai-key");
  const btnClearOpenaiKey = document.getElementById("btn-clear-openai-key");
  const openaiKeyInput = document.getElementById("openai-key");
  const openaiKeyStatus = document.getElementById("openai-key-status");

  if (btnSaveOpenaiKey && openaiKeyInput) {
    btnSaveOpenaiKey.addEventListener("click", async () => {
      const api_key = openaiKeyInput.value.trim();
      if (!api_key) {
        alert("API key is required");
        return;
      }
      btnSaveOpenaiKey.disabled = true;
      try {
        const res = await fetch("/api/settings/openai-key", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ api_key }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          alert(data.error || "Error");
          return;
        }
        openaiKeyInput.value = "";
        if (openaiKeyStatus) {
          openaiKeyStatus.textContent =
            data.message ||
            (APP.strings && APP.strings.openai_key_saved) ||
            "API key saved.";
        }
      } finally {
        btnSaveOpenaiKey.disabled = false;
      }
    });
  }

  if (btnClearOpenaiKey) {
    btnClearOpenaiKey.addEventListener("click", async () => {
      btnClearOpenaiKey.disabled = true;
      try {
        const res = await fetch("/api/settings/openai-key", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ clear: true }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          alert(data.error || "Error");
          return;
        }
        if (openaiKeyInput) openaiKeyInput.value = "";
        if (openaiKeyStatus) {
          openaiKeyStatus.textContent =
            data.message ||
            (APP.strings && APP.strings.openai_key_cleared) ||
            "API key removed.";
        }
      } finally {
        btnClearOpenaiKey.disabled = false;
      }
    });
  }

  if (settingShowPie) {
    settingShowPie.addEventListener("change", async () => {
      settingShowPie.disabled = true;
      try {
        const res = await fetch("/api/settings/pie", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ show_pie: settingShowPie.checked }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          settingShowPie.checked = !settingShowPie.checked;
          alert(data.error || "Error");
          return;
        }
        location.reload();
      } finally {
        settingShowPie.disabled = false;
      }
    });
  }
})();
