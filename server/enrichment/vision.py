"""Leggere quello che nel video si VEDE e non si sente.

Il problema che risolve
    In una lezione di programmazione o in una spiegazione con le slide, meta'
    del contenuto non viene detto a voce: e' scritto a schermo. Il codice, le
    formule, i grafici, i diagrammi. Una trascrizione fedele di quello che si
    sente, in quei video, perde proprio la parte che si voleva studiare, e chi
    la legge trova frasi tipo "come vedete qui" senza nessun qui.

Come funziona, in tre passi
    1. Si tirano fuori dal video i fotogrammi in cui l'immagine CAMBIA, non uno
       ogni tot secondi. Una slide che resta ferma due minuti vale un
       fotogramma solo, non centoventi.

    2. Ogni fotogramma viene mandato a un modello che sa guardare le immagini,
       insieme a un pezzo del parlato di quel momento. Il parlato serve da
       contesto: la stessa schermata di codice significa cose diverse a seconda
       di cosa si stava spiegando.

    3. Le note che tornano indietro vengono intrecciate al testo, nel punto
       giusto della trascrizione.

Perche' i fotogrammi vicini vengono uniti
    Perche' un cambio di inquadratura produce spesso tre o quattro fotogrammi
    quasi identici a mezzo secondo di distanza. Mandarli tutti costerebbe
    quattro volte tanto per avere quattro volte la stessa nota.

Perche' le note vuote vengono buttate
    Perche' un modello a cui si mostra una faccia che parla risponde comunque
    qualcosa, tipo "si vede una persona che parla". Non e' falso, e' inutile, e
    in un riassunto fa solo rumore.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time

from rich.progress import (
    BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn,
)

from server.config import settings
from server.config.messages import msg
from server.config.settings import (
    CONCEPT_MAP, OLLAMA_HOST, OLLAMA_NUM_CTX, RICH_PDF, SUMMARY_FRAMES, VISION_FALLBACK_INTERVAL, VISION_FRAME_WIDTH,
    VISION_MAX_FRAMES, VISION_MIN_GAP, VISION_SCENE_THRESHOLD,
)
from server.enrichment.summary import _groq_chat_capture
from server.state.credits import record_rate_limits
from server.export.pdf_rich import build_pdf_rich
from server.state.jobs import NOMI_VECCHI, VISUAL_SUBDIR, visual_subdir
from server.utils.console import SYM_FAIL, SYM_OK, console
from server.utils.contract import (
    GroqRateLimit, _is_rate_limit, _noop_progress, fermarsi,
)
from server.utils.ffmpeg import _probe_duration
from server.utils.ollama import _ollama_has_model, _ollama_installed_models
from server.utils.text import _format_timestamp, _lp, _safe_filename


def _parse_showinfo_times(stderr: str) -> list[float]:
    """A che secondo del video corrisponde ciascun fotogramma estratto.

    ffmpeg, quando tira fuori i fotogrammi, i tempi non li scrive in un file:
    li stampa fra i suoi messaggi di servizio, mescolati a tutto il resto. Qui
    si rileggono quelle righe e si pesca il numero.

    Sembra un giro storto ed e' l'unico che c'e': i file estratti si chiamano
    01, 02, 03 e non contengono nessuna traccia del momento in cui erano nel
    video. Senza questi numeri, una nota visiva non saprebbe a che punto della
    trascrizione attaccarsi.

    Una riga che non si riesce a leggere viene saltata invece di far fallire
    tutto: un fotogramma senza tempo si perde, gli altri no.
    """
    times: list[float] = []
    for line in stderr.splitlines():
        idx = line.find("pts_time:")
        if idx == -1:
            continue
        rest = line[idx + len("pts_time:"):].strip()
        token = rest.split()[0] if rest else ""
        try:
            times.append(float(token))
        except ValueError:
            continue
    return times
def _collapse_close_frames(frames: list[tuple[float, str]],
                           min_gap: float) -> list[tuple[float, str]]:
    """Raggruppa i fotogrammi entro 'min_gap' secondi (finestra a partire dal
    primo del gruppo) e tiene l'ULTIMO di ogni gruppo. Serve a eliminare le coppie
    ravvicinate che il rilevamento scene produce sulle transizioni (un frame a
    metà stacco + uno assestato): l'ultimo è di norma quello leggibile/ravvicinato.
    'frames' = [(timestamp, percorso)] ordinati per tempo. Non tocca i file."""
    if min_gap <= 0 or len(frames) < 2:
        return frames
    kept: list[tuple[float, str]] = []
    cluster_start = frames[0][0]
    last = frames[0]
    for t, p in frames[1:]:
        if t - cluster_start <= min_gap:
            last = (t, p)              # stesso gruppo: l'ultimo vince
        else:
            kept.append(last)
            cluster_start = t
            last = (t, p)
    kept.append(last)
    return kept
def extract_keyframes(video_path: str, duration: float, workdir: str) -> list[tuple[float, str]]:
    """Estrae i FOTOGRAMMI CHIAVE di un video, con il loro timestamp (secondi).

    Strategia: rilevamento di CAMBIO SCENA via ffmpeg (cattura un frame quando
    l'immagine cambia davvero: nuova slide, nuovo codice, nuova formula), così di
    natura non si ripetono fotogrammi quasi identici. Se il video è quasi statico
    e le scene rilevate sono troppo poche, ripiega su un campionamento a intervalli
    regolari. Limita il totale a VISION_MAX_FRAMES (campionamento uniforme).
    Restituisce una lista di (timestamp, percorso_jpg) ordinata per tempo."""
    frames_dir = os.path.join(workdir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    # 1) Rilevamento cambio scena.
    pattern = os.path.join(frames_dir, "kf_%05d.jpg")
    vf = (f"select='gt(scene,{VISION_SCENE_THRESHOLD})',"
          f"scale={VISION_FRAME_WIDTH}:-2,showinfo")
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", video_path, "-vf", vf,
             "-vsync", "vfr", "-q:v", "3", pattern],
            capture_output=True, text=True)
        times = _parse_showinfo_times(proc.stderr)
    except Exception as e:
        console.print(f"[warning]Estrazione fotogrammi non riuscita: {e}[/warning]")
        return []
    files = sorted(os.path.join(frames_dir, n) for n in os.listdir(frames_dir)
                   if n.startswith("kf_"))
    frames = list(zip(times, files))  # l'ordine di showinfo coincide con quello dei file
    # Elimina le coppie ravvicinate (doppio scatto sulla stessa transizione): tiene
    # un solo fotogramma per finestra, così non finiscono nel riassunto due frame
    # quasi identici (uno spesso "vuoto") e si risparmiano chiamate al modello.
    frames = _collapse_close_frames(frames, VISION_MIN_GAP)

    # 2) Fallback: video quasi statico o senza stacchi netti -> pochi cambi scena.
    # Campiona a intervalli regolari, con un passo ADATTIVO alla durata così anche
    # i video brevi ricevono comunque alcuni fotogrammi.
    min_expected = max(4, int((duration or 0) // 180))
    if len(frames) < min_expected and (duration or 0) >= 2:
        # Quanti fotogrammi vogliamo: tra min_expected e il cap, in base a quanti
        # intervalli "standard" entrano nella durata.
        want = max(min_expected,
                   min(VISION_MAX_FRAMES,
                       int((duration or 0) // VISION_FALLBACK_INTERVAL) or min_expected))
        interval = max(1.0, (duration or 0) / want)
        ipattern = os.path.join(frames_dir, "iv_%05d.jpg")
        ivf = f"fps=1/{interval:.3f},scale={VISION_FRAME_WIDTH}:-2"
        try:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-i", video_path, "-vf", ivf,
                 "-vsync", "vfr", "-q:v", "3", ipattern],
                capture_output=True, text=True, check=True)
            ifiles = sorted(os.path.join(frames_dir, n) for n in os.listdir(frames_dir)
                            if n.startswith("iv_"))
        except Exception:
            ifiles = []
        # I fotogrammi dei cambi scena si buttano SOLO se il campionamento a
        # intervalli ha davvero prodotto qualcosa. Cancellandoli prima, un ffmpeg
        # che fallisce lasciava 'frames' a puntare file ormai inesistenti: ogni
        # lettura falliva e l'analisi visiva finiva a zero note senza motivo.
        if ifiles:
            frames = [(float(i) * interval, f) for i, f in enumerate(ifiles)]
            for f in files:
                try:
                    os.remove(f)
                except OSError:
                    pass

    # 3) Cap: se sono troppi, campiona uniformemente lungo la timeline.
    if len(frames) > VISION_MAX_FRAMES:
        step = len(frames) / VISION_MAX_FRAMES
        frames = [frames[int(i * step)] for i in range(VISION_MAX_FRAMES)]
    return frames
# Prompt per il modello vision: estrae SOLO il contenuto informativo visibile e
# scarta i fotogrammi "vuoti" (volti, transizioni) rispondendo "NIENTE".
_VISION_SYSTEM_PROMPT = (
    "Analizzi UN fotogramma di un video didattico/divulgativo. Estrai SOLO il "
    "contenuto informativo VISIBILE a schermo che il parlato non può rendere:\n"
    "• CODICE sorgente: trascrivilo ALLA LETTERA (indentazione e simboli inclusi) "
    "dentro un blocco markdown ``` con il nome del linguaggio.\n"
    "• FORMULE matematiche e relativi PASSAGGI/DIMOSTRAZIONI: scrivile in LaTeX "
    "(`$...$` in linea, `$$...$$` per i passaggi), riportando tutti i passaggi "
    "visibili.\n"
    "• GRAFICI, DIAGRAMMI, TABELLE, SCHEMI: descrivili indicando assi, valori, "
    "relazioni e la conclusione che mostrano.\n"
    "• TESTO significativo di slide (titoli, definizioni, elenchi): riportalo.\n"
    "Regole: NON descrivere volti, persone che parlano, sfondi, arredi o elementi "
    "decorativi. Se il fotogramma non contiene NULLA di tecnico/informativo (solo "
    "una persona che parla, una slide di titolo, una transizione), rispondi "
    "ESATTAMENTE con la sola parola: NIENTE. Rispondi in italiano, conciso e ben "
    "strutturato, senza preamboli e SENZA includere il tuo ragionamento: fornisci "
    "solo il risultato finale."
)
_VISION_USER_PROMPT = "Estrai il contenuto tecnico/informativo visibile in questo fotogramma."
def _vision_user_prompt(context: str = "") -> str:
    """Prompt utente per il modello vision. Se 'context' (il parlato attorno a
    questo punto del video) è disponibile, lo antepone: dà al modello il CONTESTO
    di ciò di cui si sta parlando, così interpreta meglio sigle, nomi di variabili,
    simboli e formule ambigue a schermo. Vincolo esplicito: usare il contesto solo
    per INTERPRETARE, mai per inventare: si trascrive solo ciò che è VISIBILE."""
    if not context:
        return _VISION_USER_PROMPT
    return (
        "CONTESTO AUDIO. Ciò che l'oratore sta dicendo intorno a questo punto del "
        f"video:\n«{context}»\n\n"
        "Usa questo contesto SOLO per interpretare correttamente ciò che vedi "
        "(sigle, nomi di variabili, simboli, formule, termini ambigui). NON "
        "aggiungere nulla che non sia effettivamente a schermo: trascrivi "
        "esclusivamente il contenuto VISIBILE nel fotogramma.\n\n"
        + _VISION_USER_PROMPT)
def _audio_context_near(segments: list[dict] | None, ts: float,
                        window: float = 25.0, max_chars: int = 700) -> str:
    """Testo trascritto attorno al timestamp 'ts' (± 'window' secondi), da passare
    al modello vision come contesto del fotogramma. Restituisce stringa vuota se
    non ci sono segmenti utili. Troncato a 'max_chars' per non gonfiare i token."""
    if not segments:
        return ""
    lo, hi = ts - window, ts + window
    parts = [(s.get("text") or "").strip() for s in segments
             if s.get("start") is not None and lo <= s["start"] <= hi]
    ctx = " ".join(p for p in parts if p).strip()
    if len(ctx) > max_chars:
        ctx = ctx[:max_chars].rstrip() + "…"
    return ctx
def _strip_think(text: str) -> str:
    """Rimuove il ragionamento <think>…</think> dei modelli "reasoning".

    Molti modelli (es. qwen3) antepongono alla risposta un lungo blocco di
    ragionamento racchiuso in <think>…</think>: va tolto, altrimenti inquina le
    note visive e il riassunto (e gonfia l'input di 5-7×)."""
    import re
    t = re.sub(r"(?is)<think\b.*?</think>", "", text or "")
    # Tag di apertura rimasto senza chiusura (output troncato): tieni ciò che
    # segue una eventuale chiusura, altrimenti scarta il ragionamento incompleto.
    low = t.lower()
    i = low.find("<think")
    if i != -1:
        j = low.find("</think>", i)
        t = t[j + len("</think>"):] if j != -1 else t[:i]
    return re.sub(r"(?is)</?think>", "", t).strip()
def _dedup_visual_notes(notes: list[dict]) -> list[dict]:
    """Scarta le note visive quasi-identiche (stessa slide ripresa più volte),
    tenendo la PRIMA occorrenza. Confronto per similarità di Jaccard sui termini
    significativi: una slide/definizione rimasta a lungo a schermo genera note
    duplicate che, senza questo filtro, farebbero ripetere il riassunto."""
    import re

    def sig(t: str) -> set:
        """L'impronta di una nota: le parole che la distinguono dalle altre.

        Serve a riconoscere due note che dicono la stessa cosa con parole un
        po' diverse, cosa che capita continuamente quando due fotogrammi
        mostrano la stessa slide.

        Le parole di due lettere o meno si buttano perche' sono articoli e
        preposizioni: compaiono in tutte le note e non distinguono niente.
        """
        words = re.findall(r"[a-zà-ù0-9]+", t.lower())
        return {w for w in words if len(w) > 2}

    kept: list[dict] = []
    sigs: list[set] = []
    for n in notes:
        s = sig(n.get("text", ""))
        if not s:
            continue
        if any((len(s & ps) / (len(s | ps) or 1)) > 0.8 for ps in sigs):
            continue
        kept.append(n)
        sigs.append(s)
    return kept
def _fix_mermaid_arrows(text: str) -> str:
    """Raddrizza le frecce dei diagrammi, che i modelli scrivono quasi sempre male.

    La forma giusta e' `-->|etichetta|`; i modelli ci aggiungono spesso un
    altro segno di maggiore in fondo. Con quello di troppo il diagramma non
    viene disegnato affatto: la libreria si ferma, e al posto della mappa resta
    un rettangolo con dentro un messaggio d'errore.

    Correggerlo qui e' molto piu' affidabile che chiederlo nelle istruzioni al
    modello, perche' e' un errore che continua a fare anche quando gli si dice
    di non farlo.
    """
    import re
    return re.sub(r"(-->\s*\|[^|]*\|)>", r"\1", text or "")
def _strip_mermaid_blocks(text: str) -> str:
    """Toglie i diagrammi dal testo quando non erano stati chiesti.

    E' una rete di sicurezza. Se la mappa dei concetti e' spenta, al modello
    non viene chiesta; ma i modelli ogni tanto la fanno lo stesso, perche' il
    materiale sembra chiederla.

    Lasciarla passerebbe un blocco di codice di diagramma dentro un documento
    che nessuno ha preparato per disegnarlo: chi legge si troverebbe una
    ventina di righe di sintassi incomprensibile in mezzo al riassunto.
    """
    import re
    return re.sub(r"```mermaid\b.*?```\s*", "", text or "", flags=re.S).strip()
def _encode_image_b64(path: str) -> str:
    """Trasforma un file immagine in testo, perche' e' cosi' che va spedito.

    I modelli che guardano le immagini le ricevono dentro un messaggio fatto di
    testo, non come file allegato. La codifica base64 e' il modo standard di
    scrivere dei dati binari usando solo caratteri che un messaggio di testo
    puo' contenere.

    Costa circa un terzo in piu' di dimensione rispetto al file originale, ed
    e' il motivo per cui i fotogrammi vengono rimpiccioliti prima: mandare
    immagini grandi non migliora quello che il modello legge, e moltiplica
    quello che si spedisce.
    """
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")
def _vision_groq(client, b64: str, context: str = "") -> str:
    """Analizza un fotogramma con un modello multimodale di Groq.

    'context' (opzionale): il parlato trascritto attorno a questo fotogramma, per
    aiutare il modello a interpretare ciò che vede (vedi _vision_user_prompt).

    I modelli "reasoning" (es. qwen3) antepongono un blocco <think>…</think>:
    proviamo a disattivarlo a monte (reasoning_effort, per non sprecare token) e
    in ogni caso lo rimuoviamo dall'output con _strip_think."""
    data_url = f"data:image/jpeg;base64,{b64}"
    messages = [
        {"role": "system", "content": _VISION_SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": _vision_user_prompt(context)},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]},
    ]
    try:
        resp = _groq_chat_capture(
            client, settings.GROQ_VISION_MODEL, messages=messages, temperature=0.2,
            reasoning_effort="none")
    except Exception as e:
        if _is_rate_limit(str(e)):
            raise
        # Il modello non accetta 'reasoning_effort': riprova senza il parametro.
        resp = _groq_chat_capture(
            client, settings.GROQ_VISION_MODEL, messages=messages, temperature=0.2)
    return _strip_think(resp.choices[0].message.content or "")
def _vision_ollama(b64: str, context: str = "") -> str:
    """Analizza un fotogramma con un modello vision locale via Ollama (HTTP).

    'context' (opzionale): il parlato attorno al fotogramma, per aiutare il
    modello a interpretare ciò che vede (vedi _vision_user_prompt)."""
    import urllib.request
    payload = {
        "model": settings.OLLAMA_VISION_MODEL,
        "messages": [
            {"role": "system", "content": _VISION_SYSTEM_PROMPT},
            {"role": "user", "content": _vision_user_prompt(context), "images": [b64]},
        ],
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": OLLAMA_NUM_CTX},
    }
    req = urllib.request.Request(
        OLLAMA_HOST + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    return _strip_think(data.get("message", {}).get("content") or "")
def _check_ollama_vision() -> None:
    """Ollama e' acceso E ha un modello che sa guardare le immagini?

    Sono due controlli e non uno, perche' sono due problemi diversi con due
    rimedi diversi: «Ollama non parte» e «Ollama c'e' ma quel modello non l'hai
    scaricato». Un messaggio solo per tutti e due manderebbe meta' delle
    persone a reinstallare qualcosa che era gia' a posto.

    Il controllo si fa prima di cominciare perche' l'analisi visiva estrae
    prima i fotogrammi e li manda dopo: scoprendolo a quel punto, si sarebbero
    gia' spesi minuti di lavoro sul video per niente.
    """
    installed = _ollama_installed_models(timeout=5)
    if installed is None:
        raise RuntimeError(
            f"Ollama non raggiungibile su {OLLAMA_HOST}. Per l'analisi visiva in "
            "locale installa Ollama (https://ollama.com), avvialo e scarica un "
            f"modello vision, es:  ollama pull {settings.OLLAMA_VISION_MODEL}")
    if not _ollama_has_model(settings.OLLAMA_VISION_MODEL, installed):
        raise RuntimeError(
            f"Modello vision '{settings.OLLAMA_VISION_MODEL}' non presente in Ollama. "
            f"Scaricalo con:  ollama pull {settings.OLLAMA_VISION_MODEL}")
def _make_vision_analyzer(client=None):
    """Sceglie il motore dell'analisi visiva e restituisce (funzione(b64)->testo, etichetta).

    Preferisce Groq se c'è un client (backend cloud), altrimenti Ollama in locale
    (100% offline). RuntimeError se nessuno è utilizzabile (il chiamante può così
    saltare l'analisi senza bloccare il resto)."""
    if client is not None:
        return (lambda b64, ctx="": _vision_groq(client, b64, ctx)), f"Groq · {settings.GROQ_VISION_MODEL}"
    _check_ollama_vision()
    return (lambda b64, ctx="": _vision_ollama(b64, ctx)), f"locale · Ollama {settings.OLLAMA_VISION_MODEL}"
def _is_empty_visual(text: str) -> bool:
    """Il modello ha detto che in questo fotogramma non c'era niente di utile?

    Nelle istruzioni gli si chiede di rispondere NIENTE quando l'immagine non
    contiene nulla da leggere: una faccia che parla, una sigla, una schermata
    nera. Serve perche' un modello a cui si mostra qualcosa risponde comunque
    qualcosa, e «si vede una persona che parla» non e' falso, e' inutile.

    Il confronto si fa dopo aver tolto punteggiatura, asterischi e spazi,
    perche' quella parola torna indietro vestita in tutti i modi possibili:
    «NIENTE.», «**Niente**», «- niente». Sono tutte la stessa risposta.
    """
    norm = (text or "").upper()
    for ch in "*_.!#>` \n\t-":
        norm = norm.replace(ch, "")
    return norm == "" or norm == "NIENTE"
def analyze_video_visuals(video_path: str, duration: float, workdir: str,
                          client=None, frames_out_dir: str | None = None,
                          on_progress=None, quiet: bool = False,
                          stats: dict | None = None,
                          segments: list[dict] | None = None) -> list[dict]:
    """Estrae i fotogrammi chiave del video e li "legge" con un modello vision.

    'segments' (opzionale): la trascrizione audio già pronta. Se presente, per ogni
    fotogramma passa al modello il parlato attorno a quel timestamp come CONTESTO,
    così legge meglio ciò che vede (sigle, variabili, formule ambigue). Vedi
    _vision_user_prompt / _audio_context_near.

    Restituisce una lista di NOTE VISIVE {'start': sec, 'text': str, 'image': str},
    una per fotogramma con informazione (i "vuoti", cioè volti e transizioni, vengono
    scartati). Se 'frames_out_dir' è dato, COPIA lì il fotogramma di ogni nota
    tenuta (il workdir temporaneo verrà cancellato) e ne salva il nome in 'image'.

    Doppia modalità di output, così è riusabile sia dalla CLI sia dal motore/GUI:
    con 'on_progress(phase,cur,total,detail)' riporta tramite callback (niente
    console rich); senza, usa la console rich (CLI). 'quiet' silenzia comunque la
    console. Lista vuota se non c'è nulla o se il motore vision non è disponibile.

    'stats' (opzionale): dict che la funzione riempie con l'esito, così il
    chiamante (engine/GUI) può spiegare PERCHÉ non ci sono note invece di
    lasciare tutto in silenzio. Chiavi: 'frames', 'notes', 'errors',
    'rate_limited' (bool), 'last_error', 'unavailable'."""
    use_rich = on_progress is None and not quiet

    def _stat(key, value):
        """Annota com'e' andata, se qualcuno ha chiesto di saperlo.

        Serve a chi deve poi SPIEGARE perche' l'analisi visiva non ha prodotto
        niente: crediti finiti, nessun fotogramma utile, errori su tutti. Prima
        quel caso era silenzioso e restava solo una cartella vuota, che sembra
        un guasto del programma anche quando non lo e'.
        """
        if stats is not None:
            stats[key] = value

    _stat("frames", 0)
    _stat("notes", 0)
    _stat("errors", 0)
    _stat("rate_limited", False)
    _stat("last_error", None)

    def _report(cur, total, detail):
        """Riferisce l'avanzamento, se c'e' qualcuno che ascolta.

        L'analisi visiva e' il passaggio piu' lento di tutti: decine di
        fotogrammi, ciascuno mandato a un modello. Senza un avanzamento
        sembrerebbe piantata per parecchi minuti.
        """
        if on_progress:
            on_progress("visual", cur, total, detail)

    try:
        analyze_fn, label = _make_vision_analyzer(client)
    except RuntimeError as e:
        if use_rich:
            console.print(f"[warning]Analisi visiva non disponibile: {e}[/warning]")
        _report(None, None, msg("vis_unavail", e=e))
        _stat("unavailable", str(e))
        return []

    _report(None, None, msg("vis_detect"))
    if use_rich:
        with console.status("[info]Individuo i fotogrammi chiave (cambi scena)...[/info]", spinner="dots"):
            frames = extract_keyframes(video_path, duration, workdir)
    else:
        frames = extract_keyframes(video_path, duration, workdir)
    _stat("frames", len(frames))
    if not frames:
        if use_rich:
            console.print("[warning]Nessun fotogramma significativo individuato.[/warning]")
        _report(None, None, msg("vis_noframes"))
        return []
    if use_rich:
        console.print(f"  {SYM_OK} [info]{len(frames)}[/info] fotogrammi da analizzare ({label})")
    _report(0, len(frames), msg("vis_toanalyze", n=len(frames), label=label))

    notes: list[dict] = []

    def _process(update) -> None:
        """Manda i fotogrammi al modello, uno per uno, e raccoglie le note.

        Il ciclo vero dell'analisi visiva. Tre cose da sapere:

        Si controlla fra un fotogramma e l'altro se qualcuno ha chiesto di
        fermarsi, perche' quello e' il punto in cui interrompersi non fa danni.

        Gli errori su singoli fotogrammi si contano e si va avanti: un'immagine
        che il modello non digerisce non deve far perdere le altre quaranta.

        I crediti finiti invece fermano tutto, perche' da li' in poi ogni altro
        fotogramma darebbe lo stesso errore, e insistere vorrebbe dire solo
        aspettare quaranta volte per niente.
        """
        errors = 0
        for i, (ts, path) in enumerate(frames, 1):
            if fermarsi():
                break
            try:
                text = analyze_fn(_encode_image_b64(path),
                                  _audio_context_near(segments, ts))
            except Exception as e:
                if _is_rate_limit(str(e)):
                    if use_rich:
                        console.print("[warning]Crediti Groq esauriti durante l'analisi visiva: "
                                      "proseguo con i fotogrammi già letti.[/warning]")
                    _report(i, len(frames), msg("vis_ratelimit"))
                    _stat("rate_limited", True)
                    _stat("last_error", str(e))
                    break
                # Errore NON di credito sul singolo fotogramma: lo saltiamo, ma lo
                # registriamo così il chiamante non resta al buio se falliscono tutti.
                errors += 1
                _stat("errors", errors)
                _stat("last_error", str(e))
                text = ""
            if text and not _is_empty_visual(text):
                notes.append({"start": float(ts), "text": text.strip(), "_frame": path})
            update(i)

    if use_rich:
        progress = Progress(
            SpinnerColumn("dots", style="bright_yellow"),
            TextColumn("[phase]{task.description}"),
            BarColumn(bar_width=40, style="bar.back", complete_style="bright_yellow", finished_style="bold yellow"),
            TaskProgressColumn(), console=console, expand=False,
        )
        with progress:
            task_id = progress.add_task("Analizzo i fotogrammi", total=len(frames))
            _process(lambda i: progress.update(task_id, completed=i))
    else:
        _process(lambda i: _report(i, len(frames), msg("vis_analyzing", i=i, n=len(frames))))

    raw = len(notes)
    notes = _dedup_visual_notes(notes)  # scarta slide ripetute (stesso contenuto a schermo)
    _stat("notes", len(notes))
    # Conserva i fotogrammi delle note TENUTE: il workdir temporaneo verrà
    # cancellato, quindi li copiamo nella cartella definitiva e ne salviamo il nome.
    # Solo se c'è davvero qualcosa da salvare: niente cartella 'frames' vuota.
    if frames_out_dir and notes:
        try:
            os.makedirs(_lp(frames_out_dir), exist_ok=True)
            for idx, note in enumerate(notes):
                src = note.get("_frame")
                if src and os.path.isfile(src):
                    name = f"frame_{idx:03d}_{int(note['start'])}s.jpg"
                    shutil.copyfile(src, _lp(os.path.join(frames_out_dir, name)))
                    note["image"] = name
        except OSError:
            pass
    for note in notes:
        note.pop("_frame", None)
    if use_rich:
        dropped = f" ([dim]{raw - len(notes)} duplicati scartati[/dim])" if raw != len(notes) else ""
        console.print(f"  {SYM_OK} Contenuti visivi estratti: [info]{len(notes)}[/info] su {len(frames)} fotogrammi{dropped}")
    _report(len(frames), len(frames), msg("vis_extracted", k=len(notes), n=len(frames)))
    return notes
def save_visual_notes(out_root: str, meta: dict, notes: list[dict],
                      engine_label: str, do_export: bool,
                      quiet: bool = False) -> None:
    """Salva le NOTE VISIVE in results/<title>/analisi_visiva/.

    Produce: il .json, un .md leggibile e, se l'export è attivo, un PDF "ricco"
    in cui OGNI nota mostra il suo FOTOGRAMMA accanto al contenuto estratto
    (codice/formula/grafico), così il frame fa da prova/riferimento visivo.
    'quiet' silenzia la console (per il motore/GUI, che riporta a modo suo)."""
    if not notes:
        return
    safe = _safe_filename(meta["title"])
    video_dir = os.path.join(out_root, safe)
    vdir = os.path.join(video_dir, visual_subdir())
    frames_dir = os.path.join(vdir, "frames")
    os.makedirs(_lp(vdir), exist_ok=True)
    base = os.path.join(vdir, f"{safe}_visivo")
    payload = {
        "title": meta["title"],
        "engine": engine_label,
        "count": len(notes),
        "notes": [{"start": n["start"],
                   "timestamp": _format_timestamp(n["start"]),
                   "image": n.get("image"),
                   "text": n["text"]} for n in notes],
    }
    with open(_lp(base + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Markdown del documento: fotogramma (se presente) + testo, per ogni nota.
    # 'img_prefix' permette link RELATIVI per il .md (portabile) e ASSOLUTI per il
    # PDF (il browser headless deve trovare i file).
    def _companion_md(img_prefix: str, saved_in: str | None = None) -> str:
        """Il documento che si legge da solo, con le note in ordine di tempo.

        E' un file a parte e non un pezzo del riassunto, perche' risponde a una
        domanda diversa: non «di cosa parlava il video» ma «cosa c'era scritto
        a schermo, e a che minuto». Con i fotogrammi accanto, serve a ritrovare
        un pezzo di codice o una formula senza riaprire il video.
        """
        saved_line = [f"- **Salvato in:** {saved_in}"] if saved_in else []
        out = [f"# {meta['title']}: Analisi visiva", "",
               f"- **Estratto con:** {engine_label}",
               f"- **Fotogrammi con contenuto:** {len(notes)}",
               *saved_line, "", "---", ""]
        for n in notes:
            out.append(f"## [{_format_timestamp(n['start'])}]")
            out.append("")
            if n.get("image"):
                out.append(f"![fotogramma {_format_timestamp(n['start'])}]({img_prefix}{n['image']})")
                out.append("")
            out.append(n["text"])
            out.append("")
        return "\n".join(out)

    with open(_lp(base + ".md"), "w", encoding="utf-8") as f:
        f.write(_companion_md("frames/"))
    if not quiet:
        console.print(f"  {SYM_OK} Analisi visiva salvata in [info]{visual_subdir()}/[/info]")

    # PDF "ricco": fotogramma + testo estratto, uno per nota (immagini con percorso
    # ASSOLUTO). Solo se l'export è attivo e ci sono davvero dei fotogrammi salvati.
    if do_export and RICH_PDF and any(n.get("image") for n in notes):
        pdf_saved_in = os.path.abspath(vdir)
        try:
            if quiet:
                build_pdf_rich(_companion_md(frames_dir + os.sep, saved_in=pdf_saved_in), base + ".pdf")
            else:
                with console.status("[info]Creo il PDF dell'analisi visiva (fotogrammi + testo)...[/info]", spinner="dots"):
                    ok = build_pdf_rich(_companion_md(frames_dir + os.sep, saved_in=pdf_saved_in), base + ".pdf")
                if ok:
                    console.print(f"  {SYM_OK} PDF analisi visiva con i fotogrammi creato.")
        except Exception:
            pass
def load_visual_notes(out_root: str, title: str) -> list[dict]:
    """Rilegge le note visive gia' salvate per questo video.

    Serve a «solo riassunto» fatto in un secondo momento: l'analisi visiva era
    gia' stata fatta giorni prima, e rifarla costerebbe di nuovo tempo e
    crediti per ottenere le stesse identiche note.

    Si guarda anche nella cartella col nome inglese, che e' quello usato dalle
    versioni in cui l'interfaccia poteva essere in inglese. Senza, a chi aveva
    lavorato cosi' il programma direbbe che quelle note non esistono.

    Lista vuota se non c'e' niente: chi chiama ci gira sopra in un ciclo, e un
    None a quel punto sarebbe un errore lontano da qui.
    """
    safe = _safe_filename(title)
    for sub in (VISUAL_SUBDIR, NOMI_VECCHI[VISUAL_SUBDIR]):
        p = os.path.join(out_root, safe, sub, f"{safe}_visivo.json")
        if os.path.isfile(_lp(p)):
            try:
                with open(_lp(p), "r", encoding="utf-8") as f:
                    d = json.load(f)
                # Pulizia difensiva anche in lettura: toglie eventuale ragionamento
                # <think> e le note duplicate (così il riassunto resta pulito anche
                # rigenerandolo da note salvate da versioni precedenti).
                cleaned = []
                for n in d.get("notes", []):
                    txt = _strip_think(n.get("text", ""))
                    if txt and not _is_empty_visual(txt):
                        cleaned.append({"start": float(n.get("start") or 0), "text": txt,
                                        "image": n.get("image")})
                return _dedup_visual_notes(cleaned)
            except Exception:
                return []
    return []
def _split_md_blocks(text: str) -> list[str]:
    """Spezza il testo in blocchi separati da riga vuota, MA tiene interi i
    recinti di codice ``` ``` (che possono contenere righe vuote): così un
    fotogramma non finisce mai in mezzo a un blocco di codice."""
    blocks: list[str] = []
    cur: list[str] = []
    in_fence = False
    for ln in text.split("\n"):
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            cur.append(ln)
            continue
        if not ln.strip() and not in_fence:
            if cur:
                blocks.append("\n".join(cur))
                cur = []
        else:
            cur.append(ln)
    if cur:
        blocks.append("\n".join(cur))
    return [b for b in blocks if b.strip()]
def _append_frames_to_sections(sections: list[dict], notes: list[dict], img_path_fn) -> list[dict]:
    """INTERLACCIA i FOTOGRAMMI nel testo di ogni sezione, inserendoli TRA i
    paragrafi in base al loro timestamp (posizione relativa nella finestra
    temporale della sezione), invece di accodarli tutti in fondo. Così le
    immagini seguono il discorso e non formano un «muro» a fine sezione.
    'img_path_fn(nome_immagine) -> percorso' consente link relativi (per il .md,
    portabile) o assoluti (per il PDF). Non muta gli input."""
    notes = sorted([n for n in notes if n.get("image")], key=lambda n: n["start"])
    if not notes:
        return sections
    out = [dict(s) for s in sections]
    bounds: list[tuple[float, float]] = []
    if any(s.get("start") is not None for s in out):
        for i, s in enumerate(out):
            st = s.get("start") or 0
            nxt = out[i + 1].get("start") if i + 1 < len(out) else None
            bounds.append((st, nxt if nxt is not None else float("inf")))
        buckets: list[list[dict]] = [[] for _ in out]
        for note in notes:
            placed = False
            for i, (st, en) in enumerate(bounds):
                if st <= note["start"] < en:
                    buckets[i].append(note)
                    placed = True
                    break
            if not placed:
                buckets[-1].append(note)
    else:
        bounds = [(0.0, float("inf"))] + [(0.0, float("inf")) for _ in out[1:]]
        buckets = [list(notes)] + [[] for _ in out[1:]]

    def _img_md(n: dict) -> str:
        """La riga markdown che mostra il fotogramma di una nota.

        Il percorso lo compone chi chiama, perche' cambia a seconda di dove
        finira' il documento: un file accanto ai fotogrammi li raggiunge in un
        modo, uno in un'altra cartella in un altro.
        """
        return f"![Fotogramma {_format_timestamp(n['start'])}]({img_path_fn(n['image'])})"

    for i, s in enumerate(out):
        bucket = buckets[i]
        if not bucket:
            continue
        text = (s.get("text") or "").rstrip()
        paras = _split_md_blocks(text)
        if not paras:  # sezione senza testo: accoda le immagini
            s["text"] = "\n\n".join(_img_md(n) for n in bucket)
            continue
        st, en = bounds[i]
        span = (en - st) if (en != float("inf") and en > st) else None
        # Per ogni paragrafo, i fotogrammi da inserire SUBITO DOPO di esso.
        after: list[list[dict]] = [[] for _ in paras]
        n_para = len(paras)
        for j, note in enumerate(bucket):
            if span:
                frac = (note["start"] - st) / span
            else:  # senza timestamp affidabili: distribuzione uniforme
                frac = (j + 0.5) / len(bucket)
            frac = min(1.0, max(0.0, frac))
            idx = min(n_para - 1, int(frac * n_para))
            after[idx].append(note)
        pieces: list[str] = []
        for k, p in enumerate(paras):
            pieces.append(p)
            pieces.extend(_img_md(n) for n in after[k])
        s["text"] = "\n\n".join(pieces)
    return out
def _merge_visual_into_sections(sections: list[dict], notes: list[dict]) -> list[dict]:
    """Inserisce le note visive nel testo delle sezioni in base al timestamp.

    Ogni nota finisce nella sezione il cui intervallo [start, start_successiva)
    contiene il suo timestamp; se le sezioni non hanno start (testo continuo) le
    note vanno in coda in ordine. Diventano annotazioni «[A SCHERMO · mm:ss] …»
    così il modello del riassunto le vede insieme al parlato. Non muta gli input."""
    if not notes:
        return sections
    notes = sorted(notes, key=lambda n: n["start"])
    out = [dict(s) for s in sections]

    def _annotate(items: list[dict]) -> str:
        """Le note visive marcate, pronte da mescolare al parlato.

        Il marcatore davanti a ciascuna non e' decorazione: e' quello che dice
        al modello del riassunto che quel pezzo non e' stato DETTO ma VISTO.
        Senza, il riassunto risulterebbe che qualcuno ha pronunciato a voce
        venti righe di codice.
        """
        return "\n\n".join(
            f"[A SCHERMO · {_format_timestamp(n['start'])}]\n{n['text']}" for n in items)

    if any(s.get("start") is not None for s in out):
        bounds = []
        for i, s in enumerate(out):
            st = s.get("start") or 0
            nxt = out[i + 1].get("start") if i + 1 < len(out) else None
            en = nxt if nxt is not None else float("inf")
            bounds.append((st, en))
        buckets: list[list[dict]] = [[] for _ in out]
        for note in notes:
            placed = False
            for i, (st, en) in enumerate(bounds):
                if st <= note["start"] < en:
                    buckets[i].append(note)
                    placed = True
                    break
            if not placed:
                buckets[-1].append(note)
        for i, s in enumerate(out):
            if buckets[i]:
                s["text"] = (s.get("text", "").strip() + "\n\n" + _annotate(buckets[i])).strip()
    else:
        out[0]["text"] = (out[0].get("text", "").strip() + "\n\n" + _annotate(notes)).strip()
    return out
