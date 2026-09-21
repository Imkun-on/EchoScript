"""Tutte le frasi che finiscono sotto gli occhi di chi usa l'interfaccia.

Perche' stanno qui e non nella pagina
    Perche' la pagina non deve sapere l'italiano. Le riceve tutte all'avvio in
    un dizionario solo, le mette al posto giusto guardando gli attributi
    ``data-t``, e quando si cambia lingua le riscrive. Una frase si corregge in
    un file, non in cinque.

Perche' non stanno nel catalogo di transcriber.py
    Perche' quello e' il catalogo della riga di comando: mescolarli renderebbe
    difficile capire, leggendo, quali frasi appaiono a terminale e quali in
    finestra. Le due cose cambiano per motivi diversi e a ritmi diversi.

La forma
    ``'chiave': {'it': ..., 'en': ...}``. I segnaposto sono quelli di
    ``str.format`` (``{titolo}``, ``{n}``) e la pagina li sostituisce con la
    stessa convenzione, quindi la stessa frase funziona da tutt'e due i lati.
"""
from __future__ import annotations

TESTI: dict[str, str] = {

    # ── Cornice: marchio, barra laterale, sezioni ────────────────────────────

    'menu.locale':      'Locale',
    'menu.cloud':       'Cloud',

    'sez.locale.title': 'Trascrivi sul tuo computer',
    'sez.locale.desc':  "Quello che parte da qui gira su questa macchina, con i modelli "
                        "scelti qui sotto: niente rete, niente chiave, niente crediti. "
                        "L'audio non esce di casa.",
    'sez.cloud.title':  'Trascrivi sui server Groq',
    'sez.cloud.desc':   "Quello che parte da qui gira in nuvola, con i modelli scelti "
                        "qui sotto e a carico della chiave. Molto più veloce, ma "
                        "l'audio viene inviato a Groq e ogni lavoro consuma crediti.",

    # ── I tre riquadri e le loro finestre ────────────────────────────────────
    # Modelli, chiave e video: le tre cose da sapere prima di poter cominciare.
    # Ogni riquadro dice cosa si e' scelto; il come si sceglie sta in una
    # finestra, e queste sono le sue intestazioni.
    'carta.modelli':    'Modelli',
    'carta.modelli.bottone': 'Scegli i modelli',
    'carta.chiave':     'Chiave API',
    'carta.chiave.bottone': 'Carica la chiave',
    'carta.video':      'Video',
    'carta.video.bottone': 'Scegli cosa trascrivere',
    # Il posto di un valore che non c'è ancora. Una riga vuota si legge come un
    # difetto; una riga che dice di essere vuota si legge come uno stato.
    'carta.vuoto':      'da scegliere',

    'fin.modelli.locale': 'I modelli sul tuo computer',
    'fin.modelli.cloud': 'I modelli sui server Groq',
    'fin.video':        'Cosa vuoi trascrivere',
    'fin.fatto':        'Fatto',
    'res.ancora':       'Trascrivi un altro video',

    # ── Diario e stato ───────────────────────────────────────────────────────
    'log.title':        'Diario',
    'log.clear':        'Svuota',
    'log.empty':        'Qui compare quello che sta succedendo.',
    # L'ultima riga del diario. Il simbolo non e' decorazione: la pagina colora
    # le righe leggendole, e la spunta e' cio' che le fa venire verdi.
    'log.done':         '✓ Fatto',
    'status.idle':      'In attesa',
    'status.working':   'In corso',
    'status.done':      'Fatto',
    'status.error':     'Errore',

    'comune.chiudi':    'Chiudi',
    'comune.annulla':   'Annulla',
    'comune.conferma':  'Conferma',
    'comune.e':         ' e ',
    'err.busy':         "C'è già qualcosa in corso.",
    'scorciatoie':      'Invio per leggere il video  ·  Ctrl+Invio per trascrivere',
    'trascina':         'Lascia qui il link o il file',

    # ── Sezione «Trascrivi»: sorgente ────────────────────────────────────────
    'src.label':        'Cosa trascrivo',
    'src.youtube':      'Un video YouTube',
    'src.local':        'Un file sul computer',
    'src.input.url':    'Link del video o della playlist',
    'src.input.file':   'File audio o video',
    'src.load':         "Guarda cos'è",
    'src.load.loading': 'Leggo…',
    'src.load.playlist': 'Leggo i video della playlist…',
    'src.panel':        'Sorgente',
    'src.empty':        "Incolla un link e premi «Guarda cos'è», oppure scegli un file.",
    'src.start':        'Trascrivi',
    'src.busy':         'Elaborazione in corso…',

    # ── Sezione «Trascrivi»: output aggiuntivi ───────────────────────────────
    'opts.title':       'Output aggiuntivi',
    'opt.translate':    'Traduci in italiano',
    'opt.translate.desc': 'Traduzione in /traduzioni, con il modello di testo del '
                          'motore scelto (Ollama in locale, Groq in nuvola).',
    'opt.summary':      'Crea riassunto',
    'opt.summary.desc': 'Riassunto pulito per sezione in /riassunti, con lo stesso '
                        'modello di testo della traduzione.',
    'opt.visual':       'Analisi visiva del video',
    'opt.visual.desc':  '«Guarda» i fotogrammi ed estrae codice, formule e grafici a '
                        'schermo, nel riassunto più un documento con i frame. Più '
                        'lento; usa il modello vision del motore scelto (Ollama in '
                        'locale, Groq in nuvola: più crediti).',

    # ── Scheda della sorgente ────────────────────────────────────────────────
    'info.channel':     'Canale',
    'info.views':       'Visualizzazioni',
    'info.date':        'Data',
    'info.duration':    'Durata',
    'info.chapters':    'Capitoli',
    'info.likes':       'Mi piace',
    'info.subs':        'Iscritti',
    'info.category':    'Categoria',
    'info.language':    'Lingua audio',
    'info.file':        'File',
    'info.videos':      'Video',
    'chapters.some':    '{n} sezioni',
    'chapters.none':    'nessuno',

    'confirm.title':    'Conferma il video',
    'confirm.question': 'È questo il video che vuoi trascrivere?',
    'confirm.ok':       '✓ Video confermato: {titolo}',

    'playlist.title':   'Conferma la playlist',
    'playlist.question': 'Trascrivo tutti i {n} video di questa playlist?',
    'playlist.ok':      '✓ Playlist «{titolo}» · {n} video',
    'playlist.none':    'Nessun video disponibile nella playlist.',
    'playlist.batch':   'Video {i}/{n}',
    'playlist.res.title': 'Playlist completata',
    'playlist.res.done':  '{n} trascritti',
    'playlist.res.skipped': '{n} già presenti (saltati)',
    'playlist.res.failed':  '{n} non riusciti',
    'playlist.res.folder':  'Cartella della playlist',
    'playlist.stopped':  'Batch interrotto: crediti Groq esauriti. I video già '
                         'trascritti sono salvati; riprendi domani.',

    # ── Sezioni «Locale» e «Cloud» ───────────────────────────────────────────
    'eng.tag.cloud':    'CLOUD',
    'eng.tag.offline':  'OFFLINE',

    'eng.local.hint':   'Tutto quello che serve gira qui, senza rete e senza chiave: '
                        'trascrizione (Whisper), riassunto e traduzione (Ollama), '
                        'analisi visiva (Ollama vision). ✓ = già scaricato in Ollama.',
    'eng.model.whisper': 'Trascrizione (Whisper)',
    'eng.model.ollama':  'Riassunto e traduzione (Ollama)',
    'eng.model.vision':  'Analisi visiva (Ollama vision)',

    'eng.groq.hint':    'Gli stessi tre mestieri, ma in nuvola e a carico della '
                        'chiave: trascrizione, riassunto e traduzione, analisi '
                        'visiva. Niente di tutto questo tocca il tuo computer.',
    'eng.model.groq':   'Trascrizione (Whisper su Groq)',
    'eng.model.groqtesto': 'Riassunto e traduzione (Groq)',
    'eng.model.groqvista': 'Analisi visiva (Groq vision)',
    'eng.key':          'Chiave API',
    'eng.key.load':     'Carica da file .txt',
    'eng.key.get':      'Ottieni una chiave →',
    'eng.key.loaded':   '✓ {nome}',
    'eng.key.none':     'Nessun file caricato (in alternativa la chiave può stare '
                        'nel file .env).',
    'eng.key.unreadable': 'Non riesco a leggere il file della chiave: {e}',
    'eng.key.invalid':  'Il file scelto non contiene una chiave valida.',

    # Modelli Whisper locali.
    'model.base':       'base: veloce, meno accurato',
    'model.small':      'small: equilibrio consigliato ★',
    'model.medium':     'medium: più accurato, più lento',
    'model.large-v3':   'large-v3: massima accuratezza, molto lento',
    'model.large-v3-turbo': 'large-v3-turbo: quasi large, più rapido',

    # Modelli Groq di trascrizione.
    'groqm.whisper-large-v3-turbo': 'whisper-large-v3-turbo: $0.04/ora · veloce, consigliato',
    'groqm.whisper-large-v3': 'whisper-large-v3: $0.111/ora · più accurato',

    # Modelli Groq di testo (riassunto e traduzione) e di analisi visiva, per
    # numero di catalogo, come per Ollama: cosi' aggiungerne uno resta una riga
    # in transcriber.py e una qui.
    'gm.text.1':        'qualità piena, consigliato',
    'gm.text.2':        'più economico e rapido',
    'gm.vis.1':         'multimodale, ottimo con slide e codice',

    # Descrizioni dei modelli Ollama, per numero di catalogo.
    'om.text.1':        'leggero e moderno · ideale con 8 GB di RAM',
    'om.text.2':        'equilibrio qualità/peso (default)',
    'om.text.3':        'più accurato · 12-16 GB di RAM',
    'om.text.4':        'ottimo multilingua · 16 GB di RAM',
    'om.text.5':        'qualità vicina al cloud · 24 GB+ o GPU',
    'om.vis.1':         'leggero, ottimo OCR · ideale con 8 GB di RAM',
    'om.vis.2':         'multimodale leggero, buon multilingua',
    'om.vis.3':         'buon equilibrio · 12-16 GB di RAM',
    'om.vis.4':         'default storico · 16 GB di RAM',
    'om.vis.5':         'qualità vicina al cloud · 32 GB+ o GPU',

    # ── Stima prima di partire ───────────────────────────────────────────────
    'est.cost':         'Costo stimato ~${c} · Groq {m}',
    'est.time':         'Tempo stimato ~{t} su {d} · offline',

    # ── Cosa manca per partire ───────────────────────────────────────────────
    'warn.title':       'Manca qualcosa',
    'warn.prefix':      'Per avviare la trascrizione serve:',
    'warn.key':         'caricare la chiave API Groq (sezione «Motore»)',
    'warn.src.yt':      'caricare e confermare il video YouTube',
    'warn.src.local':   'scegliere un file audio',

    # ── Avanzamento ──────────────────────────────────────────────────────────
    'prog.title':       'Cosa sta facendo',
    'prog.steps':       'Passaggi',
    'prog.plan':        'Piano:',
    'prog.phase':       'Fase {i}/{n}',
    'phase.default':    'In corso…',
    'phase.info':       'Lettura informazioni',
    'phase.download':   'Download audio',
    'phase.prepare':    'Preparazione audio',
    'phase.transcribe': 'Trascrizione',
    'phase.translate':  'Traduzione in italiano',
    'phase.summarize':  'Riassunto',
    'phase.visual':     'Analisi visiva',
    'phase.export':     'Esportazione / salvataggio',

    'engine.groq':      'Groq (cloud) · {model}',
    'engine.local':     'Locale · faster-whisper {model}',
    'engine.local.hint': 'La trascrizione locale gira sulla CPU: può richiedere '
                         'diversi minuti.',

    'ov.base':          "trascrivo l'audio",
    'ov.visual':        'analizzo i fotogrammi del video',
    'ov.translate':     'lo traduco in italiano',
    'ov.summary':       'creo il riassunto',
    'ov.save':          'salvo i file (PDF incluso)',

    'narr.info':        'Leggo le informazioni della sorgente e preparo l\'elaborazione…',
    'narr.download':    'Scarico la traccia audio dal video…',
    'narr.prepare':     'Preparo l\'audio e lo divido in blocchi per Groq…',
    'narr.transcribe':  'Converto il parlato in testo, blocco per blocco…',
    'narr.export':      'Salvo la trascrizione e genero il PDF…',
    'narr.translate':   'Traduco il testo, sezione per sezione…',
    'narr.summarize':   'Creo un riassunto pulito per ogni sezione…',
    'narr.visual':      'Guardo i fotogrammi ed estraggo codice, formule e grafici…',

    # ── Video già trascritto / ripresa ──────────────────────────────────────
    'already.title':    'Questo video c\'è già',
    'already.desc':     'È già nella cartella dei risultati. Cosa vuoi fare?',
    'already.again':    'Trascrivi nuovamente',
    'already.again.desc': 'Rifà tutto da capo: trascrizione, traduzione e riassunto.',
    'already.resume':   'Riprendi da dove si è interrotto',
    'already.resume.desc': 'Continua dalla fase in cui l\'operazione si era fermata.',
    'already.translate': 'Solo traduzione',
    'already.translate.desc': 'Traduce la trascrizione salvata. Nessun credito di '
                              'trascrizione speso.',
    'already.summary':  'Solo riassunto',
    'already.summary.desc': 'Genera solo il riassunto dal testo salvato (la traduzione '
                            'se c\'è, altrimenti l\'originale).',

    'resume.title':     'Ripresa disponibile',
    'resume.desc':      'Una trascrizione di questo video si era interrotta. Cosa vuoi '
                        'fare?',
    'resume.go':        'Riprendi',
    'resume.go.desc':   'Continua dalla posizione salvata ({fatto} / {totale}).',
    'resume.restart':   'Ricomincia da capo',
    'resume.restart.desc': 'Ignora il parziale e ritrascrive tutto da zero.',

    # ── Crediti esauriti ─────────────────────────────────────────────────────
    'rate.title':       'Crediti Groq esauriti',
    'rate.msg':         'I crediti gratuiti Groq per oggi sono terminati.\n\n'
                        'La trascrizione si è fermata a {fatto} su {totale} ed è '
                        'stata salvata automaticamente.\n\n'
                        'Quando i crediti torneranno disponibili (di norma domani) '
                        'riapri questo video e scegli «Riprendi». In alternativa puoi '
                        'completarlo subito sul tuo computer.',
    'rate.later':       'Riprendo domani',
    'rate.local':       'Continua ora in locale',

    'sumlocal.title':   'Riassunto interrotto',
    'sumlocal.msg':     'I crediti Groq sono terminati durante il riassunto, che è '
                        'stato salvato come parziale.\n\nVuoi concluderlo ora in locale '
                        'con Ollama, ripartendo dalla sezione in cui si è fermato?',
    'sumlocal.yes':     'Concludi in locale',
    'sumlocal.no':      'Riprendo più tardi',

    # ── Risultato ────────────────────────────────────────────────────────────
    'res.title':        'Completato',
    'res.engine':       'Motore',
    'res.segments':     'Segmenti',
    'res.words':        'Parole',
    'res.sections':     'Sezioni',
    'res.continuous':   'testo continuo',
    'res.saved':        'Salvato in:',
    'res.root':         '(radice)',
    'res.open':         'Apri la cartella',
    'res.credits':      'Crediti Groq',
    'res.credits.used': 'Audio trascritto',
    'res.credits.left': 'Audio residuo oggi',
    'res.visual':       'Analisi visiva',
    'res.visual.count': '{n} fotogrammi con contenuto estratto',
    'res.visual.open':  'Apri l\'analisi visiva',

    # ── Crediti (sezione dedicata) ───────────────────────────────────────────

    # ── Errori ───────────────────────────────────────────────────────────────
    'err.title':        'Errore',
    'err.unknown':      'Errore sconosciuto.',
    'err.no_url':       'Incolla prima il link del video.',
    'err.no_file':      'Scegli prima un file audio.',
    'err.unexpected':   'Errore imprevisto: {e}',
}
