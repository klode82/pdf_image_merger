"""
settings.py
------------
Persisted user preferences (language, theme) — stored on disk so they
survive app restarts, plus best-effort OS UI-language detection.

Deliberately NOT using pywebview's own localStorage for this: by default
pywebview runs the underlying webview in "private mode" (WebView2
IsInPrivateModeEnabled, WebKitGTK's ephemeral WebContext, etc. — confirmed by
reading every backend under webview/platforms/*.py), which does not persist
localStorage/cookies to disk at all. A plain JSON file we own works
identically regardless of that, and is trivial to inspect/debug.
"""

from __future__ import annotations

import json
import locale
import os
import platform
import subprocess
from pathlib import Path

APP_NAME = "PDFImageMerger"

SUPPORTED_LANGUAGES = ["en", "it", "es", "fr", "zh", "hi"]
THEMES = ("auto", "light", "dark")

DEFAULT_SETTINGS = {
    "language": "auto",  # "auto", or one of SUPPORTED_LANGUAGES
    "theme": "auto",  # "auto" | "light" | "dark"
}


def config_dir() -> Path:
    """Per-OS standard location for user config files."""
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    # Linux and anything else POSIX-y: XDG Base Directory spec.
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME.lower()


def _config_path() -> Path:
    return config_dir() / "config.json"


def load() -> dict:
    """Reads the config file, filling in/repairing anything missing or
    invalid with defaults — a corrupt or hand-edited config file should
    never be able to crash the app on startup."""
    path = _config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}

    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})

    if merged["language"] != "auto" and merged["language"] not in SUPPORTED_LANGUAGES:
        merged["language"] = "auto"
    if merged["theme"] not in THEMES:
        merged["theme"] = "auto"
    return merged


def save(new_settings: dict) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(new_settings, indent=2, ensure_ascii=False), encoding="utf-8")


def detect_system_language() -> str:
    """Best-effort OS UI language -> one of SUPPORTED_LANGUAGES, defaulting
    to English. Each branch is the practically reliable way to ask that OS
    for this — a generic `locale.getlocale()` mostly just reflects the C
    locale (often unset entirely) rather than the user's actual OS UI
    language:

    - Windows: `GetUserDefaultUILanguage()` via ctypes. Not verified on a
      real Windows machine (none was available during development) — see
      docs/DEVELOPMENT_NOTES.md.
    - macOS: `defaults read -g AppleLocale`. GUI-launched .app bundles are
      not started from a shell, so they frequently don't inherit
      LANG/LC_ALL at all — the environment-variable approach that works on
      Linux can't be relied on here. Also not verified on a real Mac.
    - Linux: the LANG/LC_ALL/LANGUAGE environment variables, which is what
      the desktop session actually sets and what most GUI toolkits read.
    """
    lang_code = None
    system = platform.system()

    if system == "Windows":
        try:
            import ctypes

            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
            lang_code = locale.windows_locale.get(lcid)
        except Exception:
            lang_code = None
    elif system == "Darwin":
        try:
            proc = subprocess.run(
                ["defaults", "read", "-g", "AppleLocale"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            lang_code = proc.stdout.strip() or None
        except Exception:
            lang_code = None

    if not lang_code:
        lang_code = os.environ.get("LANG") or os.environ.get("LC_ALL") or os.environ.get("LANGUAGE")

    if not lang_code:
        try:
            lang_code, _ = locale.getlocale()
        except (ValueError, TypeError):
            lang_code = None

    if not lang_code:
        return "en"

    # "it_IT.UTF-8" / "it-IT" / "it_IT" -> "it"
    primary = lang_code.replace("-", "_").split("_")[0].split(".")[0].lower()
    return primary if primary in SUPPORTED_LANGUAGES else "en"


def resolve_language(current_settings: dict) -> str:
    """The settings' language preference, resolved to an actual language
    code — "auto" becomes whatever the OS reports (or "en")."""
    lang = current_settings.get("language", "auto")
    return detect_system_language() if lang == "auto" else lang
