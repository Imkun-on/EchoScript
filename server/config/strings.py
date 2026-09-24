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
    'menu.storico':     'Storico',

    'sez.locale.title': 'Trascrivi sul tuo computer',
    'sez.locale.desc':  "Quello che parte da qui gira su questa macchina, con i modelli "
                        "scelti qui sotto: niente rete, niente chiave, niente crediti. "
                        "L'audio non esce di casa.",
    'sez.storico.title': 'Storico dei lavori',
    'sez.storico.desc': "Tutto quello che è stato trascritto: con quale motore, quando, "
                        "quanto è costato e se è finito. Una riga per video e per "
                        "sezione; riprendere un lavoro aggiorna la sua riga.",
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

    # ── Stato della postazione ───────────────────────────────────────────────
    #
    # Qui sopra c'erano anche i testi del diario, il riquadro con le righe di
    # servizio accanto alla sorgente. Il riquadro non c'e' piu' e i suoi testi
    # sono usciti con lui; la spia e la parola di stato restano, e si sono
    # spostate nell'intestazione della sorgente.
    'status.idle':      'In attesa',
    'status.working':   'In corso',
    'status.done':      'Fatto',
    'status.error':     'Errore',

    'comune.chiudi':    'Chiudi',
    'comune.annulla':   'Annulla',
    'comune.conferma':  'Conferma',
    'comune.e':         ' e ',
    'err.busy':         "C'è già qualcosa in corso.",
    'trascina':         'Lascia qui il link o il file',

    # ── Sezione «Trascrivi»: sorgente ────────────────────────────────────────
    'src.label':        'Cosa trascrivo',
    'src.youtube':      'Un video YouTube',
    'src.local':        'Un file sul computer',
    'src.input.url':    'Link del video o della playlist',
    'src.input.file':   'File audio o video',
    # Il link si legge da solo mentre lo si incolla: niente bottone, solo una
    # riga sotto la casella che dice che cosa sta succedendo.
    'src.load.hint':    "Incolla il link: l'anteprima si apre da sola in una finestra.",
    'src.load.loading': 'Leggo il link…',
    'src.load.playlist': 'Leggo i video della playlist…',
    'src.panel':        'Sorgente',
    'src.empty':        "Incolla un link (l'anteprima si apre da sola) oppure scegli un file.",
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
    'opt.charts':       'Grafici nel riassunto',
    'opt.charts.desc':  'Quando il video dà numeri confrontabili (statistiche, '
                        'percentuali, andamenti, valori di una funzione) il riassunto '
                        'aggiunge un grafico, disegnato nel PDF. Mai con dati inventati.',
    'opt.comments':     'Commenti nei blocchi di codice',
    'opt.comments.desc': 'Il codice riportato nel riassunto arriva con brevi commenti '
                         'sulle righe che non si spiegano da sole. Il codice non cambia.',
    # Le due aggiunte valgono solo per il riassunto: spento quello, restano
    # grigie, e questa riga dice perche'.
    'opt.needsummary':  'Serve «Crea riassunto»',
    'opt.detail':       'Quanto dettagliato',
    'opt.detail.esteso': 'Esteso · ricco e completo (come sempre)',
    'opt.detail.normale': 'Normale · circa un terzo del parlato',
    'opt.detail.breve': 'Breve · solo i concetti principali',
    'opt.detail.punti': 'Punti chiave · un elenco per il ripasso',

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
    # Quando c'e' gia' una sorgente, o un lavoro in corso, l'anteprima chiede
    # dove mettere il video nuovo.
    'confirm.question.more': 'C\'è già «{titolo}». Lo sostituisco con questo, o lo '
                             'metto in coda e lo trascrivo dopo?',
    'confirm.question.busy': 'Questa sezione sta già lavorando: lo metto in coda, e '
                             'parte appena ha finito.',
    'confirm.replace':  'Sostituisci',
    'confirm.queue':    'Aggiungi alla coda',
    'confirm.queued':   '✓ In coda: {titolo} · {n} in attesa',

    # ── La coda ──────────────────────────────────────────────────────────────
    'coda.title':       'In coda',
    'coda.group':       '{n} video in fila',
    'coda.group.question': 'Li trascrivo uno dopo l\'altro, in quest\'ordine?',
    'coda.remove':      'Togli dalla coda',
    'coda.res.title':   'Coda completata',
    'coda.card':        '{n} in coda',

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
    # Le targhette accanto alle due voci nella barra laterale.
    #
    # Prima dicevano quale motore fosse scelto, e con un motore solo alla volta
    # aveva senso. Adesso i motori lavorano tutti e due, quindi la domanda
    # utile e' diventata un'altra: cosa sta succedendo di la'. E' proprio
    # l'informazione che si vuole mentre si lavora in parallelo, e la si vuole
    # senza dover cambiare stanza per averla.
    'posti.lavoro':     'IN CORSO',
    'posti.pronto':     'PRONTO',
    'posti.errore':     'ERRORE',
    'posti.attesa':     'DA VEDERE',
    # L'avviso che compare quando una stanza ha finito mentre si stava
    # guardando l'altra. Dice che c'e' qualcosa e dove, e non lo mostra:
    # interrompere chi sta preparando un altro lavoro sarebbe il contrario di
    # lavorare in parallelo.
    'posti.altrove':    'C\'è qualcosa da vedere in «{stanza}»',

    'eng.local.hint':   'Tutto quello che serve gira qui, senza rete e senza chiave: '
                        'trascrizione (Whisper), riassunto e traduzione (Ollama). '
                        '✓ = già scaricato in Ollama.',
    'eng.model.whisper': 'Trascrizione (Whisper)',
    'eng.model.ollama':  'Riassunto e traduzione (Ollama)',

    'eng.groq.hint':    'Gli stessi due mestieri, ma in nuvola e a carico della '
                        'chiave: trascrizione, riassunto e traduzione. Niente di '
                        'tutto questo tocca il tuo computer.',
    'eng.model.groq':   'Trascrizione (Whisper su Groq)',
    'eng.model.groqtesto': 'Riassunto e traduzione (Groq)',
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

    # Modelli Groq di testo (riassunto e traduzione), per numero di catalogo,
    # come per Ollama: cosi' aggiungerne uno resta una riga nelle impostazioni
    # e una qui.
    'gm.text.1':        'qualità piena, consigliato',
    'gm.text.2':        'più economico e rapido',

    # Descrizioni dei modelli Ollama, per numero di catalogo.
    'om.text.1':        'leggero e moderno · ideale con 8 GB di RAM',
    'om.text.2':        'equilibrio qualità/peso (default)',
    'om.text.3':        'più accurato · 12-16 GB di RAM',
    'om.text.4':        'ottimo multilingua · 16 GB di RAM',
    'om.text.5':        'qualità vicina al cloud · 24 GB+ o GPU',

    # ── Stima prima di partire ───────────────────────────────────────────────
    'est.cost':         'Costo stimato ~${c} · Groq {m}',
    'est.time':         'Tempo stimato ~{t} su {d} · offline',

    # ── Cosa manca per partire ───────────────────────────────────────────────
    'warn.title':       'Manca qualcosa',
    'warn.prefix':      'Per avviare la trascrizione serve:',
    'warn.key':         'caricare la chiave API Groq (riquadro «Chiave API»)',
    'warn.src.yt':      'incollare il link del video YouTube e confermarlo',
    'warn.src.local':   'scegliere un file audio',
    # Ollama si controlla prima di partire: il riassunto viene dopo la
    # trascrizione, e scoprire a meta' che era spento vuol dire aver aspettato
    # per niente.
    'warn.ollama.off':  'avviare Ollama: non risponde su {host}. Aprilo dal menu Start '
                        '(o lancia «ollama serve»), oppure spegni «Traduci» e «Crea riassunto»',
    'warn.ollama.model': 'scaricare il modello {m}: lancia «ollama pull {m}» in un terminale',

    # ── I crediti prima di partire ──────────────────────────────────────────
    'credest.title':    'I crediti potrebbero non bastare',
    'credest.desc':     'Oggi a Groq restano {restano} di audio, e da trascrivere ce '
                        'n\'è {serve}.',
    'credest.when':     'I crediti si ricaricano alle {ora}.',
    'credest.go':       'Parti lo stesso',
    'credest.go.desc':  'La trascrizione si fermerà dopo circa {restano} e verrà '
                        'salvata: la riprendi più tardi o la finisci in locale.',

    # ── Avanzamento ──────────────────────────────────────────────────────────
    'prog.title':       'Cosa sta facendo',
    'prog.steps':       'Passaggi',
    'prog.plan':        'Piano:',
    'prog.phase':       'Fase {i}/{n}',
    # Il tempo che manca alla fine della fase, stimato da quanto ci ha messo
    # finora. Compare solo quando la stima ha senso.
    'prog.eta.min':     'circa {n} min',
    'prog.eta.sec':     'meno di un minuto',
    'prog.cancel':      'Annulla',
    'prog.cancelling':  'Mi fermo al prossimo punto sicuro…',
    # Una fase che non sa quanto le manca (carica un modello, legge le
    # informazioni): al posto del numero, questo.
    'prog.working':     'in corso',
    'phase.default':    'In corso…',
    'phase.info':       'Lettura informazioni',
    'phase.download':   'Download audio',
    'phase.prepare':    'Preparazione audio',
    'phase.transcribe': 'Trascrizione',
    'phase.translate':  'Traduzione in italiano',
    'phase.summarize':  'Riassunto',
    'phase.export':     'Esportazione / salvataggio',

    'engine.groq':      'Groq (cloud) · {model}',
    'engine.local':     'Locale · faster-whisper {model}',
    'engine.local.hint': 'La trascrizione locale gira sulla CPU: può richiedere '
                         'diversi minuti.',

    'ov.base':          "trascrivo l'audio",
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
    'rate.msg':         'I crediti gratuiti Groq sono terminati.\n\n'
                        'La trascrizione si è fermata a {fatto} su {totale} ed è '
                        'stata salvata automaticamente.\n\n'
                        'Quando i crediti torneranno disponibili ({quando}) '
                        'riapri questo video e scegli «Riprendi». In alternativa puoi '
                        'completarlo subito sul tuo computer.',
    'rate.when.at':     'alle {ora}',
    'rate.when.tomorrow': 'di norma domani',
    # I crediti risultavano gia' finiti prima di cominciare: il lavoro non
    # parte nemmeno, invece di partire e restare fermo ad aspettare.
    'rate.before':      'I crediti Groq risultano già esauriti: tornano alle {ora}.\n\n'
                        'Il lavoro non è partito, così non resta fermo ad aspettare. '
                        'Riprova a quell\'ora, oppure trascrivi dalla sezione «Locale», '
                        'che non usa crediti.',
    'rate.later':       'Riprendo domani',
    'rate.ok':          'Ho capito',
    'rate.local':       'Continua ora in locale',

    'cancel.title':     'Lavoro annullato',
    'cancel.msg':       'Il lavoro si è fermato e quello che era già fatto è salvato.\n\n'
                        'Riaprendo lo stesso video trovi «Riprendi», che riparte da '
                        'dove ti eri fermato invece che da capo.',
    'cancel.batch':     'Annullato: i video già finiti sono salvati, quello in corso '
                        'si può riprendere.',

    # Le notifiche di Windows a fine lavoro, quando si stava guardando altro.
    'notify.done.title': 'EchoScript: lavoro completato',
    'notify.batch.title': 'EchoScript: coda completata',
    'notify.error.title': 'EchoScript: il lavoro si è fermato',

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
    'res.read':         'Leggi',
    'read.riassunto':   'il riassunto',
    'read.traduzione':  'la traduzione',
    'read.trascrizione': 'la trascrizione',

    # ── Storico ─────────────────────────────────────────────────────────────
    'hist.search':      'Cerca per titolo, canale o playlist…',
    'hist.count':       '{n} lavori',
    'hist.empty':       'Ancora niente: i lavori compariranno qui man mano che li fai.',
    'hist.col.url':     'URL',
    'hist.col.channel': 'Canale',
    'hist.col.title':   'Video',
    'hist.col.duration': 'Durata',
    'hist.col.credits': 'Crediti usati',
    'hist.col.kind':    'Tipo',
    'hist.col.state':   'Stato',
    'hist.col.mode':    'Modo',
    'hist.col.date':    'Data',
    'hist.single':      'Video singolo',
    'hist.playlist':    'Playlist',
    'hist.file':        'Audio registrato',
    'hist.done':        'Completo',
    'hist.half':        'A metà',
    'hist.min':         '{n} min',
    'hist.lessmin':     '< 1 min',
    'hist.free':        '0 · gratis',
    'hist.audio':       '{n} s audio',
    'hist.tokens':      '{n} token',
    'hist.read':        'Leggi',
    'hist.folder':      'Cartella',
    'hist.remove':      'Togli dallo storico',
    'hist.refresh':     'Aggiorna',
    'hist.gone':        'Questa riga non c\'è più nello storico.',
    'hist.nodoc':       'Il documento non si trova più: forse la cartella è stata '
                        'spostata o cancellata.',

    # ── Crediti (sezione dedicata) ───────────────────────────────────────────

    # ── Errori ───────────────────────────────────────────────────────────────
    'err.title':        'Errore',
    'err.unknown':      'Errore sconosciuto.',
    'err.no_url':       'Incolla prima il link del video.',
    'src.pasted':       'Link incollato in «{stanza}»: apro l\'anteprima…',
    'err.no_file':      'Scegli prima un file audio.',
    'err.unexpected':   'Errore imprevisto: {e}',

    # Il video su cui il lavoro si e' fermato, e l'etichetta del testo tecnico.
    'err.video':        'Video:',
    'err.dettaglio':    'Dettaglio tecnico',
    # Quando a fermarsi e' la lettura del link, prima ancora di cominciare.
    'err.src.title':    'Non riesco a leggere il link',
    'err.link':         'Link:',

    # ── Di cosa si tratta ────────────────────────────────────────────────────
    #
    # Una frase per ogni famiglia riconosciuta da `classifica_errore`. La chiave
    # e' 'err.causa.' piu' il nome della famiglia, quindi aggiungere una
    # famiglia la' dentro vuol dire aggiungere una riga qui, e nient'altro.
    #
    # Ognuna dice due cose: che cosa e' successo, e se ci sia qualcosa da fare.
    # La seconda parte e' quella che serve davvero: sapere che un video non e'
    # scaricabile senza sapere se valga la pena riprovare lascia fermi.
    'err.causa.rifiutato':
        'YouTube ha rifiutato il download di questo video. Di solito vuol dire '
        'che il link al file audio è scaduto, oppure che yt-dlp è indietro '
        'rispetto a un cambiamento di YouTube. Riprova, e se continua aggiorna '
        'yt-dlp con «pip install -U yt-dlp».',
    'err.causa.nonDisponibile':
        'Questo video non è scaricabile: può essere privato, riservato agli '
        'iscritti, rimosso, con limite di età oppure non disponibile in Italia. '
        'Non c\'è niente da riprovare: è una scelta di chi lo ha pubblicato.',
    'err.causa.rete':
        'La connessione non ha risposto in tempo. Controlla di essere online e '
        'riprova: se la rete era solo lenta, al secondo tentativo funziona.',
    'err.causa.crediti':
        'I crediti del servizio sono esauriti. Quello che era già stato fatto '
        'è salvato: si riprende quando tornano disponibili, oppure si finisce '
        'sul proprio computer.',
    'err.causa.chiave':
        'La chiave Groq non è stata accettata. Controllala nelle impostazioni: '
        'se è stata rigenerata sul sito, quella vecchia non vale più.',
    'err.causa.ffmpeg':
        'ffmpeg non ha funzionato. È il programma che estrae e converte '
        'l\'audio, e senza di lui non si va avanti: va installato, o rimesso fra '
        'i programmi che il sistema trova da solo.',
    'err.causa.disco':
        'Non è stato possibile scrivere il file. O lo spazio sul disco è '
        'finito, o la cartella di destinazione non è scrivibile. Se è dentro '
        'OneDrive può anche essere una sincronizzazione in corso: riprova fra '
        'un minuto.',
    'err.causa.modelloLocale':
        'Il modello sul tuo computer non è partito. Controlla che Ollama sia '
        'in esecuzione e che il modello scelto sia già stato scaricato.',
    'err.causa.programma':
        'È un difetto del programma, non un problema tuo: il link, la rete e '
        'le impostazioni non c\'entrano, e riprovare non lo risolve. Segnalalo '
        'copiando il dettaglio tecnico qui sotto, che dice esattamente dove si '
        'è rotto.',
    'err.causa.sconosciuto':
        'Il lavoro si è fermato per un motivo che il programma non sa '
        'riconoscere. Il testo qui sotto è quello originale dell\'errore.',
}
