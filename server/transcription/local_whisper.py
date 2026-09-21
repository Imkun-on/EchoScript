"""Trascrivere sul computer di chi usa il programma, senza mandare niente fuori.

Cosa cambia rispetto a Groq
    Non serve nessuna chiave, non si consuma niente, e soprattutto l'audio non
    esce di casa. In cambio ci vuole piu' tempo, e la prima volta bisogna
    scaricare il modello, che pesa da qualche centinaio di megabyte a qualche
    gigabyte a seconda di quanto lo si vuole accurato.

    Non c'e' nemmeno bisogno di tagliare l'audio in blocchi: il modello legge
    il file intero e riferisce mentre avanza.

La scheda grafica, se c'e'
    Su una scheda NVIDIA il lavoro va dalle cinque alle venti volte piu'
    veloce. Ma riconoscerla non e' scontato: puo' esserci la scheda e mancare
    la libreria, o esserci tutto e non bastare la memoria. Per questo la
    scelta viene fatta provando e non dichiarando, e se qualcosa non va si
    ripiega sul processore invece di fermarsi.
"""
from __future__ import annotations

import os

from server.config import settings
from server.config.messages import msg
from server.config.settings import (
    _USE_CONFIG, LOCAL_COMPUTE_TYPE, LOCAL_DEVICE, WORD_TIMESTAMPS,
)
from server.state.checkpoints import (
    LOCAL_CHECKPOINT_EVERY, _local_resume_point, _trim_audio,
    delete_local_checkpoint, save_local_checkpoint,
)
from server.utils.console import console
from server.utils.contract import MediaError, _never_stop, _noop_progress
from server.utils.ffmpeg import _probe_duration
from server.utils.text import _format_timestamp


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
                     resume_cp: dict | None = None, workdir: str | None = None):
    """Transcribe the entire audio LOCALLY with faster-whisper (no data over the network).

    Returns (segments, detected_language). Solleva MediaError se il modello non
    si carica o la trascrizione fallisce.

    Unlike Groq, no splitting is needed: faster-whisper processes the whole file
    and returns the segments incrementally (a generator), so progress can be
    reported as we go: `on_progress` riceve il secondo di audio raggiunto sul
    totale della durata.

    'language' forza la lingua dell'audio; il default `_USE_CONFIG` significa
    "usa settings.LANGUAGE dalla configurazione" (None sarebbe ambiguo: vale già
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
        language = settings.LANGUAGE

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
    note = msg("resume_from", ts=_format_timestamp(start_offset)) if start_offset > 0 else ""
    on_progress("transcribe", None, None,
                msg("model_load", model=model_name, dev=dev_note, note=note))
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
            on_progress("transcribe", min(abs_end, duration), duration, msg("transcribing"))
        # Periodic checkpoint, so an interruption loses at most a couple of minutes.
        if meta and (abs_end - last_saved) >= LOCAL_CHECKPOINT_EVERY:
            save_local_checkpoint(meta, all_segments, abs_end, model_name, duration, detected)
            last_saved = abs_end
    if duration and completed_fully:
        on_progress("transcribe", duration, duration, msg("transcribed"))

    # Done -> drop the checkpoint; interrupted -> keep the latest partial to resume.
    if meta:
        if completed_fully:
            delete_local_checkpoint(meta)
        else:
            save_local_checkpoint(meta, all_segments, last_abs_end, model_name, duration, detected)
    return all_segments, detected
