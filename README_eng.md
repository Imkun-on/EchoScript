<div align="center">

# 🎙️ EchoScript

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Groq-Whisper-F55036?logo=groq&logoColor=white" alt="Groq">
  <img src="https://img.shields.io/badge/faster--whisper-local-0A9396?logo=openai&logoColor=white" alt="faster-whisper">
  <img src="https://img.shields.io/badge/Rich-TUI-4EC820?logo=windowsterminal&logoColor=white" alt="Rich">
  <img src="https://img.shields.io/badge/Flet-GUI-02569B?logo=flutter&logoColor=white" alt="Flet">
  <img src="https://img.shields.io/badge/yt--dlp-downloader-FF0000?logo=youtube&logoColor=white" alt="yt-dlp">
  <img src="https://img.shields.io/badge/fpdf2-PDF-EC1C24?logo=adobeacrobatreader&logoColor=white" alt="fpdf2">
  <img src="https://img.shields.io/badge/Google_Translate-translation-4285F4?logo=googletranslate&logoColor=white" alt="deep-translator">
  <img src="https://img.shields.io/badge/Ollama-local_summary-000000?logo=ollama&logoColor=white" alt="Ollama">
  <img src="https://img.shields.io/badge/Llama_3.3_·_Qwen_2.5-LLM-7C3AED" alt="LLM">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

<p align="center">
  Transcribe YouTube videos <b>and your local audio files</b> into <b>text, Markdown, JSON and PDF</b>,<br>
  then <b>translate</b> them to Italian and get a <b>clean summary</b> (no "uh/um", repetitions or self-corrections).<br>
  <b>Fast</b> with Groq or <b>100% locally</b> for maximum privacy.<br>
  Built to <b>study</b> long videos (RAG, fine-tuning, lectures) by reading them instead of watching for hours.<br>
  Available as a <b>desktop app</b> (GUI) or from the <b>terminal</b> (CLI).<br>
  <b>No subscriptions, no daily limits, no reduced minutes.</b>
</p>

</div>

```bash
git clone https://github.com/Imkun-on/EchoScript.git
cd EchoScript
pip install -r requirements.txt

python gui/main.py        # native desktop app (GUI)
python transcriber.py     # terminal interface (CLI)
```

> 🇮🇹 The app's interface is in **Italian**; this README is the English documentation. For the Italian README see [README.md](README.md).

---

## Table of Contents

- [📋 Project description](#-project-description)
- [🆚 Why EchoScript instead of the usual "free" tools](#-why-echoscript-instead-of-the-usual-free-tools)
- [🖥️ Two interfaces: GUI or terminal](#️-two-interfaces-gui-or-terminal)
- [🖱️ Desktop app guide (for everyone)](#️-desktop-app-guide-for-everyone)
- [🔀 The two backends: cloud or local](#-the-two-backends-cloud-or-local)
- [✨ Features](#-features)
- [⬇️ Download the ready-to-use app (.exe)](#️-download-the-ready-to-use-app-exe)
- [📦 Install from source (developers)](#-install-from-source-developers)
- [🔑 How to get a Groq API key](#-how-to-get-a-groq-api-key)
- [📚 Libraries used and why](#-libraries-used-and-why)
- [🚀 Usage & examples](#-usage--examples)
- [⚙️ How it works (the phases)](#️-how-it-works-the-phases)
- [💾 Output file structure](#-output-file-structure)
- [📄 PDF export](#-pdf-export)
- [🌐 Automatic translation](#-automatic-translation)
- [🧠 Automatic summary](#-automatic-summary)
- [🛠️ Configuration](#️-configuration)
- [🔒 Privacy](#-privacy)
- [⚖️ Legal notice](#️-legal-notice)
- [📄 License](#-license)

---

## 📋 Project description

**EchoScript** is a tool (**desktop app** or **terminal**) that turns a YouTube video into **written text**, neatly organized and ready to read or to feed into other tools.

The idea comes from a real need: educational videos (about **RAG**, **fine-tuning**, lectures, talks) are often **1-2 hours** long, and you don't always have the time or focus to watch them all. EchoScript **transcribes** them using the video's **chapters** as sections, so you can *read* the content in minutes, search it, highlight it, or use it as a knowledge base.

You choose **what** to transcribe:

- 📺 **a YouTube video**, from its URL (downloads audio, info and chapters);
- 🎙️ **a local audio file** (phone voice memos, PC recordings: `m4a`, `mp3`, `wav`, `ogg`, `opus`, even `mp4`/`mov` video…), or **a whole folder** to transcribe them all in sequence (batch).

And you choose **how** to transcribe:

- ⚡ **Groq (cloud)**: extremely fast even **without a GPU** (transcribes 2 hours in seconds), practically free.
- 🔒 **Local (faster-whisper on CPU)**: **100% offline and private**, the audio never leaves your PC.

When the transcription is done you can **export to PDF** to read it comfortably, split by chapter.

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
| **Max video length** | often 10-30 min | **2h+ videos** with no problem |
| **Account required** | yes | **no** (local); for Groq just a free key |
| **Watermark / reduced quality** | common | **never** |
| **Privacy** | upload to third-party servers | **local = nothing leaves your PC** |
| **Output formats** | often only `.txt` | `.md`, `.txt`, `.json`, **`.pdf`** |
| **Works offline** | no | **yes** (local backend) |
| **Open source** | rarely | **yes** |

In short: **you are in control**, it runs on **your computer**, and there are no surprises.

---

## 🖥️ Two interfaces: GUI or terminal

EchoScript can be used in **two ways**, with the **same engine** underneath (same transcription, same output formats):

- 🖥️ **Desktop app (GUI)** with `python gui/main.py`: a native graphical interface (Flet), dark, with an animated background. For those who prefer clicking.
- ⌨️ **Terminal (CLI)** with `python transcriber.py`: the classic text interface (Rich), handy for batches and automation.

The **GUI** adds a few conveniences:

- 🌍 **Interface language** Italian/English, with a flag selector
- ▶️ **Video preview**: loading a URL opens a **confirmation window** with the cover and details (channel, views, likes, subscribers, category, language)
- 🏷️ **Engine badge** during transcription (Groq cloud or Local CPU), so you always know what you're transcribing with
- 📊 **Real progress bar** with the phase number (e.g. "Phase 2/5")
- 📄 **PDF always generated** automatically

> Both write the same files to `results/<name>/`. Pick whichever you prefer: the result is identical.

---

## 🖱️ Desktop app guide (for everyone)

This section is written for **non-technical users**: we explain every screen, every button and every message. **No programming needed.**

> ▶️ **How to start it:** double-click the executable (if you have the packaged version), or from the project folder run `python gui/main.py`.

<p align="center">
  <img src="docs/screenshot.png" alt="EchoScript - desktop app" width="840">
</p>

### Top bar: language and window buttons
- Top-right there are **two flags** 🇮🇹 / 🇬🇧: click them to switch the **interface language** (Italian or English). All text changes instantly.
- The three small buttons at the top (**–**, **▢**, **✕**) **minimize**, **maximize** and **close** the window, like in any program.

### Step 1 — "How do you want to transcribe?"
Two cards to choose from (they glow green when selected):
- 🔒 **Local**: transcribes **on your computer**, **offline**, sending nothing. Below you can pick the **model** (more accurate = slower). Best with a GPU; slower on CPU.
- ⚡ **Groq (cloud)**: **very fast**, but the audio is sent to Groq's servers. Needs a **free key**: click **"Load key from .txt file"** and select your key file; **"Get a key →"** opens the site to create one.

### Step 2 — "What do you want to transcribe?"
- 📺 **YouTube**: paste the video **link** in the field and click **"Load info"**.
- 🎙️ **Local file**: click **"Choose audio file…"** and pick a file from your computer (**videos** and **screen recordings** work too).

### The video confirmation window (YouTube)
After **"Load info"** a window opens with the video's **cover** and details (channel, views, likes, subscribers, duration, language…). It asks: *is this the right video?*
- **Confirm** → accept the video (a *"✓ Video confirmed"* line appears below).
- **Cancel** → discard it and paste another one.

### The "Transcribe" button
It's the big green button at the bottom. It becomes **active** only when everything is ready. If you press it too early, a **warning window** appears **listing what's missing**, for example:
- *load the Groq API key* (only if using Groq);
- *load and confirm the YouTube video*, or *choose an audio file*.

### During transcription
A **real progress bar** appears (not a fake animation):
- at the top a **badge** tells you what you're transcribing with: **Groq (cloud)** (green) or **Local CPU** (amber, because it can take minutes);
- on the right the **phase number** (e.g. *"Phase 2/5"*) and the overall **percentage**.

### At the end of transcription
The **PDF is always created**, automatically, and the files are saved with no further prompts.

### The result
A **"Done!"** window summarizes everything: engine used, number of words/sections, **where the files were saved** (the `results/` folder) and the list of created files. The **"Open results folder"** button opens the folder directly.

### Special messages (long or already-done video)
- 🔁 **"Video already transcribed"**: if you redo a video already done, the app asks whether to **Re-transcribe everything** (replaces the files).
- ⏸️ **"Resume available"**: if a long transcription was interrupted (Groq limit, or an interrupted local run), the app **saved the point** and offers to **Resume** from where it stopped or **Start over**.
- ⏳ **"Groq limit reached"**: an amber notice showing how many chunks were done; **resume later**, when free credits return.

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

- 🖥️ **Two interfaces**: desktop **GUI** (`gui/main.py`) or **CLI** in the terminal (`transcriber.py`)
- 🔀 **Two backends** selectable from a panel: Groq (cloud, fast) or faster-whisper (local, private)
- 🎙️ **Two sources**: **YouTube** videos (from URL) or **local audio files** (phone/PC), including **screen recordings** (`mp4`/`mov`/`mkv`…), even a **whole folder** in batch
- 📋 **Video card** before you start (title, channel, views, **likes, subscribers, category, language**, date, duration, chapters)
- 🗣️ **Audio language detected** automatically (Whisper) and shown in the summary
- ✅ **Confirmation** before transcribing
- ⬇️ **Audio-only download** (lightweight) with a progress bar (speed + ETA)
- ⏱️ **Timings & sections**: uses YouTube **chapters** as document sections
- 💾 **3 base formats** always generated: `.md` (human), `.txt` (for other LLMs), `.json` (for RAG)
- 📄 **PDF always generated** automatically, split by chapter
- 🌐 **Automatic translation** to Italian (when the audio isn't already Italian), free via Google Translate
- 🧠 **Automatic summary** of the text, **per section**: strips fillers, repetitions and self-corrections (Groq in the cloud · Ollama locally)
- 🗂️ **Organized output** in `results/<video name>/` under the `trascrizioni/`, `traduzioni/`, `riassunti/` subfolders
- 🎨 **Polished interfaces**: dark GUI with animated background, or Rich CLI with bars and panels
- 🔑 **Safe key handling**: environment variable or `.env` file (never in the code)
- 🧯 **Clear errors**: the key is validated at startup; no pointless retries on auth errors

---

## ⬇️ Download the ready-to-use app (.exe)

If you're **not a developer** and just want to use the program, you don't need to install Python or anything else: download the ready-made app.

1. Go to the project's **[Releases](https://github.com/Imkun-on/EchoScript/releases/latest)** page on GitHub.
2. Download **`EchoScript.zip`** from the latest version.
3. **Extract** the ZIP wherever you like (Desktop, Documents…). Keep the files **together**: you need both `EchoScript.exe` and the **`_internal`** folder next to it.
4. Double-click **`EchoScript.exe`**. Done: the app opens, **nothing to install**.

> 🛡️ **First launch – Windows SmartScreen:** since the app isn't code-signed, Windows may show *"Windows protected your PC"*. Click **"More info" → "Run anyway"**. This is normal for unsigned free software.

**What's included and what isn't:**
- ✅ **Everything bundled**: no Python, ffmpeg or other installs needed.
- 📥 The **first time** you use the **local** backend, the app downloads the model once from HuggingFace (then it's cached, also offline).
- ⚡ For the **Groq** (cloud) backend you only need a **free key** (see below).
- 💻 The `.exe` release is for **Windows**. **macOS/Linux** versions come from their own builds (use the from-source install meanwhile).

> To **uninstall**, just delete the folder: the app writes nothing to the system registry. (Transcriptions live in `results/` next to the executable.)

---

## 📦 Install from source (developers)

This part is only for **running from code** or **modifying** the project. For plain usage, see [Download the ready-to-use app (.exe)](#️-download-the-ready-to-use-app-exe).

### Requirements

- **Python 3.10+**
- **[ffmpeg](https://ffmpeg.org)** installed on your system (needed by yt-dlp and audio preparation)
- *(Groq only)* a free **Groq API key** (see below)
- *(local backend only)* `faster-whisper`
- *(PDF export only)* `fpdf2`
- *(desktop GUI only)* `flet`

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

> ⭐ **Entry point:** the **GUI** via `gui/main.py`, the **CLI** via `transcriber.py`.

---

## 🔑 How to get a Groq API key

The key is needed **only** if you use the **Groq** (cloud) backend. It is **free**.

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
   # Windows (PowerShell), then reopen the terminal
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
| `groq` | Official Groq API client (Whisper) | Official SDK, simple and fast |
| `faster-whisper` | *(optional)* **Local** transcription on CPU | Optimized Whisper implementation (CTranslate2), great on CPU with `int8` |
| `deep-translator` | **Translation** to Italian | Uses Google Translate (free endpoint): no key, no credits |
| `fpdf2` | *(optional)* **PDF** export | Pure-python, **no system LaTeX needed**; supports Unicode fonts |
| `flet` | *(optional)* **desktop GUI** (`gui/main.py`) | Modern native graphical interface in Python; the CLI works without it |

### External tool (not pip)

| Tool | What it's for | Notes |
|---|---|---|
| **[Ollama](https://ollama.com)** | **Local summary** (100% offline) | A separate program to install once; talked to over HTTP (no pip library). Not needed if you use Groq for the summary. Recommended model: `qwen2.5:7b` |

> For the **cloud** summary the existing **`groq`** client is reused (with a chat model, not Whisper): no extra dependency.

### Standard library (no installation)

`os`, `re`, `json`, `sys`, `signal`, `shutil`, `tempfile`, `subprocess`, `datetime`, `urllib`: paths/files, regex, JSON, Ctrl+C handling, ffmpeg/ffprobe calls, dates and — for Ollama — the HTTP calls.

---

## 🚀 Usage & examples

Run the program:

```bash
python transcriber.py
```

Typical flow:

1. **Pick the backend** (1 = Local · 2 = Groq).
2. *(if local)* **Pick the model** (1-5).
3. **Pick the source** (1 = YouTube · 2 = Local file).
4. **Say what to transcribe**: the video **URL**, or the **path** of an audio file or a **folder** (batch).
5. Check the **card** (video or file) and **confirm**.
6. Wait: you'll see the phases (**Download** if from YouTube → **Preparation** if Groq → **Transcription**) with progress bars, and the engine in use (**Groq cloud** or **Local CPU**).
7. The **PDF is always generated** automatically.
8. Find everything under `results/<name>/`.

> 🎙️ **Local files**: no download is needed (you already have the file) and YouTube metadata (channel, chapters…) doesn't exist, so the output uses the **file name** as the title and a single "continuous text" section. Point it at a **folder** and every audio file inside is transcribed in sequence, reusing the same engine and the same export choices.

### Example: Groq backend

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
```

### Example: local audio file (folder batch)

```
› Scelta (1 = Locale · 2 = Groq · q = annulla): 1
› Modello (1-5 · q = annulla): 2
› Scelta (1 = YouTube · 2 = File locale · q = annulla): 2

› Incolla il percorso del file o della cartella audio (q per uscire): C:\Users\me\voice_memos

┌─ 🎙 3 file da trascrivere ───────────────────────┐
│  #   File                              Durata     │
│  1   lecture_01.m4a                     12:04     │
│  2   monday_meeting.mp3                 47:31     │
│  3   memo.wav                            1:58     │
└──────────────────── durata totale ~1:01:33 ──────┘

› Procedo con la trascrizione di questi 3 file? (s/n): s
```

### Use case: build a RAG from videos

Transcribe your study videos, then use the **`.json`** files (segments with timestamps) as the source for your RAG pipeline: they're ready for *chunking* and indexing.

### Use case: read a talk instead of watching it

Transcribe a long talk and use **PDF export**: you get a clean PDF, split by chapter, to read on a tablet or print.

---

## ⚙️ How it works (the phases)

1. **Info**: a lightweight call (`yt-dlp`) reads ONLY the metadata (title, channel, duration, **chapters**), downloading nothing.
2. **Audio download**: only the audio track (lightweight) is downloaded, with a progress bar.
3. **Preparation** *(Groq only)*: the audio is re-encoded to 16 kHz mono and **split into ~10 min chunks** (to stay within the API size limit and give a meaningful bar).
4. **Transcription**: each chunk (Groq) or the whole file (local) is transcribed into **segments with timestamps**; each chunk's timings are corrected relative to the whole video.
5. **Assembly**: segments are grouped by **chapter** (if present) and saved in the various formats.
6. **PDF export**: always, automatically.

> 🎙️ **With a local file** the *Info* and *Download* steps are skipped: the file is fed straight to ffmpeg/Whisper. The duration is read with `ffprobe`, the title from the file name and, having no chapters, you get a single "continuous text" section.

---

## 💾 Output file structure

```
results/
└── <Video or file name>/
    ├── trascrizioni/          (the original transcription)
    │   ├── <Name>.md          (sections with timing in the heading, clean prose)
    │   ├── <Name>.txt         (clean text, for other LLMs)
    │   ├── <Name>.json        (segments with timestamps, for RAG)
    │   └── <Name>.pdf         (always, generated automatically)
    ├── traduzioni/            (if the audio wasn't in Italian)
    │   ├── <Name>_it.md
    │   ├── <Name>_it.txt
    │   ├── <Name>_it.json     (translated sections, reused by "Summary only")
    │   └── <Name>_it.pdf
    └── riassunti/             (clean summary, per section)
        ├── <Name>_riassunto.md
        ├── <Name>_riassunto.txt
        └── <Name>_riassunto.pdf
```

> For **local files** `<Name>` is the file name (without extension); for YouTube videos it's the title. In **batch**, each file gets its own `results/<file name>/` folder. The `traduzioni/` and `riassunti/` folders appear only when those steps run. (Folder names are in Italian to match the app's interface; in the GUI they follow the chosen UI language, e.g. `transcriptions/`, `translations/`, `summaries/` in English.)

### Why three (actually four) formats, and what they're for

It's not redundancy: each format solves a different need, so you never have to reconvert the text by hand.

- **`.md` (Markdown)** → **reading and publishing**. Timings appear **only in section headings**, the body is flowing prose: perfect to open in an editor, on GitHub, Notion or Obsidian, with chapters already as headings.
- **`.txt` (plain text)** → **feeding it to another LLM**. No timestamps, no formatting: the cleanest way to **paste it into ChatGPT/Claude** ("ask me questions about this", "explain it"), for full-text search or scripts.
- **`.json` (structured)** → **RAG and programmatic use**. Contains metadata + chapters + **all segments with timestamps**: ready for *chunking*, indexing into a vector DB, and reconstructing "at what minute X was said".
- **`.pdf`** → **comfortable offline reading**. Laid out and split by chapter: to read on a tablet, annotate or print.

> The same applies to **translation** and **summary**: they are saved in the same formats, so you can read the summary as a PDF, paste its `.txt` into another model, or index it.

---

## 📄 PDF export

The **PDF is always generated, automatically**. EchoScript creates:

- **`.pdf`**: via `fpdf2` (pure-python, **no LaTeX to install**, Arial font for accents), **split by chapter**.

---

## 🌐 Automatic translation

> ℹ️ Translation and summary currently run in the **CLI** (`transcriber.py`). GUI integration is coming.

After transcription, if the audio is **not already in Italian**, EchoScript **translates it to Italian** automatically (if it's already Italian it skips the step: translating `it → it` would be pointless).

- **Free and key-less.** Translation uses **Google Translate** via the `deep-translator` library: no API key, **no Groq credits spent**. The transcription stays intact; the translation goes to `traduzioni/` as separate `.md`/`.txt`/`.pdf` files, **without timings** (continuous text, easier to read).

### How long videos are handled (in blocks)

Translation services accept only a **limited number of characters per request** (~5,000 for Google). A 1-2 hour transcription is much longer and would exceed the limit. The solution is **chunking**:

1. the text is **split into ~4,500-character blocks**, cutting **on sentence boundaries** (after `.`/`?`/`!`) so sentences aren't broken mid-way;
2. each block is translated on its own;
3. the translated blocks are **stitched back** together in the original order.

This way text of any length goes through without errors. If a single sentence were monstrously long it gets force-cut to fit the limit, and if one block fails it **doesn't break everything** (that piece keeps the original as a fallback).

---

## 🧠 Automatic summary

After translation (or, if the audio was already Italian, on the **original transcription**), EchoScript generates a **clean summary** of the text, saved to `riassunti/` in the usual `.md`/`.txt`/`.pdf` formats.

### Why a summary is needed too

A transcription is **raw speech written down**: by nature it carries "noise" that makes reading tiring and hard to study:

- **fillers** ("uh", "um", "you know", "like", "so"…);
- **repetitions** and roundabout phrasing;
- **interrupted sentences** and speaker **self-corrections** ("I mean… actually no…");
- digressions and thinking pauses.

The summary produces a **concise, tidy** version that **keeps the important concepts, data, names and examples** while removing the noise. Above all, it's **per section**: if the video has **chapters**, you get **one summary per chapter** (otherwise a single summary). The result: you study a one-hour video in minutes, with the full transcription kept alongside for the details.

### Which models were introduced and why

Summarizing isn't transcribing: it needs an **LLM** (a language model), because Whisper can only turn audio into text, not rework it. EchoScript uses **two engines**, chosen based on the transcription backend:

| Backend | Summary engine | Model (default) | Why |
|---|---|---|---|
| ⚡ **Groq (cloud)** | Groq chat API | `llama-3.3-70b-versatile` | Runs on Groq's servers: you can afford a **large 70B** model → high-quality summaries, **very fast**, using the free key you already use for transcription |
| 🔒 **Local** | **Ollama** (offline) | `qwen2.5:7b` | Stays **100% offline**. **Qwen 2.5 7B** is light (~4.7 GB), **fast on CPU** and especially good **in Italian** and at following structured instructions (better than Llama 3.1 8B at the same size) |

> **Ollama** is the *program* that runs the model locally (like a "player" for models); **Qwen** is the *model*. Locally you install Ollama once (https://ollama.com) and pull the model: `ollama pull qwen2.5:7b`. No extra pip dependency: EchoScript talks to Ollama over HTTP. With **Groq** none of this is needed.

### Handling long videos: map-reduce + context

As with translation, a very long text doesn't fit in a single request (it exceeds the model's **context**). Here the solution is **map-reduce**:

1. **map** — if a section exceeds `SUMMARY_MAX_CHARS` (12,000 characters) it's split into blocks, and **each block is summarized** on its own;
2. **reduce** — the partial summaries are **merged and summarized again** into a single coherent section summary.

On top of that, for the local engine we **raise Ollama's context window to 8,192 tokens** (`num_ctx`): by default Ollama uses only 2,048 and would **silently truncate** long blocks, ruining summaries of long videos.

### The prompt used (identical for Groq and Ollama)

Quality depends on the instructions given to the model. EchoScript always sends this **system prompt** (in Italian, since the output is Italian):

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

*(Translation: "You are an expert editor. You receive the transcription of a section of a spoken video (Italian text). Turn it into a clear, faithful, fluent summary in Italian: remove fillers and hesitations; remove repetitions, broken sentences and the speaker's self-corrections, keeping only the corrected version; PRESERVE all concepts, data, proper names and important examples; DO NOT add anything not in the text and do not make things up; structure it as 3 to 6 concise bullet points and, if useful, 1-2 final summary sentences. Reply ONLY with the summary, no preamble or comments.")*

The model is then given the **section title** (if the video has chapters) and the text to summarize, with `temperature=0.3` for a faithful, non-"creative" output.

### On an already-transcribed video (regenerate without re-spending)

If you transcribe again a video **already present** in `results/`, the CLI shows a panel to choose **what to regenerate**, without necessarily starting over:

| Option | What it does |
|---|---|
| 🔁 **Re-transcribe everything** | redoes transcription + translation + summary from scratch |
| 🌐 **Translation + summary** | reuses the saved transcription, translates and summarizes it (**no transcription credits**) |
| 🧠 **Summary only** | generates **only** the summary from the saved text (the **translation** if present, otherwise the original) |
| 🎙 **Re-transcribe only** | redoes just the transcription, no translation or summary |
| ⏭ **Skip** | does nothing for that video |

> To reuse the translation, "Summary only" reads `traduzioni/<Name>_it.json` (saved alongside the translation). If that file is missing (older translations), it summarizes the original transcription.

> ⏱️ **Timing.** With Groq the summary is nearly instant. Locally on **CPU** it can take a few minutes for long videos (with a **GPU** it drops to seconds: Ollama uses it automatically when present). Everything is configurable via `.env` (model, host, context, map-reduce threshold).

---

## 🛠️ Configuration

Every "knob" is set via environment variables / a `.env` file (see
the `.env` file), no code editing needed. Each value has a sensible default:

| `.env` variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | — | Groq key (cloud transcription only) |
| `ECHOSCRIPT_GROQ_MODEL` | `whisper-large-v3-turbo` | Whisper model on Groq (turbo = fast/cheap) |
| `ECHOSCRIPT_AUDIO_LANG` | *(empty)* | Audio language: empty = auto-detect; force with `it` / `en` / … |
| `ECHOSCRIPT_WORD_TIMESTAMPS` | `1` | Word-level timestamps (useful for subtitles) |
| `ECHOSCRIPT_CHUNK_SECONDS` | `600` | Duration of each audio chunk (Groq only) |
| `ECHOSCRIPT_DEVICE` | `auto` | Local backend: `auto` (GPU if present) / `cpu` / `cuda` |
| `ECHOSCRIPT_COMPUTE_TYPE` | *(auto)* | Local precision: empty = `float16` on GPU, `int8` on CPU |
| `ECHOSCRIPT_GROQ_SUMMARY_MODEL` | `llama-3.3-70b-versatile` | **Groq chat** model used for the summary (cloud) |
| `ECHOSCRIPT_OLLAMA_MODEL` | `qwen2.5:7b` | **Ollama** model for the local summary |
| `ECHOSCRIPT_OLLAMA_HOST` | `http://localhost:11434` | Ollama server address |
| `ECHOSCRIPT_OLLAMA_NUM_CTX` | `8192` | Ollama context window (avoids truncating long blocks) |
| `ECHOSCRIPT_SUMMARY_MAX_CHARS` | `12000` | Threshold above which a section is summarized in blocks (map-reduce) |

> **Local summary.** Requires [Ollama](https://ollama.com) installed and running,
> with the model pulled: `ollama pull qwen2.5:7b`. With the **Groq** backend the
> summary uses the key you already have, with nothing else to install.

> **Automatic GPU.** The local backend uses the GPU (CUDA) when available, else
> the CPU. Install PyTorch with CUDA for acceleration (see `requirements.txt`).

---

## 🔒 Privacy

- **Local backend (faster-whisper)**: the **audio never leaves your PC**. (On first use it only downloads the model *weights* from HuggingFace.) Maximum privacy.
- **Groq backend**: the audio is **uploaded to Groq's servers** for transcription. Great for public videos, not advised for private/sensitive audio.
- **Translation**: uses **Google Translate**, so the transcription text is sent to Google's servers.
- **Summary**: with the **Groq** backend the text goes to Groq's servers; with the **local** backend it uses **Ollama on your PC**, so it **stays 100% offline** (nothing leaves the computer).

The **API key** is never written in the code: it is read from `.env` or an environment variable, and excluded from version control via `.gitignore`.

---

## ⚖️ Legal notice

EchoScript downloads audio from YouTube to transcribe it. Its use may be subject to YouTube's **Terms of Service** and to the **copyright** rules of your jurisdiction. It is intended for **personal and educational** use (e.g. studying a video by reading it): use it responsibly and only for content you have the rights to, or for personal study.

---

## 📄 License

Released under the **MIT** license.
