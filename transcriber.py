# =============================================================================
#  EchoScript — fast transcription of YouTube videos with Groq (Whisper) or local
# =============================================================================
#  HOW IT WORKS, IN BRIEF (for first-time readers):
#
#  The program turns a YouTube video into written TEXT, in 4 phases:
#
#    PHASE 0 - INFO:
#        you paste the URL and ONLY the video metadata is downloaded (title,
#        channel, views, date, duration, chapters). No heavy download: it is
#        only used to display them and ask for confirmation.
#
#    PHASE 1 - AUDIO DOWNLOAD (yt-dlp):
#        only the audio track is downloaded (not the video: much lighter).
#
#    PHASE 2 - PREPARATION (ffmpeg):
#        the audio is re-encoded to 16 kHz mono (the format Whisper prefers)
#        and SPLIT into chunks of ~10 minutes. Splitting serves both to stay
#        within the API size limits and to provide a meaningful progress bar.
#
#    PHASE 3 - TRANSCRIPTION (Groq / Whisper):
#        each chunk is sent to the Groq API, which returns the text along with
#        the timestamps of each sentence ("segments"). The timestamps of each
#        chunk are "shifted" forward by the point where the chunk starts, so
#        that in the end the timings are correct relative to the whole video.
#
#    OUTPUT:
#        a .md file with the text, the per-sentence timing and — if the video
#        has YouTube CHAPTERS — the text divided into sections.
#
#  PRIVACY: Groq is a CLOUD service. The audio is uploaded to their servers
#  for transcription: it is NOT all local. For public videos this is perfectly
#  fine; for private audio consider a local backend (e.g. faster-whisper on CPU).
#
#  The whole interface is text-based and colored with the "rich" library.
# =============================================================================

# `from __future__ import annotations` makes type annotations "strings" that are
# evaluated lazily: it allows writing modern types (e.g. "dict | None") even on
# older Python versions without runtime errors.
from __future__ import annotations

# --- Python standard library (already included, no installation) ---
import os                                          # environment variables, paths, files
import re                                          # regular expressions (file name cleanup)
import json                                        # export in .json format (for RAG/other LLMs)
import sys                                         # clean exit from the program
import signal                                      # intercept Ctrl+C
import shutil                                      # find the ffmpeg executable in PATH
import tempfile                                    # temporary folder for the audio
import subprocess                                  # launch ffmpeg/ffprobe as external processes
from datetime import datetime                      # format the publication date

# --- External libraries (see requirements.txt) ---
import yt_dlp                                       # downloads audio and metadata from YouTube
from groq import Groq                               # official Groq API client (Whisper)

# --- "rich": the library that draws the colored interface in the terminal ---
from rich.align import Align                        # center the banner
from rich.box import DOUBLE, ROUNDED, HEAVY         # border styles for the boxes
from rich.columns import Columns                    # to place several boxes side by side (cards)
from rich.console import Console, Group             # console + grouping several elements
from rich.panel import Panel                        # the "boxes" with border and title
from rich.rule import Rule                          # elegant divider lines
from rich.progress import (                         # the progress bars and their columns
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn,
    DownloadColumn, TransferSpeedColumn, MofNCompleteColumn,
)
from rich.style import Style                        # colors/bold (banner gradient)
from rich.table import Table                        # tables (video info card)
from rich.text import Text                          # text with multiple styles
from rich.theme import Theme                        # palette of reusable styles (info, error, ...)

# On Windows the default output may be cp1252, which cannot encode the symbols/
# emoji used in the interface (✓ ✗ ✂ ✎ ...). We force UTF-8 so the program never
# crashes due to encoding errors, even if the output is redirected to a file or
# to a "legacy" console. reconfigure has existed since Python 3.7.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# When running as a PyInstaller bundle (.exe), make the bundled ffmpeg/ffprobe
# discoverable by prepending the bundle directory to PATH, so shutil.which() and
# the subprocess calls find them without the user having ffmpeg installed.
if getattr(sys, "frozen", False):
    _bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.environ["PATH"] = _bundle_dir + os.pathsep + os.environ.get("PATH", "")

# === CONSOLE AND THEME ===
# We define a small palette of style names so that in the rest of the code we
# write [info]...[/info] instead of repeating the colors everywhere.
_theme = Theme({
    "info": "bright_cyan",
    "success": "bright_green",
    "warning": "yellow",
    "error": "bold red",
    "title": "bold bright_cyan",
    "phase": "bold bright_blue",
    "dim_label": "dim",
})
console = Console(theme=_theme)

# Symbols used in messages (✓ ✗ → •). Keeping them here makes them easy to change.
SYM_OK, SYM_FAIL, SYM_ARROW, SYM_DOT = "✓", "✗", "→", "•"


# === .env LOADING + CONFIG HELPERS ===========================================
# Load the .env (next to this file) into os.environ at IMPORT time, so the
# configuration constants further down can be overridden WITHOUT editing the
# code. Values already present in the real environment win over the .env file.
def _load_env_file() -> None:
    """Read KEY=value lines from a sibling .env into os.environ (no overwrite)."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
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
        pass


def _env_str(key: str, default: str) -> str:
    """Read a string env var; blank/absent -> the default."""
    v = os.environ.get(key, "").strip()
    return v if v else default


def _env_int(key: str, default: int) -> int:
    """Read an integer env var; invalid/absent -> the default."""
    try:
        return int(os.environ.get(key, "").strip())
    except (ValueError, TypeError):
        return default


def _env_opt(key: str) -> str | None:
    """Read an OPTIONAL string env var; blank/absent -> None."""
    v = os.environ.get(key, "").strip()
    return v or None


def _env_bool(key: str, default: bool) -> bool:
    """Read a boolean env var ('1/true/yes/on'); blank/absent -> the default."""
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

# === GRACEFUL SHUTDOWN ===
# A flag that becomes True on the first Ctrl+C: the loops check it to stop in an
# orderly way. On the second Ctrl+C we exit immediately.
_interrupted = False


def _signal_handler(signum, frame):
    """Called automatically when the user presses Ctrl+C."""
    global _interrupted
    if _interrupted:
        console.print("\n[error]Interruzione forzata.[/error]")
        os._exit(1)
    _interrupted = True
    console.print("\n[warning]Interruzione richiesta, completo il passaggio in corso...[/warning]")


# === BANNER ===

def _print_banner() -> None:
    """Print the startup ASCII banner with a color gradient effect.

    It is purely aesthetic. Each line is colored with a different color taken in
    rotation from the `colors` list, giving the gradient effect (as in your
    Scraper). The "%" (modulo) operator makes the index wrap around if there are
    more lines than available colors."""
    banner_lines = [
        r"  ______                                _ __              ___             ___     ",
        r" /_  __/________ _____  _______________(_) /_  ___       /   | __  ______/ (_)___ ",
        r"  / / / ___/ __ `/ __ \/ ___/ ___/ ___/ / __ \/ _ \     / /| |/ / / / __  / / __ \ ",
        r" / / / /  / /_/ / / / (__  ) /__/ /  / / /_/ /  __/    / ___ / /_/ / /_/ / / /_/ /",
        r"/_/ /_/   \__,_/_/ /_/____/\___/_/  /_/_.___/\___/____/_/  |_\__,_/\__,_/_/\____/ ",
        r"                                                /_____/                           ",
    ]
    colors = ["bright_red", "bright_magenta", "magenta", "bright_blue", "bright_cyan", "cyan"]
    # We equalize the length of all the lines (padding with spaces on the right):
    # this way the block is a perfect rectangle and, centered as a single block,
    # does not look "crooked". no_wrap prevents the art from being broken on
    # narrow terminals.
    width = max(len(line) for line in banner_lines)
    text = Text(no_wrap=True)
    for i, line in enumerate(banner_lines):
        # "\n" between one line and the next but not after the last one (no trailing empty line).
        suffix = "\n" if i < len(banner_lines) - 1 else ""
        text.append(line.ljust(width) + suffix, style=Style(color=colors[i % len(colors)], bold=True))

    console.print()
    console.print(Panel(
        Align.center(text),
        border_style="bright_magenta",
        box=DOUBLE,
        padding=(1, 2),
        expand=False,
    ))


# === FORMATTING UTILITIES ===

def _format_duration(seconds) -> str:
    """Convert a number of seconds into 'H:MM:SS' (or 'M:SS' if under an hour).

    E.g. 3725 -> '1:02:05'. If the value is not a valid number, returns '?'."""
    try:
        seconds = int(seconds)
    except (ValueError, TypeError):
        return "?"
    h, rem = divmod(seconds, 3600)   # divmod returns (quotient, remainder)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _format_timestamp(seconds: float) -> str:
    """Convert seconds (including decimals) into 'HH:MM:SS' for the timings in the text.

    E.g. 75.4 -> '00:01:15'. Used in front of every transcribed sentence."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_views(value) -> str:
    """Format the view count using the dot as the thousands separator (IT style).

    E.g. 1234567 -> '1.234.567'. If it is not a valid number, returns it as is."""
    try:
        return f"{int(value):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(value) if value not in (None, "") else "?"


def _format_upload_date(raw) -> str:
    """yt-dlp provides the date as a 'YYYYMMDD' string (e.g. '20240115').

    Here we transform it into 'DD/MM/YYYY'. If the format is not the expected
    one, we return the raw value without crashing."""
    if not raw:
        return "?"
    try:
        return datetime.strptime(str(raw), "%Y%m%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(raw)


def _safe_filename(name: str) -> str:
    """Clean up a title so that it is a valid file name on Windows.

    Replaces the forbidden characters (\\ / : * ? \" < > |) with an underscore and
    shortens overly long titles, so as not to break the filesystem."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name.strip()[:120] or "trascrizione"


def _lp(path: str) -> str:
    """Restituisce il percorso in forma 'extended-length' (prefisso \\\\?\\) su
    Windows, così le operazioni su file non incappano nel vecchio limite di 260
    caratteri (MAX_PATH): con titoli lunghi il percorso completo può superarlo e
    open()/makedirs falliscono con FileNotFoundError. No-op su altri sistemi o se
    il prefisso è già presente. Richiede un percorso ASSOLUTO con backslash, che
    os.path.abspath garantisce su Windows."""
    if os.name != "nt":
        return path
    abs_path = os.path.abspath(path)
    if abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):          # percorso di rete \\server\share
        return "\\\\?\\UNC" + abs_path[1:]   # -> \\?\UNC\server\share
    return "\\\\?\\" + abs_path


# === RATE LIMIT + CHECKPOINT (ripresa dei video lunghi su Groq) =============

class MediaError(Exception):
    """Errore nelle funzioni media condivise (download, split, trascrizione locale).

    Le funzioni "core" di questo modulo sono SENZA interfaccia: non stampano e
    non decidono cosa mostrare, segnalano il guasto sollevando questa eccezione.
    Chi chiama la traduce nella propria UI: la CLI la cattura nei wrapper
    `_cli_*` (stampa in rosso e restituisce None), il motore la riavvolge in
    `EngineError` per la GUI."""


def _noop_progress(phase, current, total, detail=""):  # pragma: no cover - trivial
    """Callback di avanzamento di default: non fa nulla.

    Permette alle funzioni core di chiamare sempre `on_progress(...)` senza
    controllare ogni volta se qualcuno sta ascoltando."""


def _never_stop() -> bool:  # pragma: no cover - trivial
    """Callback di annullamento di default: non si ferma mai.

    La CLI passa una funzione che legge il flag `_interrupted` (Ctrl+C); la GUI
    ha un suo meccanismo e lascia il default."""
    return False


class GroqRateLimit(Exception):
    """Sollevata quando Groq rifiuta per limite (429 / token-al-giorno).

    Permette a chi trascrive a blocchi di FERMARSI e salvare un checkpoint,
    invece di restituire un risultato incompleto silenziosamente."""


class TranscriptionInterrupted(Exception):
    """Trascrizione fermata a metà (rate limit): trasporta il parziale per il
    checkpoint. 'done' = numero di blocchi completati su 'total'."""

    def __init__(self, segments: list, done: int, total: int, lang):
        self.segments = segments
        self.done = done
        self.total = total
        self.lang = lang
        super().__init__(f"Trascrizione interrotta al blocco {done}/{total}")


def _is_rate_limit(msg: str) -> bool:
    m = (msg or "").lower()
    return ("429" in m or "rate_limit" in m or "rate limit" in m
            or "tokens per" in m or "requests per" in m or "too many requests" in m)


# === CREDITI GROQ: CACHE DEI RATE-LIMIT PER MODELLO ==========================
# Groq non espone un endpoint "saldo": il budget del piano free arriva SOLO
# negli header x-ratelimit-* di ogni risposta, e sono PER MODELLO (whisper per
# la trascrizione, gpt-oss per il riassunto, qwen per la visiva). Invece di
# sprecare una chiamata vera — e quindi un credito — ad ogni clic sul pulsante
# "crediti", registriamo qui gli header che le richieste REALI già producono:
# il pulsante legge questa cache, a costo zero. La cache vive per la sessione.
_RATE_LIMIT_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
_RATE_LIMIT_CACHE: dict[str, dict] = {}  # model -> {model, items, checked_at_iso}


def _rate_limit_reset_seconds(value: str | None) -> float | None:
    """Header di reset Groq ('2m59.56s', '986ms', '1h0m0s') -> secondi. None se vuoto."""
    if not value:
        return None
    total, found = 0.0, False
    for num, unit in re.findall(r"([0-9.]+)\s*(ms|s|m|h|d)", value):
        try:
            total += float(num) * _RATE_LIMIT_UNITS[unit]
            found = True
        except (ValueError, KeyError):
            pass
    return total if found else None


def _rate_limit_num(value) -> float | None:
    """float() tollerante di un valore header (int/float/None)."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_ratelimit_headers(headers) -> list[dict]:
    """Header x-ratelimit-* -> lista di gruppi limite, già con il MOMENTO ASSOLUTO
    di azzeramento (così la cache resta valida anche letta molto dopo).

    Ogni voce: {kind, remaining, limit, reset_at_iso}. 'kind' ∈
    'audio_seconds' | 'requests' | 'tokens'. Solo i gruppi presenti vengono resi."""
    def get(name: str):
        try:
            return headers.get(name)
        except Exception:
            return None

    now = datetime.now()
    items: list[dict] = []
    for kind, suffix in (("audio_seconds", "audio-seconds"),
                         ("requests", "requests"),
                         ("tokens", "tokens")):
        remaining = _rate_limit_num(get(f"x-ratelimit-remaining-{suffix}"))
        limit = _rate_limit_num(get(f"x-ratelimit-limit-{suffix}"))
        reset_s = _rate_limit_reset_seconds(get(f"x-ratelimit-reset-{suffix}"))
        if remaining is None and limit is None and reset_s is None:
            continue
        from datetime import timedelta
        reset_at = (now + timedelta(seconds=reset_s)) if reset_s is not None else None
        items.append({
            "kind": kind,
            "remaining": remaining,
            "limit": limit,
            "reset_at_iso": reset_at.isoformat() if reset_at else None,
        })
    return items


def record_rate_limits(model: str, headers) -> list[dict]:
    """Registra in cache i limiti letti dagli header di una risposta Groq REALE.

    A costo zero: gli header viaggiano con richieste che faremmo comunque. Va
    chiamata accanto a ogni chiamata Groq andata a buon fine (trascrizione,
    riassunto, visiva). Best-effort: non solleva mai."""
    try:
        items = parse_ratelimit_headers(headers)
    except Exception:
        return []
    if items:
        _RATE_LIMIT_CACHE[model] = {
            "model": model,
            "items": items,
            "checked_at_iso": datetime.now().isoformat(),
        }
    return items


def cached_rate_limits() -> list[dict]:
    """Snapshot per-modello dei limiti registrati finora (per il pulsante crediti).

    Lista (eventualmente vuota) di {model, items, checked_at_iso}. Vuota finché
    non è stata fatta almeno una chiamata Groq reale in questa sessione."""
    return list(_RATE_LIMIT_CACHE.values())


def _checkpoints_dir() -> str:
    """Cartella dedicata ai checkpoint dei video parziali."""
    root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, "results", ".checkpoints")


def _checkpoint_key(meta: dict) -> str:
    """Chiave stabile per identificare il video/file fra una sessione e l'altra.

    Basata sul TITOLO (la stessa identità della cartella dei risultati), così
    coincide sia con i metadati originali sia con quelli RICOSTRUITI dal .json
    salvato — dove l'id del video e il percorso file non sono disponibili. Questo
    è essenziale perché lo stato scritto durante il run e quello aggiornato dalle
    fasi «solo traduzione/riassunto/riprendi» (che ricaricano da disco) puntino
    allo stesso file."""
    prefix = "local_" if meta.get("source") == "local" else "yt_"
    return prefix + _safe_filename(meta.get("title") or meta.get("id") or "video")


def checkpoint_path(meta: dict) -> str:
    return os.path.join(_checkpoints_dir(), _checkpoint_key(meta) + ".json")


def load_checkpoint(meta: dict) -> dict | None:
    """Legge il checkpoint del video, o None se non esiste / è corrotto."""
    p = checkpoint_path(meta)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("done_chunks") and data.get("total_chunks"):
            return data
    except Exception:
        return None
    return None


def save_checkpoint(meta: dict, data: dict) -> None:
    """Salva (atomicamente) il parziale del video, così si può riprendere dopo."""
    os.makedirs(_checkpoints_dir(), exist_ok=True)
    p = checkpoint_path(meta)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, p)


def delete_checkpoint(meta: dict) -> None:
    try:
        os.remove(checkpoint_path(meta))
    except OSError:
        pass


# --- Local transcription checkpoint (resume a local run interrupted mid-way) -
# faster-whisper processes the whole file in one pass (no chunks like Groq), so
# to support resuming we periodically save the segments produced so far plus the
# audio time reached. On resume we trim the audio from that point with ffmpeg,
# transcribe only the remainder, and shift its timestamps back into place.

# Save a local checkpoint every this many seconds of AUDIO processed (not wall
# clock): a balance between losing little work and not writing too often.
LOCAL_CHECKPOINT_EVERY = 120


def local_checkpoint_path(meta: dict) -> str:
    """Path of the local-transcription checkpoint for this source."""
    return os.path.join(_checkpoints_dir(), _checkpoint_key(meta) + "_local.json")


def load_local_checkpoint(meta: dict) -> dict | None:
    """Read the partial local transcription, or None if absent/corrupt.

    Valid only if it carries the segments produced and the audio time reached
    ('done_seconds'); the caller also checks the model/duration still match."""
    p = local_checkpoint_path(meta)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("done_seconds") and isinstance(data.get("segments"), list):
            return data
    except Exception:
        return None
    return None


def save_local_checkpoint(meta: dict, segments: list, done_seconds: float,
                          model: str, duration: float, detected=None) -> None:
    """Atomically save the partial local transcription (for resuming)."""
    os.makedirs(_checkpoints_dir(), exist_ok=True)
    p = local_checkpoint_path(meta)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"model": model, "done_seconds": done_seconds, "duration": duration,
                   "detected_language": detected, "segments": segments},
                  f, ensure_ascii=False)
    os.replace(tmp, p)


def delete_local_checkpoint(meta: dict) -> None:
    try:
        os.remove(local_checkpoint_path(meta))
    except OSError:
        pass


def _local_resume_point(model_name: str, duration: float, resume_cp: dict | None):
    """Decide where a local transcription should start, from an EXPLICIT checkpoint.

    Returns (start_offset_seconds, prior_segments, prior_detected). A non-zero
    offset means the passed checkpoint is valid (same model and ~same duration);
    the caller will trim the audio from that point. Returns (0, [], None) when no
    checkpoint is passed or it does not match — the caller never auto-loads, so
    "start over" reliably means start over."""
    cp = resume_cp
    if not cp:
        return 0.0, [], None
    same_model = cp.get("model") == model_name
    same_audio = (not duration or not cp.get("duration")
                  or abs(float(cp["duration"]) - float(duration)) < 1.0)
    if same_model and same_audio:
        return float(cp.get("done_seconds", 0)), list(cp.get("segments") or []), cp.get("detected_language")
    return 0.0, [], None


def _trim_audio(audio_path: str, start_seconds: float, workdir: str) -> str:
    """Re-encode the audio from 'start_seconds' onward to a 16 kHz mono WAV.

    Used when resuming a local transcription: we feed faster-whisper only the
    not-yet-processed tail. Returns the path of the trimmed file."""
    out_path = os.path.join(workdir, "resume_trim.wav")
    cmd = ["ffmpeg", "-y", "-ss", str(start_seconds), "-i", audio_path,
           "-ac", "1", "-ar", str(AUDIO_SAMPLE_RATE), out_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return out_path


# --- Pipeline state store (the job "database") ------------------------------
# Un unico file JSON per video che traccia l'avanzamento di TUTTE le fasi
# (trascrizione, traduzione, riassunto). I checkpoint qui sopra riguardano solo
# la trascrizione; questo stato è di livello più alto e permette di riprendere
# esattamente dalla sezione in cui ci si è fermati — ad esempio quando i crediti
# Groq finiscono a metà del riassunto. È il "database" del job: JSON atomico e
# ispezionabile, accanto ai checkpoint in results/.checkpoints/.
#
# Le sezioni parziali (già tradotte / già riassunte) vengono salvate DENTRO lo
# stato dopo ogni sezione, così un "Riprendi" ricarica il lavoro già fatto e
# processa solo le sezioni mancanti (nessun credito Groq rispeso su ciò che era
# già pronto).

# Fasi della pipeline, in ordine di esecuzione.
PIPELINE_STAGES = ("transcription", "translation", "summary")

# Stati possibili di una fase: da fare · completata parzialmente · completata ·
# non applicabile (es. traduzione per un audio già in italiano).
STAGE_PENDING = "pending"
STAGE_PARTIAL = "partial"
STAGE_DONE = "done"
STAGE_SKIP = "skip"


def state_path(meta: dict) -> str:
    """Percorso del file di stato della pipeline per questo video/file."""
    return os.path.join(_checkpoints_dir(), _checkpoint_key(meta) + "_state.json")


def _empty_state(meta: dict, backend: str = "groq") -> dict:
    """Nuovo stato "vuoto": tutte le fasi ancora da fare."""
    return {
        "key": _checkpoint_key(meta),
        "title": meta.get("title"),
        "source": meta.get("source"),
        "url": meta.get("webpage_url") or meta.get("source_path"),
        "backend": backend,
        "detected_language": meta.get("detected_language"),
        "stages": {s: {"status": STAGE_PENDING, "done": 0, "total": 0}
                   for s in PIPELINE_STAGES},
        "updated_at": None,
    }


def load_state(meta: dict) -> dict | None:
    """Legge lo stato della pipeline, o None se assente/corrotto."""
    p = state_path(meta)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("stages"), dict):
            return data
    except Exception:
        return None
    return None


def save_state(meta: dict, state: dict) -> None:
    """Salva (atomicamente) lo stato della pipeline, timbrando l'orario."""
    os.makedirs(_checkpoints_dir(), exist_ok=True)
    p = state_path(meta)
    tmp = p + ".tmp"
    state = dict(state)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, p)


def update_stage(meta: dict, stage: str, *, status=None, done=None, total=None,
                 sections=None, extra=None, backend=None) -> dict:
    """Aggiorna una fase dello stato (creandolo se manca) e lo salva.

    Passa solo i campi che cambiano: 'sections' è la lista delle sezioni già
    completate (traduzione/riassunto) da conservare per il resume; 'extra'
    aggiunge chiavi arbitrarie alla fase (es. 'target' per la traduzione)."""
    state = load_state(meta) or _empty_state(meta, backend or "groq")
    if backend:
        state["backend"] = backend
    if meta.get("detected_language") and not state.get("detected_language"):
        state["detected_language"] = meta.get("detected_language")
    st = state["stages"].setdefault(
        stage, {"status": STAGE_PENDING, "done": 0, "total": 0})
    if status is not None:
        st["status"] = status
    if done is not None:
        st["done"] = done
    if total is not None:
        st["total"] = total
    if sections is not None:
        st["sections"] = sections
    if extra:
        st.update(extra)
    save_state(meta, state)
    return state


def delete_state(meta: dict) -> None:
    """Rimuove il file di stato (es. su "Ritrascrivi tutto" o a job concluso)."""
    try:
        os.remove(state_path(meta))
    except OSError:
        pass


def stage_status(state: dict | None, stage: str) -> str:
    """Stato ('pending'/'partial'/'done'/'skip') di una fase, robusto a None."""
    if not state:
        return STAGE_PENDING
    return state.get("stages", {}).get(stage, {}).get("status", STAGE_PENDING)


def stage_sections(state: dict | None, stage: str) -> list[dict]:
    """Sezioni già completate salvate per una fase (lista, eventualmente vuota)."""
    if not state:
        return []
    secs = state.get("stages", {}).get(stage, {}).get("sections")
    return list(secs) if isinstance(secs, list) else []


def resume_plan(state: dict | None) -> dict:
    """Da uno stato salvato, ricava la prima fase incompleta da cui riprendere.

    Ritorna {'stage', 'status', 'done', 'total'} oppure {'stage': None} se non
    c'è nulla da riprendere (tutto completato o nessuno stato). Le fasi 'skip'
    (non applicabili, es. traduzione di un audio già italiano) sono ignorate."""
    if not state:
        return {"stage": None}
    for stage in PIPELINE_STAGES:
        st = state.get("stages", {}).get(stage, {})
        status = st.get("status", STAGE_PENDING)
        if status in (STAGE_PENDING, STAGE_PARTIAL):
            return {"stage": stage, "status": status,
                    "done": int(st.get("done", 0) or 0),
                    "total": int(st.get("total", 0) or 0)}
    return {"stage": None}


def has_resumable_state(meta: dict) -> bool:
    """True se esiste uno stato con almeno una fase da riprendere.

    Serve alla UI (CLI/GUI) per mostrare l'opzione «Riprendi da dove si è
    interrotto» solo quando ha davvero senso."""
    return resume_plan(load_state(meta)).get("stage") is not None


# Subfolder names per interface language: an English user gets English folders
# (transcriptions/translations) instead of the Italian defaults. The CLI is
# Italian-only, so it always uses the "it" names; the GUI passes its current UI
# language down so the folders match what the user sees on screen.
TRANS_SUBDIRS = {"it": "trascrizioni", "en": "transcriptions"}
TRANSL_SUBDIRS = {"it": "traduzioni", "en": "translations"}
SUMMARY_SUBDIRS = {"it": "riassunti", "en": "summaries"}
VISUAL_SUBDIRS = {"it": "analisi_visiva", "en": "visual_analysis"}
# Suffix added to the summary file name, per UI language.
SUMMARY_SUFFIX = {"it": "riassunto", "en": "summary"}


def trans_subdir(lang: str | None = "it") -> str:
    """Name of the TRANSCRIPTION subfolder for the given UI language."""
    return TRANS_SUBDIRS.get(lang or "it", TRANS_SUBDIRS["it"])


def transl_subdir(lang: str | None = "it") -> str:
    """Name of the TRANSLATION subfolder for the given UI language."""
    return TRANSL_SUBDIRS.get(lang or "it", TRANSL_SUBDIRS["it"])


def summary_subdir(lang: str | None = "it") -> str:
    """Name of the SUMMARY subfolder for the given UI language."""
    return SUMMARY_SUBDIRS.get(lang or "it", SUMMARY_SUBDIRS["it"])


def visual_subdir(lang: str | None = "it") -> str:
    """Name of the VISUAL-ANALYSIS subfolder for the given UI language."""
    return VISUAL_SUBDIRS.get(lang or "it", VISUAL_SUBDIRS["it"])


def transcription_exists(out_root: str, title: str) -> bool:
    """True se in out_root/<titolo>/<trascrizioni>/ ci sono già file trascritti.

    Controlla TUTTI i possibili nomi cartella (italiano e inglese), così il
    rilevamento funziona anche se il video era stato trascritto con l'interfaccia
    in un'altra lingua."""
    base = os.path.join(out_root, _safe_filename(title))
    for sub in TRANS_SUBDIRS.values():
        d = os.path.join(base, sub)
        if os.path.isdir(_lp(d)) and any(
                n.lower().endswith((".md", ".txt", ".json", ".pdf")) for n in os.listdir(_lp(d))):
            return True
    return False


def load_existing_transcript(out_root: str, title: str):
    """Rilegge una trascrizione salvata (dal .json) e ricostruisce
    (meta, segments, engine_label), sufficienti a rigenerare SOLO la traduzione
    senza ri-trascrivere (e senza rispendere crediti). None se assente/vuota.

    Cerca il .json in tutti i possibili nomi cartella (italiano e inglese)."""
    safe = _safe_filename(title)
    p = None
    for sub in TRANS_SUBDIRS.values():
        cand = os.path.join(out_root, safe, sub, safe + ".json")
        if os.path.isfile(_lp(cand)):
            p = cand
            break
    if not p:
        return None
    try:
        with open(_lp(p), "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None
    segments = d.get("segments") or []
    if not segments:
        return None
    meta = {
        "id": "", "title": d.get("title", title),
        "channel": d.get("channel"), "views": d.get("views"),
        "upload_date": d.get("upload_date"), "duration": d.get("duration_seconds"),
        "chapters": [{"start_time": c.get("start"), "end_time": c.get("end"),
                      "title": c.get("title")} for c in (d.get("chapters") or [])],
        "webpage_url": d.get("url", ""), "source": d.get("source", "youtube"),
    }
    return meta, segments, d.get("engine", "?")


def load_existing_translation(out_root: str, title: str, target: str = "it"):
    """Rilegge le SEZIONI di una traduzione già salvata (dal .json), o None.

    Serve a «Solo riassunto» per riassumere la TRADUZIONE invece dell'originale.
    Cerca `<titolo>_<target>.json` in tutti i possibili nomi cartella traduzioni
    (italiano/inglese). Restituisce la lista di sezioni {start,title,text}."""
    safe = _safe_filename(title)
    for sub in TRANSL_SUBDIRS.values():
        p = os.path.join(out_root, safe, sub, f"{safe}_{target}.json")
        if os.path.isfile(_lp(p)):
            try:
                with open(_lp(p), "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            sections = data.get("sections")
            if sections:
                return sections
    return None


# === TRANSCRIPTION BACKEND SELECTION ===

def _option_card(number: str, icon: str, title: str, rows: list[tuple[str, str]],
                 accent: str) -> Panel:
    """Build a "card" (mini-box) for an option, with number, icon, title and a
    list of rows (symbol, text). 'accent' is the border color."""
    body = Text()
    for i, (sym, txt) in enumerate(rows):
        if i:
            body.append("\n")
        sym_style = {"✓": "success", "✗": "warning", "•": "dim"}.get(sym, "dim")
        body.append(f" {sym} ", style=sym_style)
        body.append(txt, style="dim" if sym == "•" else "")
    return Panel(
        body,
        title=f"[bold {accent}]{number}[/bold {accent}]  {icon} [bold]{title}[/bold]",
        title_align="left",
        border_style=accent, box=ROUNDED, padding=(1, 2), width=46,
    )


def choose_backend() -> str | None:
    """Show two "cards" side by side with the transcription engines and ask which one.

    Returns "local" or "groq", or None if the user cancels with 'q'. We clearly
    explain the PRIVACY vs SPEED trade-off because it is the key point of the
    choice."""
    local_card = _option_card(
        "1", "🔒", "Locale", [
            ("✓", "privacy totale: resta sul tuo PC"),
            ("✗", "più lento (nessuna GPU)"),
            ("•", "per audio privati/sensibili"),
        ], accent="bright_green")
    groq_card = _option_card(
        "2", "⚡", "Groq (cloud)", [
            ("✓", "velocissimo, anche senza GPU"),
            ("✗", "niente privacy: audio nel cloud"),
            ("•", "per video YouTube pubblici"),
        ], accent="bright_cyan")

    console.print()
    console.print(Rule("[bold bright_magenta]Come vuoi trascrivere?[/bold bright_magenta]",
                       style="bright_magenta"))
    console.print(Columns([local_card, groq_card], padding=(0, 2), align="center", equal=True))

    while True:
        choice = console.input(
            "\n[bold bright_magenta]›[/bold bright_magenta] [bold]Scelta[/bold] "
            "[dim](1 = Locale · 2 = Groq · q = annulla)[/dim]: ").strip().lower()
        if choice == "q":
            return None
        if choice == "1":
            return "local"
        if choice == "2":
            return "groq"
        console.print("[warning]Scelta non valida, riprova.[/warning]")


def choose_local_model() -> str | None:
    """Show a panel with the available local models and let one be chosen.

    It is called EVERY time the local backend is chosen (so you can change the
    model depending on the video). Returns the model name (e.g. "small") or None
    if the user cancels."""
    table = Table(show_header=True, box=None, expand=False, padding=(0, 2),
                  header_style="bold dim")
    table.add_column("#", style="bold bright_white", justify="center")
    table.add_column("Modello", style="bold bright_green", no_wrap=True)
    table.add_column("Velocità ↔ Accuratezza", style="info")
    # A visual "bar" of the model's weight (more filled = heavier/more accurate).
    weights = {"base": "▰▱▱▱▱", "small": "▰▰▱▱▱", "medium": "▰▰▰▱▱",
               "large-v3": "▰▰▰▰▰", "large-v3-turbo": "▰▰▰▰▱"}
    for key, (name, desc) in LOCAL_MODELS.items():
        badge = "  [bold bright_yellow]★ consigliato[/bold bright_yellow]" if name == "small" else ""
        bar = weights.get(name, "")
        table.add_row(key, f"{name}{badge}", f"[dim]{bar}[/dim]  {desc}")

    console.print()
    console.print(Panel(
        table,
        title="[title]🧠 Quale modello locale?[/title]", title_align="left",
        subtitle="[dim]più pieno = più accurato ma più lento su CPU[/dim]",
        border_style="bright_green", box=ROUNDED, expand=False, padding=(1, 2),
    ))

    while True:
        choice = console.input(
            "\n[bold bright_green]›[/bold bright_green] [bold]Modello[/bold] "
            "[dim](1-5 · q = annulla)[/dim]: ").strip().lower()
        if choice == "q":
            return None
        if choice in LOCAL_MODELS:
            return LOCAL_MODELS[choice][0]
        console.print("[warning]Scelta non valida, riprova.[/warning]")


def choose_groq_model() -> str | None:
    """Pannello per scegliere il modello di trascrizione Groq (cloud).

    Mostra i due modelli multilingua col prezzo per ora di audio, così la scelta
    è consapevole. Chiamato ogni volta che si sceglie il backend Groq. Restituisce
    il nome del modello (default: turbo) o None se si annulla."""
    rows = {
        "1": ("whisper-large-v3-turbo", "$0.04/ora", "▰▰▰▰▱",
              "miglior rapporto prezzo/velocità · quasi come large-v3", True),
        "2": ("whisper-large-v3", "$0.111/ora", "▰▰▰▰▰",
              "massima accuratezza · audio rumorosi/difficili · ~2,8× più caro", False),
    }
    table = Table(show_header=True, box=None, expand=False, padding=(0, 2),
                  header_style="bold dim")
    table.add_column("#", style="bold bright_white", justify="center")
    table.add_column("Modello", style="bold bright_cyan", no_wrap=True)
    table.add_column("Prezzo", style="bold bright_green", no_wrap=True)
    table.add_column("Qualità / quando", style="info")
    for key, (name, price, bar, desc, is_default) in rows.items():
        badge = "  [bold bright_yellow]★ consigliato[/bold bright_yellow]" if is_default else ""
        table.add_row(key, f"{name}{badge}", price, f"[dim]{bar}[/dim]  {desc}")

    console.print()
    console.print(Panel(
        table,
        title="[title]⚡ Quale modello Groq per la trascrizione?[/title]", title_align="left",
        subtitle="[dim]la trascrizione si paga a ORA di audio, non a token · invio = turbo[/dim]",
        border_style="bright_cyan", box=ROUNDED, expand=False, padding=(1, 2),
    ))

    while True:
        choice = console.input(
            "\n[bold bright_cyan]›[/bold bright_cyan] [bold]Modello[/bold] "
            "[dim](1-2 · invio = turbo · q = annulla)[/dim]: ").strip().lower()
        if choice == "q":
            return None
        if choice == "":
            return rows["1"][0]
        if choice in rows:
            return rows[choice][0]
        console.print("[warning]Scelta non valida, riprova.[/warning]")


def choose_ollama_model(kind: str) -> str | None:
    """Pannello per scegliere il modello OLLAMA (locale): 'text' per il
    riassunto/traduzione, 'vision' per l'analisi visiva dei fotogrammi.

    Mostra i modelli consigliati con la RAM indicativa richiesta e segna con ✓
    quelli GIÀ scaricati in Ollama (letti da /api/tags; nessun segno se Ollama
    è spento). Si può anche digitare un nome qualunque (es. mistral:7b).
    Invio = modello attuale (da .env o default). None se si annulla."""
    is_text = kind == "text"
    catalog = OLLAMA_TEXT_MODELS if is_text else OLLAMA_VISION_MODELS
    current = OLLAMA_MODEL if is_text else OLLAMA_VISION_MODEL
    installed = _ollama_installed_models()

    table = Table(show_header=True, box=None, expand=False, padding=(0, 2),
                  header_style="bold dim")
    table.add_column("#", style="bold bright_white", justify="center")
    table.add_column("Modello", style="bold bright_green", no_wrap=True)
    table.add_column("RAM", style="info", no_wrap=True)
    table.add_column("Note", style="info")
    for key, (name, ram, desc) in catalog.items():
        marks = ""
        if name == current:
            marks += "  [bold bright_yellow]★ attuale[/bold bright_yellow]"
        if installed is not None:
            marks += ("  [bold bright_green]✓ scaricato[/bold bright_green]"
                      if _ollama_has_model(name, installed)
                      else "  [dim]↓ da scaricare[/dim]")
        table.add_row(key, f"{name}{marks}", ram, desc)

    what = ("riassunto e traduzione" if is_text else "analisi visiva")
    console.print()
    console.print(Panel(
        table,
        title=f"[title]🦙 Quale modello Ollama per {what}?[/title]", title_align="left",
        subtitle="[dim]si può anche digitare un altro nome (es. mistral:7b) · "
                 f"invio = {current}[/dim]",
        border_style="bright_green", box=ROUNDED, expand=False, padding=(1, 2),
    ))
    if installed is None:
        console.print("  [dim]⚠ Ollama non raggiungibile ora: non so quali modelli "
                      "siano già scaricati (l'app lo verificherà al momento dell'uso).[/dim]")

    while True:
        choice = console.input(
            "\n[bold bright_green]›[/bold bright_green] [bold]Modello[/bold] "
            f"[dim](1-{len(catalog)} · nome · invio = attuale · q = annulla)[/dim]: ").strip()
        if choice.lower() == "q":
            return None
        if choice == "":
            return current
        name = catalog[choice][0] if choice in catalog else choice
        if installed is not None and not _ollama_has_model(name, installed):
            console.print(f"  [warning]⚠ '{name}' non è ancora scaricato: prima che "
                          f"serva, esegui  [bold]ollama pull {name}[/bold][/warning]")
        return name


# Actions offered when a video is ALREADY transcribed (numbered panel below).
# number -> (icon, title, description, action-code)
# Azioni per un video GIÀ trascritto, in ordine di visualizzazione:
# (codice, icona, nome, descrizione). «resume» viene mostrata solo se esiste uno
# stato parziale da cui riprendere (traduzione/riassunto interrotti a metà).
_EXISTING_ACTIONS = [
    ("both", "🔁", "Trascrivi nuovamente",
     "rifà tutto da capo: trascrizione + traduzione + riassunto"),
    ("resume", "⏯", "Riprendi da dove si è interrotto",
     "continua dalla fase/sezione in cui l'operazione si era fermata"),
    ("translate", "🌐", "Solo traduzione",
     "traduce in italiano la trascrizione salvata (nessun credito di trascrizione)"),
    ("summary", "🧠", "Solo riassunto",
     "genera soltanto il riassunto dal testo salvato (la traduzione se c'è, altrimenti l'originale)"),
    ("retranscribe", "🎙", "Ritrascrivi soltanto",
     "rifà solo la trascrizione, senza traduzione né riassunto"),
    ("skip", "⏭", "Salta",
     "non fare nulla per questo video"),
]


def choose_existing_action(title: str, can_resume: bool = False,
                           resume_info: str = "") -> str:
    """Pannello a elenco numerato per un video GIÀ trascritto: chiede cosa fare.

    Mostra le opzioni numerate; «Riprendi da dove si è interrotto» compare solo se
    'can_resume' è vero (c'è un parziale salvato), con 'resume_info' a specificare
    da dove. Restituisce uno dei codici azione:
    "both" · "resume" · "translate" · "summary" · "retranscribe" · "skip"."""
    actions = [a for a in _EXISTING_ACTIONS if a[0] != "resume" or can_resume]
    table = Table(show_header=True, box=None, expand=False, padding=(0, 2),
                  header_style="bold dim")
    table.add_column("#", style="bold bright_white", justify="center")
    table.add_column("Azione", style="bold bright_yellow", no_wrap=True)
    table.add_column("Cosa fa", style="info")
    mapping: dict[str, str] = {}
    for i, (code, icon, name, desc) in enumerate(actions, 1):
        key = str(i)
        mapping[key] = code
        if code == "resume" and resume_info:
            desc = f"{desc} — [bright_cyan]{resume_info}[/bright_cyan]"
        table.add_row(key, f"{icon} {name}", desc)

    console.print()
    console.print(Panel(
        table,
        title=f"[title]♻ «{title}» è già stato trascritto[/title]", title_align="left",
        subtitle="[dim]è presente in results/ — scegli come procedere[/dim]",
        border_style="bright_yellow", box=ROUNDED, expand=False, padding=(1, 2),
    ))

    while True:
        choice = console.input(
            f"\n[bold bright_yellow]›[/bold bright_yellow] [bold]Scelta[/bold] "
            f"[dim](1-{len(actions)} · q = salta)[/dim]: ").strip().lower()
        if choice == "q":
            return "skip"
        if choice in mapping:
            return mapping[choice]
        console.print("[warning]Scelta non valida, riprova.[/warning]")


# Etichette leggibili delle fasi, per i messaggi di ripresa (CLI e GUI).
STAGE_LABELS_IT = {
    "transcription": "trascrizione", "translation": "traduzione", "summary": "riassunto",
}
STAGE_LABELS_EN = {
    "transcription": "transcription", "translation": "translation", "summary": "summary",
}


def resume_info_text(meta: dict, lang: str = "it") -> str:
    """Breve testo «da dove riprende» per il video, o "" se non c'è nulla.

    Es. "riassunto — sezione 8/20". Usato nei menu CLI/GUI per spiegare all'utente
    cosa farà «Riprendi da dove si è interrotto»."""
    plan = resume_plan(load_state(meta))
    stage = plan.get("stage")
    if not stage:
        return ""
    labels = STAGE_LABELS_EN if lang == "en" else STAGE_LABELS_IT
    name = labels.get(stage, stage)
    done, total = plan.get("done", 0), plan.get("total", 0)
    if total and plan.get("status") == STAGE_PARTIAL:
        sec = "section" if lang == "en" else "sezione"
        return f"{name} — {sec} {done + 1}/{total}"
    return name


def init_run_state(meta: dict, backend: str, want_translate: bool,
                   want_summary: bool) -> dict:
    """Registra il PIANO della pipeline all'avvio di un run completo.

    Serve a «Riprendi»: sapendo quali fasi erano previste (pending) e quali no
    (skip), la ripresa esegue solo quelle giuste. Sovrascrive un eventuale stato
    precedente (usato per «Trascrivi nuovamente»/«Ritrascrivi soltanto»)."""
    state = _empty_state(meta, backend)
    state["stages"]["transcription"]["status"] = STAGE_PENDING
    state["stages"]["translation"]["status"] = (
        STAGE_PENDING if want_translate else STAGE_SKIP)
    state["stages"]["summary"]["status"] = (
        STAGE_PENDING if want_summary else STAGE_SKIP)
    save_state(meta, state)
    return state


def resume_existing(out_root: str, meta: dict, client=None, do_export: bool = True,
                    ui_lang: str = "it") -> None:
    """Riprende un video da dove la pipeline si era interrotta (traduzione/riassunto).

    Legge lo stato salvato e completa, nell'ordine, le sole fasi ancora da fare:
    traduzione (se prevista e non già completata) e poi riassunto. Ogni fase
    riparte dalla sezione in cui si era fermata (le sezioni già fatte sono
    ricaricate dallo stato). Se i crediti Groq finiscono di nuovo sul riassunto,
    offre di concluderlo in locale con Ollama."""
    title = meta["title"]
    state = load_state(meta)
    if resume_plan(state).get("stage") is None:
        console.print("[dim]Niente da riprendere: tutto già completato.[/dim]")
        return
    translated = None
    if stage_status(state, "translation") in (STAGE_PENDING, STAGE_PARTIAL):
        translated = translate_existing(out_root, title, target="it",
                                        do_export=do_export, ui_lang=ui_lang,
                                        local=client is None)
    if stage_status(load_state(meta), "summary") in (STAGE_PENDING, STAGE_PARTIAL):
        summarize_with_local_fallback(out_root, meta, client, translated,
                                      do_export, ui_lang)


def summarize_with_local_fallback(out_root: str, meta: dict, client,
                                  source_sections, do_export: bool = True,
                                  ui_lang: str = "it") -> bool:
    """Riassume; se i crediti Groq si esauriscono a metà, offre di finire in locale.

    Il riassunto parziale è già salvato nello stato: proseguendo con Ollama si
    riprende dalla sezione ferma, senza rispendere nulla. Restituisce True se il
    riassunto è stato completato."""
    ok = summarize_existing(out_root, meta["title"], client=client,
                            source_sections=source_sections, do_export=do_export,
                            ui_lang=ui_lang)
    if ok or client is None:
        return ok
    if stage_status(load_state(meta), "summary") not in (STAGE_PENDING, STAGE_PARTIAL):
        return ok
    if _confirm("Crediti Groq esauriti nel riassunto. Lo concludo ora in locale "
                "con Ollama (dalla sezione ferma)?", accent="bright_yellow"):
        return summarize_existing(out_root, meta["title"], client=None,
                                  source_sections=source_sections,
                                  do_export=do_export, ui_lang=ui_lang)
    return ok


# === SOURCE SELECTION (YouTube URL vs local file/folder) ===

def choose_source() -> str | None:
    """Ask whether to transcribe a YouTube URL or a LOCAL file/folder.

    Returns "youtube" or "local", or None if the user cancels with 'q'."""
    yt_card = _option_card(
        "1", "📺", "YouTube", [
            ("✓", "incolli l'URL di un video"),
            ("✓", "scarica audio, info e capitoli"),
            ("•", "per video pubblici online"),
        ], accent="bright_cyan")
    file_card = _option_card(
        "2", "🎙", "File locale", [
            ("✓", "audio da telefono/PC (m4a, mp3, wav...)"),
            ("✓", "anche una cartella intera (batch)"),
            ("•", "per note vocali e registrazioni"),
        ], accent="bright_green")

    console.print()
    console.print(Rule("[bold bright_magenta]Cosa vuoi trascrivere?[/bold bright_magenta]",
                       style="bright_magenta"))
    console.print(Columns([yt_card, file_card], padding=(0, 2), align="center", equal=True))

    while True:
        choice = console.input(
            "\n[bold bright_magenta]›[/bold bright_magenta] [bold]Scelta[/bold] "
            "[dim](1 = YouTube · 2 = File locale · q = annulla)[/dim]: ").strip().lower()
        if choice == "q":
            return None
        if choice == "1":
            return "youtube"
        if choice == "2":
            return "local"
        console.print("[warning]Scelta non valida, riprova.[/warning]")


def resolve_local_sources(path: str) -> list[str]:
    """Turn a user-typed path into the list of audio files to transcribe.

    - a single file  -> [that file]   (warns if its extension is unusual)
    - a folder        -> every audio/video file inside it, sorted by name
    Returns [] (after printing a clear message) if nothing usable is found."""
    # On Windows users often paste paths wrapped in quotes: strip them.
    path = os.path.expanduser(path.strip().strip('"').strip("'"))
    if not os.path.exists(path):
        console.print(f"[error]Percorso non trovato: {path}[/error]")
        return []

    if os.path.isfile(path):
        if os.path.splitext(path)[1].lower() not in AUDIO_EXTENSIONS:
            console.print("[warning]Estensione non riconosciuta: ci provo lo stesso "
                          "(ffmpeg supporta molti formati).[/warning]")
        return [path]

    # Directory: collect the audio/video files directly inside it (non-recursive).
    files = sorted(
        os.path.join(path, name)
        for name in os.listdir(path)
        if os.path.isfile(os.path.join(path, name))
        and os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS
    )
    if not files:
        console.print(f"[warning]Nessun file audio nella cartella: {path}[/warning]")
        return []
    return files


def display_local_sources(metas: list[dict]) -> None:
    """Show a card (single file) or a table (folder/batch) of the local sources."""
    if len(metas) == 1:
        m = metas[0]
        table = Table(show_header=False, box=None, expand=False, padding=(0, 1))
        table.add_column("Icona", justify="center", no_wrap=True)
        table.add_column("Campo", style="dim", justify="left", no_wrap=True)
        table.add_column("Valore", style="bold bright_white", min_width=40, overflow="fold")
        table.add_row("🎙 ", "File", os.path.basename(m["source_path"]))
        table.add_row("⏱ ", "Durata", f"[bright_cyan]{_format_duration(m['duration'])}[/bright_cyan]")
        table.add_row("📁", "Percorso", f"[dim]{m['source_path']}[/dim]")
        console.print()
        console.print(Panel(
            table, title=f"[title]🎙 {metas[0]['title']}[/title]", title_align="left",
            border_style="bright_green", box=ROUNDED, expand=False, padding=(1, 2),
        ))
        return

    table = Table(show_header=True, box=None, expand=False, padding=(0, 2), header_style="bold dim")
    table.add_column("#", style="bold bright_white", justify="center")
    table.add_column("File", style="bold bright_green", overflow="fold")
    table.add_column("Durata", style="info", justify="right", no_wrap=True)
    total = 0.0
    for i, m in enumerate(metas, 1):
        total += m["duration"] or 0
        table.add_row(str(i), os.path.basename(m["source_path"]), _format_duration(m["duration"]))
    console.print()
    console.print(Panel(
        table,
        title=f"[title]🎙 {len(metas)} file da trascrivere[/title]", title_align="left",
        subtitle=f"[dim]durata totale ~{_format_duration(total)}[/dim]",
        border_style="bright_green", box=ROUNDED, expand=False, padding=(1, 2),
    ))


def display_playlist_sources(pl: dict, metas: list[dict]) -> None:
    """Mostra il nome della playlist, il canale e la tabella dei video da trascrivere.

    Serve a far vedere all'utente COSA verrà trascritto (e sotto quale cartella)
    prima di confermare: titolo playlist -> cartella in results/, elenco numerato
    dei video con la loro durata e la durata totale stimata."""
    table = Table(show_header=True, box=None, expand=False, padding=(0, 2), header_style="bold dim")
    table.add_column("#", style="bold bright_white", justify="center")
    table.add_column("Video", style="bold bright_green", overflow="fold")
    table.add_column("Durata", style="info", justify="right", no_wrap=True)
    total = 0.0
    for i, m in enumerate(metas, 1):
        total += m["duration"] or 0
        table.add_row(str(i), m["title"], _format_duration(m["duration"]))
    sub = (f"[dim]canale: {pl.get('channel') or '?'} · "
           f"durata totale ~{_format_duration(total)}[/dim]")
    console.print()
    console.print(Panel(
        table,
        title=f"[title]▶ Playlist «{pl.get('title') or '?'}» — {len(metas)} video[/title]",
        title_align="left", subtitle=sub,
        border_style="bright_magenta", box=ROUNDED, expand=False, padding=(1, 2),
    ))


# === PROMPT (user input with a consistent style) ===

def _prompt(label: str, hint: str = "", accent: str = "bright_blue") -> str:
    """User input with a consistent style: colored arrow + label."""
    h = f" [dim]{hint}[/dim]" if hint else ""
    return console.input(f"\n[bold {accent}]›[/bold {accent}] [bold]{label}[/bold]{h}: ").strip()


def _confirm(label: str, accent: str = "bright_blue") -> bool:
    """Yes/no question with a consistent style; True only if the user answers 's'."""
    return _prompt(label, "(s/n)", accent).lower() == "s"


# === PHASE 0: VIDEO METADATA ===

def _best_thumbnail(info: dict) -> str | None:
    """Pick the best still image (cover) for a video.

    Prefers the single 'thumbnail' yt-dlp already resolves; otherwise takes the
    highest-resolution entry from the 'thumbnails' list. Returns None if absent."""
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = info.get("thumbnails") or []
    if not thumbs:
        return None
    best = max(thumbs, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))
    return best.get("url")


def get_video_info(url: str) -> dict:
    """Download ONLY the video metadata (without downloading the audio).

    Uses yt-dlp with download=False: a lightweight call that returns a large
    dictionary of information. We extract the fields we need and pack them into
    our own, cleaner dictionary. Solleva MediaError su errore (URL non valido,
    video privato, rete...). Versione SENZA interfaccia, condivisa da CLI e GUI:
    per la CLI c'è il wrapper `_cli_get_video_info`."""
    ydl_opts = {
        "quiet": True,            # no yt-dlp output on screen (we handle it ourselves)
        "no_warnings": True,
        "skip_download": True,    # do NOT download the media, only the info
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise MediaError(f"Impossibile leggere il video: {e}")

    # Some URLs (playlists) return a list of 'entries': we take the first one.
    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    categories = info.get("categories") or []
    return {
        # Copertina: la usa la GUI nella card di conferma (la CLI la ignora).
        "thumbnail": _best_thumbnail(info),
        "id": info.get("id", ""),
        "title": info.get("title", "Senza titolo"),
        "channel": info.get("channel") or info.get("uploader") or "?",
        "views": info.get("view_count"),
        "upload_date": info.get("upload_date"),
        "duration": info.get("duration"),
        # 'chapters' is a list of {start_time, end_time, title} if the video has
        # chapters; otherwise None. It will be the basis of our "sections".
        "chapters": info.get("chapters") or [],
        "webpage_url": info.get("webpage_url", url),
        "source": "youtube",
        # Metadati extra mostrati nella card info (mancanti -> None).
        "likes": info.get("like_count"),
        "subscribers": info.get("channel_follower_count"),
        "category": categories[0] if categories else None,
        # Lingua dichiarata da YouTube (spesso assente). Quella "vera" dall'audio
        # viene rilevata da Whisper durante la trascrizione (detected_language).
        "language": info.get("language"),
    }


def get_playlist_info(url: str) -> dict | None:
    """Se l'URL è una PLAYLIST YouTube, restituisce nome/canale + elenco dei video.

    Usa yt-dlp in modalità "flat" (extract_flat="in_playlist"): NON risolve i
    metadati di ogni singolo video, legge soltanto l'elenco — quindi è veloce
    anche con playlist lunghe. Restituisce None se l'URL non è una playlist
    (video singolo); solleva MediaError su errore di rete/lettura. La chiave
    'entries' è la lista degli URL dei video nell'ordine della playlist; 'title'
    è il nome della playlist (con fallback al canale) usato per la sottocartella
    in results/. Versione senza interfaccia: wrapper CLI in
    `_cli_get_playlist_info`."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",  # non scaricare i metadati di ogni video
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise MediaError(f"Impossibile leggere la playlist: {e}")

    if not info or info.get("_type") != "playlist":
        return None  # non è una playlist: si prosegue come video singolo

    entries: list[str] = []
    for e in (info.get("entries") or []):
        if not e:
            continue
        vid = e.get("id")
        vurl = e.get("url") or e.get("webpage_url")
        if vid:
            entries.append(f"https://www.youtube.com/watch?v={vid}")
        elif vurl:
            entries.append(vurl)
    if not entries:
        return None

    channel = info.get("channel") or info.get("uploader")
    return {
        "title": info.get("title") or channel,
        "channel": channel,
        "count": len(entries),
        "entries": entries,
    }


# --- Wrapper CLI dei metadati ------------------------------------------------
# Le funzioni core qui sopra sollevano MediaError; la CLI preferisce lavorare
# con None ("non è andata, vai avanti") e stampare l'errore in rosso.

def _cli_get_video_info(url: str) -> dict | None:
    """get_video_info per la CLI: stampa l'errore e restituisce None."""
    try:
        return get_video_info(url)
    except MediaError as e:
        console.print(f"[error]{e}[/error]")
        return None


def _cli_get_playlist_info(url: str) -> dict | None:
    """get_playlist_info per la CLI: stampa l'errore e restituisce None."""
    try:
        return get_playlist_info(url)
    except MediaError as e:
        console.print(f"[error]{e}[/error]")
        return None


def _is_local(meta: dict) -> bool:
    """True if the metadata describes a LOCAL file (not a YouTube video)."""
    return meta.get("source") == "local"


def local_file_meta(path: str) -> dict:
    """Build a synthetic metadata dict for a LOCAL audio/video file.

    A local file has no channel/views/upload date/chapters: we fill those with
    None/[] so the rest of the pipeline (sections, MD/TXT/JSON/PDF, translation)
    works unchanged. The title is the file name (without extension) and the
    duration is probed with ffprobe. 'webpage_url' carries the absolute path so
    it shows up as the source in the output files."""
    path = os.path.abspath(path)
    return {
        "id": "",
        "title": os.path.splitext(os.path.basename(path))[0] or "audio",
        "channel": None,
        "views": None,
        "upload_date": None,
        "duration": _probe_duration(path),
        "chapters": [],
        "webpage_url": path,
        "source": "local",
        "source_path": path,
    }


def _lang_name(code: str | None, lang: str = "it") -> str | None:
    """Nome di una lingua, in italiano (default) o in inglese ('lang="en"').

    Accetta sia i codici ISO (faster-whisper: 'en') sia i nomi interi di Whisper
    (Groq: 'english'). None se assente. Il parametro 'lang' serve alla GUI in
    inglese, che vuole i nomi lingua in inglese ('English' invece di 'Inglese')."""
    if not code:
        return None
    c = str(code).split("-")[0].strip().lower()
    full = {"italian": "it", "english": "en", "spanish": "es",
            "french": "fr", "german": "de"}
    c = full.get(c, c)
    names_it = {"it": "Italiano", "en": "Inglese", "es": "Spagnolo",
                "fr": "Francese", "de": "Tedesco"}
    names_en = {"it": "Italian", "en": "English", "es": "Spanish",
                "fr": "French", "de": "German"}
    names = names_en if lang == "en" else names_it
    return names.get(c, str(code).upper())


def _is_italian(code: str | None) -> bool:
    """True se il codice/nome lingua indica l'italiano (es. 'it', 'italian').

    Usata per saltare la traduzione automatica quando l'audio è già in italiano
    (tradurre it -> it sarebbe inutile)."""
    if not code:
        return False
    c = str(code).split("-")[0].strip().lower()
    return c in ("it", "ita", "italian", "italiano")


def _lang_code(code: str | None) -> str | None:
    """Codice ISO a 2 lettere da un codice/nome lingua ('english'->'en'), o None.

    Normalizza sia i codici (faster-whisper: 'en') sia i nomi interi (Groq:
    'english') e alcuni nomi italiani ('inglese')."""
    if not code:
        return None
    c = str(code).split("-")[0].strip().lower()
    full = {"italian": "it", "english": "en", "spanish": "es", "french": "fr",
            "german": "de", "ita": "it", "eng": "en", "italiano": "it",
            "inglese": "en", "spagnolo": "es", "francese": "fr", "tedesco": "de"}
    return full.get(c, c)


def _is_same_language(detected: str | None, target: str | None) -> bool:
    """True se l'audio rilevato è GIÀ nella lingua 'target': tradurre sarebbe inutile.

    Generalizza _is_italian a una lingua qualsiasi: con interfaccia in inglese il
    target della traduzione è l'inglese, quindi un audio inglese non va tradotto."""
    d, t = _lang_code(detected), _lang_code(target)
    return bool(d and t and d == t)


# --- Messaggi runtime localizzati (avanzamento + avvisi mostrati dalla GUI) ---
# Il motore e l'analisi visiva sono UI-agnostici ma devono mostrare i testi nella
# lingua dell'interfaccia. Qui il catalogo unico it/en; la CLI è italiano-only e
# non lo usa (i suoi pannelli rich restano in italiano). Le stringhe con {…} sono
# formattate dai chiamanti con i valori (indici, nomi, errori).
_RUNTIME_MSGS = {
    # download / lettura sorgente
    "dl_audio":       {"it": "Scarico audio", "en": "Downloading audio"},
    "extract_audio":  {"it": "Estraggo audio", "en": "Extracting audio"},
    "convert_audio":  {"it": "Converto audio in m4a", "en": "Converting audio to m4a"},
    "dl_video":       {"it": "Scarico video", "en": "Downloading video"},
    "prep_video":     {"it": "Preparo il video", "en": "Preparing the video"},
    "read_audio":     {"it": "Leggo il file audio", "en": "Reading the audio file"},
    "read_info":      {"it": "Leggo le informazioni del video", "en": "Reading video information"},
    # trascrizione
    "chunk_prep":     {"it": "Blocco {i}/{n}", "en": "Chunk {i}/{n}"},
    "chunk_send":     {"it": "Invio blocco {i}/{n} a Groq", "en": "Sending chunk {i}/{n} to Groq"},
    "chunk_done":     {"it": "Blocco {i}/{n} completato", "en": "Chunk {i}/{n} done"},
    "model_load":     {"it": "Carico il modello '{model}' su {dev}{note} (primo uso: scarica i pesi)",
                       "en": "Loading model '{model}' on {dev}{note} (first use: downloads the weights)"},
    "resume_from":    {"it": " (ripresa da {ts})", "en": " (resuming from {ts})"},
    "transcribing":   {"it": "Trascrizione in corso", "en": "Transcribing"},
    "transcribed":    {"it": "Trascrizione completata", "en": "Transcription complete"},
    # traduzione
    "translating_to": {"it": "Traduco in {lang}", "en": "Translating to {lang}"},
    "section_tr":     {"it": "Sezione {i}/{n} tradotta", "en": "Section {i}/{n} translated"},
    "tr_unavail":     {"it": "Traduzione non disponibile: {e}", "en": "Translation unavailable: {e}"},
    "tr_interrupted": {"it": "Traduzione interrotta ({e}); parziale salvato, riprendibile.",
                       "en": "Translation interrupted ({e}); partial saved, resumable."},
    "tr_pdf_fail":    {"it": "PDF della traduzione non creato: {e}", "en": "Translation PDF not created: {e}"},
    "audio_already":  {"it": "Audio già in {lang}: traduzione non necessaria.",
                       "en": "Audio already in {lang}: translation not needed."},
    # riassunto
    "summarizing":    {"it": "Riassumo le sezioni", "en": "Summarizing sections"},
    "section_sum":    {"it": "Sezione {i}/{n} riassunta", "en": "Section {i}/{n} summarized"},
    "sum_unavail":    {"it": "Riassunto non disponibile: {e}", "en": "Summary unavailable: {e}"},
    "sum_ratelimit":  {"it": "Crediti Groq esauriti: riassunto interrotto e salvato come parziale — riprendibile (anche in locale).",
                       "en": "Groq credits exhausted: summary interrupted and saved as a partial — resumable (locally too)."},
    "sum_fail":       {"it": "Riassunto fallito: {e}", "en": "Summary failed: {e}"},
    "sum_pdf_fail":   {"it": "PDF del riassunto non creato: {e}", "en": "Summary PDF not created: {e}"},
    # salvataggio
    "saving_files":   {"it": "Salvo i file", "en": "Saving files"},
    "creating_pdf":   {"it": "Creo il PDF", "en": "Creating the PDF"},
    "trans_pdf_fail": {"it": "PDF della trascrizione non creato: {e}", "en": "Transcription PDF not created: {e}"},
    # analisi visiva
    "vis_unavail":    {"it": "Analisi visiva non disponibile: {e}", "en": "Visual analysis unavailable: {e}"},
    "vis_detect":     {"it": "Individuo i fotogrammi chiave (cambi scena)…",
                       "en": "Detecting key frames (scene changes)…"},
    "vis_noframes":   {"it": "Nessun fotogramma significativo individuato",
                       "en": "No significant frames found"},
    "vis_toanalyze":  {"it": "{n} fotogrammi da analizzare ({label})",
                       "en": "{n} frames to analyze ({label})"},
    "vis_ratelimit":  {"it": "Crediti Groq esauriti durante l'analisi visiva",
                       "en": "Groq credits exhausted during visual analysis"},
    "vis_analyzing":  {"it": "Analizzo fotogramma {i}/{n}", "en": "Analyzing frame {i}/{n}"},
    "vis_extracted":  {"it": "{k} contenuti visivi estratti su {n} fotogrammi",
                       "en": "{k} visual items extracted from {n} frames"},
    "vis_skipped":    {"it": "Analisi visiva saltata: il video non era disponibile (sorgente solo-audio o download video non riuscito).",
                       "en": "Visual analysis skipped: the video was not available (audio-only source or video download failed)."},
    "vis_incomplete": {"it": "Analisi visiva non completata: {e}", "en": "Visual analysis not completed: {e}"},
    # motivi di fallimento dell'analisi visiva (_visual_failure_reason)
    "vfr_ratelimit":  {"it": "Analisi visiva interrotta: crediti {eng} esauriti. I crediti del modello vision sono SEPARATI da quelli di trascrizione/riassunto. Riprova quando si azzerano (vedi «crediti») o usa un modello vision locale via Ollama.",
                       "en": "Visual analysis interrupted: {eng} credits exhausted. The vision model's credits are SEPARATE from transcription/summary. Retry when they reset (see “credits”) or use a local vision model via Ollama."},
    "vfr_eng_groq":   {"it": "Groq (qwen vision)", "en": "Groq (qwen vision)"},
    "vfr_eng_other":  {"it": "del modello vision", "en": "of the vision model"},
    "vfr_noframes":   {"it": "Analisi visiva: nessun fotogramma significativo individuato nel video.",
                       "en": "Visual analysis: no significant frames found in the video."},
    "vfr_allerrors":  {"it": "Analisi visiva non riuscita: il modello vision ha restituito errore su tutti i {n} fotogrammi ({err}).",
                       "en": "Visual analysis failed: the vision model returned an error on all {n} frames ({err})."},
    "vfr_notech":     {"it": "Analisi visiva: nessun contenuto tecnico (codice/formule/grafici) rilevato nei {n} fotogrammi analizzati.",
                       "en": "Visual analysis: no technical content (code/formulas/charts) detected in the {n} frames analyzed."},
    "vfr_unknown_err":{"it": "errore sconosciuto", "en": "unknown error"},
}


def msg(key: str, lang: str = "it", /, **fmt) -> str:
    """Testo runtime localizzato dal catalogo _RUNTIME_MSGS (fallback: italiano).

    'lang' = "it"/"en" (posizionale, così un eventuale segnaposto {lang} nella
    stringa non entra in conflitto col parametro); i segnaposto {…} sono riempiti
    con 'fmt'."""
    d = _RUNTIME_MSGS.get(key, {})
    s = d.get(lang) or d.get("it") or key
    return s.format(**fmt) if fmt else s


def display_video_info(meta: dict) -> None:
    """Show the video card in a colored box (title, channel, views, likes,
    subscribers, category, date, duration, number of chapters)."""
    table = Table(show_header=False, box=None, expand=False, padding=(0, 1))
    table.add_column("Icona", justify="center", no_wrap=True)
    table.add_column("Campo", style="dim", justify="left", no_wrap=True)
    table.add_column("Valore", style="bold bright_white", min_width=40, overflow="fold")

    table.add_row("📺", "Canale", meta["channel"])
    table.add_row("👁 ", "Visualizzazioni", _format_views(meta["views"]))
    if meta.get("likes") is not None:
        table.add_row("👍", "Mi piace", _format_views(meta["likes"]))
    if meta.get("subscribers") is not None:
        table.add_row("👥", "Iscritti", _format_views(meta["subscribers"]))
    if meta.get("category"):
        table.add_row("🏷 ", "Categoria", meta["category"])
    lang = _lang_name(meta.get("language"))
    if lang:
        table.add_row("🗣 ", "Lingua", lang)
    table.add_row("📅", "Pubblicato", _format_upload_date(meta["upload_date"]))
    table.add_row("⏱ ", "Durata", f"[bright_cyan]{_format_duration(meta['duration'])}[/bright_cyan]")
    n_chapters = len(meta["chapters"])
    if n_chapters:
        table.add_row("📑", "Capitoli", f"[success]{n_chapters} sezioni[/success]")
    else:
        table.add_row("📑", "Capitoli", "[dim]nessuno (testo continuo)[/dim]")

    console.print()
    console.print(Panel(
        table,
        title=f"[title]🎬 {meta['title']}[/title]", title_align="left",
        border_style="bright_cyan", box=ROUNDED, expand=False, padding=(1, 2),
    ))


# === PHASE 1: AUDIO DOWNLOAD ===

def download_audio(url: str, workdir: str, on_progress=_noop_progress,
                   should_stop=_never_stop, lang: str = "it") -> str:
    """Download ONLY the video's audio into the temporary folder `workdir`.

    Versione SENZA interfaccia, condivisa da CLI e GUI: l'avanzamento esce da
    `on_progress(phase, current, total, detail)` invece di essere disegnato qui,
    così chi chiama decide se mostrarlo con una barra rich, in una GUI o per
    niente. `should_stop()` viene interrogata a ogni tick per poter annullare
    (la CLI la aggancia a Ctrl+C). Restituisce il percorso del file audio;
    solleva MediaError se qualcosa va storto. Wrapper CLI: `_cli_download_audio`."""
    out_template = os.path.join(workdir, "audio.%(ext)s")  # %(ext)s = the actual extension chosen by yt-dlp

    def _hook(d: dict) -> None:
        """Callback called by yt-dlp with the download status."""
        if should_stop():
            # Raising an exception here interrupts the yt-dlp download.
            raise KeyboardInterrupt
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            on_progress("download", done, total, msg("dl_audio", lang))
        elif d["status"] == "finished":
            # Download finished: but yt-dlp now EXTRACTS the audio with ffmpeg (a
            # few seconds, without a percentage). We signal it so it does not look stuck.
            on_progress("download", None, None, msg("extract_audio", lang))

    def _pp_hook(d: dict) -> None:
        """Post-processor callback (the audio conversion after the download).

        It serves to NOT leave the screen frozen during the audio extraction: we
        report it so the user sees that the work continues."""
        if d.get("status") == "started":
            on_progress("download", None, None, msg("convert_audio", lang))

    ydl_opts = {
        "format": "bestaudio/best",   # the best audio-only track available
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,           # suppress yt-dlp's internal bar (we draw our own)
        "progress_hooks": [_hook],
        "postprocessor_hooks": [_pp_hook],  # to show the progress of the conversion
        # Extracts/normalizes the audio into m4a via ffmpeg (already present on the system).
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise MediaError(f"Errore nel download audio: {e}")

    # The postprocessor produces a .m4a: we look for it in the working folder.
    for fname in os.listdir(workdir):
        if fname.startswith("audio."):
            return os.path.join(workdir, fname)
    raise MediaError("File audio non trovato dopo il download.")


def _download_progress(description: str):
    """Barra rich per i download: spinner, %, byte, velocità e tempo stimato.

    Restituisce (progress, task_id, on_progress): `on_progress` è la callback da
    passare alle funzioni core, che traduce i loro tick in aggiornamenti della
    barra. Il testo `detail` che arriva dal core diventa la descrizione, così la
    dicitura ("Estraggo audio", "Converto audio in m4a"…) resta una sola, presa
    dal catalogo dei messaggi."""
    progress = Progress(
        SpinnerColumn("dots", style="bright_blue"),
        TextColumn("[phase]{task.description}"),
        BarColumn(bar_width=40, style="bar.back", complete_style="bright_blue", finished_style="bright_green"),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TextColumn("[dim]→[/dim]"),
        TimeRemainingColumn(),
        console=console, expand=False,
    )
    task_id = progress.add_task(description, total=None)  # total=None: unknown until yt-dlp reports it

    def on_progress(phase, current, total, detail="") -> None:
        if current is None:
            progress.update(task_id, description=detail or description)
            return
        if total:
            progress.update(task_id, completed=current, total=total)
        else:
            progress.update(task_id, completed=current)

    return progress, task_id, on_progress


def _cli_download_audio(url: str, workdir: str) -> str | None:
    """download_audio per la CLI: barra rich, Ctrl+C e None su errore."""
    progress, _task, on_progress = _download_progress("Scarico audio")
    try:
        with progress:
            return download_audio(url, workdir, on_progress,
                                  should_stop=lambda: _interrupted)
    except KeyboardInterrupt:
        return None
    except MediaError as e:
        console.print(f"[error]{e}[/error]")
        return None


# === PHASE 2: PREPARATION / SPLITTING ===

def split_audio(audio_path: str, duration: float, workdir: str,
                on_progress=_noop_progress, should_stop=_never_stop,
                lang: str = "it") -> list[tuple[float, str]]:
    """Split the audio into chunks of CHUNK_SECONDS, re-encoding them to 16 kHz mono.

    For each chunk it launches ffmpeg with:
      -ss <start>     -> skip to the chunk's start second
      -t  <duration>  -> take only CHUNK_SECONDS seconds
      -ac 1           -> 1 channel (mono)
      -ar 16000       -> 16 kHz (format Whisper likes)
    Returns a list of pairs (offset_in_seconds, mp3_file_path).
    The offset is used later to correct each chunk's timestamps.
    Versione senza interfaccia: l'avanzamento esce da `on_progress` e
    `should_stop()` permette di annullare a metà. Wrapper CLI:
    `_cli_split_audio`."""
    chunks: list[tuple[float, str]] = []
    # Number of chunks computed in advance (rounded up) to give the bar a total.
    # max(1, ...) avoids 0 chunks on very short audio.
    n_chunks = max(1, int((duration + CHUNK_SECONDS - 1) // CHUNK_SECONDS)) if duration else 1

    start = 0.0
    idx = 0
    while start < duration:
        if should_stop():
            break
        out_path = os.path.join(workdir, f"chunk_{idx:03d}.mp3")
        cmd = [
            "ffmpeg", "-y",                 # -y = overwrite without asking
            "-ss", str(start),              # start point
            "-t", str(CHUNK_SECONDS),       # how many seconds to take
            "-i", audio_path,               # input file
            "-ac", "1",                     # mono
            "-ar", str(AUDIO_SAMPLE_RATE),  # 16 kHz
            "-b:a", AUDIO_BITRATE,          # audio bitrate
            out_path,
        ]
        # stdout/stderr discarded: we only care that the file gets created.
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        chunks.append((start, out_path))
        start += CHUNK_SECONDS
        idx += 1
        on_progress("prepare", idx, n_chunks, msg("chunk_prep", lang, i=idx, n=n_chunks))
    return chunks


def _cli_split_audio(audio_path: str, duration: float, workdir: str) -> list[tuple[float, str]]:
    """split_audio per la CLI: barra rich che cresce a ogni blocco creato."""
    n_chunks = max(1, int((duration + CHUNK_SECONDS - 1) // CHUNK_SECONDS)) if duration else 1
    progress = Progress(
        SpinnerColumn("dots", style="bright_blue"),
        TextColumn("[phase]{task.description}"),
        BarColumn(bar_width=40, style="bar.back", complete_style="bright_blue", finished_style="bright_green"),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        console=console, expand=False,
    )
    with progress:
        task_id = progress.add_task("Creo i blocchi", total=n_chunks)

        def on_progress(phase, current, total, detail="") -> None:
            progress.update(task_id, completed=current or 0)

        return split_audio(audio_path, duration, workdir, on_progress,
                           should_stop=lambda: _interrupted)


# === PHASE 3: TRANSCRIPTION WITH GROQ ===

# Sentinel telling a function to fall back to the module-level LANGUAGE config
# (we cannot use None for that, since None is itself a valid value = "auto-detect").
_USE_CONFIG = object()


def _coerce(obj, key):
    """Read 'key' from an item that may be a dict OR an object (the Groq SDK
    returns both depending on version): obj['key'] if a mapping, else
    getattr(obj, key)."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _extract_words(result) -> list[dict]:
    """Normalize Groq's per-word timestamps (when requested) to a flat list of
    {word, start, end}. Returns [] if the response carries no word timings."""
    raw = getattr(result, "words", None) or []
    words = []
    for w in raw:
        txt = _coerce(w, "word")
        start, end = _coerce(w, "start"), _coerce(w, "end")
        if txt is None or start is None or end is None:
            continue
        words.append({"word": str(txt), "start": float(start), "end": float(end)})
    return words


def _transcribe_chunk(client: Groq, chunk_path: str, prompt: str = "",
                      return_language: bool = False, language=_USE_CONFIG,
                      want_words: bool | None = None, on_headers=None):
    """Send ONE audio chunk to Groq and return the list of its segments.

    Uses response_format='verbose_json' to receive, in addition to the text, the
    start/end timestamps of each sentence ('segments'). 'prompt' contains the
    tail of the previous transcription: giving Whisper a bit of context improves
    continuity (proper names, terminology) from one chunk to the next.
    Retries up to MAX_RETRIES times in case of a network/API error.

    'language' forces the audio language (e.g. 'it'/'en'); the _USE_CONFIG
    sentinel means "use the LANGUAGE config" (None there = auto-detect).
    'want_words' requests per-word timestamps (defaults to the WORD_TIMESTAMPS
    config); when on, each segment also carries a 'words' list (start/end/word).

    'on_headers' (optional): if given, the call uses the raw response and passes
    its HTTP headers to on_headers(headers) — so the engine can read the
    x-ratelimit-* budget. None (the CLI default) keeps the plain call unchanged.

    If return_language=True, returns (segments, language) where 'language' is the
    ISO code Whisper auto-detected (e.g. 'en'/'it'), otherwise just the segments
    (backward-compatible default for the CLI)."""
    lang_opt = LANGUAGE if language is _USE_CONFIG else language
    words_on = WORD_TIMESTAMPS if want_words is None else want_words
    granularities = ["segment", "word"] if words_on else ["segment"]

    def _ret(segs, lang):
        return (segs, lang) if return_language else segs

    def _attach_words(seg_start: float, seg_end: float, words: list[dict]) -> list[dict]:
        """Pick the words whose start falls inside this segment's [start, end)."""
        return [w for w in words if seg_start - 0.05 <= w["start"] < seg_end + 0.05]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(chunk_path, "rb") as f:
                params = dict(
                    file=(os.path.basename(chunk_path), f.read()),
                    model=GROQ_MODEL,
                    response_format="verbose_json",
                    timestamp_granularities=granularities,
                    language=lang_opt,            # None = auto-detection
                    prompt=prompt[-400:],         # last ~400 characters as context
                    temperature=0.0,             # 0 = more deterministic/faithful output
                )
                if on_headers is not None:
                    # Raw response so the caller can read the x-ratelimit-* headers
                    # (the Groq "credits"); .parse() yields the same parsed object.
                    # Header reading must NEVER cost us the transcription: on any
                    # unexpected SDK error (but not rate-limit/auth) we fall back to
                    # the plain call and simply skip the credit info.
                    try:
                        raw = client.audio.transcriptions.with_raw_response.create(**params)
                    except Exception as raw_err:
                        rmsg = str(raw_err)
                        if _is_rate_limit(rmsg) or "401" in rmsg or "403" in rmsg:
                            raise
                        result = client.audio.transcriptions.create(**params)
                    else:
                        try:
                            on_headers(raw.headers)
                        except Exception:
                            pass
                        # Crediti: registra i limiti del modello di trascrizione
                        # (a costo zero, dalla risposta che stiamo già leggendo).
                        record_rate_limits(GROQ_MODEL, raw.headers)
                        result = raw.parse()
                else:
                    result = client.audio.transcriptions.create(**params)
            lang = getattr(result, "language", None)
            # result.segments is a list of objects with .start, .end, .text
            segments = getattr(result, "segments", None)
            if segments is None:
                # If for some reason there are no segments, we fall back to the whole text.
                return _ret([{"start": 0.0, "end": 0.0, "text": getattr(result, "text", "").strip()}], lang)
            words = _extract_words(result) if words_on else []
            out_segs = []
            for s in segments:
                ss, se = float(s["start"]), float(s["end"])
                seg = {"start": ss, "end": se, "text": s["text"].strip()}
                if words:
                    seg["words"] = _attach_words(ss, se, words)
                out_segs.append(seg)
            return _ret(out_segs, lang)
        except GroqRateLimit:
            raise
        except Exception as e:
            msg = str(e)
            # Limite Groq (429 / token-al-giorno): inutile insistere, fermiamoci
            # subito così chi chiama può salvare un checkpoint e riprendere dopo.
            if _is_rate_limit(msg):
                raise GroqRateLimit(msg)
            # Authentication/access errors (401/403): there is NO point retrying,
            # they do not resolve on their own. We stop immediately with a clear message.
            if "401" in msg or "403" in msg or "invalid_api_key" in msg:
                console.print(f"  [error]Accesso a Groq negato (chiave/rete): {e}[/error]")
                return _ret([], None)
            if attempt == MAX_RETRIES:
                console.print(f"  [error]Blocco fallito dopo {MAX_RETRIES} tentativi: {e}[/error]")
                return _ret([], None)
            # Increasing wait between one attempt and the next (linear backoff).
            import time
            time.sleep(2 * attempt)
    return _ret([], None)


def transcribe(client: Groq, chunks: list[tuple[float, str]],
               start_index: int = 0, prior_segments: list | None = None,
               prior_lang=None):
    """Transcribe chunks in order (con ripresa), with a progress bar.

    Parte dal blocco 'start_index' riusando 'prior_segments' già trascritti (per
    riprendere un video interrotto). Per ogni blocco aggiunge l'offset ai
    timestamp. Restituisce (segments, detected_language). Se Groq rifiuta per
    limite, solleva TranscriptionInterrupted col parziale, così si può salvare
    un checkpoint e riprendere più tardi."""
    all_segments: list[dict] = list(prior_segments or [])
    detected = prior_lang
    # Contesto iniziale: la coda di ciò che è già stato trascritto.
    context = " ".join(s["text"] for s in all_segments[-6:]) if all_segments else ""

    progress = Progress(
        SpinnerColumn("dots", style="bright_green"),
        TextColumn("[phase]{task.description}"),
        BarColumn(bar_width=40, style="bar.back", complete_style="bright_green", finished_style="bold green"),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TextColumn("[dim]│[/dim]"),
        TimeElapsedColumn(),
        TextColumn("[dim]→[/dim]"),
        TimeRemainingColumn(),
        console=console, expand=False,
    )

    n = len(chunks)
    with progress:
        task_id = progress.add_task(f"Invio blocco {start_index + 1}/{n} a Groq",
                                    total=n, completed=start_index)
        for i in range(start_index, n):
            if _interrupted:
                break
            offset, path = chunks[i]
            # We update the description BEFORE the call: the rich spinner keeps
            # animating while waiting for Groq, so the user sees the i-th chunk.
            progress.update(task_id, description=f"Invio blocco {i + 1}/{n} a Groq (attendi)")
            try:
                if i == start_index:
                    segments, lang = _transcribe_chunk(
                        client, path, prompt=context, return_language=True)
                    detected = detected or lang
                else:
                    segments = _transcribe_chunk(client, path, prompt=context)
            except GroqRateLimit:
                # Limite raggiunto: i blocchi 0..i-1 sono fatti. Trasportiamo il
                # parziale a chi chiama per il checkpoint.
                raise TranscriptionInterrupted(all_segments, i, n, detected)
            for seg in segments:
                # Timing correction: + the chunk's offset (segment AND its words).
                seg["start"] += offset
                seg["end"] += offset
                for w in seg.get("words", []):
                    w["start"] += offset
                    w["end"] += offset
                all_segments.append(seg)
            # We update the context with the text of this chunk.
            if segments:
                context = " ".join(s["text"] for s in segments)
            progress.update(task_id, advance=1, description=f"Blocco {i + 1}/{n} completato")

    return all_segments, detected


# === LOCAL BACKEND: TRANSCRIPTION WITH faster-whisper ===

def _resolve_device() -> tuple[str, str]:
    """Pick (device, compute_type) for faster-whisper, honoring the config.

    LOCAL_DEVICE 'auto' (the default) selects CUDA when a GPU is available (5-20x
    faster), otherwise CPU. An empty LOCAL_COMPUTE_TYPE auto-picks the fast,
    low-loss default for the device: float16 on GPU, int8 on CPU. Both can be
    forced via .env (ECHOSCRIPT_DEVICE / ECHOSCRIPT_COMPUTE_TYPE)."""
    device = LOCAL_DEVICE.strip().lower()
    if device in ("", "auto"):
        device = "cpu"
        try:
            import torch  # optional: only present if the user installed it
            if torch.cuda.is_available():
                device = "cuda"
        except Exception:
            pass
    compute = LOCAL_COMPUTE_TYPE.strip() or ("float16" if device == "cuda" else "int8")
    return device, compute


def transcribe_local(model_name: str, audio_path: str, duration: float,
                     on_progress=_noop_progress, should_stop=_never_stop,
                     language=_USE_CONFIG, meta: dict | None = None,
                     resume_cp: dict | None = None, workdir: str | None = None,
                     lang: str = "it"):
    """Transcribe the entire audio LOCALLY with faster-whisper (no data over the network).

    Returns (segments, detected_language). Solleva MediaError se il modello non
    si carica o la trascrizione fallisce.

    Unlike Groq, no splitting is needed: faster-whisper processes the whole file
    and returns the segments incrementally (a generator), so progress can be
    reported as we go: `on_progress` riceve il secondo di audio raggiunto sul
    totale della durata.

    'language' forza la lingua dell'audio; il default `_USE_CONFIG` significa
    "usa LANGUAGE dalla configurazione" (None sarebbe ambiguo: vale già
    "autorileva"). `should_stop()` interrompe il ciclo a fine segmento.

    RESUME: if 'meta' is given, the partial result is checkpointed every
    LOCAL_CHECKPOINT_EVERY seconds of audio. If a matching checkpoint exists (and
    'workdir' is available for the trimmed file), we trim the audio from the saved
    point with ffmpeg, transcribe only the remainder, and shift its timestamps
    back, so an interrupted long run resumes instead of starting over. Se il
    ciclo viene fermato da `should_stop`, il parziale resta salvato per la
    ripresa; se arriva in fondo, il checkpoint viene cancellato.

    PRIVACY: on the first use of a model, faster-whisper downloads its "weights"
    from HuggingFace (once only, then they stay cached). The AUDIO, however, is
    never sent anywhere: the transcription happens on your PC.

    Versione senza interfaccia. Wrapper CLI: `_cli_transcribe_local`."""
    # Silence the HuggingFace warning about symlinks (irrelevant: the cache works
    # anyway). It must be set BEFORE importing faster-whisper.
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    # "Lazy" import: only those who use the local backend need faster-whisper.
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise MediaError("faster-whisper non installato. Esegui: pip install faster-whisper")

    if language is _USE_CONFIG:
        language = LANGUAGE

    # Device/precision: GPU (CUDA) when available, else CPU (see _resolve_device).
    device, compute_type = _resolve_device()
    dev_note = "GPU (CUDA)" if device == "cuda" else "CPU"

    # Resume point (if a matching checkpoint exists): reuse prior segments and feed
    # faster-whisper only the not-yet-transcribed tail of the audio.
    start_offset, all_segments, detected = _local_resume_point(model_name, duration, resume_cp)
    transcribe_path = audio_path
    if start_offset > 0:
        if workdir is None:
            start_offset, all_segments, detected = 0.0, [], None  # cannot trim: full re-run
        else:
            try:
                transcribe_path = _trim_audio(audio_path, start_offset, workdir)
            except Exception:
                start_offset, all_segments, detected = 0.0, [], None  # trim failed: full re-run

    # Loading the model (on first use it downloads the weights) e avvio: il
    # chiamante mostra l'attesa come preferisce (spinner CLI, stato nella GUI).
    note = msg("resume_from", lang, ts=_format_timestamp(start_offset)) if start_offset > 0 else ""
    on_progress("transcribe", None, None,
                msg("model_load", lang, model=model_name, dev=dev_note, note=note))
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        # transcribe() returns (segment_generator, info). The segments are produced
        # as the audio is processed. vad_filter skips the silences; word_timestamps
        # asks for per-word timings (so segments carry a 'words' list).
        segments_gen, info = model.transcribe(
            transcribe_path, language=language, vad_filter=True, beam_size=5,
            word_timestamps=WORD_TIMESTAMPS,
        )
    except Exception as e:
        raise MediaError(f"Errore nella trascrizione locale: {e}")
    detected = detected or getattr(info, "language", None)

    last_abs_end = start_offset   # highest audio time reached (absolute)
    last_saved = start_offset     # audio time at the last checkpoint save
    completed_fully = True
    for seg in segments_gen:
        if should_stop():
            completed_fully = False
            break
        # Shift the tail's timestamps back to their absolute position.
        abs_start, abs_end = float(seg.start) + start_offset, float(seg.end) + start_offset
        entry = {"start": abs_start, "end": abs_end, "text": seg.text.strip()}
        seg_words = getattr(seg, "words", None) or []
        if seg_words:
            entry["words"] = [
                {"word": w.word, "start": float(w.start) + start_offset,
                 "end": float(w.end) + start_offset}
                for w in seg_words if w.start is not None and w.end is not None
            ]
        all_segments.append(entry)
        last_abs_end = abs_end
        if duration:
            # min() avoids exceeding 100% if the last segment overruns the estimate.
            on_progress("transcribe", min(abs_end, duration), duration, msg("transcribing", lang))
        # Periodic checkpoint, so an interruption loses at most a couple of minutes.
        if meta and (abs_end - last_saved) >= LOCAL_CHECKPOINT_EVERY:
            save_local_checkpoint(meta, all_segments, abs_end, model_name, duration, detected)
            last_saved = abs_end
    if duration and completed_fully:
        on_progress("transcribe", duration, duration, msg("transcribed", lang))

    # Done -> drop the checkpoint; interrupted -> keep the latest partial to resume.
    if meta:
        if completed_fully:
            delete_local_checkpoint(meta)
        else:
            save_local_checkpoint(meta, all_segments, last_abs_end, model_name, duration, detected)
    return all_segments, detected


def _cli_transcribe_local(model_name: str, audio_path: str, duration: float,
                          meta: dict | None = None, resume_cp: dict | None = None,
                          workdir: str | None = None):
    """transcribe_local per la CLI: spinner di caricamento, barra sulla durata,
    Ctrl+C e ([], None) invece dell'eccezione (la pipeline gestisce già il caso
    "nessun segmento")."""
    # Nota di ripresa: la stampiamo prima, come faceva la versione precedente.
    start_offset, prior, _lang = _local_resume_point(model_name, duration, resume_cp)
    if start_offset > 0 and workdir is not None:
        console.print(f"  [info]Ripresa dalla posizione {_format_timestamp(start_offset)} "
                      f"({len(prior)} segmenti già fatti).[/info]")

    progress = Progress(
        SpinnerColumn("dots", style="bright_green"),
        TextColumn("[phase]{task.description}"),
        BarColumn(bar_width=40, style="bar.back", complete_style="bright_green", finished_style="bold green"),
        TaskProgressColumn(),
        TextColumn("[dim]│[/dim]"),
        TimeElapsedColumn(),
        TextColumn("[dim]→[/dim]"),
        TimeRemainingColumn(),
        console=console, expand=False,
    )
    # total = the video's duration: the bar advances based on the reached timestamp.
    task_id = progress.add_task("Trascrivo (locale)", total=duration or None,
                                completed=min(start_offset, duration) if duration else None)

    def on_progress(phase, current, total, detail="") -> None:
        if current is None:
            # Tick senza numeri = messaggio di stato (caricamento del modello):
            # lo stampiamo sopra la barra, che resta ferma finché non parte.
            if detail:
                console.print(f"  [info]{detail}[/info]")
            return
        progress.update(task_id, completed=current)

    try:
        with progress:
            return transcribe_local(model_name, audio_path, duration, on_progress,
                                    should_stop=lambda: _interrupted, meta=meta,
                                    resume_cp=resume_cp, workdir=workdir)
    except MediaError as e:
        console.print(f"[error]{e}[/error]")
        return [], None


# === BUILDING THE FINAL DOCUMENT ===

def _build_sections(meta: dict, segments: list[dict]) -> list[dict]:
    """Group the segments into SECTIONS, the common basis of all text formats.

    If the video has YouTube chapters, it creates one section per chapter,
    joining the sentences that fall within it into a single flowing paragraph.
    Otherwise it creates a single "untitled" section with all the text. Each
    section is: {'start': seconds|None, 'title': str|None, 'text': str}."""
    chapters = meta["chapters"]
    sections: list[dict] = []
    if chapters:
        for ch in chapters:
            ch_start = ch.get("start_time", 0)
            ch_end = ch.get("end_time", float("inf"))
            text = " ".join(s["text"] for s in segments if ch_start <= s["start"] < ch_end).strip()
            sections.append({"start": ch_start, "title": ch.get("title") or "Sezione", "text": text})
    else:
        sections.append({"start": None, "title": None,
                         "text": " ".join(s["text"] for s in segments).strip()})
    return sections


def _md_header(title: str, meta: dict, engine_label: str,
               saved_in: str | None = None) -> list[str]:
    """Markdown header lines (metadata) shared between original and translated.

    Local files have no channel/views/date, so we show the source path instead.
    'saved_in' (se passato) aggiunge la riga «Salvato in:» col percorso della
    cartella di output, subito dopo «Trascritto con:» (usata nei PDF)."""
    saved_line = [f"- **Salvato in:** {saved_in}"] if saved_in else []
    if _is_local(meta):
        return [
            f"# {title}", "",
            "- **Sorgente:** File audio locale",
            f"- **File:** {meta['webpage_url']}",
            f"- **Durata:** {_format_duration(meta['duration'])}",
            f"- **Trascritto con:** {engine_label}",
            *saved_line,
            "", "---", "",
        ]
    return [
        f"# {title}", "",
        f"- **Canale:** {meta['channel']}",
        f"- **Pubblicato:** {_format_upload_date(meta['upload_date'])}",
        f"- **Visualizzazioni:** {_format_views(meta['views'])}",
        f"- **Durata:** {_format_duration(meta['duration'])}",
        f"- **URL:** {meta['webpage_url']}",
        f"- **Trascritto con:** {engine_label}",
        *saved_line,
        "", "---", "",
    ]


def build_md(title: str, meta: dict, engine_label: str, sections: list[dict],
             with_timestamps: bool = True, saved_in: str | None = None) -> str:
    """Markdown document: header + sections.

    The timings (if with_timestamps) appear ONLY in the section titles
    (## [HH:MM:SS] Title); the body is flowing prose, tidier. The translated
    version passes with_timestamps=False (no timings). 'saved_in' (usato dai PDF)
    aggiunge la riga «Salvato in:» col percorso di output nell'intestazione."""
    lines = _md_header(title, meta, engine_label, saved_in=saved_in)
    for sec in sections:
        if sec["title"] is None:
            lines.append("## Trascrizione")
        elif with_timestamps and sec["start"] is not None:
            lines.append(f"## [{_format_timestamp(sec['start'])}] {sec['title']}")
        else:
            lines.append(f"## {sec['title']}")
        lines.append("")
        if sec["text"]:
            lines.append(sec["text"])
        lines.append("")
    return "\n".join(lines)


def _strip_md_bold(text: str) -> str:
    """Toglie i marcatori **grassetto** del Markdown, lasciando il testo nudo.

    Serve al .txt del riassunto: il grassetto è utile a video/PDF, ma nel testo
    semplice gli asterischi sarebbero solo rumore."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def build_txt(title: str, meta: dict, sections: list[dict],
              markdown: bool = False) -> str:
    """Clean TXT version (for other LLMs): no timings, sections as [Title].

    Con 'markdown=True' (riassunto) il testo può contenere **grassetto**: viene
    ripulito dai marcatori per restare testo piano."""
    def _plain(s: str) -> str:
        return _strip_md_bold(s) if (markdown and s) else s
    if _is_local(meta):
        lines = [
            title,
            f"Sorgente: file locale | Durata: {_format_duration(meta['duration'])}",
            f"File: {meta['webpage_url']}", "",
        ]
    else:
        lines = [
            title,
            f"Canale: {meta['channel']} | Pubblicato: {_format_upload_date(meta['upload_date'])} "
            f"| Durata: {_format_duration(meta['duration'])}",
            f"URL: {meta['webpage_url']}", "",
        ]
    for sec in sections:
        if sec["title"]:
            lines.append(f"[{_plain(sec['title'])}]")
        if sec["text"]:
            lines.append(_plain(sec["text"]))
        lines.append("")
    return "\n".join(lines)


def build_transcript_json(meta: dict, segments: list[dict], engine_label: str) -> str:
    """Structured JSON version, ideal for RAG pipelines / programmatic use.

    Contains the metadata, the chapters and all the segments with their
    timestamps (start/end in seconds): a format easy to "split" into chunks and
    index. ensure_ascii=False keeps the accented letters readable; indent=2 makes
    it readable to the eye as well."""
    data = {
        "title": meta["title"],
        "source": meta.get("source", "youtube"),
        "channel": meta["channel"],
        "upload_date": _format_upload_date(meta["upload_date"]),
        "views": meta["views"],
        "duration_seconds": meta["duration"],
        "url": meta["webpage_url"],
        "engine": engine_label,
        "chapters": [
            {"start": ch.get("start_time"), "end": ch.get("end_time"), "title": ch.get("title")}
            for ch in meta["chapters"]
        ],
        "segments": segments,   # each segment is {start, end, text}
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


# === EXPORT FOR READING (PDF) ===

def _section_heading(sec: dict, with_timestamps: bool) -> str:
    """Build the visible title of a section (with or without timing)."""
    if sec["title"] is None:
        return "Trascrizione"
    if with_timestamps and sec["start"] is not None:
        return f"[{_format_timestamp(sec['start'])}] {sec['title']}"
    return sec["title"]


def build_pdf(title: str, meta: dict, sections: list[dict], out_path: str,
              with_timestamps: bool = True, markdown: bool = False,
              engine_label: str = "", saved_in: str | None = None) -> None:
    """Create a readable PDF, divided by chapters, with fpdf2 (no LaTeX).

    Uses Windows' Arial font (TrueType) to support accents and Unicode
    characters. Large title, metadata in italics, section titles in bold and the
    body text in paragraphs. Con 'markdown=True' (riassunto) il corpo interpreta
    il **grassetto** Markdown, così le parole chiave risaltano anche nel PDF.
    Aggiunge un SOMMARIO cliccabile in testa (link interni ai capitoli) e i
    segnalibri/outline del PDF; NON stampa data, percorso o numero di pagina.
    'saved_in' aggiunge la riga «Salvato in:» tra i metadati."""
    from fpdf import FPDF                  # lazy import: needed only when exporting
    from fpdf.enums import XPos, YPos       # to bring the cursor back to the left after each cell

    font_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    # We register Arial with a custom family name so as not to conflict with
    # fpdf's "core" fonts.
    pdf.add_font("Doc", "", os.path.join(font_dir, "arial.ttf"))
    pdf.add_font("Doc", "B", os.path.join(font_dir, "arialbd.ttf"))
    pdf.add_font("Doc", "I", os.path.join(font_dir, "ariali.ttf"))
    pdf.add_page()

    # Helper: writes a full-width paragraph and brings the cursor back to the left
    # margin (otherwise the next multi_cell would have no space).
    def cell(h: float, txt: str, md: bool = False) -> None:
        pdf.multi_cell(0, h, txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT, markdown=md)

    # Title
    pdf.set_font("Doc", "B", 18)
    cell(9, title)
    pdf.ln(1)
    # Metadata
    pdf.set_font("Doc", "I", 10)
    if _is_local(meta):
        cell(5, f"Sorgente: file locale  |  Durata: {_format_duration(meta['duration'])}")
        cell(5, meta["webpage_url"])
    else:
        cell(5, f"Canale: {meta['channel']}  |  Pubblicato: {_format_upload_date(meta['upload_date'])}"
                f"  |  Durata: {_format_duration(meta['duration'])}")
        cell(5, meta["webpage_url"])
    if engine_label:
        cell(5, f"Trascritto con: {engine_label}")
    if saved_in:
        cell(5, f"Salvato in: {saved_in}")
    pdf.ln(4)

    for sec in sections:
        pdf.set_font("Doc", "B", 14)
        # Ogni capitolo diventa una voce dei SEGNALIBRI/outline del PDF: è il
        # «Sommario» cliccabile nel pannello laterale del lettore, che rimanda al
        # capitolo. Nessun riquadro-indice dentro la pagina.
        if sec.get("title"):
            try:
                pdf.start_section(_section_heading(sec, with_timestamps))
            except Exception:
                pass
        cell(7, _section_heading(sec, with_timestamps))
        pdf.ln(1)
        if sec["text"]:
            pdf.set_font("Doc", "", 11)
            cell(6, sec["text"], md=markdown)
        pdf.ln(3)

    pdf.output(_lp(out_path))


# === TRADUZIONE (Google Translate in cloud · Ollama in locale) ==============
# Riusa una trascrizione GIÀ salvata e ne produce una versione tradotta, senza
# ri-trascrivere (quindi senza spendere crediti di trascrizione). Due motori,
# scelti come per il riassunto: con una chiave Groq si usa Google Translate
# (deep_translator, endpoint gratuito, nessuna API key dedicata); senza chiave,
# in locale, si traduce con Ollama per restare 100% offline.

# Google Translate accetta ~5000 caratteri per richiesta: spezziamo il testo in
# blocchi più piccoli sui confini di frase, per stare comodi sotto il limite.
_TRANSLATE_MAX_CHARS = 4500


def _translate_ollama(text: str, target: str) -> str:
    """Traduce un testo verso 'target' con un modello locale via Ollama (HTTP).

    Usato in modalità locale per restare 100% offline (nessun passaggio da
    Google Translate). temperature=0 per una resa fedele e deterministica."""
    import urllib.request
    lang = _lang_name(target) or target
    system = (
        f"Sei un traduttore professionista. Traduci il testo dell'utente in "
        f"{lang} in modo fedele e naturale. Conserva integralmente il "
        f"significato, i nomi propri, le cifre e la punteggiatura. Mantieni "
        f"INVARIATI, nella loro forma inglese, i termini tecnici e gli "
        f"inglesismi di uso comune (per esempio «fine tuning», «deploy», "
        f"«streaming», «feedback», «machine learning», «commit», «buffer», "
        f"«dataset», «prompt»): non tradurli né adattarli. Non aggiungere e non "
        f"omettere nulla. Rispondi esclusivamente con la traduzione, senza "
        f"preamboli, note, virgolette o commenti.")
    payload = {
        "model": OLLAMA_TRANSLATE_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "stream": False,
        "options": {"temperature": 0.0, "num_ctx": OLLAMA_NUM_CTX},
    }
    req = urllib.request.Request(
        OLLAMA_HOST + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    return (data.get("message", {}).get("content") or "").strip()


def _translate_engine_label(target: str = "it", local: bool = False) -> str:
    """Etichetta del motore di traduzione, mostrata in testa ai file salvati."""
    lang = _lang_name(target) or target
    if local:
        return f"Traduzione automatica (locale · Ollama {OLLAMA_TRANSLATE_MODEL}) → {lang}"
    return f"Traduzione automatica (Google Translate) → {lang}"


# Inglesismi / termini tecnici che devono restare in inglese anche nella
# traduzione italiana. Google Translate non è istruibile via prompt, perciò li
# «proteggiamo» con un segnaposto (NGZ<n>ZQ) prima di tradurre e li ripristiniamo
# dopo: quel formato (maiuscole + cifra) attraversa Google Translate INTATTO
# (verificato), così il termine originale non viene mai tradotto.
_ANGLICISMS = [
    "fine tuning", "fine-tuning", "machine learning", "deep learning",
    "data science", "big data", "cloud computing", "code review",
    "problem solving", "user experience", "smart working", "team building",
    "know-how", "know how", "step by step", "open source", "real time",
    "deploy", "deployment", "devops", "commit", "merge", "rebase", "branch",
    "buffer", "streaming", "stream", "streamer", "download", "upload",
    "feedback", "deadline", "meeting", "brainstorming", "briefing", "budget",
    "business", "dataset", "endpoint", "export", "import", "firmware",
    "framework", "hardware", "software", "hosting", "input", "output", "layout",
    "login", "logout", "marketing", "network", "online", "offline", "overflow",
    "password", "performance", "plugin", "prompt", "query", "rendering",
    "router", "screenshot", "server", "setup", "smartphone", "startup",
    "target", "template", "testing", "thread", "token", "toolkit", "tool",
    "trend", "tuning", "update", "upgrade", "username", "wireless", "workflow",
    "workshop", "backup", "benchmark", "cache", "container", "cookie",
    "debugging", "debug", "encoder", "decoder", "gaming", "hashtag",
    "influencer", "kernel", "latency", "mainstream", "malware", "middleware",
    "patch", "pipeline", "podcast", "proxy", "refactoring", "release",
    "rollback", "scroll", "shader", "sprint", "stack", "string", "throughput",
    "timeout", "trigger", "webcam", "widget", "browser", "frontend", "backend",
    "fullstack", "boilerplate", "changelog", "hotfix", "webinar", "wildcard",
    "ransomware", "spyware", "touchscreen", "playlist",
]
# Regex unica, alternative ordinate dalla più lunga (le locuzioni multi-parola
# devono avere la precedenza sulle singole parole al loro interno).
_ANGLICISM_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(_ANGLICISMS, key=len, reverse=True))
    + r")\b", re.IGNORECASE)
_ANGLICISM_TOKEN_RE = re.compile(r"NGZ\d+ZQ")


def _protect_anglicisms(text: str) -> tuple[str, dict[str, str]]:
    """Sostituisce gli inglesismi con segnaposto NGZ<n>ZQ (che Google preserva).

    Restituisce (testo_con_segnaposto, mappa segnaposto→forma originale)."""
    mapping: dict[str, str] = {}

    def repl(m: "re.Match") -> str:
        token = f"NGZ{len(mapping)}ZQ"
        mapping[token] = m.group(0)   # conserva la forma esatta trovata nel testo
        return token

    return _ANGLICISM_RE.sub(repl, text), mapping


def _restore_anglicisms(text: str, mapping: dict[str, str]) -> str:
    """Ripristina gli inglesismi originali al posto dei segnaposto."""
    for token, original in mapping.items():
        text = text.replace(token, original)
    # Sicurezza: se qualche segnaposto fosse sopravvissuto storpiato, lo togliamo.
    return _ANGLICISM_TOKEN_RE.sub("", text)


def _make_translator(target: str = "it", local: bool = False):
    """Sceglie il motore di traduzione e restituisce una funzione (testo -> testo).

    In modalità locale traduce con Ollama (100% offline); altrimenti usa Google
    Translate (cloud, gratuito, sorgente autorilevata). In entrambi i casi gli
    inglesismi restano in inglese: via prompt con Ollama, via segnaposto con
    Google Translate. Solleva un RuntimeError chiaro se il motore scelto non è
    disponibile (Ollama non raggiungibile o deep_translator non installato)."""
    if local:
        _check_ollama()
        return lambda text: _translate_ollama(text, target)
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        raise RuntimeError("deep_translator non installato. Esegui:  "
                           "pip install deep-translator")
    google = GoogleTranslator(source="auto", target=target).translate

    def translate(text: str) -> str:
        protected, mapping = _protect_anglicisms(text)
        result = google(protected) or ""
        return _restore_anglicisms(result, mapping)

    return translate


def _split_for_translation(text: str) -> list[str]:
    """Spezza 'text' in blocchi <= _TRANSLATE_MAX_CHARS sui confini di frase.

    Se una singola frase supera il limite, viene tagliata a forza per non
    eccedere il massimo accettato da Google Translate."""
    text = (text or "").strip()
    if not text:
        return []
    # Confini di frase mantenendo la punteggiatura (split su spazio dopo .?!).
    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        while len(part) > _TRANSLATE_MAX_CHARS:
            # Frase mostruosa: tagliala in pezzi grezzi.
            chunks.append(part[:_TRANSLATE_MAX_CHARS])
            part = part[_TRANSLATE_MAX_CHARS:]
        if len(buf) + len(part) + 1 > _TRANSLATE_MAX_CHARS:
            if buf:
                chunks.append(buf)
            buf = part
        else:
            buf = f"{buf} {part}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def _translate_text(translate_fn, text: str) -> str:
    """Traduce un testo (anche lungo) unendo i blocchi tradotti.

    'translate_fn' è la funzione restituita da _make_translator (testo -> testo):
    Google Translate (cloud) oppure Ollama (locale)."""
    out = []
    for chunk in _split_for_translation(text):
        try:
            out.append(translate_fn(chunk) or "")
        except Exception:
            # Un blocco fallito non deve far saltare l'intera traduzione:
            # si tiene l'originale come fallback per quel pezzo.
            out.append(chunk)
    return " ".join(s for s in out if s).strip()


def translate_sections(sections: list[dict], target: str = "it",
                       local: bool = False, on_progress=None,
                       done_sections: list[dict] | None = None,
                       on_section=None) -> list[dict]:
    """Traduce titolo e testo di ogni sezione verso 'target' (default italiano).

    Con 'local=True' la traduzione avviene in locale via Ollama (100% offline);
    altrimenti via Google Translate. 'on_progress(i, n)' (opzionale) viene
    chiamato dopo ogni sezione tradotta, per aggiornare una barra/spinner.
    Restituisce nuove sezioni (non muta quelle in ingresso).

    Per il RESUME: 'done_sections' sono le sezioni già tradotte in una precedente
    esecuzione (le prime len(done_sections) di 'sections'), che vengono saltate;
    'on_section(list)' (opzionale) è chiamato dopo OGNI nuova sezione con l'elenco
    completo tradotto finora, per persistere il parziale su disco (così un
    interruzione a metà è riprendibile esattamente da lì)."""
    translate_fn = _make_translator(target, local)
    out: list[dict] = list(done_sections or [])
    start_index = len(out)
    n = len(sections)
    if on_progress and start_index:
        on_progress(start_index, n)  # riflette sulla barra il lavoro già fatto
    for i in range(start_index, n):
        sec = sections[i]
        title = sec.get("title")
        new_title = (_translate_text(translate_fn, title) if title else title)
        new_text = _translate_text(translate_fn, sec.get("text", ""))
        out.append({"start": sec.get("start"), "title": new_title, "text": new_text})
        if on_section:
            on_section(out)
        if on_progress:
            on_progress(i + 1, n)
    return out


# === API KEY ===

def load_dotenv() -> None:
    """Load the variables from a '.env' file next to the script, if present.

    Thin public wrapper around _load_env_file() (the same loader used at import
    time): kept for backward compatibility, since the engine and the GUI call
    tx.load_dotenv() before reading the Groq/DeepL keys. It reads KEY=value lines
    (ignoring comments/blank lines, tolerating an 'export ' prefix), strips any
    surrounding quotes, and sets each variable ONLY if not already defined, so a
    real environment variable always wins over the .env file.

    The .env file must NOT be committed (it is already in .gitignore): keep it
    only locally, it contains your secret keys."""
    _load_env_file()


# Placeholder value of the .env file: it must be treated as "key not entered".
_GROQ_KEY_PLACEHOLDER = "gsk_la-tua-chiave-qui"


def get_groq_client() -> Groq | None:
    """Create (and VALIDATE) the Groq client by reading the API key from
    GROQ_API_KEY (environment variable or .env file). If it is missing, ask the
    user for it.

    The validation makes a small test call (models.list) BEFORE starting the
    work: this way, if the key is missing/wrong or there is a network block, you
    notice immediately, without downloading and splitting the audio in vain.

    NB: keeping the key in an environment variable / .env file is the correct
    practice: it must NEVER be written in the code nor committed to GitHub."""
    load_dotenv()  # populate os.environ from the .env file, if present
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    # The template placeholder is NOT a valid key: treat it as missing.
    if api_key == _GROQ_KEY_PLACEHOLDER:
        console.print("[warning]Nel file .env c'e' ancora il segnaposto, non la tua chiave vera.[/warning]")
        api_key = ""
    if not api_key:
        console.print("[warning]API key Groq non trovata (ne' come variabile d'ambiente ne' in .env).[/warning]")
        console.print("[dim]Opzioni: metti la chiave nel file .env  (GROQ_API_KEY=gsk_...)  "
                      "oppure usa  setx GROQ_API_KEY \"gsk_...\"  (poi riapri il terminale).[/dim]")
        console.print("[dim]La generi su https://console.groq.com/keys[/dim]")
        api_key = console.input("[bold]Incolla la tua API key Groq (o invio per annullare): [/bold]").strip()
    if not api_key:
        console.print("[error]Nessuna API key fornita.[/error]")
        return None

    try:
        client = Groq(api_key=api_key)
    except Exception as e:
        console.print(f"[error]Impossibile inizializzare il client Groq: {e}[/error]")
        return None

    # --- Validation: lightweight test call ---
    try:
        with console.status("[info]Verifico la chiave Groq...[/info]", spinner="dots"):
            client.models.list()
    except Exception as e:
        msg = str(e)
        if "401" in msg or "invalid_api_key" in msg or "Unauthorized" in msg:
            console.print("[error]Chiave Groq non valida (401). Controlla di averla copiata bene da console.groq.com/keys[/error]")
        elif "403" in msg:
            console.print("[error]Accesso negato da Groq (403). Possibili cause: chiave errata, oppure rete/VPN/regione "
                          "bloccata. Prova a disattivare eventuali VPN/proxy.[/error]")
        else:
            console.print(f"[error]Impossibile contattare Groq: {e}[/error]")
        return None

    return client


# === MAIN FLOW ===

def _print_ratelimit_notice(title: str, done_seconds: float, total_seconds: float) -> None:
    """Mostra un avviso elegante (non un errore) quando i crediti Groq finiscono.

    Riporta il MINUTAGGIO a cui la trascrizione si è fermata e ricorda che il
    progresso è salvato: si potrà riprendere quando i crediti tornano."""
    where = _format_timestamp(done_seconds)
    if total_seconds:
        where += f" / {_format_timestamp(total_seconds)}"
    body = Text()
    body.append("I crediti gratuiti Groq per oggi sono esauriti.\n\n", style="bold")
    body.append("La trascrizione si è fermata a ")
    body.append(where, style="bold bright_yellow")
    body.append(" ed è stata salvata automaticamente.\n\n")
    body.append("Quando i crediti torneranno disponibili (di norma domani) riavvia "
                "con lo stesso video e scegli «Riprendi» per continuare da dove si "
                "è interrotto.", style="dim")
    console.print()
    console.print(Panel(body, title="[warning]⏳ Crediti Groq esauriti[/warning]",
                        border_style="yellow", box=ROUNDED, padding=(1, 2),
                        title_align="left"))


# === ANALISI VISIVA: estrazione fotogrammi + lettura con un modello vision ====

def _has_video_stream(path: str) -> bool:
    """True se il file ha una traccia VIDEO (evita l'analisi su mp3/audio puri)."""
    if os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS:
        return True
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type", "-of",
             "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, check=True)
        return "video" in out.stdout
    except Exception:
        return False


def download_video(url: str, workdir: str, on_progress=_noop_progress,
                   should_stop=_never_stop, lang: str = "it") -> str:
    """Scarica il VIDEO (capped a VISION_YT_MAX_HEIGHT) per l'analisi visiva.

    A differenza di download_audio (solo audio), qui serve l'immagine: scarichiamo
    un file muxed a risoluzione contenuta, da cui poi si estraggono SIA i
    fotogrammi SIA l'audio per la trascrizione (un solo download). Versione senza
    interfaccia: restituisce il percorso del video e solleva MediaError su
    errore. Wrapper CLI: `_cli_download_video`."""
    out_template = os.path.join(workdir, "video.%(ext)s")

    def _hook(d: dict) -> None:
        if should_stop():
            raise KeyboardInterrupt
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            on_progress("download", done, total, msg("dl_video", lang))
        elif d["status"] == "finished":
            on_progress("download", None, None, msg("prep_video", lang))

    h = VISION_YT_MAX_HEIGHT
    ydl_opts = {
        # Video+audio muxed con altezza limitata; preferiamo mp4 per compatibilità.
        "format": f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best",
        "merge_output_format": "mp4",
        "outtmpl": out_template,
        "quiet": True, "no_warnings": True, "noprogress": True,
        "progress_hooks": [_hook],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise MediaError(f"Errore nel download video: {e}")
    for fname in os.listdir(workdir):
        if fname.startswith("video."):
            return os.path.join(workdir, fname)
    raise MediaError("File video non trovato dopo il download.")


def _cli_download_video(url: str, workdir: str) -> str | None:
    """download_video per la CLI: barra rich, Ctrl+C e None su errore."""
    progress, _task, on_progress = _download_progress("Scarico video")
    try:
        with progress:
            return download_video(url, workdir, on_progress,
                                  should_stop=lambda: _interrupted)
    except KeyboardInterrupt:
        return None
    except MediaError as e:
        console.print(f"[error]{e}[/error]")
        return None


def _parse_showinfo_times(stderr: str) -> list[float]:
    """Estrae i pts_time (secondi) dalle righe 'showinfo' di ffmpeg, in ordine."""
    times: list[float] = []
    for line in stderr.splitlines():
        idx = line.find("pts_time:")
        if idx == -1:
            continue
        rest = line[idx + len("pts_time:"):].strip()
        token = rest.split()[0] if rest else ""
        try:
            times.append(float(token))
        except ValueError:
            continue
    return times


def _collapse_close_frames(frames: list[tuple[float, str]],
                           min_gap: float) -> list[tuple[float, str]]:
    """Raggruppa i fotogrammi entro 'min_gap' secondi (finestra a partire dal
    primo del gruppo) e tiene l'ULTIMO di ogni gruppo. Serve a eliminare le coppie
    ravvicinate che il rilevamento scene produce sulle transizioni (un frame a
    metà stacco + uno assestato): l'ultimo è di norma quello leggibile/ravvicinato.
    'frames' = [(timestamp, percorso)] ordinati per tempo. Non tocca i file."""
    if min_gap <= 0 or len(frames) < 2:
        return frames
    kept: list[tuple[float, str]] = []
    cluster_start = frames[0][0]
    last = frames[0]
    for t, p in frames[1:]:
        if t - cluster_start <= min_gap:
            last = (t, p)              # stesso gruppo: l'ultimo vince
        else:
            kept.append(last)
            cluster_start = t
            last = (t, p)
    kept.append(last)
    return kept


def extract_keyframes(video_path: str, duration: float, workdir: str) -> list[tuple[float, str]]:
    """Estrae i FOTOGRAMMI CHIAVE di un video, con il loro timestamp (secondi).

    Strategia: rilevamento di CAMBIO SCENA via ffmpeg (cattura un frame quando
    l'immagine cambia davvero: nuova slide, nuovo codice, nuova formula), così di
    natura non si ripetono fotogrammi quasi identici. Se il video è quasi statico
    e le scene rilevate sono troppo poche, ripiega su un campionamento a intervalli
    regolari. Limita il totale a VISION_MAX_FRAMES (campionamento uniforme).
    Restituisce una lista di (timestamp, percorso_jpg) ordinata per tempo."""
    frames_dir = os.path.join(workdir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    # 1) Rilevamento cambio scena.
    pattern = os.path.join(frames_dir, "kf_%05d.jpg")
    vf = (f"select='gt(scene,{VISION_SCENE_THRESHOLD})',"
          f"scale={VISION_FRAME_WIDTH}:-2,showinfo")
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", video_path, "-vf", vf,
             "-vsync", "vfr", "-q:v", "3", pattern],
            capture_output=True, text=True)
        times = _parse_showinfo_times(proc.stderr)
    except Exception as e:
        console.print(f"[warning]Estrazione fotogrammi non riuscita: {e}[/warning]")
        return []
    files = sorted(os.path.join(frames_dir, n) for n in os.listdir(frames_dir)
                   if n.startswith("kf_"))
    frames = list(zip(times, files))  # l'ordine di showinfo coincide con quello dei file
    # Elimina le coppie ravvicinate (doppio scatto sulla stessa transizione): tiene
    # un solo fotogramma per finestra, così non finiscono nel riassunto due frame
    # quasi identici (uno spesso "vuoto") e si risparmiano chiamate al modello.
    frames = _collapse_close_frames(frames, VISION_MIN_GAP)

    # 2) Fallback: video quasi statico o senza stacchi netti -> pochi cambi scena.
    # Campiona a intervalli regolari, con un passo ADATTIVO alla durata così anche
    # i video brevi ricevono comunque alcuni fotogrammi.
    min_expected = max(4, int((duration or 0) // 180))
    if len(frames) < min_expected and (duration or 0) >= 2:
        for f in files:
            try:
                os.remove(f)
            except OSError:
                pass
        # Quanti fotogrammi vogliamo: tra min_expected e il cap, in base a quanti
        # intervalli "standard" entrano nella durata.
        want = max(min_expected,
                   min(VISION_MAX_FRAMES,
                       int((duration or 0) // VISION_FALLBACK_INTERVAL) or min_expected))
        interval = max(1.0, (duration or 0) / want)
        ipattern = os.path.join(frames_dir, "iv_%05d.jpg")
        ivf = f"fps=1/{interval:.3f},scale={VISION_FRAME_WIDTH}:-2"
        try:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-i", video_path, "-vf", ivf,
                 "-vsync", "vfr", "-q:v", "3", ipattern],
                capture_output=True, text=True, check=True)
            ifiles = sorted(os.path.join(frames_dir, n) for n in os.listdir(frames_dir)
                            if n.startswith("iv_"))
            frames = [(float(i) * interval, f) for i, f in enumerate(ifiles)]
        except Exception:
            pass

    # 3) Cap: se sono troppi, campiona uniformemente lungo la timeline.
    if len(frames) > VISION_MAX_FRAMES:
        step = len(frames) / VISION_MAX_FRAMES
        frames = [frames[int(i * step)] for i in range(VISION_MAX_FRAMES)]
    return frames


# Prompt per il modello vision: estrae SOLO il contenuto informativo visibile e
# scarta i fotogrammi "vuoti" (volti, transizioni) rispondendo "NIENTE".
_VISION_SYSTEM_PROMPT = (
    "Analizzi UN fotogramma di un video didattico/divulgativo. Estrai SOLO il "
    "contenuto informativo VISIBILE a schermo che il parlato non può rendere:\n"
    "• CODICE sorgente: trascrivilo ALLA LETTERA (indentazione e simboli inclusi) "
    "dentro un blocco markdown ``` con il nome del linguaggio.\n"
    "• FORMULE matematiche e relativi PASSAGGI/DIMOSTRAZIONI: scrivile in LaTeX "
    "(`$...$` in linea, `$$...$$` per i passaggi), riportando tutti i passaggi "
    "visibili.\n"
    "• GRAFICI, DIAGRAMMI, TABELLE, SCHEMI: descrivili indicando assi, valori, "
    "relazioni e la conclusione che mostrano.\n"
    "• TESTO significativo di slide (titoli, definizioni, elenchi): riportalo.\n"
    "Regole: NON descrivere volti, persone che parlano, sfondi, arredi o elementi "
    "decorativi. Se il fotogramma non contiene NULLA di tecnico/informativo (solo "
    "una persona che parla, una slide di titolo, una transizione), rispondi "
    "ESATTAMENTE con la sola parola: NIENTE. Rispondi in italiano, conciso e ben "
    "strutturato, senza preamboli e SENZA includere il tuo ragionamento: fornisci "
    "solo il risultato finale."
)
_VISION_USER_PROMPT = "Estrai il contenuto tecnico/informativo visibile in questo fotogramma."


def _vision_user_prompt(context: str = "") -> str:
    """Prompt utente per il modello vision. Se 'context' (il parlato attorno a
    questo punto del video) è disponibile, lo antepone: dà al modello il CONTESTO
    di ciò di cui si sta parlando, così interpreta meglio sigle, nomi di variabili,
    simboli e formule ambigue a schermo. Vincolo esplicito: usare il contesto solo
    per INTERPRETARE, mai per inventare — si trascrive solo ciò che è VISIBILE."""
    if not context:
        return _VISION_USER_PROMPT
    return (
        "CONTESTO AUDIO — ciò che l'oratore sta dicendo intorno a questo punto del "
        f"video:\n«{context}»\n\n"
        "Usa questo contesto SOLO per interpretare correttamente ciò che vedi "
        "(sigle, nomi di variabili, simboli, formule, termini ambigui). NON "
        "aggiungere nulla che non sia effettivamente a schermo: trascrivi "
        "esclusivamente il contenuto VISIBILE nel fotogramma.\n\n"
        + _VISION_USER_PROMPT)


def _audio_context_near(segments: list[dict] | None, ts: float,
                        window: float = 25.0, max_chars: int = 700) -> str:
    """Testo trascritto attorno al timestamp 'ts' (± 'window' secondi), da passare
    al modello vision come contesto del fotogramma. Restituisce stringa vuota se
    non ci sono segmenti utili. Troncato a 'max_chars' per non gonfiare i token."""
    if not segments:
        return ""
    lo, hi = ts - window, ts + window
    parts = [(s.get("text") or "").strip() for s in segments
             if s.get("start") is not None and lo <= s["start"] <= hi]
    ctx = " ".join(p for p in parts if p).strip()
    if len(ctx) > max_chars:
        ctx = ctx[:max_chars].rstrip() + "…"
    return ctx


def _strip_think(text: str) -> str:
    """Rimuove il ragionamento <think>…</think> dei modelli "reasoning".

    Molti modelli (es. qwen3) antepongono alla risposta un lungo blocco di
    ragionamento racchiuso in <think>…</think>: va tolto, altrimenti inquina le
    note visive e il riassunto (e gonfia l'input di 5-7×)."""
    import re
    t = re.sub(r"(?is)<think\b.*?</think>", "", text or "")
    # Tag di apertura rimasto senza chiusura (output troncato): tieni ciò che
    # segue una eventuale chiusura, altrimenti scarta il ragionamento incompleto.
    low = t.lower()
    i = low.find("<think")
    if i != -1:
        j = low.find("</think>", i)
        t = t[j + len("</think>"):] if j != -1 else t[:i]
    return re.sub(r"(?is)</?think>", "", t).strip()


def _dedup_visual_notes(notes: list[dict]) -> list[dict]:
    """Scarta le note visive quasi-identiche (stessa slide ripresa più volte),
    tenendo la PRIMA occorrenza. Confronto per similarità di Jaccard sui termini
    significativi: una slide/definizione rimasta a lungo a schermo genera note
    duplicate che, senza questo filtro, farebbero ripetere il riassunto."""
    import re

    def sig(t: str) -> set:
        words = re.findall(r"[a-zà-ù0-9]+", t.lower())
        return {w for w in words if len(w) > 2}

    kept: list[dict] = []
    sigs: list[set] = []
    for n in notes:
        s = sig(n.get("text", ""))
        if not s:
            continue
        if any((len(s & ps) / (len(s | ps) or 1)) > 0.8 for ps in sigs):
            continue
        kept.append(n)
        sigs.append(s)
    return kept


def _fix_mermaid_arrows(text: str) -> str:
    """Corregge la sintassi errata delle frecce Mermaid: '-->|etichetta|>' non è
    valido, va scritto '-->|etichetta|'. I modelli la sbagliano spesso."""
    import re
    return re.sub(r"(-->\s*\|[^|]*\|)>", r"\1", text or "")


def _strip_mermaid_blocks(text: str) -> str:
    """Rimuove i blocchi ```mermaid (rete di sicurezza quando la mappa concettuale
    è disattivata e il modello ne genera comunque una)."""
    import re
    return re.sub(r"```mermaid\b.*?```\s*", "", text or "", flags=re.S).strip()


def _encode_image_b64(path: str) -> str:
    """Legge un'immagine e la codifica in base64 (per le API vision)."""
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _vision_groq(client, b64: str, context: str = "") -> str:
    """Analizza un fotogramma con un modello multimodale di Groq.

    'context' (opzionale): il parlato trascritto attorno a questo fotogramma, per
    aiutare il modello a interpretare ciò che vede (vedi _vision_user_prompt).

    I modelli "reasoning" (es. qwen3) antepongono un blocco <think>…</think>:
    proviamo a disattivarlo a monte (reasoning_effort, per non sprecare token) e
    in ogni caso lo rimuoviamo dall'output con _strip_think."""
    data_url = f"data:image/jpeg;base64,{b64}"
    messages = [
        {"role": "system", "content": _VISION_SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": _vision_user_prompt(context)},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]},
    ]
    try:
        resp = _groq_chat_capture(
            client, GROQ_VISION_MODEL, messages=messages, temperature=0.2,
            reasoning_effort="none")
    except Exception as e:
        if _is_rate_limit(str(e)):
            raise
        # Il modello non accetta 'reasoning_effort': riprova senza il parametro.
        resp = _groq_chat_capture(
            client, GROQ_VISION_MODEL, messages=messages, temperature=0.2)
    return _strip_think(resp.choices[0].message.content or "")


def _vision_ollama(b64: str, context: str = "") -> str:
    """Analizza un fotogramma con un modello vision locale via Ollama (HTTP).

    'context' (opzionale): il parlato attorno al fotogramma, per aiutare il
    modello a interpretare ciò che vede (vedi _vision_user_prompt)."""
    import urllib.request
    payload = {
        "model": OLLAMA_VISION_MODEL,
        "messages": [
            {"role": "system", "content": _VISION_SYSTEM_PROMPT},
            {"role": "user", "content": _vision_user_prompt(context), "images": [b64]},
        ],
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": OLLAMA_NUM_CTX},
    }
    req = urllib.request.Request(
        OLLAMA_HOST + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    return _strip_think(data.get("message", {}).get("content") or "")


def _ollama_installed_models(timeout: float = 3) -> set[str] | None:
    """Nomi dei modelli GIÀ scaricati in Ollama (da /api/tags).

    None se Ollama non è raggiungibile (spento/non installato): chi chiama può
    così distinguere «nessun modello» da «nessuna informazione»."""
    import urllib.request
    try:
        with urllib.request.urlopen(OLLAMA_HOST + "/api/tags", timeout=timeout) as r:
            tags = json.loads(r.read().decode("utf-8"))
        return {m.get("name", "") for m in tags.get("models", [])}
    except Exception:
        return None


def _ollama_has_model(name: str, installed: set[str]) -> bool:
    """True se 'name' risulta scaricato. Con il tag esplicito (qwen2.5vl:3b) il
    confronto è esatto; senza tag (llama3.2-vision) basta lo stesso nome base
    (llama3.2-vision:latest conta)."""
    if ":" in name:
        return name in installed or name + ":latest" in installed
    return any(n.split(":")[0] == name for n in installed)


def _check_ollama_vision() -> None:
    """Verifica Ollama + presenza di un modello vision; spiega come rimediare."""
    installed = _ollama_installed_models(timeout=5)
    if installed is None:
        raise RuntimeError(
            f"Ollama non raggiungibile su {OLLAMA_HOST}. Per l'analisi visiva in "
            "locale installa Ollama (https://ollama.com), avvialo e scarica un "
            f"modello vision, es:  ollama pull {OLLAMA_VISION_MODEL}")
    if not _ollama_has_model(OLLAMA_VISION_MODEL, installed):
        raise RuntimeError(
            f"Modello vision '{OLLAMA_VISION_MODEL}' non presente in Ollama. "
            f"Scaricalo con:  ollama pull {OLLAMA_VISION_MODEL}")


def _make_vision_analyzer(client=None):
    """Sceglie il motore dell'analisi visiva e restituisce (funzione(b64)->testo, etichetta).

    Preferisce Groq se c'è un client (backend cloud), altrimenti Ollama in locale
    (100% offline). RuntimeError se nessuno è utilizzabile (il chiamante può così
    saltare l'analisi senza bloccare il resto)."""
    if client is not None:
        return (lambda b64, ctx="": _vision_groq(client, b64, ctx)), f"Groq · {GROQ_VISION_MODEL}"
    _check_ollama_vision()
    return (lambda b64, ctx="": _vision_ollama(b64, ctx)), f"locale · Ollama {OLLAMA_VISION_MODEL}"


def _is_empty_visual(text: str) -> bool:
    """True se la risposta del modello vision equivale a 'NIENTE' (frame vuoto)."""
    norm = (text or "").upper()
    for ch in "*_.!#>` \n\t-":
        norm = norm.replace(ch, "")
    return norm == "" or norm == "NIENTE"


def analyze_video_visuals(video_path: str, duration: float, workdir: str,
                          client=None, frames_out_dir: str | None = None,
                          on_progress=None, quiet: bool = False,
                          stats: dict | None = None, lang: str = "it",
                          segments: list[dict] | None = None) -> list[dict]:
    """Estrae i fotogrammi chiave del video e li "legge" con un modello vision.

    'segments' (opzionale): la trascrizione audio già pronta. Se presente, per ogni
    fotogramma passa al modello il parlato attorno a quel timestamp come CONTESTO,
    così legge meglio ciò che vede (sigle, variabili, formule ambigue). Vedi
    _vision_user_prompt / _audio_context_near.

    Restituisce una lista di NOTE VISIVE {'start': sec, 'text': str, 'image': str},
    una per fotogramma con informazione (i "vuoti" — volti, transizioni — vengono
    scartati). Se 'frames_out_dir' è dato, COPIA lì il fotogramma di ogni nota
    tenuta (il workdir temporaneo verrà cancellato) e ne salva il nome in 'image'.

    Doppia modalità di output, così è riusabile sia dalla CLI sia dal motore/GUI:
    con 'on_progress(phase,cur,total,detail)' riporta tramite callback (niente
    console rich); senza, usa la console rich (CLI). 'quiet' silenzia comunque la
    console. Lista vuota se non c'è nulla o se il motore vision non è disponibile.

    'stats' (opzionale): dict che la funzione riempie con l'esito, così il
    chiamante (engine/GUI) può spiegare PERCHÉ non ci sono note invece di
    lasciare tutto in silenzio. Chiavi: 'frames', 'notes', 'errors',
    'rate_limited' (bool), 'last_error', 'unavailable'."""
    use_rich = on_progress is None and not quiet

    def _stat(key, value):
        if stats is not None:
            stats[key] = value

    _stat("frames", 0)
    _stat("notes", 0)
    _stat("errors", 0)
    _stat("rate_limited", False)
    _stat("last_error", None)

    def _report(cur, total, detail):
        if on_progress:
            on_progress("visual", cur, total, detail)

    try:
        analyze_fn, label = _make_vision_analyzer(client)
    except RuntimeError as e:
        if use_rich:
            console.print(f"[warning]Analisi visiva non disponibile: {e}[/warning]")
        _report(None, None, msg("vis_unavail", lang, e=e))
        _stat("unavailable", str(e))
        return []

    _report(None, None, msg("vis_detect", lang))
    if use_rich:
        with console.status("[info]Individuo i fotogrammi chiave (cambi scena)...[/info]", spinner="dots"):
            frames = extract_keyframes(video_path, duration, workdir)
    else:
        frames = extract_keyframes(video_path, duration, workdir)
    _stat("frames", len(frames))
    if not frames:
        if use_rich:
            console.print("[warning]Nessun fotogramma significativo individuato.[/warning]")
        _report(None, None, msg("vis_noframes", lang))
        return []
    if use_rich:
        console.print(f"  {SYM_OK} [info]{len(frames)}[/info] fotogrammi da analizzare ({label})")
    _report(0, len(frames), msg("vis_toanalyze", lang, n=len(frames), label=label))

    notes: list[dict] = []

    def _process(update) -> None:
        errors = 0
        for i, (ts, path) in enumerate(frames, 1):
            if _interrupted:
                break
            try:
                text = analyze_fn(_encode_image_b64(path),
                                  _audio_context_near(segments, ts))
            except Exception as e:
                if _is_rate_limit(str(e)):
                    if use_rich:
                        console.print("[warning]Crediti Groq esauriti durante l'analisi visiva: "
                                      "proseguo con i fotogrammi già letti.[/warning]")
                    _report(i, len(frames), msg("vis_ratelimit", lang))
                    _stat("rate_limited", True)
                    _stat("last_error", str(e))
                    break
                # Errore NON di credito sul singolo fotogramma: lo saltiamo, ma lo
                # registriamo così il chiamante non resta al buio se falliscono tutti.
                errors += 1
                _stat("errors", errors)
                _stat("last_error", str(e))
                text = ""
            if text and not _is_empty_visual(text):
                notes.append({"start": float(ts), "text": text.strip(), "_frame": path})
            update(i)

    if use_rich:
        progress = Progress(
            SpinnerColumn("dots", style="bright_yellow"),
            TextColumn("[phase]{task.description}"),
            BarColumn(bar_width=40, style="bar.back", complete_style="bright_yellow", finished_style="bold yellow"),
            TaskProgressColumn(), console=console, expand=False,
        )
        with progress:
            task_id = progress.add_task("Analizzo i fotogrammi", total=len(frames))
            _process(lambda i: progress.update(task_id, completed=i))
    else:
        _process(lambda i: _report(i, len(frames), msg("vis_analyzing", lang, i=i, n=len(frames))))

    raw = len(notes)
    notes = _dedup_visual_notes(notes)  # scarta slide ripetute (stesso contenuto a schermo)
    _stat("notes", len(notes))
    # Conserva i fotogrammi delle note TENUTE: il workdir temporaneo verrà
    # cancellato, quindi li copiamo nella cartella definitiva e ne salviamo il nome.
    # Solo se c'è davvero qualcosa da salvare: niente cartella 'frames' vuota.
    if frames_out_dir and notes:
        try:
            os.makedirs(_lp(frames_out_dir), exist_ok=True)
            for idx, note in enumerate(notes):
                src = note.get("_frame")
                if src and os.path.isfile(src):
                    name = f"frame_{idx:03d}_{int(note['start'])}s.jpg"
                    shutil.copyfile(src, _lp(os.path.join(frames_out_dir, name)))
                    note["image"] = name
        except OSError:
            pass
    for note in notes:
        note.pop("_frame", None)
    if use_rich:
        dropped = f" ([dim]{raw - len(notes)} duplicati scartati[/dim])" if raw != len(notes) else ""
        console.print(f"  {SYM_OK} Contenuti visivi estratti: [info]{len(notes)}[/info] su {len(frames)} fotogrammi{dropped}")
    _report(len(frames), len(frames), msg("vis_extracted", lang, k=len(notes), n=len(frames)))
    return notes


def save_visual_notes(out_root: str, meta: dict, notes: list[dict],
                      engine_label: str, do_export: bool, ui_lang: str = "it",
                      quiet: bool = False) -> None:
    """Salva le NOTE VISIVE in results/<title>/analisi_visiva/.

    Produce: il .json, un .md leggibile e — se l'export è attivo — un PDF "ricco"
    in cui OGNI nota mostra il suo FOTOGRAMMA accanto al contenuto estratto
    (codice/formula/grafico), così il frame fa da prova/riferimento visivo.
    'quiet' silenzia la console (per il motore/GUI, che riporta a modo suo)."""
    if not notes:
        return
    safe = _safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe)
    vdir = os.path.join(video_dir, visual_subdir(ui_lang))
    frames_dir = os.path.join(vdir, "frames")
    os.makedirs(_lp(vdir), exist_ok=True)
    base = os.path.join(vdir, f"{safe}_visivo")
    payload = {
        "title": meta["title"],
        "engine": engine_label,
        "count": len(notes),
        "notes": [{"start": n["start"],
                   "timestamp": _format_timestamp(n["start"]),
                   "image": n.get("image"),
                   "text": n["text"]} for n in notes],
    }
    with open(_lp(base + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Markdown del documento: fotogramma (se presente) + testo, per ogni nota.
    # 'img_prefix' permette link RELATIVI per il .md (portabile) e ASSOLUTI per il
    # PDF (il browser headless deve trovare i file).
    def _companion_md(img_prefix: str, saved_in: str | None = None) -> str:
        saved_line = [f"- **Salvato in:** {saved_in}"] if saved_in else []
        out = [f"# {meta['title']} — Analisi visiva", "",
               f"- **Estratto con:** {engine_label}",
               f"- **Fotogrammi con contenuto:** {len(notes)}",
               *saved_line, "", "---", ""]
        for n in notes:
            out.append(f"## [{_format_timestamp(n['start'])}]")
            out.append("")
            if n.get("image"):
                out.append(f"![fotogramma {_format_timestamp(n['start'])}]({img_prefix}{n['image']})")
                out.append("")
            out.append(n["text"])
            out.append("")
        return "\n".join(out)

    with open(_lp(base + ".md"), "w", encoding="utf-8") as f:
        f.write(_companion_md("frames/"))
    if not quiet:
        console.print(f"  {SYM_OK} Analisi visiva salvata in [info]{visual_subdir(ui_lang)}/[/info]")

    # PDF "ricco": fotogramma + testo estratto, uno per nota (immagini con percorso
    # ASSOLUTO). Solo se l'export è attivo e ci sono davvero dei fotogrammi salvati.
    if do_export and RICH_PDF and any(n.get("image") for n in notes):
        pdf_saved_in = os.path.abspath(vdir)
        try:
            if quiet:
                build_pdf_rich(_companion_md(frames_dir + os.sep, saved_in=pdf_saved_in), base + ".pdf")
            else:
                with console.status("[info]Creo il PDF dell'analisi visiva (fotogrammi + testo)...[/info]", spinner="dots"):
                    ok = build_pdf_rich(_companion_md(frames_dir + os.sep, saved_in=pdf_saved_in), base + ".pdf")
                if ok:
                    console.print(f"  {SYM_OK} PDF analisi visiva con i fotogrammi creato.")
        except Exception:
            pass


def load_visual_notes(out_root: str, title: str) -> list[dict]:
    """Rilegge le note visive salvate (per arricchire il riassunto). [] se assenti."""
    safe = _safe_filename(title)
    for sub in VISUAL_SUBDIRS.values():
        p = os.path.join(out_root, safe, sub, f"{safe}_visivo.json")
        if os.path.isfile(_lp(p)):
            try:
                with open(_lp(p), "r", encoding="utf-8") as f:
                    d = json.load(f)
                # Pulizia difensiva anche in lettura: toglie eventuale ragionamento
                # <think> e le note duplicate (così il riassunto resta pulito anche
                # rigenerandolo da note salvate da versioni precedenti).
                cleaned = []
                for n in d.get("notes", []):
                    txt = _strip_think(n.get("text", ""))
                    if txt and not _is_empty_visual(txt):
                        cleaned.append({"start": float(n.get("start") or 0), "text": txt,
                                        "image": n.get("image")})
                return _dedup_visual_notes(cleaned)
            except Exception:
                return []
    return []


def _split_md_blocks(text: str) -> list[str]:
    """Spezza il testo in blocchi separati da riga vuota, MA tiene interi i
    recinti di codice ``` ``` (che possono contenere righe vuote): così un
    fotogramma non finisce mai in mezzo a un blocco di codice."""
    blocks: list[str] = []
    cur: list[str] = []
    in_fence = False
    for ln in text.split("\n"):
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            cur.append(ln)
            continue
        if not ln.strip() and not in_fence:
            if cur:
                blocks.append("\n".join(cur))
                cur = []
        else:
            cur.append(ln)
    if cur:
        blocks.append("\n".join(cur))
    return [b for b in blocks if b.strip()]


def _append_frames_to_sections(sections: list[dict], notes: list[dict], img_path_fn) -> list[dict]:
    """INTERLACCIA i FOTOGRAMMI nel testo di ogni sezione, inserendoli TRA i
    paragrafi in base al loro timestamp (posizione relativa nella finestra
    temporale della sezione), invece di accodarli tutti in fondo. Così le
    immagini seguono il discorso e non formano un «muro» a fine sezione.
    'img_path_fn(nome_immagine) -> percorso' consente link relativi (per il .md,
    portabile) o assoluti (per il PDF). Non muta gli input."""
    notes = sorted([n for n in notes if n.get("image")], key=lambda n: n["start"])
    if not notes:
        return sections
    out = [dict(s) for s in sections]
    bounds: list[tuple[float, float]] = []
    if any(s.get("start") is not None for s in out):
        for i, s in enumerate(out):
            st = s.get("start") or 0
            nxt = out[i + 1].get("start") if i + 1 < len(out) else None
            bounds.append((st, nxt if nxt is not None else float("inf")))
        buckets: list[list[dict]] = [[] for _ in out]
        for note in notes:
            placed = False
            for i, (st, en) in enumerate(bounds):
                if st <= note["start"] < en:
                    buckets[i].append(note)
                    placed = True
                    break
            if not placed:
                buckets[-1].append(note)
    else:
        bounds = [(0.0, float("inf"))] + [(0.0, float("inf")) for _ in out[1:]]
        buckets = [list(notes)] + [[] for _ in out[1:]]

    def _img_md(n: dict) -> str:
        return f"![Fotogramma {_format_timestamp(n['start'])}]({img_path_fn(n['image'])})"

    for i, s in enumerate(out):
        bucket = buckets[i]
        if not bucket:
            continue
        text = (s.get("text") or "").rstrip()
        paras = _split_md_blocks(text)
        if not paras:  # sezione senza testo: accoda le immagini
            s["text"] = "\n\n".join(_img_md(n) for n in bucket)
            continue
        st, en = bounds[i]
        span = (en - st) if (en != float("inf") and en > st) else None
        # Per ogni paragrafo, i fotogrammi da inserire SUBITO DOPO di esso.
        after: list[list[dict]] = [[] for _ in paras]
        n_para = len(paras)
        for j, note in enumerate(bucket):
            if span:
                frac = (note["start"] - st) / span
            else:  # senza timestamp affidabili: distribuzione uniforme
                frac = (j + 0.5) / len(bucket)
            frac = min(1.0, max(0.0, frac))
            idx = min(n_para - 1, int(frac * n_para))
            after[idx].append(note)
        pieces: list[str] = []
        for k, p in enumerate(paras):
            pieces.append(p)
            pieces.extend(_img_md(n) for n in after[k])
        s["text"] = "\n\n".join(pieces)
    return out


def _merge_visual_into_sections(sections: list[dict], notes: list[dict]) -> list[dict]:
    """Inserisce le note visive nel testo delle sezioni in base al timestamp.

    Ogni nota finisce nella sezione il cui intervallo [start, start_successiva)
    contiene il suo timestamp; se le sezioni non hanno start (testo continuo) le
    note vanno in coda in ordine. Diventano annotazioni «[A SCHERMO — mm:ss] …»
    così il modello del riassunto le vede insieme al parlato. Non muta gli input."""
    if not notes:
        return sections
    notes = sorted(notes, key=lambda n: n["start"])
    out = [dict(s) for s in sections]

    def _annotate(items: list[dict]) -> str:
        return "\n\n".join(
            f"[A SCHERMO — {_format_timestamp(n['start'])}]\n{n['text']}" for n in items)

    if any(s.get("start") is not None for s in out):
        bounds = []
        for i, s in enumerate(out):
            st = s.get("start") or 0
            nxt = out[i + 1].get("start") if i + 1 < len(out) else None
            en = nxt if nxt is not None else float("inf")
            bounds.append((st, en))
        buckets: list[list[dict]] = [[] for _ in out]
        for note in notes:
            placed = False
            for i, (st, en) in enumerate(bounds):
                if st <= note["start"] < en:
                    buckets[i].append(note)
                    placed = True
                    break
            if not placed:
                buckets[-1].append(note)
        for i, s in enumerate(out):
            if buckets[i]:
                s["text"] = (s.get("text", "").strip() + "\n\n" + _annotate(buckets[i])).strip()
    else:
        out[0]["text"] = (out[0].get("text", "").strip() + "\n\n" + _annotate(notes)).strip()
    return out


def _run_pipeline(meta: dict, source: tuple[str, str], backend: str,
                  client, local_model: str | None,
                  resume_cp: dict | None = None,
                  want_visual: bool = False,
                  out_root: str | None = None) -> tuple[list[dict], list[dict]] | None:
    """Acquire the audio for ONE source and transcribe it.

    'source' is ('youtube', url) or ('local', filepath). For a local file there
    is no download phase. Con backend Groq supporta la RIPRESA da 'resume_cp'; se
    il limite Groq viene raggiunto, salva un checkpoint e restituisce None (così
    il chiamante non salva una trascrizione incompleta). Returns the segments, or
    None on interruption / failure."""
    kind, ref = source
    # L'analisi visiva ha senso solo su sorgenti con traccia video (YouTube o
    # file video locali; un mp3 non ha fotogrammi).
    do_visual = bool(want_visual) and (kind == "youtube" or _has_video_stream(ref))

    # Build the phase labels dynamically so "Fase x/y" is always correct.
    phase_names = []
    if kind == "youtube":
        phase_names.append("download")
    if backend == "groq":
        phase_names.append("prepare")
    phase_names.append("transcribe")
    if do_visual:
        phase_names.append("visual")
    n = len(phase_names)
    step = {name: i + 1 for i, name in enumerate(phase_names)}

    # ignore_cleanup_errors: evita il PermissionError (WinError 32) su Windows se
    # l'audio temporaneo resta bloccato un istante da ffmpeg/whisper alla chiusura.
    with tempfile.TemporaryDirectory(prefix="echoscript_", ignore_cleanup_errors=True) as workdir:
        # --- Acquire the audio (e, se richiesta l'analisi visiva, il video) ---
        media_path = None  # file VIDEO da cui estrarre i fotogrammi (analisi visiva)
        if kind == "youtube":
            console.print()
            dl_label = "Download video" if do_visual else "Download audio"
            console.rule(f"[phase]⬇ Fase {step['download']}/{n} — {dl_label}[/phase]", style="bright_blue")
            if do_visual:
                # Un solo download: dal video estraiamo SIA i fotogrammi SIA l'audio.
                media_path = _cli_download_video(ref, workdir)
                if media_path:
                    audio_path = media_path
                else:
                    console.print("[warning]Download del video non riuscito: proseguo con il "
                                  "solo audio (analisi visiva disattivata).[/warning]")
                    do_visual = False
                    audio_path = _cli_download_audio(ref, workdir)
            else:
                audio_path = _cli_download_audio(ref, workdir)
            if not audio_path or _interrupted:
                console.print("[warning]Download non completato.[/warning]")
                return None
        else:
            # Local file: feed it directly (ffmpeg/whisper read it in place).
            audio_path = ref
            if do_visual:
                media_path = ref

        # Duration: from metadata if present, otherwise probe the file with ffprobe.
        duration = meta["duration"] or _probe_duration(audio_path)
        meta["duration"] = duration  # keep it consistent for the output builders

        # --- Transcription ---
        if backend == "groq":
            console.print()
            console.rule(f"[phase]✂ Fase {step['prepare']}/{n} — Preparazione audio[/phase]", style="bright_blue")
            chunks = _cli_split_audio(audio_path, duration, workdir)
            console.print(f"  {SYM_OK} Audio diviso in [info]{len(chunks)}[/info] blocchi da ~{CHUNK_SECONDS // 60} min")

            console.print()
            console.rule(f"[phase]✎ Fase {step['transcribe']}/{n} — Trascrizione · Groq (cloud)[/phase]", style="bright_green")
            # Ripresa: se il checkpoint combacia (stessi blocchi), riparti.
            start_index, prior, prior_lang = 0, None, None
            if resume_cp and resume_cp.get("total_chunks") == len(chunks):
                start_index = int(resume_cp.get("done_chunks", 0))
                prior = resume_cp.get("segments")
                prior_lang = resume_cp.get("detected_language")
            try:
                segments, detected = transcribe(client, chunks, start_index, prior, prior_lang)
            except TranscriptionInterrupted as ti:
                save_checkpoint(meta, {
                    "title": meta["title"], "id": meta.get("id"),
                    "source": meta.get("source", kind),
                    "source_path": meta.get("source_path"),
                    "webpage_url": meta.get("webpage_url"),
                    "model": GROQ_MODEL, "chunk_seconds": CHUNK_SECONDS,
                    "total_chunks": ti.total, "done_chunks": ti.done,
                    "detected_language": ti.lang, "segments": ti.segments,
                    "duration": duration,
                })
                # Minutaggio raggiunto: i blocchi sono uniformi (CHUNK_SECONDS).
                done_s = ti.done * CHUNK_SECONDS
                if duration:
                    done_s = min(done_s, duration)
                _print_ratelimit_notice(meta["title"], done_s, duration)
                # Si può completare SUBITO la parte mancante in locale (CPU/GPU),
                # riusando l'audio già scaricato (nessun nuovo download).
                ans = _prompt("Completo ora la parte mancante in locale?",
                              "(s = sì, in locale · invio = riprendo più tardi)",
                              accent="bright_cyan").strip().lower()
                if not ans.startswith("s"):
                    return None
                cont_model = local_model or choose_local_model()
                if not cont_model:
                    return None
                # Checkpoint "locale" sintetico dal parziale Groq: stesso modello e
                # durata, così la ripresa locale riparte dal minuto già raggiunto.
                local_cp = {"model": cont_model, "done_seconds": done_s,
                            "duration": duration, "detected_language": ti.lang,
                            "segments": ti.segments}
                dev, _ = _resolve_device()
                dev_label = "GPU" if dev == "cuda" else "CPU"
                console.print()
                console.rule(f"[phase]✎ Completamento in locale {dev_label} ({cont_model})[/phase]",
                             style="bright_green")
                if dev != "cuda":
                    console.print("  [warning]La trascrizione locale gira sulla CPU: può richiedere diversi minuti.[/warning]")
                segments, detected = _cli_transcribe_local(cont_model, audio_path, duration,
                                                           meta=meta, resume_cp=local_cp,
                                                           workdir=workdir)
                # Header dei file: motore combinato Groq + locale.
                meta["engine_label_override"] = f"Groq + Locale / faster-whisper {cont_model}"
            delete_checkpoint(meta)
        else:
            dev, _ = _resolve_device()
            dev_label = "GPU" if dev == "cuda" else "CPU"
            console.print()
            console.rule(f"[phase]✎ Fase {step['transcribe']}/{n} — Trascrizione · Locale {dev_label} ({local_model})[/phase]",
                         style="bright_green")
            if dev != "cuda":
                console.print("  [warning]La trascrizione locale gira sulla CPU: può richiedere diversi minuti.[/warning]")
            segments, detected = _cli_transcribe_local(local_model, audio_path, duration,
                                                       meta=meta, resume_cp=resume_cp,
                                                       workdir=workdir)

        # Lingua dell'audio rilevata da Whisper (per la card di riepilogo).
        meta["detected_language"] = detected

        # --- Analisi visiva (opzionale): "leggi" i fotogrammi del video ---
        # Va fatta ORA, finché il file video esiste (per YouTube è nella cartella
        # temporanea, cancellata all'uscita dal blocco `with`).
        visual_notes: list[dict] = []
        if do_visual and media_path and not _interrupted:
            console.print()
            console.rule(f"[phase]👁 Fase {step['visual']}/{n} — Analisi visiva (cosa si VEDE)[/phase]",
                         style="bright_yellow")
            # Cartella DEFINITIVA dei fotogrammi (li copiamo qui prima che il
            # workdir temporaneo venga cancellato), così il documento li mostra.
            frames_out_dir = None
            if out_root:
                frames_out_dir = os.path.join(out_root, _safe_filename(meta["title"]),
                                              visual_subdir(), "frames")
            visual_notes = analyze_video_visuals(media_path, duration, workdir, client,
                                                 frames_out_dir=frames_out_dir,
                                                 segments=segments)

    # (Here the temporary folder has already been deleted: the data we need
    #  — segments and visual notes — is already in memory.)
    if not segments:
        return None
    return segments, visual_notes


def _save_outputs(meta: dict, segments: list[dict], engine_label: str,
                  do_export: bool, out_root: str) -> None:
    """Write all outputs for ONE transcription, then print the summary panel.

    Layout: out_root/<title>/trascrizioni/ (md, txt, json, + pdf if exporting).
    The export choice is passed in (asked once, up front) so the same flag
    applies to every file in a batch."""
    # --- Saving: tidy folder structure ---
    #   results/<title>/
    #       trascrizioni/  -> md, txt, json (+ pdf if exported)
    safe_title = _safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe_title)
    trans_dir = os.path.join(video_dir, trans_subdir())
    os.makedirs(_lp(trans_dir), exist_ok=True)
    base_orig = os.path.join(trans_dir, safe_title)  # base path (without extension) of the originals

    # Common basis (sections) used by all text formats and by the export.
    sections = _build_sections(meta, segments)
    created: list[str] = []  # paths (relative to the video folder) of generated files, for the summary

    def _save(path: str, content: str) -> None:
        with open(_lp(path), "w", encoding="utf-8") as f:
            f.write(content)
        created.append(os.path.relpath(path, video_dir).replace("\\", "/"))

    _save(f"{base_orig}.md", build_md(meta["title"], meta, engine_label, sections, with_timestamps=True))
    _save(f"{base_orig}.txt", build_txt(meta["title"], meta, sections))
    _save(f"{base_orig}.json", build_transcript_json(meta, segments, engine_label))

    # --- Export for reading: PDF (optional) ---
    if do_export:
        console.print()
        console.rule("[phase]📄 Esportazione PDF[/phase]", style="bright_blue")
        with console.status("[info]Creo il PDF...[/info]", spinner="dots"):
            ok = _save_pdf(meta, sections, f"{base_orig}.pdf", with_timestamps=True,
                           engine_label=engine_label)
        if ok:
            created.append(os.path.relpath(f"{base_orig}.pdf", video_dir).replace("\\", "/"))

    # --- Summary ---
    n_words = sum(len(s["text"].split()) for s in segments)
    stats = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    stats.add_column("Icona", justify="center", no_wrap=True)
    stats.add_column("Label", style="dim", no_wrap=True)
    stats.add_column("Value")
    stats.add_row("🎙 ", "Motore", f"[info]{engine_label}[/info]")
    audio_lang = _lang_name(meta.get("detected_language"))
    if audio_lang:
        stats.add_row("🗣 ", "Lingua audio", f"[bold]{audio_lang}[/bold]")
    stats.add_row("🧩", "Segmenti", f"[bold]{len(segments)}[/bold]")
    stats.add_row("📝", "Parole", f"[bold]~{n_words}[/bold]")
    stats.add_row("📑", "Sezioni", f"[bold]{len(meta['chapters']) or 'testo continuo'}[/bold]")

    # Tree of generated files, grouped by subfolder (trascrizioni/traduzioni).
    groups: dict[str, list[str]] = {}
    for rel in created:
        folder, _, fname = rel.partition("/")
        groups.setdefault(folder, []).append(os.path.splitext(fname)[1] or fname)
    files_tbl = Table(show_header=False, box=None, padding=(0, 2), expand=False)
    files_tbl.add_column("Folder", style="bold bright_white", no_wrap=True)
    files_tbl.add_column("Files", style="info")
    for folder, exts in groups.items():
        icon = "📂" if folder in TRANS_SUBDIRS.values() else "🌐"
        files_tbl.add_row(f"{icon} {folder}/", "  ".join(exts))

    body = Group(
        stats,
        Text(""),
        Text.from_markup(f"[dim]📁 {video_dir}[/dim]"),
        files_tbl,
    )
    console.print()
    console.print(Panel(
        body, title="[bold bright_green]✅ Completato![/bold bright_green]",
        border_style="bright_green", box=DOUBLE, expand=False, padding=(1, 3),
    ))


def translate_existing(out_root: str, title: str, target: str = "it",
                       do_export: bool = True, ui_lang: str = "it",
                       local: bool = False):
    """Traduce una trascrizione GIÀ salvata (niente ri-trascrizione, nessun credito).

    Rilegge i file da out_root/<title>/, traduce le sezioni verso 'target'
    (default italiano) con Google Translate — o in locale via Ollama se
    'local=True' — e salva md/txt (+ pdf) sotto
    out_root/<title>/<traduzioni>/ col suffisso della lingua. Il nome della
    cartella segue la lingua dell'interfaccia ('ui_lang': it -> "traduzioni",
    en -> "translations"). Restituisce la LISTA delle sezioni tradotte (così il
    riassunto può riusarle senza ricaricarle), oppure None se non c'era nulla da
    tradurre o la traduzione è fallita."""
    existing = load_existing_transcript(out_root, title)
    if not existing:
        console.print("[warning]Nessuna trascrizione salvata da tradurre.[/warning]")
        return None
    meta, segments, _ = existing
    sections = _build_sections(meta, segments)

    # Resume: se una precedente traduzione si era interrotta a metà, ricarica le
    # sezioni già tradotte dallo stato e riparti da lì (a patto che la lingua di
    # destinazione coincida). 'on_section' salva il parziale dopo ogni sezione.
    _state = load_state(meta)
    _tr_stage = (_state or {}).get("stages", {}).get("translation", {})
    done_secs = stage_sections(_state, "translation")
    if _tr_stage.get("target") and _tr_stage.get("target") != target:
        done_secs = []  # target cambiato: il parziale non è riutilizzabile
    if len(done_secs) > len(sections):
        done_secs = done_secs[:len(sections)]

    def _persist_translation(done_list):
        update_stage(meta, "translation", status=STAGE_PARTIAL,
                     done=len(done_list), total=len(sections),
                     sections=done_list, extra={"target": target})

    safe_title = _safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe_title)
    trad_dir = os.path.join(video_dir, transl_subdir(ui_lang))
    os.makedirs(_lp(trad_dir), exist_ok=True)
    base = os.path.join(trad_dir, f"{safe_title}_{target}")
    lang_label = _lang_name(target) or target

    # Traduzione con barra di avanzamento (una tacca per sezione).
    console.print()
    console.rule(f"[phase]🌐 Traduzione → {lang_label}[/phase]", style="bright_blue")
    if done_secs:
        console.print(f"  [dim]↻ Riprendo la traduzione dalla sezione "
                      f"{len(done_secs) + 1}/{len(sections)}.[/dim]")
    progress = Progress(
        SpinnerColumn("dots", style="bright_blue"),
        TextColumn("[phase]{task.description}"),
        BarColumn(bar_width=40, style="bar.back", complete_style="bright_blue", finished_style="bold blue"),
        TaskProgressColumn(), console=console, expand=False,
    )
    try:
        with progress:
            task_id = progress.add_task("Traduco le sezioni", total=len(sections))
            translated = translate_sections(
                sections, target, local=local,
                on_progress=lambda i, n: progress.update(task_id, completed=i),
                done_sections=done_secs, on_section=_persist_translation)
    except RuntimeError as e:  # deep_translator mancante o Ollama non raggiungibile
        console.print(f"[error]{e}[/error]")
        return None
    except Exception as e:
        # Il parziale è già stato salvato da 'on_section': si potrà riprendere.
        if _is_rate_limit(str(e)):
            console.print("[warning]Limite raggiunto: traduzione parziale salvata, "
                          "potrai riprendere.[/warning]")
        else:
            console.print(f"[error]Traduzione fallita: {e}[/error]")
        return None

    engine_label = _translate_engine_label(target, local)
    created: list[str] = []

    def _save(path: str, content: str) -> None:
        with open(_lp(path), "w", encoding="utf-8") as f:
            f.write(content)
        created.append(os.path.relpath(path, video_dir).replace("\\", "/"))

    # La versione tradotta non porta i timestamp (testo continuo, più leggibile).
    _save(f"{base}.md", build_md(meta["title"], meta, engine_label, translated, with_timestamps=False))
    _save(f"{base}.txt", build_txt(meta["title"], meta, translated))
    # JSON delle SEZIONI tradotte: serve a «Solo riassunto» per riassumere la
    # traduzione (non l'originale) anche in una sessione successiva.
    _save(f"{base}.json",
          json.dumps({"target": target, "sections": translated}, ensure_ascii=False, indent=2))
    # Traduzione conclusa e salvata: segna la fase come completata nello stato.
    update_stage(meta, "translation", status=STAGE_DONE, done=len(translated),
                 total=len(sections), sections=translated, extra={"target": target})
    if do_export:
        with console.status("[info]Creo il PDF (traduzione)...[/info]", spinner="dots"):
            ok = _save_pdf(meta, translated, f"{base}.pdf", with_timestamps=False,
                           engine_label=engine_label)
        if ok:
            created.append(os.path.relpath(f"{base}.pdf", video_dir).replace("\\", "/"))

    files = "  ".join(os.path.splitext(c.split('/')[-1])[1] for c in created)
    console.print()
    console.print(Panel(
        Group(
            Text.from_markup(f"[bold]Lingua:[/bold] {lang_label}"),
            Text.from_markup(f"[dim]📁 {trad_dir}[/dim]"),
            Text.from_markup(f"[info]🌐 {os.path.basename(trad_dir)}/[/info]  {files}"),
        ),
        title="[bold bright_blue]✅ Traduzione completata![/bold bright_blue]",
        border_style="bright_blue", box=DOUBLE, expand=False, padding=(1, 3),
    ))
    return translated


# === RIASSUNTO (via LLM: Groq cloud o Ollama locale) =========================
# Dal testo italiano (la traduzione, oppure la trascrizione se l'audio era già
# italiano) produce un riassunto PER SEZIONE: pulisce intercalari, ripetizioni e
# autocorrezioni e tiene i concetti. Groq usa un modello di chat; in locale ci si
# appoggia a Ollama (nessuna dipendenza pip aggiuntiva: si parla via HTTP).

# Istruzioni date al modello: sono il cuore della qualità del riassunto.
_SUMMARY_SYSTEM_PROMPT = (
    "Sei un editor professionista specializzato nella rielaborazione di "
    "contenuti parlati. Ricevi la trascrizione di una sezione di un video "
    "(testo in italiano) e la trasformi in un riassunto fedele, dettagliato e "
    "scorrevole, redatto interamente in italiano secondo le regole seguenti.\n"
    "Pulizia del testo: elimina intercalari, riempitivi ed esitazioni (ehm, "
    "uhm, cioè, tipo, no?, allora, insomma) e rimuovi ripetizioni, frasi "
    "interrotte e autocorrezioni di chi parla, conservando soltanto la versione "
    "corretta e definitiva di ciascun passaggio.\n"
    "Fedeltà ai contenuti: conserva integralmente tutti i concetti, i dati, i "
    "nomi propri, le cifre e gli esempi rilevanti. Non aggiungere informazioni "
    "assenti nel testo, non inventare e non introdurre interpretazioni o "
    "commenti personali.\n"
    "Inglesismi e termini tecnici: mantieni in inglese i termini tecnici e gli "
    "inglesismi ormai di uso comune in italiano (per esempio «fine tuning», "
    "«deploy», «streaming», «feedback», «machine learning», «commit», «buffer», "
    "«dataset», «prompt»). NON tradurli né italianizzarli: scrivili nella forma "
    "inglese corrente, esattamente come li userebbe chi lavora nel settore.\n"
    "Errori di trascrizione: il testo proviene da una trascrizione AUTOMATICA del "
    "parlato e può contenere sviste (parole storpiate, omofoni sbagliati, "
    "spaziature o concordanze errate, un termine tecnico reso male). Quando dal "
    "contesto riconosci con ragionevole certezza un evidente errore di "
    "trascrizione, correggilo in silenzio ripristinando la parola o l'espressione "
    "corretta; se invece il dubbio è genuino, conserva il testo originale senza "
    "inventare. Non segnalare, non elencare e non commentare le correzioni.\n"
    "Stile e struttura: redigi il riassunto in prosa continua e articolata, "
    "privilegiando un testo discorsivo che ricostruisca con ricchezza il filo "
    "del discorso e ne approfondisca i passaggi anziché comprimerli. Punta a un "
    "riassunto esteso e particolareggiato, non a una sintesi telegrafica. "
    "Per facilitare la lettura, evidenzia in grassetto Markdown (**testo**) "
    "soltanto le parole o le brevissime locuzioni chiave — concetti centrali, "
    "termini tecnici, nomi propri e cifre rilevanti — usando il grassetto con "
    "parsimonia e mai su intere frasi (deve risaltare, non saturare il testo). "
    "Ricorri agli elenchi puntati solo quando indispensabili (ad esempio per "
    "enumerazioni di voci eterogenee presenti nell'originale) e mai come "
    "struttura predefinita. Mantieni un registro professionale, chiaro e coeso, "
    "con transizioni fluide tra i concetti.\n"
    "Vincoli di output: rispondi esclusivamente con il riassunto, senza "
    "preamboli, intestazioni o commenti. Non aprire mai il testo con formule "
    "del tipo \"Ecco i punti chiave\", \"In questo video si parla di\" o simili: "
    "entra direttamente nel contenuto."
)

# Estensione del prompt usata quando il testo contiene anche le note dell'ANALISI
# VISIVA: istruisce il modello a integrare codice, formule e diagrammi visti a
# schermo e ad aggiungere una mappa concettuale quando il contenuto è visuale.
_SUMMARY_VISUAL_BASE = (
    "\nIl testo può contenere annotazioni nel formato «[A SCHERMO — mm:ss] …» che "
    "riportano ciò che era VISIBILE nel video in quel momento (codice, formule, "
    "grafici, diagrammi, slide). Trattale come fonte attendibile quanto il parlato "
    "e INTEGRALE nel riassunto in modo naturale, secondo queste regole aggiuntive:\n"
    "• riporta il CODICE in blocchi markdown delimitati da ``` con il linguaggio "
    "indicato, preservandolo fedelmente;\n"
    "• scrivi le FORMULE e le relative dimostrazioni in LaTeX (`$...$` in linea, "
    "`$$...$$` per i passaggi), includendo tutti i passaggi mostrati;\n"
    "• descrivi GRAFICI, DIAGRAMMI e TABELLE riportandone dati, assi, relazioni e "
    "la conclusione.\n"
    "Importante: se la stessa slide, definizione o diagramma compare in più "
    "annotazioni (perché restava a schermo a lungo), trattalo UNA volta sola e non "
    "ripetere paragrafi o concetti già esposti. Non limitarti a citare le "
    "annotazioni: fondile nel discorso come parte integrante della spiegazione."
)
# Variante CON mappa concettuale (attivabile via ECHOSCRIPT_CONCEPT_MAP=1).
_SUMMARY_VISUAL_MAP = (
    "\nSe (e solo se) il contenuto è prevalentemente concettuale o animato, "
    "aggiungi UNA SOLA mappa concettuale complessiva alla fine, in un blocco "
    "```mermaid con sintassi `graph TD` e archi nel formato corretto "
    "`A -->|etichetta| B` (MAI `A -->|etichetta|> B`); non ripetere lo stesso "
    "diagramma più volte."
)
# Variante SENZA mappa (default): vietiamo esplicitamente i diagrammi mermaid.
_SUMMARY_VISUAL_NOMAP = (
    "\nNON generare mappe concettuali, diagrammi né blocchi ```mermaid: limitati a "
    "prosa, elenchi essenziali, codice e formule."
)
_SUMMARY_SYSTEM_PROMPT_VISUAL = _SUMMARY_SYSTEM_PROMPT + _SUMMARY_VISUAL_BASE + _SUMMARY_VISUAL_NOMAP
_SUMMARY_SYSTEM_PROMPT_VISUAL_MAP = _SUMMARY_SYSTEM_PROMPT + _SUMMARY_VISUAL_BASE + _SUMMARY_VISUAL_MAP

# --- Versione INGLESE dei prompt (usata quando l'interfaccia è in inglese) ----
# Un utente con la UI in inglese si aspetta gli output nella sua lingua: il
# riassunto viene quindi prodotto in inglese, con le stesse regole redazionali.
_SUMMARY_SYSTEM_PROMPT_EN = (
    "You are a professional editor specialized in reworking spoken content. You "
    "receive the transcription of a section of a video and turn it into a "
    "faithful, detailed and fluent summary, written entirely in English "
    "according to the following rules.\n"
    "Text cleanup: remove fillers, hesitations and discourse markers (uh, um, you "
    "know, like, I mean, so, well) and remove repetitions, interrupted sentences "
    "and the speaker's self-corrections, keeping only the correct, final version "
    "of each passage.\n"
    "Fidelity to content: preserve in full all concepts, data, proper names, "
    "figures and relevant examples. Do not add information not present in the "
    "text, do not invent, and do not introduce personal interpretations or "
    "comments.\n"
    "Technical terms: keep technical terms, code identifiers, product names and "
    "established jargon exactly as they appear; do not alter their spelling.\n"
    "Transcription errors: the text comes from an AUTOMATIC transcription of "
    "speech and may contain mistakes (garbled words, wrong homophones, spacing or "
    "agreement errors, a mishandled technical term). When the context lets you "
    "recognize with reasonable certainty an obvious transcription error, fix it "
    "silently by restoring the correct word or expression; if the doubt is "
    "genuine, keep the original text without inventing. Do not flag, list or "
    "comment on corrections.\n"
    "Style and structure: write the summary in continuous, articulated prose, "
    "favoring a discursive text that reconstructs the thread of the discourse "
    "richly and deepens its passages rather than compressing them. Aim for an "
    "extended, detailed summary, not a telegraphic synthesis. To aid reading, use "
    "Markdown bold (**text**) only on key words or very short key phrases — "
    "central concepts, technical terms, proper names and relevant figures — using "
    "bold sparingly and never on whole sentences (it must stand out, not saturate "
    "the text). Resort to bullet lists only when indispensable (for example for "
    "enumerations of heterogeneous items present in the original) and never as a "
    "default structure. Keep a professional, clear and cohesive register, with "
    "smooth transitions between concepts.\n"
    "Output constraints: reply exclusively with the summary, without preambles, "
    "headings or comments. Never open the text with phrases like \"Here are the "
    "key points\", \"In this video we talk about\" or similar: get straight into "
    "the content."
)
_SUMMARY_VISUAL_BASE_EN = (
    "\nThe text may contain annotations in the format «[ON SCREEN — mm:ss] …» that "
    "report what was VISIBLE in the video at that moment (code, formulas, charts, "
    "diagrams, slides). Treat them as a source as reliable as the speech and "
    "INTEGRATE them into the summary naturally, following these additional rules:\n"
    "• render CODE in markdown blocks delimited by ``` with the language "
    "indicated, preserving it faithfully;\n"
    "• write FORMULAS and their derivations in LaTeX (`$...$` inline, `$$...$$` "
    "for steps), including all the steps shown;\n"
    "• describe CHARTS, DIAGRAMS and TABLES reporting their data, axes, "
    "relationships and conclusion.\n"
    "Important: if the same slide, definition or diagram appears in multiple "
    "annotations (because it stayed on screen for a while), treat it ONCE only and "
    "do not repeat paragraphs or concepts already covered. Do not merely cite the "
    "annotations: blend them into the discourse as an integral part of the "
    "explanation."
)
_SUMMARY_VISUAL_MAP_EN = (
    "\nIf (and only if) the content is mostly conceptual or animated, add ONE "
    "SINGLE overall concept map at the end, in a ```mermaid block with `graph TD` "
    "syntax and edges in the correct format `A -->|label| B` (NEVER "
    "`A -->|label|> B`); do not repeat the same diagram multiple times."
)
_SUMMARY_VISUAL_NOMAP_EN = (
    "\nDo NOT generate concept maps, diagrams or ```mermaid blocks: stick to "
    "prose, essential lists, code and formulas."
)
_SUMMARY_SYSTEM_PROMPT_VISUAL_EN = _SUMMARY_SYSTEM_PROMPT_EN + _SUMMARY_VISUAL_BASE_EN + _SUMMARY_VISUAL_NOMAP_EN
_SUMMARY_SYSTEM_PROMPT_VISUAL_MAP_EN = _SUMMARY_SYSTEM_PROMPT_EN + _SUMMARY_VISUAL_BASE_EN + _SUMMARY_VISUAL_MAP_EN

# Lingua del riassunto prodotto: segue la lingua dell'interfaccia (la CLI è
# italiano-only, quindi resta "it"). Impostata dai punti d'ingresso del riassunto.
_SUMMARY_LANG = "it"
# Override temporaneo del prompt di sistema del riassunto (impostato da
# summarize_existing quando ci sono note visive da integrare). None = prompt base.
_SUMMARY_PROMPT_OVERRIDE = None


def _summary_base_prompt(lang: str | None = None) -> str:
    """Prompt base del riassunto nella lingua richiesta (default: _SUMMARY_LANG)."""
    lang = lang or globals().get("_SUMMARY_LANG", "it")
    return _SUMMARY_SYSTEM_PROMPT_EN if lang == "en" else _SUMMARY_SYSTEM_PROMPT


def _summary_visual_prompt(lang: str, concept_map: bool) -> str:
    """Prompt «visivo» del riassunto (con/senza mappa) nella lingua richiesta."""
    if lang == "en":
        return _SUMMARY_SYSTEM_PROMPT_VISUAL_MAP_EN if concept_map else _SUMMARY_SYSTEM_PROMPT_VISUAL_EN
    return _SUMMARY_SYSTEM_PROMPT_VISUAL_MAP if concept_map else _SUMMARY_SYSTEM_PROMPT_VISUAL


def _active_summary_prompt() -> str:
    """Prompt di sistema del riassunto attualmente attivo (base o «visivo»),
    nella lingua corrente (_SUMMARY_LANG)."""
    return globals().get("_SUMMARY_PROMPT_OVERRIDE") or _summary_base_prompt()


# === PDF "RICCO": HTML (MathJax + Mermaid) stampato da un browser headless =====

PDF_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pdfassets")
# Librerie JS scaricate UNA volta in cache locale (poi funziona anche offline).
_PDF_ASSET_URLS = {
    "tex-svg.js": "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js",
    "mermaid.min.js": "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js",
}

_PDF_HTML_TEMPLATE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<style>
  /* margine di pagina a ZERO: così il browser headless NON disegna il proprio
     header/footer (data in alto, percorso file in basso a sinistra, numero di
     pagina in basso a destra). I margini di stampa reali, UGUALI su ogni pagina,
     li ottiene la tabella .pagewrap qui sotto: thead/tfoot vengono ripetuti e
     RISERVANO spazio in alto e in basso su tutte le pagine. */
  @page { margin: 0; }
  body { font-family: 'Segoe UI', Calibri, Arial, sans-serif; color: #1b1b1b;
         line-height: 1.55; font-size: 12pt; margin: 0; }
  table.pagewrap { width: 100%; border-collapse: collapse; }
  table.pagewrap > thead > tr > td,
  table.pagewrap > tfoot > tr > td { height: 1.5cm; border: none; }
  table.pagewrap > tbody > tr > td { padding: 0 1.7cm; border: none;
         vertical-align: top; }
  h1 { color: #0b6b3a; font-size: 20pt; margin: 0 0 4px; }
  h2 { color: #0b6b3a; font-size: 15pt; margin: 22px 0 8px;
       border-bottom: 2px solid #d8efe2; padding-bottom: 3px; }
  h3 { color: #128a4b; font-size: 13pt; margin: 16px 0 6px; }
  strong { color: #0b3b22; }
  p { margin: 0 0 10px; text-align: justify; }
  ul { margin: 0 0 10px; padding-left: 22px; }
  hr { border: none; border-top: 1px solid #e2e2e2; margin: 14px 0; }
  code { font-family: Consolas, 'Courier New', monospace; font-size: 10.5pt;
         background: #f3f4f6; padding: 1px 4px; border-radius: 4px; }
  pre { background: #f6f8fa; border: 1px solid #e6e8eb; border-radius: 8px;
        padding: 12px 14px; overflow-x: auto; }
  pre code { background: none; padding: 0; }
  .mermaid { background: #fbfdfc; border: 1px solid #eef3f0; border-radius: 8px;
             padding: 12px; text-align: center; margin: 0 0 12px; }
  img { max-width: 100%; max-height: 15cm; display: block; margin: 8px 0 12px;
        border: 1px solid #e3e7e4; border-radius: 8px; }
</style>
<script>window.MathJax = {tex: {inlineMath: [['$','$'], ['\\\\(','\\\\)']],
    displayMath: [['$$','$$'], ['\\\\[','\\\\]']]},
  svg: {fontCache: 'global'}};</script>
<script src="__MATHJAX__"></script>
<script src="__MERMAID__"></script>
<script>window.addEventListener('load', function () {
  if (window.mermaid) { try { mermaid.initialize({startOnLoad: true, theme: 'neutral'}); } catch (e) {} }
});</script>
</head><body>
<table class="pagewrap"><thead><tr><td></td></tr></thead>
<tfoot><tr><td></td></tr></tfoot>
<tbody><tr><td>
__BODY__
</td></tr></tbody></table>
</body></html>
"""


def _md_inline_to_html(text: str) -> str:
    """Converte il markup inline di una riga: escape HTML + grassetto **…**."""
    import re
    import html as _html
    text = _html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _md_to_html(md: str) -> str:
    """Converte il markdown del riassunto in HTML per il PDF "ricco".

    Gestisce: titoli, grassetto, elenchi, righello, blocchi di codice e mermaid,
    e lascia INTATTE le formule `$…$`/`$$…$$` (le renderizza MathJax). I blocchi
    di codice/formule vengono "messi da parte" per non essere alterati dall'escape
    o dalla formattazione."""
    import re
    import html as _html
    store: dict[str, str] = {}
    block_keys: set[str] = set()  # placeholder che sono elementi di blocco (pre/mermaid)

    def _stash(content: str, block: bool = False) -> str:
        key = f"\x00{len(store)}\x00"
        store[key] = content
        if block:
            block_keys.add(key)
        return key

    # 1) Blocchi recintati ``` ``` (incl. ```mermaid). Il contenuto va escapato:
    # il browser lo de-escapa nel textContent, quindi mermaid riceve i caratteri
    # giusti (es. le frecce -->), ma l'HTML resta valido.
    def _fence(m):
        lang = (m.group(1) or "").strip().lower()
        body = _html.escape(m.group(2))
        if lang == "mermaid":
            return _stash(f'<pre class="mermaid">{body}</pre>', block=True)
        return _stash(f"<pre><code>{body}</code></pre>", block=True)

    md = re.sub(r"```([^\n]*)\n(.*?)```", _fence, md, flags=re.S)

    # 1b) Immagini ![alt](src): elemento di blocco. I percorsi locali diventano
    # file:// così il browser headless li carica.
    def _img(m):
        import pathlib
        alt = _html.escape(m.group(1))
        src = m.group(2).strip()
        if "://" not in src:
            try:
                src = pathlib.Path(src).as_uri()
            except Exception:
                pass
        return _stash(f'<img alt="{alt}" src="{src}">', block=True)

    md = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _img, md)
    # 2) Formule: lasciate grezze (MathJax le legge dal testo), ma messe da parte
    # così l'escape non tocca eventuali < > al loro interno e un'eventuale riga
    # vuota interna non spezzi il blocco display in due <p>. Si accettano ENTRAMBI
    # gli stili di delimitatori: $$…$$ / $…$ e \[…\] / \(…\) (il modello usa l'uno
    # o l'altro indistintamente). I display (\[…\], $$…$$) vanno stashati PRIMA
    # degli inline per non spezzarli.
    md = re.sub(r"\$\$(.+?)\$\$", lambda m: _stash(f"$${m.group(1)}$$"), md, flags=re.S)
    md = re.sub(r"\\\[(.+?)\\\]", lambda m: _stash(f"\\[{m.group(1)}\\]"), md, flags=re.S)
    md = re.sub(r"\\\((.+?)\\\)", lambda m: _stash(f"\\({m.group(1)}\\)"), md, flags=re.S)
    md = re.sub(r"\$(.+?)\$", lambda m: _stash(f"${m.group(1)}$"), md)
    # 3) Codice inline `…`
    md = re.sub(r"`([^`]+)`", lambda m: _stash(f"<code>{_html.escape(m.group(1))}</code>"), md)

    # 4) Struttura a blocchi, riga per riga. Gli heading (# / ## / ###) diventano
    # h1/h2/h3: da questi il browser genera i SEGNALIBRI/outline del PDF (il
    # «Sommario» cliccabile nel pannello laterale del lettore), grazie al flag
    # --generate-pdf-document-outline usato in build_pdf_rich.
    out: list[str] = []
    para: list[str] = []
    in_list = False

    def _flush_para():
        if para:
            out.append("<p>" + _md_inline_to_html(" ".join(para)) + "</p>")
            para.clear()

    def _close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in md.split("\n"):
        s = line.strip()
        if not s:
            _flush_para(); _close_list(); continue
        if s in block_keys:  # blocco codice/mermaid: elemento a sé, niente <p>
            _flush_para(); _close_list(); out.append(s); continue
        if s.startswith("### "):
            _flush_para(); _close_list(); out.append("<h3>" + _md_inline_to_html(s[4:]) + "</h3>")
        elif s.startswith("## "):
            _flush_para(); _close_list(); out.append("<h2>" + _md_inline_to_html(s[3:]) + "</h2>")
        elif s.startswith("# "):
            _flush_para(); _close_list(); out.append("<h1>" + _md_inline_to_html(s[2:]) + "</h1>")
        elif s in ("---", "***", "___"):
            _flush_para(); _close_list(); out.append("<hr>")
        elif s.startswith("- ") or s.startswith("* "):
            _flush_para()
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append("<li>" + _md_inline_to_html(s[2:]) + "</li>")
        else:
            _close_list(); para.append(s)
    _flush_para(); _close_list()

    body = "\n".join(out)
    # 5) Ripristina i blocchi messi da parte (codice/mermaid/formule).
    for key, content in store.items():
        body = body.replace(key, content)
    return body


def _ensure_pdf_assets():
    """Restituisce (path_mathjax, path_mermaid), scaricandoli in cache se mancano.

    None se non è possibile procurarseli (niente rete e niente cache)."""
    import urllib.request
    try:
        os.makedirs(PDF_ASSETS_DIR, exist_ok=True)
    except OSError:
        return None
    paths = {}
    for name, url in _PDF_ASSET_URLS.items():
        p = os.path.join(PDF_ASSETS_DIR, name)
        if not (os.path.isfile(p) and os.path.getsize(p) > 10000):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    data = r.read()
                with open(p, "wb") as f:
                    f.write(data)
            except Exception:
                return None
        paths[name] = p
    return paths["tex-svg.js"], paths["mermaid.min.js"]


def _find_browser() -> str | None:
    """Trova un browser Chromium (Edge/Chrome) per la stampa PDF. None se assente."""
    candidates: list[str] = []
    if BROWSER_PATH:
        candidates.append(BROWSER_PATH)
    for name in ("msedge", "chrome", "chromium", "chromium-browser", "brave"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    bases = [os.environ.get("ProgramFiles", r"C:\Program Files"),
             os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
             os.environ.get("LocalAppData", "")]
    for base in bases:
        if not base:
            continue
        candidates.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
        candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def build_pdf_rich(md_text: str, out_path: str) -> bool:
    """Genera un PDF con formule (MathJax) e mappe (Mermaid) DISEGNATE.

    Converte il markdown in HTML e lo stampa con un browser Chromium headless già
    presente sul sistema. Restituisce True se il PDF è stato creato, False se non
    è possibile (nessun browser/asset): in tal caso il chiamante ripiega su fpdf2."""
    import pathlib
    browser = _find_browser()
    if not browser:
        return False
    assets = _ensure_pdf_assets()
    if not assets:
        return False
    mathjax, mermaid = assets
    html_doc = (_PDF_HTML_TEMPLATE
                .replace("__MATHJAX__", pathlib.Path(mathjax).as_uri())
                .replace("__MERMAID__", pathlib.Path(mermaid).as_uri())
                .replace("__BODY__", _md_to_html(md_text)))
    with tempfile.TemporaryDirectory(prefix="echoscript_pdf_", ignore_cleanup_errors=True) as td:
        html_path = os.path.join(td, "doc.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_doc)
        # Chrome NON gestisce i percorsi lunghi (>260) né il prefisso \\?\: stampa
        # su un file temporaneo dal nome corto e poi lo copiamo nella destinazione
        # definitiva (che può essere lunga) tramite _lp().
        tmp_pdf = os.path.join(td, "out.pdf")
        cmd = [
            browser, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--no-first-run", "--no-default-browser-check", "--disable-extensions",
            # virtual-time-budget: lascia a MathJax/Mermaid il tempo di disegnare
            # prima di stampare (altrimenti il PDF esce a metà rendering).
            "--virtual-time-budget=20000", "--run-all-compositor-stages-before-draw",
            # Genera i SEGNALIBRI/outline del PDF dai titoli (h1/h2/h3): è il
            # «Sommario» cliccabile nel pannello laterale del lettore PDF, che
            # rimanda a ogni capitolo. Flag ignorato dai browser troppo vecchi
            # (nessun errore: in tal caso il PDF esce semplicemente senza outline).
            "--generate-pdf-document-outline",
            f"--print-to-pdf={tmp_pdf}", pathlib.Path(html_path).as_uri(),
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=120)
        except Exception:
            return False
        if not (os.path.isfile(tmp_pdf) and os.path.getsize(tmp_pdf) > 1500):
            return False
        try:
            shutil.copyfile(tmp_pdf, _lp(out_path))
        except OSError:
            return False
    return os.path.isfile(_lp(out_path)) and os.path.getsize(_lp(out_path)) > 1500


def _save_pdf(meta: dict, sections: list[dict], out_path: str, with_timestamps: bool,
              engine_label: str = "", markdown: bool = False) -> bool:
    """Esporta un PDF: prima quello "ricco" (formule/mappe disegnate via browser
    headless), poi ripiega su fpdf2. NON usa Groq — lavora su testo già prodotto,
    quindi NESSUN credito speso. Restituisce True se il PDF è stato creato."""
    # «Salvato in:»: la cartella di output, ricavata dal percorso del PDF. Compare
    # tra i metadati in testa al documento (non più in fondo a ogni pagina).
    saved_in = os.path.dirname(os.path.abspath(out_path))
    if RICH_PDF:
        try:
            md_text = build_md(meta["title"], meta, engine_label, sections,
                               with_timestamps=with_timestamps, saved_in=saved_in)
            if build_pdf_rich(md_text, out_path):
                return True
        except Exception:
            pass
    try:
        build_pdf(meta["title"], meta, sections, out_path,
                  with_timestamps=with_timestamps, markdown=markdown,
                  engine_label=engine_label, saved_in=saved_in)
        return True
    except Exception as e:
        console.print(f"[error]Export PDF fallito: {e}[/error]")
        return False


def _summary_user_prompt(text: str, section_title: str | None) -> str:
    """Messaggio utente per il modello: titolo della sezione (se c'è) + testo."""
    head = f"Titolo della sezione: «{section_title}».\n\n" if section_title else ""
    return f"{head}Testo da riassumere:\n\n{text}"


def _groq_chat_capture(client, model: str, **kwargs):
    """client.chat.completions.create che, quando possibile, registra i crediti
    residui del modello dagli header x-ratelimit-* (per il pulsante "crediti"),
    SENZA costo aggiuntivo. Se la variante raw fallisce per motivi diversi da
    credito/auth, ripiega sulla chiamata normale. Restituisce l'oggetto risposta
    già parsato, come la create() classica."""
    try:
        raw = client.chat.completions.with_raw_response.create(model=model, **kwargs)
    except Exception as e:
        msg = str(e)
        if _is_rate_limit(msg) or "401" in msg or "403" in msg:
            raise
        return client.chat.completions.create(model=model, **kwargs)
    try:
        record_rate_limits(model, raw.headers)
    except Exception:
        pass
    return raw.parse()


def _summarize_groq(client, text: str, section_title: str | None) -> str:
    """Riassume un testo con un modello di CHAT di Groq (non Whisper)."""
    resp = _groq_chat_capture(
        client, GROQ_SUMMARY_MODEL,
        messages=[
            {"role": "system", "content": _active_summary_prompt()},
            {"role": "user", "content": _summary_user_prompt(text, section_title)},
        ],
        temperature=0.3,
    )
    return (resp.choices[0].message.content or "").strip()


def _check_ollama() -> None:
    """Verifica che Ollama sia raggiungibile; altrimenti spiega come installarlo."""
    import urllib.request
    try:
        with urllib.request.urlopen(OLLAMA_HOST + "/api/tags", timeout=5) as r:
            r.read()
    except Exception:
        raise RuntimeError(
            f"Ollama non raggiungibile su {OLLAMA_HOST}. Per il riassunto in locale "
            "installa Ollama (https://ollama.com), avvialo e scarica un modello, "
            f"es:  ollama pull {OLLAMA_MODEL}")


def _summarize_ollama(text: str, section_title: str | None) -> str:
    """Riassume un testo con un modello locale via Ollama (HTTP, niente pip)."""
    import urllib.request
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _active_summary_prompt()},
            {"role": "user", "content": _summary_user_prompt(text, section_title)},
        ],
        "stream": False,
        # num_ctx alza la finestra di contesto (default Ollama: solo 2048 token,
        # che troncherebbe i blocchi lunghi). Senza, i video lunghi perderebbero
        # gran parte del testo nel riassunto.
        "options": {"temperature": 0.3, "num_ctx": OLLAMA_NUM_CTX},
    }
    req = urllib.request.Request(
        OLLAMA_HOST + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    return (data.get("message", {}).get("content") or "").strip()


def _make_summarizer(client=None):
    """Sceglie il motore del riassunto e restituisce (funzione, etichetta).

    Preferisce Groq se è disponibile un client (backend cloud); altrimenti usa
    Ollama in locale (100% offline). Solleva RuntimeError se nessuno è utilizzabile."""
    if client is not None:
        label = f"Riassunto automatico (Groq · {GROQ_SUMMARY_MODEL})"
        return (lambda text, title: _summarize_groq(client, text, title)), label
    _check_ollama()
    label = f"Riassunto automatico (locale · Ollama {OLLAMA_MODEL})"
    return (lambda text, title: _summarize_ollama(text, title)), label


def _summarize_long(summarize_fn, text: str, section_title: str | None) -> str:
    """Riassume un testo anche lungo: se supera SUMMARY_MAX_CHARS lo divide in
    blocchi, li riassume singolarmente e poi unisce i parziali (map-reduce)."""
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= SUMMARY_MAX_CHARS:
        return summarize_fn(text, section_title)
    # Map: riassumi a blocchi (riuso lo splitter della traduzione, con cap ampio).
    saved = globals().get("_TRANSLATE_MAX_CHARS")
    globals()["_TRANSLATE_MAX_CHARS"] = SUMMARY_MAX_CHARS
    try:
        blocks = _split_for_translation(text)
    finally:
        globals()["_TRANSLATE_MAX_CHARS"] = saved
    partials = [summarize_fn(b, section_title) for b in blocks]
    merged = "\n\n".join(p for p in partials if p)
    # Reduce: ricompatta i parziali in un unico riassunto coerente.
    return summarize_fn(merged, section_title)


def summarize_sections(sections: list[dict], summarize_fn,
                       on_progress=None, done_sections: list[dict] | None = None,
                       on_section=None) -> list[dict]:
    """Riassume ogni sezione (titolo invariato, testo -> riassunto).

    'on_progress(i, n)' (opzionale) è chiamato dopo ogni sezione. Restituisce
    nuove sezioni senza mutare quelle in ingresso.

    Per il RESUME: 'done_sections' sono le sezioni già riassunte in precedenza
    (saltate); 'on_section(list)' è chiamato dopo OGNI nuova sezione con l'elenco
    completo finora, per salvare il parziale — così se i crediti Groq finiscono a
    metà riassunto si riprende esattamente dalla sezione ferma, senza rispendere
    crediti su quelle già fatte."""
    out: list[dict] = list(done_sections or [])
    start_index = len(out)
    n = len(sections)
    if on_progress and start_index:
        on_progress(start_index, n)
    for i in range(start_index, n):
        sec = sections[i]
        summary = _summarize_long(summarize_fn, sec.get("text", ""), sec.get("title"))
        out.append({"start": sec.get("start"), "title": sec.get("title"), "text": summary})
        if on_section:
            on_section(out)
        if on_progress:
            on_progress(i + 1, n)
    return out


def summarize_existing(out_root: str, title: str, client=None,
                       source_sections: list[dict] | None = None,
                       do_export: bool = True, ui_lang: str = "it") -> bool:
    """Crea un RIASSUNTO del testo italiano di un video già trascritto.

    Riassume 'source_sections' se passate (di norma la TRADUZIONE appena
    prodotta); altrimenti ricostruisce le sezioni dalla trascrizione salvata
    (caso: audio già in italiano). Salva md/txt (+ pdf) sotto
    out_root/<title>/<riassunti>/ col nome cartella in base alla lingua UI.
    Usa Groq se 'client' è disponibile, altrimenti Ollama in locale.
    Restituisce True se il riassunto è stato prodotto, False altrimenti."""
    existing = load_existing_transcript(out_root, title)
    if not existing:
        console.print("[warning]Nessuna trascrizione salvata da riassumere.[/warning]")
        return False
    meta, segments, _ = existing
    # Quale testo riassumere:
    #  - se il chiamante passa già le sezioni (di norma la traduzione appena
    #    prodotta), usa quelle;
    #  - altrimenti («Solo riassunto») riusa la TRADUZIONE salvata se esiste,
    #    così il riassunto è del testo italiano; in mancanza, l'originale.
    if source_sections is not None:
        sections = source_sections
    else:
        sections = load_existing_translation(out_root, title) or _build_sections(meta, segments)
    if not sections:
        return False

    # Arricchimento visivo: se esistono note visive salvate (analisi dei
    # fotogrammi), le fondiamo nelle sezioni per timestamp e attiveremo il prompt
    # «visivo» (codice/formule/grafici/mappa concettuale nel riassunto).
    visual_notes = load_visual_notes(out_root, title)
    if visual_notes:
        sections = _merge_visual_into_sections(sections, visual_notes)
        console.print(f"  [dim]👁  Riassunto arricchito con {len(visual_notes)} contenuti visivi a schermo.[/dim]")

    # Resume: riprendi il riassunto dalle sezioni già fatte in una precedente
    # esecuzione (es. crediti Groq esauriti a metà). 'on_section' salva il
    # parziale dopo OGNI sezione, così non si rispendono crediti sul già fatto.
    _state = load_state(meta)
    done_secs = stage_sections(_state, "summary")
    _sum_stage = (_state or {}).get("stages", {}).get("summary", {})
    if _sum_stage.get("lang") and _sum_stage.get("lang") != (ui_lang or "it"):
        done_secs = []  # lingua del riassunto cambiata: non riusare il parziale
    if len(done_secs) > len(sections):
        done_secs = done_secs[:len(sections)]

    def _persist_summary(done_list):
        update_stage(meta, "summary", status=STAGE_PARTIAL,
                     done=len(done_list), total=len(sections), sections=done_list,
                     extra={"lang": ui_lang or "it"})

    try:
        summarize_fn, engine_label = _make_summarizer(client)
    except RuntimeError as e:
        console.print(f"[warning]Riassunto non disponibile: {e}[/warning]")
        return False

    safe_title = _safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe_title)
    sum_dir = os.path.join(video_dir, summary_subdir(ui_lang))
    os.makedirs(_lp(sum_dir), exist_ok=True)
    suffix = SUMMARY_SUFFIX.get(ui_lang or "it", SUMMARY_SUFFIX["it"])
    base = os.path.join(sum_dir, f"{safe_title}_{suffix}")

    console.print()
    console.rule("[phase]🧠 Riassunto[/phase]", style="bright_magenta")
    progress = Progress(
        SpinnerColumn("dots", style="bright_magenta"),
        TextColumn("[phase]{task.description}"),
        BarColumn(bar_width=40, style="bar.back", complete_style="bright_magenta", finished_style="bold magenta"),
        TaskProgressColumn(), console=console, expand=False,
    )
    # Lingua del riassunto = lingua dell'interfaccia (la CLI passa "it"). Attiva il
    # prompt «visivo» solo durante questo riassunto (reset nel finally), nella
    # lingua giusta e con/senza mappa concettuale a seconda di CONCEPT_MAP.
    globals()["_SUMMARY_LANG"] = ui_lang or "it"
    globals()["_SUMMARY_PROMPT_OVERRIDE"] = (
        _summary_visual_prompt(ui_lang or "it", CONCEPT_MAP) if visual_notes else None)
    if done_secs:
        console.print(f"  [dim]↻ Riprendo il riassunto dalla sezione "
                      f"{len(done_secs) + 1}/{len(sections)}.[/dim]")
    try:
        with progress:
            task_id = progress.add_task("Riassumo le sezioni", total=len(sections))
            summarized = summarize_sections(
                sections, summarize_fn,
                on_progress=lambda i, n: progress.update(task_id, completed=i),
                done_sections=done_secs, on_section=_persist_summary)
    except Exception as e:
        # Il parziale è già salvato da 'on_section': lo stato resta 'partial' e il
        # riassunto potrà riprendere da lì (anche in locale con Ollama).
        if _is_rate_limit(str(e)):
            console.print("[warning]Crediti Groq esauriti: riassunto interrotto e "
                          "salvato come parziale — potrai riprendere (anche in "
                          "locale).[/warning]")
        else:
            console.print(f"[error]Riassunto fallito: {e}[/error]")
        return False
    finally:
        globals()["_SUMMARY_PROMPT_OVERRIDE"] = None
        globals()["_SUMMARY_LANG"] = "it"

    # Pulizia diagrammi: corregge le frecce Mermaid e, se la mappa concettuale è
    # disattivata, rimuove eventuali blocchi mermaid sfuggiti al modello.
    for sec in summarized:
        txt = _fix_mermaid_arrows(sec.get("text", ""))
        if not CONCEPT_MAP:
            txt = _strip_mermaid_blocks(txt)
        sec["text"] = txt

    created: list[str] = []

    def _save(path: str, content: str) -> None:
        with open(_lp(path), "w", encoding="utf-8") as f:
            f.write(content)
        created.append(os.path.relpath(path, video_dir).replace("\\", "/"))

    # Fotogrammi nel riassunto: aggiungiamo i frame (per timestamp) alle sezioni.
    # Sono salvati in analisi_visiva/frames/: link RELATIVO per il .md (portabile)
    # e ASSOLUTO per il PDF (il browser deve trovarli). Costo Groq aggiuntivo: 0
    # (i frame esistono già, nessuna nuova chiamata al modello vision).
    frame_notes = [n for n in visual_notes if n.get("image")] if SUMMARY_FRAMES else []
    sections_md, sections_pdf = summarized, summarized
    if frame_notes:
        frames_dir = os.path.join(video_dir, visual_subdir(ui_lang), "frames")
        rel_prefix = f"../{visual_subdir(ui_lang)}/frames/"
        sections_md = _append_frames_to_sections(summarized, frame_notes, lambda img: rel_prefix + img)
        sections_pdf = _append_frames_to_sections(summarized, frame_notes,
                                                  lambda img: os.path.join(frames_dir, img))

    # Il riassunto è testo pulito: niente timestamp. Il .txt resta senza immagini.
    _save(f"{base}.md", build_md(meta["title"], meta, engine_label, sections_md, with_timestamps=False))
    _save(f"{base}.txt", build_txt(meta["title"], meta, summarized, markdown=True))
    if do_export:
        with console.status("[info]Creo il PDF (formule, mappe e fotogrammi)...[/info]", spinner="dots"):
            ok = _save_pdf(meta, sections_pdf, f"{base}.pdf", with_timestamps=False,
                           engine_label=engine_label, markdown=True)
        if ok:
            created.append(os.path.relpath(f"{base}.pdf", video_dir).replace("\\", "/"))

    files = "  ".join(os.path.splitext(c.split('/')[-1])[1] for c in created)
    console.print()
    console.print(Panel(
        Group(
            Text.from_markup(f"[bold]Motore:[/bold] {engine_label}"),
            Text.from_markup(f"[dim]📁 {sum_dir}[/dim]"),
            Text.from_markup(f"[info]🧠 {os.path.basename(sum_dir)}/[/info]  {files}"),
        ),
        title="[bold bright_magenta]✅ Riassunto completato![/bold bright_magenta]",
        border_style="bright_magenta", box=DOUBLE, expand=False, padding=(1, 3),
    ))
    # Riassunto concluso e salvato: fase completata nello stato.
    update_stage(meta, "summary", status=STAGE_DONE, done=len(summarized),
                 total=len(summarized), sections=summarized,
                 extra={"lang": ui_lang or "it"})
    return True


# === PRE-RUN ESTIMATE (cost for Groq, time for local) ========================
# Approximate Groq audio pricing ($ per hour of audio) and local processing-speed
# factors (processing time / audio time), used ONLY for the pre-run estimate so
# the user knows what to expect before committing. Figures are indicative.
GROQ_PRICE_PER_HOUR = {
    "whisper-large-v3-turbo": 0.04,
    "whisper-large-v3": 0.111,
    "distil-whisper-large-v3-en": 0.02,
}
_LOCAL_REALTIME_CPU = {
    "base": 0.10, "small": 0.18, "medium": 0.45,
    "large-v3": 0.90, "large-v3-turbo": 0.22,
}


def estimate_job(meta: dict, backend: str, model: str | None = None) -> dict:
    """Rough pre-run estimate for ONE source, BEFORE downloading/transcribing.

    Groq: estimated $ cost from the audio duration and the model's per-hour price.
    Local: estimated processing TIME from a per-model realtime factor, divided by
    ~8 on GPU. Returns a dict with a ready-to-show Italian 'detail' string."""
    duration = meta.get("duration") or 0
    hours = duration / 3600
    if backend == "groq":
        # 'model' (se passato) è il modello Groq scelto dall'utente; altrimenti il
        # default corrente. Il prezzo/ora dipende dal modello selezionato.
        gm = model or GROQ_MODEL
        price = GROQ_PRICE_PER_HOUR.get(gm, 0.04)
        cost = hours * price
        return {"backend": "groq", "duration": duration, "cost_usd": cost,
                "model": gm,
                "detail": (f"costo stimato ~${cost:.3f} (Groq {gm}, "
                           f"{_format_duration(duration)} di audio)")}
    device, _ = _resolve_device()
    rt = _LOCAL_REALTIME_CPU.get(model or "small", 0.2)
    if device == "cuda":
        rt /= 8
    secs = duration * rt
    dev = "GPU" if device == "cuda" else "CPU"
    return {"backend": "local", "duration": duration, "device": device, "seconds": secs,
            "detail": (f"tempo stimato ~{_format_duration(secs)} su {dev} "
                       f"(modello {model or 'small'}); nessun costo (offline)")}


def run() -> None:
    """Orchestration: choose the engine and the SOURCE (YouTube URL or local
    file/folder), confirm, then run download/preparation/transcription/saving.

    A local folder becomes a BATCH: every audio file inside it is transcribed in
    turn, reusing the same engine and the same translate/export choices."""
    # Prerequisite check: ffmpeg must be in the PATH.
    if not shutil.which("ffmpeg"):
        console.print("[error]ffmpeg non trovato nel PATH. Installalo prima di continuare.[/error]")
        return

    # --- Transcription backend selection (local vs Groq) ---
    backend = choose_backend()
    if not backend:
        return

    # If local, we choose the model RIGHT AWAY (so that any cancellation happens
    # before downloading anything). If Groq, we pick the CLOUD model here too, so
    # the cost estimate and the whole run use exactly the model chosen.
    local_model = None
    if backend == "local":
        local_model = choose_local_model()
        if not local_model:
            return
        # Backend locale ⇒ traduzione e riassunto girano su Ollama: si sceglie
        # qui anche quel modello (invio = attuale), come per il modello Whisper.
        om = choose_ollama_model("text")
        if not om:
            return
        global OLLAMA_MODEL, OLLAMA_TRANSLATE_MODEL
        OLLAMA_MODEL = om
        # La traduzione riusa il modello del riassunto, salvo .env esplicito.
        if not _env_str("ECHOSCRIPT_OLLAMA_TRANSLATE_MODEL", ""):
            OLLAMA_TRANSLATE_MODEL = om
    else:  # groq: scelta del modello di trascrizione cloud (costo associato)
        gm = choose_groq_model()
        if not gm:
            return
        global GROQ_MODEL
        GROQ_MODEL = gm

    # --- Source selection: YouTube URL or local file/folder ---
    source_kind = choose_source()
    if not source_kind:
        return

    # Each job is (meta, (kind, ref)). YouTube yields exactly one job; a local
    # folder yields one job per audio file found (batch).
    jobs: list[tuple[dict, tuple[str, str]]] = []
    # Se la sorgente è una playlist YouTube, tutti i suoi video finiscono in una
    # sottocartella dedicata di results/ (nome = titolo playlist, o canale).
    playlist_subdir: str | None = None
    if source_kind == "youtube":
        url = _prompt("Incolla l'URL del video o della playlist YouTube",
                      "(q per uscire)", accent="bright_magenta")
        if not url or url.lower() == "q":
            return

        # Un URL con "list=" PUÒ essere una playlist: lo verifichiamo con una
        # lettura veloce (flat). Se lo è, trascriviamo TUTTI i suoi video.
        pl = None
        if "list=" in url:
            with console.status("[info]Leggo la playlist...[/info]", spinner="dots"):
                pl = _cli_get_playlist_info(url)

        if pl and pl["count"] >= 1:
            # --- Sorgente PLAYLIST: un job per video, tutti sotto results/<playlist> ---
            collected: list[tuple[dict, str]] = []  # (meta, url) dei video disponibili
            with console.status("[info]Leggo le informazioni dei video...[/info]",
                                spinner="dots") as st:
                for i, vurl in enumerate(pl["entries"], 1):
                    st.update(f"[info]Leggo le informazioni dei video... ({i}/{pl['count']})[/info]")
                    m = _cli_get_video_info(vurl)
                    if not m:
                        # Video privato/rimosso/non disponibile: lo saltiamo e proseguiamo.
                        console.print(f"  [warning]Video {i}/{pl['count']} non disponibile: saltato.[/warning]")
                        continue
                    collected.append((m, vurl))
            if not collected:
                console.print("[error]Nessun video disponibile nella playlist.[/error]")
                return
            display_playlist_sources(pl, [m for m, _ in collected])
            total_dur = sum((m["duration"] or 0) for m, _ in collected)
            console.print(f"  [dim]💡 {estimate_job({'duration': total_dur}, backend, local_model)['detail']}[/dim]")
            n = len(collected)
            if not _confirm(f"Procedo con la trascrizione dei {n} video della playlist?",
                            accent="bright_cyan"):
                console.print("[warning]Operazione annullata.[/warning]")
                return
            jobs = [(m, ("youtube", vurl)) for m, vurl in collected]
            playlist_subdir = _safe_filename(pl["title"] or pl["channel"] or "playlist")
        else:
            # --- Video singolo (comportamento invariato) ---
            with console.status("[info]Leggo le informazioni del video...[/info]", spinner="dots"):
                meta = _cli_get_video_info(url)
            if not meta:
                return
            display_video_info(meta)
            console.print(f"  [dim]💡 {estimate_job(meta, backend, local_model)['detail']}[/dim]")
            if not _confirm("Procedo con la trascrizione di questo video?", accent="bright_cyan"):
                console.print("[warning]Operazione annullata.[/warning]")
                return
            jobs.append((meta, ("youtube", url)))
    else:
        path = _prompt("Incolla il percorso del file o della cartella audio",
                       "(q per uscire)", accent="bright_magenta")
        if not path or path.lower() == "q":
            return
        files = resolve_local_sources(path)
        if not files:
            return
        with console.status("[info]Leggo la durata dei file...[/info]", spinner="dots"):
            metas = [local_file_meta(f) for f in files]
        display_local_sources(metas)
        total_dur = sum(m["duration"] or 0 for m in metas)
        console.print(f"  [dim]💡 {estimate_job({'duration': total_dur}, backend, local_model)['detail']}[/dim]")
        what = "questo file" if len(metas) == 1 else f"questi {len(metas)} file"
        if not _confirm(f"Procedo con la trascrizione di {what}?", accent="bright_green"):
            console.print("[warning]Operazione annullata.[/warning]")
            return
        jobs = [(m, ("local", m["source_path"])) for m in metas]

    # Optional: force the audio language (otherwise Whisper auto-detects it).
    # Helps on noisy/multilingual audio where auto-detection can pick wrong.
    global LANGUAGE
    al = _prompt("Lingua dell'audio", "(invio = autorileva · es. it, en, es, fr, de)",
                 accent="bright_blue").strip().lower()
    if al:
        LANGUAGE = al

    # --- Analisi visiva opzionale (solo se la sorgente ha dei fotogrammi) ---
    has_video_source = (source_kind == "youtube") or any(
        kind == "local" and os.path.splitext(ref)[1].lower() in VIDEO_EXTENSIONS
        for _, (kind, ref) in jobs)
    want_visual = False
    if has_video_source:
        console.print()
        console.print("  [bold bright_yellow]👁  Analisi visiva del video (sperimentale)[/bold bright_yellow]")
        console.print("  [dim]Oltre all'audio, EchoScript può «guardare» i fotogrammi ed estrarre ciò che è[/dim]")
        console.print("  [dim]scritto a schermo — codice, formule, grafici, diagrammi — per includerlo nel[/dim]")
        console.print("  [dim]riassunto. È più lento e, con Groq, consuma crediti per ogni fotogramma.[/dim]")
        v_eng = "Groq cloud" if backend == "groq" else "Ollama locale"
        want_visual = _confirm(f"Attivo l'analisi visiva? (motore: {v_eng})", accent="bright_yellow")
        # In locale la vision passa da Ollama: si sceglie qui il modello.
        # Annullare il pannello disattiva SOLO l'analisi visiva, non la run.
        if want_visual and backend != "groq":
            vm = choose_ollama_model("vision")
            if not vm:
                want_visual = False
                console.print("  [dim]Analisi visiva disattivata.[/dim]")
            else:
                global OLLAMA_VISION_MODEL
                OLLAMA_VISION_MODEL = vm

    # We initialize the Groq client only if it is really needed (cloud backend),
    # and only after the user's confirmation.
    client = None
    if backend == "groq":
        client = get_groq_client()
        if not client:
            return

    # Engine label, shown in the file header and in the summary.
    engine_label = (f"Locale / faster-whisper {local_model}" if backend == "local"
                    else f"Groq / {GROQ_MODEL}")

    # Il PDF viene SEMPRE generato (come nella GUI): niente più domanda.
    do_export = True
    console.print(f"  {SYM_OK} Il PDF verrà generato automaticamente.")
    _tr_engine = (f"Google Translate" if client is not None
                  else f"Ollama in locale, offline")
    console.print(f"  {SYM_OK} A trascrizione completata, la traduzione in italiano "
                  f"verrà generata in automatico ({_tr_engine}).")

    out_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    # Playlist: tutti i video vanno in results/<nome playlist>/<titolo video>/...
    if playlist_subdir:
        out_root = os.path.join(out_root, playlist_subdir)
        os.makedirs(out_root, exist_ok=True)

    # --- Process each job (one for YouTube, one per file in a batch) ---
    total = len(jobs)
    for idx, (meta, source) in enumerate(jobs, 1):
        if _interrupted:
            break
        if total > 1:
            console.print()
            console.rule(f"[bold bright_green]🎙 File {idx}/{total}: {meta['title']}[/bold bright_green]",
                         style="bright_green")

        # Controlli prima di trascrivere: già trascritto / parziale da riprendere.
        # La ripresa esiste sia per Groq (a blocchi) sia per il locale (a tempo).
        resume_cp = load_checkpoint(meta) if backend == "groq" else load_local_checkpoint(meta)
        is_local_cp = bool(resume_cp) and "done_seconds" in resume_cp

        def _drop_cp() -> None:
            """Delete whichever checkpoint kind applies to this run."""
            delete_local_checkpoint(meta) if backend == "local" else delete_checkpoint(meta)

        # Di default, dopo una trascrizione COMPLETATA al 100% si genera anche la
        # traduzione italiana in automatico. L'unica eccezione è «ritrascrivi
        # solamente» (vedi sotto), dove l'utente chiede esplicitamente di NON
        # tradurre. Se i crediti finiscono a metà, _run_pipeline torna None e si
        # salta tutto (incluso il blocco di traduzione): mai tradotti i parziali.
        also_translate = True

        if transcription_exists(out_root, meta["title"]):
            can_resume = has_resumable_state(meta)
            action = choose_existing_action(
                meta["title"], can_resume=can_resume,
                resume_info=resume_info_text(meta) if can_resume else "")
            if action == "resume":
                # Riprendi da dove si è interrotto: completa le fasi mancanti
                # (traduzione/riassunto) ripartendo dalla sezione ferma.
                resume_existing(out_root, meta, client=client, do_export=do_export)
                continue
            if action == "translate":
                # Solo traduzione: traduce la trascrizione salvata, niente riassunto
                # e nessun credito di trascrizione.
                translate_existing(out_root, meta["title"], target="it",
                                   do_export=do_export, local=client is None)
                continue
            if action == "summary":
                # Solo riassunto: niente ri-trascrizione né traduzione. Riassume la
                # TRADUZIONE salvata se presente (vedi summarize_existing),
                # altrimenti la trascrizione originale.
                summarize_with_local_fallback(out_root, meta, client,
                                              source_sections=None, do_export=do_export)
                continue
            if action == "both":
                # Trascrivi nuovamente DA CAPO e poi traduci: butta ogni parziale.
                _drop_cp()
                delete_state(meta)
                resume_cp = None
            elif action == "retranscribe":
                _drop_cp()                 # ritrascrizione completa: butta via ogni parziale
                delete_state(meta)
                also_translate = False     # «soltanto»: niente traduzione
                resume_cp = None
            else:                          # "skip"
                console.print("[dim]Saltato.[/dim]")
                continue
        elif resume_cp:
            if is_local_cp:
                done_s = int(resume_cp.get("done_seconds", 0))
                tot_s = int(resume_cp.get("duration", 0) or 0)
                prog = (f"{_format_timestamp(done_s)} / {_format_timestamp(tot_s)}"
                        if tot_s else _format_timestamp(done_s))
                console.print(f"[info]Ripresa disponibile per «{meta['title']}»: arrivato a {prog}.[/info]")
            else:
                done, tot = resume_cp.get("done_chunks", 0), resume_cp.get("total_chunks", 0)
                console.print(f"[info]Ripresa disponibile per «{meta['title']}»: {done}/{tot} blocchi salvati.[/info]")
            ch = _prompt("Cosa fai? \\[r]iprendi · \\[d]a capo · \\[s]alta",
                         "(r/d/s)", accent="bright_cyan").strip().lower()
            if ch.startswith("s"):
                console.print("[dim]Saltato.[/dim]")
                continue
            if ch.startswith("d"):
                _drop_cp()
                resume_cp = None

        # Registra il piano della pipeline (per «Riprendi» in una sessione futura):
        # traduzione prevista salvo «ritrascrivi soltanto»; il riassunto segue
        # sempre. Non tocca un eventuale resume_cp di trascrizione già in corso.
        if not resume_cp:
            init_run_state(meta, backend, want_translate=also_translate,
                           want_summary=also_translate)

        result = _run_pipeline(meta, source, backend, client, local_model,
                               resume_cp, want_visual, out_root)
        if not result or not result[0]:
            # _run_pipeline ha già spiegato il motivo (interruzione/limite o errore).
            continue
        segments, visual_notes = result
        # Se si è completato in locale dopo il limite Groq, l'etichetta motore è
        # stata aggiornata (Groq + Locale); altrimenti vale quella scelta a monte.
        label = meta.pop("engine_label_override", engine_label)
        _save_outputs(meta, segments, label, do_export, out_root)
        # Trascrizione completata e salvata: aggiorna lo stato della pipeline.
        # Se l'audio è già in italiano la traduzione non serve (fase → skip),
        # così un futuro «Riprendi» punterà direttamente al riassunto.
        update_stage(meta, "transcription", status=STAGE_DONE)
        if _is_italian(meta.get("detected_language")):
            update_stage(meta, "translation", status=STAGE_SKIP)
        # Analisi visiva: salva le note (json + md) accanto alla trascrizione, così
        # il riassunto (anche se rigenerato in seguito) le ritrova e le integra.
        if visual_notes:
            v_label = (f"Groq · {GROQ_VISION_MODEL}" if client is not None
                       else f"Ollama · {OLLAMA_VISION_MODEL}")
            save_visual_notes(out_root, meta, visual_notes, v_label, do_export)
        # Traduzione automatica dopo una trascrizione COMPLETATA (rilegge il .json
        # appena scritto). Si arriva qui solo se _run_pipeline ha restituito i
        # segmenti, cioè a trascrizione al 100%: i parziali da crediti esauriti
        # tornano None e non passano di qui. Disattivata solo da «ritrascrivi
        # solamente». Saltata anche se l'audio è già in italiano (it -> it inutile).
        # Dopo la traduzione (o, se audio già italiano, sull'originale) si genera
        # un RIASSUNTO pulito del testo italiano: Groq se cloud, Ollama se locale.
        if also_translate:
            if _is_italian(meta.get("detected_language")):
                console.print("  [dim]🇮🇹 Audio già in italiano: traduzione saltata, riassumo l'originale.[/dim]")
                summarize_with_local_fallback(out_root, meta, client,
                                              source_sections=None, do_export=do_export)
            else:
                translated = translate_existing(out_root, meta["title"], target="it",
                                                do_export=do_export, local=client is None)
                if translated:
                    summarize_with_local_fallback(out_root, meta, client,
                                                  source_sections=translated,
                                                  do_export=do_export)


def _probe_duration(audio_path: str) -> float:
    """Ask ffprobe for the duration of an audio file (in seconds).

    Used only as a fallback if the duration was not present in the YouTube
    metadata. If ffprobe also fails, it returns 0 (the splitting into chunks
    will produce nothing and the user will be warned)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


# === MAIN ===
# Entry point: executed only if you run "python transcriber.py"
# directly (not when the file is imported by another script).
if __name__ == "__main__":
    signal.signal(signal.SIGINT, _signal_handler)  # clean Ctrl+C handling
    _print_banner()
    try:
        run()
    except KeyboardInterrupt:
        console.print("\n[warning]Interrotto dall'utente.[/warning]")
        sys.exit(0)
