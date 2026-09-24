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

Le regole di base, e le due aggiunte che si scelgono
    ``prompt_riassunto(grafici, commenti)`` compone le istruzioni per UN
    lavoro: le regole di base, piu' due aggiunte che si accendono dalla
    finestra, lavoro per lavoro:

    ``grafici``   quando il testo contiene numeri che si capiscono meglio a
                  colpo d'occhio (una statistica, una serie nel tempo, i valori
                  di una funzione), il modello aggiunge un grafico Mermaid, che
                  il PDF disegna davvero;
    ``commenti``  dentro i blocchi di codice il modello aggiunge commenti
                  brevi sulle righe che non si spiegano da sole.

Perche' le istruzioni viaggiano col lavoro e non stanno in una variabile
    C'era una variabile di modulo, PROMPT_ATTIVO, che chi metteva in fila il
    lavoro riempiva e poi svuotava. Con due postazioni che possono riassumere
    nello stesso momento sarebbe stata una gara: il riassunto di «Locale»
    avrebbe potuto usare le istruzioni scelte in «Cloud». Adesso le istruzioni
    si chiudono dentro la funzione che riassume, al momento di crearla, e
    ogni lavoro ha le sue.

Perche' era anche in inglese, e perche' non lo e' piu'
    Il riassunto seguiva la lingua dell'interfaccia, quindi di ogni regola
    esisteva una seconda copia in inglese, lunga uguale. Da quando il programma
    parla solo italiano quelle copie non le raggiungeva piu' nessuno: erano
    settanta righe di testo che nessun modello avrebbe mai letto.
"""
from __future__ import annotations

import json
import math
import re
import time

from server.config import settings
from server.config.settings import (
    OLLAMA_HOST, OLLAMA_NUM_CTX, SUMMARY_MAX_CHARS,
)
from server.utils.console import console
from server.utils.contract import GroqRateLimit, _is_rate_limit
from server.enrichment.translation import _split_for_translation
from server.state.credits import (
    aggiungi_consumo, aspetta, attesa_breve, ora_di_ripresa, record_rate_limits,
    registra_da_errore,
)
from server.utils.ollama import _check_ollama


# Dal testo italiano (la traduzione, oppure la trascrizione se l'audio era già
# italiano) produce un riassunto PER SEZIONE: pulisce intercalari, ripetizioni e
# autocorrezioni e tiene i concetti. Groq usa un modello di chat; in locale ci si
# appoggia a Ollama (nessuna dipendenza pip aggiuntiva: si parla via HTTP).

# Quanto dev'essere lungo il riassunto: si sceglie dalla finestra, lavoro per
# lavoro. Ogni misura sostituisce per intero il paragrafo «Stile e struttura»
# delle istruzioni, perche' non e' solo una lunghezza: cambia anche la forma
# (prosa distesa, prosa compatta, solo punti). La regola sul grassetto e sui
# sottotitoli sta in tutte, perche' vale per tutte.
_GRASSETTO = (
    "Per facilitare la lettura, evidenzia in grassetto Markdown (**testo**) "
    "soltanto le parole o le brevissime locuzioni chiave (concetti centrali, "
    "termini tecnici, nomi propri e cifre rilevanti) usando il grassetto con "
    "parsimonia e mai su intere frasi (deve risaltare, non saturare il testo). "
)
DETTAGLI = {
    # Quella di sempre, ed e' il valore di partenza.
    "esteso": (
        "Stile e struttura: redigi il riassunto in prosa continua e articolata, "
        "privilegiando un testo discorsivo che ricostruisca con ricchezza il filo "
        "del discorso e ne approfondisca i passaggi anziché comprimerli. Punta a un "
        "riassunto esteso e particolareggiato, non a una sintesi telegrafica. "
        + _GRASSETTO +
        "Quando la sezione affronta più argomenti distinti puoi separarli con un "
        "sottotitolo «### Titolo» su riga propria. Mantieni un registro "
        "professionale, chiaro e coeso, con transizioni fluide tra i concetti.\n"
    ),
    "normale": (
        "Stile e struttura: redigi il riassunto in prosa chiara e scorrevole, di "
        "lunghezza media: indicativamente un terzo del testo di partenza. Tieni "
        "tutti i concetti, i dati e gli esempi importanti, ma senza soffermarti sui "
        "passaggi secondari e senza ripetere ciò che è già stato detto. "
        + _GRASSETTO +
        "Quando la sezione affronta più argomenti distinti puoi separarli con un "
        "sottotitolo «### Titolo» su riga propria. Mantieni un registro "
        "professionale, chiaro e coeso.\n"
    ),
    "breve": (
        "Stile e struttura: redigi un riassunto BREVE e compatto: pochi paragrafi "
        "essenziali, indicativamente un decimo del testo di partenza. Tieni solo i "
        "concetti principali, le conclusioni e i dati decisivi; lascia fuori esempi "
        "secondari, digressioni e dettagli. Codice e formule restano, ma solo quelli "
        "indispensabili a capire. " + _GRASSETTO + "Niente sottotitoli.\n"
    ),
    "punti": (
        "Stile e struttura: il riassunto è SOLTANTO un elenco puntato di punti "
        "chiave, pensato per un ripasso veloce. Una voce per ogni concetto "
        "importante, aperta da «- », lunga una o due frasi, con il termine chiave in "
        "**grassetto** all'inizio della voce. Niente paragrafi di prosa e niente "
        "sottotitoli: questa regola vince su quella degli elenchi qui sopra. Il "
        "codice e le formule indispensabili vanno in blocco subito sotto la voce "
        "che li introduce.\n"
    ),
}
DETTAGLIO_PREDEFINITO = "esteso"
_STILE_SEGNAPOSTO = "\x00STILE\x00"

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
    + _STILE_SEGNAPOSTO +
    "Markdown ammesso: soltanto il **grassetto**, i sottotitoli «### », gli "
    "elenchi puntati «- », i blocchi ``` e le formule `$`/`$$` (più i grafici "
    "```mermaid, ma solo se le regole qui sotto li ammettono). NON usare il "
    "corsivo con asterischi singoli (*testo*), né tabelle, né note a piè di "
    "pagina, né link.\n"
    "Vincoli di output: rispondi esclusivamente con il riassunto, senza "
    "preamboli, intestazioni o commenti. Non aprire mai il testo con formule "
    "del tipo \"Ecco i punti chiave\", \"In questo video si parla di\" o simili: "
    "entra direttamente nel contenuto."
)

# Aggiunta per i GRAFICI. Mermaid ne sa disegnare parecchi tipi, ma se ne
# ammettono due soli, scritti con un modello preciso: sono quelli che i modelli
# sbagliano meno, e quelli che il PDF disegna in modo affidabile. Tutto il resto
# (flowchart, mappe concettuali) viene tolto dopo, da _pulisci_diagrammi.
_REGOLA_GRAFICI = (
    "\nGrafici: quando la sezione contiene dati numerici che si capiscono meglio "
    "a colpo d'occhio (una statistica, percentuali che compongono un totale, un "
    "confronto fra quantità, una serie che cambia nel tempo, i valori di una "
    "funzione in una dimostrazione di matematica o di fisica), aggiungi UN "
    "grafico subito dopo il paragrafo che spiega quei dati, in un blocco "
    "```mermaid. Usa SOLO numeri detti esplicitamente nel testo, oppure "
    "calcolabili esattamente dalle formule del testo (di una funzione puoi "
    "calcolare da 5 a 10 punti): se i dati mancano o sono vaghi, il grafico NON "
    "si fa. Al massimo un grafico per sezione, e nessun grafico se non aggiunge "
    "niente a quello che il testo dice già. Sono ammesse soltanto queste due "
    "forme, scritte esattamente così:\n"
    "• barre o linee:\n"
    "```mermaid\n"
    "xychart-beta\n"
    "    title \"Titolo breve\"\n"
    "    x-axis [\"Voce 1\", \"Voce 2\", \"Voce 3\"]\n"
    "    y-axis \"Unità di misura\"\n"
    "    bar [12, 45, 80]\n"
    "```\n"
    "per un andamento usa `line` al posto di `bar`; le etichette dell'asse x "
    "vanno sempre fra virgolette doppie; i valori sono numeri puri, con il punto "
    "come separatore decimale, senza unità, senza % e senza virgolette, e sono "
    "tanti quante le etichette;\n"
    "• torta, soltanto per le parti di un totale:\n"
    "```mermaid\n"
    "pie title Titolo breve\n"
    "    \"Voce A\" : 40\n"
    "    \"Voce B\" : 60\n"
    "```\n"
    "Nessun altro tipo di diagramma: niente flowchart, niente mappe concettuali. "
    "Il grafico accompagna la spiegazione e non la sostituisce: i numeri "
    "importanti restano scritti anche nel testo."
)
_REGOLA_NO_GRAFICI = (
    "\nNON generare grafici, diagrammi, mappe concettuali né blocchi ```mermaid."
)

# Aggiunta per i COMMENTI nel codice. Il vincolo che conta e' l'ultimo: il
# codice e' quello che e' stato detto, e un commento che «migliora» un'istruzione
# cambiandola sarebbe un'invenzione travestita da spiegazione.
_REGOLA_COMMENTI = (
    "\nCommenti nel codice: dentro ogni blocco di codice aggiungi commenti brevi, "
    "in italiano e nella sintassi del linguaggio (# per Python, bash e YAML, // "
    "per JavaScript, TypeScript, Java, C, C++, C#, Go e Rust, -- per SQL), sulle "
    "righe che non si capiscono da sole: che cosa fa un'istruzione, a che cosa "
    "serve un parametro, che cosa contiene una variabile. Non commentare "
    "l'ovvio e non mettere un commento su ogni riga. Il codice resta quello "
    "detto: si aggiungono soltanto commenti, senza cambiare, aggiungere o "
    "togliere istruzioni. La spiegazione in prosa prima e dopo il blocco resta."
)


def prompt_base(dettaglio: str | None = None) -> str:
    """Le regole del riassunto senza nessuna aggiunta, alla misura scelta.

    E' una funzione e non il testo letto direttamente, cosi' chi lo usa passa
    sempre dalla stessa porta. Una misura sconosciuta vale quella di partenza.
    """
    stile = DETTAGLI.get(dettaglio or DETTAGLIO_PREDEFINITO,
                         DETTAGLI[DETTAGLIO_PREDEFINITO])
    return _SUMMARY_SYSTEM_PROMPT.replace(_STILE_SEGNAPOSTO, stile)


def prompt_riassunto(grafici: bool | None = None, commenti: bool | None = None,
                     dettaglio: str | None = None) -> str:
    """Le regole per UN lavoro: quelle di base piu' le aggiunte scelte.

    None vuol dire «come dicono le impostazioni» (SUMMARY_CHARTS e
    SUMMARY_CODE_COMMENTS), che e' quello che usa la riga di comando; la
    finestra passa invece le scelte fatte con gli interruttori. 'dettaglio' e'
    una delle chiavi di DETTAGLI (None = esteso, com'era sempre stato).
    """
    if grafici is None:
        grafici = settings.SUMMARY_CHARTS
    if commenti is None:
        commenti = settings.SUMMARY_CODE_COMMENTS
    testo = prompt_base(dettaglio)
    testo += _REGOLA_GRAFICI if grafici else _REGOLA_NO_GRAFICI
    if commenti:
        testo += _REGOLA_COMMENTI
    return testo


# =============================================================================
#  I diagrammi nel testo che torna dal modello
# =============================================================================

_BLOCCO_MERMAID = re.compile(r"```mermaid[^\n]*\n(.*?)```[ \t]*\n?", re.S)


def _ripulisci_grafico(corpo: str) -> str | None:
    """Un grafico ripulito dagli errori tipici, o None se va buttato.

    I modelli sbagliano sempre le stesse cose: scrivono `xychart` senza il
    `-beta` che Mermaid 10 pretende, mettono il simbolo % dentro i valori,
    dimenticano l'asse x. Le prime due si correggono qui; un grafico senza
    dati o di un tipo non ammesso si toglie, perche' nel PDF diventerebbe un
    riquadro con un messaggio d'errore al posto del disegno.
    """
    righe = [r.rstrip() for r in (corpo or "").strip().splitlines() if r.strip()]
    if not righe:
        return None
    testa = righe[0].strip()
    if testa.lower().startswith("pie"):
        voce = re.compile(r'^\s*("[^"]+")\s*:\s*(-?[0-9.,]+)\s*%?\s*$')
        fuori, voci = [testa], 0
        for r in righe[1:]:
            m = voce.match(r)
            if m:
                valore = m.group(2).replace(",", ".")
                if not re.fullmatch(r"-?\d+(\.\d+)?", valore):
                    return None
                r = f"    {m.group(1)} : {valore}"
                voci += 1
            fuori.append(r)
        return "\n".join(fuori) if voci >= 2 else None
    if testa.lower().startswith("xychart"):
        righe[0] = "xychart-beta" + testa[len(testa.split()[0]):]
        numeri: list[float] = []
        barre = False
        for i, r in enumerate(righe):
            m = re.match(r"^(\s*)(bar|line)(\s+[^\[]*)?\[(.*)\]\s*$", r)
            if m:
                valori = [v.replace("%", "").strip() for v in m.group(4).split(",")]
                if not all(re.fullmatch(r"-?\d+(\.\d+)?", v) for v in valori):
                    return None
                righe[i] = f"{m.group(1) or '    '}{m.group(2)}{m.group(3) or ' '}[{', '.join(valori)}]"
                numeri += [float(v) for v in valori]
                barre = barre or m.group(2) == "bar"
        if not numeri or not any(r.strip().startswith("x-axis") for r in righe):
            return None
        if barre:
            righe = _asse_da_zero(righe, numeri)
        return "\n".join(righe)
    return None


def _asse_da_zero(righe: list[str], numeri: list[float]) -> list[str]:
    """Fa partire da zero l'asse verticale di un grafico a barre.

    Mermaid, lasciato fare, fa cominciare l'asse dal valore piu' piccolo: con
    120, 180, 150 e 210 la prima barra risulta alta zero e la seconda sembra
    il triplo della terza. E' il modo classico in cui un grafico a barre
    racconta una cosa falsa. Se l'asse dice gia' il suo intervallo lo si
    lascia com'e'; altrimenti si scrive da 0 a un tetto tondo sopra il massimo.
    """
    massimo, minimo = max(numeri), min(0.0, min(numeri))
    if massimo <= 0:
        return righe
    passo = 10 ** math.floor(math.log10(massimo)) / 2
    tetto = math.ceil(massimo / passo) * passo
    intervallo = f"{minimo:g} --> {tetto:g}"
    for i, r in enumerate(righe):
        if r.strip().startswith("y-axis"):
            if "-->" not in r:
                righe[i] = f"{r.rstrip()} {intervallo}"
            return righe
    indice = next(i for i, r in enumerate(righe) if r.strip().startswith("x-axis"))
    return righe[:indice + 1] + [f"    y-axis {intervallo}"] + righe[indice + 1:]


def _pulisci_diagrammi(testo: str, grafici: bool) -> str:
    """Tiene i grafici ammessi e toglie ogni altro diagramma.

    E' una rete di sicurezza. Anche quando le istruzioni li vietano, i modelli
    ogni tanto disegnano lo stesso una mappa o un flowchart; lasciarli passare
    vorrebbe dire una ventina di righe di sintassi incomprensibile in mezzo al
    riassunto, o un riquadro d'errore nel PDF.
    """
    def _sostituisci(m):
        """Il blocco ripulito, o niente se va tolto."""
        if not grafici:
            return ""
        buono = _ripulisci_grafico(m.group(1))
        return f"```mermaid\n{buono}\n```\n" if buono else ""
    fuori = _BLOCCO_MERMAID.sub(_sostituisci, testo or "")
    # Un blocco tolto lascia dietro le sue righe vuote: se ne tiene una sola.
    return re.sub(r"\n{3,}", "\n\n", fuori).strip()


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
def _groq_chat_capture(client, model: str, on_attesa=None, **kwargs):
    """client.chat.completions.create che, quando possibile, registra i crediti
    residui del modello dagli header x-ratelimit-* (per il pulsante "crediti"),
    SENZA costo aggiuntivo. Restituisce l'oggetto risposta già parsato, come la
    create() classica.

    Il client non riprova piu' da solo (``max_retries=0``, vedi
    make_groq_client), quindi le due attese si decidono qui:

    - Groq dice «limite al minuto, riprova fra 20 secondi»: si aspetta, e
      'on_attesa(secondi_rimasti)' lo dice a schermo ogni secondo;
    - Groq dice «crediti finiti fino a stasera»: si solleva subito
      GroqRateLimit, che il chiamante trasforma nell'avviso e nel parziale
      salvato.

    Un guasto di rete o del server si riprova due volte, con una pausa breve:
    era quello che faceva il client da solo, e non va perso."""
    attese = guasti = 0
    while True:
        try:
            try:
                raw = client.chat.completions.with_raw_response.create(model=model, **kwargs)
            except Exception as e:
                msg = str(e)
                if _is_rate_limit(msg) or any(c in msg for c in _DEFINITIVI):
                    raise
                # La variante che legge le intestazioni ha dato un errore suo:
                # si ripiega sulla chiamata normale, senza i crediti.
                return _conta_token(client.chat.completions.create(model=model, **kwargs))
            try:
                record_rate_limits(model, raw.headers)
            except Exception:
                pass
            return _conta_token(raw.parse())
        except Exception as e:
            msg = str(e)
            if _is_rate_limit(msg):
                registra_da_errore(model, e)
                breve = attesa_breve(e)
                if breve is not None and attese < 3:
                    attese += 1
                    aspetta(breve, on_attesa)
                    continue
                raise GroqRateLimit(msg, ora_di_ripresa(e)) from e
            if not any(c in msg for c in _DEFINITIVI) and guasti < 2:
                guasti += 1
                time.sleep(2 * guasti)
                continue
            raise


def _conta_token(risposta):
    """Somma i token di questa risposta al conto del lavoro, e la restituisce."""
    try:
        aggiungi_consumo(token=risposta.usage.total_tokens)
    except Exception:
        pass
    return risposta


# Gli errori che riprovare non sistema: richiesta sbagliata, chiave rifiutata,
# modello inesistente, testo troppo lungo.
_DEFINITIVI = ("400", "401", "403", "404", "413")


def _summarize_groq(client, text: str, section_title: str | None,
                    sistema: str | None = None, on_attesa=None) -> str:
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
        client, settings.GROQ_SUMMARY_MODEL, on_attesa=on_attesa,
        messages=[
            {"role": "system", "content": sistema or prompt_riassunto()},
            {"role": "user", "content": _summary_user_prompt(text, section_title)},
        ],
        temperature=0.3,
    )
    return (resp.choices[0].message.content or "").strip()


def _summarize_ollama(text: str, section_title: str | None,
                      sistema: str | None = None) -> str:
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
            {"role": "system", "content": sistema or prompt_riassunto()},
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


def _make_summarizer(client=None, grafici: bool | None = None,
                     commenti: bool | None = None, on_attesa=None,
                     dettaglio: str | None = None):
    """Sceglie il motore del riassunto e restituisce (funzione, etichetta).

    Preferisce Groq se è disponibile un client (backend cloud); altrimenti usa
    Ollama in locale (100% offline). Solleva RuntimeError se nessuno è utilizzabile.

    'grafici' e 'commenti' decidono le aggiunte alle istruzioni (None = come
    dicono le impostazioni). Le istruzioni si compongono QUI, una volta, e
    restano chiuse dentro la funzione restituita: ogni lavoro ha le sue, anche
    quando le due postazioni riassumono insieme. 'on_attesa' riceve il conto
    alla rovescia quando Groq chiede di aspettare il limite al minuto."""
    sistema = prompt_riassunto(grafici, commenti, dettaglio)
    if client is not None:
        label = f"Riassunto automatico (Groq · {settings.GROQ_SUMMARY_MODEL})"
        return (lambda text, title: _summarize_groq(client, text, title, sistema,
                                                    on_attesa)), label
    _check_ollama()
    label = f"Riassunto automatico (locale · Ollama {settings.OLLAMA_MODEL})"
    return (lambda text, title: _summarize_ollama(text, title, sistema)), label


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
