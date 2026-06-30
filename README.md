<div align="center">

# 🎙️ EchoScript

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Groq-Whisper-F55036?logo=groq&logoColor=white" alt="Groq">
  <img src="https://img.shields.io/badge/faster--whisper-locale-0A9396?logo=openai&logoColor=white" alt="faster-whisper">
  <img src="https://img.shields.io/badge/Rich-TUI-4EC820?logo=windowsterminal&logoColor=white" alt="Rich">
  <img src="https://img.shields.io/badge/Flet-GUI-02569B?logo=flutter&logoColor=white" alt="Flet">
  <img src="https://img.shields.io/badge/yt--dlp-downloader-FF0000?logo=youtube&logoColor=white" alt="yt-dlp">
  <img src="https://img.shields.io/badge/fpdf2-PDF-EC1C24?logo=adobeacrobatreader&logoColor=white" alt="fpdf2">
  <img src="https://img.shields.io/badge/Google_Translate-traduzione-4285F4?logo=googletranslate&logoColor=white" alt="deep-translator">
  <img src="https://img.shields.io/badge/Ollama-riassunto_locale-000000?logo=ollama&logoColor=white" alt="Ollama">
  <img src="https://img.shields.io/badge/Llama_3.3_·_Qwen_2.5-LLM-7C3AED" alt="LLM">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

<p align="center">
  Trascrivi i video YouTube <b>e i tuoi audio locali</b> in <b>testo, Markdown, JSON e PDF</b>,<br>
  poi <b>traducili</b> in italiano e ottienine un <b>riassunto pulito</b> (senza "ehm/uhm", ripetizioni e autocorrezioni).<br>
  <b>Velocemente</b> con Groq oppure <b>100% in locale</b> per la massima privacy.<br>
  Pensato per <b>studiare</b> video lunghi (RAG, fine-tuning, lezioni) leggendoli invece di guardarli per ore.<br>
  Disponibile come <b>app desktop</b> (GUI) o da <b>terminale</b> (CLI).<br>
  <b>Niente abbonamenti, niente limiti giornalieri, niente minutaggio ridotto.</b>
</p>

</div>

```bash
git clone https://github.com/Imkun-on/EchoScript.git
cd EchoScript
pip install -r requirements.txt

python gui/main.py        # interfaccia grafica desktop (GUI)
python transcriber.py     # interfaccia da terminale (CLI)
```

---

## Indice

- [📋 Descrizione del progetto](#-descrizione-del-progetto)
- [🆚 Perché EchoScript e non i soliti "tool gratis"](#-perché-echoscript-e-non-i-soliti-tool-gratis)
- [🖥️ Due interfacce: GUI o terminale](#️-due-interfacce-gui-o-terminale)
- [🖱️ Guida all'app desktop (per tutti)](#️-guida-allapp-desktop-per-tutti)
- [🔀 I due backend: cloud o locale](#-i-due-backend-cloud-o-locale)
- [✨ Caratteristiche](#-caratteristiche)
- [⬇️ Scarica l'app pronta (.exe)](#️-scarica-lapp-pronta-exe)
- [📦 Installazione da sorgente (sviluppatori)](#-installazione-da-sorgente-sviluppatori)
- [🔑 Come ottenere una API key Groq](#-come-ottenere-una-api-key-groq)
- [📚 Librerie usate e perché](#-librerie-usate-e-perché)
- [🚀 Uso ed esempi](#-uso-ed-esempi)
- [⚙️ Come funziona (le fasi)](#️-come-funziona-le-fasi)
- [💾 Struttura dei file di output](#-struttura-dei-file-di-output)
- [📄 Esportazione PDF](#-esportazione-pdf)
- [🌐 Traduzione automatica](#-traduzione-automatica)
- [🧠 Riassunto automatico](#-riassunto-automatico)
- [👁️ Analisi visiva del video](#️-analisi-visiva-del-video)
- [🛠️ Configurazione](#️-configurazione)
- [🔒 Privacy](#-privacy)
- [⚖️ Note legali](#️-note-legali)
- [📄 Licenza](#-licenza)

---

## 📋 Descrizione del progetto

**EchoScript** è uno strumento (**app desktop** o **da terminale**) che trasforma un video YouTube in **testo scritto**, ordinato e pronto da leggere o da dare in pasto ad altri strumenti.

L'idea nasce da un bisogno concreto: i video formativi (su **RAG**, **fine-tuning**, lezioni, talk) spesso durano **1-2 ore**, e non sempre si ha il tempo o la concentrazione di seguirli tutti. EchoScript li **trascrive** usando i **capitoli** del video come sezioni, così puoi *leggere* il contenuto in pochi minuti, cercarlo, evidenziarlo, o usarlo come base di conoscenza.

Puoi scegliere **cosa** trascrivere:

- 📺 **un video YouTube**, da URL (scarica audio, info e capitoli);
- 🎙️ **un file audio locale** (note vocali del telefono, registrazioni del PC: `m4a`, `mp3`, `wav`, `ogg`, `opus`, anche video `mp4`/`mov`…), oppure **un'intera cartella** per trascriverli tutti in sequenza (batch).

E puoi scegliere **come** trascrivere:

- ⚡ **Groq (cloud)**: velocissimo anche **senza GPU** (trascrive 2 ore in pochi secondi), praticamente gratis.
- 🔒 **Locale (faster-whisper su CPU)**: **100% offline e privato**, l'audio non lascia mai il tuo PC.

A fine trascrizione puoi **esportare in PDF** per leggerla comodamente, divisa per capitoli.

Lo strumento è pensato per:

- 🎓 **Studenti e autodidatti** che vogliono leggere i video invece di guardarli per ore
- 🧠 **Chi costruisce un RAG / knowledge base** a partire dai video (l'output `.json` ha già i timestamp pronti per il chunking)
- 🔐 **Chi tiene alla privacy** e vuole una trascrizione totalmente offline

---

## 🆚 Perché EchoScript e non i soliti "tool gratis"

Molti siti e app di trascrizione si presentano come "gratis", ma poi scopri che:
- dopo pochi minuti chiedono di **pagare** o di sottoscrivere un **abbonamento**;
- impongono un **limite giornaliero** (es. 30 minuti al giorno) o un **tetto di durata** per video;
- bloccano i **video lunghi** (proprio quelli che servirebbe trascrivere);
- ti fanno **creare un account**, aggiungono **watermark** o degradano la qualità;
- caricano il tuo audio su **server sconosciuti**, senza alcuna garanzia di privacy.

EchoScript nasce per **eliminare tutte queste trappole**:

| | Tipico tool "gratis" online | **EchoScript** |
|---|---|---|
| **Costo reale** | gratis → poi paywall / abbonamento | **gratis davvero** in locale · quasi gratis con il free tier Groq (chiave tua) |
| **Limite giornaliero** | spesso pochi minuti/giorno | **nessuno** in locale |
| **Durata massima video** | spesso 10-30 min | **video da 2h+** senza problemi |
| **Account obbligatorio** | sì | **no** (locale); per Groq solo una chiave gratuita |
| **Watermark / qualità ridotta** | frequenti | **mai** |
| **Privacy** | upload su server terzi | **locale = niente lascia il tuo PC** |
| **Formati di output** | spesso solo `.txt` | `.md`, `.txt`, `.json`, **`.pdf`** |
| **Funziona offline** | no | **sì** (backend locale) |
| **Open source** | quasi mai | **sì** |

In breve: **lo controlli tu**, gira sul **tuo computer**, e non ti chiede nulla a sorpresa.

---

## 🖥️ Due interfacce: GUI o terminale

EchoScript si usa in **due modi**, con lo **stesso motore** sotto (stessa trascrizione, stessi formati di output):

- 🖥️ **App desktop (GUI)** con `python gui/main.py`: interfaccia grafica nativa (Flet), scura, con sfondo animato. Pensata per chi preferisce i clic.
- ⌨️ **Terminale (CLI)** con `python transcriber.py`: la classica interfaccia testuale (Rich), comoda per batch e automazioni.

La **GUI** aggiunge alcune comodità:

- 🌍 **Lingua dell'interfaccia** italiano/inglese, con selettore a bandiere
- ▶️ **Anteprima del video**: caricando un URL si apre una **finestra di conferma** con copertina e dati (canale, views, mi piace, iscritti, categoria, lingua)
- 🏷️ **Badge del motore** durante la trascrizione (Groq cloud o Locale CPU), così sai sempre con cosa stai trascrivendo
- 📊 **Finestra di avanzamento dedicata**: barra reale, checklist dei passaggi e una frase su cosa sta avvenendo
- 🌐 **Traduzione in italiano** e 🧠 **riassunto** attivabili con due interruttori (card "Output aggiuntivi")
- 💰 **Crediti API Groq**: un pulsante mostra i **crediti residui** (e quando si azzerano); a fine lavoro vedi anche quelli **usati**
- 📄 **PDF generato sempre** in automatico

> Entrambe scrivono gli stessi file in `results/<nome>/`. Scegli quella che preferisci: il risultato è identico.

---

## 🖱️ Guida all'app desktop (per tutti)

Questa sezione è pensata per chi **non è tecnico**: spieghiamo ogni schermata, ogni pulsante e ogni messaggio. **Non serve saper programmare.**

> ▶️ **Come si avvia:** doppio clic sull'eseguibile (se hai la versione pacchettizzata), oppure dalla cartella del progetto esegui `python gui/main.py`.

<p align="center">
  <img src="docs/screenshot.png" alt="EchoScript - app desktop" width="840">
</p>

### In alto: lingua e pulsanti finestra
- In alto a destra ci sono **due bandierine** 🇮🇹 / 🇬🇧: cliccale per cambiare la **lingua dell'interfaccia** (italiano o inglese). Tutto il testo cambia all'istante.
- I tre pulsantini in cima (**–**, **▢**, **✕**) servono a **minimizzare**, **ingrandire** e **chiudere** la finestra, come in ogni programma.

### Passo 1 — "Come vuoi trascrivere?"
Due riquadri da scegliere (si illuminano di verde quando selezionati):
- 🔒 **Locale**: trascrive **sul tuo computer**, **senza internet** e senza inviare nulla. Sotto puoi scegliere il **modello** (più accurato = più lento). Consigliato se hai una GPU; su CPU è più lento.
- ⚡ **Groq (cloud)**: **velocissimo**, ma l'audio viene inviato ai server Groq. Richiede una **chiave gratuita**: clicca **"Carica chiave da file .txt"** e seleziona il file con la tua chiave. Il pulsante **"Mostra crediti API Groq"** apre una finestra con l'elenco dei **crediti residui** per la trascrizione (secondi audio, richieste) e **a che ora si azzerano**; **"Ottieni una chiave →"** apre il sito dove crearla.

> A fine trascrizione, nella finestra **"Completato!"** compaiono anche i **crediti Groq usati** (audio trascritto) e quelli **residui per oggi**.

### Passo 2 — "Cosa vuoi trascrivere?"
- 📺 **YouTube**: incolla il **link** del video nel campo e clicca **"Carica info"**.
- 🎙️ **File locale**: clicca **"Scegli file audio…"** e prendi un file dal computer (vanno bene anche **video** e **registrazioni schermo**).

### La finestra di conferma del video (YouTube)
Dopo **"Carica info"** si apre una finestra con la **copertina** del video e i suoi dati (canale, visualizzazioni, mi piace, iscritti, durata, lingua…). Ti chiede: *è questo il video giusto?*
- **Conferma** → accetti il video (sotto compare *"✓ Video confermato"*).
- **Annulla** → lo scarti e puoi incollarne un altro.

### Passo 3 — "Output aggiuntivi" (opzionale)
Sotto i due riquadri c'è una card con **tre interruttori**, tutti **spenti** di default (così una trascrizione semplice resta tale):
- 🌐 **Traduci in italiano**: se l'audio **non è già in italiano**, oltre alla trascrizione crea anche una **traduzione** nella sottocartella `traduzioni/` (Google Translate se hai la chiave Groq, altrimenti **Ollama** in locale e 100% offline).
- 🧠 **Crea riassunto**: genera un **riassunto pulito per sezione** del testo italiano in `riassunti/`. Usa **Groq** se hai caricato la chiave, altrimenti **Ollama** in locale (se installato). Se nessuno dei due è disponibile, la trascrizione viene comunque salvata e compare un avviso.
- 👁️ **Analisi visiva del video**: "guarda" i fotogrammi ed estrae **codice, formule, grafici** a schermo, includendoli nel riassunto e in un **documento dedicato** con i fotogrammi (vedi il capitolo [Analisi visiva del video](#️-analisi-visiva-del-video)). Compare solo per le sorgenti **video**.

### Il pulsante "Trascrivi"
È il grande pulsante verde in basso. Si **attiva** solo quando è tutto pronto. Se lo premi prima, compare una **finestra d'avviso** che ti **elenca cosa manca**, ad esempio:
- *caricare la chiave API Groq* (solo se usi Groq);
- *caricare e confermare il video YouTube*, oppure *scegliere un file audio*.

### Durante la trascrizione
Si apre una **finestra dedicata** con l'avanzamento (niente animazioni finte):
- in alto un **badge** dice con cosa stai trascrivendo: **Groq (cloud)** (verde) o **Locale CPU** (arancione, perché può richiedere minuti);
- una **barra reale** con il **numero di fase** (es. *"Fase 2/5"*) e la **percentuale** complessiva;
- un **elenco dei passaggi** che si spunta man mano (Trascrizione → eventuale Traduzione → eventuale Riassunto → Salvataggio): rispecchia esattamente le opzioni che hai scelto;
- una **breve frase** che racconta cosa sta avvenendo in quel momento e il **piano completo** del lavoro.

### A fine trascrizione
Il **PDF viene creato sempre**, in automatico, e i file vengono salvati senza ulteriori domande.

### Il risultato
Una finestra **"Completato!"** riassume tutto: motore usato, numero di parole/sezioni, **dove sono stati salvati i file** (cartella `results/`) e l'elenco dei file creati. Il pulsante **"Apri cartella risultati"** apre direttamente la cartella.

### Messaggi speciali (video lungo o già fatto)
- 🔁 **"Video già trascritto"**: se rifai un video già fatto, l'app ti chiede se **Ritrascrivere tutto** (sostituisce i file).
- ⏸️ **"Ripresa disponibile"**: se una trascrizione lunga si era interrotta (limite Groq, o trascrizione locale interrotta), l'app ha **salvato il punto** e ti propone di **Riprendere** da dove si era fermata o **Ricominciare** da capo.
- ⏳ **"Limite Groq raggiunto"**: avviso arancione che indica quanti blocchi sono stati fatti; **riprendi più tardi**, quando tornano i crediti gratuiti.

---

## 🔀 I due backend: cloud o locale

All'avvio un pannello ti fa scegliere il motore di trascrizione:

| Backend | Privacy | Velocità (senza GPU) | Costo | Quando usarlo |
|---|---|---|---|---|
| 🔒 **Locale** (faster-whisper) | **Massima**: l'audio resta sul PC | 🐢 Più lento | **Gratis** | Audio privati/sensibili, nessun limite |
| ⚡ **Groq** (cloud) | L'audio va sui server Groq | ⚡ Velocissimo | Free tier generoso | Video YouTube pubblici, quando hai fretta |

Se scegli **Locale**, un secondo pannello ti fa scegliere il modello ogni volta:

| Modello | Velocità ↔ Accuratezza |
|---|---|
| `base` | veloce, meno accurato |
| `small` ⭐ | equilibrio consigliato |
| `medium` | più accurato, più lento |
| `large-v3` | massima accuratezza, molto lento su CPU |
| `large-v3-turbo` | quasi "large" ma più rapido |

> Al primo uso di un modello locale, `faster-whisper` ne scarica i **pesi** da HuggingFace (una volta sola). L'**audio**, però, non viene mai inviato da nessuna parte.

---

## ✨ Caratteristiche

- 🖥️ **Due interfacce**: app desktop **GUI** (`gui/main.py`) o **CLI** da terminale (`transcriber.py`)
- 🔀 **Due backend** selezionabili da pannello: Groq (cloud, veloce) o faster-whisper (locale, privato)
- 🎙️ **Due sorgenti**: video **YouTube** (da URL) o **file audio locali** (telefono/PC), anche le **registrazioni schermo** (`mp4`/`mov`/`mkv`…), anche un'**intera cartella** in batch
- 📋 **Scheda video** prima di partire (titolo, canale, visualizzazioni, **mi piace, iscritti, categoria, lingua**, data, durata, capitoli)
- 🗣️ **Lingua dell'audio rilevata** automaticamente (Whisper) e mostrata nel riepilogo
- ✅ **Conferma** prima di trascrivere
- ⬇️ **Download solo audio** (leggero) con barra di avanzamento (velocità + tempo stimato)
- ⏱️ **Minutaggi e sezioni**: usa i **capitoli** di YouTube come sezioni del documento
- 💾 **3 formati base** sempre generati: `.md` (umano), `.txt` (per altri LLM), `.json` (per RAG)
- 📄 **PDF generato sempre** in automatico, diviso per capitoli
- 🌐 **Traduzione automatica** in italiano (se l'audio non è già in italiano): Google Translate in cloud · Ollama in locale (offline)
- 🧠 **Riassunto automatico** del testo, **per sezione**: pulisce intercalari, ripetizioni e autocorrezioni (Groq in cloud · Ollama in locale)
- 👁️ **Analisi visiva del video** (opzionale): "guarda" i fotogrammi ed estrae **codice, formule, grafici e diagrammi** a schermo, integrandoli nel riassunto e in un **documento dedicato con i fotogrammi** (Groq in cloud · Ollama in locale)
- 📐 **PDF "ricco"**: quando servono, **formule LaTeX** e **mappe** vengono renderizzate e i **fotogrammi** mostrati nel testo (browser di sistema; ripiego automatico su PDF semplice)
- 🗂️ **Output organizzato** in `results/<nome video>/` nelle sottocartelle `trascrizioni/`, `traduzioni/`, `riassunti/`, `analisi_visiva/`
- 🎨 **Interfacce curate**: GUI scura con sfondo animato, oppure CLI Rich con barre e pannelli
- 🔑 **Gestione chiave sicura**: variabile d'ambiente o file `.env` (mai nel codice)
- 🧯 **Errori chiari**: la chiave viene validata all'avvio; niente retry inutili su errori di autenticazione

---

## ⬇️ Scarica l'app pronta (.exe)

Se **non sei uno sviluppatore** e vuoi solo usare il programma, non serve installare Python né altro: scarica l'app già pronta.

1. Vai alla pagina **[Releases](https://github.com/Imkun-on/EchoScript/releases/latest)** del progetto su GitHub.
2. Scarica il file **`EchoScript.zip`** dell'ultima versione.
3. **Estrai** lo ZIP in una cartella a piacere (Desktop, Documenti…). Tieni i file **insieme**: serve sia `EchoScript.exe` sia la cartella **`_internal`** che lo accompagna.
4. Doppio click su **`EchoScript.exe`**. Fatto: si apre l'app, **senza installare nulla**.

> 🛡️ **Primo avvio – Windows SmartScreen:** poiché l'app non è firmata digitalmente, Windows può mostrare *"Windows ha protetto il PC"*. Clicca **"Ulteriori informazioni" → "Esegui comunque"**. È normale per i programmi gratuiti non firmati.

**Cosa è incluso e cosa no:**
- ✅ **Tutto incluso**: non servono Python, ffmpeg o altre installazioni.
- 📥 La **prima volta** che usi il backend **locale**, l'app scarica una tantum il modello da HuggingFace (poi resta in cache, anche offline).
- ⚡ Per il backend **Groq** (cloud) serve solo una **chiave gratuita** (vedi più sotto).
- 💻 La release `.exe` è per **Windows**. Le versioni per **macOS/Linux** arrivano dai rispettivi build (vedi sezione installazione da sorgente nel frattempo).

> Per **disinstallare** basta cancellare la cartella: l'app non scrive nel registro di sistema. (Le trascrizioni stanno in `results/` accanto all'eseguibile.)

---

## 📦 Installazione da sorgente (sviluppatori)

Questa parte serve solo se vuoi **eseguire dal codice** o **modificare** il progetto. Per il semplice uso, vedi [Scarica l'app pronta (.exe)](#️-scarica-lapp-pronta-exe).

### Requisiti

- **Python 3.10+**
- **[ffmpeg](https://ffmpeg.org)** installato nel sistema (serve a yt-dlp e alla preparazione audio)
- *(solo per Groq)* una **API key Groq** gratuita (vedi sotto)
- *(solo per il backend locale)* `faster-whisper`
- *(solo per l'export PDF)* `fpdf2`
- *(solo per la GUI desktop)* `flet`

### Passi

```bash
git clone https://github.com/Imkun-on/EchoScript.git
cd EchoScript
pip install -r requirements.txt
python transcriber.py
```

Installazione di **ffmpeg**:

```bash
# Windows
winget install Gyan.FFmpeg
# macOS
brew install ffmpeg
# Linux (Debian/Ubuntu)
sudo apt install ffmpeg
```

> ⭐ **File da lanciare:** la **GUI** da `gui/main.py`, la **CLI** da `transcriber.py`.

---

## 🔑 Come ottenere una API key Groq

La chiave serve **solo** se usi il backend **Groq** (cloud). È **gratuita**.

1. Vai su **https://console.groq.com** e **registrati** (puoi usare Google, GitHub o email).
2. Una volta dentro, apri la sezione **API Keys**: **https://console.groq.com/keys**
3. Clicca su **"Create API Key"**, dai un nome (es. `echoscript`) e **conferma**.
4. **Copia subito** la chiave (inizia con `gsk_...`): viene mostrata **una sola volta**.
5. Incollala nel file **`.env`** del progetto:
   ```
   GROQ_API_KEY=gsk_la-tua-chiave-qui
   ```
   In alternativa, impostala come variabile d'ambiente:
   ```powershell
   # Windows (PowerShell), poi riapri il terminale
   setx GROQ_API_KEY "gsk_la-tua-chiave-qui"
   ```
   ```bash
   # macOS / Linux
   export GROQ_API_KEY="gsk_la-tua-chiave-qui"
   ```
6. Fatto! Se non la imposti, il programma te la chiede all'avvio (senza salvarla).

> 📊 **Limiti del free tier**: Groq impone dei *rate limit* (richieste al minuto/giorno e secondi di audio all'ora/giorno). Sono generosi, ma un singolo video da 2h potrebbe avvicinarsi al limite orario: in tal caso ricevi un errore `429` e basta attendere. Controlli sempre i tuoi limiti su **https://console.groq.com/settings/limits**. Se preferisci nessun limite, usa il **backend locale**.

> 🔐 La chiave è **segreta**: il file `.env` è già in `.gitignore`, quindi **non finirà mai su GitHub**.

---

## 📚 Librerie usate e perché

### Dipendenze esterne (pip)

| Libreria | A cosa serve | Perché proprio questa |
|---|---|---|
| `yt-dlp` | Scarica audio e metadati (titolo, capitoli, durata) da YouTube | Lo standard de facto: gestisce stream, resume, e l'estrazione dei metadati |
| `groq` | Client ufficiale dell'API Groq (Whisper) | SDK ufficiale, semplice e veloce |
| `rich` | Interfaccia da terminale: pannelli, tabelle, barre, colori | Trasforma la CLI in un'esperienza curata (`Panel`, `Progress`, `Columns`) |
| `faster-whisper` | *(opzionale)* Trascrizione **locale** su CPU | Implementazione ottimizzata di Whisper (CTranslate2), ottima su CPU con `int8` |
| `deep-translator` | **Traduzione** in italiano (cloud) | Usa Google Translate (endpoint gratuito): nessuna chiave, nessun credito. In locale senza chiave la traduzione passa invece a **Ollama** (offline) |
| `fpdf2` | *(opzionale)* Esportazione in **PDF** | Pure-python, **niente LaTeX di sistema**; supporta font Unicode |
| `flet` | *(opzionale)* **GUI desktop** (`gui/main.py`) | Interfaccia grafica nativa moderna in Python; la CLI funziona senza |

### Strumento esterno (non pip)

| Strumento | A cosa serve | Note |
|---|---|---|
| **[Ollama](https://ollama.com)** | **Riassunto in locale** (100% offline) | Programma separato da installare una volta; ci si parla via HTTP (nessuna libreria pip). Non serve se usi Groq per il riassunto. Modello consigliato: `qwen2.5:7b` |

> Per il riassunto in **cloud** si riusa il client **`groq`** già presente (con un modello di chat, non Whisper): nessuna dipendenza in più.

### Libreria standard (nessuna installazione)

`os`, `re`, `json`, `sys`, `signal`, `shutil`, `tempfile`, `subprocess`, `datetime`, `urllib`: percorsi/file, regex, JSON, gestione Ctrl+C, chiamate a ffmpeg/ffprobe, date e — per Ollama — le chiamate HTTP.

---

## 🚀 Uso ed esempi

Avvia il programma:

```bash
python transcriber.py
```

Flusso tipico:

1. **Scegli il backend** (1 = Locale · 2 = Groq).
2. *(se locale)* **Scegli il modello** (1-5).
3. **Scegli la sorgente** (1 = YouTube · 2 = File locale).
4. **Indica cosa trascrivere**: l'**URL** del video, oppure il **percorso** di un file audio o di una **cartella** (batch).
5. Controlla la **scheda** (video o file) e **conferma**.
6. Attendi: vedrai le fasi (**Download** se da YouTube → **Preparazione** se Groq → **Trascrizione**) con barre di avanzamento, e il motore in uso (**Groq cloud** o **Locale CPU**).
7. Il **PDF viene generato sempre**, in automatico.
8. Trovi tutto in `results/<nome>/`.

> 🎙️ **File locali**: il download non serve (il file ce l'hai già) e i metadati YouTube (canale, capitoli…) non esistono, quindi l'output usa il **nome del file** come titolo e una singola sezione "testo continuo". Indicando una **cartella**, ogni file audio al suo interno viene trascritto in sequenza, riusando lo stesso motore e le stesse scelte di export.

### Esempio: backend Groq

```
─────────────── Come vuoi trascrivere? ───────────────
┌─ 1  🔒 Locale ──────────────┐  ┌─ 2  ⚡ Groq (cloud) ────────┐
│  ✓ privacy totale: resta... │  │  ✓ velocissimo, anche...    │
│  ✗ più lento (nessuna GPU)  │  │  ✗ niente privacy: cloud    │
│  • per audio privati        │  │  • per video pubblici       │
└─────────────────────────────┘  └─────────────────────────────┘

› Scelta (1 = Locale · 2 = Groq · q = annulla): 2

──────────────── Cosa vuoi trascrivere? ────────────────
┌─ 1  📺 YouTube ─────────────┐  ┌─ 2  🎙 File locale ─────────┐
│  ✓ incolli l'URL di un video│  │  ✓ audio da telefono/PC     │
│  ✓ scarica audio, info, cap.│  │  ✓ anche una cartella (batch)│
│  • per video pubblici online│  │  • per note vocali          │
└─────────────────────────────┘  └─────────────────────────────┘

› Scelta (1 = YouTube · 2 = File locale · q = annulla): 1

› Incolla l'URL del video YouTube (q per uscire): https://www.youtube.com/watch?v=...

┌─ 🎬 RAG è già vecchio? ... ──────────────────────┐
│  📺  Canale           Simone Rizzo               │
│  👁  Visualizzazioni  49.586                     │
│  👍  Mi piace         2.350                       │
│  👥  Iscritti         128.000                     │
│  🏷  Categoria        Science & Technology        │
│  🗣  Lingua           Italiano                    │
│  📅  Pubblicato       21/04/2026                 │
│  ⏱  Durata           43:09                       │
│  📑  Capitoli         21 sezioni                 │
└──────────────────────────────────────────────────┘

› Procedo con la trascrizione di questo video? (s/n): s

──── ⬇ Fase 1/3 — Download audio ────
──── ✂ Fase 2/3 — Preparazione audio ────
──── ✎ Fase 3/3 — Trascrizione · Groq (cloud) ────
```

### Esempio: file audio locale (cartella in batch)

```
› Scelta (1 = Locale · 2 = Groq · q = annulla): 1
› Modello (1-5 · q = annulla): 2
› Scelta (1 = YouTube · 2 = File locale · q = annulla): 2

› Incolla il percorso del file o della cartella audio (q per uscire): C:\Users\io\note_vocali

┌─ 🎙 3 file da trascrivere ───────────────────────┐
│  #   File                              Durata     │
│  1   lezione_01.m4a                     12:04     │
│  2   riunione_lunedi.mp3                47:31     │
│  3   memo.wav                            1:58     │
└──────────────────── durata totale ~1:01:33 ──────┘

› Procedo con la trascrizione di questi 3 file? (s/n): s

──── ✎ Fase 1/1 — Trascrizione · Locale CPU (small) ────   (per ogni file)
```

### Caso d'uso: costruire un RAG dai video

Trascrivi i video di studio, poi usa i file **`.json`** (segmenti con timestamp) come fonte per la tua pipeline RAG: sono già pronti per il *chunking* e l'indicizzazione.

### Caso d'uso: leggere un talk invece di guardarlo

Trascrivi un talk lungo e usa l'**export PDF**: ottieni un PDF pulito, diviso per capitoli, da leggere sul tablet o stampare.

---

## ⚙️ Come funziona (le fasi)

1. **Info**: con una chiamata leggera (`yt-dlp`) si leggono SOLO i metadati (titolo, canale, durata, **capitoli**), senza scaricare nulla.
2. **Download audio**: si scarica la sola traccia audio (leggera) con barra di avanzamento.
3. **Preparazione** *(solo Groq)*: l'audio viene riconvertito a 16 kHz mono e **spezzato in blocchi da ~10 min** (per stare nei limiti di dimensione dell'API e avere una barra sensata).
4. **Trascrizione**: ogni blocco (Groq) o l'intero file (locale) viene trascritto in **segmenti con timestamp**; i minutaggi di ogni blocco vengono corretti rispetto all'intero video.
5. **Assemblaggio**: i segmenti vengono raggruppati per **capitolo** (se presenti) e salvati nei vari formati.
6. **Export PDF**: sempre, in automatico.

> 🎙️ **Con un file locale** i passi *Info* e *Download* non servono: il file viene dato direttamente a ffmpeg/Whisper. La durata si ricava con `ffprobe`, il titolo dal nome del file e, non essendoci capitoli, si ottiene un'unica sezione "testo continuo".

---

## 💾 Struttura dei file di output

```
results/
└── <Nome Video o nome file>/
    ├── trascrizioni/          (la trascrizione originale)
    │   ├── <Nome>.md          (sezioni con minutaggio nel titolo, prosa pulita)
    │   ├── <Nome>.txt         (testo pulito, per altri LLM)
    │   ├── <Nome>.json        (segmenti con timestamp, per RAG)
    │   └── <Nome>.pdf         (sempre, generato in automatico)
    ├── traduzioni/            (se l'audio non era in italiano)
    │   ├── <Nome>_it.md
    │   ├── <Nome>_it.txt
    │   ├── <Nome>_it.json     (sezioni tradotte, riusate da «Solo riassunto»)
    │   └── <Nome>_it.pdf
    ├── riassunti/             (riassunto pulito, per sezione)
    │   ├── <Nome>_riassunto.md
    │   ├── <Nome>_riassunto.txt
    │   └── <Nome>_riassunto.pdf
    └── analisi_visiva/        (se attivi l'analisi visiva: cosa si VEDE nel video)
        ├── <Nome>_visivo.md   (ogni fotogramma con il contenuto estratto)
        ├── <Nome>_visivo.json
        ├── <Nome>_visivo.pdf  (fotogramma + testo, uno per nota)
        └── frames/            (i fotogrammi salvati, usati anche nel riassunto)
```

> Per i **file locali** `<Nome>` è il nome del file (senza estensione); per i video YouTube è il titolo. In **batch** ogni file produce la sua cartella `results/<nome file>/`. Le cartelle `traduzioni/`, `riassunti/` e `analisi_visiva/` compaiono solo quando quei passaggi vengono eseguiti.

### Perché tre (anzi quattro) formati e a cosa servono

Non è ridondanza: ogni formato risolve un bisogno diverso, così non sei costretto a riconvertire il testo a mano.

- **`.md` (Markdown)** → **leggere e pubblicare**. I minutaggi compaiono **solo nei titoli di sezione**, il corpo è prosa scorrevole: perfetto da aprire in un editor, su GitHub, Notion o Obsidian, con i capitoli già come intestazioni.
- **`.txt` (testo puro)** → **darlo in pasto a un altro LLM**. Niente timestamp né formattazione: il modo più pulito per **incollarlo in ChatGPT/Claude** ("fammi domande su questo", "spiegamelo"), per la ricerca full-text o per gli script.
- **`.json` (strutturato)** → **RAG e uso programmatico**. Contiene metadati + capitoli + **tutti i segmenti con timestamp**: è già pronto per il *chunking*, l'indicizzazione in un vector DB e per ricostruire "a che minuto è stato detto X".
- **`.pdf`** → **lettura comoda offline**. Impaginato e diviso per capitoli: da leggere sul tablet, annotare o stampare.

> Lo stesso vale per **traduzione** e **riassunto**: vengono salvati negli stessi formati, così puoi leggere il riassunto in PDF, incollarne il `.txt` in un altro modello o indicizzarlo.

---

## 📄 Esportazione PDF

Il **PDF viene generato sempre, in automatico** — per trascrizione, traduzione e riassunto, **diviso per capitoli**. EchoScript usa **due strategie**, con ripiego automatico:

- 📐 **PDF "ricco" (preferito).** Quando il contenuto contiene **formule**, **mappe concettuali** o **fotogrammi** (analisi visiva), il PDF viene impaginato con un **browser Chromium già presente sul sistema** (Edge su Windows): le **formule LaTeX** sono renderizzate (MathJax), le **mappe** disegnate (Mermaid) e i **fotogrammi** mostrati nel testo. **Nessun LaTeX da installare**; le due librerie JS si scaricano una sola volta in cache locale (poi funziona anche **offline**). Disattivabile con `ECHOSCRIPT_RICH_PDF=0`.
- 📄 **PDF base (ripiego).** Se non c'è un browser disponibile (o per scelta), si usa `fpdf2` (pure-python, font Arial per gli accenti): testo semplice, sempre disponibile e offline. In questo caso formule e mappe restano come testo grezzo: per la resa "bella" apri il `.md`.

---

## 🌐 Traduzione automatica

> ℹ️ Traduzione e riassunto sono disponibili sia nella **CLI** (`transcriber.py`) sia nella **GUI** (gli interruttori della card "Output aggiuntivi"), con lo stesso motore condiviso.

Dopo la trascrizione, se l'audio **non è già in italiano**, EchoScript lo **traduce in italiano** (in automatico nella CLI; attivando l'interruttore nella GUI) (se è già in italiano, salta il passaggio: tradurre `it → it` sarebbe inutile).

- **Due motori, scelti in automatico.** Se hai una **chiave Groq** la traduzione usa **Google Translate** (libreria `deep-translator`): gratis, nessuna API key dedicata, **nessun credito Groq speso**. **Senza chiave**, in locale, traduce con **Ollama sul tuo PC** così resta **100% offline** (serve Ollama avviato col modello scaricato, lo stesso del riassunto). La scelta segue quella del riassunto: niente chiave → tutto in locale.
- La trascrizione resta intatta; la traduzione finisce in `traduzioni/` come file separati `.md`/`.txt`/`.pdf`, **senza minutaggi** (testo continuo, più leggibile).

### Come viene risolto il problema dei video lunghi (a blocchi)

I servizi di traduzione accettano solo un **numero limitato di caratteri per richiesta** (~5.000 per Google). La trascrizione di un video di 1-2 ore è molto più lunga e supererebbe il limite. La soluzione è il **chunking** (divisione a blocchi):

1. il testo viene **spezzato in blocchi da ~4.500 caratteri**, tagliando **sui confini di frase** (dopo `.`/`?`/`!`) per non spezzare le frasi a metà;
2. ogni blocco viene tradotto singolarmente;
3. i blocchi tradotti vengono **ricuciti** nell'ordine originale.

Così un testo di qualsiasi lunghezza passa senza errori. Se una singola frase fosse mostruosamente lunga viene tagliata a forza per stare nel limite, e se un blocco fallisce **non blocca tutto** (per quel pezzo si tiene l'originale come fallback).

---

## 🧠 Riassunto automatico

Dopo la traduzione (o, se l'audio era già in italiano, sulla **trascrizione originale**), EchoScript genera un **riassunto pulito** del testo, salvato in `riassunti/` nei soliti formati `.md`/`.txt`/`.pdf`.

> ✨ **Parole chiave in grassetto.** Il riassunto evidenzia in **grassetto** i concetti centrali, i termini tecnici, i nomi e le cifre rilevanti (con parsimonia, mai intere frasi), per aiutare la lettura. Il grassetto si vede in `.md` e nel **PDF**; nel `.txt` (pensato per altri strumenti/LLM) i marcatori vengono rimossi per restare testo piano.

### Perché serve anche un riassunto

Una trascrizione è **parlato grezzo messo per iscritto**: per sua natura contiene "rumore" che rende la lettura faticosa e poco utile da studiare:

- **intercalari e riempitivi** ("ehm", "uhm", "cioè", "tipo", "no?", "allora"…);
- **ripetizioni** e giri di parole;
- **frasi interrotte** e **autocorrezioni** dell'oratore ("volevo dire… anzi no…");
- divagazioni e pause di pensiero.

Il riassunto produce una versione **sintetica e ordinata** che **conserva i concetti, i dati, i nomi e gli esempi importanti** ma elimina il rumore. Soprattutto, è **per sezione**: se il video ha **capitoli**, ottieni **un riassunto per capitolo** (altrimenti un riassunto unico). Risultato: studi un video di un'ora in pochi minuti, mantenendo la trascrizione completa accanto per i dettagli.

### Quali modelli sono stati introdotti e perché

Riassumere non è trascrivere: serve un **LLM** (un modello di linguaggio), perché Whisper sa solo trasformare l'audio in testo, non rielaborarlo. EchoScript usa **due motori**, scelti in base al backend di trascrizione:

| Backend | Motore del riassunto | Modello (default) | Perché |
|---|---|---|---|
| ⚡ **Groq (cloud)** | API di chat Groq | `llama-3.3-70b-versatile` | Gira sui server Groq: puoi permetterti un modello **grande da 70B** → riassunti di qualità, **velocissimi**, con la chiave gratuita che usi già per la trascrizione |
| 🔒 **Locale** | **Ollama** (offline) | `qwen2.5:7b` | Resta **100% offline**. **Qwen 2.5 7B** è leggero (~4,7 GB), **veloce su CPU** e particolarmente bravo **in italiano** e nel seguire istruzioni strutturate (meglio di Llama 3.1 8B di pari taglia) |

> **Ollama** è il *programma* che fa girare il modello in locale (come un "lettore" per i modelli); **Qwen** è il *modello*. In locale serve installare Ollama una volta (https://ollama.com) e scaricare il modello: `ollama pull qwen2.5:7b`. Nessuna dipendenza pip aggiuntiva: EchoScript parla con Ollama via HTTP. Con **Groq** non serve nulla di tutto questo.

### Il problema dei video lunghi: map-reduce + contesto

Come per la traduzione, un testo molto lungo non entra in una sola richiesta (supera il **contesto** del modello). Qui la soluzione è il **map-reduce**:

1. **map** — se una sezione supera `SUMMARY_MAX_CHARS` (12.000 caratteri) viene divisa in blocchi, e **ogni blocco viene riassunto** singolarmente;
2. **reduce** — i riassunti parziali vengono **uniti e riassunti di nuovo** in un unico riassunto coerente della sezione.

In più, per il motore locale **alziamo la finestra di contesto di Ollama a 8.192 token** (`num_ctx`): di default Ollama ne usa solo 2.048 e **troncherebbe in silenzio** i blocchi lunghi, rovinando i riassunti dei video lunghi.

### Il prompt usato (identico per Groq e Ollama)

La qualità dipende dalle istruzioni date al modello. EchoScript invia sempre questo **prompt di sistema**:

```
Sei un editor esperto. Ricevi la trascrizione di una sezione di un video parlato
(testo in italiano). Trasformala in un riassunto chiaro, fedele e scorrevole,
sempre in italiano, seguendo queste regole:
- elimina intercalari e riempitivi (ehm, uhm, cioè, tipo, no?, allora, insomma)
  e le esitazioni;
- togli ripetizioni, frasi interrotte e autocorrezioni di chi parla, tenendo solo
  la versione corretta;
- CONSERVA tutti i concetti, i dati, i nomi propri e gli esempi importanti;
- NON aggiungere nulla che non sia nel testo e non inventare;
- struttura: da 3 a 6 punti elenco concisi e, se utile, 1-2 frasi finali di sintesi.
Rispondi SOLO con il riassunto, senza preamboli né commenti.
```

Al modello viene poi passato il **titolo della sezione** (se il video ha capitoli) e il testo da riassumere, con `temperature=0.3` per un output fedele e poco "creativo".

### Su un video già trascritto (rigenerare senza rispendere)

Se trascrivi di nuovo un video **già presente** in `results/`, la CLI mostra un pannello con cui scegli **cosa rigenerare**, senza per forza ripartire da zero:

| Opzione | Cosa fa |
|---|---|
| 🔁 **Ritrascrivi tutto** | rifà da capo trascrizione + traduzione + riassunto |
| 🌐 **Traduzione + riassunto** | riusa la trascrizione salvata, la traduce e la riassume (**nessun credito di trascrizione**) |
| 🧠 **Solo riassunto** | genera **soltanto** il riassunto dal testo già salvato (la **traduzione** se presente, altrimenti l'originale) |
| 🎙 **Ritrascrivi soltanto** | rifà solo la trascrizione, senza traduzione né riassunto |
| ⏭ **Salta** | non fa nulla per quel video |

> Per riusare la traduzione, «Solo riassunto» rilegge `traduzioni/<Nome>_it.json` (salvato insieme alla traduzione). Se quel file non c'è (traduzioni vecchie), riassume la trascrizione originale.

> ⏱️ **Tempi.** Con Groq il riassunto è quasi istantaneo. In locale su **CPU** può richiedere qualche minuto per i video lunghi (con **GPU** crolla a pochi secondi: Ollama la usa in automatico se presente). Tutto è configurabile da `.env` (modello, host, contesto, soglia map-reduce).

---

## 👁️ Analisi visiva del video

> ℹ️ Disponibile sia nella **CLI** sia nella **GUI** (interruttore "Analisi visiva del video" nella card "Output aggiuntivi"). È **opzionale** e viene proposta solo quando la sorgente è un **video** (YouTube o file video locale): un mp3 non ha fotogrammi.

### A cosa serve

In molti video il valore **non è solo in ciò che si sente, ma in ciò che si vede**: un tutorial di programmazione mostra **codice** a schermo, una lezione di matematica scrive **formule e dimostrazioni**, un video tecnico mostra **grafici, diagrammi, tabelle, slide**. La sola trascrizione dell'audio **perde tutto questo**: chi parla dice *"come vedete qui"*, ma "qui" nel testo non c'è.

L'**analisi visiva** aggiunge un secondo "occhio" al tool: oltre a *trascrivere l'audio*, **guarda i fotogrammi** del video ed estrae il contenuto a schermo, integrandolo **nel riassunto** e in un **documento dedicato** con i fotogrammi accanto a ciò che mostrano.

```
video ──┬─► [audio]  ─► trascrizione (Groq/whisper)  ──┐
        │                                               ├─► RIASSUNTO (fuso per timestamp)
        └─► [frame]  ─► analisi visiva (modello vision) ┘
```

### Come funziona (in 4 passi)

1. **Estrazione intelligente dei fotogrammi.** Non si analizzano tutti i frame (sarebbero decine di migliaia): si usa il **rilevamento dei cambi di scena** di ffmpeg per catturare un fotogramma **quando l'immagine cambia davvero** — una nuova slide, un nuovo blocco di codice, una nuova formula. Sui video statici (un'unica inquadratura) si ripiega su un **campionamento a intervalli** adattivo. I quasi-duplicati vengono scartati e c'è un **tetto massimo** di fotogrammi, per tenere sotto controllo costo e tempo.
2. **Lettura con un modello "vision".** Ogni fotogramma viene letto da un **modello multimodale** con un prompt mirato: *trascrivi alla lettera il codice (indicando il linguaggio), scrivi le formule in LaTeX con i passaggi, descrivi grafici e diagrammi, riporta il testo delle slide*. I fotogrammi "vuoti" (un volto che parla, una transizione) vengono **scartati**. Due motori, come per trascrizione e riassunto: **Groq** (cloud) o **Ollama** (locale, offline).
3. **Fusione per timestamp.** Le "note visive" estratte vengono **interlacciate con il parlato** sulla linea temporale, così il modello del riassunto vede *"al minuto 4:12 si dice X **mentre a schermo c'è questo codice/formula**"*.
4. **Integrazione nel riassunto + documento dedicato.** Il riassunto incorpora il **codice** in blocchi, le **formule** in LaTeX e i **fotogrammi** raggruppati per sezione. In più viene salvato il documento `analisi_visiva/` con **ogni fotogramma accanto al contenuto estratto**.

### Perché così (e non un'"immagine generata")

Per il contenuto tecnico vale una regola: **estrai, non immaginare**. Un modello generativo (text-to-image) "ridisegnerebbe" il grafico inventando valori ed etichette. Invece:

- per il **codice**, la riproduzione fedele è la **trascrizione alla lettera** (già pronta da copiare ed eseguire), e il **fotogramma allegato** fa da prova: verifichi a colpo d'occhio se il modello ha sbagliato un carattere;
- per **grafici e disegni**, la riproduzione più fedele in assoluto è **il fotogramma stesso** — i pixel originali — che il tool ti mostra accanto alla spiegazione.

### Cosa ottieni

Una nuova sottocartella `analisi_visiva/` con:

- `<Nome>_visivo.md` e `.json` — le note estratte con i loro timestamp;
- `<Nome>_visivo.pdf` — **ogni fotogramma con accanto il suo contenuto** (codice, formula, descrizione del grafico);
- `frames/` — i fotogrammi salvati.

E nel **riassunto** trovi il codice e le formule integrati nel testo, con i fotogrammi raggruppati per sezione.

### Costo, requisiti e limiti (in chiaro)

- **Costo.** L'analisi visiva è la parte **più pesante**: le immagini "costano" molti token. Su **Groq** consuma più crediti del resto (in dollari resta bassa — pochi centesimi a video — ma sul **piano gratuito** ne limita il numero giornaliero). In **locale** con Ollama è **gratis e offline**, solo più lenta e richiede un modello vision installato (`ollama pull llama3.2-vision`).
- **Mostrare i fotogrammi costa zero**: il costo è solo la *lettura* dei frame; allegarli e impaginarli nel PDF è tutto locale.
- **Limiti onesti.** Il codice è "quasi sempre giusto", ma un singolo carattere errato lo romperebbe: il fotogramma allegato serve proprio a controllare. Il codice che **scorre** su più schermate non viene ancora ricucito in un unico file.

### Configurazione

Tutto regolabile da `.env`: `ECHOSCRIPT_GROQ_VISION_MODEL`, `ECHOSCRIPT_OLLAMA_VISION_MODEL`, `ECHOSCRIPT_VISION_SCENE` (sensibilità ai cambi di scena), `ECHOSCRIPT_VISION_MAX_FRAMES` (tetto fotogrammi), `ECHOSCRIPT_SUMMARY_FRAMES` (fotogrammi nel riassunto), `ECHOSCRIPT_CONCEPT_MAP` (mappa concettuale Mermaid nel riassunto, **disattivata** di default).

---

## 🛠️ Configurazione

Tutte le "manopole" si impostano da variabili d'ambiente / file `.env` (vedi
il file `.env`), senza toccare il codice. Ogni valore ha un default sensato:

| Variabile `.env` | Default | Descrizione |
|---|---|---|
| `GROQ_API_KEY` | — | Chiave Groq (solo per la trascrizione cloud) |
| `ECHOSCRIPT_GROQ_MODEL` | `whisper-large-v3-turbo` | Modello Whisper su Groq (turbo = veloce/economico) |
| `ECHOSCRIPT_AUDIO_LANG` | *(vuoto)* | Lingua dell'audio: vuoto = autorileva; forza con `it` / `en` / … |
| `ECHOSCRIPT_WORD_TIMESTAMPS` | `1` | Timestamp a livello di parola (utili per sottotitoli) |
| `ECHOSCRIPT_CHUNK_SECONDS` | `600` | Durata di ogni blocco audio (solo Groq) |
| `ECHOSCRIPT_DEVICE` | `auto` | Backend locale: `auto` (GPU se c'è) / `cpu` / `cuda` |
| `ECHOSCRIPT_COMPUTE_TYPE` | *(auto)* | Precisione locale: vuoto = `float16` su GPU, `int8` su CPU |
| `ECHOSCRIPT_GROQ_SUMMARY_MODEL` | `llama-3.3-70b-versatile` | Modello di **chat Groq** per il riassunto (cloud) |
| `ECHOSCRIPT_OLLAMA_MODEL` | `qwen2.5:7b` | Modello **Ollama** per il riassunto in locale |
| `ECHOSCRIPT_OLLAMA_TRANSLATE_MODEL` | *(= `OLLAMA_MODEL`)* | Modello **Ollama** per la **traduzione** in locale (di default lo stesso del riassunto) |
| `ECHOSCRIPT_OLLAMA_HOST` | `http://localhost:11434` | Indirizzo del server Ollama |
| `ECHOSCRIPT_OLLAMA_NUM_CTX` | `8192` | Finestra di contesto Ollama (evita il troncamento sui blocchi lunghi) |
| `ECHOSCRIPT_SUMMARY_MAX_CHARS` | `12000` | Soglia oltre cui una sezione viene riassunta a blocchi (map-reduce) |
| `ECHOSCRIPT_GROQ_VISION_MODEL` | `qwen/qwen3.6-27b` | Modello **vision** su Groq (analisi visiva, cloud) |
| `ECHOSCRIPT_OLLAMA_VISION_MODEL` | `llama3.2-vision` | Modello **vision** su Ollama (analisi visiva, locale) |
| `ECHOSCRIPT_VISION_SCENE` | `0.4` | Soglia di cambio scena per scegliere i fotogrammi (più basso = più fotogrammi) |
| `ECHOSCRIPT_VISION_MAX_FRAMES` | `60` | Tetto massimo di fotogrammi analizzati per video (costo/tempo) |
| `ECHOSCRIPT_SUMMARY_FRAMES` | `1` | Mostra i fotogrammi anche nel riassunto (0 = solo nel documento dedicato) |
| `ECHOSCRIPT_CONCEPT_MAP` | `0` | Mappa concettuale Mermaid nel riassunto (disattivata di default) |
| `ECHOSCRIPT_RICH_PDF` | `1` | PDF "ricco" con formule/mappe/frame via browser (0 = solo fpdf2) |

> **Traduzione e riassunto in locale.** Senza chiave Groq, **sia la traduzione sia
> il riassunto** girano in locale: serve [Ollama](https://ollama.com) installato e
> avviato, con il modello scaricato (`ollama pull qwen2.5:7b`). Con il backend
> **Groq** usano invece la chiave che hai già (Google Translate + Groq), senza
> installare altro.

> **GPU automatica.** Il backend locale usa la GPU (CUDA) se disponibile,
> altrimenti la CPU. Installa PyTorch con CUDA per l'accelerazione (vedi
> `requirements.txt`).

---

## 🔒 Privacy

- **Backend locale (faster-whisper)**: l'**audio non lascia mai il tuo PC**. (Al primo uso scarica solo i *pesi* del modello da HuggingFace.) Massima privacy.
- **Backend Groq**: l'audio viene **caricato sui server Groq** per la trascrizione. Ottimo per video pubblici, sconsigliato per audio privati/sensibili.
- **Traduzione**: con una **chiave Groq** usa **Google Translate** (il testo va ai server di Google); **senza chiave**, in locale, traduce con **Ollama sul tuo PC** → **100% offline**.
- **Riassunto**: con il backend **Groq** il testo va ai server Groq; con il backend **locale** usa **Ollama sul tuo PC**, quindi **resta 100% offline** (niente lascia il computer).

> 🔒 **Offline totale.** Con il **backend locale e senza chiave Groq** l'intera pipeline — trascrizione, traduzione e riassunto — gira **sul tuo PC**: nessun dato lascia il computer. Servono [Ollama](https://ollama.com) installato e avviato e il modello scaricato (`ollama pull qwen2.5:7b`), usati sia per la traduzione sia per il riassunto.

La **API key** non è mai scritta nel codice: si legge da `.env` o da variabile d'ambiente, ed è esclusa dal versionamento tramite `.gitignore`.

---

## 💬 Feedback

In caso di miglioramenti o suggerimenti, scrivete pure: ogni idea, segnalazione
di bug o proposta è benvenuta. Aprite una **issue** su GitHub oppure lasciate un
commento — il progetto cresce anche grazie ai vostri riscontri.

---

## ⚖️ Note legali

EchoScript scarica l'audio da YouTube per trascriverlo. L'uso potrebbe essere soggetto ai **Termini di Servizio** di YouTube e alle norme sul **diritto d'autore** della tua giurisdizione. È pensato per uso **personale ed educativo** (es. studiare un video leggendolo): usalo in modo responsabile e solo per contenuti di cui hai i diritti o per fini di studio personale.

---

## 📄 Licenza

Rilasciato sotto licenza **MIT**.

---

<div align="center">
🇬🇧 <a href="README_eng.md">Read this in English</a>
</div>
