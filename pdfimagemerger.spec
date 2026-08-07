# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PDFImageMerger — built via build.sh, not run directly.
# A .spec file (plain Python) is used instead of a long CLI command because
# --add-data's separator differs by platform (":" on Linux/macOS, ";" on
# Windows) — tuples below sidestep that entirely.

import os
import platform

datas = [
    ("frontend", "frontend"),
    ("assets", "assets"),
]
binaries = []
hiddenimports = []
system = platform.system()

if system == "Linux":
    # The packaged Linux build standardizes on the Qt backend (see main.py):
    # pip-installable, no system GTK packages required on the machine that
    # runs the result. PyQt6-WebEngine needs its own data/binaries
    # (translations, ICU data, the QtWebEngineProcess helper executable)
    # picked up explicitly — PyInstaller's generic import scan alone misses
    # them.
    from PyInstaller.utils.hooks import collect_all

    for pkg in ("PyQt6", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineCore"):
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden

elif system == "Windows":
    # pywebview's native Windows backend (EdgeChromium/WebView2) looks for
    # these DLLs — among a few fallback locations — flat next to sys.argv[0]
    # or, for a onefile build, flat at the PyInstaller runtime extraction
    # root (sys._MEIPASS). Verified against pywebview's own
    # webview/util.py:interop_dll_path(), not guessed: PyInstaller's generic
    # scan does not pick these up on its own since they're loaded via
    # pythonnet/clr, not a normal Python import.
    import webview

    lib_dir = os.path.join(os.path.dirname(webview.__file__), "lib")
    flat_dlls = [
        "Microsoft.Web.WebView2.Core.dll",
        "Microsoft.Web.WebView2.WinForms.dll",
        "WebBrowserInterop.x64.dll",
        "WebBrowserInterop.x86.dll",
    ]
    for name in flat_dlls:
        path = os.path.join(lib_dir, name)
        if os.path.exists(path):
            datas.append((path, "."))

    arch_dir = "win-x64" if platform.machine().endswith("64") else "win-x86"
    loader_dll = os.path.join(lib_dir, "runtimes", arch_dir, "native", "WebView2Loader.dll")
    if os.path.exists(loader_dll):
        datas.append((loader_dll, "."))

icon_path = "assets/icon.ico" if system == "Windows" else "assets/icon.png"

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PDFImageMerger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
