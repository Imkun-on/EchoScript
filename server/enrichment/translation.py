"""Tradurre una trascrizione gia' fatta.

Le due strade
    In nuvola, con Google Translate, che e' gratuito e non chiede nessuna
    chiave; oppure sul computer, con Ollama, che non manda niente fuori di
    casa. La scelta segue lo stesso interruttore del resto del programma.

Gli anglicismi, e perche' meritano un trattamento a parte
    Un traduttore automatico non sa distinguere una parola inglese usata come
    termine tecnico da una parola inglese da tradurre. Lasciato fare,
    trasforma "il deploy del branch" in qualcosa che nessuno ha mai detto.

    Quindi prima di tradurre quelle parole vengono nascoste dietro dei
    segnaposto, e dopo rimesse dov'erano. E' il grosso del codice di questo
    file, e non e' un dettaglio: e' la differenza fra una traduzione leggibile
    e una che fa ridere.

Perche' il testo viene spezzato
    Perche' i traduttori hanno un tetto di caratteri per richiesta. Lo si
    spezza sui confini delle frasi e non a caso, altrimenti la traduzione
    perde il filo esattamente nel punto del taglio.
"""
from __future__ import annotations

import json
import os
import re
import time

from server.config import settings
from server.config.settings import OLLAMA_HOST, OLLAMA_NUM_CTX
from server.config.messages import msg
from server.utils.media import _is_italian, _lang_name
from server.utils.ollama import _check_ollama
from server.utils.text import _safe_filename


# Riusa una trascrizione GIÀ salvata e ne produce una versione tradotta, senza
# ri-trascrivere (quindi senza spendere crediti di trascrizione). Due motori,
# scelti come per il riassunto — cioè dal BACKEND, non dalla presenza di una
# chiave: col backend Groq si usa Google Translate (deep_translator, endpoint
# gratuito, nessuna API key dedicata); col backend locale si traduce con Ollama,
# così una lavorazione «sul mio computer» resta 100% offline anche quando una
# chiave è caricata per altri lavori.

# Google Translate accetta ~5000 caratteri per richiesta: spezziamo il testo in
# blocchi più piccoli sui confini di frase, per stare comodi sotto il limite.
_TRANSLATE_MAX_CHARS = 4500


def _translate_ollama(text: str, target: str) -> str:
    """Traduce un testo verso 'target' con un modello locale via Ollama (HTTP).

    Usato in modalità locale per restare 100% offline (nessun passaggio da
    Google Translate). temperature=0 per una resa fedele e deterministica."""
    import urllib.request
    lang = _lang_name(target) or target
    system = (
        f"Sei un traduttore professionista. Traduci il testo dell'utente in "
        f"{lang} in modo fedele e naturale. Conserva integralmente il "
        f"significato, i nomi propri, le cifre e la punteggiatura. Mantieni "
        f"INVARIATI, nella loro forma inglese, i termini tecnici e gli "
        f"inglesismi di uso comune (per esempio «fine tuning», «deploy», "
        f"«streaming», «feedback», «machine learning», «commit», «buffer», "
        f"«dataset», «prompt»): non tradurli né adattarli. Non aggiungere e non "
        f"omettere nulla. Rispondi esclusivamente con la traduzione, senza "
        f"preamboli, note, virgolette o commenti.")
    payload = {
        "model": settings.OLLAMA_TRANSLATE_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "stream": False,
        "options": {"temperature": 0.0, "num_ctx": OLLAMA_NUM_CTX},
    }
    req = urllib.request.Request(
        OLLAMA_HOST + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    return (data.get("message", {}).get("content") or "").strip()


def _translate_engine_label(target: str = "it", local: bool = False) -> str:
    """La riga che dice, in testa al file tradotto, chi l'ha tradotto.

    Non e' decorazione. Una traduzione automatica va letta sapendo che e'
    automatica, e sapendo da CHI: Google Translate e un modello locale
    sbagliano in modi diversi, e chi rilegge il file mesi dopo non ha altro
    modo di ricordarselo.
    """
    lang = _lang_name(target) or target
    if local:
        return f"Traduzione automatica (locale · Ollama {settings.OLLAMA_TRANSLATE_MODEL}) → {lang}"
    return f"Traduzione automatica (Google Translate) → {lang}"


# Inglesismi / termini tecnici che devono restare in inglese anche nella
# traduzione italiana. Google Translate non è istruibile via prompt, perciò li
# «proteggiamo» con un segnaposto (NGZ<n>ZQ) prima di tradurre e li ripristiniamo
# dopo: quel formato (maiuscole + cifra) attraversa Google Translate INTATTO
# (verificato), così il termine originale non viene mai tradotto.
_ANGLICISMS = [
    "fine tuning", "fine-tuning", "machine learning", "deep learning",
    "data science", "big data", "cloud computing", "code review",
    "problem solving", "user experience", "smart working", "team building",
    "know-how", "know how", "step by step", "open source", "real time",
    "deploy", "deployment", "devops", "commit", "merge", "rebase", "branch",
    "buffer", "streaming", "stream", "streamer", "download", "upload",
    "feedback", "deadline", "meeting", "brainstorming", "briefing", "budget",
    "business", "dataset", "endpoint", "export", "import", "firmware",
    "framework", "hardware", "software", "hosting", "input", "output", "layout",
    "login", "logout", "marketing", "network", "online", "offline", "overflow",
    "password", "performance", "plugin", "prompt", "query", "rendering",
    "router", "screenshot", "server", "setup", "smartphone", "startup",
    "target", "template", "testing", "thread", "token", "toolkit", "tool",
    "trend", "tuning", "update", "upgrade", "username", "wireless", "workflow",
    "workshop", "backup", "benchmark", "cache", "container", "cookie",
    "debugging", "debug", "encoder", "decoder", "gaming", "hashtag",
    "influencer", "kernel", "latency", "mainstream", "malware", "middleware",
    "patch", "pipeline", "podcast", "proxy", "refactoring", "release",
    "rollback", "scroll", "shader", "sprint", "stack", "string", "throughput",
    "timeout", "trigger", "webcam", "widget", "browser", "frontend", "backend",
    "fullstack", "boilerplate", "changelog", "hotfix", "webinar", "wildcard",
    "ransomware", "spyware", "touchscreen", "playlist",
]
# Regex unica, alternative ordinate dalla più lunga (le locuzioni multi-parola
# devono avere la precedenza sulle singole parole al loro interno).
_ANGLICISM_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(_ANGLICISMS, key=len, reverse=True))
    + r")\b", re.IGNORECASE)
_ANGLICISM_TOKEN_RE = re.compile(r"NGZ\d+ZQ")


def _protect_anglicisms(text: str) -> tuple[str, dict[str, str]]:
    """Sostituisce gli inglesismi con segnaposto NGZ<n>ZQ (che Google preserva).

    Restituisce (testo_con_segnaposto, mappa segnaposto→forma originale)."""
    mapping: dict[str, str] = {}

    def repl(m: "re.Match") -> str:
        """Sostituisce un termine inglese con un segnaposto, e se lo ricorda.

        Il segnaposto ha quella forma strana apposta: deve essere qualcosa che
        un traduttore automatico non provi a tradurre, non spezzi e non
        riordini. Le lettere maiuscole senza vocali riconoscibili e il numero
        in mezzo servono proprio a non sembrare una parola.

        Si conserva la forma ESATTA trovata nel testo, maiuscole comprese:
        rimettendo a posto si deve ritrovare quello che c'era, non una versione
        normalizzata.
        """
        token = f"NGZ{len(mapping)}ZQ"
        mapping[token] = m.group(0)
        return token

    return _ANGLICISM_RE.sub(repl, text), mapping


def _restore_anglicisms(text: str, mapping: dict[str, str]) -> str:
    """Rimette i termini inglesi dov'erano, al posto dei segnaposto.

    L'ultima riga toglie i segnaposto eventualmente sopravvissuti storpiati.
    Serve perche' il traduttore, ogni tanto, ci mette dentro uno spazio o
    cambia una maiuscola: a quel punto il segnaposto non viene piu'
    riconosciuto e, senza questa pulizia, resterebbe a schermo come una sigla
    senza senso in mezzo alla frase.

    Meglio una parola mancante che una sigla incomprensibile: la prima si
    nota appena, la seconda fa sembrare rotto tutto il documento.
    """
    for token, original in mapping.items():
        text = text.replace(token, original)
    # Sicurezza: se qualche segnaposto fosse sopravvissuto storpiato, lo togliamo.
    return _ANGLICISM_TOKEN_RE.sub("", text)


def _make_translator(target: str = "it", local: bool = False):
    """Sceglie il motore di traduzione e restituisce una funzione (testo -> testo).

    In modalità locale traduce con Ollama (100% offline); altrimenti usa Google
    Translate (cloud, gratuito, sorgente autorilevata). In entrambi i casi gli
    inglesismi restano in inglese: via prompt con Ollama, via segnaposto con
    Google Translate. Solleva un RuntimeError chiaro se il motore scelto non è
    disponibile (Ollama non raggiungibile o deep_translator non installato)."""
    if local:
        _check_ollama()
        return lambda text: _translate_ollama(text, target)
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        raise RuntimeError("deep_translator non installato. Esegui:  "
                           "pip install deep-translator")
    google = GoogleTranslator(source="auto", target=target).translate

    def translate(text: str) -> str:
        """Traduce un pezzo di testo proteggendo prima i termini inglesi.

        I tre passaggi sono sempre questi e in quest'ordine: nascondi, traduci,
        rimetti. Stanno insieme in una funzione sola perche' saltarne uno
        produce un risultato che sembra giusto e non lo e', ed e' il tipo di
        errore che si scopre leggendo il documento finito.
        """
        protected, mapping = _protect_anglicisms(text)
        result = google(protected) or ""
        return _restore_anglicisms(result, mapping)

    return translate


def _split_for_translation(text: str) -> list[str]:
    """Spezza 'text' in blocchi <= _TRANSLATE_MAX_CHARS sui confini di frase.

    Se una singola frase supera il limite, viene tagliata a forza per non
    eccedere il massimo accettato da Google Translate."""
    text = (text or "").strip()
    if not text:
        return []
    # Confini di frase mantenendo la punteggiatura (split su spazio dopo .?!).
    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        while len(part) > _TRANSLATE_MAX_CHARS:
            # Frase mostruosa: tagliala in pezzi grezzi. Prima però va chiuso il
            # blocco in preparazione: senza, i pezzi di questa frase finirebbero
            # in coda PRIMA del testo che li precede, e la traduzione (o il
            # riassunto, che riusa questo splitter) uscirebbe con i paragrafi
            # scambiati di posto.
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append(part[:_TRANSLATE_MAX_CHARS])
            part = part[_TRANSLATE_MAX_CHARS:]
        if len(buf) + len(part) + 1 > _TRANSLATE_MAX_CHARS:
            if buf:
                chunks.append(buf)
            buf = part
        else:
            buf = f"{buf} {part}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def _translate_text(translate_fn, text: str) -> str:
    """Traduce un testo (anche lungo) unendo i blocchi tradotti.

    'translate_fn' è la funzione restituita da _make_translator (testo -> testo):
    Google Translate (cloud) oppure Ollama (locale)."""
    out = []
    for chunk in _split_for_translation(text):
        try:
            out.append(translate_fn(chunk) or "")
        except Exception:
            # Un blocco fallito non deve far saltare l'intera traduzione:
            # si tiene l'originale come fallback per quel pezzo.
            out.append(chunk)
    return " ".join(s for s in out if s).strip()


def translate_sections(sections: list[dict], target: str = "it",
                       local: bool = False, on_progress=None,
                       done_sections: list[dict] | None = None,
                       on_section=None) -> list[dict]:
    """Traduce titolo e testo di ogni sezione verso 'target' (default italiano).

    Con 'local=True' la traduzione avviene in locale via Ollama (100% offline);
    altrimenti via Google Translate. 'on_progress(i, n)' (opzionale) viene
    chiamato dopo ogni sezione tradotta, per aggiornare una barra/spinner.
    Restituisce nuove sezioni (non muta quelle in ingresso).

    Per il RESUME: 'done_sections' sono le sezioni già tradotte in una precedente
    esecuzione (le prime len(done_sections) di 'sections'), che vengono saltate;
    'on_section(list)' (opzionale) è chiamato dopo OGNI nuova sezione con l'elenco
    completo tradotto finora, per persistere il parziale su disco (così un
    interruzione a metà è riprendibile esattamente da lì)."""
    translate_fn = _make_translator(target, local)
    out: list[dict] = list(done_sections or [])
    start_index = len(out)
    n = len(sections)
    if on_progress and start_index:
        on_progress(start_index, n)  # riflette sulla barra il lavoro già fatto
    for i in range(start_index, n):
        sec = sections[i]
        title = sec.get("title")
        new_title = (_translate_text(translate_fn, title) if title else title)
        new_text = _translate_text(translate_fn, sec.get("text", ""))
        out.append({"start": sec.get("start"), "title": new_title, "text": new_text})
        if on_section:
            on_section(out)
        if on_progress:
            on_progress(i + 1, n)
    return out
