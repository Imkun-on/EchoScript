"""Il riassunto: le istruzioni che si danno al modello.

Cosa c'e' qui dentro
    Due cose: le istruzioni che si danno al modello, e il lavoro di mandargli
    il testo a pezzi e rimettere insieme le risposte.

    Le istruzioni sono quasi soltanto testo: le regole che il modello deve seguire mentre
    trasforma una trascrizione in un riassunto: cosa togliere (le esitazioni,
    le ripetizioni, le frasi lasciate a meta'), cosa non toccare mai (i nomi,
    i numeri, i termini tecnici), come comportarsi con gli errori che la
    trascrizione automatica si porta dietro.

    Sono scritte per esteso e non riassunte a loro volta perche' e' l'unico
    modo di ottenere risultati uguali fra un video e l'altro. Un'istruzione
    vaga da' un riassunto diverso ogni volta.

Le tre forme, e quando si usa ciascuna
    ``prompt_base()``     quando c'e' solo il parlato;
    ``prompt_visivo()``   quando ci sono anche le note di cio' che nel video
                          si VEDE, e vanno intrecciate al testo;
    ``prompt_attivo()``   quella da usare adesso, che e' la seconda se c'e'
                          qualcosa di visivo e la prima altrimenti.

Perche' era anche in inglese, e perche' non lo e' piu'
    Il riassunto seguiva la lingua dell'interfaccia, quindi di ogni regola
    esisteva una seconda copia in inglese, lunga uguale. Da quando il programma
    parla solo italiano quelle copie non le raggiungeva piu' nessuno: erano
    settanta righe di testo che nessun modello avrebbe mai letto.

PROMPT_ATTIVO: l'unica cosa qui dentro che cambia
    Vale None quasi sempre, e viene riempito da chi mette in fila il lavoro
    quando scopre che per quel video ci sono anche delle note visive.

    Va letto e scritto SEMPRE come ``summary.PROMPT_ATTIVO``, mai importandolo
    per nome: importandolo se ne prende una fotografia, e da quel momento si
    userebbe per sempre il prompt sbagliato senza nessun errore che lo dica.
    E' la stessa regola delle impostazioni, per lo stesso motivo.
"""
from __future__ import annotations

import json
import re
import time

from server.config import settings
from server.config.settings import (
    OLLAMA_HOST, OLLAMA_NUM_CTX, SUMMARY_MAX_CHARS,
)
from server.utils.console import console
from server.utils.contract import GroqRateLimit, _is_rate_limit
from server.enrichment.translation import _split_for_translation
from server.state.credits import record_rate_limits
from server.utils.ollama import _check_ollama


# Dal testo italiano (la traduzione, oppure la trascrizione se l'audio era già
# italiano) produce un riassunto PER SEZIONE: pulisce intercalari, ripetizioni e
# autocorrezioni e tiene i concetti. Groq usa un modello di chat; in locale ci si
# appoggia a Ollama (nessuna dipendenza pip aggiuntiva: si parla via HTTP).

# Istruzioni date al modello: sono il cuore della qualità del riassunto.
_SUMMARY_SYSTEM_PROMPT = (
    "Sei un editor professionista specializzato nella rielaborazione di "
    "contenuti parlati. Ricevi la trascrizione di una sezione di un video "
    "(testo in italiano) e la trasformi in un riassunto fedele, dettagliato e "
    "scorrevole, redatto interamente in italiano secondo le regole seguenti.\n"
    "Voce e punto di vista: scrivi come se stessi spiegando TU l'argomento a "
    "chi legge. Il riassunto non racconta un video, espone la materia. È "
    "quindi VIETATO qualsiasi riferimento alla fonte o a chi parla: non "
    "scrivere mai «il video», «il tutorial», «il corso», «la lezione», "
    "«l'autore», «il relatore», «l'oratore», «lo speaker», «viene spiegato "
    "che», «viene mostrato che», «si dice che», «dicono che», «il video "
    "sottolinea», «nel prossimo video». Trasforma ogni frase di questo tipo "
    "nell'affermazione diretta che contiene: al posto di «il video spiega che "
    "withColumn non opera in-place» scrivi «withColumn non opera in-place». "
    "Se una frase, tolto il riferimento alla fonte, non dice più nulla di "
    "sostanziale, eliminala del tutto.\n"
    "Pulizia del testo: elimina intercalari, riempitivi ed esitazioni (ehm, "
    "uhm, cioè, tipo, no?, allora, insomma) e rimuovi ripetizioni, frasi "
    "interrotte e autocorrezioni di chi parla, conservando soltanto la versione "
    "corretta e definitiva di ciascun passaggio. Elimina anche tutto ciò che "
    "non è contenuto: saluti e convenevoli, inviti a iscriversi o a seguire la "
    "playlist, scuse per il ritardo, annunci di video futuri, promozioni.\n"
    "Fedeltà ai contenuti: conserva integralmente tutti i concetti, i dati, i "
    "nomi propri, le cifre e gli esempi rilevanti. Non aggiungere informazioni "
    "assenti nel testo, non inventare e non introdurre interpretazioni o "
    "commenti personali.\n"
    "Inglesismi e termini tecnici: mantieni in inglese i termini tecnici e gli "
    "inglesismi ormai di uso comune in italiano (per esempio «fine tuning», "
    "«deploy», «streaming», «feedback», «machine learning», «commit», «buffer», "
    "«dataset», «prompt»). NON tradurli né italianizzarli: scrivili nella forma "
    "inglese corrente, esattamente come li userebbe chi lavora nel settore.\n"
    "Errori di trascrizione: il testo proviene da una trascrizione AUTOMATICA del "
    "parlato e può contenere sviste (parole storpiate, omofoni sbagliati, "
    "spaziature o concordanze errate, un termine tecnico reso male). Quando dal "
    "contesto riconosci con ragionevole certezza un evidente errore di "
    "trascrizione, correggilo in silenzio ripristinando la parola o l'espressione "
    "corretta; se invece il dubbio è genuino, conserva il testo originale senza "
    "inventare. Non segnalare, non elencare e non commentare le correzioni.\n"
    "Codice, comandi e formule SEMPRE in blocco: ogni volta che compare del "
    "codice, un comando da terminale, una chiamata di funzione con i suoi "
    "argomenti, una configurazione o una formula, NON lasciarlo dentro la riga "
    "di prosa, mettilo in un blocco a sé su righe proprie.\n"
    "• il codice va in un blocco markdown delimitato da ``` con il nome del "
    "linguaggio subito dopo i primi tre apici (```python, ```sql, ```bash), "
    "riportato fedelmente e su più righe quando le istruzioni sono più di una;\n"
    "• le formule e i passaggi matematici vanno in LaTeX: `$...$` quando un "
    "simbolo è citato dentro la frase, `$$...$$` su riga propria per le formule "
    "vere e proprie e per ogni passaggio di una dimostrazione;\n"
    "• ogni blocco va accompagnato dalla spiegazione di che cosa fa, scritta in "
    "parole tue: una riga prima che introduca il problema che risolve e una "
    "riga dopo, quando serve, che commenti il risultato o i parametri "
    "importanti. Un blocco lasciato lì senza spiegazione non va bene;\n"
    "• gli apici singoli `così` restano ammessi SOLTANTO per un nome isolato "
    "citato nel discorso (il nome di una colonna, di un parametro, di una "
    "classe, di un file). Appena ci sono parentesi, argomenti o più di "
    "un'istruzione si usa il blocco;\n"
    "• se lo stesso comando ricorre più volte, mostralo in blocco la prima "
    "volta e poi richiamalo per nome senza ripeterlo.\n"
    "Elenchi: quando chi parla enumera cose brevi e omogenee (i passi di una "
    "procedura, le opzioni di un metodo, i parametri di una funzione, i "
    "vantaggi, i tipi, le voci di una lista), rendile come elenco puntato, una "
    "voce per riga aperta da «- », e non come frasi incolonnate dentro un "
    "paragrafo. Vale anche per le enumerazioni numerate a voce («il primo step "
    "è..., il secondo...»), che diventano comunque un elenco puntato con «- ». "
    "Quando la voce ha un nome, aprila con quel nome in **grassetto** seguito "
    "dalla spiegazione. Resta invece in prosa tutto ciò che è ragionamento, "
    "motivazione o collegamento fra i concetti: l'elenco serve alle cose "
    "brevi, non sostituisce il discorso.\n"
    "Stile e struttura: redigi il riassunto in prosa continua e articolata, "
    "privilegiando un testo discorsivo che ricostruisca con ricchezza il filo "
    "del discorso e ne approfondisca i passaggi anziché comprimerli. Punta a un "
    "riassunto esteso e particolareggiato, non a una sintesi telegrafica. "
    "Per facilitare la lettura, evidenzia in grassetto Markdown (**testo**) "
    "soltanto le parole o le brevissime locuzioni chiave (concetti centrali, "
    "termini tecnici, nomi propri e cifre rilevanti) usando il grassetto con "
    "parsimonia e mai su intere frasi (deve risaltare, non saturare il testo). "
    "Quando la sezione affronta più argomenti distinti puoi separarli con un "
    "sottotitolo «### Titolo» su riga propria. Mantieni un registro "
    "professionale, chiaro e coeso, con transizioni fluide tra i concetti.\n"
    "Markdown ammesso: soltanto il **grassetto**, i sottotitoli «### », gli "
    "elenchi puntati «- », i blocchi ``` e le formule `$`/`$$`. NON usare il "
    "corsivo con asterischi singoli (*testo*), né tabelle, né note a piè di "
    "pagina, né link.\n"
    "Vincoli di output: rispondi esclusivamente con il riassunto, senza "
    "preamboli, intestazioni o commenti. Non aprire mai il testo con formule "
    "del tipo \"Ecco i punti chiave\", \"In questo video si parla di\" o simili: "
    "entra direttamente nel contenuto."
)

# Estensione del prompt usata quando il testo contiene anche le note dell'ANALISI
# VISIVA: istruisce il modello a integrare codice, formule e diagrammi visti a
# schermo e ad aggiungere una mappa concettuale quando il contenuto è visuale.
_SUMMARY_VISUAL_BASE = (
    "\nIl testo può contenere annotazioni nel formato «[A SCHERMO · mm:ss] …» che "
    "riportano ciò che era VISIBILE nel video in quel momento (codice, formule, "
    "grafici, diagrammi, slide). Trattale come fonte attendibile quanto il parlato "
    "e INTEGRALE nel riassunto in modo naturale, secondo queste regole aggiuntive:\n"
    "• il codice e le formule che arrivano dalle annotazioni seguono le stesse "
    "regole del resto del riassunto: blocco ``` con il linguaggio per il codice, "
    "LaTeX per le formule, e in tutti e due i casi la spiegazione di che cosa "
    "fanno. Il codice visto a schermo va preservato fedelmente, indentazione "
    "compresa, e le dimostrazioni riportate con tutti i passaggi mostrati;\n"
    "• descrivi GRAFICI, DIAGRAMMI e TABELLE riportandone dati, assi, relazioni e "
    "la conclusione. Quando l'immagine mostra un elenco di voci brevi (i punti di "
    "una slide, le colonne di una tabella, le voci di una legenda) rendile come "
    "elenco puntato «- »;\n"
    "• non citare mai l'annotazione in quanto tale: niente «a schermo si vede», "
    "«nella slide compare», «il diagramma mostra». Quello che era scritto a "
    "schermo va detto come lo diresti tu spiegando l'argomento, fuso nel discorso "
    "insieme al parlato.\n"
    "Importante: se la stessa slide, definizione o diagramma compare in più "
    "annotazioni (perché restava a schermo a lungo), trattalo UNA volta sola e non "
    "ripetere paragrafi o concetti già esposti. Non limitarti a citare le "
    "annotazioni: fondile nel discorso come parte integrante della spiegazione."
)
# Variante CON mappa concettuale (attivabile via ECHOSCRIPT_CONCEPT_MAP=1).
_SUMMARY_VISUAL_MAP = (
    "\nSe (e solo se) il contenuto è prevalentemente concettuale o animato, "
    "aggiungi UNA SOLA mappa concettuale complessiva alla fine, in un blocco "
    "```mermaid con sintassi `graph TD` e archi nel formato corretto "
    "`A -->|etichetta| B` (MAI `A -->|etichetta|> B`); non ripetere lo stesso "
    "diagramma più volte."
)
# Variante SENZA mappa (default): vietiamo esplicitamente i diagrammi mermaid.
_SUMMARY_VISUAL_NOMAP = (
    "\nNON generare mappe concettuali, diagrammi né blocchi ```mermaid: limitati a "
    "prosa, elenchi puntati, blocchi di codice e formule."
)
_SUMMARY_SYSTEM_PROMPT_VISUAL = _SUMMARY_SYSTEM_PROMPT + _SUMMARY_VISUAL_BASE + _SUMMARY_VISUAL_NOMAP
_SUMMARY_SYSTEM_PROMPT_VISUAL_MAP = _SUMMARY_SYSTEM_PROMPT + _SUMMARY_VISUAL_BASE + _SUMMARY_VISUAL_MAP

# Il prompt da usare adesso. None = quello base.
#
# Lo riempie chi mette in fila il lavoro, quando per quel video ci sono anche
# le note di cio' che si vede. Vedi la spiegazione in cima al file sul perche'
# va sempre letto come `summary.PROMPT_ATTIVO`.
PROMPT_ATTIVO = None


def prompt_base() -> str:
    """Le regole del riassunto quando c'e' soltanto il parlato.

    E' una funzione e non il testo letto direttamente, cosi' chi lo usa passa
    sempre dalla stessa porta e il giorno in cui la scelta del prompt dovesse
    dipendere da qualcos'altro, si cambia qui dentro e basta.
    """
    return _SUMMARY_SYSTEM_PROMPT


def prompt_visivo(mappa_concetti: bool) -> str:
    """Le regole quando ci sono anche le note di cio' che si vede nel video.

    ``mappa_concetti`` decide se al modello viene anche chiesto di disegnare
    una mappa dei concetti. Sono due testi diversi e non uno con un pezzo in
    piu', perche' chiedere una mappa cambia anche come conviene organizzare il
    resto del riassunto.
    """
    return _SUMMARY_SYSTEM_PROMPT_VISUAL_MAP if mappa_concetti else _SUMMARY_SYSTEM_PROMPT_VISUAL


def prompt_attivo() -> str:
    """Le regole da usare adesso: quelle visive se ci sono, altrimenti le base.

    E' la porta che usano tutti quelli che riassumono davvero, e serve a non
    far decidere a ciascuno di loro se per questo video ci fossero o no delle
    note visive. Quella decisione e' gia' stata presa da chi ha messo in fila
    il lavoro, e sta scritta in PROMPT_ATTIVO.
    """
    return PROMPT_ATTIVO or prompt_base()


# =============================================================================
#  Il lavoro: mandare il testo al modello e rimettere insieme le risposte
# =============================================================================
#
# Perche' a pezzi e non tutto insieme
#     Perche' i modelli hanno un tetto a quanto testo riescono a tenere in
#     mente in una volta. Una trascrizione di due ore lo supera largamente.
#
#     Si spezza per sezioni, che e' il taglio giusto: una sezione e' gia'
#     un'unita' di senso, quindi il modello non perde il filo come farebbe se
#     lo si tagliasse a un numero fisso di caratteri.

def _summary_user_prompt(text: str, section_title: str | None) -> str:
    """Il messaggio che si manda al modello: il testo, col suo titolo davanti.

    Il titolo della sezione, quando c'e', cambia il risultato piu' di quanto si
    creda: dice al modello di cosa si sta parlando prima ancora che legga, e lo
    aiuta a capire quali sono i termini importanti e quali le divagazioni.

    Le regole di COME riassumere non sono qui: stanno nel messaggio di sistema
    (vedi i prompt in cima al file). Qui c'e' solo il materiale.
    """
    head = f"Titolo della sezione: «{section_title}».\n\n" if section_title else ""
    return f"{head}Testo da riassumere:\n\n{text}"
def _groq_chat_capture(client, model: str, **kwargs):
    """client.chat.completions.create che, quando possibile, registra i crediti
    residui del modello dagli header x-ratelimit-* (per il pulsante "crediti"),
    SENZA costo aggiuntivo. Se la variante raw fallisce per motivi diversi da
    credito/auth, ripiega sulla chiamata normale. Restituisce l'oggetto risposta
    già parsato, come la create() classica."""
    try:
        raw = client.chat.completions.with_raw_response.create(model=model, **kwargs)
    except Exception as e:
        msg = str(e)
        if _is_rate_limit(msg) or "401" in msg or "403" in msg:
            raise
        return client.chat.completions.create(model=model, **kwargs)
    try:
        record_rate_limits(model, raw.headers)
    except Exception:
        pass
    return raw.parse()
def _summarize_groq(client, text: str, section_title: str | None) -> str:
    """Riassume un pezzo di testo con un modello di Groq.

    Attenzione, non e' lo stesso modello che trascrive. Whisper trasforma
    l'audio in parole e non sa fare altro; qui serve un modello che capisca il
    testo, ed e' un modello diverso, con un prezzo diverso e un limite di
    crediti a parte. Nei menu compaiono infatti come due scelte distinte.

    La temperatura bassa non e' un dettaglio: significa «attieniti al testo».
    Un riassunto creativo sarebbe un riassunto che aggiunge cose che nel video
    non c'erano, ed e' il difetto peggiore che possa avere.
    """
    resp = _groq_chat_capture(
        client, settings.GROQ_SUMMARY_MODEL,
        messages=[
            {"role": "system", "content": prompt_attivo()},
            {"role": "user", "content": _summary_user_prompt(text, section_title)},
        ],
        temperature=0.3,
    )
    return (resp.choices[0].message.content or "").strip()
def _summarize_ollama(text: str, section_title: str | None) -> str:
    """Riassume un pezzo di testo con un modello che gira su questo computer.

    Si parla con Ollama via rete locale invece che con una libreria Python, e
    non e' un ripiego: vuol dire che nel pacchetto del programma non entra
    nessuna libreria in piu', e che il giorno in cui Ollama cambia versione non
    c'e' niente da aggiornare qui dentro.

    La finestra di contesto viene alzata apposta. Ollama, lasciato ai suoi
    valori, ne usa una piccola: il modello leggerebbe solo l'inizio del testo e
    riassumerebbe quello, senza nessun errore, dando un riassunto che sembra
    solo un po' sbrigativo. E' un difetto difficile da scoprire proprio perche'
    non si presenta come tale.
    """
    import urllib.request
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": prompt_attivo()},
            {"role": "user", "content": _summary_user_prompt(text, section_title)},
        ],
        "stream": False,
        # num_ctx alza la finestra di contesto (default Ollama: solo 2048 token,
        # che troncherebbe i blocchi lunghi). Senza, i video lunghi perderebbero
        # gran parte del testo nel riassunto.
        "options": {"temperature": 0.3, "num_ctx": OLLAMA_NUM_CTX},
    }
    req = urllib.request.Request(
        OLLAMA_HOST + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    return (data.get("message", {}).get("content") or "").strip()
def _make_summarizer(client=None):
    """Sceglie il motore del riassunto e restituisce (funzione, etichetta).

    Preferisce Groq se è disponibile un client (backend cloud); altrimenti usa
    Ollama in locale (100% offline). Solleva RuntimeError se nessuno è utilizzabile."""
    if client is not None:
        label = f"Riassunto automatico (Groq · {settings.GROQ_SUMMARY_MODEL})"
        return (lambda text, title: _summarize_groq(client, text, title)), label
    _check_ollama()
    label = f"Riassunto automatico (locale · Ollama {settings.OLLAMA_MODEL})"
    return (lambda text, title: _summarize_ollama(text, title)), label
def _summarize_long(summarize_fn, text: str, section_title: str | None) -> str:
    """Riassume un testo lungo quanto si vuole, a costo di farlo in due giri.

    Il problema
        Ogni modello ha un tetto a quanto testo riesce a tenere in mente in una
        volta. Una sezione lunga lo supera, e quello che succede allora non e'
        un errore: il modello legge quello che ci sta e ignora il resto, in
        silenzio. Il riassunto che ne esce sembra solo un po' povero.

    La soluzione, in due passaggi
        Prima si taglia il testo in blocchi e si riassume ogni blocco per conto
        suo. Poi si prendono quei riassunti parziali e si riassumono a loro
        volta, ottenendone uno solo.

        Il secondo giro non e' facoltativo: senza, il risultato sarebbe un
        elenco di riassunti scollegati, con le stesse cose ripetute tre volte
        perche' comparivano in tre blocchi diversi.

    Perche' riusa il tagliatore della traduzione
        Perche' il problema e' identico, tagliare un testo lungo sui confini
        delle frasi, e averne due copie vorrebbe dire correggere ogni difetto
        due volte.
    """
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= SUMMARY_MAX_CHARS:
        return summarize_fn(text, section_title)
    # Map: riassumi a blocchi (riuso lo splitter della traduzione, con cap ampio).
    saved = globals().get("_TRANSLATE_MAX_CHARS")
    globals()["_TRANSLATE_MAX_CHARS"] = SUMMARY_MAX_CHARS
    try:
        blocks = _split_for_translation(text)
    finally:
        globals()["_TRANSLATE_MAX_CHARS"] = saved
    partials = [summarize_fn(b, section_title) for b in blocks]
    merged = "\n\n".join(p for p in partials if p)
    # Reduce: ricompatta i parziali in un unico riassunto coerente.
    return summarize_fn(merged, section_title)
def summarize_sections(sections: list[dict], summarize_fn,
                       on_progress=None, done_sections: list[dict] | None = None,
                       on_section=None) -> list[dict]:
    """Riassume ogni sezione (titolo invariato, testo -> riassunto).

    'on_progress(i, n)' (opzionale) è chiamato dopo ogni sezione. Restituisce
    nuove sezioni senza mutare quelle in ingresso.

    Per il RESUME: 'done_sections' sono le sezioni già riassunte in precedenza
    (saltate); 'on_section(list)' è chiamato dopo OGNI nuova sezione con l'elenco
    completo finora, per salvare il parziale: così se i crediti Groq finiscono a
    metà riassunto si riprende esattamente dalla sezione ferma, senza rispendere
    crediti su quelle già fatte."""
    out: list[dict] = list(done_sections or [])
    start_index = len(out)
    n = len(sections)
    if on_progress and start_index:
        on_progress(start_index, n)
    for i in range(start_index, n):
        sec = sections[i]
        summary = _summarize_long(summarize_fn, sec.get("text", ""), sec.get("title"))
        out.append({"start": sec.get("start"), "title": sec.get("title"), "text": summary})
        if on_section:
            on_section(out)
        if on_progress:
            on_progress(i + 1, n)
    return out
