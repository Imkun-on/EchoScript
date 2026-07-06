# =============================================================================
#  EchoScript — shared engine (UI-agnostic)
# =============================================================================
#  This module is the headless "engine" used by BOTH the CLI (transcriber.py)
#  and the GUI (gui/app.py). It performs the heavy work — fetching video info,
#  downloading audio, splitting, transcribing (Groq or local), translating and
#  exporting — WITHOUT touching the terminal: instead of printing to the rich
#  console, it reports progress through a simple callback. This keeps the logic
#  reusable from a graphical front-end (where there is no terminal at all).
#
#  Pure, presentation-free helpers (formatters, Markdown/TXT/JSON/PDF
#  builders, the Groq translation primitive, etc.) are imported and reused from
#  transcriber.py so there is a single source of truth for the output formats.
# =============================================================================

from __future__ import annotations

import os
import sys
import json
import time
import shutil
import subprocess
import tempfile

# Make the project root importable so we can reuse transcriber.py's pure helpers.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import yt_dlp                       # audio + metadata download
import transcriber as tx           # reuse the pure helpers/builders/config

# Where all results are written (same folder the CLI uses).
RESULTS_DIR = os.path.join(_PROJECT_ROOT, "results")


class EngineError(Exception):
    """Raised for any user-facing engine failure (bad key, network, etc.).

    The message is meant to be shown directly to the user (in Italian, to match
    the app's interface)."""


class RateLimitReached(EngineError):
    """Trascrizione Groq interrotta dal limite (429 / token-al-giorno).

    Il parziale è stato salvato in un checkpoint: il video potrà riprendere da
    dove si è fermato. Porta con sé il MINUTAGGIO raggiunto (done_seconds) sul
    totale (total_seconds), oltre ai blocchi fatti/totali, per comporre un
    messaggio elegante e leggibile dall'utente."""

    def __init__(self, done: int, total: int, done_seconds: float = 0.0,
                 total_seconds: float = 0.0):
        self.done = done
        self.total = total
        self.done_seconds = done_seconds
        self.total_seconds = total_seconds
        at = tx._format_timestamp(done_seconds)
        of = tx._format_timestamp(total_seconds) if total_seconds else None
        where = f"{at} su {of}" if of else at
        super().__init__(
            "I crediti gratuiti Groq per oggi sono esauriti. La trascrizione si è "
            f"fermata a {where} ed è stata salvata automaticamente: riprendila "
            "quando i crediti tornano disponibili (di norma il giorno successivo) "
            "scegliendo «Riprendi», oppure completala subito in locale.")


def _friendly_groq_error(e: Exception) -> str:
    """Turn a raw Groq exception into a short, user-friendly Italian message."""
    msg = str(e)
    if "429" in msg or "rate_limit" in msg or "tokens per day" in msg.lower():
        return ("limite giornaliero Groq raggiunto per la trascrizione. "
                "Riprova più tardi (quando tornano i crediti gratuiti).")
    if "401" in msg or "invalid_api_key" in msg:
        return "chiave Groq non valida."
    return msg


# A progress callback has the signature:
#   on_progress(phase: str, current: float|None, total: float|None, detail: str)
# where 'phase' is one of: "info", "download", "prepare", "transcribe",
# "translate", "export"; current/total describe the bar (None = indeterminate);
# 'detail' is a short human note. A no-op default keeps every function callable
# without a callback.
def _noop(phase, current, total, detail=""):  # pragma: no cover - trivial
    pass


# --- Lingua dei messaggi del motore (avanzamento/avvisi) --------------------
# Il motore è UI-agnostico ma mostra i testi nella lingua dell'interfaccia:
# ogni operazione pubblica (transcribe_only/save_results/continue_local/
# translate_only/summary_only/resume) imposta _ENGINE_LANG da options["ui_lang"].
# I run non sono concorrenti (la GUI ne esegue uno per volta), quindi un global va
# bene. '_L' pesca dal catalogo condiviso in transcriber (fallback: italiano).
_ENGINE_LANG = "it"


def _set_engine_lang(options: dict) -> None:
    global _ENGINE_LANG
    _ENGINE_LANG = options.get("ui_lang") or "it"


def _L(key: str, **fmt) -> str:
    """Messaggio localizzato nella lingua del motore corrente (_ENGINE_LANG)."""
    return tx.msg(key, _ENGINE_LANG, **fmt)


# === VIDEO METADATA ===

def get_video_info(url: str) -> dict:
    """Fetch ONLY the video metadata (no download). Raises EngineError on failure.

    Returns the same clean dict shape used across EchoScript (title, channel,
    views, upload_date, duration, chapters, webpage_url)."""
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise EngineError(f"Impossibile leggere il video: {e}")

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
        "chapters": info.get("chapters") or [],
        "webpage_url": info.get("webpage_url", url),
        "thumbnail": _best_thumbnail(info),
        # Metadati extra mostrati nella GUI (possono mancare: restano None).
        "likes": info.get("like_count"),
        "subscribers": info.get("channel_follower_count"),
        "category": categories[0] if categories else None,
        # Lingua dichiarata da YouTube (best effort: spesso assente). La lingua
        # "vera" dall'audio viene poi rilevata da Whisper durante la trascrizione.
        "language": info.get("language"),
    }


def get_playlist_info(url: str) -> dict | None:
    """Se l'URL è una PLAYLIST YouTube, ne legge nome/canale + elenco dei video.

    Usa yt-dlp in modalità "flat" (extract_flat="in_playlist"): NON risolve i
    metadati di ogni singolo video, legge solo l'elenco — quindi è veloce anche
    con playlist lunghe. Restituisce None se l'URL NON è una playlist (video
    singolo); solleva EngineError su errore di rete/lettura. La chiave 'entries'
    è la lista degli URL dei video nell'ordine della playlist; 'title' (con
    fallback al canale) diventa il nome della sottocartella in results/."""
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "extract_flat": "in_playlist"}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise EngineError(f"Impossibile leggere la playlist: {e}")

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


# === GROQ CLIENT ===

def make_groq_client(api_key: str | None = None):
    """Create and VALIDATE a Groq client. Raises EngineError with a clear message.

    The key is taken from the argument, otherwise from GROQ_API_KEY (env or the
    .env file). The placeholder value is treated as "missing". A lightweight
    models.list() call validates the key before any real work begins."""
    tx.load_dotenv()
    key = (api_key or os.environ.get("GROQ_API_KEY", "")).strip()
    if key == tx._GROQ_KEY_PLACEHOLDER:
        key = ""
    if not key:
        raise EngineError("API key Groq mancante. Inseriscila nel campo apposito "
                          "oppure nel file .env (la generi su console.groq.com/keys).")
    try:
        from groq import Groq
        client = Groq(api_key=key)
        client.models.list()  # validation call
        return client
    except Exception as e:
        msg = str(e)
        if "401" in msg or "invalid_api_key" in msg or "Unauthorized" in msg:
            raise EngineError("Chiave Groq non valida (401). Controlla di averla copiata bene.")
        if "403" in msg:
            raise EngineError("Accesso negato da Groq (403): possibile chiave errata o rete/VPN bloccata.")
        raise EngineError(f"Impossibile contattare Groq: {e}")


# === GROQ RATE LIMITS / "CREDITS" ============================================
# Groq does not expose a "balance" endpoint: the free-tier budget is reported
# only via the x-ratelimit-* HTTP headers attached to every API response. To
# READ them without doing real work we send a ~1-second silent audio clip to the
# transcription endpoint (the same one the app uses) and parse the headers from
# the raw response. Costs ~1 second of the daily audio budget — negligible.

import re as _re
from datetime import datetime as _datetime, timedelta as _timedelta

_RESET_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}


def _parse_reset_duration(value: str | None) -> float | None:
    """Parse a Groq reset header (e.g. '2m59.56s', '986ms', '7.66s', '1h0m0s')
    into seconds. Returns None if the value is empty/unparseable."""
    if not value:
        return None
    total = 0.0
    found = False
    for num, unit in _re.findall(r"([0-9.]+)\s*(ms|s|m|h|d)", value):
        try:
            total += float(num) * _RESET_UNITS[unit]
            found = True
        except ValueError:
            pass
    return total if found else None


def _reset_clock(seconds: float | None) -> str | None:
    """Local wall-clock time (HH:MM) at which a limit resets, given a duration
    in seconds from now. None if 'seconds' is None."""
    if seconds is None:
        return None
    return (_datetime.now() + _timedelta(seconds=seconds)).strftime("%H:%M")


def _num(value: str | None) -> float | None:
    """Best-effort float() of a header value (handles ints, floats, None)."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_ratelimit_headers(headers) -> list[dict]:
    """Turn the x-ratelimit-* headers into a tidy list of limit groups.

    Each item: {kind, remaining, limit, reset_seconds, reset_clock}. 'kind' is
    one of 'audio_seconds' | 'requests' | 'tokens' (the GUI localizes the label).
    Only groups actually present in the response are returned."""
    def get(name: str):
        try:
            return headers.get(name)
        except Exception:
            return None

    items: list[dict] = []
    # Order: audio-seconds first (it's what gates transcription), then requests/tokens.
    for kind, suffix in (("audio_seconds", "audio-seconds"),
                         ("requests", "requests"),
                         ("tokens", "tokens")):
        remaining = _num(get(f"x-ratelimit-remaining-{suffix}"))
        limit = _num(get(f"x-ratelimit-limit-{suffix}"))
        reset_s = _parse_reset_duration(get(f"x-ratelimit-reset-{suffix}"))
        if remaining is None and limit is None and reset_s is None:
            continue
        items.append({
            "kind": kind,
            "remaining": remaining,
            "limit": limit,
            "reset_seconds": reset_s,
            "reset_clock": _reset_clock(reset_s),
        })
    return items


def _silent_probe_audio(workdir: str) -> str:
    """Generate a ~1s silent 16 kHz mono mp3 used only to read rate-limit headers."""
    out_path = os.path.join(workdir, "probe.mp3")
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
           f"anullsrc=r={tx.AUDIO_SAMPLE_RATE}:cl=mono", "-t", "1",
           "-b:a", tx.AUDIO_BITRATE, out_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return out_path


def fetch_groq_limits(api_key: str | None = None) -> dict:
    """Read the current Groq rate limits ("credits") for the transcription model.

    Sends a ~1-second silent clip to the audio endpoint and parses the
    x-ratelimit-* headers of the raw response. Returns
    {checked_at: 'HH:MM', items: [...], raw: {header: value}}. Raises EngineError
    on a missing/invalid key or a network failure (message ready to show)."""
    client = make_groq_client(api_key)  # validates the key, clear errors
    with tempfile.TemporaryDirectory(prefix="echoscript_lim_", ignore_cleanup_errors=True) as workdir:
        try:
            probe = _silent_probe_audio(workdir)
        except Exception as e:
            raise EngineError(f"Impossibile creare l'audio di test (serve ffmpeg): {e}")
        try:
            with open(probe, "rb") as f:
                raw = client.audio.transcriptions.with_raw_response.create(
                    file=(os.path.basename(probe), f.read()),
                    model=tx.GROQ_MODEL,
                    response_format="json",
                    temperature=0.0,
                )
            headers = raw.headers
        except Exception as e:
            msg = str(e)
            if tx._is_rate_limit(msg):
                # Già a zero: prova comunque a leggere gli header dell'errore 429.
                headers = getattr(getattr(e, "response", None), "headers", {})
            elif "401" in msg or "invalid_api_key" in msg:
                raise EngineError("Chiave Groq non valida (401).")
            else:
                raise EngineError(f"Impossibile leggere i limiti Groq: {e}")

    items = _parse_ratelimit_headers(headers)
    # Tutti gli header x-ratelimit-* grezzi (per debug / vista \"completa\").
    raw_map = {}
    try:
        for k, v in headers.items():
            if str(k).lower().startswith("x-ratelimit"):
                raw_map[str(k).lower()] = v
    except Exception:
        pass
    return {"checked_at": _datetime.now().strftime("%H:%M"),
            "items": items, "raw": raw_map}


def get_cached_credits() -> list[dict]:
    """Crediti Groq residui PER MODELLO, letti dalla cache che le richieste reali
    (trascrizione/riassunto/analisi visiva) hanno già popolato — quindi a COSTO
    ZERO: questa funzione NON contatta Groq, non consuma alcun credito.

    Restituisce una lista (vuota finché non è stata fatta almeno una chiamata
    Groq in questa sessione) ordinata trascrizione → riassunto → visiva, ognuna:
    {model, role, checked_at, items: [{kind, remaining, limit, reset_seconds,
    reset_at_iso}]}. 'reset_seconds' è ricalcolato ADESSO dal momento assoluto di
    azzeramento salvato in cache, così resta corretto anche a distanza di ore."""
    now = _datetime.now()
    # I tre modelli Groq usati dall'app, SEMPRE elencati (anche se non ancora
    # chiamati in questa sessione): così il pannello crediti mostra tutti i modelli
    # e non solo quelli già interrogati. 'used' distingue i due casi per la GUI.
    known = [
        (tx.GROQ_MODEL, "transcription", 0),
        (tx.GROQ_SUMMARY_MODEL, "summary", 1),
        (tx.GROQ_VISION_MODEL, "vision", 2),
    ]
    known_models = {m for m, _, _ in known}
    cache_by_model = {snap.get("model", ""): snap for snap in tx.cached_rate_limits()}

    def _items_from(snap: dict) -> list[dict]:
        items: list[dict] = []
        for it in snap.get("items", []):
            rem_s = None
            if it.get("reset_at_iso"):
                try:
                    reset_at = _datetime.fromisoformat(it["reset_at_iso"])
                    rem_s = max(0.0, (reset_at - now).total_seconds())
                except Exception:
                    rem_s = None
            # 'used' = crediti consumati = limite - rimanenti (quando entrambi noti).
            rem, lim = it.get("remaining"), it.get("limit")
            used_val = (lim - rem) if (rem is not None and lim is not None) else None
            items.append({
                "kind": it.get("kind"),
                "remaining": rem,
                "limit": lim,
                "used": used_val,
                "reset_seconds": rem_s,
                "reset_at_iso": it.get("reset_at_iso"),
            })
        return items

    def _checked(snap: dict) -> str:
        try:
            return _datetime.fromisoformat(snap["checked_at_iso"]).strftime("%H:%M")
        except Exception:
            return now.strftime("%H:%M")

    out: list[dict] = []
    for model, role, order in known:
        snap = cache_by_model.get(model)
        out.append({
            "model": model, "role": role, "_order": order,
            "used": bool(snap),
            "checked_at": _checked(snap) if snap else None,
            "items": _items_from(snap) if snap else [],
        })
    # Eventuali altri modelli in cache non fra i tre noti (raro): in coda.
    for model, snap in cache_by_model.items():
        if model in known_models:
            continue
        out.append({"model": model, "role": "other", "_order": 9, "used": True,
                    "checked_at": _checked(snap), "items": _items_from(snap)})
    out.sort(key=lambda d: d.get("_order", 9))
    return out


# === AUDIO DOWNLOAD ===

def download_audio(url: str, workdir: str, on_progress=_noop) -> str:
    """Download only the audio track into 'workdir', reporting progress.

    Returns the path to the downloaded audio file. Raises EngineError on failure."""
    out_template = os.path.join(workdir, "audio.%(ext)s")

    def hook(d: dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            on_progress("download", done, total, _L("dl_audio"))
        elif d["status"] == "finished":
            on_progress("download", None, None, _L("extract_audio"))

    def pp_hook(d: dict) -> None:
        if d.get("status") == "started":
            on_progress("download", None, None, _L("convert_audio"))

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise EngineError(f"Errore nel download audio: {e}")

    for fname in os.listdir(workdir):
        if fname.startswith("audio."):
            return os.path.join(workdir, fname)
    raise EngineError("File audio non trovato dopo il download.")


def download_video(url: str, workdir: str, on_progress=_noop) -> str:
    """Scarica il VIDEO (a risoluzione contenuta) per l'analisi visiva.

    A differenza di download_audio, qui serve l'immagine: da questo unico file si
    estraggono SIA i fotogrammi SIA l'audio per la trascrizione. Restituisce il
    percorso del video. Raises EngineError on failure."""
    out_template = os.path.join(workdir, "video.%(ext)s")

    def hook(d: dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            on_progress("download", done, total, _L("dl_video"))
        elif d["status"] == "finished":
            on_progress("download", None, None, _L("prep_video"))

    h = tx.VISION_YT_MAX_HEIGHT
    ydl_opts = {
        "format": f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best",
        "merge_output_format": "mp4",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise EngineError(f"Errore nel download video: {e}")

    for fname in os.listdir(workdir):
        if fname.startswith("video."):
            return os.path.join(workdir, fname)
    raise EngineError("File video non trovato dopo il download.")


# === AUDIO SPLITTING (Groq only) ===

def split_audio(audio_path: str, duration: float, workdir: str, on_progress=_noop) -> list[tuple[float, str]]:
    """Split the audio into ~CHUNK_SECONDS chunks (16 kHz mono), reporting progress.

    Returns a list of (offset_seconds, chunk_path) pairs."""
    chunks: list[tuple[float, str]] = []
    n_chunks = max(1, int((duration + tx.CHUNK_SECONDS - 1) // tx.CHUNK_SECONDS)) if duration else 1
    start = 0.0
    idx = 0
    while start < duration:
        out_path = os.path.join(workdir, f"chunk_{idx:03d}.mp3")
        cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(tx.CHUNK_SECONDS),
               "-i", audio_path, "-ac", "1", "-ar", str(tx.AUDIO_SAMPLE_RATE),
               "-b:a", tx.AUDIO_BITRATE, out_path]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        chunks.append((start, out_path))
        start += tx.CHUNK_SECONDS
        idx += 1
        on_progress("prepare", idx, n_chunks, _L("chunk_prep", i=idx, n=n_chunks))
    return chunks


# === TRANSCRIPTION ===

def transcribe_groq(client, chunks: list[tuple[float, str]], on_progress=_noop,
                    start_index: int = 0, prior_segments: list | None = None,
                    prior_lang=None, language=None, usage_out: dict | None = None):
    """Transcribe chunks via Groq, con RIPRESA da 'start_index' (riusando
    'prior_segments' già fatti). Shifta i timestamp di ogni blocco (e le parole).

    'language' forza la lingua audio (None = autorileva). Se 'usage_out' è un
    dict, viene riempito con i limiti Groq letti dagli header dell'ULTIMO blocco
    (usage_out['items'] = lista di gruppi limite) per mostrare i crediti residui.
    Returns (segments, detected_language). Se Groq rifiuta per limite, solleva
    tx.TranscriptionInterrupted col parziale (per il checkpoint)."""
    all_segments: list[dict] = list(prior_segments or [])
    context = " ".join(s["text"] for s in all_segments[-6:]) if all_segments else ""
    detected = prior_lang
    n = len(chunks)
    # Cattura header dell'ultimo blocco (solo se al chiamante interessano i crediti).
    _hdr: dict = {}
    sink = (lambda h: _hdr.__setitem__("headers", h)) if usage_out is not None else None
    for i in range(start_index, n):
        offset, path = chunks[i]
        on_progress("transcribe", i, n, _L("chunk_send", i=i + 1, n=n))
        try:
            if i == start_index:
                segments, lang = tx._transcribe_chunk(
                    client, path, prompt=context, return_language=True,
                    language=language, on_headers=sink)
                detected = detected or lang
            else:
                segments = tx._transcribe_chunk(
                    client, path, prompt=context, language=language, on_headers=sink)
        except tx.GroqRateLimit:
            # I blocchi 0..i-1 sono completati: passali a chi orchestra.
            raise tx.TranscriptionInterrupted(all_segments, i, n, detected)
        for seg in segments:
            seg["start"] += offset
            seg["end"] += offset
            for w in seg.get("words", []):
                w["start"] += offset
                w["end"] += offset
            all_segments.append(seg)
        if segments:
            context = " ".join(s["text"] for s in segments)
        on_progress("transcribe", i + 1, n, _L("chunk_done", i=i + 1, n=n))
    # Crediti residui letti dall'ultimo blocco trascritto (best effort).
    if usage_out is not None and _hdr.get("headers") is not None:
        usage_out["items"] = _parse_ratelimit_headers(_hdr["headers"])
    return all_segments, detected


def transcribe_local(model_name: str, audio_path: str, duration: float, on_progress=_noop,
                     language=None, meta: dict | None = None,
                     resume_cp: dict | None = None, workdir: str | None = None):
    """Transcribe the whole file locally with faster-whisper, reporting progress.

    Picks GPU (CUDA) automatically when available, else CPU (see tx._resolve_device),
    and asks for per-word timestamps when WORD_TIMESTAMPS is on. 'language' forces
    the audio language (None = auto-detect).

    RESUME: if 'meta' is given, the partial result is checkpointed every
    LOCAL_CHECKPOINT_EVERY seconds of audio (so a crash/close mid-run can resume).
    If 'resume_cp' matches (and 'workdir' is available), the audio is trimmed from
    the saved point and only the remainder is transcribed, with timestamps shifted
    back. Returns (segments, detected_language). Raises EngineError on load failure."""
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise EngineError("faster-whisper non installato. Esegui: pip install faster-whisper")

    device, compute_type = tx._resolve_device()
    dev_note = "GPU (CUDA)" if device == "cuda" else "CPU"

    # Resume point (if a matching checkpoint is passed): trim and reuse prior segs.
    start_offset, out, detected = tx._local_resume_point(model_name, duration, resume_cp)
    transcribe_path = audio_path
    if start_offset > 0 and workdir:
        try:
            transcribe_path = tx._trim_audio(audio_path, start_offset, workdir)
        except Exception:
            start_offset, out, detected = 0.0, [], None
    elif start_offset > 0:
        start_offset, out, detected = 0.0, [], None  # cannot trim without a workdir

    note = (_L("resume_from", ts=tx._format_timestamp(start_offset)) if start_offset > 0 else "")
    on_progress("transcribe", None, None,
                _L("model_load", model=model_name, dev=dev_note, note=note))
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        segments_gen, info = model.transcribe(
            transcribe_path, language=language, vad_filter=True, beam_size=5,
            word_timestamps=tx.WORD_TIMESTAMPS,
        )
    except Exception as e:
        raise EngineError(f"Errore nella trascrizione locale: {e}")

    detected = detected or getattr(info, "language", None)
    last_saved = start_offset
    for seg in segments_gen:
        abs_start, abs_end = float(seg.start) + start_offset, float(seg.end) + start_offset
        entry = {"start": abs_start, "end": abs_end, "text": seg.text.strip()}
        seg_words = getattr(seg, "words", None) or []
        if seg_words:
            entry["words"] = [
                {"word": w.word, "start": float(w.start) + start_offset,
                 "end": float(w.end) + start_offset}
                for w in seg_words if w.start is not None and w.end is not None
            ]
        out.append(entry)
        if duration:
            on_progress("transcribe", min(abs_end, duration), duration, _L("transcribing"))
        if meta and (abs_end - last_saved) >= tx.LOCAL_CHECKPOINT_EVERY:
            tx.save_local_checkpoint(meta, out, abs_end, model_name, duration, detected)
            last_saved = abs_end
    if duration:
        on_progress("transcribe", duration, duration, _L("transcribed"))
    if meta:
        tx.delete_local_checkpoint(meta)  # completed fully -> no partial to keep
    return out, detected


# === FILE HELPERS ===

def _ensure_dir(path: str) -> None:
    """Make sure the PARENT directory of 'path' exists.

    Called right before every write: on OneDrive-synced folders the directory
    can be briefly renamed/locked while syncing, which would otherwise cause a
    'No such file or directory' (Errno 2) error mid-run."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _write(path: str, content: str, created: list[str], root: str) -> None:
    """Write a UTF-8 file and record its path relative to 'root' (for the result).

    Re-ensures the parent directory exists first and retries once on a transient
    filesystem error (e.g. OneDrive touching the folder during sync)."""
    for attempt in (1, 2):
        try:
            _ensure_dir(path)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            created.append(os.path.relpath(path, root).replace("\\", "/"))
            return
        except OSError:
            if attempt == 2:
                raise
            time.sleep(0.4)  # let OneDrive finish, then retry once


# === HIGH-LEVEL ORCHESTRATION ===

def video_meta(source: str, options: dict, on_progress=_noop) -> dict:
    """Solo i metadati della sorgente (senza scaricare/trascrivere).

    Serve alla GUI per controllare PRIMA di trascrivere se il video è già stato
    trascritto o se esiste un checkpoint parziale."""
    if options.get("source_kind", "youtube") == "local":
        if not os.path.isfile(source):
            raise EngineError(f"File non trovato: {source}")
        return tx.local_file_meta(source)
    return get_video_info(source)


def transcribe_only(source: str, options: dict, on_progress=_noop, resume: bool = False):
    """PHASE 1 — download/read + transcribe ONE source, returning data IN MEMORY.

    'source' is a YouTube URL or, when options["source_kind"] == "local", the
    path of a local audio/video file. Local files skip the download phase.

    Con backend Groq supporta la RIPRESA: se 'resume' è True e c'è un checkpoint
    del video, riparte dal blocco salvato; se il limite Groq viene raggiunto,
    salva/aggiorna il checkpoint e solleva RateLimitReached. A trascrizione
    completa il checkpoint viene rimosso.

    Returns (meta, segments, engine_label, client)."""
    _set_engine_lang(options)
    # Modello di trascrizione Groq scelto dall'utente (GUI): diventa quello attivo
    # per l'intera lavorazione, così API call, etichette e checkpoint lo usano.
    if options.get("groq_model"):
        tx.GROQ_MODEL = options["groq_model"]
    backend = options.get("backend", "groq")
    model = options.get("model")
    source_kind = options.get("source_kind", "youtube")
    # Forced audio language (None = auto-detect); explicit option wins over .env.
    audio_lang = options.get("audio_lang") or tx.LANGUAGE

    # A Groq client is needed only for cloud transcription.
    client = None
    if backend == "groq":
        client = make_groq_client(options.get("api_key"))

    # Metadata: YouTube needs a network call; a local file is described synthetically.
    if source_kind == "local":
        if not os.path.isfile(source):
            raise EngineError(f"File non trovato: {source}")
        on_progress("info", None, None, _L("read_audio"))
        meta = tx.local_file_meta(source)
    else:
        on_progress("info", None, None, _L("read_info"))
        meta = get_video_info(source)

    engine_label = (f"Locale / faster-whisper {model}" if backend == "local"
                    else f"Groq / {tx.GROQ_MODEL}")

    # Checkpoint da cui riprendere (Groq a blocchi, oppure locale a tempo).
    cp = None
    local_cp = None
    if resume:
        if backend == "groq":
            cp = tx.load_checkpoint(meta)
        else:
            local_cp = tx.load_local_checkpoint(meta)

    # Analisi visiva: serve il VIDEO (non solo l'audio) e va CONSERVATO oltre il
    # workdir temporaneo, perché i fotogrammi si estraggono nella fase 2
    # (save_results). Per YouTube lo scarichiamo in una cartella che sopravvive;
    # per un file locale usiamo il file stesso. Chiavi con underscore: i builder
    # dei file non le serializzano.
    do_visual = bool(options.get("visual")) and (
        source_kind == "youtube" or tx._has_video_stream(source))
    meta["_video_path"] = None
    meta["_video_tmpdir"] = None

    with tempfile.TemporaryDirectory(prefix="echoscript_", ignore_cleanup_errors=True) as workdir:
        if source_kind == "local":
            audio_path = source  # fed directly to ffmpeg / whisper
            if do_visual:
                meta["_video_path"] = source  # il file locale resta dov'è
        elif do_visual:
            # Un solo download (video): da qui estraiamo audio e fotogrammi.
            vtmp = tempfile.mkdtemp(prefix="echoscript_vid_")
            try:
                meta["_video_path"] = download_video(source, vtmp, on_progress)
                meta["_video_tmpdir"] = vtmp
                audio_path = meta["_video_path"]
            except EngineError:
                # Video non scaricabile: ripiego su solo-audio (niente analisi visiva).
                shutil.rmtree(vtmp, ignore_errors=True)
                do_visual = False
                meta["_video_path"] = None
                audio_path = download_audio(source, workdir, on_progress)
        else:
            audio_path = download_audio(source, workdir, on_progress)
        duration = meta["duration"] or tx._probe_duration(audio_path)
        meta["duration"] = duration  # keep it consistent for the output builders
        if backend == "groq":
            chunks = split_audio(audio_path, duration, workdir, on_progress)
            # La ripresa è valida solo se i blocchi coincidono (stessa durata).
            start_index, prior, prior_lang = 0, None, None
            if cp and cp.get("total_chunks") == len(chunks):
                start_index = int(cp.get("done_chunks", 0))
                prior = cp.get("segments")
                prior_lang = cp.get("detected_language")
            groq_usage: dict = {}
            try:
                segments, detected_lang = transcribe_groq(
                    client, chunks, on_progress, start_index, prior, prior_lang,
                    language=audio_lang, usage_out=groq_usage)
            except tx.TranscriptionInterrupted as ti:
                # Limite raggiunto: salva/aggiorna il checkpoint e segnala.
                tx.save_checkpoint(meta, {
                    "title": meta["title"], "id": meta.get("id"),
                    "source": meta.get("source", source_kind),
                    "source_path": meta.get("source_path"),
                    "webpage_url": meta.get("webpage_url"),
                    "model": tx.GROQ_MODEL, "chunk_seconds": tx.CHUNK_SECONDS,
                    "total_chunks": ti.total, "done_chunks": ti.done,
                    "detected_language": ti.lang, "segments": ti.segments,
                    "duration": duration,
                })
                # Minutaggio raggiunto: i blocchi sono uniformi (CHUNK_SECONDS),
                # quindi il tempo fatto = blocchi completati × durata blocco,
                # limitato alla durata totale del video.
                done_s = ti.done * tx.CHUNK_SECONDS
                if duration:
                    done_s = min(done_s, duration)
                raise RateLimitReached(ti.done, ti.total, done_s, duration or 0.0)
            # Trascrizione completa: niente più parziale da conservare.
            tx.delete_checkpoint(meta)
            # Crediti Groq residui letti durante la trascrizione (per il riepilogo).
            # Chiave con underscore: i builder dei file non la serializzano.
            if groq_usage.get("items"):
                meta["_groq_limits"] = groq_usage["items"]
        else:
            segments, detected_lang = transcribe_local(
                model, audio_path, duration, on_progress, language=audio_lang,
                meta=meta, resume_cp=local_cp, workdir=workdir)

    if not segments:
        raise EngineError("Nessun testo trascritto.")
    # Lingua dell'audio: quella rilevata da Whisper è autorevole; in mancanza, si
    # ripiega su quella dichiarata da YouTube. Serve alla GUI per decidere se
    # proporre la traduzione (italiano -> non serve; inglese -> sì).
    meta["detected_language"] = detected_lang or meta.get("language")
    return meta, segments, engine_label, client


def continue_local_from_groq(source: str, options: dict, on_progress=_noop):
    """Completa IN LOCALE una trascrizione Groq fermata dal limite giornaliero.

    Riusa il parziale salvato nel checkpoint Groq (i blocchi già trascritti),
    riscarica/riusa l'audio, trascrive in locale (faster-whisper: GPU se c'è,
    altrimenti CPU) SOLO la parte mancante e la unisce al parziale. A fine
    lavoro rimuove ogni checkpoint del video.

    Serve al pulsante «Continua ora in locale» mostrato quando i crediti Groq si
    esauriscono. Returns (meta, segments, engine_label, None)."""
    _set_engine_lang(options)
    source_kind = options.get("source_kind", "youtube")
    model = options.get("model") or "small"
    audio_lang = options.get("audio_lang") or tx.LANGUAGE

    # Metadati: servono a ritrovare il checkpoint (chiave) e a conoscere la durata.
    if source_kind == "local":
        if not os.path.isfile(source):
            raise EngineError(f"File non trovato: {source}")
        on_progress("info", None, None, _L("read_audio"))
        meta = tx.local_file_meta(source)
    else:
        on_progress("info", None, None, _L("read_info"))
        meta = get_video_info(source)

    cp = tx.load_checkpoint(meta)
    if not cp:
        raise EngineError("Nessun parziale Groq da completare per questo video.")

    duration = cp.get("duration") or meta.get("duration") or 0.0
    meta["duration"] = duration
    chunk_seconds = cp.get("chunk_seconds") or tx.CHUNK_SECONDS
    done_seconds = int(cp.get("done_chunks", 0)) * chunk_seconds
    if duration:
        done_seconds = min(done_seconds, duration)

    # Checkpoint "locale" sintetico costruito dal parziale Groq: stesso modello e
    # stessa durata, così _local_resume_point lo accetta, riusa i segmenti già
    # fatti e riparte esattamente dal minuto in cui Groq si era fermato.
    local_cp = {
        "model": model,
        "done_seconds": done_seconds,
        "duration": duration,
        "detected_language": cp.get("detected_language"),
        "segments": list(cp.get("segments") or []),
    }
    engine_label = f"Groq + Locale / faster-whisper {model}"

    with tempfile.TemporaryDirectory(prefix="echoscript_", ignore_cleanup_errors=True) as workdir:
        if source_kind == "local":
            audio_path = source
        else:
            audio_path = download_audio(source, workdir, on_progress)
        if not duration:
            duration = tx._probe_duration(audio_path)
            meta["duration"] = duration
            local_cp["duration"] = duration
        segments, detected = transcribe_local(
            model, audio_path, duration, on_progress, language=audio_lang,
            meta=meta, resume_cp=local_cp, workdir=workdir)

    if not segments:
        raise EngineError("Nessun testo trascritto.")
    # Completato: via ogni parziale (sia Groq sia l'eventuale locale intermedio).
    tx.delete_checkpoint(meta)
    tx.delete_local_checkpoint(meta)
    meta["detected_language"] = detected or cp.get("detected_language") or meta.get("language")
    return meta, segments, engine_label, None


# === TRANSLATION & SUMMARY (post-transcription, UI-agnostic) =================
# These mirror the CLI's translate_existing()/summarize_existing() but are
# headless: they write through _write() and report through on_progress() instead
# of printing to the rich console. Failures are turned into warnings (the
# transcription is already saved), never into a hard error.

def _translate_outputs(meta: dict, sections: list[dict], options: dict,
                       video_dir: str, created: list[str], warnings: list[str],
                       on_progress=_noop, local: bool = False) -> list[dict] | None:
    """Translate the transcription sections to Italian and write md/txt/json(+pdf).

    With 'local=True' the translation runs offline via Ollama (no Google
    Translate); otherwise it uses Google Translate. Returns the translated
    sections (so the summary can reuse them) or None if translation was
    skipped/failed. Writes under <video_dir>/<traduzioni>/ with the folder name
    following the UI language. A None return never aborts the run: a clear
    warning is appended instead."""
    # La traduzione punta alla lingua dell'INTERFACCIA: UI italiana -> italiano,
    # UI inglese -> inglese (un utente straniero vuole gli output nella sua lingua).
    target = options.get("ui_lang", "it") or "it"
    safe_title = tx._safe_filename(meta["title"])
    trad_dir = os.path.join(video_dir, tx.transl_subdir(options.get("ui_lang", "it")))
    base = os.path.join(trad_dir, f"{safe_title}_{target}")
    lang_label = tx._lang_name(target, _ENGINE_LANG) or target

    n = len(sections)
    # Resume: ricarica dallo stato le sezioni già tradotte (se una precedente
    # esecuzione si era interrotta) e riparti da lì; 'on_section' salva il
    # parziale dopo ogni sezione, così è sempre riprendibile.
    _state = tx.load_state(meta)
    _tr = (_state or {}).get("stages", {}).get("translation", {})
    done_secs = tx.stage_sections(_state, "translation")
    if _tr.get("target") and _tr.get("target") != target:
        done_secs = []
    if len(done_secs) > n:
        done_secs = done_secs[:n]

    def _persist_translation(done_list):
        tx.update_stage(meta, "translation", status=tx.STAGE_PARTIAL,
                        done=len(done_list), total=n, sections=done_list,
                        extra={"target": target})

    on_progress("translate", len(done_secs), n, _L("translating_to", lang=lang_label))
    try:
        translated = tx.translate_sections(
            sections, target, local=local,
            on_progress=lambda i, tot: on_progress("translate", i, tot,
                                                   _L("section_tr", i=i, n=tot)),
            done_sections=done_secs, on_section=_persist_translation)
    except RuntimeError as e:        # deep_translator non installato o Ollama giù
        warnings.append(_L("tr_unavail", e=e))
        return None
    except Exception as e:
        # Parziale già salvato da 'on_section': la traduzione sarà riprendibile.
        warnings.append(_L("tr_interrupted", e=e))
        return None

    engine_label = tx._translate_engine_label(target, local)
    # La versione tradotta è testo continuo, senza timestamp (più leggibile).
    _write(f"{base}.md", tx.build_md(meta["title"], meta, engine_label, translated, with_timestamps=False), created, video_dir)
    _write(f"{base}.txt", tx.build_txt(meta["title"], meta, translated), created, video_dir)
    # JSON delle sezioni tradotte: utile per ririassumere la traduzione dopo.
    _write(f"{base}.json",
           json.dumps({"target": target, "sections": translated}, ensure_ascii=False, indent=2),
           created, video_dir)
    if options.get("export"):
        try:
            _ensure_dir(f"{base}.pdf")
            if tx._save_pdf(meta, translated, f"{base}.pdf", with_timestamps=False,
                            engine_label=engine_label):
                created.append(os.path.relpath(f"{base}.pdf", video_dir).replace("\\", "/"))
        except Exception as e:
            warnings.append(_L("tr_pdf_fail", e=e))
    # Traduzione completata e salvata: fase 'done' nello stato.
    tx.update_stage(meta, "translation", status=tx.STAGE_DONE,
                    done=len(translated), total=n, sections=translated,
                    extra={"target": target})
    return translated


def _resolve_summary_client(options: dict, client):
    """Pick the chat client for the summary: the Groq transcription client if we
    have one, otherwise build one from the loaded key, otherwise None (-> Ollama).

    Reusing/recreating a Groq client lets a LOCAL-backend user with a Groq key
    still get a cloud summary instead of needing Ollama installed."""
    if client is not None:
        return client
    key = (options.get("api_key") or "").strip()
    if key:
        try:
            return make_groq_client(key)
        except EngineError:
            return None
    return None


def _summarize_outputs(meta: dict, sections: list[dict], options: dict,
                       video_dir: str, created: list[str], warnings: list[str],
                       client=None, on_progress=_noop, visual_notes=None) -> str:
    """Summarize the (Italian) sections per-section and write md/txt(+pdf).

    'sections' should already be Italian (the translation when available, else
    the original). Uses Groq when a client/key is available, else Ollama. Any
    failure becomes a warning — the transcription/translation stay saved.

    Se 'visual_notes' è dato (analisi visiva), le note vengono fuse nel testo per
    timestamp, si attiva il prompt «visivo» (codice/formule/mappe) e i FOTOGRAMMI
    vengono inseriti nel riassunto. Il PDF è quello "ricco" (formule/mappe/frame)."""
    sum_client = _resolve_summary_client(options, client)
    try:
        summarize_fn, engine_label = tx._make_summarizer(sum_client)
    except RuntimeError as e:        # né Groq né Ollama disponibili
        warnings.append(_L("sum_unavail", e=e))
        return "skipped"

    safe_title = tx._safe_filename(meta["title"])
    ui_lang = options.get("ui_lang", "it")
    sum_dir = os.path.join(video_dir, tx.summary_subdir(ui_lang))
    suffix = tx.SUMMARY_SUFFIX.get(ui_lang or "it", tx.SUMMARY_SUFFIX["it"])
    base = os.path.join(sum_dir, f"{safe_title}_{suffix}")

    # Arricchimento visivo: fonde le note nelle sezioni e attiva il prompt giusto.
    visual_notes = visual_notes or []
    if visual_notes:
        sections = tx._merge_visual_into_sections(sections, visual_notes)

    n = len(sections)
    # Resume: riparti dalle sezioni già riassunte (es. crediti Groq esauriti a
    # metà); 'on_section' salva il parziale dopo ogni sezione. Se la lingua UI è
    # cambiata dall'ultima volta, il parziale (in un'altra lingua) non si riusa.
    _sum_state = tx.load_state(meta)
    done_secs = tx.stage_sections(_sum_state, "summary")
    _sum_stage = (_sum_state or {}).get("stages", {}).get("summary", {})
    if _sum_stage.get("lang") and _sum_stage.get("lang") != (ui_lang or "it"):
        done_secs = []
    if len(done_secs) > n:
        done_secs = done_secs[:n]

    def _persist_summary(done_list):
        tx.update_stage(meta, "summary", status=tx.STAGE_PARTIAL,
                        done=len(done_list), total=n, sections=done_list,
                        extra={"lang": ui_lang or "it"})

    on_progress("summarize", len(done_secs), n, _L("summarizing"))
    # Lingua del riassunto = lingua dell'interfaccia; il prompt «visivo» (se ci
    # sono note visive) viene scelto nella stessa lingua.
    tx._SUMMARY_LANG = ui_lang or "it"
    tx._SUMMARY_PROMPT_OVERRIDE = (
        tx._summary_visual_prompt(ui_lang or "it", tx.CONCEPT_MAP) if visual_notes else None)
    try:
        summarized = tx.summarize_sections(
            sections, summarize_fn,
            on_progress=lambda i, tot: on_progress("summarize", i, tot,
                                                   _L("section_sum", i=i, n=tot)),
            done_sections=done_secs, on_section=_persist_summary)
    except Exception as e:
        # Parziale già salvato: lo stato resta 'partial' e il riassunto potrà
        # riprendere da lì (anche in locale con Ollama).
        if tx._is_rate_limit(str(e)):
            warnings.append(_L("sum_ratelimit"))
            return "partial"
        warnings.append(_L("sum_fail", e=e))
        return "error"
    finally:
        tx._SUMMARY_PROMPT_OVERRIDE = None
        tx._SUMMARY_LANG = "it"

    # Pulizia diagrammi: corregge le frecce Mermaid e, se la mappa concettuale è
    # disattivata, rimuove eventuali blocchi mermaid sfuggiti al modello.
    for sec in summarized:
        txt = tx._fix_mermaid_arrows(sec.get("text", ""))
        if not tx.CONCEPT_MAP:
            txt = tx._strip_mermaid_blocks(txt)
        sec["text"] = txt

    # Fotogrammi nel riassunto (link RELATIVI nel .md, ASSOLUTI nel PDF).
    frame_notes = [n for n in visual_notes if n.get("image")] if tx.SUMMARY_FRAMES else []
    sections_md, sections_pdf = summarized, summarized
    if frame_notes:
        frames_dir = os.path.join(video_dir, tx.visual_subdir(ui_lang), "frames")
        rel_prefix = f"../{tx.visual_subdir(ui_lang)}/frames/"
        sections_md = tx._append_frames_to_sections(summarized, frame_notes, lambda img: rel_prefix + img)
        sections_pdf = tx._append_frames_to_sections(summarized, frame_notes,
                                                    lambda img: os.path.join(frames_dir, img))

    # Il riassunto è testo pulito: niente timestamp. Il .txt resta senza immagini.
    _write(f"{base}.md", tx.build_md(meta["title"], meta, engine_label, sections_md, with_timestamps=False), created, video_dir)
    _write(f"{base}.txt", tx.build_txt(meta["title"], meta, summarized, markdown=True), created, video_dir)
    if options.get("export"):
        try:
            _ensure_dir(f"{base}.pdf")
            if tx._save_pdf(meta, sections_pdf, f"{base}.pdf", with_timestamps=False,
                            engine_label=engine_label, markdown=True):
                created.append(os.path.relpath(f"{base}.pdf", video_dir).replace("\\", "/"))
        except Exception as e:
            warnings.append(_L("sum_pdf_fail", e=e))
    # Riassunto completato e salvato: fase 'done' nello stato.
    tx.update_stage(meta, "summary", status=tx.STAGE_DONE,
                    done=len(summarized), total=len(summarized), sections=summarized,
                    extra={"lang": ui_lang or "it"})
    return "done"


def _visual_failure_reason(stats: dict, is_groq: bool, lang: str = "it") -> str:
    """Frase (per i 'warnings' mostrati in GUI) che spiega perché l'analisi visiva
    non ha prodotto note, partendo dall'esito raccolto in 'stats'. Prima questo
    caso era SILENZIOSO: restava solo una cartella 'frames' vuota. Localizzata
    nella lingua dell'interfaccia ('lang')."""
    if stats.get("unavailable"):
        return tx.msg("vis_unavail", lang, e=stats["unavailable"])
    if stats.get("rate_limited"):
        eng = tx.msg("vfr_eng_groq" if is_groq else "vfr_eng_other", lang)
        return tx.msg("vfr_ratelimit", lang, eng=eng)
    frames = stats.get("frames", 0)
    if frames == 0:
        return tx.msg("vfr_noframes", lang)
    if stats.get("errors"):
        err = stats.get("last_error") or tx.msg("vfr_unknown_err", lang)
        return tx.msg("vfr_allerrors", lang, n=frames, err=err)
    return tx.msg("vfr_notech", lang, n=frames)


def save_results(meta: dict, segments: list[dict], engine_label: str, options: dict,
                 out_root: str, client=None, on_progress=_noop) -> dict:
    """PHASE 2 — write all outputs under 'out_root', creating the subfolders.

    Layout: out_root/<title>/<trascrizioni>/ (md, txt, json, + pdf if exporting).
    The subfolder name follows the UI language passed in options["ui_lang"]
    (it -> "trascrizioni", en -> "transcriptions"), so an English user gets
    English-named folders. The chosen 'out_root' lets the user save anywhere
    (e.g. outside OneDrive). The 'client' argument (the Groq transcription
    client) is accepted for backward compatibility but unused here. Returns the
    result dict."""
    _set_engine_lang(options)
    do_export = bool(options.get("export"))

    safe_title = tx._safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe_title)
    trans_dir = os.path.join(video_dir, tx.trans_subdir(options.get("ui_lang", "it")))
    base_orig = os.path.join(trans_dir, safe_title)

    sections = tx._build_sections(meta, segments)
    created: list[str] = []
    warnings: list[str] = []
    on_progress("export", None, None, _L("saving_files"))
    _write(f"{base_orig}.md", tx.build_md(meta["title"], meta, engine_label, sections, with_timestamps=True), created, video_dir)
    _write(f"{base_orig}.txt", tx.build_txt(meta["title"], meta, sections), created, video_dir)
    _write(f"{base_orig}.json", tx.build_transcript_json(meta, segments, engine_label), created, video_dir)

    # Stato pipeline: la trascrizione è ora su disco. Registra il PIANO (quali
    # fasi erano richieste) così un futuro «Riprendi» sa cosa completare e da dove.
    _ui_lang = options.get("ui_lang", "it") or "it"
    _want_tr = bool(options.get("translate")) and not tx._is_same_language(
        meta.get("detected_language"), _ui_lang)
    _want_sum = bool(options.get("summarize"))
    _st = tx._empty_state(meta, options.get("backend", "groq"))
    _st["stages"]["transcription"]["status"] = tx.STAGE_DONE
    _st["stages"]["translation"]["status"] = tx.STAGE_PENDING if _want_tr else tx.STAGE_SKIP
    _st["stages"]["summary"]["status"] = tx.STAGE_PENDING if _want_sum else tx.STAGE_SKIP
    tx.save_state(meta, _st)

    # Optional PDF export of the transcription (PDF "ricco": formule/mappe/frame
    # renderizzati via browser headless, con ripiego automatico su fpdf2).
    if do_export:
        on_progress("export", None, None, _L("creating_pdf"))
        try:
            _ensure_dir(f"{base_orig}.pdf")
            if tx._save_pdf(meta, sections, f"{base_orig}.pdf", with_timestamps=True,
                            engine_label=engine_label):
                created.append(os.path.relpath(f"{base_orig}.pdf", video_dir).replace("\\", "/"))
        except Exception as e:
            warnings.append(_L("trans_pdf_fail", e=e))

    # --- Optional translation (to Italian) and per-section summary ---
    # The transcription is already on disk, so any failure here is a warning, not
    # a fatal error. The summary works on the ITALIAN text: the translation when
    # produced, otherwise the original (already Italian, or accepted as-is).
    # Un solo client chat per tutto il post-processing (analisi visiva, traduzione,
    # riassunto): se è None siamo offline, quindi traduzione/vision vanno in locale
    # (Ollama). Risolto solo se serve (evita una validazione Groq di rete a vuoto).
    chat_client = (_resolve_summary_client(options, client)
                   if (options.get("translate") or options.get("summarize")
                       or options.get("visual"))
                   else None)

    # --- Analisi visiva (opzionale): legge i fotogrammi del video, salva il
    # documento dedicato e fornisce le note per arricchire il riassunto ---
    visual_notes: list[dict] = []
    visual_info = None
    if options.get("visual") and not meta.get("_video_path"):
        # Richiesta ma impossibile: il video non c'era (solo audio / download
        # video fallito). Va detto, altrimenti l'utente non sa perché manca.
        warnings.append(_L("vis_skipped"))
    elif options.get("visual") and meta.get("_video_path"):
        vstats: dict = {}
        try:
            vis_label = (f"Groq · {tx.GROQ_VISION_MODEL}" if chat_client is not None
                         else f"Ollama · {tx.OLLAMA_VISION_MODEL}")
            frames_out = os.path.join(video_dir, tx.visual_subdir(options.get("ui_lang", "it")), "frames")
            with tempfile.TemporaryDirectory(prefix="echoscript_vis_", ignore_cleanup_errors=True) as vwork:
                visual_notes = tx.analyze_video_visuals(
                    meta["_video_path"], meta.get("duration") or 0.0, vwork,
                    client=chat_client, frames_out_dir=frames_out,
                    on_progress=on_progress, stats=vstats, lang=_ENGINE_LANG)
            if visual_notes:
                tx.save_visual_notes(out_root, meta, visual_notes, vis_label,
                                     do_export, options.get("ui_lang", "it"), quiet=True)
                visual_info = {
                    "count": len(visual_notes),
                    "with_image": sum(1 for n in visual_notes if n.get("image")),
                    "dir": os.path.join(video_dir, tx.visual_subdir(options.get("ui_lang", "it"))),
                }
            else:
                # Nessuna nota: spiega il MOTIVO (prima era silenzioso — cartella
                # 'frames' vuota e basta) leggendo l'esito riportato in 'vstats'.
                warnings.append(_visual_failure_reason(vstats, chat_client is not None, _ENGINE_LANG))
        except Exception as e:
            warnings.append(_L("vis_incomplete", e=e))
        finally:
            # Pulizia del video temporaneo scaricato per la visiva (caso YouTube).
            if meta.get("_video_tmpdir"):
                shutil.rmtree(meta["_video_tmpdir"], ignore_errors=True)
                meta["_video_tmpdir"] = None

    translated_sections = None
    audio_lang = meta.get("detected_language")
    if options.get("translate"):
        if tx._is_same_language(audio_lang, _ui_lang):
            # L'audio è già nella lingua dell'interfaccia: tradurre sarebbe inutile.
            _ln = tx._lang_name(_ui_lang, _ENGINE_LANG) or _ui_lang
            warnings.append(_L("audio_already", lang=_ln))
        else:
            translated_sections = _translate_outputs(
                meta, sections, options, video_dir, created, warnings,
                on_progress, local=chat_client is None)
    summary_status = None
    if options.get("summarize"):
        summary_status = _summarize_outputs(
            meta, translated_sections or sections, options, video_dir,
            created, warnings, chat_client, on_progress, visual_notes=visual_notes)

    n_words = sum(len(s["text"].split()) for s in segments)
    # Crediti Groq: secondi audio consumati da QUESTA trascrizione (≈ durata) e i
    # limiti residui letti durante il run. Solo per i run Groq cloud.
    credits = None
    if options.get("backend") == "groq":
        credits = {
            "audio_seconds_used": meta.get("duration") or 0.0,
            "limits": meta.get("_groq_limits") or [],
        }
    return {
        "title": meta["title"],
        "video_dir": video_dir,
        "files": created,
        "segments": len(segments),
        "words": n_words,
        "sections": len(meta["chapters"]) or 0,
        "engine_label": engine_label,
        "warnings": warnings,
        "credits": credits,
        "visual": visual_info,
        # 'partial' quando il riassunto si è interrotto per crediti Groq esauriti:
        # la GUI può offrire di concluderlo in locale (Ollama), dalla sezione ferma.
        "summary_status": summary_status,
    }


# === POST-PROCESS ONLY (già trascritto: solo traduzione / solo riassunto /
# riprendi) ===================================================================
# Riusano una trascrizione GIÀ salvata (nessun credito di trascrizione) e sono
# state-aware: ogni fase riparte dalla sezione in cui si era interrotta. Servono
# alle voci del menu «video già trascritto» nella GUI e restituiscono lo stesso
# tipo di dizionario di save_results(), così l'interfaccia può mostrarne l'esito.

def _load_saved_transcript(meta: dict, out_root: str):
    """Carica (disk_meta, segments, engine_label) dalla trascrizione salvata.

    Usa i metadati RICOSTRUITI dal .json per contenuti/PDF, ma tiene la lingua
    rilevata dai metadati originali se disponibile. La chiave di stato è basata
    sul titolo, quindi coincide con quella scritta durante la trascrizione."""
    existing = tx.load_existing_transcript(out_root, meta["title"])
    if not existing:
        raise EngineError("Nessuna trascrizione salvata trovata per questo video.")
    disk_meta, segments, engine_label = existing
    if meta.get("detected_language"):
        disk_meta["detected_language"] = meta["detected_language"]
    return disk_meta, segments, engine_label


def _post_result(disk_meta: dict, segments: list[dict], engine_label: str,
                 video_dir: str, created: list[str], warnings: list[str],
                 summary_status=None) -> dict:
    """Dizionario risultato per la GUI (stessa forma di save_results)."""
    return {
        "title": disk_meta["title"],
        "video_dir": video_dir,
        "files": created,
        "segments": len(segments),
        "words": sum(len(s.get("text", "").split()) for s in segments),
        "sections": len(disk_meta.get("chapters") or []) or 0,
        "engine_label": engine_label,
        "warnings": warnings,
        "credits": None,
        "visual": None,
        "summary_status": summary_status,
    }


def translate_only(meta: dict, options: dict, out_root: str, on_progress=_noop) -> dict:
    """Solo traduzione di un video già trascritto (nessun riassunto).

    Riprende una traduzione parziale se presente. Non consuma crediti di
    trascrizione; la traduzione usa Google Translate (o Ollama se offline)."""
    _set_engine_lang(options)
    disk_meta, segments, engine_label = _load_saved_transcript(meta, out_root)
    video_dir = os.path.join(out_root, tx._safe_filename(disk_meta["title"]))
    sections = tx._build_sections(disk_meta, segments)
    created, warnings = [], []
    chat_client = _resolve_summary_client(options, None)
    _translate_outputs(disk_meta, sections, options, video_dir, created, warnings,
                       on_progress, local=chat_client is None)
    return _post_result(disk_meta, segments, engine_label, video_dir, created, warnings)


def summary_only(meta: dict, options: dict, out_root: str, on_progress=_noop) -> dict:
    """Solo riassunto di un video già trascritto.

    Riassume la TRADUZIONE salvata se presente (testo italiano), altrimenti la
    trascrizione originale. Riprende un riassunto parziale se presente. Se i
    crediti Groq finiscono a metà, l'esito è 'partial' (la GUI offrirà di
    concluderlo in locale)."""
    _set_engine_lang(options)
    disk_meta, segments, engine_label = _load_saved_transcript(meta, out_root)
    video_dir = os.path.join(out_root, tx._safe_filename(disk_meta["title"]))
    sections = (tx.load_existing_translation(out_root, disk_meta["title"])
                or tx._build_sections(disk_meta, segments))
    visual_notes = tx.load_visual_notes(out_root, disk_meta["title"]) or []
    created, warnings = [], []
    chat_client = _resolve_summary_client(options, None)
    status = _summarize_outputs(disk_meta, sections, options, video_dir, created,
                                warnings, chat_client, on_progress,
                                visual_notes=visual_notes)
    return _post_result(disk_meta, segments, engine_label, video_dir, created,
                        warnings, summary_status=status)


def resume(meta: dict, options: dict, out_root: str, on_progress=_noop) -> dict:
    """Riprendi la pipeline di un video da dove si era interrotta.

    Completa, nell'ordine, le sole fasi ancora da fare (traduzione poi riassunto),
    ciascuna ripartendo dalla sezione ferma. L'esito 'summary_status' == 'partial'
    segnala che il riassunto è di nuovo incompleto (crediti Groq): la GUI potrà
    offrire di finirlo in locale."""
    _set_engine_lang(options)
    disk_meta, segments, engine_label = _load_saved_transcript(meta, out_root)
    video_dir = os.path.join(out_root, tx._safe_filename(disk_meta["title"]))
    created, warnings = [], []
    chat_client = _resolve_summary_client(options, None)
    sections = tx._build_sections(disk_meta, segments)

    state = tx.load_state(disk_meta)
    translated = None
    if tx.stage_status(state, "translation") in (tx.STAGE_PENDING, tx.STAGE_PARTIAL):
        translated = _translate_outputs(disk_meta, sections, options, video_dir,
                                        created, warnings, on_progress,
                                        local=chat_client is None)
    summary_status = None
    if tx.stage_status(tx.load_state(disk_meta), "summary") in (tx.STAGE_PENDING, tx.STAGE_PARTIAL):
        src = (translated or tx.load_existing_translation(out_root, disk_meta["title"])
               or sections)
        visual_notes = tx.load_visual_notes(out_root, disk_meta["title"]) or []
        summary_status = _summarize_outputs(disk_meta, src, options, video_dir,
                                            created, warnings, chat_client,
                                            on_progress, visual_notes=visual_notes)
    return _post_result(disk_meta, segments, engine_label, video_dir, created,
                        warnings, summary_status=summary_status)


def can_resume(meta: dict, out_root: str) -> bool:
    """True se il video ha uno stato con una fase da riprendere (per il menu GUI)."""
    disk_meta = dict(meta)
    return tx.has_resumable_state(disk_meta)


def resume_hint(meta: dict, out_root: str, lang: str = "it") -> str:
    """Testo breve «riprende da…» per il video (o "" se niente da riprendere)."""
    return tx.resume_info_text(dict(meta), lang)


def process(url: str, options: dict, on_progress=_noop, out_root: str = RESULTS_DIR) -> dict:
    """Convenience: run BOTH phases in one go (used by tests / non-interactive).

    The GUI instead calls transcribe_only() and then save_results() so it can
    ask the user where to save in between."""
    meta, segments, engine_label, client = transcribe_only(url, options, on_progress)
    return save_results(meta, segments, engine_label, options, out_root, client, on_progress)
