# PDFImageMerger

Tool desktop semplice e cross-platform (Windows / macOS / Linux) per unire le
immagini di una cartella in un unico PDF. GUI con [pywebview](https://pywebview.flowrl.com/)
+ [Franken UI](https://franken-ui.dev/) (vendorizzato localmente: l'app funziona anche offline).

## Funzionalità

- Aggiunta immagini scegliendo una cartella, singoli file, **oppure trascinandoli
  direttamente nella finestra** (anche una cartella intera).
- Lista dei file da unire, riordinabile per drag & drop, con anteprima, dimensioni
  e peso di ciascuna immagine; rimozione singola o svuotamento completo.
- Formato pagina: A4 / Letter / Legal / A5, oppure "adatta all'immagine" (nessuna
  pagina fissa, ogni immagine diventa una pagina delle sue stesse dimensioni).
- Orientamento verticale/orizzontale (per i formati a pagina fissa).
- Risoluzione (72 / 150 / 300 / 600 DPI) e livello di compressione (bassa/media/alta),
  i due parametri che determinano davvero la dimensione finale del file.
- **Stima della dimensione finale del PDF** prima di crearlo, calcolata comprimendo
  davvero un campione delle immagini con le impostazioni scelte (non un numero a caso).
- **Flag "Non modificare le immagini"**: disattiva formato pagina/orientamento/
  risoluzione/compressione e usa ogni immagine esattamente come è — stessa
  dimensione in pixel, zero perdita di qualità (vedi sotto come è implementato
  davvero). File risultante più pesante, a fronte di zero modifiche.
- Scelta del nome del file e della cartella di destinazione.
- Barra di progresso durante la creazione; a fine lavoro, scorciatoie per aprire il
  PDF o la cartella che lo contiene.

## Requisiti

```bash
pip install -r requirements.txt
```

Questo basta su tutte le piattaforme. Su Windows e macOS pywebview usa i
backend nativi (WebView2/pythonnet, WKWebView/pyobjc), che porta già con sé
come dipendenze. **Su Linux non è incluso di default nessun backend**: il
`requirements.txt` installa quindi anche l'extra `pywebview[qt]`
(QtPy + PyQt6 + PyQt6-WebEngine) — pip puro, nessun pacchetto di sistema o
`sudo` richiesto, funziona anche dentro un virtualenv isolato.

**Alternativa Linux più leggera** (backend GTK di sistema invece di Qt via
pip): richiede `sudo` e un venv creato con `--system-site-packages`, perché
PyGObject si appoggia alle librerie GTK del sistema e non è "isolabile" in un
venv puro:

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install pywebview Pillow   # senza l'extra [qt], qui basta GTK
```

## Avvio

```bash
python main.py
```

### Errore "You must have either QT or GTK ... installed"

Significa che pywebview non ha trovato nessuno dei due backend — vedi la
sezione Requisiti sopra e scegli una delle due strade per il tuo caso.

### La finestra si apre ma resta vuota (con "dma_buf" / "Compositor returned
### null texture" in console)

QtWebEngine (il motore Chromium usato dal backend Qt) non riesce ad accedere
alla GPU — capita spesso su VM, sessioni remote o desktop Wayland. `main.py`
imposta già `QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu` in automatico su Linux
per evitarlo. Se dovesse ripresentarsi comunque, prova a forzare anche il
backend di visualizzazione di Qt su X11 (utile sui sistemi Wayland):

```bash
QT_QPA_PLATFORM=xcb python main.py
```

## Build standalone (AppImage / .exe)

Un eseguibile distribuibile che non richiede Python installato su chi lo usa,
via [PyInstaller](https://pyinstaller.org/). Stesso spec (`pdfimagemerger.spec`)
per entrambi gli script: si adatta da solo in base al sistema operativo.

**Linux:**

```bash
./build.sh
```

→ `dist/PDFImageMerger-x86_64.AppImage`, un singolo file eseguibile
(`chmod +x` + doppio click o `./PDFImageMerger-*.AppImage`), niente da
installare. Costruito e **verificato con un lancio reale** (finestra apparsa
correttamente, nessun errore di packaging).

**Windows — due modi equivalenti, scegli quello che preferisci:**

```cmd
build.cmd
```
nel prompt di Windows normale (cmd.exe), oppure `./build.sh` da
[Git Bash](https://git-scm.com/downloads) se già lo usi. Entrambi lanciano lo
stesso identico `pdfimagemerger.spec` con PyInstaller.

→ `dist\PDFImageMerger.exe`, singolo file.

⚠️ **PyInstaller non compila incrociato**: uno di questi due script va
eseguito *su ciascun sistema* per produrre l'artefatto di quel sistema — una
AppImage non si può generare da Windows né un .exe da Linux senza strumenti
come Wine, che questo progetto deliberatamente non usa (troppo fragili da
supportare per un tool "semplice"). La build Windows usa il backend nativo
WebView2 (nessun Qt bundlato: eseguibile molto più leggero della AppImage) —
i percorsi delle sue DLL sono stati inseriti nello spec leggendo il codice
sorgente di pywebview (`webview/util.py:interop_dll_path`), ma **non è stata
concretamente testata su una macchina Windows reale** in questo lavoro (non
disponibile): se al primo avvio manca una DLL, la soluzione nota è copiare
manualmente `WebView2Loader.dll` (si trova dentro
`site-packages\webview\lib\runtimes\win-x64\native\` del tuo venv) accanto a
`PDFImageMerger.exe`.

La build Linux pesa ~260MB: quasi tutto è Chromium via QtWebEngine (bundlato
perché su Linux, a differenza di Windows/macOS, non c'è un motore browser di
sistema garantito). `build.sh` scarica `appimagetool` una tantum in
`.build-tools/` (serve una connessione internet la prima volta).

## Struttura del progetto

```
pdf_image_merger/
├── main.py            # bootstrap pywebview + drag&drop nativo (path reali dei file)
├── api.py             # ponte Python <-> JS (pywebview.api.*), stato della lista file
├── pdf_builder.py      # logica pura immagini/PDF (nessuna dipendenza GUI, testabile a sé)
├── build.sh            # build standalone: AppImage su Linux, .exe su Windows (via Git Bash)
├── build.cmd           # come build.sh, ma per il prompt Windows nativo (cmd.exe)
├── pdfimagemerger.spec # spec PyInstaller usato da build.sh
├── assets/
│   ├── generate_icon.py   # rigenera icon.png/icon.ico (nessun tool esterno)
│   ├── icon.png
│   └── icon.ico
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── vendor/franken-ui/   # Franken UI vendorizzato: l'app non richiede internet
└── requirements.txt
```

`pdf_builder.py` non ha alcuna dipendenza da pywebview: può essere importato e
testato da solo (è quello che è stato fatto in fase di sviluppo per validare stime
e geometria delle pagine con [Pillow](https://pillow.readthedocs.io/) e
[pikepdf](https://pikepdf.readthedocs.io/)).

## Batch grandi (centinaia di immagini)

Il PDF viene costruito a blocchi (non tutte le pagine tenute in RAM insieme):
la dimensione del blocco si adatta da sola in base a formato pagina e DPI
scelti, per restare sempre entro qualche centinaio di MB di picco, poi i
blocchi vengono uniti con [pikepdf](https://pikepdf.readthedocs.io/) (che
lavora sui flussi JPEG già compressi, non sui pixel grezzi). Testato con 800
immagini A4 a 300 DPI: picco di RAM ~550 MB invece delle decine di GB che
richiederebbe tenere 800 pagine decodificate tutte insieme in memoria.

## Note tecniche

- Il drag & drop dal file manager del sistema operativo sfrutta l'API
  `window.dom.document.events.drop` di pywebview (>=5.0), l'unico modo per
  ottenere il **percorso reale** dei file rilasciati — il browser, per motivi
  di sicurezza, non lo espone a JavaScript.
- Le immagini vengono normalizzate (rotazione EXIF, trasparenza appiattita su
  sfondo bianco) e compresse in JPEG dentro il PDF con la qualità scelta.
- **"Non modificare le immagini" non usa il writer PDF di Pillow**: per le
  immagini RGB, `Image.save(..., "PDF", ...)` di Pillow ricomprime *sempre* in
  JPEG, qualunque cosa gli si passi — non esiste un modo lossless attraverso
  quella API (verificato leggendo `PdfImagePlugin._write_image`: per il modo
  "RGB" il filtro `DCTDecode`/JPEG è scelto senza condizioni). Per questo flag
  le pagine vengono quindi costruite a mano con
  [pikepdf](https://pikepdf.readthedocs.io/), con due percorsi:
  - **JPEG con orientamento EXIF non specchiato (i casi reali di fotocamere/
    telefoni)**: i byte del file originale vengono incorporati **letteralmente
    invariati** come stream `DCTDecode` — non un ri-encode, il file stesso.
    Verificato byte per byte (lo stream nel PDF == i byte del file su disco).
    Una rotazione EXIF (90°/180°/270°, i tag 3/6/8) viene compensata solo con
    una matrice di posizionamento nel content-stream della pagina — i PDF
    non guardano i tag EXIF dei JPEG incorporati, quindi va gestita a parte;
    le matrici sono state derivate e verificate rendendo davvero con
    Ghostscript/Poppler un'immagine di test a 4 quadranti asimmetrici, non
    solo calcolate a mano. Gli EXIF specchiati (tag 2/4/5/7, praticamente
    inesistenti in natura) ricadono nel percorso sotto per non rischiare una
    matrice di mirroring sbagliata.
  - **Tutto il resto** (PNG/BMP/TIFF/WEBP/GIF, o quei rari JPEG specchiati):
    decodifica una volta e i pixel finiscono in uno stream `FlateDecode`
    (zlib, senza perdita) — zero perdita, ma il file cresce comunque, perché
    Flate comprime il rumore fotografico molto peggio di JPEG.

  Risultato concreto testato: 100 JPEG da 1MB ciascuno restano ~100MB nel PDF
  (rapporto 1.03×, solo overhead di struttura PDF) — non i ~1.6GB che si
  otterrebbero decodificando e ricomprimendo tutto in Flate. Elaborando
  un'immagine alla volta, questa modalità non ha nemmeno bisogno del
  chunking usato per le centinaia di immagini in modalità normale.
