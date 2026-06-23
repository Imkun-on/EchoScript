<div align="center">

# 🎙️ EchoScript

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Groq-Whisper-F55036?logo=groq&logoColor=white" alt="Groq">
  <img src="https://img.shields.io/badge/faster--whisper-local-0A9396?logo=openai&logoColor=white" alt="faster-whisper">
  <img src="https://img.shields.io/badge/Rich-TUI-4EC820?logo=windowsterminal&logoColor=white" alt="Rich">
  <img src="https://img.shields.io/badge/yt--dlp-downloader-FF0000?logo=youtube&logoColor=white" alt="yt-dlp">
  <img src="https://img.shields.io/badge/fpdf2-PDF-EC1C24?logo=adobeacrobatreader&logoColor=white" alt="fpdf2">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

<p align="center">
  Transcribe (and <b>translate</b>) YouTube videos into <b>text, Markdown, JSON, PDF and LaTeX</b>,<br>
  <b>fast</b> with Groq or <b>100% locally</b> for maximum privacy.<br>
  Built to <b>study</b> long videos (RAG, fine-tuning, lectures) by reading them instead of watching for hours.<br>
  <b>No subscriptions, no daily limits, no reduced minutes.</b>
</p>

</div>

```bash
git clone https://github.com/Imkun-on/EchoScript.git
cd EchoScript
pip install -r requirements.txt
python transcriber.py
```

> 🇮🇹 The app's interface is in **Italian**; this README is the English documentation. For the Italian README see [README.md](README.md).

---

## Table of Contents

- [📋 Project description](#-project-description)
- [🆚 Why EchoScript instead of the usual "free" tools](#-why-echoscript-instead-of-the-usual-free-tools)
- [🔀 The two backends: cloud or local](#-the-two-backends-cloud-or-local)
- [✨ Features](#-features)
- [📦 Installation](#-installation)
- [🔑 How to get a Groq API key](#-how-to-get-a-groq-api-key)
- [📚 Libraries used and why](#-libraries-used-and-why)
- [🚀 Usage & examples](#-usage--examples)
- [⚙️ How it works (the phases)](#️-how-it-works-the-phases)
- [💾 Output file structure](#-output-file-structure)
- [🌐 Italian translation](#-italian-translation)
- [📄 PDF / LaTeX export](#-pdf--latex-export)
- [🛠️ Configuration](#️-configuration)
- [🔒 Privacy](#-privacy)
- [⚖️ Legal notice](#️-legal-notice)
- [📄 License](#-license)

---

## 📋 Project description

**EchoScript** is a terminal tool that turns a YouTube video into **written text**, neatly organized and ready to read or to feed into other tools.

The idea comes from a real need: educational videos (about **RAG**, **fine-tuning**, lectures, talks) are often **1–2 hours** long, and you don't always have the time or focus to watch them all. EchoScript **transcribes** them — using the video's **chapters** as sections — so you can *read* the content in minutes, search it, highlight it, or use it as a knowledge base.

You choose **how** to transcribe:

- ⚡ **Groq (cloud)** — extremely fast even **without a GPU** (transcribes 2 hours in seconds), practically free.
- 🔒 **Local (faster-whisper on CPU)** — **100% offline and private**: the audio never leaves your PC.

When the transcription is done you can **translate it into Italian** (handy for English videos) and **export to PDF and LaTeX** to read comfortably, split by chapter.

This tool is for:

- 🎓 **Students and self-learners** who'd rather read videos than watch them for hours
- 🧠 **Anyone building a RAG / knowledge base** from videos (the `.json` output already has timestamps ready for chunking)
- 🔐 **Privacy-conscious users** who want a fully offline transcription

---

## 🆚 Why EchoScript instead of the usual "free" tools

Many transcription websites and apps advertise themselves as "free", but then you discover that:
- after a few minutes they ask you to **pay** or to start a **subscription**;
- they impose a **daily limit** (e.g. 30 minutes/day) or a per-video **duration cap**;
- they block **long videos** (exactly the ones worth transcribing);
- they force you to **create an account**, add **watermarks**, or degrade quality;
- they upload your audio to **unknown servers**, with no privacy guarantees.

EchoScript was built to **remove all these traps**:

| | Typical "free" online tool | **EchoScript** |
|---|---|---|
| **Real cost** | free → then paywall / subscription | **truly free** locally · nearly free with Groq's free tier (your own key) |
| **Daily limit** | often a few minutes/day | **none** locally |
| **Max video length** | often 10–30 min | **2h+ videos** with no problem |
| **Account required** | yes | **no** (local); for Groq just a free key |
| **Watermark / reduced quality** | common | **never** |
| **Privacy** | upload to third-party servers | **local = nothing leaves your PC** |
| **Output formats** | often only `.txt` | `.md`, `.txt`, `.json`, **`.pdf`**, **`.tex`** + **Italian translation** |
| **Works offline** | no | **yes** (local backend) |
| **Open source** | rarely | **yes** |

In short: **you are in control**, it runs on **your computer**, and there are no surprises.

---

## 🔀 The two backends: cloud or local

On startup a panel lets you choose the transcription engine:

| Backend | Privacy | Speed (no GPU) | Cost | When to use |
|---|---|---|---|---|
| 🔒 **Local** (faster-whisper) | **Maximum**: audio stays on your PC | 🐢 Slower | **Free** | Private/sensitive audio, no limits |
| ⚡ **Groq** (cloud) | Audio goes to Groq's servers | ⚡ Very fast | Generous free tier | Public YouTube videos, when in a hurry |

If you choose **Local**, a second panel lets you pick the model each time:

| Model | Speed ↔ Accuracy |
|---|---|
| `base` | fast, less accurate |
| `small` ⭐ | recommended balance |
| `medium` | more accurate, slower |
| `large-v3` | maximum accuracy, very slow on CPU |
| `large-v3-turbo` | nearly "large" but faster |

> On first use of a local model, `faster-whisper` downloads its **weights** from HuggingFace (once). The **audio**, however, is never sent anywhere.

---

## ✨ Features

- 🔀 **Two backends** selectable from a panel: Groq (cloud, fast) or faster-whisper (local, private)
- 📋 **Video card** before you start (title, channel, views, date, duration, number of chapters)
- ✅ **Confirmation** before transcribing
- ⬇️ **Audio-only download** (lightweight) with a progress bar (speed + ETA)
- ⏱️ **Timings & sections**: uses YouTube **chapters** as document sections
- 💾 **3 base formats** always generated: `.md` (human), `.txt` (for other LLMs), `.json` (for RAG)
- 🌐 **Optional Italian translation** (via Groq LLM) in separate, clean files
- 📄 **Optional PDF + LaTeX export**, split by chapter (including the translated version)
- 🗂️ **Organized output** in `results/<video name>/` with `trascrizioni/` and `traduzioni/` subfolders
- 🎨 **Polished interface** (Rich): banner, cards, panels, bars with elapsed/remaining time
- 🔑 **Safe key handling**: environment variable or `.env` file (never in the code)
- 🧯 **Clear errors**: the key is validated at startup; no pointless retries on auth errors

---

## 📦 Installation

### Requirements

- **Python 3.9+**
- **[ffmpeg](https://ffmpeg.org)** installed on your system (needed by yt-dlp and audio preparation)
- *(Groq only)* a free **Groq API key** — see below
- *(local backend only)* `faster-whisper`
- *(PDF export only)* `fpdf2`

### Steps

```bash
git clone https://github.com/Imkun-on/EchoScript.git
cd EchoScript
pip install -r requirements.txt
python transcriber.py
```

Install **ffmpeg**:

```bash
# Windows
winget install Gyan.FFmpeg
# macOS
brew install ffmpeg
# Linux (Debian/Ubuntu)
sudo apt install ffmpeg
```

> ⭐ **Entry point:** always run the program via `transcriber.py`.

---

## 🔑 How to get a Groq API key

The key is needed **only** if you use the **Groq** (cloud) backend or the Italian **translation**. It is **free**.

1. Go to **https://console.groq.com** and **sign up** (you can use Google, GitHub or email).
2. Once inside, open the **API Keys** section: **https://console.groq.com/keys**
3. Click **"Create API Key"**, give it a name (e.g. `echoscript`) and **confirm**.
4. **Copy the key immediately** (it starts with `gsk_...`): it is shown **only once**.
5. Paste it into the project's **`.env`** file:
   ```
   GROQ_API_KEY=gsk_your-key-here
   ```
   Alternatively, set it as an environment variable:
   ```powershell
   # Windows (PowerShell) — then reopen the terminal
   setx GROQ_API_KEY "gsk_your-key-here"
   ```
   ```bash
   # macOS / Linux
   export GROQ_API_KEY="gsk_your-key-here"
   ```
6. Done! If you don't set it, the program will ask for it at startup (without saving it).

> 📊 **Free tier limits**: Groq enforces *rate limits* (requests per minute/day and audio seconds per hour/day). They are generous, but a single 2h video might approach the hourly limit: if so you get a `429` error and just need to wait. Check your limits at **https://console.groq.com/settings/limits**. If you want no limits at all, use the **local backend**.

> 🔐 The key is **secret**: the `.env` file is already in `.gitignore`, so it will **never** end up on GitHub.

---

## 📚 Libraries used and why

### External dependencies (pip)

| Library | What it's for | Why this one |
|---|---|---|
| `yt-dlp` | Downloads audio and metadata (title, chapters, duration) from YouTube | The de-facto standard: handles streams, resume, and metadata extraction |
| `groq` | Official Groq API client (Whisper + LLM for translation) | Official SDK, simple and fast |
| `faster-whisper` | *(optional)* **Local** transcription on CPU | Optimized Whisper implementation (CTranslate2), great on CPU with `int8` |
| `fpdf2` | *(optional)* **PDF** export | Pure-python, **no system LaTeX needed**; supports Unicode fonts |

### Standard library (no installation)

`os`, `re`, `json`, `sys`, `signal`, `shutil`, `tempfile`, `subprocess`, `datetime` — paths/files, regex, JSON, Ctrl+C handling, ffmpeg/ffprobe calls, dates.

> **LaTeX** (`.tex`) is generated directly, with no dependencies. **Translation** uses Groq's LLM (already included in the `groq` package).

---

## 🚀 Usage & examples

Run the program:

```bash
python transcriber.py
```

Typical flow:

1. **Pick the backend** (1 = Local · 2 = Groq).
2. *(if local)* **Pick the model** (1–5).
3. **Paste the YouTube URL**.
4. Check the **video card** and **confirm**.
5. Wait: you'll see the **Download → Preparation → Transcription** phases with progress bars.
6. Answer whether you want to **translate into Italian** and whether to **export to PDF/LaTeX**.
7. Find everything under `results/<video name>/`.

### Example — Groq backend

```
─────────────── Come vuoi trascrivere? ───────────────
┌─ 1  🔒 Locale ──────────────┐  ┌─ 2  ⚡ Groq (cloud) ────────┐
│  ✓ privacy totale: resta... │  │  ✓ velocissimo, anche...    │
│  ✗ più lento (nessuna GPU)  │  │  ✗ niente privacy: cloud    │
│  • per audio privati        │  │  • per video pubblici       │
└─────────────────────────────┘  └─────────────────────────────┘

› Scelta (1 = Locale · 2 = Groq · q = annulla): 2
› Incolla l'URL del video YouTube (q per uscire): https://www.youtube.com/watch?v=...
```

### Use case — build a RAG from videos

Transcribe your study videos, then use the **`.json`** files (segments with timestamps) as the source for your RAG pipeline: they're ready for *chunking* and indexing.

### Use case — read an English talk in Italian

Transcribe an English talk, choose **Italian translation** and **PDF export**: you get a clean PDF in Italian, split by chapter, to read on a tablet or print.

---

## ⚙️ How it works (the phases)

1. **Info** — a lightweight call (`yt-dlp`) reads ONLY the metadata (title, channel, duration, **chapters**), downloading nothing.
2. **Audio download** — only the audio track (lightweight) is downloaded, with a progress bar.
3. **Preparation** *(Groq only)* — the audio is re-encoded to 16 kHz mono and **split into ~10 min chunks** (to stay within the API size limit and give a meaningful bar).
4. **Transcription** — each chunk (Groq) or the whole file (local) is transcribed into **segments with timestamps**; each chunk's timings are corrected relative to the whole video.
5. **Assembly** — segments are grouped by **chapter** (if present) and saved in the various formats.
6. **Translation / Export** — optional, on request.

---

## 💾 Output file structure

```
results/
└── <Video Name>/
    ├── trascrizioni/           (transcriptions)
    │   ├── <Video Name>.md     (sections with timing in the heading, clean prose)
    │   ├── <Video Name>.txt    (clean text, for other LLMs)
    │   ├── <Video Name>.json   (segments with timestamps, for RAG)
    │   ├── <Video Name>.tex    (only if you export)
    │   └── <Video Name>.pdf    (only if you export)
    └── traduzioni/             (translations — only if you translate)
        ├── <Video Name>.md     (Italian, no timings)
        ├── <Video Name>.txt
        ├── <Video Name>.tex
        └── <Video Name>.pdf
```

- **`.md`** — human-readable: timings appear **only in section headings**, the body is flowing prose.
- **`.txt`** — clean text with no timestamps: ideal to **paste into another LLM** (ChatGPT/Claude).
- **`.json`** — metadata + chapters + **all segments with timestamps**: perfect for a **RAG** pipeline.

> Folder names are in Italian (`trascrizioni` = transcriptions, `traduzioni` = translations) to match the app's interface.

---

## 🌐 Italian translation

When the transcription is done, if you confirm, EchoScript translates the text into Italian using an **LLM on Groq** (`llama-3.3-70b-versatile`), which is great with technical terms (RAG, fine-tuning, embedding...). Long videos are translated **section by section** to stay within the model's limits.

- Translated files go into the **`traduzioni/`** subfolder.
- They are **clean**, **without timings** (a comfortable reading version).
- The **original stays intact**.

> Translation uses Groq (cloud): if you transcribed locally, EchoScript **warns you** before sending the text.

---

## 📄 PDF / LaTeX export

When the transcription is done, if you confirm, EchoScript generates:

- **`.pdf`** — via `fpdf2` (pure-python, **no LaTeX to install**, Arial font for accents), **split by chapter**.
- **`.tex`** — a **LaTeX** document with one `\section` per chapter, to compile wherever you like (Overleaf, MiKTeX, TeX Live).

If you also created the translated version, the files in `traduzioni/` are exported too.

---

## 🛠️ Configuration

The main "knobs" are constants at the top of `transcriber.py`:

| Constant | Default | Description |
|---|---|---|
| `GROQ_MODEL` | `whisper-large-v3-turbo` | Whisper model on Groq (turbo = fast/cheap) |
| `GROQ_TRANSLATE_MODEL` | `llama-3.3-70b-versatile` | LLM used for translation |
| `CHUNK_SECONDS` | `600` | Duration of each audio chunk (Groq only) |
| `AUDIO_SAMPLE_RATE` | `16000` | 16 kHz, recommended for Whisper |
| `LANGUAGE` | `None` | `None` = auto-detect; force with `"it"` / `"en"` |
| `LOCAL_COMPUTE_TYPE` | `int8` | Quantization for the local backend (faster on CPU) |
| `TRANSLATE_MAX_CHARS` | `2500` | Max length of translated pieces per call |

---

## 🔒 Privacy

- **Local backend (faster-whisper)**: the **audio never leaves your PC**. (On first use it only downloads the model *weights* from HuggingFace.) Maximum privacy.
- **Groq backend**: the audio is **uploaded to Groq's servers** for transcription. Great for public videos, not advised for private/sensitive audio.
- **Translation**: uses Groq, so the text is sent to their servers (with a warning if you transcribed locally).

The **API key** is never written in the code: it is read from `.env` or an environment variable, and excluded from version control via `.gitignore`.

---

## ⚖️ Legal notice

EchoScript downloads audio from YouTube to transcribe it. Its use may be subject to YouTube's **Terms of Service** and to the **copyright** rules of your jurisdiction. It is intended for **personal and educational** use (e.g. studying a video by reading it): use it responsibly and only for content you have the rights to, or for personal study.

---

## 📄 License

Released under the **MIT** license.
