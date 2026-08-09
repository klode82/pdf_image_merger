<!--
  These are the original, detailed Italian development notes accumulated
  while building PDFImageMerger — kept as-is for anyone who wants the deep
  technical rationale behind specific bugs and fixes. The main README.md is
  the English, GitHub-facing overview; this file is the "why", in full.
-->

# PDFImageMerger — Note di sviluppo (dettagliate)

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

### Windows: la finestra si blocca (rondella di caricamento) dopo averla spostata

Causa individuata: pywebview espone a JS le funzioni Python leggendo per
riflessione **tutti** gli attributi dell'oggetto `js_api` — nel nostro caso
`Api`, che tiene un riferimento alla finestra stessa (`self.window`). Su
Windows quella scansione può proseguire dentro `window.native` (il controllo
WinForms/WebView2 vero e proprio) e finire in un loop infinito su
`System.Drawing.Rectangle.Empty` (visibile in console come
`AccessibilityObject.Bounds.Empty.Empty.Empty...` — bug noto e ancora aperto
di pywebview, [issue #1815](https://github.com/r0x0r/pywebview/issues/1815)).
Il problema si nota spostando la finestra perché WebView2 può generare un
evento "NavigationCompleted" spurio in quel momento, che rilancia la
scansione da capo.

Già corretto in `api.py`: `set_window()` marca la finestra con
`_serializable = False`, l'escape hatch che pywebview stesso offre per
escludere un oggetto dalla scansione — verificato riproducendo la scansione
reale di pywebview contro la nostra classe `Api` (nessun loop, tutti i
metodi comunque esposti correttamente a JS).

### Linux: traceback "ModuleNotFoundError: No module named 'gi'" all'avvio

pywebview prova sempre GTK prima di Qt a meno che non gli si dica altrimenti
(`webview/guilib.py`), e quel tentativo è un semplice `import gi` senza alcuna
protezione sul rumore in console — stampa un traceback completo anche se poi
ripiega su Qt senza problemi. Dato che il nostro setup Linux di default
installa `pywebview[qt]` e non i binding GTK, quel traceback si presentava a
ogni avvio. `main.py` ora forza `gui="qt"` quando PyQt6 è davvero disponibile
(o sempre, nella build compilata, che lo include sempre) — verificato in
`webview/guilib.py` che con `forced_gui == "qt"` l'ordine di tentativo diventa
`[import_qt, import_gtk]`, e `import_gtk` non viene mai nemmeno raggiunto una
volta che Qt va a buon fine. Se PyQt6 non è disponibile (percorso GTK di
sistema alternativo, vedi sopra), il rilevamento automatico di pywebview resta
intatto.

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

### Windows: "Windows ha protetto il tuo PC" / SmartScreen

`PDFImageMerger.exe` non è firmato digitalmente (firmare un eseguibile
richiede un certificato di code-signing a pagamento, ~70-500€/anno da
un'autorità come DigiCert/Sectigo — non impostato per questo progetto), quindi
Windows SmartScreen lo segnala come proveniente da un "produttore
sconosciuto". Non è un problema del programma: è così per qualunque
eseguibile non firmato. Per eseguirlo comunque: nella finestra di avviso,
clicca **"Informazioni"** poi **"Esegui comunque"**.

Due strade gratuite se si vuole andare oltre il semplice "Esegui comunque":

- **Certificato autofirmato**: gratis, ma elimina l'avviso solo sul PC dove
  importi manualmente il certificato come attendibile — non aiuta per la
  distribuzione ad altri.
  ```powershell
  $cert = New-SelfSignedCertificate -Subject "CN=Il Tuo Nome" -Type CodeSigningCert -CertStoreLocation "Cert:\CurrentUser\My" -KeyExportPolicy Exportable -KeySpec Signature -KeyLength 2048 -KeyAlgorithm RSA -HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears(5)
  $pwd = ConvertTo-SecureString -String "TuaPassword" -Force -AsPlainText
  Export-PfxCertificate -Cert $cert -FilePath "C:\percorso\pdfimagemerger-cert.pfx" -Password $pwd
  # poi rendilo attendibile con Import-Certificate su Cert:\LocalMachine\Root,
  # e firma con: signtool sign /f cert.pfx /p TuaPassword /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\PDFImageMerger.exe
  ```
- **[SignPath Foundation](https://signpath.org/)**: firma gratuita e
  davvero riconosciuta da Windows, ma solo per progetti open source con
  repository pubblico, licenza open source, build verificabile da CI, e
  approvazione manuale per ogni release (giorni/settimane di attesa).

## Struttura del progetto

```
pdf_image_merger/
├── main.py            # bootstrap pywebview + drag&drop nativo (path reali dei file)
├── api.py             # ponte Python <-> JS (pywebview.api.*), stato della lista file
├── pdf_builder.py      # logica pura immagini/PDF (nessuna dipendenza GUI, testabile a sé)
├── build.sh            # build standalone: AppImage su Linux, .exe su Windows (via Git Bash)
├── build.cmd           # come build.sh, ma per il prompt Windows nativo (cmd.exe)
├── pdfimagemerger.spec # spec PyInstaller usato da build.sh
├── VERSION             # unica fonte di verità per la versione (mostrata nel titolo finestra)
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

## Percorsi lunghi su Windows (MAX_PATH)

Windows limita i percorsi file a ~260 caratteri con le API legacy, a meno di
usare il prefisso `\\?\`, che le bypassa incondizionatamente. Con archivi di
immagini annidati su più livelli di cartelle (es. fumetti/manga organizzati per
serie/numero/capitolo) è facile superare quella soglia anche se nessun singolo
nome di file o cartella sembra eccessivo. `pdf_builder.py` applica il prefisso
`\\?\` (o `\\?\UNC\` per i percorsi di rete) ad ogni chiamata reale di I/O
(apertura immagini, stat, lettura byte, elenco cartella, scrittura PDF finale)
— verificato in isolamento con `ntpath` (che riconosce correttamente il
prefisso) e con l'intera suite di regressione su Linux (dove il prefisso è
semplicemente un no-op).

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
- Il toggle "Non modificare le immagini" usa la classe `uk-toggle-switch-primary`
  di Franken UI — senza il modificatore `-primary`/`-destructive`, il CSS
  della libreria muove solo il pallino ma non colora mai la traccia al click.

## Lingua e tema: perché non `localStorage`

Prima di implementare le 6 lingue (inglese, italiano, spagnolo, francese,
cinese semplificato, hindi) e la persistenza del tema, ho verificato leggendo
**ogni** backend in `webview/platforms/*.py` che pywebview di default esegue
il motore webview sottostante in modalità privata/effimera:
`edgechromium.py` chiama `IsInPrivateModeEnabled`, `gtk.py` crea
esplicitamente un "ephemeral context" (`WebContext.new_ephemeral()`), e così
via su ogni piattaforma. Significa che `localStorage` non viene mai scritto
su disco a meno di disattivare esplicitamente questa modalità — la
persistenza del tema che avevo implementato inizialmente con
`localStorage.setItem(...)` non sarebbe quindi sopravvissuta a un riavvio
dell'app. Corretto spostando lingua e tema in un file JSON gestito
direttamente da `settings.py`, in una cartella standard per ogni sistema
operativo (vedi il README principale, sezione "Localization").

Il rilevamento della lingua di sistema (`settings.detect_system_language()`)
usa un approccio diverso per ogni OS invece di un generico
`locale.getlocale()` (che riflette perlopiù la locale C, spesso non
impostata): `GetUserDefaultUILanguage()` via ctypes su Windows, `defaults
read -g AppleLocale` su macOS (le app GUI in bundle `.app` spesso non
erediteno affatto `LANG`/`LC_ALL`, non essendo lanciate da una shell), le
variabili d'ambiente `LANG`/`LC_ALL`/`LANGUAGE` su Linux. I rami Windows e
macOS sono stati verificati solo mockando le rispettive API (nessuna
macchina Windows o Mac disponibile durante lo sviluppo), non su un sistema
reale.

**Verifica del cambio lingua/tema**: fatta pilotando l'app reale (avviata
con `--debug`) tramite il protocollo Chrome DevTools (CDP) via WebSocket —
non con uno screenshot. Ho collegato un piccolo script Node al target CDP
dell'app, simulato il cambio di ciascuna delle 6 lingue e del tema
selezionando davvero gli elementi `<select>` e disparando eventi `change`
reali (fondamentale: chiamare le funzioni interne di `app.js` direttamente
da un contesto esterno NON funziona, perché sono racchiuse nella IIFE di
modulo e irraggiungibili dall'esterno — errore che ho effettivamente commesso
nel primo tentativo, scoprendolo proprio grazie a questa verifica), e letto
il contenuto testuale risultante nel DOM per ciascuna lingua. Verificata
anche la persistenza reale: cambiato il tema, poi richiamato
`get_settings()` da capo (rilettura indipendente dal file su disco) per
confermare che il valore fosse davvero scritto, non solo tenuto in memoria.
