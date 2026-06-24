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

# === CONFIGURATION ===
# The program's "knobs", collected here at the top.
GROQ_MODEL = "whisper-large-v3-turbo"   # Whisper model on Groq: "turbo" is very fast and cheap.
                                        # Alternatives: "whisper-large-v3" (more accurate/slower),
                                        # "distil-whisper-large-v3-en" (English only, ultra-fast).
# Audio/video extensions accepted as LOCAL sources (phone recordings, PC files,
# video files from which ffmpeg extracts the audio track). ffmpeg reads all of
# these; anything not listed is still attempted but with a gentle warning.
AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".m4b", ".wav", ".ogg", ".oga", ".opus", ".aac", ".flac",
    ".wma", ".aiff", ".aif", ".amr", ".3gp", ".caf",          # audio
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",          # video (audio extracted)
}

CHUNK_SECONDS = 600                     # duration of each audio chunk in seconds (10 minutes)
AUDIO_SAMPLE_RATE = 16000              # 16 kHz: the sample rate recommended for Whisper
AUDIO_BITRATE = "64k"                  # audio bitrate of the chunks (low = small files, quality fine for speech)
MAX_RETRIES = 3                        # attempts per chunk before giving up
LANGUAGE = None                        # None = automatic language detection. Force with "it" or "en" if you want.

# --- Translation into Italian (via LLM on Groq) ---
# Chat model used to translate the transcription. "llama-3.3-70b-versatile" gives
# clearly BETTER quality (technical nuance, fluency) than the small models: it is
# the default because translation quality matters more than speed here. Trade-off:
# a lower free-tier daily token limit (~100k/day), so on very long videos you may
# hit it (the run warns and keeps the transcription). For maximum throughput on
# long videos you can switch back to "llama-3.1-8b-instant" (~500k/day, lower quality).
GROQ_TRANSLATE_MODEL = "llama-3.3-70b-versatile"
# Long texts are translated in pieces of ~at most this number of characters, so
# as not to exceed the model's output limit (splitting at sentence boundaries).
TRANSLATE_MAX_CHARS = 2500

# --- LOCAL backend (faster-whisper on CPU) ---
# compute_type "int8" is the fastest on CPU (8-bit quantization): it loses very
# little quality but is much faster than "float32".
LOCAL_COMPUTE_TYPE = "int8"
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


def transcription_exists(out_root: str, title: str) -> bool:
    """True se in out_root/<titolo>/trascrizioni/ ci sono già file trascritti."""
    d = os.path.join(out_root, _safe_filename(title), "trascrizioni")
    if not os.path.isdir(d):
        return False
    return any(n.lower().endswith((".md", ".txt", ".json", ".pdf")) for n in os.listdir(d))


def load_existing_transcript(out_root: str, title: str):
    """Rilegge una trascrizione salvata (dal .json) e ricostruisce
    (meta, segments, engine_label), sufficienti a rigenerare SOLO la traduzione
    senza ri-trascrivere (e senza rispendere crediti). None se assente/vuota."""
    p = os.path.join(out_root, _safe_filename(title), "trascrizioni",
                     _safe_filename(title) + ".json")
    if not os.path.isfile(p):
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

def _transcribe_chunk(client: Groq, chunk_path: str, prompt: str = "",
                      return_language: bool = False):
    """Send ONE audio chunk to Groq and return the list of its segments.

    Uses response_format='verbose_json' to receive, in addition to the text, the
    start/end timestamps of each sentence ('segments'). 'prompt' contains the
    tail of the previous transcription: giving Whisper a bit of context improves
    continuity (proper names, terminology) from one chunk to the next.
    Retries up to MAX_RETRIES times in case of a network/API error.

    If return_language=True, returns (segments, language) where 'language' is the
    ISO code Whisper auto-detected (e.g. 'en'/'it'), otherwise just the segments
    (backward-compatible default for the CLI)."""
    def _ret(segs, lang):
        return (segs, lang) if return_language else segs

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(chunk_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    file=(os.path.basename(chunk_path), f.read()),
                    model=GROQ_MODEL,
                    response_format="verbose_json",
                    # timestamp_granularities requests timestamps at the segment (sentence) level.
                    timestamp_granularities=["segment"],
                    language=LANGUAGE,            # None = auto-detection
                    prompt=prompt[-400:],         # last ~400 characters as context
                    temperature=0.0,             # 0 = more deterministic/faithful output
                )
            lang = getattr(result, "language", None)
            # result.segments is a list of objects with .start, .end, .text
            segments = getattr(result, "segments", None)
            if segments is None:
                # If for some reason there are no segments, we fall back to the whole text.
                return _ret([{"start": 0.0, "end": 0.0, "text": getattr(result, "text", "").strip()}], lang)
            return _ret([
                {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"].strip()}
                for s in segments
            ], lang)
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
                # Timing correction: + the chunk's offset.
                seg["start"] += offset
                seg["end"] += offset
                all_segments.append(seg)
            # We update the context with the text of this chunk.
            if segments:
                context = " ".join(s["text"] for s in segments)
            progress.update(task_id, advance=1, description=f"Blocco {i + 1}/{n} completato")

    return all_segments, detected


# === LOCAL BACKEND: TRANSCRIPTION WITH faster-whisper ===

def transcribe_local(model_name: str, audio_path: str, duration: float):
    """Transcribe the entire audio LOCALLY with faster-whisper (no data over the network).

    Returns (segments, detected_language).

    Unlike Groq, no splitting is needed: faster-whisper processes the whole file
    and returns the segments incrementally (a generator), so we can update the
    bar as we go. The bar uses the video's DURATION as the total and advances up
    to the 'end' of the last processed segment.

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

    # Loading the model (on first use it downloads the weights).
    with console.status(
        f"[info]Carico il modello '{model_name}'... "
        f"(al primo uso scarica i pesi da HuggingFace, una volta sola)[/info]",
        spinner="dots",
    ):
        try:
            model = WhisperModel(model_name, device="cpu", compute_type=LOCAL_COMPUTE_TYPE)
        except Exception as e:
            console.print(f"[error]Impossibile caricare il modello: {e}[/error]")
            return [], None

    # transcribe() returns (segment_generator, info). The segments are produced
    # as the audio is processed. vad_filter skips the silences.
    try:
        segments_gen, info = model.transcribe(
            audio_path, language=LANGUAGE, vad_filter=True, beam_size=5,
        )
    except Exception as e:
        console.print(f"[error]Errore durante la trascrizione locale: {e}[/error]")
        return [], None
    detected = getattr(info, "language", None)

    all_segments: list[dict] = []
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

    with progress:
        # total = the video's duration: the bar advances based on the reached timestamp.
        task_id = progress.add_task("Trascrivo (locale)", total=duration or None)
        for seg in segments_gen:
            if _interrupted:
                break
            all_segments.append({
                "start": float(seg.start), "end": float(seg.end), "text": seg.text.strip(),
            })
            if duration:
                # min() avoids exceeding 100% if the last segment overruns the estimated duration.
                progress.update(task_id, completed=min(seg.end, duration))
        if duration:
            progress.update(task_id, completed=duration)  # brings the bar to 100% at the end of the loop

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


# === TRANSLATION INTO ITALIAN (via LLM on Groq) ===

def _split_for_translation(text: str, max_chars: int) -> list[str]:
    """Split a long text into pieces <= max_chars, cutting at sentence boundaries.

    Avoids exceeding the model's output limit on very long texts (e.g. a video
    without chapters). It splits at the sentence-ending punctuation (.!?) and
    re-joins the sentences as long as they fit within the limit."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    # Split keeping the sentence-ending punctuation attached to the sentence.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = sent
        else:
            current = f"{current} {sent}".strip()
    if current:
        chunks.append(current.strip())
    return chunks


def _strip_markdown(s: str) -> str:
    """Rimuove la formattazione Markdown che gli LLM tendono ad aggiungere.

    Serve perché il modello (spec. il 70b) "abbellisce" il testo con grassetto
    (`**parola**`), corsivo, titoli ed elenchi: nel `.md` diventa grassetto
    indesiderato, nel PDF/TXT restano asterischi visibili. Qui togliamo gli
    enfatici **/__/*/_ , i titoli (#) e i marcatori di elenco/citazione."""
    # Grassetto e corsivo (coppie di marcatori attorno al testo).
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"__(.+?)__", r"\1", s)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", s)
    # Eventuali marcatori spaiati rimasti.
    s = s.replace("**", "").replace("__", "")
    # Marcatori a inizio riga: titoli #, citazioni >, elenchi -, *, +.
    s = re.sub(r"(?m)^\s{0,3}(#{1,6}\s+|>\s+|[-*+]\s+)", "", s)
    return s.strip()


def translate_text_groq(client, text: str) -> str:
    """Translate a text into Italian using an LLM on Groq.

    The system prompt asks to keep the technical terms correct and to return
    ONLY the translation, in PLAIN text (no Markdown). Long texts are translated
    in pieces (see _split_for_translation) and stitched back together. As a
    safety net we also strip any Markdown the model adds anyway."""
    text = (text or "").strip()
    if not text:
        return ""
    out_parts: list[str] = []
    for piece in _split_for_translation(text, TRANSLATE_MAX_CHARS):
        resp = client.chat.completions.create(
            model=GROQ_TRANSLATE_MODEL,
            messages=[
                {"role": "system", "content": (
                    "Sei un traduttore professionista. Traduci in italiano il testo dell'utente. "
                    "Mantieni corretti i termini tecnici di informatica/AI (es. RAG, fine-tuning, "
                    "embedding, prompt, token, dataset). Restituisci SOLO la traduzione, in "
                    "TESTO SEMPLICE: NON usare formattazione Markdown, niente grassetto, corsivo, "
                    "asterischi, titoli (#) o elenchi puntati. Niente introduzioni, note o "
                    "virgolette aggiunte; mantieni la punteggiatura del testo originale."
                )},
                {"role": "user", "content": piece},
            ],
            temperature=0.2,
        )
        out_parts.append(_strip_markdown(resp.choices[0].message.content.strip()))
    return " ".join(out_parts)


def translate_sections(client, sections: list[dict]) -> list[dict]:
    """Translate the title and text of each section, with a progress bar.

    Returns new sections (same structure) with the contents in Italian. Keeps
    'start' (for consistency) even though the translated version does not show
    the timings."""
    translated: list[dict] = []
    progress = Progress(
        SpinnerColumn("dots", style="bright_magenta"),
        TextColumn("[phase]{task.description}"),
        BarColumn(bar_width=40, style="bar.back", complete_style="bright_magenta", finished_style="bold magenta"),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TextColumn("[dim]│[/dim]"),
        TimeElapsedColumn(),
        console=console, expand=False,
    )
    n = len(sections)
    with progress:
        task_id = progress.add_task(f"Traduco 1/{n}", total=n)
        for i, sec in enumerate(sections, 1):
            if _interrupted:
                break
            progress.update(task_id, description=f"Traduco sezione {i}/{n} (attendi)")
            t_title = translate_text_groq(client, sec["title"]) if sec["title"] else None
            t_text = translate_text_groq(client, sec["text"]) if sec["text"] else ""
            translated.append({"start": sec["start"], "title": t_title, "text": t_text})
            progress.update(task_id, advance=1, description=f"Sezione {i}/{n} tradotta")
    return translated


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


# === API KEY ===

def load_dotenv() -> None:
    """Load the variables from a '.env' file next to the script, if present.

    It is a mini-parser with no external dependencies: it reads lines in the
    KEY=value format (ignoring empty lines and comments with '#'), removes any
    quotes around the value, and sets the environment variable ONLY if it is not
    already defined. This way a real environment variable (e.g. set with setx)
    always takes precedence over the .env file.

    The .env file must NOT be committed (it is already in .gitignore): keep it
    only locally, it contains your secret key."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments. Tolerate the "export " prefix.
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):]
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")  # partition splits at the FIRST '='
                key = key.strip()
                value = value.strip().strip('"').strip("'")  # strip spaces and quotes
                # setdefault: does not overwrite an already existing variable.
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError as e:
        console.print(f"[warning]Impossibile leggere .env: {e}[/warning]")


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
                console.print(f"\n[warning]Limite Groq raggiunto: trascritti "
                              f"{ti.done}/{ti.total} blocchi. Progresso salvato: "
                              f"riavvia con lo stesso video per riprendere.[/warning]")
                return None
            delete_checkpoint(meta)
        else:
            console.print()
            console.rule(f"[phase]✎ Fase {step['transcribe']}/{n} — Trascrizione · Locale CPU ({local_model})[/phase]",
                         style="bright_green")
            console.print("  [warning]La trascrizione locale gira sulla CPU: può richiedere diversi minuti.[/warning]")
            segments, detected = transcribe_local(local_model, audio_path, duration)

        # Lingua dell'audio rilevata da Whisper (per la card di riepilogo).
        meta["detected_language"] = detected

    # (Here the temporary folder has already been deleted: the data we need
    #  — the segments — is already in memory.)
    return segments or None


def _save_outputs(meta: dict, segments: list[dict], engine_label: str,
                  do_translate: bool, tclient, do_export: bool, out_root: str) -> None:
    """Write all outputs for ONE transcription, then print the summary panel.

    Layout: out_root/<title>/trascrizioni/ (+ traduzioni/ if translating). The
    translation and export choices are passed in (asked once, up front) so the
    same flags apply to every file in a batch."""
    # --- Saving: tidy folder structure ---
    #   results/<title>/
    #       trascrizioni/  -> md, txt, json (+ pdf, tex if exported)
    #       traduzioni/    -> Italian version (+ pdf, tex if exported)
    safe_title = _safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe_title)
    trans_dir = os.path.join(video_dir, "trascrizioni")
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

    # --- Translation into Italian (optional, in the 'traduzioni' subfolder) ---
    it_sections = None       # translated sections (if requested), reused by the export
    it_title = None
    base_trad = None         # base path of the translated files (set if translating)
    if do_translate and tclient is not None:
        console.print()
        console.rule("[phase]🌐 Traduzione in italiano (Groq)[/phase]", style="bright_magenta")
        with console.status("[info]Traduco il titolo...[/info]", spinner="dots"):
            it_title = translate_text_groq(tclient, meta["title"])
        it_sections = translate_sections(tclient, sections)
        if it_sections:
            # We create the 'traduzioni' subfolder only now that it is really needed.
            trad_dir = os.path.join(video_dir, "traduzioni")
            os.makedirs(trad_dir, exist_ok=True)
            base_trad = os.path.join(trad_dir, safe_title)
            # The translated files have NO timings (clean version to read).
            _save(f"{base_trad}.md", build_md(it_title, meta, f"{engine_label} (tradotto in italiano)",
                                              it_sections, with_timestamps=False))
            _save(f"{base_trad}.txt", build_txt(it_title, meta, it_sections))

    # --- Export for reading: PDF (optional) ---
    if do_export:
        console.print()
        console.rule("[phase]📄 Esportazione PDF[/phase]", style="bright_blue")
        # (title, sections, timings, base-path, label) for the original and, if present, the translated one.
        exports = [(meta["title"], sections, True, base_orig, "originale")]
        if it_sections and base_trad:
            exports.append((it_title, it_sections, False, base_trad, "IT"))
        for title, secs, ts, base_path, etichetta in exports:
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
        icon = "📂" if folder == "trascrizioni" else "🌐"
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


def _translate_existing_cli(out_root: str, title: str, tclient) -> None:
    """SOLA ri-traduzione (CLI): rilegge la trascrizione salvata e rigenera solo
    i file di traduzione (md/txt/pdf), senza ri-trascrivere."""
    loaded = load_existing_transcript(out_root, title)
    if not loaded:
        console.print("[error]Trascrizione esistente non trovata o illeggibile.[/error]")
        return
    meta, segments, engine_label = loaded
    safe = _safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe)
    sections = _build_sections(meta, segments)
    console.print()
    console.rule("[phase]🌐 Sola traduzione in italiano (Groq)[/phase]", style="bright_magenta")
    try:
        with console.status("[info]Traduco il titolo...[/info]", spinner="dots"):
            it_title = translate_text_groq(tclient, meta["title"])
        it_sections = translate_sections(tclient, sections)
    except Exception as e:
        console.print(f"[error]Traduzione non riuscita: {e}[/error]")
        return
    if not it_sections:
        console.print("[warning]Traduzione vuota.[/warning]")
        return
    trad_dir = os.path.join(video_dir, "traduzioni")
    os.makedirs(trad_dir, exist_ok=True)
    base = os.path.join(trad_dir, safe)
    with open(f"{base}.md", "w", encoding="utf-8") as f:
        f.write(build_md(it_title, meta, f"{engine_label} (tradotto in italiano)",
                         it_sections, with_timestamps=True))
    with open(f"{base}.txt", "w", encoding="utf-8") as f:
        f.write(build_txt(it_title, meta, it_sections))
    try:
        with console.status("[info]Creo il PDF...[/info]", spinner="dots"):
            build_pdf(it_title, meta, it_sections, f"{base}.pdf", with_timestamps=True)
    except Exception as e:
        console.print(f"[error]Export PDF fallito: {e}[/error]")
    console.print(f"[success]✓ Traduzione aggiornata in {trad_dir}[/success]")


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
        what = "questo file" if len(metas) == 1 else f"questi {len(metas)} file"
        if not _confirm(f"Procedo con la trascrizione di {what}?", accent="bright_green"):
            console.print("[warning]Operazione annullata.[/warning]")
            return
        jobs = [(m, ("local", m["source_path"])) for m in metas]

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

    # Translate/export are asked ONCE here and applied to every job (so a batch
    # does not stop to ask between files).
    do_translate = _confirm("Vuoi creare anche la versione tradotta in italiano?", accent="bright_magenta")
    tclient = client  # the translation always uses Groq, even when transcribing locally
    if do_translate and tclient is None:
        console.print("[warning]La traduzione usa Groq (cloud): il testo verra' inviato ai loro server.[/warning]")
        tclient = get_groq_client()
        if tclient is None:
            console.print("[warning]Traduzione saltata (nessun client Groq).[/warning]")
            do_translate = False
    # Il PDF viene SEMPRE generato (come nella GUI): niente più domanda.
    do_export = True
    console.print(f"  {SYM_OK} Il PDF verrà generato automaticamente.")

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
        resume_cp = load_checkpoint(meta) if backend == "groq" else None
        if transcription_exists(out_root, meta["title"]):
            console.print(f"[warning]«{meta['title']}» è già stato trascritto in results/.[/warning]")
            ch = _prompt("Cosa fai? [r]itrascrivi tutto · [t]raduci soltanto · [s]alta",
                         "(r/t/s)", accent="bright_yellow").strip().lower()
            if ch.startswith("t"):
                tc = tclient or client or get_groq_client()
                if tc:
                    _translate_existing_cli(out_root, meta["title"], tc)
                continue
            if not ch.startswith("r"):
                console.print("[dim]Saltato.[/dim]")
                continue
            resume_cp = None  # ritrascrizione completa: ignora eventuale parziale
        elif resume_cp:
            done, tot = resume_cp.get("done_chunks", 0), resume_cp.get("total_chunks", 0)
            console.print(f"[info]Ripresa disponibile per «{meta['title']}»: {done}/{tot} blocchi salvati.[/info]")
            ch = _prompt("Cosa fai? [r]iprendi · [d]a capo · [s]alta",
                         "(r/d/s)", accent="bright_cyan").strip().lower()
            if ch.startswith("s"):
                console.print("[dim]Saltato.[/dim]")
                continue
            if ch.startswith("d"):
                delete_checkpoint(meta)
                resume_cp = None

        segments = _run_pipeline(meta, source, backend, client, local_model, resume_cp)
        if not segments:
            # _run_pipeline ha già spiegato il motivo (interruzione/limite o errore).
            continue
        _save_outputs(meta, segments, engine_label, do_translate, tclient, do_export, out_root)


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
