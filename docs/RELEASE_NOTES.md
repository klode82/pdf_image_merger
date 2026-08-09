<!--
  Copy the section below into GitHub's "Releases" page when publishing this
  version (tag v1.0.1). Kept in its own file, in English, so it's ready to
  paste as-is — the rest of docs/ (DEVELOPMENT_NOTES.md) is the deeper,
  Italian dev diary this project has been keeping instead.
-->

## v1.0.1

### New

- **Localization**: PDFImageMerger now speaks English, Italian, Spanish,
  French, Chinese (Simplified), and Hindi. It follows your OS language on
  first launch — open **Preferences** (gear icon, top right) to pick one
  explicitly, or to set the theme (Automatic/Light/Dark) instead.

### Fixed

- Language and theme preferences did not actually survive an app restart.
  pywebview runs its underlying webview in a private/ephemeral mode by
  default on every backend, which never writes `localStorage` to disk —
  so a preference saved there was silently gone on the next launch.
  Preferences now live in their own JSON config file instead (see the
  README's [Localization](../README.md#localization) section for the
  exact path per OS).
- Linux: a `ModuleNotFoundError: No module named 'gi'` traceback appeared
  in the console on every launch. pywebview probes for a GTK backend
  before falling back to Qt unless told otherwise; the app now skips that
  probe entirely when PyQt6 is available (which is the default install —
  see `requirements.txt`), instead of just tolerating the noise.
- The **"Don't modify images"** toggle switch never actually changed color
  when turned on — Franken UI's toggle component needs an explicit
  `uk-toggle-switch-primary` modifier class for that; it was missing.

### Under the hood

- The handful of user-facing strings the Python backend itself generates
  (build errors, native file-dialog filters) now come from the same
  translation catalog as the UI, instead of being hardcoded in Italian.
