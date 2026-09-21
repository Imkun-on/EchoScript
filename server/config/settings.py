"""Le manopole del programma: tutto cio' che si puo' regolare.

Da dove arrivano i valori
    Ognuno ha un valore di partenza scritto qui, che va bene per la maggior
    parte dei casi. Chi vuole cambiarlo non tocca il codice: mette una riga nel
    file ``.env``, accanto al programma, e da li' in poi vince quella. Una vera
    variabile d'ambiente del sistema vince su entrambi.

    E' il motivo per cui questo file e' pieno di ``_env_str(...)`` invece che di
    valori scritti a mano: ogni riga dice sia quanto vale di suo, sia con quale
    nome la si puo' cambiare da fuori.

I SETTE CHE CAMBIANO MENTRE IL PROGRAMMA GIRA
    ``GROQ_MODEL``, ``GROQ_SUMMARY_MODEL``, ``GROQ_VISION_MODEL``,
    ``OLLAMA_MODEL``, ``OLLAMA_TRANSLATE_MODEL``, ``OLLAMA_VISION_MODEL``,
    ``LANGUAGE``.

    Questi non sono costanti: li riscrivono l'interfaccia e il direttore
    d'orchestra ogni volta che si sceglie qualcosa nei menu.

    Per questo vanno letti SEMPRE cosi'::

        from server.config import settings
        ...
        modello = settings.GROQ_MODEL        # giusto

    e MAI cosi'::

        from server.config.settings import GROQ_MODEL
        ...
        modello = GROQ_MODEL                 # sbagliato

    La seconda forma non da' nessun errore, ed e' proprio questo il problema:
    si porta a casa una fotografia del valore nell'istante dell'import, e da
    quel momento usa sempre quella. Il programma continua a girare tranquillo
    usando il modello che l'utente ha smesso di volere venti minuti prima.

    Con la prima forma si chiede ogni volta all'unico oggetto che custodisce il
    valore, e la risposta e' quella vera.

    Tutti gli altri valori qui dentro non cambiano mai dopo l'avvio, quindi si
    possono tranquillamente importare per nome.
"""
from __future__ import annotations

import os
import sys


# === .env LOADING + CONFIG HELPERS ===========================================
# Load the .env into os.environ at IMPORT time, so the configuration constants
# further down can be overridden WITHOUT editing the code. Values already
# present in the real environment win over the .env file.
def _env_candidates() -> list[str]:
    """Dove cercare il .env, nell'ordine in cui vince chi arriva prima.

    Da sorgenti c'è un posto solo: accanto a questo file. Dentro l'eseguibile
    ce ne sono due, e non sono equivalenti.

    Il primo è la cartella dell'.exe, cioè, dopo l'installazione, quella che
    l'installatore apre da «Programs/EchoScript» dentro %LOCALAPPDATA%. È
    l'unico che una persona sappia trovare («apri la cartella del programma»),
    ed è l'unico che sopravvive a un aggiornamento: l'installazione rifà
    `_internal` da zero ogni volta.

    Il secondo è accanto a questo file, che da impacchettati sta dentro
    `_internal`. Resta solo per non rompere chi ci aveva già messo il suo .env
    quando quello era l'unico posto in cui il programma guardava."""
    accanto_al_file = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        accanto_all_exe = os.path.dirname(os.path.abspath(sys.executable))
        return [os.path.join(accanto_all_exe, ".env"),
                os.path.join(accanto_al_file, ".env")]
    return [os.path.join(accanto_al_file, ".env")]


def _load_env_file() -> None:
    """Legge il file .env e mette i suoi valori fra le variabili d'ambiente.

    Perche' i valori del file NON sovrascrivono quelli gia' presenti
        Perche' l'ordine di precedenza deve essere prevedibile, e quello
        sensato e': chi e' piu' vicino al momento in cui si lancia il
        programma, vince.

        Una variabile scritta nel terminale un secondo prima di lanciare e'
        l'intenzione piu' recente di chi sta usando il programma. Il file .env
        e' una preferenza scritta settimane fa e dimenticata. Se il file
        vincesse, non ci sarebbe modo di fare una prova al volo con un valore
        diverso senza modificare il file e poi ricordarsi di rimetterlo com'era.

    Perche' tollera righe scritte in tanti modi
        Perche' un .env viene scritto a mano, spesso copiando da un esempio.
        Le righe vuote e i commenti si saltano, la parola `export` davanti (che
        serve su Linux e su Windows non vuol dire niente) si ignora, e le
        virgolette intorno al valore si tolgono.

        Una riga senza segno di uguale viene semplicemente saltata invece di
        far fallire tutto: un file .env scritto male non deve impedire al
        programma di partire.
    """
    for env_path in _env_candidates():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[len("export "):]
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
        except OSError:
            continue


def _env_str(key: str, default: str) -> str:
    """Una manopola di testo: il valore scritto fuori, o quello di partenza.

    Assente e vuoto contano come la stessa cosa. E' voluto: chi scrive
    `ECHOSCRIPT_QUALCOSA=` nel file .env quasi sempre sta cancellando la
    propria scelta, non chiedendo una stringa vuota.
    """
    v = os.environ.get(key, "").strip()
    return v if v else default


def _env_int(key: str, default: int) -> int:
    """Una manopola numerica, con il valore di partenza se non si capisce.

    Un valore illeggibile non fa cadere il programma: si usa quello di
    partenza. Il motivo e' che questi valori li scrive una persona a mano in un
    file di testo, e un errore di battitura li' dentro non deve impedire di
    trascrivere un video.
    """
    try:
        return int(os.environ.get(key, "").strip())
    except (ValueError, TypeError):
        return default


def _env_opt(key: str) -> str | None:
    """Una manopola che puo' anche non esserci, e allora vale None.

    Diversa da _env_str perche' qui NON esiste un valore di partenza: l'assenza
    e' essa stessa un'informazione. La lingua dell'audio ne e' l'esempio: None
    vuol dire «riconoscila da sola», che e' una richiesta precisa e non la
    mancanza di una richiesta.
    """
    v = os.environ.get(key, "").strip()
    return v or None


def _env_bool(key: str, default: bool) -> bool:
    """Una manopola acceso/spento.

    Accetta parecchi modi di dire «si'» perche' chi scrive un file .env a mano
    usa quello che gli viene in mente: 1, true, yes, on, e anche si e si'
    accentato, che a scriverli in italiano vengono naturali.

    Qualunque altra cosa conta come «no». Non e' distrazione: fra il dubbio di
    aver capito male e l'accendere una funzione che costa crediti, conviene non
    accenderla.
    """
    v = os.environ.get(key, "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on", "si", "sì")


# === CONFIGURATION (every value overridable from .env) =======================
# The program's "knobs". Each has a sensible default but can be tuned from a .env
# entry / environment variable, so users never need to edit this file.
_load_env_file()

# Whisper model on Groq: "turbo" is very fast and cheap. Alternatives:
# "whisper-large-v3" (more accurate/slower), "distil-whisper-large-v3-en" (EN only).
GROQ_MODEL = _env_str("ECHOSCRIPT_GROQ_MODEL", "whisper-large-v3-turbo")

# Modelli di trascrizione Groq SELEZIONABILI dall'utente (GUI e CLI): entrambi
# multilingua. 'turbo' = miglior rapporto prezzo/velocità (default); 'large-v3' =
# più accurato ma ~2,8× più costoso. Il primo è il default. (Il distil, solo
# inglese, resta impostabile via ECHOSCRIPT_GROQ_MODEL ma non è nel selettore.)
GROQ_TRANSCRIBE_MODELS = ("whisper-large-v3-turbo", "whisper-large-v3")

# Audio/video extensions accepted as LOCAL sources (phone recordings, PC files,
# video files from which ffmpeg extracts the audio track). ffmpeg reads all of
# these; anything not listed is still attempted but with a gentle warning.
AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".m4b", ".wav", ".ogg", ".oga", ".opus", ".aac", ".flac",
    ".wma", ".aiff", ".aif", ".amr", ".3gp", ".caf",          # audio
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",          # video (audio extracted)
}

CHUNK_SECONDS = _env_int("ECHOSCRIPT_CHUNK_SECONDS", 600)      # seconds per audio chunk (10 min)
AUDIO_SAMPLE_RATE = _env_int("ECHOSCRIPT_SAMPLE_RATE", 16000)  # 16 kHz: recommended for Whisper
AUDIO_BITRATE = _env_str("ECHOSCRIPT_BITRATE", "64k")          # chunk bitrate (low is fine for speech)
MAX_RETRIES = _env_int("ECHOSCRIPT_MAX_RETRIES", 3)            # attempts per chunk before giving up
# Audio language: None = auto-detect (Whisper). Force with e.g. "it"/"en" via the
# ECHOSCRIPT_AUDIO_LANG env var or, per-run, the GUI/CLI selector.
# Il valore che vuol dire "usa quella scritta qui sopra".
#
# Serve perche' None e' gia' preso: None significa "riconosci da sola che
# lingua e'". Senza un terzo valore non ci sarebbe modo di distinguere
# "lasciami decidere" da "non lo so", che sono due richieste diverse.
_USE_CONFIG = object()

LANGUAGE = _env_opt("ECHOSCRIPT_AUDIO_LANG")
# Word-level timestamps: ask Groq/faster-whisper for per-WORD timings (enables
# precise subtitles later). On by default; disable with ECHOSCRIPT_WORD_TIMESTAMPS=0.
WORD_TIMESTAMPS = _env_bool("ECHOSCRIPT_WORD_TIMESTAMPS", True)

# --- LOCAL backend (faster-whisper) ---
# Device: "auto" picks CUDA (GPU) when available, else CPU. compute_type "" means
# "auto" (float16 on GPU, int8 on CPU); both can be forced via .env.
LOCAL_DEVICE = _env_str("ECHOSCRIPT_DEVICE", "auto")
LOCAL_COMPUTE_TYPE = _env_str("ECHOSCRIPT_COMPUTE_TYPE", "")
# Local models selectable in the panel (number -> (model_name, description)).
# Bigger = more accurate but slower on CPU. The time estimates are for a video
# of ~2 hours without a GPU and are indicative (they depend on your processor).
LOCAL_MODELS = {
    "1": ("base",           "veloce (~5-12 min/2h), meno accurato"),
    "2": ("small",          "equilibrio consigliato (~10-25 min/2h)"),
    "3": ("medium",         "piu' accurato ma lento (~30-60 min/2h)"),
    "4": ("large-v3",       "massima accuratezza, MOLTO lento (1-2h+/2h)"),
    "5": ("large-v3-turbo", "quasi 'large', piu' veloce: buon compromesso CPU"),
}

# --- SUMMARY (riassunto via LLM) ---
# Dopo la traduzione si genera un riassunto pulito del testo italiano (toglie
# intercalari "ehm/uhm", ripetizioni, autocorrezioni). Due motori:
#   • Groq (cloud): usato quando il backend è Groq (chiave già disponibile),
#     tramite un modello di CHAT (non Whisper). Velocissimo.
#   • Ollama (locale): usato quando il backend è locale, per restare 100%
#     offline. Richiede Ollama installato e avviato (https://ollama.com) con un
#     modello scaricato (es. `ollama pull llama3.1:8b`).
# Default: gpt-oss-120b (Production; sostituto del deprecato llama-3.3-70b-versatile,
# spento da Groq il 16 ago 2026 per i tier free/developer). Più economico e stabile.
GROQ_SUMMARY_MODEL = _env_str("ECHOSCRIPT_GROQ_SUMMARY_MODEL", "openai/gpt-oss-120b")
# Modelli di CHAT Groq selezionabili (riassunto + traduzione lato cloud). Sono
# l'equivalente in nuvola di OLLAMA_TEXT_MODELS: catalogo corto e curato, perché
# è la scelta di chi ha detto "fai tutto sui server" e vuole solo decidere quanto
# spendere. Qualunque altro modello resta imponibile da .env.
GROQ_TEXT_MODELS = {
    "1": ("openai/gpt-oss-120b", "qualità piena (default)"),
    "2": ("openai/gpt-oss-20b",  "più economico e rapido"),
}
OLLAMA_MODEL = _env_str("ECHOSCRIPT_OLLAMA_MODEL", "qwen2.5:7b")
# Modello Ollama per la TRADUZIONE locale (vedi più sotto). Di default riusa lo
# stesso del riassunto, così basta scaricarne uno solo per restare 100% offline.
OLLAMA_TRANSLATE_MODEL = _env_str("ECHOSCRIPT_OLLAMA_TRANSLATE_MODEL", OLLAMA_MODEL)
OLLAMA_HOST = _env_str("ECHOSCRIPT_OLLAMA_HOST", "http://localhost:11434")
# Finestra di contesto per Ollama. ATTENZIONE: di default Ollama usa solo 2048
# token e TRONCA in silenzio gli input più lunghi (rovinando i riassunti dei
# video lunghi). Lo alziamo per far entrare un blocco intero (~SUMMARY_MAX_CHARS)
# + prompt + risposta. 8192 è un buon compromisso qualità/RAM su 7-8B.
OLLAMA_NUM_CTX = _env_int("ECHOSCRIPT_OLLAMA_NUM_CTX", 8192)
# Oltre questa lunghezza (caratteri) una sezione viene riassunta a blocchi e poi
# i parziali vengono uniti (map-reduce), per non sforare il contesto del modello.
SUMMARY_MAX_CHARS = _env_int("ECHOSCRIPT_SUMMARY_MAX_CHARS", 12000)

# --- ANALISI VISIVA (vision) — trascrive ciò che si VEDE nel video ---
# Oltre all'audio, EchoScript può "guardare" i fotogrammi di un video (slide,
# codice a schermo, formule, grafici, diagrammi) ed estrarne il contenuto con un
# modello multimodale, per arricchire il riassunto. È OPZIONALE (chiesto a ogni
# run su sorgenti video) e usa gli stessi due motori del resto del programma:
#   • Groq (cloud): modello vision di GroqCloud (veloce; consuma crediti/frame).
#   • Ollama (locale): modello vision via Ollama (100% offline; richiede
#     `ollama pull <modello-vision>`, es. llama3.2-vision).
# Estensioni con traccia VIDEO (da cui ha senso estrarre i fotogrammi).
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
# Modello vision su Groq. Default: qwen3.6-27b (multimodale; sostituto del
# deprecato llama-4-scout). Cambiabile da .env.
GROQ_VISION_MODEL = _env_str("ECHOSCRIPT_GROQ_VISION_MODEL", "qwen/qwen3.6-27b")
# Modelli vision Groq selezionabili, come sopra per il testo.
GROQ_VISION_MODELS = {
    "1": ("qwen/qwen3.6-27b", "multimodale, buon OCR (default)"),
}
# Modello vision su Ollama (locale). Scaricalo con: ollama pull llama3.2-vision
OLLAMA_VISION_MODEL = _env_str("ECHOSCRIPT_OLLAMA_VISION_MODEL", "llama3.2-vision")

# --- Modelli Ollama proposti nei pannelli di scelta (CLI e GUI) ---
# Numero -> (nome modello, RAM indicativa richiesta, descrizione). Il pannello
# segna quelli GIÀ scaricati (letti da /api/tags) e accetta anche un nome
# digitato a mano; .env resta la via per forzare un modello qualunque.
# TESTO = riassunto + traduzione in locale (backend locale, niente chiave Groq).
OLLAMA_TEXT_MODELS = {
    "1": ("qwen3:4b",    "~4 GB",  "leggero e moderno: ideale con 8 GB di RAM"),
    "2": ("qwen2.5:7b",  "~6 GB",  "equilibrio qualità/peso (default)"),
    "3": ("qwen3:8b",    "~7 GB",  "più accurato (12-16 GB di RAM)"),
    "4": ("gemma3:12b",  "~10 GB", "ottimo multilingua (16 GB di RAM)"),
    "5": ("gpt-oss:20b", "~16 GB", "qualità vicina al cloud (24 GB+ o GPU)"),
}
# VISION = analisi visiva dei fotogrammi in locale.
OLLAMA_VISION_MODELS = {
    "1": ("qwen2.5vl:3b",    "~4 GB",  "leggero, ottimo OCR: ideale con 8 GB di RAM"),
    "2": ("gemma3:4b",       "~4 GB",  "multimodale leggero, buon multilingua"),
    "3": ("qwen2.5vl:7b",    "~7 GB",  "buon equilibrio (12-16 GB di RAM)"),
    "4": ("llama3.2-vision", "~9 GB",  "default storico (16 GB di RAM)"),
    "5": ("qwen2.5vl:32b",   "~24 GB", "qualità vicina al cloud (32 GB+ o GPU)"),
}
# Soglia di "cambio scena" (0..1) per scegliere i fotogrammi: più è bassa, più
# fotogrammi (e più analisi/costo). 0.4 cattura bene i cambi di slide/codice.
VISION_SCENE_THRESHOLD = float(_env_str("ECHOSCRIPT_VISION_SCENE", "0.4"))
# Larghezza (px) a cui ridimensionare i fotogrammi prima dell'analisi (riduce
# token/banda; l'altezza resta proporzionale).
VISION_FRAME_WIDTH = _env_int("ECHOSCRIPT_VISION_WIDTH", 1280)
# Tetto massimo di fotogrammi analizzati per video (controlla costo/tempo): se il
# rilevamento scene ne trova di più, vengono campionati uniformemente.
VISION_MAX_FRAMES = _env_int("ECHOSCRIPT_VISION_MAX_FRAMES", 60)
# Se il rilevamento scene trova troppi pochi fotogrammi (video con un'unica
# inquadratura fissa), si campiona a intervalli regolari ogni N secondi.
VISION_FALLBACK_INTERVAL = _env_int("ECHOSCRIPT_VISION_INTERVAL", 45)
# Distanza minima (secondi) tra due fotogrammi chiave. Il rilevamento scene di
# ffmpeg spesso scatta DUE volte sulla stessa transizione (un frame a metà stacco
# + uno assestato), generando coppie ravvicinate ridondanti — spesso una è lo
# shot largo "dove non si vede nulla". Raggruppiamo i frame entro questa finestra
# e teniamo l'ULTIMO del gruppo (lo stato assestato, più leggibile). 0 disattiva.
VISION_MIN_GAP = _env_int("ECHOSCRIPT_VISION_MIN_GAP", 8)
# Risoluzione massima del video scaricato da YouTube per l'analisi visiva (più
# bassa = download più leggero). Usata solo quando l'analisi è attiva.
VISION_YT_MAX_HEIGHT = _env_int("ECHOSCRIPT_VISION_YT_HEIGHT", 720)

# --- PDF "ricco" (formule LaTeX + mappe Mermaid DISEGNATE) ---
# Il PDF base (fpdf2) è testo semplice: mostra le formule come `$...$` grezzo e i
# blocchi mermaid come testo. Per un PDF in cui formule e mappe sono davvero
# renderizzate, generiamo un HTML (MathJax + Mermaid) e lo stampiamo con un
# browser Chromium GIÀ presente sul sistema (Edge su Windows): nessun LaTeX da
# installare. Se manca il browser o la rete (serve solo la prima volta, per
# scaricare le due librerie JS in cache locale), si ripiega in automatico sul PDF
# fpdf2. Disattivabile con ECHOSCRIPT_RICH_PDF=0.
RICH_PDF = _env_bool("ECHOSCRIPT_RICH_PDF", True)
# Percorso a un browser Chromium specifico (altrimenti rilevato in automatico).
BROWSER_PATH = _env_opt("ECHOSCRIPT_BROWSER")

# Mappa concettuale (diagramma Mermaid) nel riassunto dei video con analisi
# visiva. Disattivata di default: spesso è banale/ridondante rispetto al testo e
# i diagrammi generati da un LLM sono la parte meno affidabile. Codice e formule
# restano comunque (sono il vero valore). Attivala con ECHOSCRIPT_CONCEPT_MAP=1.
CONCEPT_MAP = _env_bool("ECHOSCRIPT_CONCEPT_MAP", False)
# Mostra i FOTOGRAMMI anche dentro il riassunto (oltre che nel documento di
# analisi visiva), accanto al testo, raggruppati per sezione/timestamp. Costo
# Groq aggiuntivo: ZERO (i frame esistono già). Disattiva con ECHOSCRIPT_SUMMARY_FRAMES=0.
SUMMARY_FRAMES = _env_bool("ECHOSCRIPT_SUMMARY_FRAMES", True)
