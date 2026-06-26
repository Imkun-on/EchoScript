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
GROQ_SUMMARY_MODEL = _env_str("ECHOSCRIPT_GROQ_SUMMARY_MODEL", "llama-3.3-70b-versatile")
OLLAMA_MODEL = _env_str("ECHOSCRIPT_OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_HOST = _env_str("ECHOSCRIPT_OLLAMA_HOST", "http://localhost:11434")
# Finestra di contesto per Ollama. ATTENZIONE: di default Ollama usa solo 2048
# token e TRONCA in silenzio gli input più lunghi (rovinando i riassunti dei
# video lunghi). Lo alziamo per far entrare un blocco intero (~SUMMARY_MAX_CHARS)
# + prompt + risposta. 8192 è un buon compromisso qualità/RAM su 7-8B.
OLLAMA_NUM_CTX = _env_int("ECHOSCRIPT_OLLAMA_NUM_CTX", 8192)
# Oltre questa lunghezza (caratteri) una sezione viene riassunta a blocchi e poi
# i parziali vengono uniti (map-reduce), per non sforare il contesto del modello.
SUMMARY_MAX_CHARS = _env_int("ECHOSCRIPT_SUMMARY_MAX_CHARS", 12000)

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


# === RATE LIMIT + CHECKPOINT (ripresa dei video lunghi su Groq) =============

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


def _checkpoints_dir() -> str:
    """Cartella dedicata ai checkpoint dei video parziali."""
    root = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(root, "results", ".checkpoints")


def _checkpoint_key(meta: dict) -> str:
    """Chiave stabile per identificare il video/file fra una sessione e l'altra."""
    if meta.get("source") == "local":
        base = os.path.basename(meta.get("source_path") or meta.get("webpage_url") or meta.get("title") or "local")
        return "local_" + _safe_filename(base)
    return "yt_" + _safe_filename(meta.get("id") or meta.get("title") or "video")


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


# Subfolder names per interface language: an English user gets English folders
# (transcriptions/translations) instead of the Italian defaults. The CLI is
# Italian-only, so it always uses the "it" names; the GUI passes its current UI
# language down so the folders match what the user sees on screen.
TRANS_SUBDIRS = {"it": "trascrizioni", "en": "transcriptions"}
TRANSL_SUBDIRS = {"it": "traduzioni", "en": "translations"}
SUMMARY_SUBDIRS = {"it": "riassunti", "en": "summaries"}
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


def transcription_exists(out_root: str, title: str) -> bool:
    """True se in out_root/<titolo>/<trascrizioni>/ ci sono già file trascritti.

    Controlla TUTTI i possibili nomi cartella (italiano e inglese), così il
    rilevamento funziona anche se il video era stato trascritto con l'interfaccia
    in un'altra lingua."""
    base = os.path.join(out_root, _safe_filename(title))
    for sub in TRANS_SUBDIRS.values():
        d = os.path.join(base, sub)
        if os.path.isdir(d) and any(
                n.lower().endswith((".md", ".txt", ".json", ".pdf")) for n in os.listdir(d)):
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
        if os.path.isfile(cand):
            p = cand
            break
    if not p:
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
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
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
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


# Actions offered when a video is ALREADY transcribed (numbered panel below).
# number -> (icon, title, description, action-code)
_EXISTING_ACTIONS = {
    "1": ("🔁", "Ritrascrivi tutto",
          "rifà da capo trascrizione + traduzione + riassunto", "both"),
    "2": ("🌐", "Traduzione + riassunto",
          "riusa la trascrizione salvata, la traduce e la riassume (nessun credito di trascrizione)", "translate"),
    "3": ("🧠", "Solo riassunto",
          "genera soltanto il riassunto dal testo salvato (la traduzione se c'è, altrimenti l'originale)", "summary"),
    "4": ("🎙", "Ritrascrivi soltanto",
          "rifà solo la trascrizione, senza traduzione né riassunto", "retranscribe"),
    "5": ("⏭", "Salta",
          "non fare nulla per questo video", "skip"),
}


def choose_existing_action(title: str) -> str:
    """Pannello a elenco numerato per un video GIÀ trascritto: chiede cosa fare.

    Mostra le opzioni numerate (come gli altri pannelli) ed è più chiaro del
    vecchio prompt a lettere. Restituisce uno dei codici azione:
    "both" · "translate" · "summary" · "retranscribe" · "skip"."""
    table = Table(show_header=True, box=None, expand=False, padding=(0, 2),
                  header_style="bold dim")
    table.add_column("#", style="bold bright_white", justify="center")
    table.add_column("Azione", style="bold bright_yellow", no_wrap=True)
    table.add_column("Cosa fa", style="info")
    for key, (icon, name, desc, _code) in _EXISTING_ACTIONS.items():
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
            "\n[bold bright_yellow]›[/bold bright_yellow] [bold]Scelta[/bold] "
            "[dim](1-5 · q = salta)[/dim]: ").strip().lower()
        if choice == "q":
            return "skip"
        if choice in _EXISTING_ACTIONS:
            return _EXISTING_ACTIONS[choice][3]
        console.print("[warning]Scelta non valida, riprova.[/warning]")


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


# === PROMPT (user input with a consistent style) ===

def _prompt(label: str, hint: str = "", accent: str = "bright_blue") -> str:
    """User input with a consistent style: colored arrow + label."""
    h = f" [dim]{hint}[/dim]" if hint else ""
    return console.input(f"\n[bold {accent}]›[/bold {accent}] [bold]{label}[/bold]{h}: ").strip()


def _confirm(label: str, accent: str = "bright_blue") -> bool:
    """Yes/no question with a consistent style; True only if the user answers 's'."""
    return _prompt(label, "(s/n)", accent).lower() == "s"


# === PHASE 0: VIDEO METADATA ===

def get_video_info(url: str) -> dict | None:
    """Download ONLY the video metadata (without downloading the audio).

    Uses yt-dlp with download=False: a lightweight call that returns a large
    dictionary of information. We extract the fields we need and pack them into
    our own, cleaner dictionary. In case of an error (invalid URL, private
    video, network...) it returns None."""
    ydl_opts = {
        "quiet": True,            # no yt-dlp output on screen (we handle it ourselves)
        "no_warnings": True,
        "skip_download": True,    # do NOT download the media, only the info
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        console.print(f"[error]Impossibile leggere il video: {e}[/error]")
        return None

    # Some URLs (playlists) return a list of 'entries': we take the first one.
    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    categories = info.get("categories") or []
    return {
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


def _lang_name(code: str | None) -> str | None:
    """Nome italiano di una lingua. Accetta sia i codici ISO (faster-whisper:
    'en') sia i nomi interi di Whisper (Groq: 'english'). None se assente."""
    if not code:
        return None
    c = str(code).split("-")[0].strip().lower()
    full = {"italian": "it", "english": "en", "spanish": "es",
            "french": "fr", "german": "de"}
    c = full.get(c, c)
    names = {"it": "Italiano", "en": "Inglese", "es": "Spagnolo",
             "fr": "Francese", "de": "Tedesco"}
    return names.get(c, str(code).upper())


def _is_italian(code: str | None) -> bool:
    """True se il codice/nome lingua indica l'italiano (es. 'it', 'italian').

    Usata per saltare la traduzione automatica quando l'audio è già in italiano
    (tradurre it -> it sarebbe inutile)."""
    if not code:
        return False
    c = str(code).split("-")[0].strip().lower()
    return c in ("it", "ita", "italian", "italiano")


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

def download_audio(url: str, workdir: str) -> str | None:
    """Download ONLY the video's audio into the temporary folder `workdir`.

    Shows a progress bar with percentage, speed and estimated time, updated by
    the yt-dlp hook (a function that yt-dlp calls continuously during the
    download). Returns the path of the downloaded audio file, or None if
    something goes wrong."""
    out_template = os.path.join(workdir, "audio.%(ext)s")  # %(ext)s = the actual extension chosen by yt-dlp

    # A bar with: spinner, description, bar, percentage, downloaded bytes, speed,
    # and estimated remaining time at the end.
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
    task_id = progress.add_task("Scarico audio", total=None)  # total=None: unknown until yt-dlp reports it

    def _hook(d: dict) -> None:
        """Callback called by yt-dlp with the download status."""
        if _interrupted:
            # Raising an exception here interrupts the yt-dlp download.
            raise KeyboardInterrupt
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            if total:
                progress.update(task_id, completed=done, total=total)
            else:
                progress.update(task_id, completed=done)
        elif d["status"] == "finished":
            # Download finished: but yt-dlp now EXTRACTS the audio with ffmpeg (a
            # few seconds, without a percentage). We signal it so it does not look stuck.
            progress.update(task_id, description="Estraggo audio (attendi)")

    def _pp_hook(d: dict) -> None:
        """Post-processor callback (the audio conversion after the download).

        It serves to NOT leave the screen frozen during the audio extraction: we
        update the description so the user sees that the work continues."""
        status = d.get("status")
        if status == "started":
            progress.update(task_id, description="Converto audio in m4a (attendi)")
        elif status == "finished":
            progress.update(task_id, description="Audio pronto")

    ydl_opts = {
        "format": "bestaudio/best",   # the best audio-only track available
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,           # suppress yt-dlp's internal bar (we use our rich one)
        "progress_hooks": [_hook],
        "postprocessor_hooks": [_pp_hook],  # to show the progress of the conversion
        # Extracts/normalizes the audio into m4a via ffmpeg (already present on the system).
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
        }],
    }

    try:
        with progress:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
    except KeyboardInterrupt:
        return None
    except Exception as e:
        console.print(f"[error]Errore nel download audio: {e}[/error]")
        return None

    # The postprocessor produces a .m4a: we look for it in the working folder.
    for fname in os.listdir(workdir):
        if fname.startswith("audio."):
            return os.path.join(workdir, fname)
    return None


# === PHASE 2: PREPARATION / SPLITTING ===

def split_audio(audio_path: str, duration: float, workdir: str) -> list[tuple[float, str]]:
    """Split the audio into chunks of CHUNK_SECONDS, re-encoding them to 16 kHz mono.

    For each chunk it launches ffmpeg with:
      -ss <start>     -> skip to the chunk's start second
      -t  <duration>  -> take only CHUNK_SECONDS seconds
      -ac 1           -> 1 channel (mono)
      -ar 16000       -> 16 kHz (format Whisper likes)
    Returns a list of pairs (offset_in_seconds, mp3_file_path).
    The offset is used later to correct each chunk's timestamps.
    Shows a progress bar that grows as the chunks are created."""
    chunks: list[tuple[float, str]] = []
    # Number of chunks computed in advance (rounded up) to give the bar a total.
    # max(1, ...) avoids 0 chunks on very short audio.
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
        start = 0.0
        idx = 0
        while start < duration:
            if _interrupted:
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
            progress.advance(task_id)
    return chunks


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
                      want_words: bool | None = None):
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
                result = client.audio.transcriptions.create(
                    file=(os.path.basename(chunk_path), f.read()),
                    model=GROQ_MODEL,
                    response_format="verbose_json",
                    timestamp_granularities=granularities,
                    language=lang_opt,            # None = auto-detection
                    prompt=prompt[-400:],         # last ~400 characters as context
                    temperature=0.0,             # 0 = more deterministic/faithful output
                )
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
                     meta: dict | None = None, resume_cp: dict | None = None,
                     workdir: str | None = None):
    """Transcribe the entire audio LOCALLY with faster-whisper (no data over the network).

    Returns (segments, detected_language).

    Unlike Groq, no splitting is needed: faster-whisper processes the whole file
    and returns the segments incrementally (a generator), so we can update the
    bar as we go. The bar uses the video's DURATION as the total and advances up
    to the 'end' of the last processed segment.

    RESUME: if 'meta' is given, the partial result is checkpointed every
    LOCAL_CHECKPOINT_EVERY seconds of audio. If a matching checkpoint exists (and
    'workdir' is available for the trimmed file), we trim the audio from the saved
    point with ffmpeg, transcribe only the remainder, and shift its timestamps
    back, so an interrupted long run resumes instead of starting over.

    PRIVACY: on the first use of a model, faster-whisper downloads its "weights"
    from HuggingFace (once only, then they stay cached). The AUDIO, however, is
    never sent anywhere: the transcription happens on your PC."""
    # Silence the HuggingFace warning about symlinks (irrelevant: the cache works
    # anyway). It must be set BEFORE importing faster-whisper.
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    # "Lazy" import: only those who use the local backend need faster-whisper.
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        console.print("[error]faster-whisper non installato. Esegui:  pip install faster-whisper[/error]")
        return [], None

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
                console.print(f"  [info]Ripresa dalla posizione {_format_timestamp(start_offset)} "
                              f"({len(all_segments)} segmenti già fatti).[/info]")
            except Exception:
                start_offset, all_segments, detected = 0.0, [], None  # trim failed: full re-run

    # Loading the model (on first use it downloads the weights).
    with console.status(
        f"[info]Carico il modello '{model_name}' su {dev_note}... "
        f"(al primo uso scarica i pesi da HuggingFace, una volta sola)[/info]",
        spinner="dots",
    ):
        try:
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
        except Exception as e:
            console.print(f"[error]Impossibile caricare il modello: {e}[/error]")
            return [], None

    # transcribe() returns (segment_generator, info). The segments are produced
    # as the audio is processed. vad_filter skips the silences; word_timestamps
    # asks for per-word timings (so segments carry a 'words' list).
    try:
        segments_gen, info = model.transcribe(
            transcribe_path, language=LANGUAGE, vad_filter=True, beam_size=5,
            word_timestamps=WORD_TIMESTAMPS,
        )
    except Exception as e:
        console.print(f"[error]Errore durante la trascrizione locale: {e}[/error]")
        return all_segments or [], detected
    detected = detected or getattr(info, "language", None)

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

    last_abs_end = start_offset   # highest audio time reached (absolute)
    last_saved = start_offset     # audio time at the last checkpoint save
    completed_fully = True
    with progress:
        # total = the video's duration: the bar advances based on the reached timestamp.
        task_id = progress.add_task("Trascrivo (locale)", total=duration or None,
                                    completed=min(start_offset, duration) if duration else None)
        for seg in segments_gen:
            if _interrupted:
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
                progress.update(task_id, completed=min(abs_end, duration))
            # Periodic checkpoint, so an interruption loses at most a couple of minutes.
            if meta and (abs_end - last_saved) >= LOCAL_CHECKPOINT_EVERY:
                save_local_checkpoint(meta, all_segments, abs_end, model_name, duration, detected)
                last_saved = abs_end
        if duration and completed_fully:
            progress.update(task_id, completed=duration)  # bring the bar to 100% when done

    # Done -> drop the checkpoint; interrupted -> keep the latest partial to resume.
    if meta:
        if completed_fully:
            delete_local_checkpoint(meta)
        else:
            save_local_checkpoint(meta, all_segments, last_abs_end, model_name, duration, detected)
    return all_segments, detected


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


def _md_header(title: str, meta: dict, engine_label: str) -> list[str]:
    """Markdown header lines (metadata) shared between original and translated.

    Local files have no channel/views/date, so we show the source path instead."""
    if _is_local(meta):
        return [
            f"# {title}", "",
            "- **Sorgente:** File audio locale",
            f"- **File:** {meta['webpage_url']}",
            f"- **Durata:** {_format_duration(meta['duration'])}",
            f"- **Trascritto con:** {engine_label}",
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
        "", "---", "",
    ]


def build_md(title: str, meta: dict, engine_label: str, sections: list[dict],
             with_timestamps: bool = True) -> str:
    """Markdown document: header + sections.

    The timings (if with_timestamps) appear ONLY in the section titles
    (## [HH:MM:SS] Title); the body is flowing prose, tidier. The translated
    version passes with_timestamps=False (no timings)."""
    lines = _md_header(title, meta, engine_label)
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


def build_txt(title: str, meta: dict, sections: list[dict]) -> str:
    """Clean TXT version (for other LLMs): no timings, sections as [Title]."""
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
            lines.append(f"[{sec['title']}]")
        if sec["text"]:
            lines.append(sec["text"])
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
              with_timestamps: bool = True) -> None:
    """Create a readable PDF, divided by chapters, with fpdf2 (no LaTeX).

    Uses Windows' Arial font (TrueType) to support accents and Unicode
    characters. Large title, metadata in italics, section titles in bold and the
    body text in paragraphs."""
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
    def cell(h: float, txt: str) -> None:
        pdf.multi_cell(0, h, txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

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
    pdf.ln(4)

    for sec in sections:
        pdf.set_font("Doc", "B", 14)
        cell(7, _section_heading(sec, with_timestamps))
        pdf.ln(1)
        if sec["text"]:
            pdf.set_font("Doc", "", 11)
            cell(6, sec["text"])
        pdf.ln(3)

    pdf.output(out_path)


# === TRADUZIONE (gratuita, via Google Translate) ============================
# Riusa una trascrizione GIÀ salvata e ne produce una versione tradotta, senza
# ri-trascrivere (quindi senza spendere crediti Groq) e senza alcuna API key:
# si appoggia a deep_translator.GoogleTranslator (endpoint pubblico gratuito).

# Google Translate accetta ~5000 caratteri per richiesta: spezziamo il testo in
# blocchi più piccoli sui confini di frase, per stare comodi sotto il limite.
_TRANSLATE_MAX_CHARS = 4500


def _make_translator(target: str = "it"):
    """Crea un traduttore Google (sorgente autorilevata) verso 'target'.

    Solleva un errore chiaro se deep_translator non è installato."""
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        raise RuntimeError("deep_translator non installato. Esegui:  "
                           "pip install deep-translator")
    return GoogleTranslator(source="auto", target=target)


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


def _translate_text(translator, text: str) -> str:
    """Traduce un testo (anche lungo) unendo i blocchi tradotti."""
    out = []
    for chunk in _split_for_translation(text):
        try:
            out.append(translator.translate(chunk) or "")
        except Exception:
            # Un blocco fallito non deve far saltare l'intera traduzione:
            # si tiene l'originale come fallback per quel pezzo.
            out.append(chunk)
    return " ".join(s for s in out if s).strip()


def translate_sections(sections: list[dict], target: str = "it",
                       on_progress=None) -> list[dict]:
    """Traduce titolo e testo di ogni sezione verso 'target' (default italiano).

    'on_progress(i, n)' (opzionale) viene chiamato dopo ogni sezione tradotta,
    per aggiornare una barra/spinner. Restituisce nuove sezioni (non muta quelle
    in ingresso)."""
    translator = _make_translator(target)
    out: list[dict] = []
    n = len(sections)
    for i, sec in enumerate(sections, 1):
        title = sec.get("title")
        new_title = (_translate_text(translator, title) if title else title)
        new_text = _translate_text(translator, sec.get("text", ""))
        out.append({"start": sec.get("start"), "title": new_title, "text": new_text})
        if on_progress:
            on_progress(i, n)
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


def _run_pipeline(meta: dict, source: tuple[str, str], backend: str,
                  client, local_model: str | None,
                  resume_cp: dict | None = None) -> list[dict] | None:
    """Acquire the audio for ONE source and transcribe it.

    'source' is ('youtube', url) or ('local', filepath). For a local file there
    is no download phase. Con backend Groq supporta la RIPRESA da 'resume_cp'; se
    il limite Groq viene raggiunto, salva un checkpoint e restituisce None (così
    il chiamante non salva una trascrizione incompleta). Returns the segments, or
    None on interruption / failure."""
    kind, ref = source

    # Build the phase labels dynamically so "Fase x/y" is always correct.
    phase_names = []
    if kind == "youtube":
        phase_names.append("download")
    if backend == "groq":
        phase_names.append("prepare")
    phase_names.append("transcribe")
    n = len(phase_names)
    step = {name: i + 1 for i, name in enumerate(phase_names)}

    # ignore_cleanup_errors: evita il PermissionError (WinError 32) su Windows se
    # l'audio temporaneo resta bloccato un istante da ffmpeg/whisper alla chiusura.
    with tempfile.TemporaryDirectory(prefix="echoscript_", ignore_cleanup_errors=True) as workdir:
        # --- Acquire the audio ---
        if kind == "youtube":
            console.print()
            console.rule(f"[phase]⬇ Fase {step['download']}/{n} — Download audio[/phase]", style="bright_blue")
            audio_path = download_audio(ref, workdir)
            if not audio_path or _interrupted:
                console.print("[warning]Download non completato.[/warning]")
                return None
        else:
            # Local file: feed it directly (ffmpeg/whisper read it in place).
            audio_path = ref

        # Duration: from metadata if present, otherwise probe the file with ffprobe.
        duration = meta["duration"] or _probe_duration(audio_path)
        meta["duration"] = duration  # keep it consistent for the output builders

        # --- Transcription ---
        if backend == "groq":
            console.print()
            console.rule(f"[phase]✂ Fase {step['prepare']}/{n} — Preparazione audio[/phase]", style="bright_blue")
            chunks = split_audio(audio_path, duration, workdir)
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
                segments, detected = transcribe_local(cont_model, audio_path, duration,
                                                      meta=meta, resume_cp=local_cp, workdir=workdir)
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
            segments, detected = transcribe_local(local_model, audio_path, duration,
                                                  meta=meta, resume_cp=resume_cp, workdir=workdir)

        # Lingua dell'audio rilevata da Whisper (per la card di riepilogo).
        meta["detected_language"] = detected

    # (Here the temporary folder has already been deleted: the data we need
    #  — the segments — is already in memory.)
    return segments or None


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
    os.makedirs(trans_dir, exist_ok=True)
    base_orig = os.path.join(trans_dir, safe_title)  # base path (without extension) of the originals

    # Common basis (sections) used by all text formats and by the export.
    sections = _build_sections(meta, segments)
    created: list[str] = []  # paths (relative to the video folder) of generated files, for the summary

    def _save(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        created.append(os.path.relpath(path, video_dir).replace("\\", "/"))

    _save(f"{base_orig}.md", build_md(meta["title"], meta, engine_label, sections, with_timestamps=True))
    _save(f"{base_orig}.txt", build_txt(meta["title"], meta, sections))
    _save(f"{base_orig}.json", build_transcript_json(meta, segments, engine_label))

    # --- Export for reading: PDF (optional) ---
    if do_export:
        console.print()
        console.rule("[phase]📄 Esportazione PDF[/phase]", style="bright_blue")
        for title, secs, ts, base_path, etichetta in [(meta["title"], sections, True, base_orig, "originale")]:
            try:
                with console.status(f"[info]Creo il PDF ({etichetta})...[/info]", spinner="dots"):
                    build_pdf(title, meta, secs, f"{base_path}.pdf", with_timestamps=ts)
                created.append(os.path.relpath(f"{base_path}.pdf", video_dir).replace("\\", "/"))
            except Exception as e:
                console.print(f"[error]Export fallito ({etichetta}): {e}[/error]")

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
                       do_export: bool = True, ui_lang: str = "it"):
    """Traduce una trascrizione GIÀ salvata (niente ri-trascrizione, nessun credito).

    Rilegge i file da out_root/<title>/, traduce le sezioni verso 'target'
    (default italiano) con Google Translate e salva md/txt (+ pdf) sotto
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

    safe_title = _safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe_title)
    trad_dir = os.path.join(video_dir, transl_subdir(ui_lang))
    os.makedirs(trad_dir, exist_ok=True)
    base = os.path.join(trad_dir, f"{safe_title}_{target}")
    lang_label = _lang_name(target) or target

    # Traduzione con barra di avanzamento (una tacca per sezione).
    console.print()
    console.rule(f"[phase]🌐 Traduzione → {lang_label}[/phase]", style="bright_blue")
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
                sections, target,
                on_progress=lambda i, n: progress.update(task_id, completed=i))
    except RuntimeError as e:  # deep_translator mancante
        console.print(f"[error]{e}[/error]")
        return None
    except Exception as e:
        console.print(f"[error]Traduzione fallita: {e}[/error]")
        return None

    engine_label = f"Traduzione automatica (Google Translate) → {lang_label}"
    created: list[str] = []

    def _save(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        created.append(os.path.relpath(path, video_dir).replace("\\", "/"))

    # La versione tradotta non porta i timestamp (testo continuo, più leggibile).
    _save(f"{base}.md", build_md(meta["title"], meta, engine_label, translated, with_timestamps=False))
    _save(f"{base}.txt", build_txt(meta["title"], meta, translated))
    # JSON delle SEZIONI tradotte: serve a «Solo riassunto» per riassumere la
    # traduzione (non l'originale) anche in una sessione successiva.
    _save(f"{base}.json",
          json.dumps({"target": target, "sections": translated}, ensure_ascii=False, indent=2))
    if do_export:
        try:
            with console.status("[info]Creo il PDF (traduzione)...[/info]", spinner="dots"):
                build_pdf(meta["title"], meta, translated, f"{base}.pdf", with_timestamps=False)
            created.append(os.path.relpath(f"{base}.pdf", video_dir).replace("\\", "/"))
        except Exception as e:
            console.print(f"[error]Export PDF traduzione fallito: {e}[/error]")

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
    "Sei un editor esperto. Ricevi la trascrizione di una sezione di un video "
    "parlato (testo in italiano). Trasformala in un riassunto chiaro, fedele e "
    "scorrevole, sempre in italiano, seguendo queste regole:\n"
    "- elimina intercalari e riempitivi (ehm, uhm, cioè, tipo, no?, allora, "
    "insomma) e le esitazioni;\n"
    "- togli ripetizioni, frasi interrotte e autocorrezioni di chi parla, "
    "tenendo solo la versione corretta;\n"
    "- CONSERVA tutti i concetti, i dati, i nomi propri e gli esempi importanti;\n"
    "- NON aggiungere nulla che non sia nel testo e non inventare;\n"
    "- struttura: da 3 a 6 punti elenco concisi e, se utile, 1-2 frasi finali "
    "di sintesi.\n"
    "Rispondi SOLO con il riassunto, senza preamboli né commenti."
)


def _summary_user_prompt(text: str, section_title: str | None) -> str:
    """Messaggio utente per il modello: titolo della sezione (se c'è) + testo."""
    head = f"Titolo della sezione: «{section_title}».\n\n" if section_title else ""
    return f"{head}Testo da riassumere:\n\n{text}"


def _summarize_groq(client, text: str, section_title: str | None) -> str:
    """Riassume un testo con un modello di CHAT di Groq (non Whisper)."""
    resp = client.chat.completions.create(
        model=GROQ_SUMMARY_MODEL,
        messages=[
            {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
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
            {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
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
                       on_progress=None) -> list[dict]:
    """Riassume ogni sezione (titolo invariato, testo -> riassunto).

    'on_progress(i, n)' (opzionale) è chiamato dopo ogni sezione. Restituisce
    nuove sezioni senza mutare quelle in ingresso."""
    out: list[dict] = []
    n = len(sections)
    for i, sec in enumerate(sections, 1):
        summary = _summarize_long(summarize_fn, sec.get("text", ""), sec.get("title"))
        out.append({"start": sec.get("start"), "title": sec.get("title"), "text": summary})
        if on_progress:
            on_progress(i, n)
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

    try:
        summarize_fn, engine_label = _make_summarizer(client)
    except RuntimeError as e:
        console.print(f"[warning]Riassunto non disponibile: {e}[/warning]")
        return False

    safe_title = _safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe_title)
    sum_dir = os.path.join(video_dir, summary_subdir(ui_lang))
    os.makedirs(sum_dir, exist_ok=True)
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
    try:
        with progress:
            task_id = progress.add_task("Riassumo le sezioni", total=len(sections))
            summarized = summarize_sections(
                sections, summarize_fn,
                on_progress=lambda i, n: progress.update(task_id, completed=i))
    except Exception as e:
        if _is_rate_limit(str(e)):
            console.print("[warning]Crediti Groq esauriti: riassunto saltato "
                          "(la trascrizione e la traduzione sono già salvate).[/warning]")
        else:
            console.print(f"[error]Riassunto fallito: {e}[/error]")
        return False

    created: list[str] = []

    def _save(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        created.append(os.path.relpath(path, video_dir).replace("\\", "/"))

    # Il riassunto è testo pulito: niente timestamp.
    _save(f"{base}.md", build_md(meta["title"], meta, engine_label, summarized, with_timestamps=False))
    _save(f"{base}.txt", build_txt(meta["title"], meta, summarized))
    if do_export:
        try:
            with console.status("[info]Creo il PDF (riassunto)...[/info]", spinner="dots"):
                build_pdf(meta["title"], meta, summarized, f"{base}.pdf", with_timestamps=False)
            created.append(os.path.relpath(f"{base}.pdf", video_dir).replace("\\", "/"))
        except Exception as e:
            console.print(f"[error]Export PDF riassunto fallito: {e}[/error]")

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
        price = GROQ_PRICE_PER_HOUR.get(GROQ_MODEL, 0.04)
        cost = hours * price
        return {"backend": "groq", "duration": duration, "cost_usd": cost,
                "detail": (f"costo stimato ~${cost:.3f} (Groq {GROQ_MODEL}, "
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
    # before downloading anything).
    local_model = None
    if backend == "local":
        local_model = choose_local_model()
        if not local_model:
            return

    # --- Source selection: YouTube URL or local file/folder ---
    source_kind = choose_source()
    if not source_kind:
        return

    # Each job is (meta, (kind, ref)). YouTube yields exactly one job; a local
    # folder yields one job per audio file found (batch).
    jobs: list[tuple[dict, tuple[str, str]]] = []
    if source_kind == "youtube":
        url = _prompt("Incolla l'URL del video YouTube", "(q per uscire)", accent="bright_magenta")
        if not url or url.lower() == "q":
            return
        with console.status("[info]Leggo le informazioni del video...[/info]", spinner="dots"):
            meta = get_video_info(url)
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
    console.print(f"  {SYM_OK} A trascrizione completata, la traduzione in italiano "
                  "verrà generata in automatico.")

    out_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

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
            action = choose_existing_action(meta["title"])
            if action == "translate":
                # Traduzione + riassunto: riusa i file salvati, nessuna
                # ri-trascrizione e nessun credito di trascrizione. Traduce, poi
                # riassume la traduzione e passa al prossimo job.
                translated = translate_existing(out_root, meta["title"], target="it",
                                                do_export=do_export)
                if translated:
                    summarize_existing(out_root, meta["title"], client=client,
                                       source_sections=translated, do_export=do_export)
                continue
            if action == "summary":
                # Solo riassunto: niente ri-trascrizione né traduzione. Riassume la
                # TRADUZIONE salvata se presente (vedi summarize_existing),
                # altrimenti la trascrizione originale.
                summarize_existing(out_root, meta["title"], client=client,
                                   source_sections=None, do_export=do_export)
                continue
            if action == "both":
                # Ritrascrivi DA CAPO e poi traduci: butta il parziale.
                _drop_cp()
                resume_cp = None
            elif action == "retranscribe":
                _drop_cp()                 # ritrascrizione completa: butta via ogni parziale
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

        segments = _run_pipeline(meta, source, backend, client, local_model, resume_cp)
        if not segments:
            # _run_pipeline ha già spiegato il motivo (interruzione/limite o errore).
            continue
        # Se si è completato in locale dopo il limite Groq, l'etichetta motore è
        # stata aggiornata (Groq + Locale); altrimenti vale quella scelta a monte.
        label = meta.pop("engine_label_override", engine_label)
        _save_outputs(meta, segments, label, do_export, out_root)
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
                summarize_existing(out_root, meta["title"], client=client,
                                   source_sections=None, do_export=do_export)
            else:
                translated = translate_existing(out_root, meta["title"], target="it",
                                                do_export=do_export)
                if translated:
                    summarize_existing(out_root, meta["title"], client=client,
                                       source_sections=translated, do_export=do_export)


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
