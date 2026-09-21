"""Dalla trascrizione al documento: markdown, testo semplice, json.

Cosa cambia fra i tre
    Non il contenuto, ma a chi sono destinati. Il markdown e' per leggere: ha i
    titoli, i tempi cliccabili, l'intestazione con i dati del video. Il testo
    semplice e' per chi deve copiarlo altrove senza portarsi dietro la
    formattazione. Il json e' per le macchine: un altro programma, o un altro
    modello, che deve rimettere le mani su questo materiale.

Le sezioni
    Il parlato non arriva a paragrafi: arriva a frammenti di pochi secondi, con
    l'ora di inizio. Raggrupparli in sezioni con un titolo e' la differenza fra
    un muro di testo e qualcosa che si legge, ed e' il lavoro che fa
    ``_build_sections``.

Non stampa niente, di proposito
    Queste funzioni ricevono dei dati e restituiscono del testo. Non sanno se
    qualcuno le sta guardando, e per questo funzionano uguale dalla riga di
    comando e da dentro una finestra.
"""
from __future__ import annotations

import json
import os
import re

from server.utils.media import _is_local
from server.utils.text import (
    _format_duration, _format_timestamp, _format_upload_date, _format_views,
    _safe_filename,
)


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


def _md_header(title: str, meta: dict, engine_label: str,
               saved_in: str | None = None) -> list[str]:
    """Markdown header lines (metadata) shared between original and translated.

    Local files have no channel/views/date, so we show the source path instead.
    'saved_in' (se passato) aggiunge la riga «Salvato in:» col percorso della
    cartella di output, subito dopo «Trascritto con:» (usata nei PDF)."""
    saved_line = [f"- **Salvato in:** {saved_in}"] if saved_in else []
    if _is_local(meta):
        return [
            f"# {title}", "",
            "- **Sorgente:** File audio locale",
            f"- **File:** {meta['webpage_url']}",
            f"- **Durata:** {_format_duration(meta['duration'])}",
            f"- **Trascritto con:** {engine_label}",
            *saved_line,
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
        *saved_line,
        "", "---", "",
    ]


def build_md(title: str, meta: dict, engine_label: str, sections: list[dict],
             with_timestamps: bool = True, saved_in: str | None = None) -> str:
    """Markdown document: header + sections.

    The timings (if with_timestamps) appear ONLY in the section titles
    (## [HH:MM:SS] Title); the body is flowing prose, tidier. The translated
    version passes with_timestamps=False (no timings). 'saved_in' (usato dai PDF)
    aggiunge la riga «Salvato in:» col percorso di output nell'intestazione."""
    lines = _md_header(title, meta, engine_label, saved_in=saved_in)
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


def _strip_md_bold(text: str) -> str:
    """Toglie i marcatori **grassetto** del Markdown, lasciando il testo nudo.

    Serve al .txt del riassunto: il grassetto è utile a video/PDF, ma nel testo
    semplice gli asterischi sarebbero solo rumore."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def build_txt(title: str, meta: dict, sections: list[dict],
              markdown: bool = False) -> str:
    """Clean TXT version (for other LLMs): no timings, sections as [Title].

    Con 'markdown=True' (riassunto) il testo può contenere **grassetto**: viene
    ripulito dai marcatori per restare testo piano."""
    def _plain(s: str) -> str:
        return _strip_md_bold(s) if (markdown and s) else s
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
            lines.append(f"[{_plain(sec['title'])}]")
        if sec["text"]:
            lines.append(_plain(sec["text"]))
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
