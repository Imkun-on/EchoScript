"""Il riassunto: le istruzioni che si danno al modello.

Cosa c'e' qui dentro
    Quasi soltanto testo. Sono le regole che il modello deve seguire mentre
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
    "Pulizia del testo: elimina intercalari, riempitivi ed esitazioni (ehm, "
    "uhm, cioè, tipo, no?, allora, insomma) e rimuovi ripetizioni, frasi "
    "interrotte e autocorrezioni di chi parla, conservando soltanto la versione "
    "corretta e definitiva di ciascun passaggio.\n"
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
    "Stile e struttura: redigi il riassunto in prosa continua e articolata, "
    "privilegiando un testo discorsivo che ricostruisca con ricchezza il filo "
    "del discorso e ne approfondisca i passaggi anziché comprimerli. Punta a un "
    "riassunto esteso e particolareggiato, non a una sintesi telegrafica. "
    "Per facilitare la lettura, evidenzia in grassetto Markdown (**testo**) "
    "soltanto le parole o le brevissime locuzioni chiave — concetti centrali, "
    "termini tecnici, nomi propri e cifre rilevanti — usando il grassetto con "
    "parsimonia e mai su intere frasi (deve risaltare, non saturare il testo). "
    "Ricorri agli elenchi puntati solo quando indispensabili (ad esempio per "
    "enumerazioni di voci eterogenee presenti nell'originale) e mai come "
    "struttura predefinita. Mantieni un registro professionale, chiaro e coeso, "
    "con transizioni fluide tra i concetti.\n"
    "Vincoli di output: rispondi esclusivamente con il riassunto, senza "
    "preamboli, intestazioni o commenti. Non aprire mai il testo con formule "
    "del tipo \"Ecco i punti chiave\", \"In questo video si parla di\" o simili: "
    "entra direttamente nel contenuto."
)

# Estensione del prompt usata quando il testo contiene anche le note dell'ANALISI
# VISIVA: istruisce il modello a integrare codice, formule e diagrammi visti a
# schermo e ad aggiungere una mappa concettuale quando il contenuto è visuale.
_SUMMARY_VISUAL_BASE = (
    "\nIl testo può contenere annotazioni nel formato «[A SCHERMO — mm:ss] …» che "
    "riportano ciò che era VISIBILE nel video in quel momento (codice, formule, "
    "grafici, diagrammi, slide). Trattale come fonte attendibile quanto il parlato "
    "e INTEGRALE nel riassunto in modo naturale, secondo queste regole aggiuntive:\n"
    "• riporta il CODICE in blocchi markdown delimitati da ``` con il linguaggio "
    "indicato, preservandolo fedelmente;\n"
    "• scrivi le FORMULE e le relative dimostrazioni in LaTeX (`$...$` in linea, "
    "`$$...$$` per i passaggi), includendo tutti i passaggi mostrati;\n"
    "• descrivi GRAFICI, DIAGRAMMI e TABELLE riportandone dati, assi, relazioni e "
    "la conclusione.\n"
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
    "prosa, elenchi essenziali, codice e formule."
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
    """Le regole del riassunto quando c'e' solo il parlato."""
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
    """Quello da usare in questo momento: il visivo se c'e', il base altrimenti."""
    return PROMPT_ATTIVO or prompt_base()
