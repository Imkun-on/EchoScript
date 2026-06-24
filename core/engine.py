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
import time
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
    dove si è fermato. Porta con sé i blocchi fatti/totali per il messaggio."""

    def __init__(self, done: int, total: int):
        self.done = done
        self.total = total
        super().__init__(
            f"Limite Groq raggiunto: trascritti {done}/{total} blocchi. "
            "Il progresso è stato salvato: riprendi questo video più tardi, "
            "quando tornano i crediti gratuiti.")


def _friendly_groq_error(e: Exception) -> str:
    """Turn a raw Groq exception into a short, user-friendly Italian message."""
    msg = str(e)
    if "429" in msg or "rate_limit" in msg or "tokens per day" in msg.lower():
        return ("limite giornaliero di token Groq raggiunto per il modello di traduzione. "
                "Riprova più tardi, oppure imposta un modello con limiti più alti "
                "(GROQ_TRANSLATE_MODEL in transcriber.py).")
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


def get_rate_limits(api_key: str | None = None, model: str | None = None) -> dict:
    """Read Groq's current rate-limit status for a chat model.

    Groq has no "balance" endpoint: the limits live in the x-ratelimit-* response
    headers of a real call. We make the smallest possible completion (1 token) and
    parse those headers. By default we probe the TRANSLATION model, since its daily
    token limit (TPD) is the one that actually blocks EchoScript's translation step.

    Returns a dict with limit/remaining/reset for both requests and tokens (values
    are strings as Groq sends them, or None if a header is absent). Raises
    EngineError with a friendly message on failure (e.g. bad key)."""
    client = make_groq_client(api_key)  # also validates the key
    model = model or tx.GROQ_TRANSLATE_MODEL
    try:
        resp = client.chat.completions.with_raw_response.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        h = resp.headers
    except Exception as e:
        raise EngineError("Impossibile leggere i limiti Groq: " + _friendly_groq_error(e))

    return {
        "model": model,
        "limit_requests": h.get("x-ratelimit-limit-requests"),
        "remaining_requests": h.get("x-ratelimit-remaining-requests"),
        "reset_requests": h.get("x-ratelimit-reset-requests"),
        "limit_tokens": h.get("x-ratelimit-limit-tokens"),
        "remaining_tokens": h.get("x-ratelimit-remaining-tokens"),
        "reset_tokens": h.get("x-ratelimit-reset-tokens"),
        "retry_after": h.get("retry-after"),
    }


# === AUDIO DOWNLOAD ===

def download_audio(url: str, workdir: str, on_progress=_noop) -> str:
    """Download only the audio track into 'workdir', reporting progress.

    Returns the path to the downloaded audio file. Raises EngineError on failure."""
    out_template = os.path.join(workdir, "audio.%(ext)s")

    def hook(d: dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            on_progress("download", done, total, "Scarico audio")
        elif d["status"] == "finished":
            on_progress("download", None, None, "Estraggo audio")

    def pp_hook(d: dict) -> None:
        if d.get("status") == "started":
            on_progress("download", None, None, "Converto audio in m4a")

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
        on_progress("prepare", idx, n_chunks, f"Blocco {idx}/{n_chunks}")
    return chunks


# === TRANSCRIPTION ===

def transcribe_groq(client, chunks: list[tuple[float, str]], on_progress=_noop,
                    start_index: int = 0, prior_segments: list | None = None,
                    prior_lang=None):
    """Transcribe chunks via Groq, con RIPRESA da 'start_index' (riusando
    'prior_segments' già fatti). Shifta i timestamp di ogni blocco.

    Returns (segments, detected_language). Se Groq rifiuta per limite, solleva
    tx.TranscriptionInterrupted col parziale (per il checkpoint)."""
    all_segments: list[dict] = list(prior_segments or [])
    context = " ".join(s["text"] for s in all_segments[-6:]) if all_segments else ""
    detected = prior_lang
    n = len(chunks)
    for i in range(start_index, n):
        offset, path = chunks[i]
        on_progress("transcribe", i, n, f"Invio blocco {i + 1}/{n} a Groq")
        try:
            if i == start_index:
                segments, lang = tx._transcribe_chunk(
                    client, path, prompt=context, return_language=True)
                detected = detected or lang
            else:
                segments = tx._transcribe_chunk(client, path, prompt=context)
        except tx.GroqRateLimit:
            # I blocchi 0..i-1 sono completati: passali a chi orchestra.
            raise tx.TranscriptionInterrupted(all_segments, i, n, detected)
        for seg in segments:
            seg["start"] += offset
            seg["end"] += offset
            all_segments.append(seg)
        if segments:
            context = " ".join(s["text"] for s in segments)
        on_progress("transcribe", i + 1, n, f"Blocco {i + 1}/{n} completato")
    return all_segments, detected


def transcribe_local(model_name: str, audio_path: str, duration: float, on_progress=_noop):
    """Transcribe the whole file locally with faster-whisper, reporting progress.

    Returns (segments, detected_language): faster-whisper rileva la lingua
    dell'audio (codice ISO tipo 'en'/'it'). Raises EngineError if faster-whisper
    is not installed or fails to load."""
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise EngineError("faster-whisper non installato. Esegui: pip install faster-whisper")

    on_progress("transcribe", None, None, f"Carico il modello '{model_name}' (primo uso: scarica i pesi)")
    try:
        model = WhisperModel(model_name, device="cpu", compute_type=tx.LOCAL_COMPUTE_TYPE)
        segments_gen, info = model.transcribe(
            audio_path, language=tx.LANGUAGE, vad_filter=True, beam_size=5,
        )
    except Exception as e:
        raise EngineError(f"Errore nella trascrizione locale: {e}")

    detected = getattr(info, "language", None)
    out: list[dict] = []
    for seg in segments_gen:
        out.append({"start": float(seg.start), "end": float(seg.end), "text": seg.text.strip()})
        if duration:
            on_progress("transcribe", min(seg.end, duration), duration, "Trascrizione in corso")
    if duration:
        on_progress("transcribe", duration, duration, "Trascrizione completata")
    return out, detected


# === TRANSLATION ===

def translate_sections(client, sections: list[dict], on_progress=_noop) -> list[dict]:
    """Translate each section's title and text into Italian via the Groq LLM."""
    out: list[dict] = []
    n = len(sections)
    for i, sec in enumerate(sections, 1):
        on_progress("translate", i - 1, n, f"Traduco sezione {i}/{n}")
        t_title = tx.translate_text_groq(client, sec["title"]) if sec["title"] else None
        t_text = tx.translate_text_groq(client, sec["text"]) if sec["text"] else ""
        out.append({"start": sec["start"], "title": t_title, "text": t_text})
        on_progress("translate", i, n, f"Sezione {i}/{n} tradotta")
    return out


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
    backend = options.get("backend", "groq")
    model = options.get("model")
    source_kind = options.get("source_kind", "youtube")

    # A Groq client is needed for cloud transcription and/or the translation step.
    client = None
    if backend == "groq" or bool(options.get("translate")):
        client = make_groq_client(options.get("api_key"))

    # Metadata: YouTube needs a network call; a local file is described synthetically.
    if source_kind == "local":
        if not os.path.isfile(source):
            raise EngineError(f"File non trovato: {source}")
        on_progress("info", None, None, "Leggo il file audio")
        meta = tx.local_file_meta(source)
    else:
        on_progress("info", None, None, "Leggo le informazioni del video")
        meta = get_video_info(source)

    engine_label = (f"Locale / faster-whisper {model}" if backend == "local"
                    else f"Groq / {tx.GROQ_MODEL}")

    # Checkpoint da cui riprendere (solo Groq, solo se richiesto).
    cp = tx.load_checkpoint(meta) if (backend == "groq" and resume) else None

    with tempfile.TemporaryDirectory(prefix="echoscript_", ignore_cleanup_errors=True) as workdir:
        if source_kind == "local":
            audio_path = source  # fed directly to ffmpeg / whisper
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
            try:
                segments, detected_lang = transcribe_groq(
                    client, chunks, on_progress, start_index, prior, prior_lang)
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
                raise RateLimitReached(ti.done, ti.total)
            # Trascrizione completa: niente più parziale da conservare.
            tx.delete_checkpoint(meta)
        else:
            segments, detected_lang = transcribe_local(model, audio_path, duration, on_progress)

    if not segments:
        raise EngineError("Nessun testo trascritto.")
    # Lingua dell'audio: quella rilevata da Whisper è autorevole; in mancanza, si
    # ripiega su quella dichiarata da YouTube. Serve alla GUI per decidere se
    # proporre la traduzione (italiano -> non serve; inglese -> sì).
    meta["detected_language"] = detected_lang or meta.get("language")
    return meta, segments, engine_label, client


def save_results(meta: dict, segments: list[dict], engine_label: str, options: dict,
                 out_root: str, client=None, on_progress=_noop) -> dict:
    """PHASE 2 — write all outputs under 'out_root', creating the subfolders.

    Layout: out_root/<title>/trascrizioni/ (+ traduzioni/ if translating). The
    chosen 'out_root' lets the user save anywhere (e.g. outside OneDrive).
    Returns the result summary dict."""
    do_translate = bool(options.get("translate"))
    do_export = bool(options.get("export"))

    safe_title = tx._safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe_title)
    trans_dir = os.path.join(video_dir, "trascrizioni")
    base_orig = os.path.join(trans_dir, safe_title)

    sections = tx._build_sections(meta, segments)
    created: list[str] = []
    warnings: list[str] = []
    on_progress("export", None, None, "Salvo i file")
    _write(f"{base_orig}.md", tx.build_md(meta["title"], meta, engine_label, sections, with_timestamps=True), created, video_dir)
    _write(f"{base_orig}.txt", tx.build_txt(meta["title"], meta, sections), created, video_dir)
    _write(f"{base_orig}.json", tx.build_transcript_json(meta, segments, engine_label), created, video_dir)

    # Optional Italian translation -> out_root/<title>/traduzioni/
    # A failure here (e.g. Groq daily token limit) must NOT lose the transcription
    # already saved above: we warn and keep going (export still runs on the original).
    it_sections = None
    it_title = None
    base_trad = None
    if do_translate and client is not None:
        try:
            it_title = tx.translate_text_groq(client, meta["title"])
            it_sections = translate_sections(client, sections, on_progress)
            if it_sections:
                base_trad = os.path.join(video_dir, "traduzioni", safe_title)
                # with_timestamps=True: la traduzione esce nello STESSO formato
                # della trascrizione (sezioni/capitoli con minutaggio nel titolo).
                _write(f"{base_trad}.md", tx.build_md(it_title, meta, f"{engine_label} (tradotto in italiano)",
                                                      it_sections, with_timestamps=True), created, video_dir)
                _write(f"{base_trad}.txt", tx.build_txt(it_title, meta, it_sections), created, video_dir)
        except Exception as e:
            it_sections = None  # so the export step below skips the translated version
            warnings.append("Traduzione non riuscita: " + _friendly_groq_error(e))

    # Optional PDF export (original and, if present, translated).
    # NB: il PDF è prodotto direttamente con fpdf2 (build_pdf), indipendente dal
    # LaTeX; per la GUI non generiamo più il .tex (ridondante per lo scopo).
    if do_export:
        exports = [(meta["title"], sections, True, base_orig)]
        if it_sections and base_trad:
            # ts=True: PDF tradotto con sezioni + minutaggio, come l'originale.
            exports.append((it_title, it_sections, True, base_trad))
        for title, secs, ts, base_path in exports:
            on_progress("export", None, None, "Creo il PDF")
            for attempt in (1, 2):  # defensive dir-ensure + single retry (OneDrive)
                try:
                    _ensure_dir(f"{base_path}.pdf")
                    tx.build_pdf(title, meta, secs, f"{base_path}.pdf", with_timestamps=ts)
                    created.append(os.path.relpath(f"{base_path}.pdf", video_dir).replace("\\", "/"))
                    break
                except OSError:
                    if attempt == 2:
                        raise
                    time.sleep(0.4)

    n_words = sum(len(s["text"].split()) for s in segments)
    return {
        "title": meta["title"],
        "video_dir": video_dir,
        "files": created,
        "segments": len(segments),
        "words": n_words,
        "sections": len(meta["chapters"]) or 0,
        "engine_label": engine_label,
        "warnings": warnings,
    }


def translate_existing(out_root: str, title: str, client, on_progress=_noop) -> dict:
    """SOLA ri-traduzione: rilegge la trascrizione già salvata e rigenera SOLO i
    file di traduzione (md/txt/pdf), SENZA ri-trascrivere né toccare gli originali.

    Riusa i segmenti dal .json esistente, quindi non spende crediti di
    trascrizione. Restituisce il dict di riepilogo; solleva EngineError se non
    trova la trascrizione o se la traduzione fallisce."""
    loaded = tx.load_existing_transcript(out_root, title)
    if not loaded:
        raise EngineError("Trascrizione esistente non trovata o illeggibile.")
    meta, segments, engine_label = loaded
    safe_title = tx._safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe_title)
    sections = tx._build_sections(meta, segments)
    created: list[str] = []

    try:
        it_title = tx.translate_text_groq(client, meta["title"])
        it_sections = translate_sections(client, sections, on_progress)
    except Exception as e:
        raise EngineError("Traduzione non riuscita: " + _friendly_groq_error(e))
    if not it_sections:
        raise EngineError("La traduzione è risultata vuota.")

    base_trad = os.path.join(video_dir, "traduzioni", safe_title)
    on_progress("export", None, None, "Salvo la traduzione")
    _write(f"{base_trad}.md", tx.build_md(it_title, meta, f"{engine_label} (tradotto in italiano)",
                                          it_sections, with_timestamps=True), created, video_dir)
    _write(f"{base_trad}.txt", tx.build_txt(it_title, meta, it_sections), created, video_dir)
    for attempt in (1, 2):
        try:
            _ensure_dir(f"{base_trad}.pdf")
            tx.build_pdf(it_title, meta, it_sections, f"{base_trad}.pdf", with_timestamps=True)
            created.append(os.path.relpath(f"{base_trad}.pdf", video_dir).replace("\\", "/"))
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(0.4)

    n_words = sum(len(s["text"].split()) for s in segments)
    return {
        "title": meta["title"], "video_dir": video_dir, "files": created,
        "segments": len(segments), "words": n_words,
        "sections": len(meta["chapters"]) or 0, "engine_label": engine_label,
        "warnings": [],
    }


def process(url: str, options: dict, on_progress=_noop, out_root: str = RESULTS_DIR) -> dict:
    """Convenience: run BOTH phases in one go (used by tests / non-interactive).

    The GUI instead calls transcribe_only() and then save_results() so it can
    ask the user where to save in between."""
    meta, segments, engine_label, client = transcribe_only(url, options, on_progress)
    return save_results(meta, segments, engine_label, options, out_root, client, on_progress)
