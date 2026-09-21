"""Il programma vero: tutto quello che lavora mentre la finestra sta a guardare.

Come e' diviso, e perche' proprio cosi'
    La pagina dentro la finestra (``client/``) non fa niente di sostanziale:
    mostra, raccoglie quello che si clicca, e aspetta. Il lavoro e' qui dentro,
    e qui dentro e' diviso per MESTIERE, non per ordine di esecuzione:

    ``config/``
        Le manopole e i punti fermi: dove stanno le cartelle, in che lingua si
        parla, quali frasi si mostrano, quali modelli si usano. Non fa niente,
        risponde soltanto.

    ``sources/``
        Da dove arriva l'audio: un link di YouTube, oppure un file che sta gia'
        sul disco. Si occupa di procurarselo, non di capirlo.

    ``transcription/``
        Il mestiere centrale: l'audio diventa parole. Due motori diversi, uno
        che manda tutto a Groq e uno che macina sul computer di chi lo usa.

    ``enrichment/``
        Cosa si fa alle parole una volta che ci sono: riassumerle, tradurle,
        metterci accanto quello che nel video si VEDE e non si sente.

    ``export/``
        Come esce dalla porta: il documento, i due tipi di PDF.

    ``state/``
        Cio' che deve sopravvivere a una chiusura: i parziali di un video
        lungo, quanto si e' gia' consumato di Groq oggi.

    ``services/``
        Il direttore d'orchestra, che chiama gli altri nell'ordine giusto e
        non sa fare niente per conto suo.

    ``controllers/``
        Il ponte verso la pagina: riceve una richiesta, chiama chi la sa
        eseguire, restituisce la risposta.

La direzione delle dipendenze
    Va sempre verso il basso di quell'elenco. ``controllers`` puo' chiamare
    ``services``, ``services`` puo' chiamare tutti gli altri, e ``config`` non
    chiama nessuno. Al contrario mai: il giorno in cui ``transcription``
    importasse ``services`` si chiuderebbe un cerchio, e Python a quel punto si
    ferma con un errore che non indica il file colpevole ma quello sfortunato.
"""
