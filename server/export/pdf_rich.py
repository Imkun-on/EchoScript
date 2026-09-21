"""Il PDF «ricco»: formule disegnate e mappe dei concetti, non testo grezzo.

Come fa a disegnare le formule
    Non le disegna lui. Costruisce una pagina web che contiene il riassunto
    piu' due librerie JavaScript (una per le formule matematiche, una per i
    diagrammi), apre quella pagina con un browser che sul computer c'e' gia', e
    gli chiede di stamparla in PDF.

    Sembra un giro largo, ed e' invece il piu' corto che esista: l'alternativa
    sarebbe installare LaTeX, che sono qualche gigabyte e un'installazione che
    va storta spesso.

Il browser, e perche' non se ne porta dietro uno
    Su Windows 11 Edge c'e' sempre. Se non c'e', va bene Chrome. Se non c'e'
    nessuno dei due, si ripiega sul PDF semplice e non si dice niente di
    drammatico: il documento esce lo stesso, solo con le formule scritte in
    testo invece che disegnate.

Le due librerie, scaricate una volta sola
    La prima volta vengono prese da internet e messe da parte in una cartella
    accanto al programma. Da li' in avanti funziona anche senza rete. E' il
    motivo per cui quella cartella non sta dentro il pacchetto del programma:
    verrebbe rifatta da zero a ogni aggiornamento, e ogni versione nuova
    ripartirebbe a scaricarle.

_save_pdf: chi sceglie fra i due
    E' la porta d'ingresso di tutti e due i PDF. Prova il ricco; se manca una
    delle condizioni, fa il semplice. Chi la chiama non deve sapere quale dei
    due otterra', e infatti nella maggior parte dei casi non se ne accorge.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request

from server.config import paths, settings
from server.config.settings import BROWSER_PATH, RICH_PDF
from server.export.document import build_md
from server.export.pdf_basic import build_pdf
from server.utils.console import SYM_FAIL, console
from server.utils.media import _is_local
from server.utils.text import _format_timestamp, _lp, _safe_filename


PDF_ASSETS_DIR = paths.dati(".pdfassets")
# Librerie JS scaricate UNA volta in cache locale (poi funziona anche offline).
#
# Accanto all'eseguibile, non dentro `_internal`: è una cache che si riempie
# mentre il programma gira, e `_internal` viene rifatta da zero a ogni
# aggiornamento, quindi ogni nuova versione ripartirebbe a scaricarle. Da
# sorgenti le due cartelle coincidono e non cambia niente.
#
# La domanda "dove sta la cartella dei dati" la sa già paths, e adesso gliela
# si fa invece di ricalcolarla: prima c'era una funzione _data_root() qui
# dentro che rispondeva la stessa cosa in un modo diverso, ed era solo un modo
# in più di poter sbagliare.
_PDF_ASSET_URLS = {
    "tex-svg.js": "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js",
    "mermaid.min.js": "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js",
}
_PDF_HTML_TEMPLATE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<style>
  /* margine di pagina a ZERO: così il browser headless NON disegna il proprio
     header/footer (data in alto, percorso file in basso a sinistra, numero di
     pagina in basso a destra). I margini di stampa reali, UGUALI su ogni pagina,
     li ottiene la tabella .pagewrap qui sotto: thead/tfoot vengono ripetuti e
     RISERVANO spazio in alto e in basso su tutte le pagine. */
  @page { margin: 0; }
  body { font-family: 'Segoe UI', Calibri, Arial, sans-serif; color: #1b1b1b;
         line-height: 1.55; font-size: 12pt; margin: 0; }
  table.pagewrap { width: 100%; border-collapse: collapse; }
  table.pagewrap > thead > tr > td,
  table.pagewrap > tfoot > tr > td { height: 1.5cm; border: none; }
  table.pagewrap > tbody > tr > td { padding: 0 1.7cm; border: none;
         vertical-align: top; }
  h1 { color: #0b6b3a; font-size: 20pt; margin: 0 0 4px; }
  h2 { color: #0b6b3a; font-size: 15pt; margin: 22px 0 8px;
       border-bottom: 2px solid #d8efe2; padding-bottom: 3px; }
  h3 { color: #128a4b; font-size: 13pt; margin: 16px 0 6px; }
  strong { color: #0b3b22; }
  p { margin: 0 0 10px; text-align: justify; }
  ul { margin: 0 0 10px; padding-left: 22px; }
  hr { border: none; border-top: 1px solid #e2e2e2; margin: 14px 0; }
  code { font-family: Consolas, 'Courier New', monospace; font-size: 10.5pt;
         background: #f3f4f6; padding: 1px 4px; border-radius: 4px; }
  pre { background: #f6f8fa; border: 1px solid #e6e8eb; border-radius: 8px;
        padding: 12px 14px; overflow-x: auto; }
  pre code { background: none; padding: 0; }
  .mermaid { background: #fbfdfc; border: 1px solid #eef3f0; border-radius: 8px;
             padding: 12px; text-align: center; margin: 0 0 12px; }
  img { max-width: 100%; max-height: 15cm; display: block; margin: 8px 0 12px;
        border: 1px solid #e3e7e4; border-radius: 8px; }
</style>
<script>window.MathJax = {tex: {inlineMath: [['$','$'], ['\\\\(','\\\\)']],
    displayMath: [['$$','$$'], ['\\\\[','\\\\]']]},
  svg: {fontCache: 'global'}};</script>
<script src="__MATHJAX__"></script>
<script src="__MERMAID__"></script>
<script>window.addEventListener('load', function () {
  if (window.mermaid) { try { mermaid.initialize({startOnLoad: true, theme: 'neutral'}); } catch (e) {} }
});</script>
</head><body>
<table class="pagewrap"><thead><tr><td></td></tr></thead>
<tfoot><tr><td></td></tr></tfoot>
<tbody><tr><td>
__BODY__
</td></tr></tbody></table>
</body></html>
"""
def _md_inline_to_html(text: str) -> str:
    """Una riga di markdown diventa una riga di HTML.

    L'ordine dei due passaggi non e' scambiabile, ed e' tutta la sostanza di
    questa funzione. Prima si neutralizzano i caratteri che in HTML hanno un
    significato, POI si mette il grassetto.

    Al contrario, il grassetto appena inserito verrebbe neutralizzato insieme
    al resto e comparirebbe a schermo come testo invece che come formato. E
    soprattutto: un riassunto che parla di HTML, e contiene per esempio del
    codice con delle parentesi angolari, finirebbe per essere interpretato
    come struttura della pagina invece che mostrato.
    """
    import re
    import html as _html
    text = _html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
def _md_to_html(md: str) -> str:
    """Converte il markdown del riassunto in HTML per il PDF "ricco".

    Gestisce: titoli, grassetto, elenchi, righello, blocchi di codice e mermaid,
    e lascia INTATTE le formule `$…$`/`$$…$$` (le renderizza MathJax). I blocchi
    di codice/formule vengono "messi da parte" per non essere alterati dall'escape
    o dalla formattazione."""
    import re
    import html as _html
    store: dict[str, str] = {}
    block_keys: set[str] = set()  # placeholder che sono elementi di blocco (pre/mermaid)

    def _stash(content: str, block: bool = False) -> str:
        """Mette da parte un pezzo di HTML gia' pronto e lascia un segnaposto.

        Serve ai pezzi che NON vanno toccati dal resto della conversione: un
        blocco di codice, un diagramma, un'immagine. Se restassero nel testo,
        i passaggi successivi ci metterebbero dentro il grassetto, andrebbero
        a capo dove non si deve, e rovinerebbero il codice proprio dove e'
        importante che resti esatto.

        Il segnaposto e' fatto con un carattere che in un testo scritto da una
        persona non esiste, cosi' non puo' collidere con niente.
        """
        key = f"\x00{len(store)}\x00"
        store[key] = content
        if block:
            block_keys.add(key)
        return key

    # 1) Blocchi recintati ``` ``` (incl. ```mermaid). Il contenuto va escapato:
    # il browser lo de-escapa nel textContent, quindi mermaid riceve i caratteri
    # giusti (es. le frecce -->), ma l'HTML resta valido.
    def _fence(m):
        """Un blocco di codice fra apici tripli diventa HTML.

        Due destini diversi a seconda di com'e' marcato. Se dice `mermaid`, e'
        un diagramma e va consegnato alla libreria che lo disegnera'. Tutto il
        resto e' codice e va mostrato cosi' com'e', con gli spazi al posto
        giusto.
        """
        lang = (m.group(1) or "").strip().lower()
        body = _html.escape(m.group(2))
        if lang == "mermaid":
            return _stash(f'<pre class="mermaid">{body}</pre>', block=True)
        return _stash(f"<pre><code>{body}</code></pre>", block=True)

    md = re.sub(r"```([^\n]*)\n(.*?)```", _fence, md, flags=re.S)

    # 1b) Immagini ![alt](src): elemento di blocco. I percorsi locali diventano
    # file:// così il browser headless li carica.
    def _img(m):
        """Un'immagine di markdown diventa un tag HTML.

        Il giro sul percorso serve ai fotogrammi estratti dal video, che sono
        file sul disco. Un browser, in una pagina locale, non carica un
        percorso scritto alla maniera di Windows: gli va dato nella forma degli
        indirizzi, e la conversione la fa la riga qui sotto.

        Se non riesce si lascia com'era: peggio che vada, quell'immagine non si
        vede, e il resto del documento esce lo stesso.
        """
        import pathlib
        alt = _html.escape(m.group(1))
        src = m.group(2).strip()
        if "://" not in src:
            try:
                src = pathlib.Path(src).as_uri()
            except Exception:
                pass
        return _stash(f'<img alt="{alt}" src="{src}">', block=True)

    md = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _img, md)
    # 2) Formule: lasciate grezze (MathJax le legge dal testo), ma messe da parte
    # così l'escape non tocca eventuali < > al loro interno e un'eventuale riga
    # vuota interna non spezzi il blocco display in due <p>. Si accettano ENTRAMBI
    # gli stili di delimitatori: $$…$$ / $…$ e \[…\] / \(…\) (il modello usa l'uno
    # o l'altro indistintamente). I display (\[…\], $$…$$) vanno stashati PRIMA
    # degli inline per non spezzarli.
    md = re.sub(r"\$\$(.+?)\$\$", lambda m: _stash(f"$${m.group(1)}$$"), md, flags=re.S)
    md = re.sub(r"\\\[(.+?)\\\]", lambda m: _stash(f"\\[{m.group(1)}\\]"), md, flags=re.S)
    md = re.sub(r"\\\((.+?)\\\)", lambda m: _stash(f"\\({m.group(1)}\\)"), md, flags=re.S)
    md = re.sub(r"\$(.+?)\$", lambda m: _stash(f"${m.group(1)}$"), md)
    # 3) Codice inline `…`
    md = re.sub(r"`([^`]+)`", lambda m: _stash(f"<code>{_html.escape(m.group(1))}</code>"), md)

    # 4) Struttura a blocchi, riga per riga. Gli heading (# / ## / ###) diventano
    # h1/h2/h3: da questi il browser genera i SEGNALIBRI/outline del PDF (il
    # «Sommario» cliccabile nel pannello laterale del lettore), grazie al flag
    # --generate-pdf-document-outline usato in build_pdf_rich.
    out: list[str] = []
    para: list[str] = []
    in_list = False

    def _flush_para():
        """Chiude il paragrafo che si stava accumulando, se ce n'era uno.

        Il testo arriva riga per riga, ma un paragrafo puo' essere fatto di
        piu' righe: le si mette da parte finche' non si incontra qualcosa che
        chiude il discorso, cioe' una riga vuota, un titolo o un elenco. A quel
        punto le si unisce in un paragrafo solo.
        """
        if para:
            out.append("<p>" + _md_inline_to_html(" ".join(para)) + "</p>")
            para.clear()

    def _close_list():
        """Chiude l'elenco puntato aperto, se ce n'era uno.

        Stessa logica del paragrafo: un elenco comincia alla prima riga che
        sembra una voce e finisce alla prima che non lo sembra piu'. Nessuno
        dice esplicitamente dove finisce, quindi lo si chiude quando si incontra
        altro.

        Un elenco lasciato aperto non produce un errore: produce una pagina in
        cui tutto quello che viene dopo risulta rientrato, e la causa non si
        capisce guardando il punto in cui si vede il difetto.
        """
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in md.split("\n"):
        s = line.strip()
        if not s:
            _flush_para(); _close_list(); continue
        if s in block_keys:  # blocco codice/mermaid: elemento a sé, niente <p>
            _flush_para(); _close_list(); out.append(s); continue
        if s.startswith("### "):
            _flush_para(); _close_list(); out.append("<h3>" + _md_inline_to_html(s[4:]) + "</h3>")
        elif s.startswith("## "):
            _flush_para(); _close_list(); out.append("<h2>" + _md_inline_to_html(s[3:]) + "</h2>")
        elif s.startswith("# "):
            _flush_para(); _close_list(); out.append("<h1>" + _md_inline_to_html(s[2:]) + "</h1>")
        elif s in ("---", "***", "___"):
            _flush_para(); _close_list(); out.append("<hr>")
        elif s.startswith("- ") or s.startswith("* "):
            _flush_para()
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append("<li>" + _md_inline_to_html(s[2:]) + "</li>")
        else:
            _close_list(); para.append(s)
    _flush_para(); _close_list()

    body = "\n".join(out)
    # 5) Ripristina i blocchi messi da parte (codice/mermaid/formule).
    for key, content in store.items():
        body = body.replace(key, content)
    return body
def _ensure_pdf_assets():
    """Restituisce (path_mathjax, path_mermaid), scaricandoli in cache se mancano.

    None se non è possibile procurarseli (niente rete e niente cache)."""
    import urllib.request
    try:
        os.makedirs(PDF_ASSETS_DIR, exist_ok=True)
    except OSError:
        return None
    paths = {}
    for name, url in _PDF_ASSET_URLS.items():
        p = os.path.join(PDF_ASSETS_DIR, name)
        if not (os.path.isfile(p) and os.path.getsize(p) > 10000):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    data = r.read()
                with open(p, "wb") as f:
                    f.write(data)
            except Exception:
                return None
        paths[name] = p
    return paths["tex-svg.js"], paths["mermaid.min.js"]
def _find_browser() -> str | None:
    """Cerca un browser sul computer, perche' e' lui a disegnare il PDF.

    Perche' se ne cercano tanti
        Perche' la ricerca deve funzionare su una macchina qualunque, e non c'e'
        modo di sapere in anticipo cosa ci sia installato. Su Windows 11 Edge
        c'e' sempre; altrove puo' esserci Chrome, Chromium o Brave. Vanno tutti
        bene: sono lo stesso motore con nomi diversi, e stampano lo stesso PDF.

    L'ordine in cui si cerca
        Prima quello eventualmente indicato a mano nelle impostazioni, perche'
        chi l'ha scritto sa cosa vuole. Poi quelli raggiungibili per nome. Poi
        i posti in cui Windows li installa di solito, che serve quando il
        browser c'e' ma nessuno lo ha messo fra i programmi richiamabili.

    None non e' un guasto
        Vuol dire che non c'e' nessun browser, e chi chiama fara' il PDF
        semplice. Il documento esce lo stesso, solo con le formule scritte in
        testo invece che disegnate.
    """
    candidates: list[str] = []
    if BROWSER_PATH:
        candidates.append(BROWSER_PATH)
    for name in ("msedge", "chrome", "chromium", "chromium-browser", "brave"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    bases = [os.environ.get("ProgramFiles", r"C:\Program Files"),
             os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
             os.environ.get("LocalAppData", "")]
    for base in bases:
        if not base:
            continue
        candidates.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
        candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None
def build_pdf_rich(md_text: str, out_path: str) -> bool:
    """Genera un PDF con formule (MathJax) e mappe (Mermaid) DISEGNATE.

    Converte il markdown in HTML e lo stampa con un browser Chromium headless già
    presente sul sistema. Restituisce True se il PDF è stato creato, False se non
    è possibile (nessun browser/asset): in tal caso il chiamante ripiega su fpdf2."""
    import pathlib
    browser = _find_browser()
    if not browser:
        return False
    assets = _ensure_pdf_assets()
    if not assets:
        return False
    mathjax, mermaid = assets
    html_doc = (_PDF_HTML_TEMPLATE
                .replace("__MATHJAX__", pathlib.Path(mathjax).as_uri())
                .replace("__MERMAID__", pathlib.Path(mermaid).as_uri())
                .replace("__BODY__", _md_to_html(md_text)))
    with tempfile.TemporaryDirectory(prefix="echoscript_pdf_", ignore_cleanup_errors=True) as td:
        html_path = os.path.join(td, "doc.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_doc)
        # Chrome NON gestisce i percorsi lunghi (>260) né il prefisso \\?\: stampa
        # su un file temporaneo dal nome corto e poi lo copiamo nella destinazione
        # definitiva (che può essere lunga) tramite _lp().
        tmp_pdf = os.path.join(td, "out.pdf")
        cmd = [
            browser, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--no-first-run", "--no-default-browser-check", "--disable-extensions",
            # virtual-time-budget: lascia a MathJax/Mermaid il tempo di disegnare
            # prima di stampare (altrimenti il PDF esce a metà rendering).
            "--virtual-time-budget=20000", "--run-all-compositor-stages-before-draw",
            # Genera i SEGNALIBRI/outline del PDF dai titoli (h1/h2/h3): è il
            # «Sommario» cliccabile nel pannello laterale del lettore PDF, che
            # rimanda a ogni capitolo. Flag ignorato dai browser troppo vecchi
            # (nessun errore: in tal caso il PDF esce semplicemente senza outline).
            "--generate-pdf-document-outline",
            f"--print-to-pdf={tmp_pdf}", pathlib.Path(html_path).as_uri(),
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=120)
        except Exception:
            return False
        if not (os.path.isfile(tmp_pdf) and os.path.getsize(tmp_pdf) > 1500):
            return False
        try:
            shutil.copyfile(tmp_pdf, _lp(out_path))
        except OSError:
            return False
    return os.path.isfile(_lp(out_path)) and os.path.getsize(_lp(out_path)) > 1500
def _save_pdf(meta: dict, sections: list[dict], out_path: str, with_timestamps: bool,
              engine_label: str = "", markdown: bool = False) -> bool:
    """Esporta un PDF: prima quello "ricco" (formule/mappe disegnate via browser
    headless), poi ripiega su fpdf2. NON usa Groq — lavora su testo già prodotto,
    quindi NESSUN credito speso. Restituisce True se il PDF è stato creato."""
    # «Salvato in:»: la cartella di output, ricavata dal percorso del PDF. Compare
    # tra i metadati in testa al documento (non più in fondo a ogni pagina).
    saved_in = os.path.dirname(os.path.abspath(out_path))
    if RICH_PDF:
        try:
            md_text = build_md(meta["title"], meta, engine_label, sections,
                               with_timestamps=with_timestamps, saved_in=saved_in)
            if build_pdf_rich(md_text, out_path):
                return True
        except Exception:
            pass
    try:
        build_pdf(meta["title"], meta, sections, out_path,
                  with_timestamps=with_timestamps, markdown=markdown,
                  engine_label=engine_label, saved_in=saved_in)
        return True
    except Exception as e:
        console.print(f"[error]Export PDF fallito: {e}[/error]")
        return False
