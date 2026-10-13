"""Il documento Word: la versione che si puo' correggere.

Perche' esiste
    Il PDF si legge, ma non si tocca. Chi vuole sistemare una frase del
    riassunto, tagliare una sezione o incollarlo in una relazione ha bisogno di
    un file che il suo programma di scrittura apra e modifichi. Il .docx e'
    quello che aprono tutti: Word, LibreOffice, Google Documenti, Pages.

Perche' e' scritto a mano e non con una libreria
    Un .docx e' un archivio zip con dentro qualche file XML. Quello che serve
    qui (titoli, paragrafi, grassetto, elenchi, blocchi di codice) sta in poche
    decine di righe di XML, e scriverle a mano vuol dire non aggiungere al
    programma installato una libreria in piu', con le sue dipendenze compilate.

Cosa ci finisce dentro, e cosa no
    Il testo com'e' nel markdown: titoli, grassetto, elenchi puntati, codice in
    carattere a spaziatura fissa. Le formule restano scritte in LaTeX, in
    corsivo, perche' Word non sa disegnarle da quella forma; i grafici
    diventano l'elenco di voci e valori che hanno anche nel file di testo.
    Chi vuole vederli disegnati ha il PDF.
"""
from __future__ import annotations

import re
import zipfile
from xml.sax.saxutils import escape

from server.export import document
from server.utils.text import _lp

_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')

_TIPI = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

_RELAZIONI = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_RELAZIONI_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _stile(sid: str, nome: str, ppr: str = "", rpr: str = "", base: str = "Normal") -> str:
    """Uno stile di paragrafo, con i suoi margini e il suo carattere."""
    eredita = f'<w:basedOn w:val="{base}"/>' if base and sid != base else ""
    predefinito = ' w:default="1"' if sid == "Normal" else ""
    return (f'<w:style w:type="paragraph"{predefinito} w:styleId="{sid}"><w:name w:val="{nome}"/>'
            f'{eredita}<w:qFormat/><w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')


# Gli stili portano gli stessi colori del PDF: il verde dei titoli, il grigio
# chiaro dei blocchi di codice. Chi apre il .docx deve riconoscere lo stesso
# documento, non un parente sbiadito.
_STILI = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          f'<w:styles {_NS}>'
          '<w:docDefaults><w:rPrDefault><w:rPr>'
          '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
          '<w:sz w:val="22"/><w:lang w:val="it-IT"/></w:rPr></w:rPrDefault>'
          '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/>'
          '</w:pPr></w:pPrDefault></w:docDefaults>'
          + _stile("Normal", "Normal", base="")
          + _stile("Title", "Title", '<w:spacing w:after="200"/>',
                   '<w:b/><w:color w:val="0B6B3A"/><w:sz w:val="40"/>')
          + _stile("Heading1", "heading 1", '<w:keepNext/><w:spacing w:before="360" w:after="120"/>'
                   '<w:outlineLvl w:val="0"/>', '<w:b/><w:color w:val="0B6B3A"/><w:sz w:val="30"/>')
          + _stile("Heading2", "heading 2", '<w:keepNext/><w:spacing w:before="240" w:after="80"/>'
                   '<w:outlineLvl w:val="1"/>', '<w:b/><w:color w:val="128A4B"/><w:sz w:val="26"/>')
          + _stile("Heading3", "heading 3", '<w:keepNext/><w:spacing w:before="200" w:after="60"/>'
                   '<w:outlineLvl w:val="2"/>', '<w:b/><w:color w:val="128A4B"/><w:sz w:val="23"/>')
          + _stile("Elenco", "Elenco puntato", '<w:spacing w:after="60"/>'
                   '<w:ind w:left="567" w:hanging="283"/>')
          + _stile("Codice", "Codice", '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
                   '<w:shd w:val="clear" w:color="auto" w:fill="F3F4F6"/><w:ind w:left="284"/>',
                   '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:sz w:val="19"/>')
          + _stile("Formula", "Formula", '<w:jc w:val="center"/>',
                   '<w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/><w:i/>')
          + '</w:styles>')


def _run(testo: str, grassetto: bool = False, codice: bool = False) -> str:
    """Un pezzo di testo con il suo aspetto. Gli spazi restano come sono."""
    proprieta = ""
    if grassetto:
        proprieta += "<w:b/>"
    if codice:
        proprieta += ('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>'
                      '<w:shd w:val="clear" w:color="auto" w:fill="F3F4F6"/>')
    rpr = f"<w:rPr>{proprieta}</w:rPr>" if proprieta else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(testo)}</w:t></w:r>'


def _in_linea(testo: str) -> str:
    """Il testo di una riga, con il **grassetto** e il `codice` al loro posto."""
    pezzi = []
    for parte in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", testo):
        if not parte:
            continue
        if parte.startswith("**") and parte.endswith("**") and len(parte) > 4:
            pezzi.append(_run(parte[2:-2], grassetto=True))
        elif parte.startswith("`") and parte.endswith("`") and len(parte) > 2:
            pezzi.append(_run(parte[1:-1], codice=True))
        else:
            pezzi.append(_run(parte))
    return "".join(pezzi)


def _paragrafo(contenuto: str, stile: str | None = None) -> str:
    """Un paragrafo, con lo stile indicato (None = il testo normale)."""
    ppr = f'<w:pPr><w:pStyle w:val="{stile}"/></w:pPr>' if stile else ""
    return f"<w:p>{ppr}{contenuto}</w:p>"


def _corpo(md: str) -> str:
    """Dal markdown del documento ai paragrafi di Word."""
    fuori: list[str] = []
    if "```molecola" in md:
        from server.export import molecola
        molecola.prepara(md)        # tutti i nomi a OPSIN in una volta, non blocco per blocco
    righe = md.split("\n")
    i = 0
    while i < len(righe):
        riga = righe[i]
        nuda = riga.strip()
        if nuda.startswith("```"):
            # Un blocco recintato: codice riga per riga, grafico detto a parole.
            lingua = nuda[3:].strip().lower()
            blocco = []
            i += 1
            while i < len(righe) and not righe[i].strip().startswith("```"):
                blocco.append(righe[i])
                i += 1
            i += 1
            if lingua in document.DISEGNI:
                for voce in document._grafico_a_parole(lingua, [b.strip() for b in blocco]):
                    if voce.startswith("- "):
                        fuori.append(_paragrafo(_run("•\t") + _in_linea(voce[2:]), "Elenco"))
                    else:
                        fuori.append(_paragrafo(_in_linea(voce)))
            else:
                for b in blocco or [""]:
                    fuori.append(_paragrafo(_run(b), "Codice"))
                fuori.append(_paragrafo(""))
            continue
        if nuda.startswith("$$"):
            # Una formula su piu' righe si raccoglie fino ai $$ di chiusura.
            formula = nuda[2:]
            while not formula.rstrip().endswith("$$") and i + 1 < len(righe):
                i += 1
                formula += " " + righe[i].strip()
            fuori.append(_paragrafo(_run(formula.strip().rstrip("$").strip()), "Formula"))
            i += 1
            continue
        titolo = re.match(r"^(#{1,6})\s+(.+)$", nuda)
        if titolo:
            livello = len(titolo.group(1))
            stile = "Title" if livello == 1 else f"Heading{min(livello - 1, 3)}"
            fuori.append(_paragrafo(_in_linea(titolo.group(2)), stile))
        elif re.match(r"^[-*]\s+", nuda):
            fuori.append(_paragrafo(_run("•\t") + _in_linea(re.sub(r"^[-*]\s+", "", nuda)),
                                    "Elenco"))
        elif nuda == "---":
            pass
        elif nuda:
            fuori.append(_paragrafo(_in_linea(nuda)))
        i += 1
    return "".join(fuori)


def build_docx(md: str, out_path: str) -> None:
    """Scrive in 'out_path' il documento Word del markdown dato."""
    documento = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 f'<w:document {_NS}><w:body>{_corpo(md)}'
                 '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                 '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
                 'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
                 '</w:body></w:document>')
    with zipfile.ZipFile(_lp(out_path), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _TIPI)
        z.writestr("_rels/.rels", _RELAZIONI)
        z.writestr("word/_rels/document.xml.rels", _RELAZIONI_DOC)
        z.writestr("word/styles.xml", _STILI)
        z.writestr("word/document.xml", documento)


def save_docx(meta: dict, sections: list[dict], out_path: str, with_timestamps: bool,
              engine_label: str = "") -> bool:
    """Il .docx di un documento, con la stessa intestazione del .md e del PDF.

    Non solleva mai: un .docx mancato non deve far fallire il resto, visto che
    gli stessi contenuti sono gia' salvati negli altri formati. Restituisce
    True se il file e' stato scritto.
    """
    try:
        md = document.build_md(meta["title"], meta, engine_label, sections,
                               with_timestamps=with_timestamps)
        build_docx(md, out_path)
        return True
    except Exception:
        return False
