<div align="center">

<img src="assets/icon.png" alt="PDFImageMerger icon" width="96" height="96" />

# PDFImageMerger

**Turn a folder of images into one PDF — fast, offline, and cross-platform.**

[![Version](https://img.shields.io/badge/version-1.0.0-blue)](https://github.com/klode82/pdf_image_merger/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#installation)
[![pywebview](https://img.shields.io/badge/pywebview-%E2%89%A55.4-informational)](https://pywebview.flowrl.com/)
[![Pillow](https://img.shields.io/badge/Pillow-%E2%89%A510.0-informational)](https://pillow.readthedocs.io/)
[![pikepdf](https://img.shields.io/badge/pikepdf-%E2%89%A58.0-informational)](https://pikepdf.readthedocs.io/)
[![UI: Franken UI](https://img.shields.io/badge/UI-Franken%20UI-informational)](https://franken-ui.dev/)
[![Packaging: PyInstaller](https://img.shields.io/badge/packaging-PyInstaller-informational)](https://pyinstaller.org/)

</div>

<p align="center">
  <a href="https://www.buymeacoffee.com/aurigalab" target="_blank" title="buymeacoffee">
    <img src="https://iili.io/JoQ1MeS.md.png"  alt="buymeacoffee-yellow-badge" style="width:160px">
  </a>
</p>

---

## The problem

If you've ever scanned a stack of documents, downloaded a comic/manga chapter
as a folder of numbered `.jpg` files, or photographed a set of receipts, you've
run into the same annoying gap: you have *images*, but you actually need *one
PDF*. The usual options all fall short in some way:

- General-purpose PDF suites are heavyweight installs for a one-off task.
- Web-based "image to PDF" converters mean uploading your files to someone
  else's server — a non-starter for anything private, and painfully slow for
  a folder with hundreds of images.
- Quick scripts and one-off tools tend to choke on large batches (holding
  every page in memory at once), mangle EXIF-rotated photos, silently
  re-compress images you wanted left alone, or simply break on Windows once a
  folder's path gets long enough — which happens fast with deeply nested
  archives.

**PDFImageMerger** is a small, focused desktop tool that does exactly one job
well: merge the images in a folder into a single, well-formed PDF — locally,
quickly, and with real control over the size/quality tradeoff, instead of a
black box.

## What it does

Point it at a folder (or drag images straight into the window), tune a
handful of settings, and get a PDF. That's the whole idea — but the details
are where it earns its keep:

- **Three ways to add images** — pick a folder, pick individual files, or
  drag & drop them straight into the window (a whole folder works too).
- **Reorderable file list** with per-image thumbnail, dimensions, and file
  size; drag rows to reorder, remove one, sort the list, or clear it.
- **Page format control** — A4 / Letter / Legal / A5, or "fit to image" (no
  fixed page — every image becomes a page sized to itself), plus
  portrait/landscape orientation.
- **Resolution & compression control** (72–600 DPI, low/medium/high) — the
  two knobs that actually determine the final file size.
- **A real size estimate before you commit** — it compresses a sample of the
  actual images with the actual settings you picked and extrapolates; not a
  guess.
- **"Keep images unmodified" mode** — skip resizing and recompression
  entirely. Where possible (plain JPEGs with a non-mirrored orientation),
  the original file's bytes are embedded **byte-for-byte**, not
  re-encoded — verified against real output, not just assumed. Everything
  else still comes through losslessly, just not byte-identical.
- **Handles large batches without exploding memory** — pages are built and
  merged in small chunks sized to your settings, not held all in memory at
  once. Tested at 800 images without breaking a sweat.
- **Fully offline UI** — the frontend framework is vendored locally, no CDN,
  no network required to run the app.
- **Cross-platform** — runs from source on Windows, Linux, and macOS; ships
  as a standalone single-file executable for Windows (`.exe`) and Linux
  (`.AppImage`), no Python installation required on the machine that runs it.

## Table of contents

- [Installation](#installation)
- [Usage](#usage)
- [Building a standalone executable](#building-a-standalone-executable)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Under the hood](#under-the-hood)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Installation

```bash
git clone https://github.com/klode82/pdf_image_merger.git
cd pdf_image_merger
pip install -r requirements.txt
```

That's the whole setup on **Windows** and **macOS** — pywebview pulls in its
native backend dependencies (WebView2/pythonnet, WKWebView/pyobjc) on its own.

**Linux** doesn't ship a bundled backend by default, so `requirements.txt`
also installs the `pywebview[qt]` extra there (QtPy + PyQt6 + PyQt6-WebEngine)
— pure `pip`, no system packages or `sudo` required, and it works inside an
isolated virtualenv. If you'd rather use a system GTK install instead, see
[`docs/DEVELOPMENT_NOTES.md`](docs/DEVELOPMENT_NOTES.md) for that path.

## Usage

```bash
python main.py
```

1. Add images: **Choose folder**, **Choose images**, or just drag files (or a
   whole folder) into the window.
2. Reorder/remove/sort as needed in the file list.
3. Pick a page format, orientation, resolution and compression level — or
   flip on **"Don't modify images"** to skip all of that and keep every
   pixel exactly as it is.
4. Check the live size estimate, name the output file, choose a destination.
5. Click **Create PDF**. When it's done, jump straight to the file or its
   folder — or hit **Create new** to start the next batch without losing your
   settings.

## Building a standalone executable

A distributable build that doesn't require Python on the machine that runs
it, via [PyInstaller](https://pyinstaller.org/). Both scripts drive the same
`pdfimagemerger.spec`, which adapts itself per OS.

| Platform | Command | Output |
|---|---|---|
| Linux | `./build.sh` | `dist/PDFImageMerger-x86_64.AppImage` |
| Windows (cmd.exe) | `build.cmd` | `dist\PDFImageMerger.exe` |
| Windows (Git Bash) | `./build.sh` | `dist\PDFImageMerger.exe` |

> **PyInstaller does not cross-compile.** Run the build *on* each target OS
> to get that OS's artifact — there's no supported way to produce the Windows
> `.exe` from Linux (or vice versa) without something like Wine, which this
> project deliberately avoids for being too fragile to support.

The Windows executable isn't code-signed (that requires a paid certificate),
so Windows SmartScreen will flag it as coming from an "unknown publisher" —
see [Troubleshooting](#troubleshooting).

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Desktop shell | [pywebview](https://pywebview.flowrl.com/) | Native window + OS webview control, no bundled browser engine required on Windows/macOS |
| UI framework | [Franken UI](https://franken-ui.dev/) | HTML-first component library on UIkit 3 — vendored locally, so the UI works fully offline |
| Image processing | [Pillow](https://pillow.readthedocs.io/) | Decoding, EXIF handling, resizing, thumbnailing |
| PDF construction | [pikepdf](https://pikepdf.readthedocs.io/) (qpdf) | Low-level page/stream control — needed because Pillow's own PDF writer can't do what this app needs (see [Under the hood](#under-the-hood)) |
| Packaging | [PyInstaller](https://pyinstaller.org/) | Standalone single-file executables for Windows and Linux |

## Architecture

```
pdf_image_merger/
├── main.py               # pywebview bootstrap + native OS drag & drop
├── api.py                # Python <-> JS bridge (pywebview.api.*), file-list state
├── pdf_builder.py         # pure image/PDF logic — no GUI dependency, independently testable
├── build.sh / build.cmd   # standalone executable builds (Linux AppImage / Windows exe)
├── pdfimagemerger.spec    # PyInstaller spec used by both build scripts
├── VERSION                # single source of truth for the version shown in the window title
├── assets/                # app icon + the script that generates it
└── frontend/
    ├── index.html, app.js
    └── vendor/franken-ui/ # Franken UI, vendored — no CDN, works offline
```

`pdf_builder.py` has zero dependency on pywebview or any GUI code — it's
importable and testable entirely on its own, which is exactly how its size
estimates and page geometry were validated during development.

## Under the hood

A few decisions that shaped this app beyond "call Pillow and save":

- **Memory-safe large batches.** Pillow's own multi-page PDF save holds every
  decoded page in RAM at once — fine for a handful of images, not for
  hundreds at print resolution. Pages are built and merged in small chunks
  (sized dynamically from the page resolution) instead, keeping peak memory
  bounded regardless of batch size. Verified at 800 images: ~550 MB peak
  instead of the tens of GB naive decoding would need.
- **Byte-exact "keep it as-is" mode.** Pillow's PDF writer *always*
  re-encodes RGB images as JPEG — there's no lossless path through that API
  at all (confirmed by reading `PdfImagePlugin` itself). So "don't modify
  images" bypasses Pillow's writer and builds PDF pages by hand with
  pikepdf: a source JPEG's original bytes go in as a `DCTDecode` stream
  completely untouched — not a re-encode, verified byte-for-byte against the
  file on disk — with EXIF rotation compensated purely via a placement
  matrix in the page's content stream (PDF viewers don't look at embedded
  JPEGs' EXIF tags). Everything else falls back to a lossless (zlib) path.
  Real result: 100 JPEGs at 1MB each stay ~100MB in the output PDF, not the
  ~1.6GB a naive decode-and-recompress would produce.
- **Windows long-path safety.** Windows' legacy file APIs cap paths around
  260 characters — easy to hit with a few levels of descriptive subfolder
  names (a comic/manga archive organized by series/volume/chapter is a
  textbook case) even when no single name looks unreasonable. Every actual
  file I/O call goes through the `\\?\` long-path prefix, which Windows
  honors unconditionally.
- **Native OS drag & drop.** Getting the *real filesystem path* of a dropped
  file — not just its name, which is all a browser exposes by default —
  uses pywebview's `window.dom` DOM-event bridge rather than plain HTML5
  drag & drop.

More background on specific bugs hunted down along the way — a pywebview
reflection bug that could freeze the window on Windows, a Windows icon
format gotcha, a Franken UI toggle-switch styling miss, and more — is in
[`docs/DEVELOPMENT_NOTES.md`](docs/DEVELOPMENT_NOTES.md) (Italian, written
during development; deep technical detail, GitHub-issue-linked where
relevant).

## Troubleshooting

**"You must have either QT or GTK installed" (Linux)** — pywebview couldn't
find a usable backend; see [Installation](#installation).

**Blank window / "dma_buf" errors in the console (Linux)** — QtWebEngine
failing to get GPU acceleration, common on VMs and some Wayland setups.
`main.py` already disables GPU compositing by default on Linux; if it still
happens, try `QT_QPA_PLATFORM=xcb python main.py`.

**"Windows protected your PC" / SmartScreen** — the executable isn't
code-signed (that costs money); this is expected for any unsigned `.exe`,
not a sign of anything wrong. Click **More info → Run anyway**.

For anything more specific — including bugs that were found and fixed during
development, with the full diagnosis — see
[`docs/DEVELOPMENT_NOTES.md`](docs/DEVELOPMENT_NOTES.md).

## Contributing

Issues and pull requests are welcome. `pdf_builder.py` is fully decoupled
from the GUI, so most logic changes (page geometry, size estimation, PDF
construction) can be tested without touching pywebview at all.

## License

[MIT](LICENSE) © 2026 AurigaLAB
