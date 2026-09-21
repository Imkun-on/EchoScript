"""Cos'e' questa cosa che mi hanno dato: titolo, durata, copertina.

Il primo passo di ogni lavoro
    Prima di scaricare un solo byte, il programma guarda cosa c'e' dietro un
    link o dentro un file: come si chiama, quanto dura, di che canale e',
    quando e' stato pubblicato. Serve a due cose che contano piu' di quanto
    sembri.

    La prima e' poter chiedere conferma. Un link incollato male porta a un
    video sbagliato, e accorgersene DOPO mezz'ora di trascrizione, con i
    crediti gia' spesi, e' il modo peggiore di scoprirlo. Con la copertina e il
    titolo davanti, l'errore si vede in un secondo.

    La seconda e' la durata, che e' l'unico numero da cui si possa stimare
    quanto costera' e quanto ci vorra'.

Due sorgenti, la stessa risposta
    Un video di YouTube e un file sul disco sono cose diverse, ma il resto del
    programma non deve accorgersene: tutt'e due finiscono in un dizionario
    fatto allo stesso modo. Da li' in poi nessuno chiede piu' da dove venisse.
"""
from __future__ import annotations

import json
import os
import subprocess

import yt_dlp

from server.config import settings
from server.config.messages import msg
from server.utils.contract import MediaError, _noop_progress
from server.utils.ffmpeg import _probe_duration
from server.utils.media import _lang_name
from server.utils.text import _format_duration, _safe_filename


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
    metadati di ogni singolo video, legge soltanto l'elenco, quindi è veloce
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
