"""Il PDF semplice: quello che si fa sempre e non puo' fallire.

Perche' ce ne sono due
    Questo e quello "ricco". Questo disegna testo e basta, usando una libreria
    che sta dentro il pacchetto: non gli serve nient'altro, quindi funziona su
    qualunque computer, senza rete, sempre.

    Quello ricco sa disegnare le formule e le mappe, ma per farlo ha bisogno di
    un browser gia' installato e, la prima volta, di scaricare due librerie. Se
    una di quelle due cose manca, si ripiega su questo.

    E' la ragione per cui questo file esiste ed e' rimasto semplice: e' la rete
    di sicurezza dell'altro.
"""
from __future__ import annotations

import os
import re

from server.export import document
from server.utils.media import _is_local
from server.utils.text import (
    _format_duration, _format_timestamp, _format_upload_date, _lp,
    _safe_filename,
)


def _section_heading(sec: dict, with_timestamps: bool) -> str:
    """Il titolo di una sezione come si vede nel PDF.

    Tre casi, e il primo e' quello che si dimentica sempre: una trascrizione
    puo' non avere sezioni affatto, e allora il titolo non esiste e si scrive
    semplicemente «Trascrizione».

    Il minutaggio davanti al titolo si mette solo se e' stato chiesto e se
    quella sezione ne ha uno. Serve a chi legge il PDF con il video aperto di
    fianco e vuole saltare al punto giusto.
    """
    if sec["title"] is None:
        return "Trascrizione"
    if with_timestamps and sec["start"] is not None:
        return f"[{_format_timestamp(sec['start'])}] {sec['title']}"
    return sec["title"]


def build_pdf(title: str, meta: dict, sections: list[dict], out_path: str,
              with_timestamps: bool = True, markdown: bool = False,
              engine_label: str = "") -> None:
    """Create a readable PDF, divided by chapters, with fpdf2 (no LaTeX).

    Uses Windows' Arial font (TrueType) to support accents and Unicode
    characters. Large title, metadata in italics, section titles in bold and the
    body text in paragraphs. Con 'markdown=True' (riassunto) il corpo interpreta
    il **grassetto** Markdown, così le parole chiave risaltano anche nel PDF.
    Aggiunge un SOMMARIO cliccabile in testa (link interni ai capitoli) e i
    segnalibri/outline del PDF; NON stampa data, percorso o numero di pagina."""
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
    def cell(h: float, txt: str, md: bool = False) -> None:
        """Scrive un blocco di testo e va a capo, a tutta larghezza.

        Una scorciatoia con un nome corto perche' qui sotto viene chiamata una
        trentina di volte, e ogni volta servirebbero gli stessi quattro
        argomenti sempre uguali. Larghezza zero, per fpdf2, vuol dire «fino al
        margine destro».
        """
        pdf.multi_cell(0, h, txt, new_x=XPos.LMARGIN, new_y=YPos.NEXT, markdown=md)

    # Title
    pdf.set_font("Doc", "B", 18)
    cell(9, title)
    pdf.ln(1)
    # Metadata
    pdf.set_font("Doc", "I", 10)
    if _is_local(meta):
        cell(5, f"Sorgente: file locale  |  Durata: {_format_duration(meta['duration'])}")
        cell(5, meta["webpage_url"])
    else:
        cell(5, f"Canale: {meta['channel']}  |  Pubblicato: {_format_upload_date(meta['upload_date'])}"
                f"  |  Durata: {_format_duration(meta['duration'])}")
        cell(5, meta["webpage_url"])
    if engine_label:
        cell(5, f"Trascritto con: {engine_label}")
    pdf.ln(4)

    for sec in sections:
        pdf.set_font("Doc", "B", 14)
        # Ogni capitolo diventa una voce dei SEGNALIBRI/outline del PDF: è il
        # «Sommario» cliccabile nel pannello laterale del lettore, che rimanda al
        # capitolo. Nessun riquadro-indice dentro la pagina.
        if sec.get("title"):
            try:
                pdf.start_section(_section_heading(sec, with_timestamps))
            except Exception:
                pass
        cell(7, _section_heading(sec, with_timestamps))
        pdf.ln(1)
        if sec["text"]:
            pdf.set_font("Doc", "", 11)
            # Il riassunto e' scritto in markdown, ma fpdf2 sa disegnare solo il
            # grassetto: i cancelletti dei sottotitoli e i tre apici del codice
            # finirebbero stampati tali e quali. Si tolgono prima, tenendo il
            # grassetto che invece la libreria disegna davvero.
            corpo = document.appiattisci_markdown(sec["text"], grassetto=True) if markdown else sec["text"]
            cell(6, corpo, md=markdown)
        pdf.ln(3)

    pdf.output(_lp(out_path))
