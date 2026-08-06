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
    ``str.format`` — ``{titolo}``, ``{n}`` — e la pagina li sostituisce con la
    stessa convenzione, quindi la stessa frase funziona da tutt'e due i lati.
"""
from __future__ import annotations

TESTI: dict[str, dict[str, str]] = {

    # ── Cornice: marchio, barra laterale, sezioni ────────────────────────────
    'app.subtitle':     {'it': 'Ascolta  ·  Trascrivi  ·  Traduci',
                         'en': 'Listen  ·  Transcribe  ·  Translate'},
    'app.language':     {'it': 'Lingua', 'en': 'Language'},

    'menu.locale':      {'it': 'Locale', 'en': 'Local'},
    'menu.cloud':       {'it': 'Cloud', 'en': 'Cloud'},
    'menu.crediti':     {'it': 'Crediti', 'en': 'Credits'},

    'sez.locale.title': {'it': 'Trascrivi sul tuo computer',
                         'en': 'Transcribe on your computer'},
    'sez.locale.desc':  {'it': "Quello che parte da qui gira su questa macchina, con i modelli "
                               "scelti qui sotto: niente rete, niente chiave, niente crediti. "
                               "L'audio non esce di casa.",
                         'en': 'Anything started here runs on this machine, with the models '
                               'chosen below: no network, no key, no credits. The audio never '
                               'leaves the house.'},
    'sez.cloud.title':  {'it': 'Trascrivi sui server Groq',
                         'en': 'Transcribe on the Groq servers'},
    'sez.cloud.desc':   {'it': "Quello che parte da qui gira in nuvola, con i modelli scelti "
                               "qui sotto e a carico della chiave. Molto più veloce, ma "
                               "l'audio viene inviato a Groq e ogni lavoro consuma crediti.",
                         'en': 'Anything started here runs in the cloud, with the models '
                               'chosen below and charged to the key. Far faster, but the audio '
                               'is sent to Groq and every job spends credits.'},
    'sez.crediti.title': {'it': 'Crediti Groq', 'en': 'Groq credits'},
    'sez.crediti.desc':  {'it': "Quanto audio hai già mandato a Groq e quanto te ne resta oggi.",
                          'en': 'How much audio you already sent to Groq, and how much is left '
                                'today.'},

    # ── Diario e stato ───────────────────────────────────────────────────────
    'log.title':        {'it': 'Diario', 'en': 'Log'},
    'log.clear':        {'it': 'Svuota', 'en': 'Clear'},
    'log.empty':        {'it': 'Qui compare quello che sta succedendo.',
                         'en': 'What is happening shows up here.'},
    # L'ultima riga del diario. Il simbolo non e' decorazione: la pagina colora
    # le righe leggendole, e la spunta e' cio' che le fa venire verdi.
    'log.done':         {'it': '✓ Fatto', 'en': '✓ Done'},
    'status.idle':      {'it': 'In attesa', 'en': 'Idle'},
    'status.working':   {'it': 'In corso', 'en': 'Working'},
    'status.done':      {'it': 'Fatto', 'en': 'Done'},
    'status.error':     {'it': 'Errore', 'en': 'Error'},

    'comune.chiudi':    {'it': 'Chiudi', 'en': 'Close'},
    'comune.annulla':   {'it': 'Annulla', 'en': 'Cancel'},
    'comune.conferma':  {'it': 'Conferma', 'en': 'Confirm'},
    'comune.e':         {'it': ' e ', 'en': ' and '},
    'err.busy':         {'it': "C'è già qualcosa in corso.",
                         'en': 'Something is already running.'},
    'scorciatoie':      {'it': 'Invio per leggere il video  ·  Ctrl+Invio per trascrivere',
                         'en': 'Enter to read the video  ·  Ctrl+Enter to transcribe'},
    'trascina':         {'it': 'Lascia qui il link o il file',
                         'en': 'Drop the link or the file here'},

    # ── Sezione «Trascrivi»: sorgente ────────────────────────────────────────
    'src.label':        {'it': 'Cosa trascrivo', 'en': 'What to transcribe'},
    'src.youtube':      {'it': 'Un video YouTube', 'en': 'A YouTube video'},
    'src.local':        {'it': 'Un file sul computer', 'en': 'A file on this computer'},
    'src.input.url':    {'it': 'Link del video o della playlist',
                         'en': 'Link to the video or the playlist'},
    'src.input.file':   {'it': 'File audio o video', 'en': 'Audio or video file'},
    'src.load':         {'it': "Guarda cos'è", 'en': 'See what it is'},
    'src.load.loading': {'it': 'Leggo…', 'en': 'Reading…'},
    'src.load.playlist': {'it': 'Leggo i video della playlist…',
                          'en': 'Reading the playlist videos…'},
    'src.panel':        {'it': 'Sorgente', 'en': 'Source'},
    'src.empty':        {'it': "Incolla un link e premi «Guarda cos'è», oppure scegli un file.",
                         'en': 'Paste a link and press "See what it is", or pick a file.'},
    'src.start':        {'it': 'Trascrivi', 'en': 'Transcribe'},
    'src.busy':         {'it': 'Elaborazione in corso…', 'en': 'Processing…'},

    # ── Sezione «Trascrivi»: output aggiuntivi ───────────────────────────────
    'opts.title':       {'it': 'Output aggiuntivi', 'en': 'Extra outputs'},
    'opt.translate':    {'it': 'Traduci in italiano', 'en': 'Translate to English'},
    'opt.translate.desc': {'it': 'Traduzione in /traduzioni, con il modello di testo del '
                                 'motore scelto (Ollama in locale, Groq in nuvola).',
                           'en': 'Translation in /translations, using the text model of the '
                                 'chosen engine (Ollama locally, Groq in the cloud).'},
    'opt.summary':      {'it': 'Crea riassunto', 'en': 'Create summary'},
    'opt.summary.desc': {'it': 'Riassunto pulito per sezione in /riassunti, con lo stesso '
                               'modello di testo della traduzione.',
                         'en': 'Clean per-section summary in /summaries, using the same text '
                               'model as the translation.'},
    'opt.visual':       {'it': 'Analisi visiva del video', 'en': 'Visual analysis of the video'},
    'opt.visual.desc':  {'it': '«Guarda» i fotogrammi ed estrae codice, formule e grafici a '
                               'schermo, nel riassunto più un documento con i frame. Più '
                               'lento; usa il modello vision del motore scelto (Ollama in '
                               'locale, Groq in nuvola: più crediti).',
                         'en': 'It "looks" at the frames and extracts on-screen code, formulas '
                               'and charts, into the summary plus a document with the frames. '
                               'Slower; uses the vision model of the chosen engine (Ollama '
                               'locally, Groq in the cloud: more credits).'},

    # ── Scheda della sorgente ────────────────────────────────────────────────
    'info.channel':     {'it': 'Canale', 'en': 'Channel'},
    'info.views':       {'it': 'Visualizzazioni', 'en': 'Views'},
    'info.date':        {'it': 'Data', 'en': 'Date'},
    'info.duration':    {'it': 'Durata', 'en': 'Duration'},
    'info.chapters':    {'it': 'Capitoli', 'en': 'Chapters'},
    'info.likes':       {'it': 'Mi piace', 'en': 'Likes'},
    'info.subs':        {'it': 'Iscritti', 'en': 'Subscribers'},
    'info.category':    {'it': 'Categoria', 'en': 'Category'},
    'info.language':    {'it': 'Lingua audio', 'en': 'Audio language'},
    'info.file':        {'it': 'File', 'en': 'File'},
    'info.videos':      {'it': 'Video', 'en': 'Videos'},
    'chapters.some':    {'it': '{n} sezioni', 'en': '{n} sections'},
    'chapters.none':    {'it': 'nessuno', 'en': 'none'},

    'confirm.title':    {'it': 'Conferma il video', 'en': 'Confirm the video'},
    'confirm.question': {'it': 'È questo il video che vuoi trascrivere?',
                         'en': 'Is this the video you want to transcribe?'},
    'confirm.ok':       {'it': '✓ Video confermato: {titolo}',
                         'en': '✓ Video confirmed: {titolo}'},

    'playlist.title':   {'it': 'Conferma la playlist', 'en': 'Confirm the playlist'},
    'playlist.question': {'it': 'Trascrivo tutti i {n} video di questa playlist?',
                          'en': 'Transcribe all {n} videos in this playlist?'},
    'playlist.ok':      {'it': '✓ Playlist «{titolo}» · {n} video',
                         'en': '✓ Playlist «{titolo}» · {n} videos'},
    'playlist.none':    {'it': 'Nessun video disponibile nella playlist.',
                         'en': 'No available videos in the playlist.'},
    'playlist.batch':   {'it': 'Video {i}/{n}', 'en': 'Video {i}/{n}'},
    'playlist.res.title': {'it': 'Playlist completata', 'en': 'Playlist complete'},
    'playlist.res.done':  {'it': '{n} trascritti', 'en': '{n} transcribed'},
    'playlist.res.skipped': {'it': '{n} già presenti (saltati)',
                             'en': '{n} already present (skipped)'},
    'playlist.res.failed':  {'it': '{n} non riusciti', 'en': '{n} failed'},
    'playlist.res.folder':  {'it': 'Cartella della playlist', 'en': 'Playlist folder'},
    'playlist.stopped':  {'it': 'Batch interrotto: crediti Groq esauriti. I video già '
                                'trascritti sono salvati; riprendi domani.',
                          'en': 'Batch stopped: Groq credits exhausted. Completed videos are '
                                'saved; resume tomorrow.'},

    # ── Sezioni «Locale» e «Cloud» ───────────────────────────────────────────
    'eng.tag.cloud':    {'it': 'CLOUD', 'en': 'CLOUD'},
    'eng.tag.offline':  {'it': 'OFFLINE', 'en': 'OFFLINE'},

    'eng.local.title':  {'it': 'Solo modelli sul tuo computer',
                         'en': 'Only models on your computer'},
    'eng.local.hint':   {'it': 'Tutto quello che serve gira qui, senza rete e senza chiave: '
                               'trascrizione (Whisper), riassunto e traduzione (Ollama), '
                               'analisi visiva (Ollama vision). ✓ = già scaricato in Ollama.',
                         'en': 'Everything runs here, with no network and no key: '
                               'transcription (Whisper), summary and translation (Ollama), '
                               'visual analysis (Ollama vision). ✓ = already pulled in Ollama.'},
    'eng.model.whisper': {'it': 'Trascrizione (Whisper)', 'en': 'Transcription (Whisper)'},
    'eng.model.ollama':  {'it': 'Riassunto e traduzione (Ollama)',
                          'en': 'Summary and translation (Ollama)'},
    'eng.model.vision':  {'it': 'Analisi visiva (Ollama vision)',
                          'en': 'Visual analysis (Ollama vision)'},

    'eng.groq.title':   {'it': 'Solo modelli sui server Groq',
                         'en': 'Only models on the Groq servers'},
    'eng.groq.hint':    {'it': 'Gli stessi tre mestieri, ma in nuvola e a carico della '
                               'chiave: trascrizione, riassunto e traduzione, analisi '
                               'visiva. Niente di tutto questo tocca il tuo computer.',
                         'en': 'The same three jobs, but in the cloud and charged to the '
                               'key: transcription, summary and translation, visual '
                               'analysis. None of it touches your computer.'},
    'eng.model.groq':   {'it': 'Trascrizione (Whisper su Groq)',
                         'en': 'Transcription (Whisper on Groq)'},
    'eng.model.groqtesto': {'it': 'Riassunto e traduzione (Groq)',
                            'en': 'Summary and translation (Groq)'},
    'eng.model.groqvista': {'it': 'Analisi visiva (Groq vision)',
                            'en': 'Visual analysis (Groq vision)'},
    'eng.key':          {'it': 'Chiave API', 'en': 'API key'},
    'eng.key.hint':     {'it': 'Scegli il file .txt con la chiave: viene letta e tenuta in '
                               'memoria per questa sessione. A schermo resta solo il nome del '
                               'file.',
                         'en': 'Pick the .txt file with the key: it is read and kept in memory '
                               'for this session. Only the file name stays on screen.'},
    'eng.key.load':     {'it': 'Carica da file .txt', 'en': 'Load from a .txt file'},
    'eng.key.get':      {'it': 'Ottieni una chiave →', 'en': 'Get a key →'},
    'eng.key.loaded':   {'it': '✓ {nome}', 'en': '✓ {nome}'},
    'eng.key.none':     {'it': 'Nessun file caricato (in alternativa la chiave può stare '
                               'nel file .env).',
                         'en': 'No file loaded (the key can also live in the .env file).'},
    'eng.key.unreadable': {'it': 'Non riesco a leggere il file della chiave: {e}',
                           'en': 'Cannot read the key file: {e}'},
    'eng.key.invalid':  {'it': 'Il file scelto non contiene una chiave valida.',
                         'en': 'The chosen file does not contain a valid key.'},

    # Modelli Whisper locali.
    'model.base':       {'it': 'base: veloce, meno accurato',
                         'en': 'base: fast, less accurate'},
    'model.small':      {'it': 'small: equilibrio consigliato ★',
                         'en': 'small: recommended balance ★'},
    'model.medium':     {'it': 'medium: più accurato, più lento',
                         'en': 'medium: more accurate, slower'},
    'model.large-v3':   {'it': 'large-v3: massima accuratezza, molto lento',
                         'en': 'large-v3: top accuracy, very slow'},
    'model.large-v3-turbo': {'it': 'large-v3-turbo: quasi large, più rapido',
                             'en': 'large-v3-turbo: near large, faster'},

    # Modelli Groq di trascrizione.
    'groqm.whisper-large-v3-turbo': {'it': 'whisper-large-v3-turbo: $0.04/ora · veloce, consigliato',
                                     'en': 'whisper-large-v3-turbo: $0.04/hr · fast, recommended'},
    'groqm.whisper-large-v3': {'it': 'whisper-large-v3: $0.111/ora · più accurato',
                               'en': 'whisper-large-v3: $0.111/hr · more accurate'},

    # Modelli Groq di testo (riassunto e traduzione) e di analisi visiva, per
    # numero di catalogo — come per Ollama, cosi' aggiungerne uno resta una riga
    # in transcriber.py e una qui.
    'gm.text.1':        {'it': 'qualità piena, consigliato', 'en': 'full quality, recommended'},
    'gm.text.2':        {'it': 'più economico e rapido', 'en': 'cheaper and faster'},
    'gm.vis.1':         {'it': 'multimodale, ottimo con slide e codice',
                         'en': 'multimodal, great with slides and code'},

    # Descrizioni dei modelli Ollama, per numero di catalogo.
    'om.text.1':        {'it': 'leggero e moderno · ideale con 8 GB di RAM',
                         'en': 'light and modern · ideal with 8 GB of RAM'},
    'om.text.2':        {'it': 'equilibrio qualità/peso (default)',
                         'en': 'quality/size balance (default)'},
    'om.text.3':        {'it': 'più accurato · 12-16 GB di RAM',
                         'en': 'more accurate · 12-16 GB of RAM'},
    'om.text.4':        {'it': 'ottimo multilingua · 16 GB di RAM',
                         'en': 'great multilingual · 16 GB of RAM'},
    'om.text.5':        {'it': 'qualità vicina al cloud · 24 GB+ o GPU',
                         'en': 'near-cloud quality · 24 GB+ or GPU'},
    'om.vis.1':         {'it': 'leggero, ottimo OCR · ideale con 8 GB di RAM',
                         'en': 'light, great OCR · ideal with 8 GB of RAM'},
    'om.vis.2':         {'it': 'multimodale leggero, buon multilingua',
                         'en': 'light multimodal, good multilingual'},
    'om.vis.3':         {'it': 'buon equilibrio · 12-16 GB di RAM',
                         'en': 'good balance · 12-16 GB of RAM'},
    'om.vis.4':         {'it': 'default storico · 16 GB di RAM',
                         'en': 'long-time default · 16 GB of RAM'},
    'om.vis.5':         {'it': 'qualità vicina al cloud · 32 GB+ o GPU',
                         'en': 'near-cloud quality · 32 GB+ or GPU'},

    # ── Stima prima di partire ───────────────────────────────────────────────
    'est.cost':         {'it': 'Costo stimato ~${c} · Groq {m}',
                         'en': 'Estimated cost ~${c} · Groq {m}'},
    'est.time':         {'it': 'Tempo stimato ~{t} su {d} · offline',
                         'en': 'Estimated time ~{t} on {d} · offline'},

    # ── Cosa manca per partire ───────────────────────────────────────────────
    'warn.title':       {'it': 'Manca qualcosa', 'en': "Something's missing"},
    'warn.prefix':      {'it': 'Per avviare la trascrizione serve:',
                         'en': 'To start transcribing you need to:'},
    'warn.key':         {'it': 'caricare la chiave API Groq (sezione «Motore»)',
                         'en': 'load the Groq API key (the "Engine" section)'},
    'warn.src.yt':      {'it': 'caricare e confermare il video YouTube',
                         'en': 'load and confirm the YouTube video'},
    'warn.src.local':   {'it': 'scegliere un file audio',
                         'en': 'choose an audio file'},

    # ── Avanzamento ──────────────────────────────────────────────────────────
    'prog.title':       {'it': 'Cosa sta facendo', 'en': 'What it is doing'},
    'prog.steps':       {'it': 'Passaggi', 'en': 'Steps'},
    'prog.plan':        {'it': 'Piano:', 'en': 'Plan:'},
    'prog.phase':       {'it': 'Fase {i}/{n}', 'en': 'Phase {i}/{n}'},
    'phase.default':    {'it': 'In corso…', 'en': 'Working…'},
    'phase.info':       {'it': 'Lettura informazioni', 'en': 'Reading information'},
    'phase.download':   {'it': 'Download audio', 'en': 'Downloading audio'},
    'phase.prepare':    {'it': 'Preparazione audio', 'en': 'Preparing audio'},
    'phase.transcribe': {'it': 'Trascrizione', 'en': 'Transcribing'},
    'phase.translate':  {'it': 'Traduzione in italiano', 'en': 'Translating to English'},
    'phase.summarize':  {'it': 'Riassunto', 'en': 'Summarizing'},
    'phase.visual':     {'it': 'Analisi visiva', 'en': 'Visual analysis'},
    'phase.export':     {'it': 'Esportazione / salvataggio', 'en': 'Exporting / saving'},

    'engine.groq':      {'it': 'Groq (cloud) · {model}', 'en': 'Groq (cloud) · {model}'},
    'engine.local':     {'it': 'Locale · faster-whisper {model}',
                         'en': 'Local · faster-whisper {model}'},
    'engine.local.hint': {'it': 'La trascrizione locale gira sulla CPU: può richiedere '
                                'diversi minuti.',
                          'en': 'Local transcription runs on the CPU: it can take several '
                                'minutes.'},

    'ov.base':          {'it': "trascrivo l'audio", 'en': 'transcribe the audio'},
    'ov.visual':        {'it': 'analizzo i fotogrammi del video',
                         'en': 'analyze the video frames'},
    'ov.translate':     {'it': 'lo traduco in italiano', 'en': 'translate it to English'},
    'ov.summary':       {'it': 'creo il riassunto', 'en': 'create the summary'},
    'ov.save':          {'it': 'salvo i file (PDF incluso)', 'en': 'save the files (PDF included)'},

    'narr.info':        {'it': 'Leggo le informazioni della sorgente e preparo l\'elaborazione…',
                         'en': 'Reading the source info and getting ready…'},
    'narr.download':    {'it': 'Scarico la traccia audio dal video…',
                         'en': 'Downloading the audio track from the video…'},
    'narr.prepare':     {'it': 'Preparo l\'audio e lo divido in blocchi per Groq…',
                         'en': 'Preparing the audio and splitting it into chunks for Groq…'},
    'narr.transcribe':  {'it': 'Converto il parlato in testo, blocco per blocco…',
                         'en': 'Turning speech into text, chunk by chunk…'},
    'narr.export':      {'it': 'Salvo la trascrizione e genero il PDF…',
                         'en': 'Saving the transcription and generating the PDF…'},
    'narr.translate':   {'it': 'Traduco il testo, sezione per sezione…',
                         'en': 'Translating the text, section by section…'},
    'narr.summarize':   {'it': 'Creo un riassunto pulito per ogni sezione…',
                         'en': 'Creating a clean summary for each section…'},
    'narr.visual':      {'it': 'Guardo i fotogrammi ed estraggo codice, formule e grafici…',
                         'en': 'Looking at the frames and extracting code, formulas and charts…'},

    # ── Video già trascritto / ripresa ──────────────────────────────────────
    'already.title':    {'it': 'Questo video c\'è già', 'en': 'This video is already there'},
    'already.desc':     {'it': 'È già nella cartella dei risultati. Cosa vuoi fare?',
                         'en': 'It is already in the results folder. What do you want to do?'},
    'already.again':    {'it': 'Trascrivi nuovamente', 'en': 'Transcribe again'},
    'already.again.desc': {'it': 'Rifà tutto da capo: trascrizione, traduzione e riassunto.',
                           'en': 'Redo everything from scratch: transcription, translation and '
                                 'summary.'},
    'already.resume':   {'it': 'Riprendi da dove si è interrotto',
                         'en': 'Resume where it stopped'},
    'already.resume.desc': {'it': 'Continua dalla fase in cui l\'operazione si era fermata.',
                            'en': 'Continue from the stage where the run was interrupted.'},
    'already.translate': {'it': 'Solo traduzione', 'en': 'Translation only'},
    'already.translate.desc': {'it': 'Traduce la trascrizione salvata. Nessun credito di '
                                     'trascrizione speso.',
                               'en': 'Translates the saved transcription. No transcription '
                                     'credits spent.'},
    'already.summary':  {'it': 'Solo riassunto', 'en': 'Summary only'},
    'already.summary.desc': {'it': 'Genera solo il riassunto dal testo salvato (la traduzione '
                                   'se c\'è, altrimenti l\'originale).',
                             'en': 'Generates only the summary from the saved text (the '
                                   'translation if present, else the original).'},

    'resume.title':     {'it': 'Ripresa disponibile', 'en': 'Resume available'},
    'resume.desc':      {'it': 'Una trascrizione di questo video si era interrotta. Cosa vuoi '
                               'fare?',
                         'en': 'A transcription of this video was interrupted. What do you want '
                               'to do?'},
    'resume.go':        {'it': 'Riprendi', 'en': 'Resume'},
    'resume.go.desc':   {'it': 'Continua dalla posizione salvata ({fatto} / {totale}).',
                         'en': 'Continue from the saved position ({fatto} / {totale}).'},
    'resume.restart':   {'it': 'Ricomincia da capo', 'en': 'Start over'},
    'resume.restart.desc': {'it': 'Ignora il parziale e ritrascrive tutto da zero.',
                            'en': 'Discard the partial and re-transcribe from scratch.'},

    # ── Crediti esauriti ─────────────────────────────────────────────────────
    'rate.title':       {'it': 'Crediti Groq esauriti', 'en': 'Groq credits exhausted'},
    'rate.msg':         {'it': 'I crediti gratuiti Groq per oggi sono terminati.\n\n'
                               'La trascrizione si è fermata a {fatto} su {totale} ed è '
                               'stata salvata automaticamente.\n\n'
                               'Quando i crediti torneranno disponibili (di norma domani) '
                               'riapri questo video e scegli «Riprendi». In alternativa puoi '
                               'completarlo subito sul tuo computer.',
                         'en': "Today's free Groq credits are used up.\n\n"
                               'Transcription stopped at {fatto} of {totale} and was saved '
                               'automatically.\n\n'
                               'When credits become available again (usually tomorrow), reopen '
                               'this video and choose "Resume". Alternatively, you can finish '
                               'it now on your own computer.'},
    'rate.later':       {'it': 'Riprendo domani', 'en': "I'll resume tomorrow"},
    'rate.local':       {'it': 'Continua ora in locale', 'en': 'Continue now, locally'},

    'sumlocal.title':   {'it': 'Riassunto interrotto', 'en': 'Summary interrupted'},
    'sumlocal.msg':     {'it': 'I crediti Groq sono terminati durante il riassunto, che è '
                               'stato salvato come parziale.\n\nVuoi concluderlo ora in locale '
                               'con Ollama, ripartendo dalla sezione in cui si è fermato?',
                         'en': 'Groq credits ran out during the summary, which was saved as a '
                               'partial.\n\nDo you want to finish it now locally with Ollama, '
                               'resuming from the section where it stopped?'},
    'sumlocal.yes':     {'it': 'Concludi in locale', 'en': 'Finish locally'},
    'sumlocal.no':      {'it': 'Riprendo più tardi', 'en': "I'll resume later"},

    # ── Risultato ────────────────────────────────────────────────────────────
    'res.title':        {'it': 'Completato', 'en': 'Done'},
    'res.engine':       {'it': 'Motore', 'en': 'Engine'},
    'res.segments':     {'it': 'Segmenti', 'en': 'Segments'},
    'res.words':        {'it': 'Parole', 'en': 'Words'},
    'res.sections':     {'it': 'Sezioni', 'en': 'Sections'},
    'res.continuous':   {'it': 'testo continuo', 'en': 'continuous text'},
    'res.saved':        {'it': 'Salvato in:', 'en': 'Saved in:'},
    'res.root':         {'it': '(radice)', 'en': '(root)'},
    'res.open':         {'it': 'Apri la cartella', 'en': 'Open the folder'},
    'res.credits':      {'it': 'Crediti Groq', 'en': 'Groq credits'},
    'res.credits.used': {'it': 'Audio trascritto', 'en': 'Audio transcribed'},
    'res.credits.left': {'it': 'Audio residuo oggi', 'en': 'Audio left today'},
    'res.visual':       {'it': 'Analisi visiva', 'en': 'Visual analysis'},
    'res.visual.count': {'it': '{n} fotogrammi con contenuto estratto',
                         'en': '{n} frames with extracted content'},
    'res.visual.open':  {'it': 'Apri l\'analisi visiva', 'en': 'Open the visual analysis'},

    # ── Crediti (sezione dedicata) ───────────────────────────────────────────
    'lim.note':         {'it': 'Letti dalle richieste già fatte (trascrizione, riassunto, '
                               'analisi visiva): aprire questa pagina NON contatta Groq e non '
                               'consuma alcun credito.',
                         'en': 'Read from requests you already made (transcription, summary, '
                               'visual analysis): opening this page does NOT contact Groq and '
                               'spends no credits.'},
    'lim.empty':        {'it': 'Ancora nessun dato. Esegui una trascrizione, un riassunto o '
                               'un\'analisi visiva: i crediti residui di ciascun modello '
                               'compariranno qui, senza spendere nulla per controllare.',
                         'en': 'No data yet. Run a transcription, a summary or a visual '
                               'analysis: each model\'s remaining credits will show up here, '
                               'without spending anything to check.'},
    'lim.refresh':      {'it': 'Aggiorna', 'en': 'Refresh'},
    'lim.role.transcription': {'it': 'Trascrizione', 'en': 'Transcription'},
    'lim.role.summary': {'it': 'Riassunto', 'en': 'Summary'},
    'lim.role.vision':  {'it': 'Analisi visiva', 'en': 'Visual analysis'},
    'lim.role.other':   {'it': 'Altro', 'en': 'Other'},
    'lim.checked':      {'it': 'aggiornato alle {v}', 'en': 'updated at {v}'},
    'lim.kind.audio_seconds': {'it': 'Audio (secondi)', 'en': 'Audio (seconds)'},
    'lim.kind.requests': {'it': 'Richieste', 'en': 'Requests'},
    'lim.kind.tokens':  {'it': 'Token', 'en': 'Tokens'},
    'lim.used':         {'it': 'Crediti utilizzati: {v}', 'en': 'Credits used: {v}'},
    'lim.left':         {'it': 'Crediti rimanenti: {v}', 'en': 'Credits remaining: {v}'},
    'lim.reset':        {'it': 'Ripristino crediti: {v}', 'en': 'Credits reset: {v}'},
    'lim.remaining':    {'it': '{rem} / {lim} rimasti', 'en': '{rem} / {lim} left'},
    'lim.remaining_only': {'it': '{rem} rimasti', 'en': '{rem} left'},
    'lim.unused':       {'it': 'Non ancora utilizzato in questa sessione: nessun credito '
                               'consumato.',
                         'en': 'Not used yet this session: no credits spent.'},
    'lim.none':         {'it': 'Nessun dato sui limiti restituito da Groq.',
                         'en': 'Groq returned no limit data.'},
    'lim.reset.at':     {'it': '{orologio} (tra {durata})', 'en': '{orologio} (in {durata})'},
    'lim.reset.in':     {'it': 'tra {durata}', 'en': 'in {durata}'},
    'lim.reset.today':  {'it': 'alle {hm}', 'en': 'at {hm}'},
    'lim.reset.tomorrow': {'it': 'domani alle {hm}', 'en': 'tomorrow at {hm}'},
    'lim.reset.date':   {'it': 'il {dm} alle {hm}', 'en': 'on {dm} at {hm}'},

    # ── Errori ───────────────────────────────────────────────────────────────
    'err.title':        {'it': 'Errore', 'en': 'Error'},
    'err.unknown':      {'it': 'Errore sconosciuto.', 'en': 'Unknown error.'},
    'err.no_url':       {'it': 'Incolla prima il link del video.',
                         'en': 'Paste the video link first.'},
    'err.no_file':      {'it': 'Scegli prima un file audio.',
                         'en': 'Choose an audio file first.'},
    'err.unexpected':   {'it': 'Errore imprevisto: {e}', 'en': 'Unexpected error: {e}'},
}
