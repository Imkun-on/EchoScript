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

import os as _os
import sys as _sys

# La radice del progetto raggiungibile anche lanciando `python cli/main.py`.
#
# Senza, Python cerca i moduli solo accanto a questo file e dentro cli/ non
# c'e' nessun server/. Le due righe qui sotto risalgono di una cartella e la
# mettono in cima all'elenco dei posti dove cercare.
_RADICE = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _RADICE not in _sys.path:
    _sys.path.insert(0, _RADICE)

# --- Python standard library (already included, no installation) ---
import os                                          # environment variables, paths, files
import re                                          # regular expressions (file name cleanup)
import json                                        # export in .json format (for RAG/other LLMs)
import sys                                         # clean exit from the program
import signal                                      # intercept Ctrl+C
import time                                        # brevi attese: retry di scrittura, backoff
import shutil                                      # find the ffmpeg executable in PATH
import tempfile                                    # temporary folder for the audio
import subprocess                                  # launch ffmpeg/ffprobe as external processes
from datetime import datetime, timedelta           # format the publication date / limit resets

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

# === LA CONSOLE: sta in server/utils/console.py ==============================
#
# Una sola per tutti e due i modi di usare il programma: quando gira dentro una
# finestra, e' la finestra a dirottare l'uscita standard e a raccogliere queste
# righe per il diario. Chi scrive il codice del motore non deve sapere chi lo
# sta guardando.
from server.utils.console import (
    SYM_ARROW, SYM_DOT, SYM_FAIL, SYM_OK, console,
)

# === LE MANOPOLE: stanno in server/config/settings.py ========================
#
# Erano duecentoquarantacinque righe qui dentro, e adesso sono un file a parte.
# Il motivo non e' la lunghezza: e' che quei valori servono a mezzo programma,
# e tenerli dentro il file che fa le trascrizioni obbligava chiunque volesse
# leggerne uno a importare anche tutto il resto.
#
# ATTENZIONE alle due righe qui sotto, che non sono intercambiabili.
#
# La prima importa il MODULO. Serve per i sette valori che cambiano mentre il
# programma gira (quale modello Groq, quale modello Ollama, in che lingua), che
# vanno letti come `settings.GROQ_MODEL` ogni volta che servono. Importandoli
# per nome ci si porterebbe a casa una fotografia del valore al momento
# dell'import, e da li' in poi si userebbe sempre quella: nessun errore,
# nessun avviso, e il programma che usa il modello sbagliato.
#
# La seconda importa per nome tutto il resto, che dopo l'avvio non cambia mai.
from server.config import paths, settings
from server.config.settings import (
    AUDIO_BITRATE, AUDIO_EXTENSIONS, AUDIO_SAMPLE_RATE, BROWSER_PATH,
    CHUNK_SECONDS, CONCEPT_MAP, GROQ_TEXT_MODELS, GROQ_TRANSCRIBE_MODELS,
    GROQ_VISION_MODELS, LOCAL_COMPUTE_TYPE, LOCAL_DEVICE, LOCAL_MODELS,
    MAX_RETRIES, OLLAMA_HOST, OLLAMA_NUM_CTX, OLLAMA_TEXT_MODELS,
    OLLAMA_VISION_MODELS, RICH_PDF, SUMMARY_FRAMES, SUMMARY_MAX_CHARS,
    VIDEO_EXTENSIONS, VISION_FALLBACK_INTERVAL, VISION_FRAME_WIDTH,
    VISION_MAX_FRAMES, VISION_MIN_GAP, VISION_SCENE_THRESHOLD,
    VISION_YT_MAX_HEIGHT, WORD_TIMESTAMPS, _env_bool, _env_candidates,
    _env_int, _env_opt, _env_str, _load_env_file,
)

# === GRACEFUL SHUTDOWN ===
def _signal_handler(signum, frame):
    """Chiamata da sola quando si preme Ctrl+C.

    La prima volta non ferma niente di brutale: segna che si vuole smettere e
    lascia finire il pezzo in corso. Il motivo e' che in mezzo a un pezzo c'e'
    quasi sempre una scrittura su disco, e interromperla a meta' lascia un file
    rotto che poi nessuno capisce da dove sia uscito.

    La seconda volta si esce subito, perche' a quel punto chi preme lo sta
    chiedendo sul serio.

    La bandiera non sta qui ma in server/utils/contract.py, perche' a doverla
    LEGGERE sono le funzioni di lavoro, che di tastiere non sanno niente.
    """
    if fermarsi():
        console.print("\n[error]Interruzione forzata.[/error]")
        os._exit(1)
    chiedi_di_fermarsi()
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


# === MESSA IN BELLA: sta in server/utils/text.py =============================
#
# Durate, date, numeri, nomi di file sicuri. Sono uscite di qui perche' le usa
# tutto il programma e non appartengono alle trascrizioni piu' che a qualunque
# altra cosa. Si importano per nome perche' sono funzioni, e una funzione non
# cambia sotto i piedi a nessuno.
from server.utils.text import (
    _format_duration, _format_timestamp, _format_upload_date, _format_views,
    _lp, _safe_filename, write_text_file,
)

# === IL PATTO CON CHI CHIAMA: sta in server/utils/contract.py ================
#
# Le eccezioni con cui le funzioni di lavoro segnalano un guasto senza sapere
# chi le sta guardando, e le due richiamate di riserva che permettono di
# riferire l'avanzamento anche quando non sta ascoltando nessuno.
# Domande sul materiale: da dove arriva, in che lingua parla.
from server.utils.media import (
    _is_italian, _is_local, _is_same_language, _lang_code, _lang_name,
)
# Le tre domande che si fanno a Ollama prima di cominciare.
from server.utils.ollama import (
    _check_ollama, _ollama_has_model, _ollama_installed_models,
)
from server.utils.contract import (
    chiedi_di_fermarsi, fermarsi,
    GroqRateLimit, MediaError, TranscriptionInterrupted, _is_rate_limit,
    _never_stop, _noop_progress,
)

# === STATO E PARZIALI: stanno in server/state/ ===============================
#
# Seicento righe uscite di qui, divise in tre perche' erano tre mestieri:
# i limiti Groq consumati, i parziali per riprendere un video lungo, e le fasi
# gia' fatte di un lavoro. Stavano insieme solo perche' tutte e tre scrivono
# su disco, che non e' un motivo per stare nello stesso file.
from server.state.checkpoints import (
    LOCAL_CHECKPOINT_EVERY, _checkpoint_key, _checkpoints_dir,
    _local_resume_point, _trim_audio, checkpoint_path, delete_checkpoint,
    delete_local_checkpoint, load_checkpoint, load_local_checkpoint,
    local_checkpoint_path, save_checkpoint, save_local_checkpoint,
)
from server.state.credits import (
    _RATE_LIMIT_CACHE, _RATE_LIMIT_UNITS, _rate_limit_num,
    _rate_limit_reset_seconds, cached_rate_limits, parse_ratelimit_headers,
    ratelimit_groups, record_rate_limits,
)
from server.state.jobs import (
    PIPELINE_STAGES, STAGE_DONE, STAGE_PARTIAL, STAGE_PENDING, STAGE_SKIP,
    NOMI_VECCHI, SUMMARY_SUBDIR, SUMMARY_SUFFIX, TRANSL_SUBDIR, TRANS_SUBDIR,
    VISUAL_SUBDIR, _empty_state, delete_state, has_resumable_state,
    load_existing_transcript, load_existing_translation, load_state,
    resume_plan, resume_sections, save_state, stage_sections, stage_status,
    state_path, summary_subdir, trans_subdir, transcription_exists,
    transl_subdir, update_stage, visual_subdir,
)

# === TRANSCRIPTION BACKEND SELECTION ===

def _option_card(number: str, icon: str, title: str, rows: list[tuple[str, str]],
                 accent: str) -> Panel:
    """Una scheda: il riquadro con cui si presenta una scelta nei menu.

    Numero, icona, titolo e qualche riga di dettaglio. Le scelte importanti di
    questo programma sono sempre due o tre, e messe una accanto all'altra in
    riquadri della stessa forma si confrontano a colpo d'occhio: e' il motivo
    per cui i menu non sono un elenco numerato.

    Il colore del bordo distingue le alternative fra loro senza bisogno di
    leggerle: locale e nuvola hanno due colori fissi in tutto il programma.
    """
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
    current = settings.OLLAMA_MODEL if is_text else settings.OLLAMA_VISION_MODEL
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


# === temporaneo ==============================================================
#
# temporaneo
from server.state.jobs import (
    STAGE_LABELS_IT, resume_info_text,
)

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


def resume_existing(out_root: str, meta: dict, client=None, do_export: bool = True) -> None:
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
                                        do_export=do_export,
                                        local=client is None)
    if stage_status(load_state(meta), "summary") in (STAGE_PENDING, STAGE_PARTIAL):
        summarize_with_local_fallback(out_root, meta, client, translated,
                                      do_export)


def summarize_with_local_fallback(out_root: str, meta: dict, client,
                                  source_sections, do_export: bool = True) -> bool:
    """Riassume; se i crediti Groq si esauriscono a metà, offre di finire in locale.

    Il riassunto parziale è già salvato nello stato: proseguendo con Ollama si
    riprende dalla sezione ferma, senza rispendere nulla. Restituisce True se il
    riassunto è stato completato."""
    ok = summarize_existing(out_root, meta["title"], client=client,
                            source_sections=source_sections, do_export=do_export)
    if ok or client is None:
        return ok
    if stage_status(load_state(meta), "summary") not in (STAGE_PENDING, STAGE_PARTIAL):
        return ok
    if _confirm("Crediti Groq esauriti nel riassunto. Lo concludo ora in locale "
                "con Ollama (dalla sezione ferma)?", accent="bright_yellow"):
        return summarize_existing(out_root, meta["title"], client=None,
                                  source_sections=source_sections,
                                  do_export=do_export)
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
    """Mostra il file scelto, o l'elenco se si e' scelta una cartella intera.

    Due forme diverse per due situazioni diverse. Un file solo merita una
    scheda con i suoi dati; venti file meritano una tabella, perche' quello che
    serve li' e' scorrere l'elenco e vedere la durata totale prima di far
    partire qualcosa che durera' ore.
    """
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
    """Una domanda a chi sta usando il programma, sempre con lo stesso aspetto.

    La freccia colorata all'inizio non e' decorazione: in un terminale pieno di
    righe di avanzamento e' il segno che distingue «adesso tocca a te» da
    «sto ancora lavorando». Senza, le domande si perdono nel flusso e restano
    li' senza che nessuno se ne accorga.
    """
    h = f" [dim]{hint}[/dim]" if hint else ""
    return console.input(f"\n[bold {accent}]›[/bold {accent}] [bold]{label}[/bold]{h}: ").strip()


def _confirm(label: str, accent: str = "bright_blue") -> bool:
    """Una domanda da si' o no. Vale «si'» solo la s esplicita.

    Qualunque altra cosa, compreso l'invio a vuoto, conta come no. E' voluto:
    quasi tutte queste domande precedono qualcosa che costa tempo o crediti, e
    davanti a una risposta ambigua conviene non farlo.
    """
    return _prompt(label, "(s/n)", accent).lower() == "s"


# === PHASE 0: VIDEO METADATA ===

# === I METADATI: stanno in server/sources/metadata.py ========================
#
# Cosa c'e' dietro un link o dentro un file, prima di scaricare niente.
from server.sources.metadata import (
    _best_thumbnail, get_playlist_info, get_video_info, local_file_meta,
)

# --- Wrapper CLI dei metadati ------------------------------------------------
# Le funzioni core qui sopra sollevano MediaError; la CLI preferisce lavorare
# con None ("non è andata, vai avanti") e stampare l'errore in rosso.

def _cli_get_video_info(url: str) -> dict | None:
    """Come get_video_info, ma parlando: stampa l'errore e torna None.

    E' uno degli involucri che questo file mette intorno alle funzioni del
    motore. Il motore solleva un'eccezione e non stampa niente, perche' non sa
    chi lo sta guardando; qui si sa, quindi l'errore si scrive in rosso e si
    torna al menu invece di far cadere il programma.
    """
    try:
        return get_video_info(url)
    except MediaError as e:
        console.print(f"[error]{e}[/error]")
        return None


def _cli_get_playlist_info(url: str) -> dict | None:
    """Come get_playlist_info, ma stampando l'errore e tornando None.

    Stesso involucro di _cli_get_video_info, per lo stesso motivo.
    """
    try:
        return get_playlist_info(url)
    except MediaError as e:
        console.print(f"[error]{e}[/error]")
        return None


# === I MESSAGGI DI AVANZAMENTO: stanno in server/config/messages.py ==========
#
# Le righe che compaiono nel diario mentre il programma lavora. Erano in due
# lingue perche' il motore doveva parlare la lingua dell'interfaccia; adesso
# ce n'e' una sola, e `msg` non ha piu' bisogno di sapere in quale scrivere.
from server.config.messages import _RUNTIME_MSGS, msg    # noqa: F401



def display_video_info(meta: dict) -> None:
    """La scheda del video, da guardare prima di dire di si'.

    E' il momento in cui si scopre di aver incollato il link sbagliato, ed e'
    il motivo per cui questa scheda esiste. Accorgersene qui costa un secondo;
    accorgersene dopo costa mezz'ora di trascrizione e i crediti che sono
    andati con lei.

    Per questo ci sono anche i dati che apparentemente non servono a niente,
    come le visualizzazioni e il canale: sono quelli da cui si riconosce il
    video, molto piu' del titolo, che fra due lezioni della stessa serie e'
    quasi identico.
    """
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

# === LO SCARICAMENTO: sta in server/sources/download.py ======================
#
# Procurarsi l'audio. Solo l'audio: il video intero pesa dieci volte tanto.
from server.sources.download import (
    download_audio,
)

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
        """Riceve l'avanzamento dal motore e lo mette dentro la barra.

        Un avanzamento senza numeri non e' un errore: vuol dire «sto facendo
        qualcosa di cui non conosco la durata», per esempio convertire un file
        gia' scaricato. In quel caso si cambia solo la scritta e la barra resta
        dov'e', invece di farla saltare a un punto inventato.
        """
        if current is None:
            progress.update(task_id, description=detail or description)
            return
        if total:
            progress.update(task_id, completed=current, total=total)
        else:
            progress.update(task_id, completed=current)

    return progress, task_id, on_progress


def _cli_download_audio(url: str, workdir: str) -> str | None:
    """Scarica l'audio mostrando una barra, e gestisce il Ctrl+C.

    Involucro del motore per il terminale: la funzione vera riferisce
    l'avanzamento a chi la chiama, e qui quel racconto diventa una barra che
    si riempie.
    """
    progress, _task, on_progress = _download_progress("Scarico audio")
    try:
        with progress:
            return download_audio(url, workdir, on_progress,
                                  should_stop=fermarsi)
    except KeyboardInterrupt:
        return None
    except MediaError as e:
        console.print(f"[error]{e}[/error]")
        return None


# === PHASE 2: PREPARATION / SPLITTING ===

# === LA PREPARAZIONE DELL'AUDIO: sta in server/transcription/audio.py ========
#
# Riportare l'audio a un formato leggero e tagliarlo in blocchi trascrivibili.
from server.transcription.audio import (
    split_audio,
)

def _cli_split_audio(audio_path: str, duration: float, workdir: str) -> list[tuple[float, str]]:
    """Divide l'audio mostrando una barra che cresce a ogni blocco.

    Il numero di blocchi si calcola prima invece di scoprirlo strada facendo,
    cosi' la barra puo' dire «3 di 40» dal primo istante. Una barra che non sa
    quanti pezzi saranno puo' solo girare a vuoto, e girare a vuoto per due
    minuti non distingue un lavoro che procede da uno piantato.
    """
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
            """Sposta la barra al punto riferito, e basta.

            La piu' semplice delle tre: qui il totale e' noto da prima e non
            cambia, quindi non c'e' niente da decidere.
            """
            progress.update(task_id, completed=current or 0)

        try:
            return split_audio(audio_path, duration, workdir, on_progress,
                               should_stop=fermarsi)
        except MediaError as e:
            # Come gli altri wrapper `_cli_*`: il guasto si stampa in rosso e si
            # restituisce il vuoto, che la pipeline sa gia' trattare come "questo
            # video non si e' potuto fare". Lasciarlo salire farebbe uscire un
            # traceback in mezzo a un batch, interrompendo anche gli altri file.
            console.print(f"[error]{e}[/error]")
            return []


# === PHASE 3: TRANSCRIPTION WITH GROQ ===

# === LA TRASCRIZIONE SU GROQ: sta in server/transcription/groq_api.py ========
#
# Un blocco di audio alla volta verso i server di Groq, e cosa fare quando
# la risposta e' «hai finito i crediti per oggi», che non e' un guasto.
from server.transcription.groq_api import (
    _coerce, _extract_words, _transcribe_chunk,
)

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
            if fermarsi():
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

# === IL BACKEND LOCALE: sta in server/transcription/local_whisper.py =========
#
# Trascrivere su questo computer: piu' lento, gratuito, e niente esce di casa.
from server.transcription.local_whisper import (
    _resolve_device, transcribe_local,
)

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
        """L'avanzamento della trascrizione locale, che ha un caso in piu'.

        Prima che il lavoro cominci c'e' il caricamento del modello, che la
        prima volta scarica qualche gigabyte e dura parecchio. Non ha un
        avanzamento, quindi si stampa come riga sopra la barra: la barra resta
        a zero, ma almeno si sa che non e' piantato.
        """
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
                                    should_stop=fermarsi, meta=meta,
                                    resume_cp=resume_cp, workdir=workdir)
    except MediaError as e:
        console.print(f"[error]{e}[/error]")
        return [], None


# === IL DOCUMENTO: sta in server/export/document.py ==========================
#
# Markdown, testo semplice e json: lo stesso contenuto per tre destinatari
# diversi. Non stampano niente, quindi si sono spostate senza toccare una riga.
from server.export.document import (
    _build_sections, _md_header, _strip_md_bold, build_md,
    build_transcript_json, build_txt,
)

# === IL PDF SEMPLICE: sta in server/export/pdf_basic.py ======================
#
# Quello che funziona sempre, senza rete e senza browser: e' la rete di
# sicurezza del PDF ricco.
from server.export.pdf_basic import (
    _section_heading, build_pdf,
)

# === LA TRADUZIONE: sta in server/enrichment/translation.py ==================
#
# Google Translate in nuvola oppure Ollama in locale, piu' il lavoro di
# proteggere gli anglicismi perche' non vengano tradotti alla lettera.
from server.enrichment.translation import (
    _ANGLICISMS, _ANGLICISM_RE, _ANGLICISM_TOKEN_RE, _TRANSLATE_MAX_CHARS,
    _make_translator, _protect_anglicisms, _restore_anglicisms,
    _split_for_translation, _translate_engine_label, _translate_ollama,
    _translate_text, translate_sections,
)

# === API KEY ===

# === LA CHIAVE DI GROQ: sta in server/config/groq_key.py =====================
#
# Da dove si prende, e perche' il segnaposto del file di esempio conta come
# «chiave assente» invece che come chiave sbagliata.
from server.config.groq_key import (
    _GROQ_KEY_PLACEHOLDER, load_dotenv,
)

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

# === temporaneo ==============================================================
#
# temporaneo
from server.sources.download import (
    _has_video_stream, download_video,
)

def _cli_download_video(url: str, workdir: str) -> str | None:
    """Scarica il video mostrando una barra, e gestisce il Ctrl+C.

    Come il gemello dell'audio. Si usa solo quando e' stata chiesta l'analisi
    visiva, perche' e' l'unica cosa per cui servano i fotogrammi.
    """
    progress, _task, on_progress = _download_progress("Scarico video")
    try:
        with progress:
            return download_video(url, workdir, on_progress,
                                  should_stop=fermarsi)
    except KeyboardInterrupt:
        return None
    except MediaError as e:
        console.print(f"[error]{e}[/error]")
        return None


# === L'ANALISI VISIVA: sta in server/enrichment/vision.py ====================
#
# Leggere quello che nel video si VEDE e non si sente: codice, formule,
# grafici, diagrammi. In certe lezioni e' meta' del contenuto.
from server.enrichment.vision import (
    _VISION_SYSTEM_PROMPT, _VISION_USER_PROMPT, _append_frames_to_sections,
    _audio_context_near, _check_ollama_vision, _collapse_close_frames,
    _dedup_visual_notes, _encode_image_b64, _fix_mermaid_arrows,
    _is_empty_visual, _make_vision_analyzer, _merge_visual_into_sections,
    _parse_showinfo_times, _split_md_blocks, _strip_mermaid_blocks,
    _strip_think, _vision_groq, _vision_ollama, _vision_user_prompt,
    analyze_video_visuals, extract_keyframes, load_visual_notes,
    save_visual_notes,
)

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
            if not audio_path or fermarsi():
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
                    "model": settings.GROQ_MODEL, "chunk_seconds": CHUNK_SECONDS,
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
        if do_visual and media_path and not fermarsi():
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
        """Scrive un file e lo segna fra quelli prodotti.

        Passa dalla scrittura condivisa col motore, che si occupa di due
        fastidi: i percorsi oltre i 260 caratteri, che i titoli di video lunghi
        raggiungono facilmente, e i tentativi ripetuti quando la cartella e'
        dentro OneDrive e la sincronizzazione tiene il file occupato.
        """
        write_text_file(path, content, created, video_dir)

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
        icon = "📂" if folder in (TRANS_SUBDIR, NOMI_VECCHI[TRANS_SUBDIR]) else "🌐"
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
                       do_export: bool = True,
                       local: bool = False):
    """Traduce una trascrizione GIÀ salvata (niente ri-trascrizione, nessun credito).

    Rilegge i file da out_root/<title>/, traduce le sezioni verso 'target'
    (default italiano) con Google Translate — o in locale via Ollama se
    'local=True' — e salva md/txt (+ pdf) sotto
    out_root/<title>/traduzioni/ col suffisso della lingua.
    Restituisce la LISTA delle sezioni tradotte (così il
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
    done_secs, _persist_translation = resume_sections(
        meta, "translation", len(sections), "target", target)

    safe_title = _safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe_title)
    trad_dir = os.path.join(video_dir, transl_subdir())
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
        """Scrive un file e lo segna fra quelli prodotti.

        Passa dalla scrittura condivisa col motore, che si occupa di due
        fastidi: i percorsi oltre i 260 caratteri, che i titoli di video lunghi
        raggiungono facilmente, e i tentativi ripetuti quando la cartella e'
        dentro OneDrive e la sincronizzazione tiene il file occupato.
        """
        write_text_file(path, content, created, video_dir)

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


# === RIASSUNTO: sta in server/enrichment/summary.py ==========================
#
# Erano le istruzioni che si danno al modello, in due copie: una italiana e una
# inglese, perche' il riassunto seguiva la lingua dell'interfaccia. Da quando
# il programma parla solo italiano la seconda non la raggiungeva piu' nessuno,
# quindi e' uscita insieme alla prima.
from server.enrichment import summary

# === PDF "RICCO": HTML (MathJax + Mermaid) stampato da un browser headless =====

# === IL PDF RICCO: sta in server/export/pdf_rich.py ==========================
#
# Formule e mappe disegnate davvero, stampando una pagina web con un browser
# che sul computer c'e' gia'. Se manca, si ripiega sul PDF semplice.
from server.export.pdf_rich import (
    PDF_ASSETS_DIR, _PDF_ASSET_URLS, _PDF_HTML_TEMPLATE, _ensure_pdf_assets,
    _find_browser, _md_inline_to_html, _md_to_html, _save_pdf,
    build_pdf_rich,
)

# === IL RIASSUNTO, IL LAVORO =================================================
#
# temporaneo
from server.enrichment.summary import (
    _groq_chat_capture, _make_summarizer, _summarize_groq, _summarize_long,
    _summarize_ollama, _summary_user_prompt, summarize_sections,
)


def summarize_existing(out_root: str, title: str, client=None,
                       source_sections: list[dict] | None = None,
                       do_export: bool = True) -> bool:
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
        # La traduzione salvata porta nel nome la lingua di destinazione, che è
        # quella dell'interfaccia: cercandola sempre come "_it" un utente con la
        # UI in inglese non l'avrebbe mai ritrovata, e il riassunto sarebbe stato
        # fatto sull'originale senza dirlo.
        sections = (load_existing_translation(out_root, title)
                    or _build_sections(meta, segments))
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
    done_secs, _persist_summary = resume_sections(
        meta, "summary", len(sections), "lang", "it")

    try:
        summarize_fn, engine_label = _make_summarizer(client)
    except RuntimeError as e:
        console.print(f"[warning]Riassunto non disponibile: {e}[/warning]")
        return False

    safe_title = _safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe_title)
    sum_dir = os.path.join(video_dir, summary_subdir())
    os.makedirs(_lp(sum_dir), exist_ok=True)
    suffix = SUMMARY_SUFFIX
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
    summary.PROMPT_ATTIVO = (
        summary.prompt_visivo(CONCEPT_MAP) if visual_notes else None)
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
        """Scrive un file e lo segna fra quelli prodotti.

        Passa dalla scrittura condivisa col motore, che si occupa di due
        fastidi: i percorsi oltre i 260 caratteri, che i titoli di video lunghi
        raggiungono facilmente, e i tentativi ripetuti quando la cartella e'
        dentro OneDrive e la sincronizzazione tiene il file occupato.
        """
        write_text_file(path, content, created, video_dir)

    # Fotogrammi nel riassunto: aggiungiamo i frame (per timestamp) alle sezioni.
    # Sono salvati in analisi_visiva/frames/: link RELATIVO per il .md (portabile)
    # e ASSOLUTO per il PDF (il browser deve trovarli). Costo Groq aggiuntivo: 0
    # (i frame esistono già, nessuna nuova chiamata al modello vision).
    frame_notes = [n for n in visual_notes if n.get("image")] if SUMMARY_FRAMES else []
    sections_md, sections_pdf = summarized, summarized
    if frame_notes:
        frames_dir = os.path.join(video_dir, visual_subdir(), "frames")
        rel_prefix = f"../{visual_subdir()}/frames/"
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
                 extra={"lang": "it"})
    return True


# === LA STIMA PRIMA DI PARTIRE: sta in server/services/estimate.py ===========
#
# Quanto costera' e quanto ci vorra', detto quando c'e' ancora tempo per
# cambiare idea.
from server.services.estimate import (
    GROQ_PRICE_PER_HOUR, _LOCAL_REALTIME_CPU, estimate_job,
)

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
        settings.OLLAMA_MODEL = om
        # La traduzione riusa il modello del riassunto, salvo .env esplicito.
        if not _env_str("ECHOSCRIPT_OLLAMA_TRANSLATE_MODEL", ""):
            settings.OLLAMA_TRANSLATE_MODEL = om
    else:  # groq: scelta del modello di trascrizione cloud (costo associato)
        gm = choose_groq_model()
        if not gm:
            return
        settings.GROQ_MODEL = gm

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
    al = _prompt("Lingua dell'audio", "(invio = autorileva · es. it, en, es, fr, de)",
                 accent="bright_blue").strip().lower()
    if al:
        settings.LANGUAGE = al

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
                settings.OLLAMA_VISION_MODEL = vm

    # We initialize the Groq client only if it is really needed (cloud backend),
    # and only after the user's confirmation.
    client = None
    if backend == "groq":
        client = get_groq_client()
        if not client:
            return

    # Engine label, shown in the file header and in the summary.
    engine_label = (f"Locale / faster-whisper {local_model}" if backend == "local"
                    else f"Groq / {settings.GROQ_MODEL}")

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
        if fermarsi():
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
            """Butta via il parziale giusto per questo lavoro.

        Ce ne sono due tipi, uno per Groq e uno per la trascrizione locale, e
        vanno cancellati quello che si e' usato. Cancellarli tutti e due
        sembrerebbe piu' prudente e invece butterebbe via un lavoro lasciato a
        meta' con l'altro motore, che magari si voleva riprendere.
        """
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
            v_label = (f"Groq · {settings.GROQ_VISION_MODEL}" if client is not None
                       else f"Ollama · {settings.OLLAMA_VISION_MODEL}")
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


# === LE DOMANDE A FFMPEG: stanno in server/utils/ffmpeg.py ===================
#
# Quanto dura questo file. Una domanda sola, ma la fanno in tre.
from server.utils.ffmpeg import (
    _probe_duration,
)

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
