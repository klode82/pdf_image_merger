"""
PDFImageMerger
==============
Entry point. Creates the pywebview window around frontend/index.html and
wires up native OS -> window drag & drop (which pywebview can only resolve
to real filesystem paths on the Python side, via DOMEventHandler).

Run with:  python main.py
"""

from __future__ import annotations

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
ICON_PATH = BASE_DIR / "assets" / "icon.png"

WINDOW_TITLE = "PDFImageMerger"
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

    # The packaged Linux build (see build.sh) bundles PyQt6 specifically, so
    # pin the backend there instead of letting pywebview probe for GTK first
    # (which isn't bundled and would just waste a failed import on every
    # launch). Windows keeps using its native WebView2 backend either way —
    # forcing "qt" there would break the packaged .exe, which never bundles
    # PyQt6. A plain `python main.py` from source keeps auto-detecting.
    is_frozen = getattr(sys, "frozen", False)
    gui = "qt" if (is_frozen and platform.system() == "Linux") else None

    webview.start(
        bind,
        window,
        gui=gui,
        icon=str(ICON_PATH) if ICON_PATH.exists() else None,
        debug="--debug" in sys.argv,
    )


if __name__ == "__main__":
    main()
