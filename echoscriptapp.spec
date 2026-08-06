# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
#  PyInstaller spec per EchoScript — interfaccia web dentro WebView2.
# =============================================================================
#  Costruzione:  pyinstaller echoscriptapp.spec --noconfirm
#  Risultato:    dist/EchoScript/EchoScript.exe  (+ la cartella _internal/)
#
#  Qui non c'e' nessun motore grafico da impacchettare: WebView2 e' gia'
#  installato su Windows 10 e 11, quindi l'interfaccia sono sette file di testo
#  dentro web/, qualche decina di kilobyte al posto di qualche decina di
#  megabyte.
#
#  Cosa entra: l'host (EchoScriptApp.py), i moduli condivisi, il motore, la
#  pagina web, l'icona e la schermata di avvio, e ffmpeg/ffprobe trovati nel
#  PATH al momento della costruzione, cosi' l'eseguibile e' autosufficiente.
#  PyTorch resta FUORI di proposito: faster-whisper gira su ctranslate2 (CPU) e
#  il riconoscimento della GPU, se non lo trova, degrada senza rompersi.
#
#  NB: i pesi dei modelli Whisper locali NON vengono impacchettati;
#  faster-whisper li scarica da HuggingFace al primo uso e poi li tiene in cache.
# =============================================================================
import os
import shutil
import sys
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.getcwd())

# La barra della schermata di avvio: misure, carattere e colore stanno in
# Shared/avvio.py, che e' anche chi la riempie a programma partito. Prenderle da
# li' invece di ricopiarle qui e' l'unico modo perche' il riempimento cada
# esattamente sul binario disegnato dentro caricamento.png.
sys.path.insert(0, ROOT)
from Shared import avvio as _avvio

# --- ffmpeg + ffprobe, risolti dal PATH al momento della costruzione ---------
binaries = []
for _strumento in ('ffmpeg', 'ffprobe'):
    _percorso = shutil.which(_strumento)
    if _percorso:
        binaries.append((_percorso, '.'))   # nella radice del pacchetto (sul PATH a runtime)

# --- La pagina: e' l'interfaccia, quindi senza non si parte ------------------
datas = [('web', 'web')]

# --- Le immagini: icona della finestra e schermata di avvio ------------------
# Si elencano una per una invece di prendere tutta la cartella, perche' dentro
# assets/ c'e' anche marchio.py, cioe' le istruzioni per disegnarle. Servono a
# chi tocca il disegno, non al programma che gira.
ASSETS = os.path.join(ROOT, 'assets')
ICONA = os.path.join(ASSETS, 'EchoScript.ico')
AVVIO = os.path.join(ASSETS, 'caricamento.png')
for _immagine in (ICONA, AVVIO, os.path.join(ASSETS, 'EchoScript.png')):
    if os.path.isfile(_immagine):
        datas.append((_immagine, 'assets'))

hiddenimports = ['transcriber', 'engine', 'Shared', 'Shared.i18n',
                 'Shared.percorsi', 'Shared.strings_app', 'Shared.avvio']

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
    ['EchoScriptApp.py'],
    pathex=[ROOT, os.path.join(ROOT, 'core')],
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
    # tkinter invece RESTA, anche se nessuna riga del programma lo importa: la
    # schermata di avvio e' disegnata dal bootloader con Tcl/Tk, e le librerie le
    # trova solo se l'analisi le ha raccolte. Una decina di megabyte pagati per
    # non lasciare lo schermo vuoto per mezzo minuto dopo il doppio clic.
    excludes=[
        'torch', 'matplotlib', 'pandas',
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

# --- La schermata di avvio ---------------------------------------------------
# La mostra il bootloader appena parte, prima che esista un interprete Python:
# e' l'unica cosa che copre i secondi fra il doppio clic e la comparsa della
# finestra. A chiuderla e' EchoScriptApp.py, ma solo quando la pagina ha
# davvero dipinto il primo fotogramma: vedi _chiudi_caricamento() la' dentro,
# e il commento sull'ordine dell'avvio in cima a quel file.
#
# La riga di testo qui sotto NON e' un messaggio: e' il riempimento della barra.
# L'immagine porta gia' disegnato il binario vuoto, e il programma ci scrive
# sopra una fila di trattini che cresce a ogni pezzo caricato (Shared/avvio.py).
# Di suo il bootloader ci stamperebbe i nomi dei file che sta estraendo, uno
# dopo l'altro: informazione per chi costruisce il pacchetto, rumore per chi lo
# usa. Il testo iniziale e' vuoto di proposito — finirebbe dentro il file Tcl,
# che Tcl 8.6 rilegge con la codifica di sistema e non in UTF-8, e un trattino
# scritto li' comparirebbe come scarabocchio; gli aggiornamenti successivi
# passano invece da un canale dichiarato UTF-8 e sono sicuri.
caricamento = Splash(
    AVVIO,
    binaries=a.binaries,
    datas=a.datas,
    text_pos=_avvio.POSIZIONE,
    text_size=_avvio.CORPO,
    text_font=_avvio.CARATTERE,
    text_color=_avvio.COLORE,
    text_default=_avvio.barra(0.0),
    minify_script=True,
    always_on_top=False,      # stare davanti a tutto e' da finestra di errore
) if os.path.isfile(AVVIO) else None

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
    *([caricamento] if caricamento else []),
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
    # Tcl/Tk per la schermata di avvio. In modalita' a cartella vanno qui, non
    # nell'EXE: nell'EXE ci va solo l'oggetto Splash.
    *([caricamento.binaries] if caricamento else []),
    strip=False,
    upx=False,
    upx_exclude=[],
    name='EchoScript',
)
