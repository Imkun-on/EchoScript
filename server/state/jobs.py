"""A che punto e' un lavoro, e cosa resta da fare.

Che differenza c'e' con i parziali
    I parziali (``checkpoints.py``) dicono a che pezzo di audio si era
    arrivati. Questo dice a che FASE si era arrivati: trascritto si',
    tradotto no, riassunto a meta'.

    Servono tutt'e due perche' rispondono a due domande diverse. «Riprendi
    quel video» ha bisogno del pezzo; «di questo video ho gia' il riassunto?»
    ha bisogno della fase.

Perche' e' scritto su disco e non tenuto a mente
    Perche' la domanda arriva quasi sempre dopo aver chiuso e riaperto il
    programma. Uno riapre EchoScript il giorno dopo, incolla lo stesso link, e
    si aspetta che il programma gli dica «questo ce l'hai gia'» invece di
    rifare un'ora di lavoro.

I nomi delle sottocartelle
    Stanno qui in fondo, e non e' una stranezza: sapere DOVE finisce ogni cosa
    fa parte del sapere se quella cosa esiste gia'. Le due domande hanno la
    stessa risposta, quindi vivono accanto.

"""
from __future__ import annotations

import json
import os

from datetime import datetime

from server.state.checkpoints import _checkpoint_key, _checkpoints_dir
from server.utils.text import _lp, _safe_filename

# --- Pipeline state store (the job "database") ------------------------------
# Un unico file JSON per video che traccia l'avanzamento di TUTTE le fasi
# (trascrizione, traduzione, riassunto). I checkpoint qui sopra riguardano solo
# la trascrizione; questo stato è di livello più alto e permette di riprendere
# esattamente dalla sezione in cui ci si è fermati — ad esempio quando i crediti
# Groq finiscono a metà del riassunto. È il "database" del job: JSON atomico e
# ispezionabile, accanto ai checkpoint in results/.checkpoints/.
#
# Le sezioni parziali (già tradotte / già riassunte) vengono salvate DENTRO lo
# stato dopo ogni sezione, così un "Riprendi" ricarica il lavoro già fatto e
# processa solo le sezioni mancanti (nessun credito Groq rispeso su ciò che era
# già pronto).

# Fasi della pipeline, in ordine di esecuzione.
PIPELINE_STAGES = ("transcription", "translation", "summary")

# Stati possibili di una fase: da fare · completata parzialmente · completata ·
# non applicabile (es. traduzione per un audio già in italiano).
STAGE_PENDING = "pending"
STAGE_PARTIAL = "partial"
STAGE_DONE = "done"
STAGE_SKIP = "skip"


def state_path(meta: dict) -> str:
    """Dove sta il foglietto con le fasi gia' fatte di questo video.

    Sta nella stessa cartella dei parziali e con lo stesso nome di base, piu'
    `_state`. I tre file di un video (il parziale di Groq, quello locale, e
    questo) si riconoscono cosi' a colpo d'occhio aprendo la cartella.
    """
    return os.path.join(_checkpoints_dir(), _checkpoint_key(meta) + "_state.json")


def _empty_state(meta: dict, backend: str = "groq") -> dict:
    """Un foglietto nuovo, con tutte le fasi ancora da fare.

    Dentro ci finiscono anche titolo, indirizzo e motore usato, che a rigore
    sarebbero un doppione dei metadati. Il doppione e' voluto: questo file
    viene riletto giorni dopo, quando i metadati non ci sono piu' perche' nessuno
    li ha ricaricati. Senza quei campi, il foglietto direbbe che qualcosa e'
    stato fatto ma non su cosa.
    """
    return {
        "key": _checkpoint_key(meta),
        "title": meta.get("title"),
        "source": meta.get("source"),
        "url": meta.get("webpage_url") or meta.get("source_path"),
        "backend": backend,
        "detected_language": meta.get("detected_language"),
        "stages": {s: {"status": STAGE_PENDING, "done": 0, "total": 0}
                   for s in PIPELINE_STAGES},
        "updated_at": None,
    }


def load_state(meta: dict) -> dict | None:
    """Rilegge il foglietto delle fasi, o None se non c'e' o non si capisce.

    Il controllo sulla forma del contenuto non e' pignoleria. Questo file viene
    scritto e riscritto man mano che le fasi avanzano, e un'interruzione nel
    momento sbagliato puo' lasciare qualcosa che e' json valido ma non e' uno
    stato. Trattarlo come assente fa ricominciare da capo, che e' spiacevole
    ma corretto; fidarsi porterebbe a un errore molto piu' avanti, in un punto
    che con questo file non c'entra niente.
    """
    p = state_path(meta)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("stages"), dict):
            return data
    except Exception:
        return None
    return None


def save_state(meta: dict, state: dict) -> None:
    """Scrive il foglietto delle fasi, con l'ora dell'ultimo aggiornamento.

    Stesso giro dello scrivi-e-rinomina degli altri file di stato: o c'e' tutto
    o non c'e' niente, mai un file a meta'.

    L'orario serve a chi guarda: riaprendo un video lasciato indietro, «fermo
    da tre settimane» e «fermo da dieci minuti» portano a decisioni diverse.
    """
    os.makedirs(_checkpoints_dir(), exist_ok=True)
    p = state_path(meta)
    tmp = p + ".tmp"
    state = dict(state)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, p)


def update_stage(meta: dict, stage: str, *, status=None, done=None, total=None,
                 sections=None, extra=None, backend=None) -> dict:
    """Aggiorna una fase dello stato (creandolo se manca) e lo salva.

    Passa solo i campi che cambiano: 'sections' è la lista delle sezioni già
    completate (traduzione/riassunto) da conservare per il resume; 'extra'
    aggiunge chiavi arbitrarie alla fase (es. 'target' per la traduzione)."""
    state = load_state(meta) or _empty_state(meta, backend or "groq")
    if backend:
        state["backend"] = backend
    if meta.get("detected_language") and not state.get("detected_language"):
        state["detected_language"] = meta.get("detected_language")
    st = state["stages"].setdefault(
        stage, {"status": STAGE_PENDING, "done": 0, "total": 0})
    if status is not None:
        st["status"] = status
    if done is not None:
        st["done"] = done
    if total is not None:
        st["total"] = total
    if sections is not None:
        st["sections"] = sections
    if extra:
        st.update(extra)
    save_state(meta, state)
    return state


def delete_state(meta: dict) -> None:
    """Butta via il foglietto: o il lavoro e' finito, o si ricomincia da capo.

    Sono i due casi in cui non ha piu' senso ricordare a che punto si era, e
    sono opposti fra loro: «ho finito» e «rifai tutto». In tutti e due, quello
    che c'era scritto adesso sarebbe una bugia.

    Un file che non c'era non e' un problema e non si dice niente.
    """
    try:
        os.remove(state_path(meta))
    except OSError:
        pass


def stage_status(state: dict | None, stage: str) -> str:
    """A che punto e' una fase: da fare, a meta', fatta, oppure saltata.

    Regge senza lamentarsi uno stato che non c'e', una fase mai vista e un
    foglietto scritto da una versione precedente del programma: in tutti quei
    casi risponde «da fare». E' la risposta giusta, perche' se non risulta
    fatta allora va fatta.

    La quarta possibilita', «saltata», non e' un fallimento: e' una fase che
    non era stata chiesta. Distinguerla da «da fare» serve perche' «Riprendi»
    non deve mettersi a tradurre un video per cui nessuno aveva chiesto una
    traduzione.
    """
    if not state:
        return STAGE_PENDING
    return state.get("stages", {}).get(stage, {}).get("status", STAGE_PENDING)


def stage_sections(state: dict | None, stage: str) -> list[dict]:
    """I pezzi gia' fatti di una fase rimasta a meta'.

    Serve a riprendere davvero da dove si era: senza questi pezzi, «riprendi»
    saprebbe solo che la fase era incompleta e la rifarebbe tutta.

    Torna sempre una lista, anche quando dentro il file c'era qualcos'altro.
    Chi chiama ci deve girare sopra in un ciclo, e un None a quel punto
    sarebbe un errore in un posto lontano da qui.
    """
    if not state:
        return []
    secs = state.get("stages", {}).get(stage, {}).get("sections")
    return list(secs) if isinstance(secs, list) else []


def resume_sections(meta: dict, stage: str, total: int, key: str, value):
    """Prepara la RIPRESA a sezioni di una fase lunga (traduzione o riassunto).

    Sia la traduzione sia il riassunto lavorano sezione per sezione e salvano il
    parziale dopo ognuna, così un'interruzione (tipicamente i crediti Groq
    esauriti a metà) non fa rispendere lavoro già fatto. Rileggendo quel
    parziale servono sempre le stesse tre cautele:

    1. il parziale vale solo se l'IMPOSTAZIONE con cui era stato prodotto non è
       cambiata — la lingua di destinazione per la traduzione ('target'), la
       lingua del riassunto ('lang'). Se è cambiata, il testo già fatto è nella
       lingua sbagliata e va buttato;
    2. se le sezioni salvate sono PIÙ di quelle attuali (la trascrizione è stata
       rifatta e ora è più corta), la coda in eccesso va tagliata, altrimenti si
       riprenderebbe oltre la fine;
    3. il salvataggio del parziale deve riportare gli stessi campi, o alla
       ripresa successiva la cautela 1 non potrebbe più scattare.

    Restituisce (done_sections, persist) dove 'persist' è la funzione da passare
    come `on_section` a translate_sections/summarize_sections."""
    state = load_state(meta)
    done = stage_sections(state, stage)
    saved = (state or {}).get("stages", {}).get(stage, {}).get(key)
    if saved and saved != value:
        done = []          # impostazione cambiata: il parziale non è riutilizzabile
    if len(done) > total:
        done = done[:total]  # trascrizione più corta di prima: taglia l'eccesso

    def persist(done_list):
        """Scrive sul foglietto i pezzi fatti finora, e li segna come parziali.

        Viene passata a chi sta lavorando perche' la chiami dopo OGNI pezzo,
        non alla fine. E' tutto il senso della cosa: un salvataggio finale non
        servirebbe a niente, visto che il caso da coprire e' proprio quello in
        cui alla fine non ci si arriva.
        """
        update_stage(meta, stage, status=STAGE_PARTIAL, done=len(done_list),
                     total=total, sections=done_list, extra={key: value})

    return done, persist


def resume_plan(state: dict | None) -> dict:
    """Da uno stato salvato, ricava la prima fase incompleta da cui riprendere.

    Ritorna {'stage', 'status', 'done', 'total'} oppure {'stage': None} se non
    c'è nulla da riprendere (tutto completato o nessuno stato). Le fasi 'skip'
    (non applicabili, es. traduzione di un audio già italiano) sono ignorate."""
    if not state:
        return {"stage": None}
    for stage in PIPELINE_STAGES:
        st = state.get("stages", {}).get(stage, {})
        status = st.get("status", STAGE_PENDING)
        if status in (STAGE_PENDING, STAGE_PARTIAL):
            return {"stage": stage, "status": status,
                    "done": int(st.get("done", 0) or 0),
                    "total": int(st.get("total", 0) or 0)}
    return {"stage": None}


def has_resumable_state(meta: dict) -> bool:
    """True se esiste uno stato con almeno una fase da riprendere.

    Serve alla UI (CLI/GUI) per mostrare l'opzione «Riprendi da dove si è
    interrotto» solo quando ha davvero senso."""
    return resume_plan(load_state(meta)).get("stage") is not None


# Subfolder names per interface language: an English user gets English folders
# (transcriptions/translations) instead of the Italian defaults. The CLI is
# Italian-only, so it always uses the "it" names; the GUI passes its current UI
# language down so the folders match what the user sees on screen.
# I nomi delle sottocartelle in cui finisce ogni cosa.
TRANS_SUBDIR = "trascrizioni"
TRANSL_SUBDIR = "traduzioni"
SUMMARY_SUBDIR = "riassunti"
VISUAL_SUBDIR = "analisi_visiva"

# Il pezzo che si aggiunge al nome del file del riassunto.
SUMMARY_SUFFIX = "riassunto"

# I nomi che queste cartelle avevano quando l'interfaccia poteva essere in
# inglese. Non ci si scrive piu' dentro, ma si continua a GUARDARCI.
#
# Il motivo non e' nostalgia: chi aveva gia' trascritto dei video con
# l'interfaccia in inglese ha quelle cartelle sul proprio disco, con dentro il
# proprio lavoro. Togliendo questa riga il programma gli direbbe che quei video
# non li ha mai fatti, e glieli rifarebbe da capo.
NOMI_VECCHI = {
    TRANS_SUBDIR: "transcriptions",
    TRANSL_SUBDIR: "translations",
    SUMMARY_SUBDIR: "summaries",
    VISUAL_SUBDIR: "visual_analysis",
}


def trans_subdir() -> str:
    """Il nome della sottocartella delle trascrizioni.

    E' una funzione e non il nome scritto direttamente nei punti che lo usano,
    per una ragione che vale anche per le tre sorelle qui sotto: sono una
    decina i posti che compongono quel percorso, e il giorno in cui la cartella
    cambiasse nome, cercarne dieci occorrenze in un programma intero e'
    esattamente il modo in cui se ne dimentica una.
    """
    return TRANS_SUBDIR


def transl_subdir() -> str:
    """Il nome della sottocartella delle traduzioni.

    Funzione e non costante scritta nei punti d'uso, per lo stesso motivo
    spiegato in trans_subdir.
    """
    return TRANSL_SUBDIR


def summary_subdir() -> str:
    """Il nome della sottocartella dei riassunti.

    Funzione e non costante scritta nei punti d'uso, per lo stesso motivo
    spiegato in trans_subdir.
    """
    return SUMMARY_SUBDIR


def visual_subdir() -> str:
    """Il nome della sottocartella dell'analisi visiva.

    Funzione e non costante scritta nei punti d'uso, per lo stesso motivo
    spiegato in trans_subdir.
    """
    return VISUAL_SUBDIR


def transcription_exists(out_root: str, title: str) -> bool:
    """True se in out_root/<titolo>/<trascrizioni>/ ci sono già file trascritti.

    Controlla TUTTI i possibili nomi cartella (italiano e inglese), così il
    rilevamento funziona anche se il video era stato trascritto con l'interfaccia
    in un'altra lingua."""
    base = os.path.join(out_root, _safe_filename(title))
    for sub in (TRANS_SUBDIR, NOMI_VECCHI[TRANS_SUBDIR]):
        d = os.path.join(base, sub)
        if os.path.isdir(_lp(d)) and any(
                n.lower().endswith((".md", ".txt", ".json", ".pdf")) for n in os.listdir(_lp(d))):
            return True
    return False


def load_existing_transcript(out_root: str, title: str):
    """Rilegge una trascrizione salvata (dal .json) e ricostruisce
    (meta, segments, engine_label), sufficienti a rigenerare SOLO la traduzione
    senza ri-trascrivere (e senza rispendere crediti). None se assente/vuota.

    Cerca il .json in tutti i possibili nomi cartella (italiano e inglese)."""
    safe = _safe_filename(title)
    p = None
    for sub in (TRANS_SUBDIR, NOMI_VECCHI[TRANS_SUBDIR]):
        cand = os.path.join(out_root, safe, sub, safe + ".json")
        if os.path.isfile(_lp(cand)):
            p = cand
            break
    if not p:
        return None
    try:
        with open(_lp(p), "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None
    segments = d.get("segments") or []
    if not segments:
        return None
    meta = {
        "id": "", "title": d.get("title", title),
        "channel": d.get("channel"), "views": d.get("views"),
        "upload_date": d.get("upload_date"), "duration": d.get("duration_seconds"),
        "chapters": [{"start_time": c.get("start"), "end_time": c.get("end"),
                      "title": c.get("title")} for c in (d.get("chapters") or [])],
        "webpage_url": d.get("url", ""), "source": d.get("source", "youtube"),
    }
    return meta, segments, d.get("engine", "?")


def load_existing_translation(out_root: str, title: str, target: str = "it"):
    """Rilegge le SEZIONI di una traduzione già salvata (dal .json), o None.

    Serve a «Solo riassunto» per riassumere la TRADUZIONE invece dell'originale.
    Cerca `<titolo>_<target>.json` in tutti i possibili nomi cartella traduzioni
    (italiano/inglese). Restituisce la lista di sezioni {start,title,text}."""
    safe = _safe_filename(title)
    for sub in (TRANSL_SUBDIR, NOMI_VECCHI[TRANSL_SUBDIR]):
        p = os.path.join(out_root, safe, sub, f"{safe}_{target}.json")
        if os.path.isfile(_lp(p)):
            try:
                with open(_lp(p), "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            sections = data.get("sections")
            if sections:
                return sections
    return None


# Etichette leggibili delle fasi, per i messaggi di ripresa (CLI e GUI).
STAGE_LABELS_IT = {
    "transcription": "trascrizione", "translation": "traduzione", "summary": "riassunto",
}
def resume_info_text(meta: dict) -> str:
    """Breve testo «da dove riprende» per il video, o "" se non c'è nulla.

    Es. "riassunto — sezione 8/20". Usato nei menu CLI/GUI per spiegare all'utente
    cosa farà «Riprendi da dove si è interrotto»."""
    plan = resume_plan(load_state(meta))
    stage = plan.get("stage")
    if not stage:
        return ""
    labels = STAGE_LABELS_IT
    name = labels.get(stage, stage)
    done, total = plan.get("done", 0), plan.get("total", 0)
    if total and plan.get("status") == STAGE_PARTIAL:
        sec = "sezione"
        return f"{name} — {sec} {done + 1}/{total}"
    return name
