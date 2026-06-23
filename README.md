<div align="center">

# 🎙️ EchoScript

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Groq-Whisper-F55036?logo=groq&logoColor=white" alt="Groq">
  <img src="https://img.shields.io/badge/faster--whisper-locale-0A9396?logo=openai&logoColor=white" alt="faster-whisper">
  <img src="https://img.shields.io/badge/Rich-TUI-4EC820?logo=windowsterminal&logoColor=white" alt="Rich">
  <img src="https://img.shields.io/badge/yt--dlp-downloader-FF0000?logo=youtube&logoColor=white" alt="yt-dlp">
  <img src="https://img.shields.io/badge/fpdf2-PDF-EC1C24?logo=adobeacrobatreader&logoColor=white" alt="fpdf2">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

<p align="center">
  Trascrivi (e <b>traduci</b>) i video YouTube in <b>testo, Markdown, JSON, PDF e LaTeX</b>,<br>
  <b>velocemente</b> con Groq oppure <b>100% in locale</b> per la massima privacy.<br>
  Pensato per <b>studiare</b> video lunghi (RAG, fine-tuning, lezioni) leggendoli invece di guardarli per ore.<br>
  <b>Niente abbonamenti, niente limiti giornalieri, niente minutaggio ridotto.</b>
</p>

</div>

```bash
git clone https://github.com/Imkun-on/EchoScript.git
cd EchoScript
pip install -r requirements.txt
python transcriber.py
```

---

## Indice

- [📋 Descrizione del progetto](#-descrizione-del-progetto)
- [🆚 Perché EchoScript e non i soliti "tool gratis"](#-perché-echoscript-e-non-i-soliti-tool-gratis)
- [🔀 I due backend: cloud o locale](#-i-due-backend-cloud-o-locale)
- [✨ Caratteristiche](#-caratteristiche)
- [📦 Installazione](#-installazione)
- [🔑 Come ottenere una API key Groq](#-come-ottenere-una-api-key-groq)
- [📚 Librerie usate e perché](#-librerie-usate-e-perché)
- [🚀 Uso ed esempi](#-uso-ed-esempi)
- [⚙️ Come funziona (le fasi)](#️-come-funziona-le-fasi)
- [💾 Struttura dei file di output](#-struttura-dei-file-di-output)
- [🌐 Traduzione in italiano](#-traduzione-in-italiano)
- [📄 Esportazione PDF / LaTeX](#-esportazione-pdf--latex)
- [🛠️ Configurazione](#️-configurazione)
- [🔒 Privacy](#-privacy)
- [⚖️ Note legali](#️-note-legali)
- [📄 Licenza](#-licenza)

---

## 📋 Descrizione del progetto

**EchoScript** è uno strumento da terminale che trasforma un video YouTube in **testo scritto**, ordinato e pronto da leggere o da dare in pasto ad altri strumenti.

L'idea nasce da un bisogno concreto: i video formativi (su **RAG**, **fine-tuning**, lezioni, talk) spesso durano **1-2 ore**, e non sempre si ha il tempo o la concentrazione di seguirli tutti. EchoScript li **trascrive** usando i **capitoli** del video come sezioni, così puoi *leggere* il contenuto in pochi minuti, cercarlo, evidenziarlo, o usarlo come base di conoscenza.

Puoi scegliere **come** trascrivere:

- ⚡ **Groq (cloud)**: velocissimo anche **senza GPU** (trascrive 2 ore in pochi secondi), praticamente gratis.
- 🔒 **Locale (faster-whisper su CPU)**: **100% offline e privato**, l'audio non lascia mai il tuo PC.

A fine trascrizione puoi **tradurre in italiano** (utile per i video in inglese) ed **esportare in PDF e LaTeX** per leggerli comodamente, divisi per capitoli.

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
| **Formati di output** | spesso solo `.txt` | `.md`, `.txt`, `.json`, **`.pdf`**, **`.tex`** + **traduzione IT** |
| **Funziona offline** | no | **sì** (backend locale) |
| **Open source** | quasi mai | **sì** |

In breve: **lo controlli tu**, gira sul **tuo computer**, e non ti chiede nulla a sorpresa.

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

- 🔀 **Due backend** selezionabili da pannello: Groq (cloud, veloce) o faster-whisper (locale, privato)
- 📋 **Scheda video** prima di partire (titolo, canale, visualizzazioni, data, durata, numero di capitoli)
- ✅ **Conferma** prima di trascrivere
- ⬇️ **Download solo audio** (leggero) con barra di avanzamento (velocità + tempo stimato)
- ⏱️ **Minutaggi e sezioni**: usa i **capitoli** di YouTube come sezioni del documento
- 💾 **3 formati base** sempre generati: `.md` (umano), `.txt` (per altri LLM), `.json` (per RAG)
- 🌐 **Traduzione in italiano** opzionale (via LLM Groq) in file separati e puliti
- 📄 **Export PDF + LaTeX** opzionale, diviso per capitoli (anche della versione tradotta)
- 🗂️ **Output organizzato** in `results/<nome video>/` con sottocartelle `trascrizioni/` e `traduzioni/`
- 🎨 **Interfaccia curata** (Rich): banner, schede, pannelli, barre con tempo trascorso/stimato
- 🔑 **Gestione chiave sicura**: variabile d'ambiente o file `.env` (mai nel codice)
- 🧯 **Errori chiari**: la chiave viene validata all'avvio; niente retry inutili su errori di autenticazione

---

## 📦 Installazione

### Requisiti

- **Python 3.9+**
- **[ffmpeg](https://ffmpeg.org)** installato nel sistema (serve a yt-dlp e alla preparazione audio)
- *(solo per Groq)* una **API key Groq** gratuita (vedi sotto)
- *(solo per il backend locale)* `faster-whisper`
- *(solo per l'export PDF)* `fpdf2`

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

> ⭐ **File da lanciare:** il programma si avvia **sempre** da `transcriber.py`.

---

## 🔑 Come ottenere una API key Groq

La chiave serve **solo** se usi il backend **Groq** (cloud) o la **traduzione** in italiano. È **gratuita**.

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
| `groq` | Client ufficiale dell'API Groq (Whisper + LLM per la traduzione) | SDK ufficiale, semplice e veloce |
| `rich` | Interfaccia da terminale: pannelli, tabelle, barre, colori | Trasforma la CLI in un'esperienza curata (`Panel`, `Progress`, `Columns`) |
| `faster-whisper` | *(opzionale)* Trascrizione **locale** su CPU | Implementazione ottimizzata di Whisper (CTranslate2), ottima su CPU con `int8` |
| `fpdf2` | *(opzionale)* Esportazione in **PDF** | Pure-python, **niente LaTeX di sistema**; supporta font Unicode |

### Libreria standard (nessuna installazione)

`os`, `re`, `json`, `sys`, `signal`, `shutil`, `tempfile`, `subprocess`, `datetime`: percorsi/file, regex, JSON, gestione Ctrl+C, chiamate a ffmpeg/ffprobe, date.

> Il **LaTeX** (`.tex`) viene generato direttamente, senza dipendenze. La **traduzione** usa l'LLM di Groq (già incluso nel pacchetto `groq`).

---

## 🚀 Uso ed esempi

Avvia il programma:

```bash
python transcriber.py
```

Flusso tipico:

1. **Scegli il backend** (1 = Locale · 2 = Groq).
2. *(se locale)* **Scegli il modello** (1-5).
3. **Incolla l'URL** del video YouTube.
4. Controlla la **scheda del video** e **conferma**.
5. Attendi: vedrai le fasi **Download → Preparazione → Trascrizione** con barre di avanzamento.
6. Rispondi se vuoi **tradurre in italiano** e se vuoi **esportare in PDF/LaTeX**.
7. Trovi tutto in `results/<nome video>/`.

### Esempio: backend Groq

```
─────────────── Come vuoi trascrivere? ───────────────
┌─ 1  🔒 Locale ──────────────┐  ┌─ 2  ⚡ Groq (cloud) ────────┐
│  ✓ privacy totale: resta... │  │  ✓ velocissimo, anche...    │
│  ✗ più lento (nessuna GPU)  │  │  ✗ niente privacy: cloud    │
│  • per audio privati        │  │  • per video pubblici       │
└─────────────────────────────┘  └─────────────────────────────┘

› Scelta (1 = Locale · 2 = Groq · q = annulla): 2

› Incolla l'URL del video YouTube (q per uscire): https://www.youtube.com/watch?v=...

┌─ 🎬 RAG è già vecchio? ... ──────────────────────┐
│  📺  Canale           Simone Rizzo               │
│  👁  Visualizzazioni  49.586                     │
│  📅  Pubblicato       21/04/2026                 │
│  ⏱  Durata           43:09                       │
│  📑  Capitoli         21 sezioni                 │
└──────────────────────────────────────────────────┘

› Procedo con la trascrizione di questo video? (s/n): s

──── ⬇ Fase 1/3 — Download audio ────
──── ✂ Fase 2/3 — Preparazione audio ────
──── ✎ Fase 3/3 — Trascrizione (Groq) ────
```

### Caso d'uso: costruire un RAG dai video

Trascrivi i video di studio, poi usa i file **`.json`** (segmenti con timestamp) come fonte per la tua pipeline RAG: sono già pronti per il *chunking* e l'indicizzazione.

### Caso d'uso: leggere un talk inglese in italiano

Trascrivi un talk in inglese, scegli **traduzione in italiano** ed **export PDF**: ottieni un PDF pulito in italiano, diviso per capitoli, da leggere sul tablet o stampare.

---

## ⚙️ Come funziona (le fasi)

1. **Info**: con una chiamata leggera (`yt-dlp`) si leggono SOLO i metadati (titolo, canale, durata, **capitoli**), senza scaricare nulla.
2. **Download audio**: si scarica la sola traccia audio (leggera) con barra di avanzamento.
3. **Preparazione** *(solo Groq)*: l'audio viene riconvertito a 16 kHz mono e **spezzato in blocchi da ~10 min** (per stare nei limiti di dimensione dell'API e avere una barra sensata).
4. **Trascrizione**: ogni blocco (Groq) o l'intero file (locale) viene trascritto in **segmenti con timestamp**; i minutaggi di ogni blocco vengono corretti rispetto all'intero video.
5. **Assemblaggio**: i segmenti vengono raggruppati per **capitolo** (se presenti) e salvati nei vari formati.
6. **Traduzione / Export**: opzionali, su richiesta.

---

## 💾 Struttura dei file di output

```
results/
└── <Nome Video>/
    ├── trascrizioni/
    │   ├── <Nome Video>.md      (sezioni con minutaggio nel titolo, prosa pulita)
    │   ├── <Nome Video>.txt     (testo pulito, per altri LLM)
    │   ├── <Nome Video>.json    (segmenti con timestamp, per RAG)
    │   ├── <Nome Video>.tex     (solo se esporti)
    │   └── <Nome Video>.pdf     (solo se esporti)
    └── traduzioni/              (solo se traduci)
        ├── <Nome Video>.md      (italiano, senza minutaggi)
        ├── <Nome Video>.txt
        ├── <Nome Video>.tex
        └── <Nome Video>.pdf
```

- **`.md`**: leggibile dall'uomo: i minutaggi compaiono **solo nei titoli di sezione**, il corpo è prosa scorrevole.
- **`.txt`**: testo pulito senza timestamp: ideale da **incollare in un altro LLM** (ChatGPT/Claude).
- **`.json`**: metadati + capitoli + **tutti i segmenti con timestamp**: perfetto per una pipeline **RAG**.

---

## 🌐 Traduzione in italiano

A fine trascrizione, se confermi, EchoScript traduce il testo in italiano usando un **LLM su Groq** (`llama-3.3-70b-versatile`), ottimo sui termini tecnici (RAG, fine-tuning, embedding...). I video lunghi vengono tradotti **sezione per sezione** per non superare i limiti del modello.

- I file tradotti finiscono nella sottocartella **`traduzioni/`**.
- Sono **puliti**, **senza minutaggi** (versione comoda da leggere).
- L'**originale resta intatto**.

> La traduzione usa Groq (cloud): se hai trascritto in locale, EchoScript ti **avvisa** prima di inviare il testo.

---

## 📄 Esportazione PDF / LaTeX

A fine trascrizione, se confermi, EchoScript genera:

- **`.pdf`**: tramite `fpdf2` (pure-python, **niente LaTeX da installare**, font Arial per gli accenti), **diviso per capitoli**.
- **`.tex`**: documento **LaTeX** con `\section` per capitolo, da compilare dove vuoi (Overleaf, MiKTeX, TeX Live).

Se hai creato anche la versione tradotta, vengono esportati anche **`.it`** … cioè i file nella cartella `traduzioni/`.

---

## 🛠️ Configurazione

Le "manopole" principali sono costanti in cima a `transcriber.py`:

| Costante | Default | Descrizione |
|---|---|---|
| `GROQ_MODEL` | `whisper-large-v3-turbo` | Modello Whisper su Groq (turbo = veloce/economico) |
| `GROQ_TRANSLATE_MODEL` | `llama-3.3-70b-versatile` | LLM usato per la traduzione |
| `CHUNK_SECONDS` | `600` | Durata di ogni blocco audio (solo Groq) |
| `AUDIO_SAMPLE_RATE` | `16000` | 16 kHz, consigliato per Whisper |
| `LANGUAGE` | `None` | `None` = autorileva; forza con `"it"` / `"en"` |
| `LOCAL_COMPUTE_TYPE` | `int8` | Quantizzazione per il backend locale (più veloce su CPU) |
| `TRANSLATE_MAX_CHARS` | `2500` | Lunghezza max dei pezzi tradotti per chiamata |

---

## 🔒 Privacy

- **Backend locale (faster-whisper)**: l'**audio non lascia mai il tuo PC**. (Al primo uso scarica solo i *pesi* del modello da HuggingFace.) Massima privacy.
- **Backend Groq**: l'audio viene **caricato sui server Groq** per la trascrizione. Ottimo per video pubblici, sconsigliato per audio privati/sensibili.
- **Traduzione**: usa Groq, quindi il testo viene inviato ai loro server (con avviso se hai trascritto in locale).

La **API key** non è mai scritta nel codice: si legge da `.env` o da variabile d'ambiente, ed è esclusa dal versionamento tramite `.gitignore`.

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
