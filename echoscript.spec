# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
#  PyInstaller spec per EchoScript — interfaccia web dentro WebView2.
# =============================================================================
#  Costruzione:  pyinstaller echoscript.spec --noconfirm
#  Risultato:    dist/EchoScript/EchoScript.exe  (+ la cartella _internal/)
#
#  Qui non c'e' nessun motore grafico da impacchettare: WebView2 e' gia'
#  installato su Windows 10 e 11, quindi l'interfaccia sono sette file di testo
#  dentro client/, qualche decina di kilobyte al posto di qualche decina
#  megabyte.
#
#  Cosa entra: il punto d'ingresso (EchoScript.py), i moduli del server, la
#  pagina, l'icona, e ffmpeg/ffprobe trovati nel PATH al momento della
#  costruzione, cosi' l'eseguibile e' autosufficiente.
#
#  Cosa NON entra piu': la schermata di avvio disegnata da PyInstaller, e con
#  lei Tcl/Tk. Adesso l'attesa la copre la pagina stessa, che sta a schermo
#  intero e ha una barra che scorre davvero.
#  PyTorch resta FUORI di proposito: faster-whisper gira su ctranslate2 (CPU) e
#  il riconoscimento della GPU, se non lo trova, degrada senza rompersi.
#
#  NB: i pesi dei modelli Whisper locali NON vengono impacchettati;
#  faster-whisper li scarica da HuggingFace al primo uso e poi li tiene in cache.
# =============================================================================
import os
import shutil
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.getcwd())

# --- ffmpeg + ffprobe, risolti dal PATH al momento della costruzione ---------
binaries = []
for _strumento in ('ffmpeg', 'ffprobe'):
    _percorso = shutil.which(_strumento)
    if _percorso:
        binaries.append((_percorso, '.'))   # nella radice del pacchetto (sul PATH a runtime)

# --- La pagina: e' l'interfaccia, quindi senza non si parte ------------------
datas = [('client', 'client')]

# --- Le immagini: icona della finestra e schermata di avvio ------------------
# Si elencano una per una invece di prendere tutta la cartella, perche' dentro
# assets/ c'e' anche marchio.py, cioe' le istruzioni per disegnarle. Servono a
# chi tocca il disegno, non al programma che gira.
ASSETS = os.path.join(ROOT, 'assets')
ICONA = os.path.join(ASSETS, 'EchoScript.ico')
for _immagine in (ICONA, os.path.join(ASSETS, 'EchoScript.png')):
    if os.path.isfile(_immagine):
        datas.append((_immagine, 'assets'))

hiddenimports = ['transcriber',
                 'server',
                 'server.config', 'server.config.i18n',
                 'server.config.messages', 'server.config.paths',
                 'server.config.settings',
                 'server.config.strings',
                 'server.controllers', 'server.controllers.api',
                 'server.controllers.bridge',
                 'server.services', 'server.services.pipeline',
                 'server.sources', 'server.sources.download',
                 'server.sources.metadata',
                 'server.transcription', 'server.transcription.audio',
                 'server.enrichment', 'server.enrichment.summary',
                 'server.enrichment.translation',
                 'server.export', 'server.export.document',
                 'server.export.pdf_basic',
                 'server.state', 'server.state.checkpoints',
                 'server.state.credits', 'server.state.jobs',
                 'server.utils', 'server.utils.contract',
                 'server.utils.ffmpeg', 'server.utils.media',
                 'server.utils.ollama',
                 'server.utils.text']

for _pacchetto in ('webview', 'faster_whisper', 'av', 'ctranslate2',
                   'onnxruntime', 'tokenizers', 'huggingface_hub', 'yt_dlp',
                   'groq', 'fpdf', 'rich', 'deep_translator'):
    try:
        _d, _b, _h = collect_all(_pacchetto)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        pass

a = Analysis(
    ['EchoScript.py'],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # ── Cosa NON deve entrare ────────────────────────────────────────────────
    #
    # Questa lista non e' prudenza, e' meta' del peso del pacchetto. I
    # collect_all qui sopra raccolgono TUTTI i sottomoduli di ogni pacchetto,
    # compresi quelli che esistono solo per integrarsi con librerie che qui
    # nessuno usa; l'analisi li segue e si porta dietro mezzo ambiente Python
    # della macchina che costruisce. Misurato su una build vera: 1360 MB, di cui
    # circa 500 di roba mai importata.
    #
    # Qt e' la voce singola piu' pesante, 628 MB. Ci arriva da pywebview, che
    # porta un backend per ogni sistema e in quello Qt importa PySide6. Su
    # Windows pywebview usa winforms con WebView2, quindi webview/platforms/qt.py
    # resta nel pacchetto ma non verra' mai importato: e' la stessa situazione di
    # una macchina senza PySide6, che pywebview gestisce da se'.
    #
    # Gli altri arrivano dalle integrazioni facoltative di huggingface_hub.
    # faster-whisper importa soltanto av, ctranslate2, huggingface_hub, numpy,
    # onnxruntime, tokenizers e tqdm: nessuno di questi nomi compare fra i suoi
    # import, e infatti toglierli non cambia una riga di comportamento.
    #
    # tkinter c'era, e adesso se ne va. Stava dentro per un motivo solo: la
    # schermata di avvio era disegnata dall'avviatore di PyInstaller con Tcl/Tk,
    # e quelle librerie ci finivano solo se l'analisi le raccoglieva. Adesso la
    # schermata di avvio e' la pagina stessa, quindi sono una decina di megabyte
    # che non servono piu' a niente.
    excludes=[
        'torch', 'matplotlib', 'pandas',
        # Tcl/Tk: serviva alla vecchia schermata di avvio, che non c'e' piu'
        'tkinter', '_tkinter', 'Tkinter',
        # Qt, via pywebview
        'PySide6', 'shiboken6', 'PyQt5', 'PyQt6', 'qtpy',
        # integrazioni facoltative di huggingface_hub
        'cv2', 'nltk', 'pyarrow', 'transformers', 'datasets', 'scipy',
        'numba', 'llvmlite', 'sklearn', 'sympy', 'tensorflow', 'jax',
        'IPython', 'jedi',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

# --- Il manifest: la scala dello schermo dichiarata SUBITO -------------------
# E' il manifest predefinito di PyInstaller con una riga in piu': <dpiAware>.
#
# Serve a togliere un difetto che si vedeva a occhio nudo. pywebview, quando
# avvia la finestra, chiama SetProcessDPIAware(): da quel momento il programma
# dichiara di sapersi disegnare da se' alla scala dello schermo. Finche' non lo
# dichiara, e' Windows a stirargli le finestre — su uno schermo al 125% la
# schermata di avvio da 440x260 veniva mostrata a 550x325, ingrandita e quindi
# sfocata. Nell'istante della dichiarazione lo stiramento cessa e la finestra
# SCATTA alla misura vera, ri-centrandosi: un ridimensionamento improvviso in
# mezzo all'avvio, misurato al secondo 3,7 su questa macchina.
#
# Dichiarandolo qui vale dal primo istante, prima ancora che esista un
# interprete Python: la schermata di avvio nasce gia' della misura giusta e non
# si muove piu'. Lo stato finale del programma non cambia di nulla — e' lo
# stesso che pywebview imposta comunque — cambia solo QUANDO viene raggiunto.
#
# longPathAware resta: senza, i percorsi oltre i 260 caratteri (titoli di video
# lunghi) tornerebbero a fallire.
MANIFEST = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="asInvoker" uiAccess="false"></requestedExecutionLevel>
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{e2011457-1546-43c5-a5fe-008deee3d3f0}"></supportedOS>
      <supportedOS Id="{35138b9a-5d96-4fbd-8e2d-a2440225f93a}"></supportedOS>
      <supportedOS Id="{4a2f28e3-53b9-4441-ba9c-d69d4a4a6e38}"></supportedOS>
      <supportedOS Id="{1f676c76-80e1-4239-95bb-83d0f6d0da78}"></supportedOS>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"></supportedOS>
    </application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true</dpiAware>
    </windowsSettings>
  </application>
  <dependency>
    <dependentAssembly>
      <assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"></assemblyIdentity>
    </dependentAssembly>
  </dependency>
</assembly>
"""

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EchoScript',
    manifest=MANIFEST,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # applicazione con finestra: niente console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICONA if os.path.isfile(ICONA) else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='EchoScript',
)
