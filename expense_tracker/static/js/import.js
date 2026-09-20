/* Statement import dropzone + modal */

(function () {
  const APP = window.APP || {};
  const ui = APP.ui || {};
  const openModal = ui.openModal || function () {};

  const importModal = document.getElementById("import-modal");
  const allowedImportExt = [".csv", ".xlsx", ".xls"];

  function isAllowedImportFile(file) {
    const name = (file && file.name ? file.name : "").toLowerCase();
    return allowedImportExt.some((ext) => name.endsWith(ext));
  }

  function formatFileSize(bytes) {
    const n = Number(bytes) || 0;
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatFileDate(file) {
    const ms = file && file.lastModified ? file.lastModified : Date.now();
    try {
      return new Date(ms).toLocaleDateString(undefined, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });
    } catch {
      return "";
    }
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function bindImportDropzone(prefix) {
    const form = document.getElementById(`${prefix}-form`);
    const fileInput = document.getElementById(`${prefix}-file`);
    const dropzone = document.getElementById(`${prefix}-dropzone`);
    const idle = document.getElementById(`${prefix}-idle`);
    const selected = document.getElementById(`${prefix}-selected`);
    const fileList = document.getElementById(`${prefix}-file-list`);
    const fileListBody = document.getElementById(`${prefix}-file-list-body`);
    const resultBox = document.getElementById(`${prefix}-result`);
    const submit = document.getElementById(`${prefix}-submit`);
    if (!form || !fileInput || !dropzone) return null;

    let dragCount = 0;
    let importedOk = false;
    let submitting = false;

    function clearResult() {
      if (!resultBox) return;
      resultBox.classList.add("hidden");
      resultBox.classList.remove("is-success", "is-error", "is-mixed");
      resultBox.textContent = "";
    }

    function showResult(payload) {
      if (!resultBox) return;
      const parts = [];
      if (payload.message) parts.push(payload.message);
      if (payload.error) parts.push(payload.error);
      if (!parts.length && Array.isArray(payload.errors) && payload.errors.length) {
        parts.push(payload.errors.join("; "));
      }
      resultBox.textContent = parts.join(" ");
      resultBox.classList.remove("hidden", "is-success", "is-error", "is-mixed");
      if (payload.ok && payload.error) resultBox.classList.add("is-mixed");
      else if (payload.ok) resultBox.classList.add("is-success");
      else resultBox.classList.add("is-error");
    }

    function renderFileTable(files) {
      if (!fileList || !fileListBody) return;
      fileListBody.innerHTML = "";
      if (!files.length) {
        fileList.classList.add("hidden");
        return;
      }
      files.forEach((file) => {
        const tr = document.createElement("tr");
        tr.innerHTML =
          `<td class="col-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</td>` +
          `<td class="col-date">${escapeHtml(formatFileDate(file))}</td>` +
          `<td class="col-size">${escapeHtml(formatFileSize(file.size))}</td>`;
        fileListBody.appendChild(tr);
      });
      fileList.classList.remove("hidden");
    }

    function setSubmitIdle() {
      if (!submit) return;
      submit.disabled = !(fileInput.files && fileInput.files.length);
      submit.textContent =
        (APP.strings && APP.strings.import_file) || submit.textContent;
    }

    function reset() {
      dragCount = 0;
      submitting = false;
      importedOk = false;
      fileInput.value = "";
      dropzone.classList.remove("has-file", "is-dragging");
      if (idle) idle.classList.remove("hidden");
      if (selected) selected.classList.add("hidden");
      renderFileTable([]);
      clearResult();
      setSubmitIdle();
      if (submit) submit.disabled = true;
    }

    function showSelected(files) {
      clearResult();
      dropzone.classList.add("has-file");
      if (idle) idle.classList.add("hidden");
      if (selected) selected.classList.remove("hidden");
      renderFileTable(files);
      setSubmitIdle();
    }

    function assignFiles(fileListLike) {
      const incoming = Array.from(fileListLike || []).filter(Boolean);
      if (!incoming.length) return false;
      const allowed = incoming.filter(isAllowedImportFile);
      if (!allowed.length) {
        alert(
          (APP.strings && APP.strings.import_invalid_type) ||
            "Use a CSV or Excel file (.csv, .xlsx, .xls)."
        );
        return false;
      }
      try {
        const dt = new DataTransfer();
        allowed.forEach((file) => dt.items.add(file));
        fileInput.files = dt.files;
      } catch {
        return false;
      }
      showSelected(allowed);
      return true;
    }

    fileInput.addEventListener("change", () => {
      const files = fileInput.files ? Array.from(fileInput.files) : [];
      if (!files.length) {
        reset();
        return;
      }
      const allowed = files.filter(isAllowedImportFile);
      if (!allowed.length) {
        reset();
        alert(
          (APP.strings && APP.strings.import_invalid_type) ||
            "Use a CSV or Excel file (.csv, .xlsx, .xls)."
        );
        return;
      }
      if (allowed.length !== files.length) {
        assignFiles(allowed);
        return;
      }
      showSelected(allowed);
    });

    ["dragenter", "dragover"].forEach((type) => {
      dropzone.addEventListener(type, (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
        if (type === "dragenter") dragCount += 1;
        dropzone.classList.add("is-dragging");
      });
    });
    dropzone.addEventListener("dragleave", (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragCount -= 1;
      if (dragCount <= 0) {
        dragCount = 0;
        dropzone.classList.remove("is-dragging");
      }
    });
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      dragCount = 0;
      dropzone.classList.remove("is-dragging");
      const files = e.dataTransfer && e.dataTransfer.files;
      assignFiles(files);
    });

    form.addEventListener("dragover", (e) => {
      if (
        e.dataTransfer &&
        e.dataTransfer.types &&
        e.dataTransfer.types.includes("Files")
      ) {
        e.preventDefault();
      }
    });
    form.addEventListener("drop", (e) => {
      if (
        e.dataTransfer &&
        e.dataTransfer.files &&
        e.dataTransfer.files.length
      ) {
        e.preventDefault();
        assignFiles(e.dataTransfer.files);
      }
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (submitting) return;
      if (!fileInput.files || !fileInput.files.length) return;

      submitting = true;
      clearResult();
      if (submit) {
        submit.disabled = true;
        submit.textContent =
          (APP.strings && APP.strings.importing) || "Importing…";
      }

      try {
        const res = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        let payload = {};
        try {
          payload = await res.json();
        } catch {
          payload = {
            ok: false,
            error:
              (APP.strings && APP.strings.import_failed) ||
              "Import failed. Please try again.",
          };
        }
        showResult(payload);
        if (payload.ok) {
          importedOk = true;
          fileInput.value = "";
          dropzone.classList.remove("has-file");
          if (idle) idle.classList.remove("hidden");
          if (selected) selected.classList.add("hidden");
          if (submit) submit.disabled = true;
          // Inline (empty-state) import: keep result visible briefly, then refresh.
          if (prefix === "empty-import") {
            window.setTimeout(() => window.location.reload(), 900);
          }
        }
      } catch {
        showResult({
          ok: false,
          error:
            (APP.strings && APP.strings.import_failed) ||
            "Import failed. Please try again.",
        });
      } finally {
        submitting = false;
        if (submit) {
          submit.textContent =
            (APP.strings && APP.strings.import_file) || "Import file";
          if (!importedOk && fileInput.files && fileInput.files.length) {
            submit.disabled = false;
          }
        }
      }
    });

    reset();
    return {
      reset,
      assignFiles,
      consumeImport: () => {
        const ok = importedOk;
        importedOk = false;
        return ok;
      },
    };
  }

  const modalImport = bindImportDropzone("import");
  bindImportDropzone("empty-import");

  if (importModal) {
    importModal.addEventListener("close", () => {
      const shouldReload = modalImport && modalImport.consumeImport();
      if (modalImport) modalImport.reset();
      if (shouldReload) window.location.reload();
    });
    importModal.addEventListener("dragover", (e) => {
      if (
        e.dataTransfer &&
        e.dataTransfer.types &&
        e.dataTransfer.types.includes("Files")
      ) {
        e.preventDefault();
      }
    });
    importModal.addEventListener("drop", (e) => {
      if (
        e.dataTransfer &&
        e.dataTransfer.files &&
        e.dataTransfer.files.length
      ) {
        e.preventDefault();
        if (modalImport) modalImport.assignFiles(e.dataTransfer.files);
      }
    });
  }

  const btnImport = document.getElementById("btn-import");
  if (btnImport) {
    btnImport.addEventListener("click", () => {
      if (modalImport) modalImport.reset();
      openModal(importModal);
    });
  }
})();
