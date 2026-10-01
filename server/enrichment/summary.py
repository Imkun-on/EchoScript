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

Le materie
    Oltre alle due aggiunte scelte dalla finestra ce ne sono altre che si
    scelgono da sole, pezzo per pezzo: le regole di una materia (matematica,
    statistica...) entrano solo nei pezzi di testo che ne parlano (vedi
    ``materie``). Sono lunghe, e un video di cucina non deve pagarne i token.

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
    "volta e poi richiamalo per nome senza ripeterlo;\n"
    "• NON inventare codice: scrivilo solo se nel video compare davvero (una "
    "lezione di programmazione, l'uso di un software, un comando). Un calcolo, "
    "un sistema di equazioni o un esercizio di matematica, fisica o chimica "
    "non si trasforma mai in codice, nemmeno per verificarlo: si svolge con "
    "le formule.\n"
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
    "```piano, ```spazio, ```molecola e ```mermaid, ma solo se le regole qui sotto li ammettono). NON usare il "
    "corsivo con asterischi singoli (*testo*), né tabelle, né note a piè di "
    "pagina, né link.\n"
    "Vincoli di output: rispondi esclusivamente con il riassunto, senza "
    "preamboli, intestazioni o commenti. Non aprire mai il testo con formule "
    "del tipo \"Ecco i punti chiave\", \"In questo video si parla di\" o simili: "
    "entra direttamente nel contenuto."
)

# Aggiunta per i GRAFICI. Due strumenti per due casi diversi. La matematica
# ha il suo piano cartesiano (```piano, disegnato da export/piano.py): un
# grafico a linee di Mermaid unisce i punti con segmenti dritti e non ha gli
# assi nell'origine, e una parabola fatta cosi' usciva come una «V». Mermaid
# resta per i dati veri, e solo nelle due forme che i modelli sbagliano meno.
# Tutto il resto (flowchart, mappe concettuali) viene tolto dopo, da
# _pulisci_diagrammi.
_REGOLA_PIANO = (
    "\nGrafici: ci sono due strumenti, per due casi diversi. Se nessuno dei due "
    "casi si presenta, nessun grafico.\n"
    "1) Piano cartesiano, per matematica, analisi e fisica: quando la sezione "
    "studia o disegna una funzione, una retta, una parabola, una "
    "circonferenza, un'ellisse, un'iperbole, oppure un esercizio chiede punti "
    "notevoli (vertice, fuoco, centro, intersezioni, tangenti, asintoti), "
    "aggiungi un piano cartesiano subito dopo lo svolgimento, in un blocco "
    "```piano scritto esattamente così:\n"
    "```piano\n"
    "titolo: Parabola e retta tangente nel punto T\n"
    "x: -1, 5\n"
    "y: -2, 6\n"
    "curva: y = x^2 - 4x + 3\n"
    "curva: y = 2x - 6\n"
    "punto: V (2, -1)\n"
    "punto: T (3, 0)\n"
    "```\n"
    "Regole del piano: ogni riga «curva:» è un'equazione in x e y, nella forma "
    "y = ..., x = ..., oppure implicita come (x - 1)^2 + (y - 2)^2 = 9 o "
    "x^2/4 + y^2/9 = 1; usa ^ per le potenze, sqrt(), sin(), cos(), exp(), "
    "log() e il punto come separatore decimale. Ogni riga «punto:» ha un nome "
    "facoltativo e le coordinate fra parentesi. «x:» e «y:» sono gli intervalli "
    "da mostrare: sceglili in modo che si vedano bene i punti importanti. "
    "Metti SOLO curve e punti dell'esercizio, con i valori del testo o "
    "calcolati esattamente da lui. Non scrivere altro nel blocco.\n"
)

# Le istruzioni AVANZATE del piano e dello spazio: definizioni, analisi,
# trigonometria, geometria, campi, successioni, 3D. Sono lunghe (piu' di
# diecimila caratteri, circa tremila token), e servono solo quando si parla di
# matematica: si aggiungono soltanto ai pezzi di testo che ne parlano (vedi
# materie), cosi' gli altri non pagano quei token a ogni richiesta.
_REGOLA_GRAFICI_AVANZATI = (
    "Per una DEFINIZIONE o un concetto spiegato con le lettere e non con i "
    "numeri (il luogo dei punti di una conica, il ruolo di un parametro, la "
    "retta tangente in generale), il piano si fa lo stesso: scegli tu dei "
    "valori semplici solo per disegnare, e nascondili con «numeri: no». Si "
    "vedono allora la forma, i nomi dei punti e delle rette e le relazioni. "
    "Esempio, la definizione di parabola:\n"
    "```piano\n"
    "titolo: La parabola come luogo dei punti\n"
    "numeri: no\n"
    "x: -3, 3\n"
    "y: -2, 4\n"
    "curva: y = x^2/4 | parabola\n"
    "curva d: y = -1 | direttrice\n"
    "punto: F (0, 1)\n"
    "punto: P (2, 1)\n"
    "punto: H (2, -1)\n"
    "segmento: P - F\n"
    "segmento: P - H\n"
    "nota: $\\overline{PF} = \\overline{PH}$ per ogni punto P della parabola\n"
    "```\n"
    "e il ruolo di un parametro, con una curva per ogni valore:\n"
    "```piano\n"
    "titolo: Come cambia la parabola al variare di a\n"
    "numeri: no\n"
    "x: -3, 3\n"
    "y: -3, 4\n"
    "curva: y = ax^2 per a = 0.25, 1, 3, -1 | $y = ax^2$\n"
    "```\n"
    "In breve: «curva d:» dà un nome alla curva, scritto accanto a lei; dopo "
    "«|» va quello che la legenda deve dire al posto dell'equazione; «per a = "
    "...» disegna una curva per ogni valore; «segmento: A - B» traccia un "
    "segmento tratteggiato fra due punti già nominati; «nota:» aggiunge una "
    "riga sotto il grafico, anche con formule fra $.\n"
    "Per l'analisi e le disequazioni ci sono anche:\n"
    "• funzioni a tratti: «curva: y = x + 1 se x < 0» e «curva: y = x^2 se "
    "0 <= x <= 2», una riga per tratto; gli estremi prendono da soli il "
    "pallino pieno (<=, incluso) o vuoto (<, escluso);\n"
    "• aree: «area: sotto y = x^2 da 0 a 2» colora fra la curva e l'asse x "
    "(l'integrale definito); «area: tra y = x e y = x^2 da 0 a 1» fra due "
    "curve; «area: x^2 + y^2 <= 4» o «area: x < -1 oppure x > 3» dove vale una "
    "disuguaglianza (soluzioni di una disequazione, dominio di una funzione "
    "di due variabili). Anche qui dopo «|» si può scrivere cosa dire in "
    "legenda, per esempio «| $\\int_0^2 x^2\\,dx = \\frac{8}{3}$». Disegna "
    "sempre anche la curva che fa da bordo all'area.\n"
    "Per trigonometria, curve speciali, vettori e numeri complessi ci sono:\n"
    "• curve parametriche: «curva: x = t - sin(t), y = 1 - cos(t) con t da 0 "
    "a 4*pi»; polari: «curva: r = 1 + cos(θ)» (θ da 0 a 2π se non si dice "
    "altro);\n"
    "• vettori, disegnati come frecce: «vettore v: (2, 1)» parte "
    "dall'origine, «vettore w: (1, 2) da P» parte da un punto, «vettore: A -> "
    "B» va da un punto all'altro;\n"
    "• angoli: «angolo α: da 0 a pi/3» o in gradi «angolo α: da 0° a 60°», con "
    "il vertice nell'origine o «in P»;\n"
    "• tacche a multipli di π: «tacche x: pi/2» scrive π/2, π, 3π/2 sull'asse, "
    "come si fa per le funzioni goniometriche;\n"
    "• nomi degli assi: «assi: Re, Im» per il piano di Gauss.\n"
    "Per la geometria dei triangoli e dei poligoni:\n"
    "• «poligono: A, B, C» colora la figura e ne disegna i lati (i vertici "
    "sono punti già scritti, o coordinate); «lato: A - B | c» è un lato pieno "
    "col suo nome a metà, «segmento: P - H | h» uno tratteggiato (altezze, "
    "proiezioni, distanze);\n"
    "• «angolo α: in A tra B e C» segna l'angolo nel vertice A fra i lati AB "
    "e AC; se è retto diventa da solo il quadratino.\n"
    "Per i campi (Analisi 2, fisica, equazioni differenziali):\n"
    "• «campo: (-y, x)» disegna un campo vettoriale come frecce su una "
    "griglia; «campo: gradiente di x^2 + y^2» il gradiente di una funzione; "
    "«linea: da (1, 0)» la linea di campo che passa da un punto;\n"
    "• «direzioni: y' = x - y» disegna il campo di direzioni di un'equazione "
    "differenziale del primo ordine; «soluzione: da (0, 1)» la soluzione che "
    "passa da quel punto (il problema di Cauchy), calcolata dal programma: "
    "metti più soluzioni per mostrare come cambiano col dato iniziale.\n"
    "Per successioni, serie e integrali:\n"
    "• «successione: a_n = 1/n per n da 1 a 20» disegna i termini come punti "
    "separati; «serie: a_n = 1/n^2 per n da 1 a 20» le somme parziali S_n; "
    "aggiungi «curva: y = L» per mostrare il limite;\n"
    "• «rettangoli: y = x^2 da 0 a 2 con n = 8 sinistra» disegna la somma di "
    "Riemann (sinistra, destra o medio) e ne scrive il valore: insieme alla "
    "curva e all'area mostra come i rettangoli si avvicinano all'integrale.\n"
    "Per lo SPAZIO a tre dimensioni (funzioni di due variabili, superfici, "
    "solidi, curve nello spazio, vettori in tre coordinate, figure della "
    "topologia come sfera, toro e nastro di Möbius) si usa un blocco "
    "```spazio, con le stesse regole del piano:\n"
    "```spazio\n"
    "titolo: Paraboloide e il suo vertice\n"
    "x: -2, 2\n"
    "y: -2, 2\n"
    "z: 0, 8\n"
    "superficie: z = x^2 + y^2\n"
    "punto: V (0, 0, 0)\n"
    "```\n"
    "Le righe dello spazio: «superficie: z = f(x, y)» per il grafico di una "
    "funzione di due variabili (si colora per altezza); «superficie: x = ..., "
    "y = ..., z = ... con u da 0 a 2*pi, v da 0 a pi» per una superficie "
    "parametrica, per esempio la sfera x = cos(u)*sin(v), y = sin(u)*sin(v), "
    "z = cos(v) o il toro x = (2 + cos(v))*cos(u), y = (2 + cos(v))*sin(u), "
    "z = sin(v); «superficie: x^2 + y^2 - z^2 = 1» per una superficie data da "
    "un'equazione in x, y e z (quadriche come ellissoidi, iperboloidi, coni, "
    "paraboloidi scritti in forma implicita), che si scrive così com'è; "
    "«curva: x = cos(t), y = sin(t), z = t con t da 0 a 4*pi» per "
    "una curva nello spazio; «punto: P (1, 2, 3)»; «vettore v: (1, 0, 2)», "
    "anche «da P» o «A -> B»; «segmento: A - B»; «vista: -60, 30» sceglie da "
    "dove si guarda (azimut ed elevazione in gradi: cambiala se da quella di "
    "partenza la figura si vede di taglio); «numeri: no», «nota:» e «|» come "
    "nel piano. Anche qui: uno spazio per ogni esercizio o definizione.\n"
)

# La statistica ha grafici suoi, che il piano disegna (vedi export/piano.py):
# istogramma, boxplot, dispersione. Le barre di Mermaid mettono le classi di
# un istogramma come voci staccate e non sanno che cosa sia una densita';
# restano per i dati qualitativi.
_GRAFICI_STATISTICA = (
    "Per la STATISTICA e la PROBABILITÀ il piano ha righe apposta. Si usano al "
    "posto delle barre di Mermaid quando i dati sono numeri su una scala "
    "(altezze, voti, tempi, redditi, punteggi); Mermaid resta per le modalità "
    "qualitative (colori, partiti, materie preferite) e per le serie nel tempo. "
    "Esempio, la distribuzione delle altezze di una classe:\n"
    "```piano\n"
    "titolo: Altezze degli studenti\n"
    "assi: altezza (cm), frequenza\n"
    "istogramma: [150, 160) 4; [160, 170) 9; [170, 180) 6; [180, 190) 1\n"
    "```\n"
    "Le righe della statistica:\n"
    "• «istogramma: [a, b) f; ...» una classe per pezzo, separati da «;», con "
    "la frequenza assoluta detta nel testo. Scrivi SEMPRE le frequenze e mai "
    "le densità: se le classi hanno ampiezze diverse il programma disegna da "
    "solo la densità (frequenza / ampiezza). Per una distribuzione discreta "
    "(un dado, una binomiale) usa classi larghe 1 attorno a ogni valore, "
    "[-0.5, 0.5) [0.5, 1.5) ..., con la probabilità al posto della frequenza;\n"
    "• «boxplot A: min, Q1, mediana, Q3, max» i cinque numeri in quest'ordine, "
    "più «con anomali 20, 25» per i valori anomali; per confrontare gruppi, "
    "un boxplot per riga, ognuno col suo nome;\n"
    "• «dati: (1, 2), (2, 3.5), (4, 4)» la nuvola di punti di una dispersione, "
    "con TUTTE le coppie del testo; la retta di regressione, se il testo la "
    "calcola, si aggiunge come «curva: y = 0.8x + 1.2 | retta di regressione»;\n"
    "• per una distribuzione continua la densità è una curva, per la normale "
    "«curva: y = exp(-(x - 170)^2/(2*8^2))/(8*sqrt(2*pi))» con i valori veri "
    "di μ e σ, e una probabilità è un'area sotto la curva: «area: sotto y = ... "
    "da 162 a 178 | $P(162 \\le X \\le 178) \\approx 0.68$»;\n"
    "• «assi: nome x, nome y» dà il nome agli assi (la grandezza con la sua "
    "unità, e «frequenza» o «densità»). Con istogramma, boxplot e dati puoi "
    "omettere «x:» e «y:», perché il programma li sceglie attorno ai dati; "
    "per una curva da sola scrivili.\n"
)

# Le regole di contenuto della statistica, che valgono anche senza grafici.
_REGOLA_STATISTICA = (
    "\nStatistica e probabilità:\n"
    "• quando il testo calcola un indice (media, mediana, moda, varianza, "
    "deviazione standard, quartili, coefficiente di variazione, covarianza, "
    "correlazione), scrivi prima la formula in `$$`, poi la stessa formula "
    "con i numeri sostituiti, poi il risultato con la sua unità di misura (la "
    "varianza ha l'unità al quadrato);\n"
    "• popolazione e campione restano come li tratta il testo: $\\mu$, "
    "$\\sigma^2$ e $N$ per la popolazione, $\\bar{x}$, $s^2$ e $n - 1$ per il "
    "campione. Non cambiare il divisore rispetto a quello usato nel testo;\n"
    "• i dati di partenza (una serie di valori, una tabella di frequenze) si "
    "riportano tutti. Una tabella diventa un elenco puntato, una voce per "
    "classe o modalità: «- **[160, 170)**: 9 studenti, frequenza relativa "
    "0.45»;\n"
    "• i simboli detti a voce («x segnato», «sigma quadro», «mu», «p di A dato "
    "B») diventano i loro simboli: $\\bar{x}$, $\\sigma^2$, $\\mu$, "
    "$P(A \\mid B)$;\n"
    "• nella probabilità scrivi l'evento a parole e in simboli ($P(A \\cap B)$, "
    "$P(A \\cup B)$, $P(\\bar{A})$) e il risultato come frazione, e anche in "
    "decimali o percentuale se il testo lo fa; nel calcolo combinatorio di' "
    "quale schema si usa (permutazioni, disposizioni, combinazioni, con o "
    "senza ripetizione) e perché;\n"
    "• in un test d'ipotesi o in un intervallo di confidenza i passi restano "
    "separati: ipotesi $H_0$ e $H_1$, livello di significatività, statistica "
    "test, valore critico o p-value, conclusione detta a parole;\n"
    "• tieni gli arrotondamenti del testo, senza aggiungere né togliere cifre.\n"
)

# Barre, linee e torta, e le regole che valgono per tutti i grafici.
_REGOLA_GRAFICI_DATI = (
    "2) Barre, linee o torta, soltanto per DATI veri: una statistica, "
    "percentuali che compongono un totale, quantità misurate da confrontare, "
    "una serie che cambia nel tempo. MAI per una funzione o una figura "
    "geometrica (per quelle c'è il piano), e MAI per mettere a confronto i "
    "risultati di esercizi diversi (i raggi di tre esempi, le soluzioni di tre "
    "equazioni): quei numeri restano nel testo. Usa SOLO numeri detti "
    "esplicitamente nel testo: se i dati mancano o sono vaghi, il grafico NON "
    "si fa. Sono ammesse soltanto queste due forme, scritte esattamente così:\n"
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
    "UN PIANO PER OGNI ESERCIZIO O DEFINIZIONE: in un piano vanno soltanto le "
    "curve e i punti di quell'esercizio (la parabola e la SUA tangente, la "
    "circonferenza e il SUO centro) o di quella definizione. Esercizi diversi, "
    "anche nella stessa sezione, hanno ognuno il proprio piano, subito dopo il "
    "proprio svolgimento: mai curve di esercizi diversi sovrapposte nello "
    "stesso piano. L'unica eccezione è una famiglia con «per a = ...», che "
    "mostra un solo concetto. Per barre, linee e torta: al massimo uno per "
    "sezione.\n"
    "Nessun altro tipo di diagramma: niente "
    "flowchart, niente mappe concettuali. Il grafico accompagna la spiegazione "
    "e non la sostituisce: i risultati importanti restano scritti anche nel testo."
)

# Le regole di contenuto della chimica. Le formule e le reazioni si scrivono
# con \ce{...} (l'estensione mhchem di MathJax): H2O con i pedici giusti, le
# frecce di reazione e di equilibrio, le cariche, gli stati di aggregazione.
_REGOLA_CHIMICA = (
    "\nChimica:\n"
    "• ogni formula chimica e ogni reazione si scrivono con \\ce{...} dentro "
    "le formule: $\\ce{H2O}$ nella frase, e su riga propria $$\\ce{2H2 + O2 -> "
    "2H2O}$$. Dentro \\ce i numeri dopo un elemento diventano pedici da soli "
    "(H2SO4), le cariche si scrivono con ^ ($\\ce{SO4^2-}$, $\\ce{Na+}$), lo "
    "stato fra parentesi ($\\ce{NaCl(aq)}$, $\\ce{H2O(l)}$), la freccia "
    "semplice è ->, l'equilibrio <=>, un gas che si libera ^ e un precipitato v;\n"
    "• una reazione si scrive sempre bilanciata, con i coefficienti che dice il "
    "testo; se il testo la bilancia passo passo, i passi restano;\n"
    "• il nome di un composto resta quello del testo (IUPAC o tradizionale); "
    "se il testo li dice tutti e due, li riporti tutti e due;\n"
    "• nei calcoli (moli, masse, concentrazioni, pH, costanti di equilibrio) "
    "vale la stessa regola degli esercizi: dati, formula, sostituzione dei "
    "numeri, risultato con la sua unità di misura ($\\mathrm{mol/L}$, "
    "$\\mathrm{g/mol}$);\n"
    "• i simboli detti a voce («acca due o», «esse o quattro due meno») "
    "diventano la loro formula: $\\ce{H2O}$, $\\ce{SO4^2-}$.\n"
)

# Il disegno delle molecole: il blocco ```molecola, disegnato da
# export/molecola.py con RDKit. Il modello scrive la struttura in SMILES;
# la formula accanto fa da controllo, perche' lo SMILES e' la cosa che un
# modello sbaglia piu' facilmente, e se i due non tornano il blocco si toglie.
_GRAFICI_CHIMICA = (
    "Per la CHIMICA c'è il disegno delle molecole: quando la sezione parla di "
    "una molecola precisa (la sua struttura, la sua forma, i suoi legami, un "
    "composto organico e il suo nome), aggiungi subito dopo la spiegazione un "
    "blocco ```molecola scritto esattamente così:\n"
    "```molecola\n"
    "nome: acido acetilsalicilico\n"
    "iupac: 2-acetyloxybenzoic acid\n"
    "formula: C9H8O4\n"
    "smiles: CC(=O)Oc1ccccc1C(=O)O\n"
    "```\n"
    "Le righe della molecola: «nome:» come lo dice il testo; «iupac:» il nome "
    "IUPAC sistematico IN INGLESE (per esempio ethanol, propan-2-one, "
    "2-methylpropane, (2R)-butan-2-ol, sodium chloride), anche quando il testo "
    "usa un nome comune o italiano: serve a controllare la struttura; «formula:» la "
    "formula molecolare, con tutti gli atomi, idrogeni compresi, e la carica "
    "con ^ per gli ioni (NH4^+); «smiles:» la struttura in SMILES, che deve "
    "descrivere ESATTAMENTE la molecola della formula: gli anelli aromatici in "
    "minuscolo (c1ccccc1), la stereochimica con @ e @@ e con / e \\ solo se il "
    "testo ne parla; facoltativa «nota:» per una riga sotto il disegno (per "
    "esempio l'angolo di legame detto nel testo). Il programma sceglie da solo "
    "il disegno: il modello 3D a sfere e bastoncini per le molecole piccole "
    "(H2O, NH3, CH4, CO2, H2SO4), la formula a scheletro dei libri di organica "
    "per i composti del carbonio; «vista: 3d», «vista: scheletro» o «vista: "
    "entrambe» lo cambiano (entrambe per la forma di un composto organico, per "
    "esempio la sedia del cicloesano); «vista: lewis» disegna la struttura di "
    "Lewis (tutti gli atomi, i legami come trattini, le coppie di elettroni "
    "non condivise come puntini, le cariche formali): usala quando il testo "
    "parla di struttura di Lewis, coppie solitarie, ottetto o cariche formali. "
    "I puntini li mette il programma: tu scrivi solo lo SMILES, con le cariche "
    "formali se ci sono (lo ione nitrato è [O-][N+](=O)[O-]). Una molecola per "
    "blocco, soltanto molecole nominate nel testo, al massimo quattro per "
    "sezione. Se non sei sicuro della struttura, niente blocco.\n"
)

# Le reazioni disegnate: il blocco ```reazione, disegnato da export/reazione.py
# sempre con RDKit. Il bilanciamento e' il controllo: atomi e cariche devono
# tornare fra reagenti e prodotti, o il blocco si toglie.
_GRAFICI_REAZIONE = (
    "Per una reazione fra molecole che vale la pena di VEDERE (chimica "
    "organica, un meccanismo) c'è il blocco ```reazione:\n"
    "```reazione\n"
    "titolo: Esterificazione di Fischer\n"
    "reagenti: CC(=O)O | acido acetico; CCO | etanolo\n"
    "prodotti: CC(=O)OCC | acetato di etile; O | acqua\n"
    "sopra: H2SO4\n"
    "sotto: calore\n"
    "tipo: equilibrio\n"
    "```\n"
    "Le molecole in SMILES, separate da «;»; dopo «|» il nome; un numero "
    "davanti è il coefficiente («2 O=O»). La reazione dev'essere BILANCIATA e "
    "con TUTTI i prodotti (anche l'acqua, l'HBr, lo ione che se ne va): se "
    "atomi o cariche non tornano fra le due parti, il disegno non si fa. "
    "«sopra:» e «sotto:» sono le scritte sulla freccia (catalizzatore, "
    "solvente, calore); «tipo: equilibrio» mette la doppia freccia. Per un "
    "passo di MECCANISMO numera dentro lo SMILES gli atomi coinvolti e "
    "aggiungi «frecce:»:\n"
    "```reazione\n"
    "titolo: Sostituzione nucleofila SN2\n"
    "reagenti: [OH-:1]; [CH3:2][Br:3]\n"
    "prodotti: CO | metanolo; [Br-] | ione bromuro\n"
    "frecce: 1 -> 2; 2-3 -> 3\n"
    "```\n"
    "«1 -> 2» va dall'atomo 1 all'atomo 2 (una coppia di elettroni che "
    "attacca); «2-3 -> 3» dal legame fra 2 e 3 all'atomo 3 (il legame si rompe "
    "e gli elettroni restano su 3); «1-2 -> 2-5» da un legame al punto fra due "
    "atomi dove ne nasce uno nuovo. Un blocco per ogni passo, soltanto i passi "
    "che il testo descrive, al massimo quattro per sezione. Le reazioni "
    "inorganiche semplici restano scritte con \\ce, senza blocco.\n"
)

# Gli altri disegni della chimica (export/chimica.py): qui il modello scrive
# solo i dati del testo, e i conti li fa il programma. Non hanno bisogno di
# RDKit, quindi si chiedono anche quando le molecole non si possono disegnare.
_GRAFICI_CHIMICA_CALCOLATI = (
    "Altri disegni della chimica, ognuno soltanto quando la sezione parla "
    "proprio di quello. Tu scrivi i dati del testo; i conti e il disegno li fa "
    "il programma, quindi non calcolare e non inventare niente:\n"
    "• configurazione elettronica a caselle e frecce: ```orbitali con «elemento: "
    "Fe» (o uno ione: «elemento: Fe^3+»). «configurazione: 1s2 2s1 2p3» si "
    "aggiunge solo se il testo ne scrive una diversa dallo stato fondamentale "
    "(uno stato eccitato). Per la FORMA degli orbitali: «forme: s, p, d», "
    "oppure i singoli («px, dz2») o gli ibridi («sp, sp2, sp3»);\n"
    "• curva di titolazione: ```titolazione con «analita: acido debole, 0,1 M, "
    "25 mL, Ka = 1,8e-5 | acido acetico» e «titolante: base forte, 0,1 M | "
    "NaOH» (acido o base, forte o debole; per i deboli la Ka o la Kb, oppure "
    "pKa o pKb); facoltativo «indicatore: fenolftaleina, 8,2 - 10». Solo con "
    "le concentrazioni e il volume detti nel testo;\n"
    "• profilo di energia della reazione: ```energia con «livelli: reagenti 0; "
    "stato di transizione 85; prodotti -40» (i valori del testo, e «unita: "
    "kJ/mol»; a più stadi «reagenti 0; TS1 60; intermedio 20; TS2 45; prodotti "
    "-30») e, se il testo ne parla, «catalizzatore: 50». Se il testo non dà "
    "numeri scrivi soltanto «tipo: esotermica» o «tipo: endotermica» (e "
    "«catalizzatore: sì»);\n"
    "• reticolo cristallino: ```reticolo con «tipo:» uno fra cubico semplice, "
    "cubico a corpo centrato, cubico a facce centrate, cloruro di sodio, "
    "cloruro di cesio, diamante; facoltativo «atomi: Fe» (per i due ionici "
    "«atomi: Na, Cl», prima il catione);\n"
    "• tavola periodica: ```tavola con una o più righe fra «evidenzia: Na, "
    "Cl», «gruppo: 17», «periodo: 3», «blocco: d», «tendenza: "
    "elettronegatività» (oppure energia di ionizzazione, affinità elettronica, "
    "raggio atomico, carattere metallico) e «colora: blocchi» o «colora: "
    "famiglie».\n"
    "In tutti sono facoltativi «titolo:» e «nota:». Esempio:\n"
    "```titolazione\n"
    "titolo: Titolazione dell'acido acetico con NaOH\n"
    "analita: acido debole, 0,1 M, 25 mL, Ka = 1,8e-5 | acido acetico\n"
    "titolante: base forte, 0,1 M | NaOH\n"
    "indicatore: fenolftaleina, 8,2 - 10\n"
    "```\n"
)

# Le regole di contenuto della fisica: l'esercizio svolto come si fa a
# scuola, e le unita' di misura sempre attaccate ai numeri.
_REGOLA_FISICA = (
    "\nFisica:\n"
    "• un esercizio si svolge in passi separati: i dati, come elenco puntato "
    "con simbolo, valore e unità di misura («- **massa**: $m = 2\\,\\mathrm{kg}$»), "
    "l'incognita, la legge o formula usata detta per nome (secondo principio "
    "della dinamica, conservazione dell'energia, legge di Ohm), la formula "
    "girata per ricavare l'incognita se serve, la sostituzione dei numeri, il "
    "risultato;\n"
    "• ogni valore ha la sua unità di misura, scritta in formula con "
    "\\mathrm e uno spazio sottile: $v = 12\\,\\mathrm{m/s}$, "
    "$g = 9{,}81\\,\\mathrm{m/s^2}$, $F = 5\\,\\mathrm{N}$. Le conversioni di "
    "unità che il testo fa (km/h in m/s, g in kg) restano come passaggio;\n"
    "• numeri molto grandi o piccoli in notazione scientifica, "
    "$3{,}0 \\times 10^{8}\\,\\mathrm{m/s}$; tieni le cifre e gli arrotondamenti "
    "del testo, e le costanti con il valore che usa il testo;\n"
    "• i vettori si scrivono $\\vec F$, il loro modulo $F$ o $|\\vec F|$, le "
    "componenti $F_x$ e $F_y$; distingui sempre grandezze vettoriali e scalari "
    "come fa il testo;\n"
    "• le grandezze dette a voce («metri al secondo quadro», «delta t», «effe "
    "con vettore») diventano simboli e unità: $\\mathrm{m/s^2}$, $\\Delta t$, "
    "$\\vec F$.\n"
)

# I disegni della fisica: tutti col piano cartesiano (export/piano.py), che
# sa gia' fare curve, aree, vettori, poligoni, angoli e campi. Qui si dice
# come usarlo per i casi della fisica, e le righe si ripetono anche se sono
# gia' nelle istruzioni avanzate della matematica: un testo di fisica puo'
# non averle.
_GRAFICI_FISICA = (
    "Per la FISICA si usa lo stesso piano (```piano), in questi casi:\n"
    "• grafici del moto e delle grandezze nel tempo (s-t, v-t, a-t, "
    "l'energia, la carica di un condensatore): la variabile orizzontale si "
    "scrive SEMPRE x e quella verticale y anche se sono t e v, e «assi: t (s), "
    "v (m/s)» dà i nomi veri agli assi. In un grafico v-t lo spostamento è "
    "l'area sotto la curva: «area: sotto y = 2 + 2x da 0 a 5 | $\\Delta s = "
    "35\\,\\mathrm{m}$». Un moto a tratti si scrive un tratto per riga con "
    "«se»: «curva: y = 2x se 0 <= x <= 3»;\n"
    "• traiettorie (moto parabolico) e onde: la curva con «se» per fermarla "
    "dove il moto finisce, e i punti notevoli (gittata, altezza massima; "
    "creste, lunghezza d'onda con «segmento: P - Q | λ»);\n"
    "• forze su un corpo (diagramma di corpo libero), piano inclinato, "
    "ottica con i raggi: un disegno senza misure, con «numeri: no» e «assi: "
    "no». Il corpo è un poligono («poligono: (-1, -0.7), (1, -0.7), (1, 0.7), "
    "(-1, 0.7)»), il piano inclinato un triangolo con l'angolo («angolo α: in "
    "A tra B e C»), le forze sono vettori che partono dal punto di "
    "applicazione («punto: G (0, 0)» e «vettore P: (0, -2) da G»), lunghi in "
    "proporzione alla loro intensità quando il testo la dice; un raggio è un "
    "«vettore: A -> B». Per la somma delle forze aggiungi «nota: $\\vec N + "
    "\\vec P = m\\vec a$»;\n"
    "• campi (elettrico, magnetico, gravitazionale): «campo: (P, Q)» con le "
    "componenti del campo in x e y, per esempio per una carica positiva "
    "nell'origine «campo: (x/(x^2+y^2)^1.5, y/(x^2+y^2)^1.5)», la carica come "
    "punto; «linea: da (1, 0)» per una linea di campo.\n"
    "Esempio, le forze su un blocco trascinato con attrito:\n"
    "```piano\n"
    "titolo: Forze sul blocco\n"
    "numeri: no\n"
    "assi: no\n"
    "x: -3.5, 3.5\n"
    "y: -3, 3\n"
    "poligono: (-1, -0.7), (1, -0.7), (1, 0.7), (-1, 0.7)\n"
    "punto: G (0, 0)\n"
    "vettore P: (0, -2.2) da G\n"
    "vettore N: (0, 2.2) da G\n"
    "vettore F: (2.4, 0) da G\n"
    "vettore Fa: (-1.4, 0) da G\n"
    "```\n"
)

# Le materie: per ognuna le regole di contenuto (valgono sempre) e quelle dei
# grafici (solo con i grafici accesi, fra il piano di base e le barre). L'ordine
# e' quello in cui entrano nelle istruzioni.
_MATERIE = {
    "matematica": ("", _REGOLA_GRAFICI_AVANZATI),
    "statistica": (_REGOLA_STATISTICA, _GRAFICI_STATISTICA),
    "chimica": (_REGOLA_CHIMICA, _GRAFICI_CHIMICA),
    "fisica": (_REGOLA_FISICA, _GRAFICI_FISICA),
}

_REGOLA_NO_GRAFICI = (
    "\nNON generare grafici, diagrammi, mappe concettuali né blocchi ```mermaid, "
    "```piano, ```spazio, ```molecola, ```reazione, ```orbitali, ```titolazione, "
    "```energia, ```reticolo o ```tavola."
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
                     dettaglio: str | None = None, materie=None) -> str:
    """Le regole per UN lavoro: quelle di base piu' le aggiunte scelte.

    None vuol dire «come dicono le impostazioni» (SUMMARY_CHARTS e
    SUMMARY_CODE_COMMENTS), che e' quello che usa la riga di comando; la
    finestra passa invece le scelte fatte con gli interruttori. 'dettaglio' e'
    una delle chiavi di DETTAGLI (None = esteso, com'era sempre stato).

    'materie' sono le materie di cui parla il testo (vedi la funzione
    materie): per ognuna entrano le sue regole, e con i grafici accesi i suoi
    grafici. None vuol dire tutte. Un testo di nessuna materia ha comunque il
    piano cartesiano di base e i grafici dei dati.
    """
    if grafici is None:
        grafici = settings.SUMMARY_CHARTS
    if commenti is None:
        commenti = settings.SUMMARY_CODE_COMMENTS
    scelte = [m for m in _MATERIE if materie is None or m in materie]
    testo = prompt_base(dettaglio)
    testo += "".join(_MATERIE[m][0] for m in scelte)
    if grafici:
        from server.export import molecola
        disegni = []
        for m in scelte:
            if m != "chimica":
                disegni.append(_MATERIE[m][1])
                continue
            # Senza RDKit molecole e reazioni non si disegnano: meglio non
            # chiederle. Gli altri disegni della chimica si calcolano e basta.
            if molecola.disponibile():
                disegni.append(_MATERIE[m][1] + _GRAFICI_REAZIONE)
            disegni.append(_GRAFICI_CHIMICA_CALCOLATI)
        testo += _REGOLA_PIANO + "".join(disegni) + _REGOLA_GRAFICI_DATI
    else:
        testo += _REGOLA_NO_GRAFICI
    if commenti:
        testo += _REGOLA_COMMENTI
    return testo


# =============================================================================
#  I diagrammi nel testo che torna dal modello
# =============================================================================

_BLOCCO_MERMAID = re.compile(r"```mermaid[^\n]*\n(.*?)```[ \t]*\n?", re.S)
_BLOCCO_PIANO = re.compile(r"```piano[^\n]*\n(.*?)```[ \t]*\n?", re.S)
_BLOCCO_SPAZIO = re.compile(r"```spazio[^\n]*\n(.*?)```[ \t]*\n?", re.S)
_BLOCCO_MOLECOLA = re.compile(r"```molecola[^\n]*\n(.*?)```[ \t]*\n?", re.S)
# Gli altri disegni della chimica: i nomi sono quelli di export/chimica.BLOCCHI.
_BLOCCO_CHIMICA = re.compile(
    r"```(reazione|orbitali|titolazione|energia|reticolo|tavola)[^\n]*\n(.*?)```[ \t]*\n?",
    re.S | re.I)


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
    def _piano(m):
        """Il piano se si riesce a disegnare, o niente: mai la descrizione a vista."""
        from server.export import piano
        if not grafici or not piano.leggi(m.group(1)):
            return ""
        return f"```piano\n{m.group(1).strip()}\n```\n"
    fuori = _BLOCCO_MERMAID.sub(_sostituisci, testo or "")
    fuori = _BLOCCO_PIANO.sub(_piano, fuori)

    def _spazio(m):
        """Lo spazio 3D se si riesce a disegnare, o niente."""
        from server.export import spazio
        if not grafici or not spazio.leggi(m.group(1)):
            return ""
        return f"```spazio\n{m.group(1).strip()}\n```\n"
    fuori = _BLOCCO_SPAZIO.sub(_spazio, fuori)
    if grafici and "```molecola" in fuori:
        from server.export import molecola
        molecola.prepara(fuori)     # tutti i nomi a OPSIN in una volta, non blocco per blocco

    def _molecola(m):
        """La molecola se esiste e la formula torna, o niente.

        Se lo SMILES era sbagliato e la struttura giusta viene dal nome, nel
        riassunto si scrive quella giusta: chi lo riapre su un computer senza
        Java deve vedere la stessa molecola.
        """
        from server.export import molecola
        letta = molecola.leggi(m.group(1)) if grafici else None
        if not letta:
            return ""
        corpo = m.group(1).strip()
        senza_smiles = not re.search(r"(?im)^\s*smiles\s*:", corpo)
        if letta["verifica"] == "corretta" or senza_smiles:
            corpo = re.sub(r"(?im)^\s*smiles\s*:.*$", "", corpo).strip()
            corpo += f"\nsmiles: {letta['smiles']}"
        return f"```molecola\n{corpo}\n```\n"
    fuori = _BLOCCO_MOLECOLA.sub(_molecola, fuori)

    def _chimica(m):
        """Un altro disegno della chimica, se i suoi dati tornano, o niente."""
        from server.export import chimica
        if not grafici or not chimica.leggi(m.group(1).lower(), m.group(2)):
            return ""
        return f"```{m.group(1).lower()}\n{m.group(2).strip()}\n```\n"
    fuori = _BLOCCO_CHIMICA.sub(_chimica, fuori)
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
            # Prima del limite: il rifiuto «richiesta troppo grande» parla anche
            # lui di «rate_limit» e di «tokens per minute», e scambiato per
            # crediti finiti fermerebbe il lavoro dicendo di tornare domani.
            if _troppo_grande(msg):
                raise RichiestaTroppoGrande(msg) from e
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


class RichiestaTroppoGrande(Exception):
    """Groq ha rifiutato la richiesta perche' troppo grande per l'account.

    Non e' un guasto e non vuol dire crediti finiti: lo stesso testo, diviso
    in blocchi piu' piccoli, passa. Chi la riceve (_summarize_long) fa proprio
    questo.
    """


def _troppo_grande(msg: str) -> bool:
    """Vero se l'errore e' il rifiuto di una richiesta troppo grande (413)."""
    m = (msg or "").lower()
    return "413" in m or "request too large" in m or "request entity too large" in m


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
    import urllib.error
    try:
        try:
            with urllib.request.urlopen(req, timeout=settings.OLLAMA_TIMEOUT) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.URLError as e:
            # Il tempo scaduto mentre ci si collega arriva impacchettato cosi'.
            if isinstance(e.reason, TimeoutError):
                raise e.reason from e
            raise
    except TimeoutError as e:
        # «timed out» da solo non dice che cosa fare. Quasi sempre vuol dire
        # un modello troppo grande per il computer, che lavora dal disco.
        attesa = (f"{settings.OLLAMA_TIMEOUT // 60} minuti" if settings.OLLAMA_TIMEOUT >= 60
                  else f"{settings.OLLAMA_TIMEOUT} secondi")
        raise RuntimeError(
            f"il modello locale {settings.OLLAMA_MODEL} non ha finito in "
            f"{attesa}. Su questo computer e' troppo "
            "lento: prova un modello piu' piccolo (per esempio qwen2.5:3b), spegni "
            "«Grafici» per accorciare le istruzioni, oppure riprendi in «Cloud»."
        ) from e
    return (data.get("message", {}).get("content") or "").strip()


# Le parole che dicono che un testo parla di matematica: radici di parola,
# cosi' «derivata», «derivate», «derivabile» contano tutte. Sono parole che in
# un discorso qualunque compaiono di rado; «funzione», «limite» o «serie» da
# sole no, ma insieme alle altre si'. Per questo conta quante parole diverse
# compaiono, non quante volte.
_PAROLE_MATEMATICA = (
    "derivat", "integral", "equazion", "disequazion", "parabol", "circonferenz",
    "ellisse", "iperbol", "asintot", "funzion", "limite", "limiti", "polinom",
    "logaritm", "esponenzial", "trigonometr", "goniometr", "seno", "coseno",
    "tangent", "vettor", "matric", "determinant", "autovalor", "autovettor",
    "ascissa", "ordinata", "cartesian", "codominio",
    "successione", "successioni", "teorema",
    "geometri", "triangol", "cateto", "ipotenusa", "perpendicolar",
    "parallel", "gradiente", "differenzial", "topologi", "quadrica", "paraboloide",
    "iperboloide", "ellissoide", "piano tangente", "massimo relativo", "minimo relativo",
    "flesso", "concavit", "radice quadrata", "al quadrato", "al cubo", "fratto",
    "pi greco", "radianti", "direttrice", "retta", "rette",
    "sistema lineare", "numeri complessi", "parte reale", "parte immaginaria",
    "campo vettoriale", "curva di livello", "curve di livello", "riemann",
    "primitiva", "grafico della funzione",
)
# Anche i segni lasciati dalle formule (nei riassunti parziali, che il secondo
# giro rilegge): LaTeX e potenze scritte col cappelletto.
# Le formule della chimica ($\ce{H2O}$) non contano: sono chimica.
_SEGNI_MATEMATICA = re.compile(r"\\(?:frac|sqrt|int|sum|lim|sin|cos|vec)|\$(?!\\ce)[^$]{1,80}\$|\b[a-z]\^\d")

# Il lessico della statistica e della probabilita'. Qui le radici corte
# sbagliano piu' che in matematica: «media» sta dentro «immediatamente»,
# «campione» e' anche quello del mondo, «dado» anche quello da brodo. Per
# questo molte voci sono locuzioni intere.
_PAROLE_STATISTICA = (
    "statistic", "media aritmetica", "media ponderata", "media geometrica",
    "media armonica", "valore medio", "mediana", "varianz", "deviazione standard",
    "scarto quadratico", "scarto medio", "coefficiente di variazione",
    "frequenza assoluta", "frequenze assolute", "frequenza relativa",
    "frequenze relative", "frequenza cumulata", "frequenze cumulate",
    "distribuzione normale", "distribuzione di probabilit", "gaussian",
    "normale standard", "quartil", "percentil", "box plot", "boxplot",
    "istogramm", "diagramma a torta", "regressione", "correlazion", "covarianz",
    "campionament", "campione casuale", "spazio campionario", "probabilit",
    "eventi indipendenti", "eventi incompatibili", "evento contrario",
    "valore atteso", "speranza matematica", "variabile aleatoria",
    "variabili aleatorie", "variabile casuale", "variabili casuali", "binomial",
    "poisson", "bayes", "calcolo combinatorio", "permutazion", "combinazioni semplici",
    "combinazioni con ripetizione", "disposizioni semplici", "disposizioni con ripetizione",
    "fattoriale", "intervallo di confidenza", "test d'ipotesi", "test di ipotesi",
    "ipotesi nulla", "p-value", "livello di significativit", "chi quadro",
    "chi-quadro", "legge dei grandi numeri", "limite centrale", "outlier",
    "valori anomali", "indici di posizione", "indici di dispersione",
)

# Il lessico della chimica. Anche qui niente radici che stanno dentro parole
# comuni: «ione» e' dentro «lezione», «valenz» dentro «equivalenza», «esteri»
# dentro «esteriore», «ammin» dentro «amministrazione», «alcan» dentro
# «Balcani».
_PAROLE_CHIMICA = (
    "chimic", "molecol", "atom", "elettron", "protoni", "neutroni", "orbital",
    "legame covalent", "legami covalent", "legame ionic", "legami ionic",
    "legame a idrogeno", "legami a idrogeno", "legame metallic", "di valenza",
    "elettronegativit", "numero di ossidazione", "ossidazion", "redox",
    "ossidoriduzion", "reagent", "stechiometri", "numero di moli", "massa molare",
    "molarit", "molalit", "concentrazione molare", "soluto", "solvente",
    "acido forte", "acido debole", "base forte", "base debole", "acidi e basi",
    "soluzione tampone", "titolazion", "equilibrio chimico", "costante di equilibrio",
    "chatelier", "catalizzat", "entalpi", "idrocarbur", "alcano", "alcani",
    "alchen", "alchin", "aromatic", "benzen", "gruppo funzionale",
    "gruppi funzionali", "aldeid", "cheton", "ammina", "ammine", "ammid",
    "acido carbossilico", "acidi carbossilici", "isomer", "chiral", "enantiomer",
    "nomenclatura", "iupac", "tavola periodica", "configurazione elettronica",
    "catione", "cationi", "anione", "anioni", "ossido", "ossidi", "idrossid",
    "anidrid", "precipitat", "elettrolit", "ossigeno", "idrogeno", "carbonio",
    "azoto", "sodio", "cloruro", "solfat", "nitrat", "carbonat",
)

# Il lessico della fisica. «volt» sta dentro «volta», «moto» e' anche la
# motocicletta, «forze» anche quelle armate, «onde» e' anche «da dove»: per
# queste si usano locuzioni intere.
_PAROLE_FISICA = (
    "fisic", "velocit", "accelerazion", "newton", "joule", "watt", "pascal",
    "principio della dinamica", "principi della dinamica", "forza peso",
    "forza di attrito", "forza elastica", "forza centripeta", "risultante delle forze",
    "diagramma di corpo libero", "attrito", "piano inclinato", "moto rettilineo",
    "moto uniforme", "uniformemente accelerato", "caduta libera", "moto parabolico",
    "moto circolare", "moto armonico", "accelerazione di gravit", "gravitazion",
    "energia cinetica", "energia potenziale", "energia meccanica",
    "conservazione dell'energia", "lavoro di una forza", "quantità di moto",
    "impulso", "urto elastico", "urti", "momento di una forza", "momento angolare",
    "pressione atmosferica", "principio di archimede", "spinta di archimede",
    "termodinamic", "calore specifico", "dilatazione termica", "gas perfett",
    "carica elettrica", "cariche elettriche", "coulomb", "campo elettrico",
    "campo magnetico", "potenziale elettrico", "differenza di potenziale",
    "corrente elettrica", "intensità di corrente", "legge di ohm", "resistenza elettrica",
    "resistori", "circuito elettrico", "circuiti", "condensator", "induzione elettromagnetica",
    "lunghezza d'onda", "onde elettromagnetiche", "onda sonora", "onde sonore",
    "rifrazion", "riflessione della luce", "lente convergente", "lente divergente", "lenti convergenti", "specchio",
    "relativit", "quantistic", "fotone", "fotoni", "grandezze fisiche",
    "grandezza vettoriale", "grandezze vettoriali", "sistema internazionale",
    "metri al secondo", "chilogrammi",
)

# Il lessico di ogni materia: una materia c'e' quando nel testo compaiono
# almeno tre parole diverse del suo lessico.
_LESSICI = {
    "matematica": _PAROLE_MATEMATICA,
    "statistica": _PAROLE_STATISTICA,
    "chimica": _PAROLE_CHIMICA,
    "fisica": _PAROLE_FISICA,
}


def materie(testo: str, titolo: str | None = None) -> frozenset[str]:
    """Le materie di cui parla il testo (o il titolo della sezione).

    Basta un conto semplice: almeno tre parole diverse del lessico di una
    materia; per la matematica valgono anche le formule scritte, per la
    chimica i \\ce{...} (nei riassunti parziali del secondo giro). Un video di
    cucina che dice «al quadrato» una volta resta fuori; una lezione sulle
    derivate ci entra subito. Sbagliare per eccesso costa qualche token; per
    difetto, qualche regola o grafico in meno: nessuno dei due e' un guasto.
    Un testo puo' parlare di piu' materie: una lezione sulla gaussiana e'
    statistica e matematica insieme.
    """
    minuscolo = f" {titolo or ''} {testo or ''} ".lower()
    trovate = {m for m, parole in _LESSICI.items()
               if sum(1 for p in parole if p in minuscolo) >= 3}
    if len(_SEGNI_MATEMATICA.findall(testo or "")) >= 2:
        trovate.add("matematica")
    if (testo or "").count("\\ce{") >= 2:
        trovate.add("chimica")
    return frozenset(trovate)


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
    # Le istruzioni si scelgono pezzo per pezzo, secondo le materie di cui il
    # pezzo parla; ogni combinazione si compone una volta sola.
    composte: dict[frozenset[str], str] = {}

    def sistema(text, title):
        chiave = materie(text, title)
        if chiave not in composte:
            composte[chiave] = prompt_riassunto(grafici, commenti, dettaglio, chiave)
        return composte[chiave]

    # Ogni motore si porta dietro la misura dei suoi blocchi (max_chars), che
    # _summarize_long legge: grande per Groq, piccola per Ollama.
    if client is not None:
        label = f"Riassunto automatico (Groq · {settings.GROQ_SUMMARY_MODEL})"

        def con_groq(text, title):
            return _summarize_groq(client, text, title, sistema(text, title), on_attesa)
        con_groq.max_chars = settings.GROQ_SUMMARY_MAX_CHARS
        return con_groq, label
    _check_ollama()
    label = f"Riassunto automatico (locale · Ollama {settings.OLLAMA_MODEL})"

    def con_ollama(text, title):
        return _summarize_ollama(text, title, sistema(text, title))
    con_ollama.max_chars = settings.OLLAMA_SUMMARY_MAX_CHARS
    return con_ollama, label


def _summarize_long(summarize_fn, text: str, section_title: str | None,
                    massimo: int | None = None) -> str:
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

    Quanto sono grandi i blocchi
        Lo dice il motore (summarize_fn.max_chars, vedi _make_summarizer), o
        'massimo' se lo si passa. Ogni blocco si porta dietro tutte le
        istruzioni, quindi blocchi piu' grandi vogliono dire meno token. Se
        Groq rifiuta un blocco perche' troppo grande per l'account, si rifa'
        tutto con la misura di ripiego, SUMMARY_MAX_CHARS.

        Prima la misura si cambiava scrivendo una variabile di questo file,
        ma il tagliatore leggeva quella di translation.py: i blocchi erano
        sempre da 4.500 caratteri, e un video di mezz'ora costava sei
        richieste invece di una.
    """
    text = (text or "").strip()
    if not text:
        return ""
    massimo = massimo or getattr(summarize_fn, "max_chars", None) or SUMMARY_MAX_CHARS
    try:
        if len(text) <= massimo:
            return summarize_fn(text, section_title)
        # Map: riassumi a blocchi (riuso lo splitter della traduzione).
        blocks = _split_for_translation(text, massimo)
        partials = [summarize_fn(b, section_title) for b in blocks]
        merged = "\n\n".join(p for p in partials if p)
        # Reduce: ricompatta i parziali in un unico riassunto coerente.
        return summarize_fn(merged, section_title)
    except RichiestaTroppoGrande:
        if massimo <= SUMMARY_MAX_CHARS:
            raise
        console.print(f"[warning]Groq: richiesta troppo grande, riprovo a blocchi da "
                      f"{SUMMARY_MAX_CHARS} caratteri.[/warning]")
        return _summarize_long(summarize_fn, text, section_title, SUMMARY_MAX_CHARS)
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
