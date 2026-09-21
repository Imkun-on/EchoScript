"""I messaggi che raccontano cosa sta succedendo, mentre succede.

A cosa servono
    Sono le righe che compaiono nel diario e sotto la barra di avanzamento:
    «Scarico audio», «Blocco 3/12 completato», «Traduzione interrotta».

    Stanno tutte qui e non sparse nel codice che le produce, per lo stesso
    motivo per cui ci stanno le frasi dell'interfaccia: chi vuole cambiare una
    parola apre questo file, invece di cercare in quale funzione era finita.

Perche' sono separate dalle frasi dell'interfaccia
    Perche' le usano due mondi diversi. Le frasi di ``strings.py`` le mostra la
    pagina, e arrivano tutte insieme all'avvio. Queste le produce il motore
    mentre lavora, e passano da un'altra strada: il motore le consegna a chi lo
    ha chiamato, che decide se scriverle in un terminale o mandarle a una
    finestra.

    E' anche il motivo per cui il motore puo' girare senza nessuna interfaccia:
    non sa a chi le sta dando.

Erano in due lingue
    Il motore doveva parlare la lingua dell'interfaccia, quindi ogni messaggio
    aveva la sua copia inglese. Da quando il programma parla solo italiano
    quella meta' non la leggeva piu' nessuno, e la funzione ``msg`` non ha piu'
    bisogno di sapere in che lingua scrivere: ce n'e' una sola.

I buchi nelle frasi
    Le graffe, tipo ``{i}`` e ``{n}``, le riempie chi chiama passando i valori
    per nome. Scriverli col nome e non con la posizione serve a chi legge
    questo file: si capisce cosa andra' a finire li' dentro senza dover trovare
    chi chiama.
"""
from __future__ import annotations


# Il catalogo. Le chiavi sono raggruppate per fase del lavoro, nello stesso
# ordine in cui le fasi si susseguono: cercando il messaggio di un passaggio si
# guarda dove quel passaggio avviene, invece di scorrere l'elenco intero.
#
# La riga di comando non passa di qui: ha i suoi pannelli colorati, scritti sul
# posto, perche' un terminale puo' mostrare cose che una finestra non puo' e
# viceversa.
_RUNTIME_MSGS = {
    # download / lettura sorgente
    "dl_audio":       "Scarico audio",
    "extract_audio":  "Estraggo audio",
    "convert_audio":  "Converto audio in m4a",
    "dl_video":       "Scarico video",
    "prep_video":     "Preparo il video",
    "read_audio":     "Leggo il file audio",
    "read_info":      "Leggo le informazioni del video",
    # trascrizione
    "chunk_prep":     "Blocco {i}/{n}",
    "chunk_send":     "Invio blocco {i}/{n} a Groq",
    "chunk_done":     "Blocco {i}/{n} completato",
    "model_load":     "Carico il modello '{model}' su {dev}{note} (primo uso: scarica i pesi)",
    "resume_from":    " (ripresa da {ts})",
    "transcribing":   "Trascrizione in corso",
    "transcribed":    "Trascrizione completata",
    # traduzione
    "translating_to": "Traduco in {lang}",
    "section_tr":     "Sezione {i}/{n} tradotta",
    "tr_unavail":     "Traduzione non disponibile: {e}",
    "tr_interrupted": "Traduzione interrotta ({e}); parziale salvato, riprendibile.",
    "tr_pdf_fail":    "PDF della traduzione non creato: {e}",
    "audio_already":  "Audio già in {lang}: traduzione non necessaria.",
    # riassunto
    "summarizing":    "Riassumo le sezioni",
    "section_sum":    "Sezione {i}/{n} riassunta",
    "sum_unavail":    "Riassunto non disponibile: {e}",
    "sum_ratelimit":  "Crediti Groq esauriti: riassunto interrotto e salvato come parziale, riprendibile (anche in locale).",
    "sum_fail":       "Riassunto fallito: {e}",
    "sum_pdf_fail":   "PDF del riassunto non creato: {e}",
    # salvataggio
    "saving_files":   "Salvo i file",
    "creating_pdf":   "Creo il PDF",
    "trans_pdf_fail": "PDF della trascrizione non creato: {e}",
    # analisi visiva
    "vis_unavail":    "Analisi visiva non disponibile: {e}",
    "vis_detect":     "Individuo i fotogrammi chiave (cambi scena)…",
    "vis_noframes":   "Nessun fotogramma significativo individuato",
    "vis_toanalyze":  "{n} fotogrammi da analizzare ({label})",
    "vis_ratelimit":  "Crediti Groq esauriti durante l'analisi visiva",
    "vis_analyzing":  "Analizzo fotogramma {i}/{n}",
    "vis_extracted":  "{k} contenuti visivi estratti su {n} fotogrammi",
    "vis_skipped":    "Analisi visiva saltata: il video non era disponibile (sorgente solo-audio o download video non riuscito).",
    "vis_incomplete": "Analisi visiva non completata: {e}",
    # motivi di fallimento dell'analisi visiva (_visual_failure_reason)
    "vfr_ratelimit":  "Analisi visiva interrotta: crediti {eng} esauriti. I crediti del modello vision sono SEPARATI da quelli di trascrizione/riassunto. Riprova quando si azzerano (vedi «crediti») o usa un modello vision locale via Ollama.",
    "vfr_eng_groq":   "Groq (qwen vision)",
    "vfr_eng_other":  "del modello vision",
    "vfr_noframes":   "Analisi visiva: nessun fotogramma significativo individuato nel video.",
    "vfr_allerrors":  "Analisi visiva non riuscita: il modello vision ha restituito errore su tutti i {n} fotogrammi ({err}).",
    "vfr_notech":     "Analisi visiva: nessun contenuto tecnico (codice/formule/grafici) rilevato nei {n} fotogrammi analizzati.",
    "vfr_unknown_err":"errore sconosciuto",
}


def msg(key: str, **fmt) -> str:
    """Il messaggio che sta dietro una chiave, coi buchi riempiti.

    I buchi sono le graffe dentro la frase, e si riempiono passandoli per nome:
    ``msg("chunk_done", i=3, n=12)``.

    Una chiave che non esiste torna indietro cosi' com'e', invece di far
    cadere il programma. A schermo si leggerebbe qualcosa tipo ``chunk_donee``,
    che e' brutto ma dice subito dove si e' sbagliato a scrivere; e soprattutto
    non interrompe una trascrizione di due ore per un errore di battitura in
    una riga di diario.
    """
    testo = _RUNTIME_MSGS.get(key) or key
    return testo.format(**fmt) if fmt else testo
