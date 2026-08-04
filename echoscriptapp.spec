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
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.getcwd())

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
                 'Shared.percorsi', 'Shared.strings_app']

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
caricamento = Splash(
    AVVIO,
    binaries=a.binaries,
    datas=a.datas,
    # Senza posizione il bootloader non scrive niente sopra l'immagine.
    # Dandogliela ci stamperebbe i percorsi dei file che sta estraendo, uno
    # dopo l'altro; il nome del programma e' gia' disegnato nell'immagine.
    text_pos=None,
    minify_script=True,
    always_on_top=False,      # stare davanti a tutto e' da finestra di errore
) if os.path.isfile(AVVIO) else None

exe = EXE(
    pyz,
    a.scripts,
    *([caricamento] if caricamento else []),
    [],
    exclude_binaries=True,
    name='EchoScript',
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
