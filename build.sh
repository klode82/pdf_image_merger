#!/usr/bin/env bash
# Build a standalone, distributable PDFImageMerger for the platform this
# script is run on:
#
#   - Linux:                 dist/PDFImageMerger-x86_64.AppImage
#   - Windows (Git Bash):    dist/PDFImageMerger.exe
#
# IMPORTANT — PyInstaller does not cross-compile. Run this script ON EACH
# target OS to get that OS's artifact: a Linux machine produces the
# AppImage, a Windows machine (with Git Bash, so this .sh can run at all)
# produces the .exe. There is no supported way here to build the Windows
# .exe from Linux or vice versa without something like Wine, which is
# fragile enough that this script deliberately does not attempt it.
#
# Usage:  ./build.sh

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

APP_NAME="PDFImageMerger"
DIST_DIR="$(pwd)/dist"
BUILD_DIR="$(pwd)/build"
TOOLS_DIR="$(pwd)/.build-tools"
APPIMAGETOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

detect_os() {
  case "$(uname -s)" in
    Linux*) echo "linux" ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
    Darwin*) echo "macos" ;;
    *) echo "unknown" ;;
  esac
}

OS="$(detect_os)"
log "Platform: $OS ($(uname -s))"

PYTHON=python3
command -v python3 >/dev/null 2>&1 || PYTHON=python
command -v "$PYTHON" >/dev/null 2>&1 || die "Nessun python3/python trovato nel PATH."

# ---------------------------------------------------------------------------
# 1. Dependencies (app requirements + PyInstaller)
# ---------------------------------------------------------------------------
log "Installo le dipendenze (pip install -r requirements.txt + pyinstaller)"
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet -r requirements.txt
"$PYTHON" -m pip install --quiet pyinstaller

log "Rigenero l'icona (assets/icon.png + assets/icon.ico)"
"$PYTHON" assets/generate_icon.py

# ---------------------------------------------------------------------------
# 2. PyInstaller onefile build — same spec on every OS, it self-adapts
#    (see pdfimagemerger.spec: Qt bundling on Linux, WebView2 DLLs on
#    Windows, nothing extra on macOS).
# ---------------------------------------------------------------------------
log "Eseguo PyInstaller (build monolitica, può richiedere qualche minuto)"
rm -rf "$BUILD_DIR" "$DIST_DIR"
"$PYTHON" -m PyInstaller --noconfirm --clean pdfimagemerger.spec

case "$OS" in
  windows)
    [ -f "$DIST_DIR/${APP_NAME}.exe" ] || die "Build fallita: ${APP_NAME}.exe non trovato in dist/"
    log "Fatto: dist/${APP_NAME}.exe"
    ;;

  linux)
    [ -f "$DIST_DIR/$APP_NAME" ] || die "Build fallita: $APP_NAME non trovato in dist/"

    # -------------------------------------------------------------------
    # 3. Wrap the Linux binary into a portable AppImage.
    # -------------------------------------------------------------------
    log "Preparo appimagetool"
    mkdir -p "$TOOLS_DIR"
    APPIMAGETOOL="$TOOLS_DIR/appimagetool"
    if [ ! -x "$APPIMAGETOOL" ]; then
      log "Scarico appimagetool (una tantum, resta in .build-tools/)"
      curl -fL "$APPIMAGETOOL_URL" -o "$APPIMAGETOOL" \
        || die "Download di appimagetool fallito. Controlla la connessione e riprova."
      chmod +x "$APPIMAGETOOL"
    fi

    log "Assemblo l'AppDir"
    APPDIR="$BUILD_DIR/${APP_NAME}.AppDir"
    rm -rf "$APPDIR"
    mkdir -p "$APPDIR/usr/bin"
    cp "$DIST_DIR/$APP_NAME" "$APPDIR/usr/bin/"
    cp "assets/icon.png" "$APPDIR/pdfimagemerger.png"

    cat > "$APPDIR/pdfimagemerger.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Unisci immagini in un unico PDF
Exec=$APP_NAME
Icon=pdfimagemerger
Categories=Graphics;
Terminal=false
EOF

    cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/bin/PDFImageMerger" "$@"
EOF
    chmod +x "$APPDIR/AppRun"

    log "Genero l'AppImage"
    # --appimage-extract-and-run: non richiede FUSE, utile su molte macchine
    # di sviluppo/CI dove FUSE non è configurato.
    ARCH=x86_64 "$APPIMAGETOOL" --appimage-extract-and-run \
      "$APPDIR" "$DIST_DIR/${APP_NAME}-x86_64.AppImage" \
      || die "appimagetool ha fallito."

    log "Fatto: dist/${APP_NAME}-x86_64.AppImage"
    ;;

  macos)
    [ -f "$DIST_DIR/$APP_NAME" ] || die "Build fallita: $APP_NAME non trovato in dist/"
    log "Fatto: dist/${APP_NAME} (bundle .app non generato — vedi README)"
    ;;

  *)
    echo "Piattaforma '$(uname -s)' non riconosciuta: build PyInstaller completata in dist/, ma nessun packaging aggiuntivo è stato eseguito." >&2
    ;;
esac

log "Dimensione artefatti in dist/:"
du -sh "$DIST_DIR"/* 2>/dev/null || true
