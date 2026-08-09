"""
api.py
------
The bridge exposed to the frontend as `pywebview.api.*`. Keeps all state
(the working file list) and delegates every actual image/PDF operation to
pdf_builder.py. Every public method returns plain JSON-serializable data and
never lets an exception cross into JS unhandled.
"""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

import webview

import pdf_builder as pb
import settings as app_settings

# Shown next to each language in the picker — always in that language's own
# name (an "autonym"), regardless of the UI's current language, so someone
# can find their language even if the UI is currently showing the wrong one.
LANGUAGE_NAMES = {
    "en": "English",
    "it": "Italiano",
    "es": "Español",
    "fr": "Français",
    "zh": "中文",
    "hi": "हिन्दी",
}


def _to_js_literal(value) -> str:
    """JSON that is also always safe to splice straight into a JS expression.

    json.dumps happily emits raw U+2028/U+2029, which are valid JSON but are
    line terminators inside a JS string literal — evaluate_js() runs the text
    as a script, not through JSON.parse, so an image filename containing one
    could otherwise break the generated call.
    """
    return json.dumps(value).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


class Api:
    def __init__(self, base_dir: Path | None = None):
        self.window: webview.Window | None = None
        self._files: list[str] = []          # ordered, de-duplicated absolute paths
        self._thumb_cache: dict[str, str | None] = {}
        # True while a scan (folder/files pick, or a drop) or a build is
        # running. JS disables its own buttons before it even calls in, but
        # a drop is triggered from Python's own DOM handler (main.py), with
        # no JS click to hang a "disable the buttons" moment off of — this
        # flag is what actually rejects a second overlapping drop/pick/build,
        # and is also what tells JS (via the same onScanProgress signal) to
        # disable everything for a drop-triggered scan too.
        self._busy = False
        # base_dir mirrors main.py's frozen-aware BASE_DIR (PyInstaller
        # unpacks bundled data to sys._MEIPASS at runtime, not next to this
        # .py file) — passed in from main.py so this one bit of path logic
        # has a single source of truth instead of being duplicated here.
        self._base_dir = base_dir or Path(__file__).resolve().parent
        self._translations_cache: dict[str, dict] = {}
        self._lang = app_settings.resolve_language(app_settings.load())

    def set_window(self, window: webview.Window) -> None:
        # pywebview reflectively walks every attribute of the js_api object
        # (this Api instance) to auto-expose its methods to JS — see
        # inject_pywebview() in webview/util.py. Without this marker it
        # happily recurses from `self.window` into `window.native` (the raw
        # WinForms/WebView2 control) and, on Windows, gets stuck in infinite
        # recursion on System.Drawing.Rectangle.Empty — reflected as
        # "AccessibilityObject.Bounds.Empty.Empty.Empty..." in the console,
        # and can freeze the UI thread since re-injection runs on every
        # WebView2 NavigationCompleted event (which a window move can
        # spuriously retrigger). Confirmed upstream bug, still open:
        # github.com/r0x0r/pywebview/issues/1815. `_serializable = False` is
        # pywebview's own documented escape hatch for exactly this case.
        window._serializable = False
        self.window = window

    # ------------------------------------------------------------------
    # Settings / i18n
    # ------------------------------------------------------------------

    def _load_translations(self, lang: str) -> dict:
        if lang not in self._translations_cache:
            path = self._base_dir / "frontend" / "i18n" / f"{lang}.json"
            try:
                self._translations_cache[lang] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._translations_cache[lang] = {}
        return self._translations_cache[lang]

    def _t(self, dotted_key: str, **params) -> str:
        """Backend-side translation for the handful of user-facing strings
        Python itself generates (file-dialog filters, build errors) — the
        same JSON catalogs the frontend uses, so there's exactly one set of
        translated strings, not two."""
        node = self._load_translations(self._lang)
        for part in dotted_key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        text = node if isinstance(node, str) else dotted_key
        for key, value in params.items():
            text = text.replace("{" + key + "}", str(value))
        return text

    def get_settings(self) -> dict:
        prefs = app_settings.load()
        self._lang = app_settings.resolve_language(prefs)
        return {
            "language_pref": prefs["language"],
            "language": self._lang,
            "theme_pref": prefs["theme"],
            "translations": self._load_translations(self._lang),
            "available_languages": [
                {"code": code, "name": name} for code, name in LANGUAGE_NAMES.items()
            ],
        }

    def set_language(self, lang: str) -> dict:
        prefs = app_settings.load()
        prefs["language"] = lang if lang == "auto" or lang in app_settings.SUPPORTED_LANGUAGES else "auto"
        app_settings.save(prefs)
        return self.get_settings()

    def set_theme(self, theme: str) -> dict:
        prefs = app_settings.load()
        prefs["theme"] = theme if theme in app_settings.THEMES else "auto"
        app_settings.save(prefs)
        return self.get_settings()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_scan_progress(self, done: int, total: int) -> None:
        if self.window is not None:
            self.window.evaluate_js(f"window.pdfMerger && window.pdfMerger.onScanProgress({done},{total})")

    def _emit_busy_rejected(self) -> None:
        if self.window is not None:
            self.window.evaluate_js("window.pdfMerger && window.pdfMerger.onBusyRejected && window.pdfMerger.onBusyRejected()")

    def _files_payload(self, report_progress: bool = False) -> dict:
        """Reads size/dimensions and builds a thumbnail for every file in the
        list. Thumbnails are cached by path, so this is only slow the first
        time a given image is seen — but that first pass, for a folder with
        hundreds of images, is exactly what report_progress narrates.
        """
        items = []
        total = len(self._files)
        if report_progress and total:
            self._emit_scan_progress(0, total)
        for i, raw_path in enumerate(self._files):
            path = Path(raw_path)
            info = pb.get_image_info(path)
            if info is not None:
                d = info.to_dict()
                if raw_path not in self._thumb_cache:
                    self._thumb_cache[raw_path] = pb.make_thumbnail_data_uri(path)
                d["thumb"] = self._thumb_cache[raw_path]
                items.append(d)
            if report_progress:
                self._emit_scan_progress(i + 1, total)
        return {"files": items}

    def _add_paths(self, paths) -> int:
        added = 0
        for p in paths:
            expanded = pb.expand_dropped_path(Path(p))
            for img_path in expanded:
                key = str(img_path.resolve())
                if key not in self._files:
                    self._files.append(key)
                    added += 1
        return added

    def notify_files_dropped(self, raw_paths: list[str]) -> None:
        """Called from the Python-side DOM drop handler in main.py (not from JS).

        JS can dim the dropzone all it wants, but it can't actually stop the
        OS from delivering another drop while one is still being processed —
        this check is the real guard.
        """
        if self._busy:
            self._emit_busy_rejected()
            return
        self._busy = True
        try:
            self._add_paths(raw_paths)
            if self.window is not None:
                payload = _to_js_literal(self._files_payload(report_progress=True))
                self.window.evaluate_js(f"window.pdfMerger && window.pdfMerger.onFilesUpdated({payload})")
        finally:
            self._busy = False

    # ------------------------------------------------------------------
    # File list management (called from JS)
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        return self._files_payload()

    def pick_folder(self) -> dict:
        if self._busy:
            return self._files_payload()
        self._busy = True
        try:
            result = self.window.create_file_dialog(webview.FileDialog.FOLDER)
            if not result:
                return self._files_payload()
            folder = result if isinstance(result, str) else result[0]
            self._add_paths([folder])
            payload = self._files_payload(report_progress=True)
            # So JS can name the PDF after the folder without having to
            # guess it back out of the first file's path.
            payload["folder_name"] = Path(folder).name
            return payload
        finally:
            self._busy = False

    def pick_files(self) -> dict:
        if self._busy:
            return self._files_payload()
        self._busy = True
        try:
            exts = ";".join(f"*{e}" for e in sorted(pb.SUPPORTED_EXTENSIONS))
            result = self.window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=True,
                file_types=(
                    f"{self._t('dialogs.imagesFilter')} ({exts})",
                    f"{self._t('dialogs.allFilesFilter')} (*.*)",
                ),
            )
            if not result:
                return self._files_payload()
            self._add_paths(result)
            return self._files_payload(report_progress=True)
        finally:
            self._busy = False

    def remove_file(self, path: str) -> dict:
        self._files = [f for f in self._files if f != path]
        self._thumb_cache.pop(path, None)
        return self._files_payload()

    def clear_files(self) -> dict:
        self._files = []
        self._thumb_cache = {}
        return self._files_payload()

    def reorder_files(self, ordered_paths: list[str]) -> dict:
        known = set(self._files)
        new_order = [p for p in ordered_paths if p in known]
        # Safety net: append anything the frontend didn't know about (shouldn't happen).
        new_order += [p for p in self._files if p not in new_order]
        self._files = new_order
        return self._files_payload()

    def sort_files(self) -> dict:
        """Plain ascending sort by filename. Adding a whole folder already
        sorts this way (see pdf_builder.list_images()), but dropping/picking
        individual files keeps whatever order the OS reported them in —
        which isn't guaranteed to be sorted at all."""
        self._files.sort(key=lambda p: Path(p).name.lower())
        return self._files_payload()

    # ------------------------------------------------------------------
    # Estimate / build
    # ------------------------------------------------------------------

    def estimate(self, settings: dict) -> dict:
        if not self._files:
            return {"estimated_bytes": 0, "estimated_human": "0 B", "sampled": 0, "total": 0}
        try:
            return pb.estimate_pdf_size([Path(p) for p in self._files], settings)
        except Exception as exc:  # pragma: no cover - defensive
            return {"error": str(exc)}

    def choose_destination_folder(self) -> dict:
        """Folder picker: kept separate from the filename field, as requested."""
        result = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        if not result:
            return {"path": None}
        path = result if isinstance(result, str) else result[0]
        return {"path": path}

    def build(self, settings: dict, output_path: str) -> dict:
        if self._busy:
            return {"success": False, "error": self._t("errors.busy")}
        if not self._files:
            return {"success": False, "error": self._t("errors.noImages")}
        if not output_path:
            return {"success": False, "error": self._t("errors.noDestination")}

        def progress(done: int, total: int) -> None:
            if self.window is not None:
                self.window.evaluate_js(f"window.pdfMerger && window.pdfMerger.onBuildProgress({done},{total})")

        self._busy = True
        try:
            result = pb.build_pdf(
                [Path(p) for p in self._files],
                Path(output_path),
                settings,
                progress_cb=progress,
            )
            return {"success": True, **result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        finally:
            self._busy = False

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def open_output(self, path: str) -> dict:
        return self._open_path(path)

    def reveal_output(self, path: str) -> dict:
        return self._open_path(str(Path(path).parent))

    @staticmethod
    def _open_path(path: str) -> dict:
        try:
            system = platform.system()
            if system == "Windows":
                import os

                os.startfile(path)  # type: ignore[attr-defined]
            elif system == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
