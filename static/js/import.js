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

  function bindImportDropzone(prefix) {
    const form = document.getElementById(`${prefix}-form`);
    const fileInput = document.getElementById(`${prefix}-file`);
    const dropzone = document.getElementById(`${prefix}-dropzone`);
    const idle = document.getElementById(`${prefix}-idle`);
    const selected = document.getElementById(`${prefix}-selected`);
    const fileName = document.getElementById(`${prefix}-file-name`);
    const submit = document.getElementById(`${prefix}-submit`);
    if (!form || !fileInput || !dropzone) return null;

    let dragCount = 0;

    function reset() {
      dragCount = 0;
      fileInput.value = "";
      dropzone.classList.remove("has-file", "is-dragging");
      if (idle) idle.classList.remove("hidden");
      if (selected) selected.classList.add("hidden");
      if (fileName) fileName.textContent = "";
      if (submit) {
        submit.disabled = true;
        submit.textContent =
          (APP.strings && APP.strings.import_file) || submit.textContent;
      }
    }

    function selectedLabel(files) {
      if (files.length === 1) return files[0].name;
      const tmpl =
        (APP.strings && APP.strings.files_selected) || "{n} files selected";
      return tmpl.replace("{n}", String(files.length));
    }

    function showSelected(files) {
      dropzone.classList.add("has-file");
      if (idle) idle.classList.add("hidden");
      if (selected) selected.classList.remove("hidden");
      if (fileName) fileName.textContent = selectedLabel(files);
      if (submit) submit.disabled = false;
    }

    function assignFiles(fileList) {
      const incoming = Array.from(fileList || []).filter(Boolean);
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

    form.addEventListener("submit", () => {
      if (submit) {
        submit.disabled = true;
        submit.textContent =
          (APP.strings && APP.strings.importing) || "Importing…";
      }
    });

    reset();
    return { reset, assignFiles };
  }

  const modalImport = bindImportDropzone("import");
  bindImportDropzone("empty-import");

  if (importModal) {
    importModal.addEventListener("close", () => {
      if (modalImport) modalImport.reset();
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
