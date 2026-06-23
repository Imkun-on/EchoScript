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
CHUNK_SECONDS = 600                     # duration of each audio chunk in seconds (10 minutes)
AUDIO_SAMPLE_RATE = 16000              # 16 kHz: the sample rate recommended for Whisper
AUDIO_BITRATE = "64k"                  # audio bitrate of the chunks (low = small files, quality fine for speech)
MAX_RETRIES = 3                        # attempts per chunk before giving up
LANGUAGE = None                        # None = automatic language detection. Force with "it" or "en" if you want.

# --- Translation into Italian (via LLM on Groq) ---
# Chat model used to translate the transcription. "llama-3.3-70b-versatile"
# offers excellent quality on technical terms (RAG, fine-tuning, embedding...).
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
    }


def display_video_info(meta: dict) -> None:
    """Show the video card in a colored box (title, channel, views, date,
    duration, number of chapters)."""
    table = Table(show_header=False, box=None, expand=False, padding=(0, 1))
    table.add_column("Icona", justify="center", no_wrap=True)
    table.add_column("Campo", style="dim", justify="left", no_wrap=True)
    table.add_column("Valore", style="bold bright_white", min_width=40, overflow="fold")

    table.add_row("📺", "Canale", meta["channel"])
    table.add_row("👁 ", "Visualizzazioni", _format_views(meta["views"]))
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

def _transcribe_chunk(client: Groq, chunk_path: str, prompt: str = "") -> list[dict]:
    """Send ONE audio chunk to Groq and return the list of its segments.

    Uses response_format='verbose_json' to receive, in addition to the text, the
    start/end timestamps of each sentence ('segments'). 'prompt' contains the
    tail of the previous transcription: giving Whisper a bit of context improves
    continuity (proper names, terminology) from one chunk to the next.
    Retries up to MAX_RETRIES times in case of a network/API error."""
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
            # result.segments is a list of objects with .start, .end, .text
            segments = getattr(result, "segments", None)
            if segments is None:
                # If for some reason there are no segments, we fall back to the whole text.
                return [{"start": 0.0, "end": 0.0, "text": getattr(result, "text", "").strip()}]
            return [
                {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"].strip()}
                for s in segments
            ]
        except Exception as e:
            msg = str(e)
            # Authentication/access errors (401/403): there is NO point retrying,
            # they do not resolve on their own. We stop immediately with a clear message.
            if "401" in msg or "403" in msg or "invalid_api_key" in msg:
                console.print(f"  [error]Accesso a Groq negato (chiave/rete): {e}[/error]")
                return []
            if attempt == MAX_RETRIES:
                console.print(f"  [error]Blocco fallito dopo {MAX_RETRIES} tentativi: {e}[/error]")
                return []
            # Increasing wait between one attempt and the next (linear backoff).
            import time
            time.sleep(2 * attempt)
    return []


def transcribe(client: Groq, chunks: list[tuple[float, str]]) -> list[dict]:
    """Transcribe all chunks in order, with a progress bar.

    For each chunk: transcribe it, then ADD the chunk's offset (start) to each
    segment's start/end, so the timings become relative to the whole video and
    not to the individual chunk. Returns the complete list of ordered segments,
    each {start, end, text}."""
    all_segments: list[dict] = []
    context = ""  # tail of the last text, passed as 'prompt' to the next chunk

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
        task_id = progress.add_task(f"Invio blocco 1/{n} a Groq", total=n)
        for i, (offset, path) in enumerate(chunks, 1):
            if _interrupted:
                break
            # We update the description BEFORE the call: the rich spinner keeps
            # animating while waiting for Groq, so the user sees that the i-th
            # chunk is in progress and is not waiting for nothing.
            progress.update(task_id, description=f"Invio blocco {i}/{n} a Groq (attendi)")
            segments = _transcribe_chunk(client, path, prompt=context)
            for seg in segments:
                # Timing correction: + the chunk's offset.
                seg["start"] += offset
                seg["end"] += offset
                all_segments.append(seg)
            # We update the context with the text of this chunk.
            if segments:
                context = " ".join(s["text"] for s in segments)
            progress.update(task_id, advance=1, description=f"Blocco {i}/{n} completato")

    return all_segments


# === LOCAL BACKEND: TRANSCRIPTION WITH faster-whisper ===

def transcribe_local(model_name: str, audio_path: str, duration: float) -> list[dict]:
    """Transcribe the entire audio LOCALLY with faster-whisper (no data over the network).

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
        return []

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
            return []

    # transcribe() returns (segment_generator, info). The segments are produced
    # as the audio is processed. vad_filter skips the silences.
    try:
        segments_gen, _info = model.transcribe(
            audio_path, language=LANGUAGE, vad_filter=True, beam_size=5,
        )
    except Exception as e:
        console.print(f"[error]Errore durante la trascrizione locale: {e}[/error]")
        return []

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

    return all_segments


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
    """Markdown header lines (metadata) shared between original and translated."""
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


def translate_text_groq(client, text: str) -> str:
    """Translate a text into Italian using an LLM on Groq.

    The system prompt asks to keep the technical terms correct and to return
    ONLY the translation. Long texts are translated in pieces (see
    _split_for_translation) and then stitched back together."""
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
                    "embedding, prompt, token, dataset). Restituisci SOLO la traduzione, senza "
                    "introduzioni, note o virgolette aggiunte."
                )},
                {"role": "user", "content": piece},
            ],
            temperature=0.2,
        )
        out_parts.append(resp.choices[0].message.content.strip())
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


# === EXPORT FOR READING (PDF and LaTeX) ===

def _section_heading(sec: dict, with_timestamps: bool) -> str:
    """Build the visible title of a section (with or without timing)."""
    if sec["title"] is None:
        return "Trascrizione"
    if with_timestamps and sec["start"] is not None:
        return f"[{_format_timestamp(sec['start'])}] {sec['title']}"
    return sec["title"]


def _latex_escape(s: str) -> str:
    """Escape the LaTeX special characters (#, $, %, &, _, {, }, \\, ~, ^)."""
    repl = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(repl.get(ch, ch) for ch in s)


def build_latex(title: str, meta: dict, sections: list[dict], with_timestamps: bool = True) -> str:
    """Generate a LaTeX document (.tex) divided into \\section per chapter.

    It requires no installation to be CREATED; to obtain the PDF you compile it
    wherever you want (Overleaf, MiKTeX, TeX Live)."""
    L = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[italian]{babel}",
        r"\usepackage{parskip}",
        r"\usepackage{hyperref}",
        rf"\title{{{_latex_escape(title)}}}",
        r"\date{}",
        r"\begin{document}",
        r"\maketitle",
        r"\begin{itemize}",
        rf"  \item Canale: {_latex_escape(meta['channel'])}",
        rf"  \item Pubblicato: {_latex_escape(_format_upload_date(meta['upload_date']))}",
        rf"  \item Durata: {_latex_escape(_format_duration(meta['duration']))}",
        rf"  \item URL: \url{{{meta['webpage_url']}}}",
        r"\end{itemize}",
        r"",
    ]
    for sec in sections:
        L.append(rf"\section{{{_latex_escape(_section_heading(sec, with_timestamps))}}}")
        if sec["text"]:
            L.append(_latex_escape(sec["text"]))
        L.append("")
    L.append(r"\end{document}")
    return "\n".join(L)


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

def run() -> None:
    """Orchestration: ask for the URL, show the info, confirm, and then run the
    download -> splitting -> transcription -> saving phases."""
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

    # --- We ask for the URL ---
    url = _prompt("Incolla l'URL del video YouTube", "(q per uscire)", accent="bright_magenta")
    if not url or url.lower() == "q":
        return

    # --- PHASE 0: metadata ---
    with console.status("[info]Leggo le informazioni del video...[/info]", spinner="dots"):
        meta = get_video_info(url)
    if not meta:
        return
    display_video_info(meta)

    # --- Confirmation ---
    if not _confirm("Procedo con la trascrizione di questo video?", accent="bright_cyan"):
        console.print("[warning]Operazione annullata.[/warning]")
        return

    # We initialize the Groq client only if it is really needed (cloud backend)
    # and only after the user's confirmation.
    client = None
    if backend == "groq":
        client = get_groq_client()
        if not client:
            return

    # Engine label, shown in the file header and in the summary.
    if backend == "local":
        engine_label = f"Locale / faster-whisper {local_model}"
    else:
        engine_label = f"Groq / {GROQ_MODEL}"

    # Number of phases: Groq has 3 (download + split + transcription), local 2
    # (download + transcription, without splitting).
    n_phases = 3 if backend == "groq" else 2

    # We use a temporary folder that is automatically deleted at the end (even in
    # case of an error), so as not to leave audio files lying around.
    with tempfile.TemporaryDirectory(prefix="yt_transcribe_") as workdir:
        # --- PHASE 1: audio download ---
        console.print()
        console.rule(f"[phase]⬇ Fase 1/{n_phases} — Download audio[/phase]", style="bright_blue")
        audio_path = download_audio(url, workdir)
        if not audio_path or _interrupted:
            console.print("[warning]Download non completato.[/warning]")
            return

        # Video duration (needed both for the Groq split and for the local bar).
        duration = meta["duration"] or 0
        if not duration:
            # If for some reason the duration was missing from the metadata, we ask ffprobe.
            duration = _probe_duration(audio_path)

        if backend == "groq":
            # --- PHASE 2: splitting (Groq only) ---
            console.print()
            console.rule("[phase]✂ Fase 2/3 — Preparazione audio[/phase]", style="bright_blue")
            chunks = split_audio(audio_path, duration, workdir)
            console.print(f"  {SYM_OK} Audio diviso in [info]{len(chunks)}[/info] blocchi da ~{CHUNK_SECONDS // 60} min")

            # --- PHASE 3: transcription (Groq) ---
            console.print()
            console.rule("[phase]✎ Fase 3/3 — Trascrizione (Groq)[/phase]", style="bright_green")
            segments = transcribe(client, chunks)
        else:
            # --- PHASE 2: local transcription (no splitting) ---
            console.print()
            console.rule(f"[phase]✎ Fase 2/2 — Trascrizione locale ({local_model})[/phase]", style="bright_green")
            segments = transcribe_local(local_model, audio_path, duration)

    # (Here the temporary folder has already been deleted: the data we need
    #  — the segments — is already in memory.)

    if not segments:
        console.print("[error]Nessun testo trascritto.[/error]")
        return

    # --- Saving: tidy folder structure ---
    #   results/<video name>/
    #       trascrizioni/  -> md, txt, json (+ pdf, tex if exported)
    #       traduzioni/    -> Italian version (+ pdf, tex if exported)
    safe_title = _safe_filename(meta["title"])
    video_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", safe_title)
    trans_dir = os.path.join(video_dir, "trascrizioni")
    os.makedirs(trans_dir, exist_ok=True)
    base_orig = os.path.join(trans_dir, safe_title)  # base path (without extension) of the originals

    # Common basis (sections) used by all text formats and by the export.
    sections = _build_sections(meta, segments)
    created: list[str] = []  # paths (relative to results/) of the generated files, for the summary

    def _save(path: str, content: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        # We save the path relative to the video folder (e.g. "trascrizioni/x.md").
        created.append(os.path.relpath(path, video_dir).replace("\\", "/"))

    _save(f"{base_orig}.md", build_md(meta["title"], meta, engine_label, sections, with_timestamps=True))
    _save(f"{base_orig}.txt", build_txt(meta["title"], meta, sections))
    _save(f"{base_orig}.json", build_transcript_json(meta, segments, engine_label))

    # --- Translation into Italian (optional, in the 'traduzioni' subfolder) ---
    it_sections = None       # translated sections (if requested), reused by the export
    it_title = None
    base_trad = None         # base path of the translated files (set if translating)
    if _confirm("Vuoi creare anche la versione tradotta in italiano?", accent="bright_magenta"):
        # To translate, a Groq client is needed (even if you transcribed locally).
        tclient = client
        if tclient is None:
            console.print("[warning]La traduzione usa Groq (cloud): il testo verra' inviato ai loro server.[/warning]")
            tclient = get_groq_client()
        if tclient is None:
            console.print("[warning]Traduzione saltata (nessun client Groq).[/warning]")
        else:
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

    # --- Export for reading: PDF + LaTeX (optional) ---
    if _confirm("Vuoi esportare in PDF e LaTeX (per leggerli comodamente)?", accent="bright_blue"):
        console.print()
        console.rule("[phase]📄 Esportazione PDF / LaTeX[/phase]", style="bright_blue")
        # (title, sections, timings, base-path) for the original and, if present, the translated one.
        exports = [(meta["title"], sections, True, base_orig, "originale")]
        if it_sections and base_trad:
            exports.append((it_title, it_sections, False, base_trad, "IT"))
        for title, secs, ts, base_path, etichetta in exports:
            try:
                _save(f"{base_path}.tex", build_latex(title, meta, secs, with_timestamps=ts))
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
