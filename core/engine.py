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
                    prior_lang=None, language=None):
    """Transcribe chunks via Groq, con RIPRESA da 'start_index' (riusando
    'prior_segments' già fatti). Shifta i timestamp di ogni blocco (e le parole).

    'language' forza la lingua audio (None = autorileva). Returns (segments,
    detected_language). Se Groq rifiuta per limite, solleva
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
                    client, path, prompt=context, return_language=True, language=language)
                detected = detected or lang
            else:
                segments = tx._transcribe_chunk(client, path, prompt=context, language=language)
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
        on_progress("transcribe", i + 1, n, f"Blocco {i + 1}/{n} completato")
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

    note = (f" (ripresa da {tx._format_timestamp(start_offset)})" if start_offset > 0 else "")
    on_progress("transcribe", None, None,
                f"Carico il modello '{model_name}' su {dev_note}{note} (primo uso: scarica i pesi)")
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
            on_progress("transcribe", min(abs_end, duration), duration, "Trascrizione in corso")
        if meta and (abs_end - last_saved) >= tx.LOCAL_CHECKPOINT_EVERY:
            tx.save_local_checkpoint(meta, out, abs_end, model_name, duration, detected)
            last_saved = abs_end
    if duration:
        on_progress("transcribe", duration, duration, "Trascrizione completata")
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
        on_progress("info", None, None, "Leggo il file audio")
        meta = tx.local_file_meta(source)
    else:
        on_progress("info", None, None, "Leggo le informazioni del video")
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
                    client, chunks, on_progress, start_index, prior, prior_lang,
                    language=audio_lang)
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
    source_kind = options.get("source_kind", "youtube")
    model = options.get("model") or "small"
    audio_lang = options.get("audio_lang") or tx.LANGUAGE

    # Metadati: servono a ritrovare il checkpoint (chiave) e a conoscere la durata.
    if source_kind == "local":
        if not os.path.isfile(source):
            raise EngineError(f"File non trovato: {source}")
        on_progress("info", None, None, "Leggo il file audio")
        meta = tx.local_file_meta(source)
    else:
        on_progress("info", None, None, "Leggo le informazioni del video")
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


def save_results(meta: dict, segments: list[dict], engine_label: str, options: dict,
                 out_root: str, client=None, on_progress=_noop) -> dict:
    """PHASE 2 — write all outputs under 'out_root', creating the subfolders.

    Layout: out_root/<title>/trascrizioni/ (md, txt, json, + pdf if exporting).
    The chosen 'out_root' lets the user save anywhere (e.g. outside OneDrive).
    The 'client' argument (the Groq transcription client) is accepted for
    backward compatibility but unused here. Returns the result dict."""
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

    # Optional PDF export of the transcription.
    if do_export:
        on_progress("export", None, None, "Creo il PDF")
        for attempt in (1, 2):  # defensive dir-ensure + single retry (OneDrive)
            try:
                _ensure_dir(f"{base_orig}.pdf")
                tx.build_pdf(meta["title"], meta, sections, f"{base_orig}.pdf", with_timestamps=True)
                created.append(os.path.relpath(f"{base_orig}.pdf", video_dir).replace("\\", "/"))
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


def process(url: str, options: dict, on_progress=_noop, out_root: str = RESULTS_DIR) -> dict:
    """Convenience: run BOTH phases in one go (used by tests / non-interactive).

    The GUI instead calls transcribe_only() and then save_results() so it can
    ask the user where to save in between."""
    meta, segments, engine_label, client = transcribe_only(url, options, on_progress)
    return save_results(meta, segments, engine_label, options, out_root, client, on_progress)
