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
    btnNew: document.getElementById("btn-new"),
    progressWrap: document.getElementById("progress-wrap"),
    buildProgress: document.getElementById("build-progress"),
    progressLabel: document.getElementById("progress-label"),
    resultWrap: document.getElementById("result-wrap"),

    scanProgressWrap: document.getElementById("scan-progress-wrap"),
    scanProgress: document.getElementById("scan-progress"),
    scanProgressLabel: document.getElementById("scan-progress-label"),

    dragOverlay: document.getElementById("drag-overlay"),
    dragOverlayIcon: document.getElementById("drag-overlay-icon"),
    dragOverlayText: document.getElementById("drag-overlay-text"),
    toastRoot: document.getElementById("toast-root"),
    btnTheme: document.getElementById("btn-theme"),
    iconTheme: document.getElementById("icon-theme"),

    btnSettings: document.getElementById("btn-settings"),
    settingsModal: document.getElementById("settings-modal"),
    btnSettingsClose: document.getElementById("btn-settings-close"),
    btnSettingsClose2: document.getElementById("btn-settings-close-2"),
    selLanguage: document.getElementById("sel-language"),
    selThemePref: document.getElementById("sel-theme-pref"),
  };

  let files = [];
  let destinationFolder = null;
  let filenameTouched = false;
  let estimateSeq = 0;
  let isBusy = false; // mirrors Api._busy — a scan or a build is running

  // ------------------------------------------------------------------
  // i18n — translations come from Python (api.get_settings()), which reads
  // the same frontend/i18n/*.json this app.js would otherwise have to
  // fetch() itself. Fetching a local file works fine for <img>/<link> under
  // pywebview's file:// origin, but explicit fetch()/XHR of another local
  // file is exactly the kind of thing that varies across pywebview's
  // different underlying browser engines (WebView2/QtWebEngine/WebKitGTK/
  // WKWebView) — routing it through the already-proven pywebview.api
  // bridge sidesteps that entirely, and Python needs these same strings
  // for its own error messages anyway, so there's one catalog, not two.
  // ------------------------------------------------------------------

  let translations = {};
  let settingsMeta = { language: "en", language_pref: "auto", theme_pref: "auto" };

  function t(key, params) {
    let node = translations;
    for (const part of key.split(".")) {
      node = node && typeof node === "object" ? node[part] : undefined;
    }
    let text = typeof node === "string" ? node : key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        text = text.split(`{${k}}`).join(v);
      }
    }
    return text;
  }

  function applyTranslations() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      el.title = t(el.getAttribute("data-i18n-title"));
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.getAttribute("data-i18n-placeholder"));
    });
  }

  function populateLanguageOptions(languages, currentPref) {
    els.selLanguage.querySelectorAll('option:not([value="auto"])').forEach((o) => o.remove());
    for (const lang of languages || []) {
      const opt = document.createElement("option");
      opt.value = lang.code;
      opt.textContent = lang.name; // each language's own name for itself — never translated
      els.selLanguage.appendChild(opt);
    }
    els.selLanguage.value = currentPref;
  }

  async function loadAndApplySettings() {
    const s = await window.pywebview.api.get_settings();
    settingsMeta = s;
    translations = s.translations || {};
    document.documentElement.lang = s.language;
    applyTranslations();
    populateLanguageOptions(s.available_languages, s.language_pref);
    els.selThemePref.value = s.theme_pref;
    applyTheme(s.theme_pref);
    if (!filenameTouched && files.length === 0) {
      els.inputFilename.value = t("pdfOptions.filename.default");
    }
  }

  // ------------------------------------------------------------------
  // Theme — persisted on the Python side (see settings.py), not via
  // localStorage: pywebview defaults to "private mode" for the underlying
  // webview engine (WebView2 IsInPrivateModeEnabled, WebKitGTK's ephemeral
  // WebContext, etc. — confirmed by reading every webview/platforms/*.py
  // backend), which does not persist localStorage to disk at all. "auto"
  // is resolved to light/dark here, in JS, via matchMedia — the one part
  // of this that's genuinely more reliable from the browser side than
  // asking the OS directly from Python.
  // ------------------------------------------------------------------

  function resolveThemeMode(pref) {
    if (pref === "light" || pref === "dark") return pref;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme(pref) {
    const mode = resolveThemeMode(pref);
    document.documentElement.classList.toggle("dark", mode === "dark");
    els.iconTheme.setAttribute("icon", mode === "dark" ? "sun" : "moon");
  }

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
    // "destructive" variant — "success" is our own addition (see the
    // .uk-alert-success rule in index.html's <style>).
    const modifier = tone === "error" ? " uk-alert-destructive" : tone === "success" ? " uk-alert-success" : "";
    const el = document.createElement("div");
    el.className = `uk-alert shadow-lg${modifier}`;
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
    const parentName = parts.length > 1 ? parts[parts.length - 2] : t("pdfOptions.filename.default");
    els.inputFilename.value = (parentName || t("pdfOptions.filename.default")).trim();
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
        <span class="drag-handle text-muted-foreground" title="${escapeHtml(t("fileList.dragToReorder"))}">
          <uk-icon icon="grip-vertical" size="16"></uk-icon>
        </span>
        ${thumbHtml}
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-medium">${escapeHtml(f.name)}</div>
          <div class="truncate text-xs text-muted-foreground">${f.width}×${f.height} · ${f.size_human}</div>
        </div>
        <button class="uk-btn uk-btn-ghost uk-btn-icon shrink-0 btn-remove" type="button" title="${escapeHtml(t("fileList.remove"))}">
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
    // By the time a files payload lands, any scan in progress is done —
    // whatever started it (a button click or a drop we didn't initiate).
    hideScanProgress();
    setBusyUI(false);
  }

  function showScanProgress() {
    els.scanProgressWrap.classList.remove("hidden");
    els.scanProgressWrap.classList.add("flex");
  }

  function hideScanProgress() {
    els.scanProgressWrap.classList.add("hidden");
    els.scanProgressWrap.classList.remove("flex");
  }

  // Disables every entry point that could start a second, overlapping scan
  // or build — the pick buttons, the drop zone, and the build button — and
  // shows it visually. `Api._busy` is the actual guard (JS can't stop the
  // OS from delivering a drop event), this just keeps the UI honest about it.
  function setBusyUI(busy) {
    isBusy = busy;
    els.btnPickFolder.disabled = busy;
    els.btnPickFiles.disabled = busy;
    els.btnSort.disabled = busy;
    els.btnClear.disabled = busy;
    els.btnNew.disabled = busy;
    els.dropzone.classList.toggle("opacity-50", busy);
    els.dropzone.classList.toggle("pointer-events-none", busy);
    updateBuildAvailability();
  }

  // Called by Python after a native drag & drop lands (see api.notify_files_dropped).
  window.pdfMerger = window.pdfMerger || {};
  window.pdfMerger.onFilesUpdated = (payload) => applyFilesPayload(payload);
  window.pdfMerger.onBuildProgress = (done, total) => {
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    els.buildProgress.value = pct;
    els.progressLabel.textContent = t("progress.buildLabel", { done, total });
  };
  window.pdfMerger.onScanProgress = (done, total) => {
    if (total <= 0) return;
    showScanProgress();
    setBusyUI(true); // fires for drop-triggered scans too, not just button clicks
    els.scanProgress.value = Math.round((done / total) * 100);
    els.scanProgressLabel.textContent = t("progress.scanLabel", { done, total });
  };
  window.pdfMerger.onBusyRejected = () => {
    toast(t("toast.busyRejected"), "error");
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
      els.estimateValue.textContent = t("estimate.notAvailable");
      els.estimateNote.textContent = res && res.error ? res.error : "";
      return;
    }
    els.estimateValue.textContent = res.estimated_human;
    const pagesNote = t(res.total === 1 ? "estimate.page" : "estimate.pages", { count: res.total });
    const sampleNote = res.is_partial_sample
      ? t("estimate.partialSample", { sampled: res.sampled, total: res.total })
      : "";
    const losslessNote = els.chkOriginalQuality.checked ? t("estimate.losslessNote") : "";
    els.estimateNote.textContent = pagesNote + sampleNote + losslessNote;
  }

  // ------------------------------------------------------------------
  // Build availability / build action
  // ------------------------------------------------------------------

  function updateBuildAvailability() {
    els.btnBuild.disabled =
      isBusy || files.length === 0 || !destinationFolder || !els.inputFilename.value.trim();
  }

  async function handleBuild() {
    const name = els.inputFilename.value.trim() || t("pdfOptions.filename.default");
    const sep = destinationFolder.includes("\\") && !destinationFolder.includes("/") ? "\\" : "/";
    const outputPath = destinationFolder.replace(/[/\\]+$/, "") + sep + name.replace(/\.pdf$/i, "") + ".pdf";

    setBusyUI(true);
    els.resultWrap.classList.add("hidden");
    els.progressWrap.classList.remove("hidden");
    els.progressWrap.classList.add("flex");
    els.buildProgress.value = 0;
    els.progressLabel.textContent = t("progress.buildLabel", { done: 0, total: files.length });

    const res = await window.pywebview.api.build(currentSettings(), outputPath);

    els.progressWrap.classList.add("hidden");
    els.progressWrap.classList.remove("flex");
    setBusyUI(false);

    if (!res || !res.success) {
      toast((res && res.error) || t("toast.buildFailed"), "error");
      return;
    }

    els.resultWrap.classList.remove("hidden");
    els.resultWrap.classList.add("flex");
    const pagesText = t(res.pages === 1 ? "result.page" : "result.pages", { count: res.pages });
    els.resultWrap.innerHTML = `
      <uk-icon icon="check-circle-2" class="text-primary shrink-0"></uk-icon>
      <div class="min-w-0 flex-1">
        <div class="truncate font-medium">${escapeHtml(res.output_path)}</div>
        <div class="text-xs text-muted-foreground">${escapeHtml(pagesText)} · ${res.size_human}</div>
      </div>
      <button id="btn-open-folder" class="uk-btn uk-btn-ghost uk-btn-icon" title="${escapeHtml(t("result.openFolderTitle"))}" type="button">
        <uk-icon icon="folder-open" size="16"></uk-icon>
      </button>
      <button id="btn-open-file" class="uk-btn uk-btn-ghost uk-btn-icon" title="${escapeHtml(t("result.openFileTitle"))}" type="button">
        <uk-icon icon="external-link" size="16"></uk-icon>
      </button>
    `;
    document.getElementById("btn-open-folder").addEventListener("click", () => window.pywebview.api.reveal_output(res.output_path));
    document.getElementById("btn-open-file").addEventListener("click", () => window.pywebview.api.open_output(res.output_path));

    toast(t("toast.buildSuccess"), "success");
  }

  // Resets everything for a new merge job: file list, destination,
  // filename, and any leftover result/progress from the previous one.
  // Deliberately leaves the PDF settings (format/DPI/quality/…) alone —
  // reusing them for the next batch is the common case.
  async function handleNew() {
    applyFilesPayload(await window.pywebview.api.clear_files());
    destinationFolder = null;
    els.inputDestination.value = "";
    els.inputFilename.value = t("pdfOptions.filename.default");
    filenameTouched = false;
    els.resultWrap.classList.add("hidden");
    els.resultWrap.classList.remove("flex");
    hideScanProgress();
    els.progressWrap.classList.add("hidden");
    els.progressWrap.classList.remove("flex");
    updateBuildAvailability();
  }

  // ------------------------------------------------------------------
  // Preferences modal
  // ------------------------------------------------------------------

  function openSettingsModal() {
    els.settingsModal.classList.remove("hidden");
    els.settingsModal.classList.add("flex");
  }

  function closeSettingsModal() {
    els.settingsModal.classList.add("hidden");
    els.settingsModal.classList.remove("flex");
  }

  els.btnSettings.addEventListener("click", openSettingsModal);
  els.btnSettingsClose.addEventListener("click", closeSettingsModal);
  els.btnSettingsClose2.addEventListener("click", closeSettingsModal);
  els.settingsModal.addEventListener("click", (e) => {
    if (e.target === els.settingsModal) closeSettingsModal();
  });

  els.selLanguage.addEventListener("change", async () => {
    const s = await window.pywebview.api.set_language(els.selLanguage.value);
    settingsMeta = s;
    translations = s.translations || {};
    document.documentElement.lang = s.language;
    applyTranslations();
    renderFiles(); // refresh dynamic per-row tooltips (drag handle / remove) in the new language
    scheduleEstimate();
  });

  els.selThemePref.addEventListener("change", async () => {
    const s = await window.pywebview.api.set_theme(els.selThemePref.value);
    settingsMeta = s;
    applyTheme(s.theme_pref);
  });

  // ------------------------------------------------------------------
  // Wiring
  // ------------------------------------------------------------------

  els.btnPickFolder.addEventListener("click", async () => {
    setBusyUI(true);
    const res = await window.pywebview.api.pick_folder();
    applyFilesPayload(res);
    // Name the PDF after the picked folder — takes priority over
    // applyFilesPayload's generic "guess it from the first file" heuristic,
    // since here we know the folder for certain.
    if (res && res.folder_name && !filenameTouched) {
      els.inputFilename.value = res.folder_name;
      updateBuildAvailability();
    }
  });
  els.btnPickFiles.addEventListener("click", async () => {
    setBusyUI(true);
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
  els.btnNew.addEventListener("click", handleNew);

  // Visual-only drag feedback (actual file paths are resolved on the Python
  // side via DOMEventHandler, see main.py — the browser sandbox otherwise
  // hides real filesystem paths from JS). When busy, the overlay still
  // shows — just to say the drop won't be accepted — because Python's own
  // guard in notify_files_dropped() is what actually rejects it either way.
  ["dragenter", "dragover"].forEach((evt) =>
    window.addEventListener(evt, (e) => {
      e.preventDefault();
      els.dragOverlay.classList.remove("hidden");
      els.dragOverlay.classList.add("flex");
      els.dragOverlayIcon.setAttribute("icon", isBusy ? "hourglass" : "download");
      els.dragOverlayText.textContent = isBusy ? t("dragOverlay.busy") : t("dragOverlay.ready");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    window.addEventListener(evt, (e) => {
      if (evt === "drop") e.preventDefault();
      els.dragOverlay.classList.add("hidden");
      els.dragOverlay.classList.remove("flex");
    })
  );

  // Quick header toggle: flips between an explicit light/dark choice. The
  // Preferences modal's own select is where "automatic (system)" lives.
  els.btnTheme.addEventListener("click", async () => {
    const next = resolveThemeMode(settingsMeta.theme_pref) === "dark" ? "light" : "dark";
    const s = await window.pywebview.api.set_theme(next);
    settingsMeta = s;
    els.selThemePref.value = s.theme_pref;
    applyTheme(s.theme_pref);
  });

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------

  async function init() {
    updateSettingsAvailability();
    await loadAndApplySettings();
    applyFilesPayload(await window.pywebview.api.get_state());
  }

  if (window.pywebview && window.pywebview.api) {
    init();
  } else {
    window.addEventListener("pywebviewready", init);
  }
})();
