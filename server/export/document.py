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
import re

from server.utils.media import _is_local
from server.utils.text import (
    _format_duration, _format_timestamp, _format_upload_date, _format_views
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


def _md_header(title: str, meta: dict, engine_label: str) -> list[str]:
    """Markdown header lines (metadata) shared between original and translated.

    Local files have no channel/views/date, so we show the source path instead.

    Qui dentro c'era anche una riga «Salvato in:» col percorso della cartella,
    stampata solo nei PDF. E' stata tolta: in un documento che si legge, o che
    si manda a qualcun altro, il percorso di una cartella sul computer di chi
    l'ha prodotto non serve a niente e occupa due righe in cima alla prima
    pagina. Dove sia salvato il file lo dice gia' la finestra dei risultati, a
    chi in quel momento la cosa interessa davvero.
    """
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


def _strip_md_bold(text: str) -> str:
    """Toglie i marcatori **grassetto** e *corsivo* del Markdown, lasciando il
    testo nudo.

    Serve al .txt del riassunto: il grassetto è utile a video/PDF, ma nel testo
    semplice gli asterischi sarebbero solo rumore. Il corsivo va tolto DOPO, e
    non prima, perché si scrive con un asterisco solo e il grassetto con due:
    cercandolo per primo si mangerebbe metà di ogni grassetto."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", text)


def grafico_in_testo(righe: list[str]) -> list[str]:
    """Un grafico Mermaid detto a parole, per chi non lo puo' disegnare.

    Il file di testo e il PDF di ripiego non sanno disegnare niente: lasciato
    com'e', un grafico diventerebbe «xychart-beta», «x-axis [...]» e una fila
    di numeri fra parentesi, cioe' sintassi. Qui diventa quello che il grafico
    dice: il titolo, e una riga per ogni voce col suo valore.

    Se il blocco non si riesce a leggere non si restituisce niente: il testo
    intorno spiega gia' gli stessi dati, perche' le istruzioni del riassunto lo
    chiedono.
    """
    testa = (righe[0] if righe else "").strip()
    fuori: list[str] = []
    if testa.startswith("pie"):
        titolo = re.sub(r"^pie\s*(showData\s*)?(title\s*)?", "", testa).strip()
        fuori.append(f"Grafico: {titolo}" if titolo else "Grafico:")
        for r in righe[1:]:
            m = re.match(r'^"([^"]+)"\s*:\s*(\S+)$', r.strip())
            if m:
                fuori.append(f"- {m.group(1)}: {m.group(2)}")
    elif testa.startswith("xychart"):
        titolo, etichette, unita, serie = "", [], "", []
        for r in righe[1:]:
            r = r.strip()
            if r.startswith("title"):
                titolo = r[5:].strip().strip('"')
            elif r.startswith("x-axis"):
                dentro = re.search(r"\[(.*)\]", r)
                if dentro:
                    etichette = [e.strip().strip('"') for e in dentro.group(1).split(",")]
            elif r.startswith("y-axis"):
                m = re.search(r'"([^"]+)"', r)
                unita = m.group(1) if m else ""
            else:
                m = re.match(r"^(bar|line)\b[^\[]*\[(.*)\]$", r)
                if m:
                    serie.append([v.strip() for v in m.group(2).split(",")])
        if not etichette or not serie:
            return []
        fuori.append(f"Grafico: {titolo}" if titolo else "Grafico:")
        coda = f" ({unita})" if unita else ""
        for i, nome in enumerate(etichette):
            valori = [s[i] for s in serie if i < len(s)]
            if valori:
                fuori.append(f"- {nome}: {' / '.join(valori)}{coda}")
    return fuori if len(fuori) > 1 else []


# I blocchi che sono un disegno e non codice: nel testo e nel Word non restano
# come sintassi, diventano poche righe che dicono che cosa c'era disegnato.
DISEGNI = ("mermaid", "piano", "spazio", "molecola", "reazione", "orbitali",
           "titolazione", "energia", "reticolo", "tavola")


def _grafico_a_parole(tipo: str, righe: list[str]) -> list[str]:
    """Un grafico (mermaid) o un piano cartesiano detto a parole."""
    if tipo in ("reazione", "orbitali", "titolazione", "energia", "reticolo", "tavola"):
        from server.export import chimica
        return chimica.in_testo(tipo, "\n".join(righe))
    if tipo == "piano":
        from server.export import piano
        return piano.in_testo("\n".join(righe))
    if tipo == "spazio":
        from server.export import spazio
        return spazio.in_testo("\n".join(righe))
    if tipo == "molecola":
        from server.export import molecola
        return molecola.in_testo("\n".join(righe))
    return grafico_in_testo(righe)


def appiattisci_markdown(text: str, grassetto: bool = False) -> str:
    """Toglie dal riassunto i segni di markdown che chi legge non deve vedere.

    A che cosa serve
        Il riassunto arriva scritto in markdown, perche' e' quello che il PDF
        «ricco» sa disegnare: i cancelletti diventano titoli, i tre apici
        diventano il riquadro grigio del codice. Ma gli altri due formati, il
        file di testo e il PDF di ripiego, disegnano testo e basta: li' quei
        segni restano a vista, e si legge «#### Elettroliti forti e deboli»
        con i cancelletti davanti, che e' esattamente il difetto che questa
        funzione esiste per togliere.

    Che cosa fa, in concreto
        Il titolo perde i cancelletti e resta il suo testo, che e' l'unica cosa
        che interessa a chi legge. Le righe dei tre apici spariscono e il
        codice in mezzo resta dov'e': senza il riquadro grigio non si perde
        niente di importante, mentre una riga di soli apici in mezzo al testo
        non vuol dire proprio nulla. I grafici invece non restano come
        sintassi: diventano un elenco di voci e valori (grafico_in_testo).

    Il grassetto, che e' l'unica differenza fra i due usi
        Il file di testo lo vuole via, perche' gli asterischi sono rumore. Il
        PDF di ripiego lo vuole tenere, perche' la libreria che lo disegna il
        grassetto lo sa fare e sarebbe un peccato buttarlo. Da qui l'unico
        interruttore di questa funzione.
    """
    if not text:
        return text
    if "```molecola" in text:
        from server.export import molecola
        molecola.prepara(text)      # tutti i nomi a OPSIN in una volta, non blocco per blocco
    righe = []
    grafico = None          # le righe di un blocco mermaid o piano, mentre lo si legge
    tipo = ""
    for riga in text.split("\n"):
        nuda = riga.strip()
        if grafico is not None:
            if nuda.startswith("```"):
                righe.extend(_grafico_a_parole(tipo, grafico))
                grafico = None
            else:
                grafico.append(nuda)
            continue
        if nuda.startswith(tuple("```" + nome for nome in DISEGNI)):
            grafico, tipo = [], nuda[3:].strip().lower()
            continue
        if nuda.startswith("```"):        # apertura o chiusura di un blocco
            continue
        m = re.match(r"^(#{1,6})\s+(.+)$", nuda)
        righe.append(m.group(2) if m else riga)
    if grafico:
        righe.extend(_grafico_a_parole(tipo, grafico))
    fuori = "\n".join(righe)
    return fuori if grassetto else _strip_md_bold(fuori)


def build_txt(title: str, meta: dict, sections: list[dict],
              markdown: bool = False) -> str:
    """Clean TXT version (for other LLMs): no timings, sections as [Title].

    Con 'markdown=True' (riassunto) il testo può contenere **grassetto**: viene
    ripulito dai marcatori per restare testo piano."""
    def _plain(s: str) -> str:
        """Toglie i segni del markdown, che in un file di testo sono rumore.

        Il riassunto arriva scritto in markdown: i termini importanti fra doppi
        asterischi, i sottotitoli dietro ai cancelletti, il codice fra tre
        apici. In un file markdown vanno bene; in un file di testo semplice si
        vedrebbero tali e quali, che e' peggio di non averli.
        """
        return appiattisci_markdown(s) if (markdown and s) else s
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
