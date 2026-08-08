// PDFImageMerger frontend logic. No framework/build step: talks to Python
// through the pywebview.api.* bridge and renders FrankenUI markup by hand.

(() => {
  "use strict";

  const els = {
    dropzone: document.getElementById("dropzone"),
    btnPickFolder: document.getElementById("btn-pick-folder"),
    btnPickFiles: document.getElementById("btn-pick-files"),
    btnSort: document.getElementById("btn-sort"),
    btnClear: document.getElementById("btn-clear"),
    fileList: document.getElementById("file-list"),
    fileCount: document.getElementById("file-count"),
    emptyHint: document.getElementById("empty-hint"),

    chkOriginalQuality: document.getElementById("chk-original-quality"),
    formatField: document.getElementById("format-field"),
    selFormat: document.getElementById("sel-format"),
    orientationField: document.getElementById("orientation-field"),
    orientationGroup: document.getElementById("orientation-group"),
    resolutionQualityField: document.getElementById("resolution-quality-field"),
    selDpi: document.getElementById("sel-dpi"),
    selQuality: document.getElementById("sel-quality"),

    inputFilename: document.getElementById("input-filename"),
    inputDestination: document.getElementById("input-destination"),
    btnChooseDest: document.getElementById("btn-choose-dest"),

    estimateValue: document.getElementById("estimate-value"),
    estimateNote: document.getElementById("estimate-note"),

    btnBuild: document.getElementById("btn-build"),
    progressWrap: document.getElementById("progress-wrap"),
    buildProgress: document.getElementById("build-progress"),
    progressLabel: document.getElementById("progress-label"),
    resultWrap: document.getElementById("result-wrap"),

    scanProgressWrap: document.getElementById("scan-progress-wrap"),
    scanProgress: document.getElementById("scan-progress"),
    scanProgressLabel: document.getElementById("scan-progress-label"),

    dragOverlay: document.getElementById("drag-overlay"),
    toastRoot: document.getElementById("toast-root"),
    btnTheme: document.getElementById("btn-theme"),
    iconTheme: document.getElementById("icon-theme"),
  };

  let files = [];
  let destinationFolder = null;
  let filenameTouched = false;
  let estimateSeq = 0;

  // ------------------------------------------------------------------
  // Small helpers
  // ------------------------------------------------------------------

  function debounce(fn, wait) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), wait);
    };
  }

  function toast(message, tone = "default") {
    // Franken UI's alert component only ships a default look plus a
    // "destructive" variant, so that's the only branch we need here.
    const el = document.createElement("div");
    el.className = `uk-alert shadow-lg${tone === "error" ? " uk-alert-destructive" : ""}`;
    el.innerHTML = `<p>${escapeHtml(message)}</p>`;
    els.toastRoot.appendChild(el);
    setTimeout(() => el.remove(), 4500);
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function currentSettings() {
    const originalQuality = els.chkOriginalQuality.checked;
    return {
      page_format: originalQuality ? "auto" : els.selFormat.value,
      orientation: getOrientation(),
      dpi: parseInt(els.selDpi.value, 10),
      quality: els.selQuality.value,
      original_quality: originalQuality,
    };
  }

  function getOrientation() {
    const active = els.orientationGroup.querySelector('[aria-pressed="true"]');
    return active ? active.dataset.value : "portrait";
  }

  function updateSettingsAvailability() {
    const originalQuality = els.chkOriginalQuality.checked;

    els.selFormat.disabled = originalQuality;
    els.formatField.classList.toggle("opacity-50", originalQuality);
    els.selDpi.disabled = originalQuality;
    els.selQuality.disabled = originalQuality;
    els.resolutionQualityField.classList.toggle("opacity-50", originalQuality);

    const isAuto = originalQuality || els.selFormat.value === "auto";
    els.orientationField.classList.toggle("opacity-50", isAuto);
    els.orientationGroup.querySelectorAll("button").forEach((b) => (b.disabled = isAuto));
  }

  function suggestFilenameFromFiles() {
    if (filenameTouched || files.length === 0) return;
    const first = files[0].path;
    const parts = first.split(/[\\/]/);
    const parentName = parts.length > 1 ? parts[parts.length - 2] : "documento";
    els.inputFilename.value = (parentName || "documento").trim();
  }

  // ------------------------------------------------------------------
  // File list rendering
  // ------------------------------------------------------------------

  function renderFiles() {
    els.fileCount.textContent = files.length;
    els.emptyHint.classList.toggle("hidden", files.length > 0);
    els.fileList.innerHTML = "";

    for (const f of files) {
      const li = document.createElement("li");
      li.className =
        "file-row uk-sortable-item flex items-center gap-3 rounded-md border border-border p-2 bg-background";
      li.dataset.path = f.path;

      const thumbHtml = f.thumb
        ? `<img src="${f.thumb}" class="h-10 w-10 shrink-0 rounded border border-border" />`
        : `<div class="flex h-10 w-10 shrink-0 items-center justify-center rounded border border-border text-muted-foreground"><uk-icon icon="image" size="16"></uk-icon></div>`;

      li.innerHTML = `
        <span class="drag-handle text-muted-foreground" title="Trascina per riordinare">
          <uk-icon icon="grip-vertical" size="16"></uk-icon>
        </span>
        ${thumbHtml}
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-medium">${escapeHtml(f.name)}</div>
          <div class="truncate text-xs text-muted-foreground">${f.width}×${f.height} · ${f.size_human}</div>
        </div>
        <button class="uk-btn uk-btn-ghost uk-btn-icon shrink-0 btn-remove" type="button" title="Rimuovi">
          <uk-icon icon="x" size="16"></uk-icon>
        </button>
      `;

      li.querySelector(".btn-remove").addEventListener("click", async (e) => {
        e.stopPropagation();
        const res = await window.pywebview.api.remove_file(f.path);
        applyFilesPayload(res);
      });

      els.fileList.appendChild(li);
    }

    updateBuildAvailability();
  }

  function applyFilesPayload(payload) {
    if (!payload) return;
    files = payload.files || [];
    renderFiles();
    suggestFilenameFromFiles();
    scheduleEstimate();
    // By the time a files payload lands, any scan in progress is done.
    hideScanProgress();
    setScanningButtonsDisabled(false);
  }

  function showScanProgress() {
    els.scanProgressWrap.classList.remove("hidden");
    els.scanProgressWrap.classList.add("flex");
  }

  function hideScanProgress() {
    els.scanProgressWrap.classList.add("hidden");
    els.scanProgressWrap.classList.remove("flex");
  }

  function setScanningButtonsDisabled(disabled) {
    els.btnPickFolder.disabled = disabled;
    els.btnPickFiles.disabled = disabled;
    els.btnClear.disabled = disabled;
  }

  // Called by Python after a native drag & drop lands (see api.notify_files_dropped).
  window.pdfMerger = window.pdfMerger || {};
  window.pdfMerger.onFilesUpdated = (payload) => applyFilesPayload(payload);
  window.pdfMerger.onBuildProgress = (done, total) => {
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    els.buildProgress.value = pct;
    els.progressLabel.textContent = `Elaborazione immagine ${done} di ${total}…`;
  };
  window.pdfMerger.onScanProgress = (done, total) => {
    if (total <= 0) return;
    showScanProgress();
    els.scanProgress.value = Math.round((done / total) * 100);
    els.scanProgressLabel.textContent = `Analisi immagine ${done} di ${total}…`;
  };

  // ------------------------------------------------------------------
  // Sortable reorder (Franken UI's uk-sortable fires "stop" when a drag ends)
  // ------------------------------------------------------------------

  els.fileList.addEventListener("stop", async () => {
    const order = Array.from(els.fileList.querySelectorAll(".file-row")).map((li) => li.dataset.path);
    const res = await window.pywebview.api.reorder_files(order);
    files = res.files || [];
    // No full re-render needed (DOM order is already correct); just refresh availability/estimate.
    updateBuildAvailability();
    scheduleEstimate();
  });

  // ------------------------------------------------------------------
  // Estimate
  // ------------------------------------------------------------------

  const scheduleEstimate = debounce(runEstimate, 350);

  async function runEstimate() {
    if (files.length === 0) {
      els.estimateValue.textContent = "—";
      els.estimateNote.textContent = "";
      return;
    }
    const seq = ++estimateSeq;
    els.estimateValue.textContent = "…";
    const res = await window.pywebview.api.estimate(currentSettings());
    if (seq !== estimateSeq) return; // a newer request superseded this one
    if (!res || res.error) {
      els.estimateValue.textContent = "n/d";
      els.estimateNote.textContent = res && res.error ? res.error : "";
      return;
    }
    els.estimateValue.textContent = res.estimated_human;
    const pagesNote = `${res.total} pagin${res.total === 1 ? "a" : "e"}`;
    const sampleNote = res.is_partial_sample
      ? ` (stima su ${res.sampled} di ${res.total} immagini campionate)`
      : "";
    const losslessNote = els.chkOriginalQuality.checked ? " · qualità originale, senza compressione" : "";
    els.estimateNote.textContent = pagesNote + sampleNote + losslessNote;
  }

  // ------------------------------------------------------------------
  // Build availability / build action
  // ------------------------------------------------------------------

  function updateBuildAvailability() {
    els.btnBuild.disabled = files.length === 0 || !destinationFolder || !els.inputFilename.value.trim();
  }

  async function handleBuild() {
    const name = els.inputFilename.value.trim() || "documento";
    const sep = destinationFolder.includes("\\") && !destinationFolder.includes("/") ? "\\" : "/";
    const outputPath = destinationFolder.replace(/[/\\]+$/, "") + sep + name.replace(/\.pdf$/i, "") + ".pdf";

    els.btnBuild.disabled = true;
    els.resultWrap.classList.add("hidden");
    els.progressWrap.classList.remove("hidden");
    els.progressWrap.classList.add("flex");
    els.buildProgress.value = 0;
    els.progressLabel.textContent = `Elaborazione immagine 0 di ${files.length}…`;

    const res = await window.pywebview.api.build(currentSettings(), outputPath);

    els.progressWrap.classList.add("hidden");
    els.progressWrap.classList.remove("flex");

    if (!res || !res.success) {
      toast((res && res.error) || "Creazione del PDF non riuscita.", "error");
      updateBuildAvailability();
      return;
    }

    els.resultWrap.classList.remove("hidden");
    els.resultWrap.classList.add("flex");
    els.resultWrap.innerHTML = `
      <uk-icon icon="check-circle-2" class="text-primary shrink-0"></uk-icon>
      <div class="min-w-0 flex-1">
        <div class="truncate font-medium">${escapeHtml(res.output_path)}</div>
        <div class="text-xs text-muted-foreground">${res.pages} pagine · ${res.size_human}</div>
      </div>
      <button id="btn-open-folder" class="uk-btn uk-btn-ghost uk-btn-icon" title="Apri cartella" type="button">
        <uk-icon icon="folder-open" size="16"></uk-icon>
      </button>
      <button id="btn-open-file" class="uk-btn uk-btn-ghost uk-btn-icon" title="Apri PDF" type="button">
        <uk-icon icon="external-link" size="16"></uk-icon>
      </button>
    `;
    document.getElementById("btn-open-folder").addEventListener("click", () => window.pywebview.api.reveal_output(res.output_path));
    document.getElementById("btn-open-file").addEventListener("click", () => window.pywebview.api.open_output(res.output_path));

    toast("PDF creato correttamente.");
    updateBuildAvailability();
  }

  // ------------------------------------------------------------------
  // Wiring
  // ------------------------------------------------------------------

  els.btnPickFolder.addEventListener("click", async () => {
    setScanningButtonsDisabled(true);
    applyFilesPayload(await window.pywebview.api.pick_folder());
  });
  els.btnPickFiles.addEventListener("click", async () => {
    setScanningButtonsDisabled(true);
    applyFilesPayload(await window.pywebview.api.pick_files());
  });
  els.btnSort.addEventListener("click", async () => applyFilesPayload(await window.pywebview.api.sort_files()));
  els.btnClear.addEventListener("click", async () => applyFilesPayload(await window.pywebview.api.clear_files()));

  els.selFormat.addEventListener("change", () => {
    updateSettingsAvailability();
    scheduleEstimate();
  });
  els.selDpi.addEventListener("change", scheduleEstimate);
  els.selQuality.addEventListener("change", scheduleEstimate);
  els.chkOriginalQuality.addEventListener("change", () => {
    updateSettingsAvailability();
    scheduleEstimate();
  });

  els.orientationGroup.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      els.orientationGroup.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
      btn.setAttribute("aria-pressed", "true");
      scheduleEstimate();
    });
  });

  els.inputFilename.addEventListener("input", () => {
    filenameTouched = true;
    updateBuildAvailability();
  });

  els.btnChooseDest.addEventListener("click", async () => {
    const res = await window.pywebview.api.choose_destination_folder();
    if (res && res.path) {
      destinationFolder = res.path;
      els.inputDestination.value = res.path;
      updateBuildAvailability();
    }
  });

  els.btnBuild.addEventListener("click", handleBuild);

  // Visual-only drag feedback (actual file paths are resolved on the Python
  // side via DOMEventHandler, see main.py — the browser sandbox otherwise
  // hides real filesystem paths from JS).
  ["dragenter", "dragover"].forEach((evt) =>
    window.addEventListener(evt, (e) => {
      e.preventDefault();
      els.dragOverlay.classList.remove("hidden");
      els.dragOverlay.classList.add("flex");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    window.addEventListener(evt, (e) => {
      if (evt === "drop") e.preventDefault();
      els.dragOverlay.classList.add("hidden");
      els.dragOverlay.classList.remove("flex");
    })
  );

  // Theme toggle (persisted, mirrors Franken UI's own convention).
  function applyTheme(mode) {
    document.documentElement.classList.toggle("dark", mode === "dark");
    els.iconTheme.setAttribute("icon", mode === "dark" ? "sun" : "moon");
    localStorage.setItem("pdfmerger-theme", mode);
  }
  els.btnTheme.addEventListener("click", () => {
    const next = document.documentElement.classList.contains("dark") ? "light" : "dark";
    applyTheme(next);
  });
  applyTheme(
    localStorage.getItem("pdfmerger-theme") ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
  );

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------

  function init() {
    updateSettingsAvailability();
    window.pywebview.api.get_state().then(applyFilesPayload);
  }

  if (window.pywebview && window.pywebview.api) {
    init();
  } else {
    window.addEventListener("pywebviewready", init);
  }
})();
