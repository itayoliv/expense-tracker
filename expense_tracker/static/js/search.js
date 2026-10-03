/* Dashboard transaction search: suggestions while typing, apply with the form */

(function () {
  const APP = window.APP || {};
  const input = document.getElementById("txn-search");
  const list = document.getElementById("txn-search-suggestions");
  const form = document.getElementById("period-form");
  if (!input || !list || !form) return;

  const fieldLabels = {
    description: (APP.strings && APP.strings.search_field_description) || "Description",
    details: (APP.strings && APP.strings.search_field_details) || "Details",
    custom_description:
      (APP.strings && APP.strings.search_field_custom_description) ||
      "Custom description",
    tag: (APP.strings && APP.strings.search_field_tag) || "Tag",
  };

  let timer = 0;
  let requestId = 0;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function hideSuggestions() {
    list.classList.add("hidden");
    list.innerHTML = "";
  }

  function showSuggestions(options) {
    list.innerHTML = "";
    if (!options.length) {
      hideSuggestions();
      return;
    }
    options.forEach((option) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "txn-search-option";
      button.setAttribute("role", "option");
      const label = fieldLabels[option.field] || option.field || "";
      button.innerHTML =
        `<span class="txn-search-text">${escapeHtml(option.text)}</span>` +
        `<span class="txn-search-field">${escapeHtml(label)}</span>`;
      button.addEventListener("mousedown", (event) => {
        event.preventDefault();
      });
      button.addEventListener("click", () => {
        input.value = option.text || "";
        hideSuggestions();
        if (form.requestSubmit) form.requestSubmit();
        else form.submit();
      });
      list.appendChild(button);
    });
    list.classList.remove("hidden");
  }

  async function fetchSuggestions() {
    const query = input.value.trim();
    if (!query) {
      hideSuggestions();
      return;
    }
    const current = ++requestId;
    const params = new URLSearchParams();
    params.set("q", query);
    params.set("view", (APP.view) || "expenses");
    const dateFrom = document.getElementById("date_from");
    const dateTo = document.getElementById("date_to");
    if (dateFrom && dateFrom.value) params.set("date_from", dateFrom.value);
    if (dateTo && dateTo.value) params.set("date_to", dateTo.value);
    try {
      const res = await fetch(`/api/txn-search?${params.toString()}`, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!res.ok || current !== requestId) return;
      const data = await res.json();
      if (current !== requestId) return;
      showSuggestions(Array.isArray(data.options) ? data.options : []);
    } catch {
      if (current === requestId) hideSuggestions();
    }
  }

  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(fetchSuggestions, 200);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideSuggestions();
  });

  document.addEventListener("click", (event) => {
    if (!form.contains(event.target)) hideSuggestions();
  });
})();
