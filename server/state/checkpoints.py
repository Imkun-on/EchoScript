"""I parziali: dove si era arrivati, per poter riprendere.

Il problema che risolve
    Un video di due ore diventa una quarantina di pezzi, e ogni pezzo e' una
    richiesta a Groq o un giro di macina sul computer. Se al trentesimo pezzo
    cade la rete, finiscono i crediti, o semplicemente si chiude la finestra,
    senza questi file i ventinove pezzi gia' fatti sarebbero da rifare.

    Qui invece, dopo ogni pezzo, si annota su disco a che punto si era.
    Riaprendo il programma, «Riprendi» trova quel foglietto e riparte dal
    trentesimo.

Dove finiscono
    Dentro ``results/.checkpoints``, cioe' accanto alle trascrizioni e non in
    una cartella temporanea. Il punto e' proprio che devono sopravvivere alla
    chiusura del programma: un parziale che sparisce quando si chiude la
    finestra non serve a niente, perche' e' esattamente quello il momento in
    cui serve.

Come si riconosce un video fra una sessione e l'altra
    Dal titolo, non dal suo indirizzo. Sembra meno preciso, e lo e', ma e'
    l'unica cosa che si ritrova uguale anche ricostruendo i dati da un file
    gia' salvato, dove l'indirizzo non c'e' piu'.

"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from server.config import paths
from server.config.settings import AUDIO_SAMPLE_RATE
from server.utils.text import _safe_filename

def _checkpoints_dir() -> str:
    """Cartella dedicata ai checkpoint dei video parziali.

    Sta dentro `results/` per lo stesso motivo per cui ci stanno le trascrizioni:
    se i parziali finissero altrove, «Riprendi» non troverebbe mai nulla da
    riprendere."""
    return paths.dati("results", ".checkpoints")


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
