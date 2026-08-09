"""
PDFImageMerger
==============
Entry point. Creates the pywebview window around frontend/index.html and
wires up native OS -> window drag & drop (which pywebview can only resolve
to real filesystem paths on the Python side, via DOMEventHandler).

Run with:  python main.py
"""

from __future__ import annotations

import importlib.util
import os
import platform
import sys
from pathlib import Path

# QtWebEngine (Chromium) on Linux quite often fails to get a GPU-accelerated
# rendering surface under VMs, remote sessions or some Wayland compositors —
# symptom: the window opens at the right size/title but stays blank, with
# "dma_buf"/"Compositor returned null texture" warnings in the console.
# Disabling GPU compositing fixes it; the cost is a bit more CPU for
# rendering, which is a non-issue for a small, mostly-static UI like this
# one. Only takes effect if pywebview ends up using the Qt backend, and only
# if the caller hasn't already set this themselves. Must happen before
# `import webview` pulls in the Qt/WebEngine stack.
if platform.system() == "Linux":
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

import webview
from webview.dom import DOMEventHandler

from api import Api


def _base_dir() -> Path:
    """Where to find frontend/ and assets/ — different when PyInstaller has
    frozen this into a single executable: bundled data files are unpacked
    into a temp dir at runtime, reported via sys._MEIPASS, not next to this
    .py file (which no longer exists as a real file at all in that case).
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
INDEX_HTML = BASE_DIR / "frontend" / "index.html"
# Windows' window-icon path goes through .NET's System.Drawing.Icon, which
# only accepts an actual .ico file — handing it a .png raises
# "argument 'picture' must be an image that can be used as an Icon."
# (confirmed in pywebview's own webview/platforms/winforms.py: it does
# `self.Icon = Icon(_state['icon'])` with no format conversion). Qt (Linux)
# and Cocoa (macOS) both accept .png directly via their own icon classes.
ICON_PATH = BASE_DIR / "assets" / ("icon.ico" if platform.system() == "Windows" else "icon.png")


def _read_version() -> str:
    """VERSION at the project root is the single source of truth — bump it
    there, nowhere else. Falls back quietly if it's ever missing so a
    packaging slip doesn't crash the app over a cosmetic detail."""
    try:
        return (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


VERSION = _read_version()
WINDOW_TITLE = f"PDFImageMerger v{VERSION}"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}


def _on_drag(event):
    # No-op handler: its only job is to preventDefault/stopPropagation (done
    # via the DOMEventHandler flags below) so the browser allows the drop.
    pass


def _make_on_drop(api: Api):
    def _on_drop(event):
        files = (event or {}).get("dataTransfer", {}).get("files", [])
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if paths:
            api.notify_files_dropped(paths)

    return _on_drop


def bind_drag_and_drop(window: webview.Window, api: Api) -> None:
    document = window.dom.document
    document.events.dragenter += DOMEventHandler(_on_drag, True, True)
    document.events.dragstart += DOMEventHandler(_on_drag, True, True)
    document.events.dragover += DOMEventHandler(_on_drag, True, True, debounce=200)
    document.events.drop += DOMEventHandler(_make_on_drop(api), True, True)


def _linux_gui() -> str | None:
    """Which pywebview backend to force on Linux, or None to let it
    auto-detect.

    pywebview's own auto-detection (webview/guilib.py) tries GTK before Qt
    unless told otherwise, and that attempt is a plain `import gi` with no
    guard around the console noise — it logs a full traceback for the
    ModuleNotFoundError even though it then falls back to Qt just fine. Our
    default Linux install (`pywebview[qt]` in requirements.txt) never
    installs GTK bindings, so that traceback fires on every single launch.
    Forcing gui="qt" up front skips the GTK probe entirely instead of just
    tolerating its noise — confirmed in guilib.py: with forced_gui == "qt"
    the probe order becomes [import_qt, import_gtk], and import_gtk is never
    even reached once Qt succeeds.

    Only forces it when PyQt6 is actually importable, so the README's
    alternative "system GTK, no PyQt6" install path keeps auto-detecting
    (and getting GTK) exactly as before.
    """
    if platform.system() != "Linux":
        return None
    if getattr(sys, "frozen", False):
        return "qt"  # packaged build always bundles PyQt6 — see pdfimagemerger.spec
    if importlib.util.find_spec("PyQt6") is not None:
        return "qt"
    return None


def main() -> None:
    api = Api()

    window = webview.create_window(
        WINDOW_TITLE,
        url=str(INDEX_HTML),
        js_api=api,
        width=1180,
        height=780,
        min_size=(860, 600),
        background_color="#0b0b0c",
        text_select=False,
        confirm_close=False,
    )
    api.set_window(window)

    def bind(win: webview.Window) -> None:
        bind_drag_and_drop(win, api)

    # Windows keeps using its native WebView2 backend either way — forcing
    # "qt" there would break the packaged .exe, which never bundles PyQt6.
    gui = _linux_gui()

    webview.start(
        bind,
        window,
        gui=gui,
        icon=str(ICON_PATH) if ICON_PATH.exists() else None,
        debug="--debug" in sys.argv,
    )


if __name__ == "__main__":
    main()
