# =============================================================================
#  EchoScript — desktop GUI (Flet)
# =============================================================================
#  Native graphical interface built entirely with Flet. It drives the headless
#  engine (core/engine.py), the very same one used by the CLI: there is NO
#  transcription logic here, only presentation and orchestration. This keeps a
#  single source of truth for the heavy work and lets the GUI stay thin.
#
#  The heavy work (download / transcription / translation / saving) runs in a
#  BACKGROUND thread; the engine reports progress through an
#  `on_progress(phase, current, total, detail)` callback with which we update
#  the progress bar. Flet allows updating controls from a secondary thread, so
#  the window never freezes — that is exactly why every long-running action is
#  launched on its own daemon thread and only touches the UI through `page.update()`.
#
#  Interface language: Italian (default) or English, selectable from the title
#  bar. Every user-facing string goes through self.t(), so switching language at
#  runtime only needs to re-read the strings, not rebuild the UI.
#
#  Palette: green + black with emerald shades (professional, dark look).
# =============================================================================

import os
import sys
import math
import random
import threading
import time
import webbrowser

_GUI_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_GUI_DIR)
# Make the engine and the "pure" helpers shared with the CLI importable.
for _p in (os.path.join(_PROJECT_ROOT, "core"), _PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import flet as ft
import flet.canvas as cv  # vector drawing for the animated background (particles)

import engine            # core/engine.py
import transcriber as tx  # reuse of the pure formatters (duration, views, etc.)


# === PALETTE (green / black + emerald shades) ==============================
BG        = "#0A0F0C"   # window background: black with a green veil
SURFACE   = "#111A14"   # card
SURFACE2  = "#16221B"   # selected / highlighted surface
BORDER    = "#243329"   # neutral border
BORDER_HI = "#2F8F57"   # green border (selected state)
GREEN     = "#22C55E"   # primary
GREEN_HI  = "#4ADE80"   # bright accent
GREEN_DK  = "#15803D"   # deep green (gradient)
TEXT      = "#E8F1EB"   # main text
MUTED     = "#8A9A90"   # secondary text
DANGER    = "#F87171"
WARN      = "#FBBF24"

# Height shared by the two configuration cards so they always stay identical
# regardless of content (see _build_ui). Sized for the tallest case (Groq
# backend with the key loader). A fixed shared height is the workaround for
# Flet 0.27 lacking IntrinsicHeight. Kept compact so the WHOLE home fits on one
# screen without a vertical scrollbar (the inner card column scrolls if needed).
CARD_HEIGHT = 284

# Local models offered in the dropdown (whisper model key -> i18n key).
_LOCAL_MODELS = [
    ("base",           "model_base"),
    ("small",          "model_small"),
    ("medium",         "model_medium"),
    ("large-v3",       "model_largev3"),
    ("large-v3-turbo", "model_turbo"),
]

# === LOCALIZED STRINGS (it = default, en) ==================================
# Every user-facing text lives below. self.t("key") returns the version in the
# current language; the ones with {placeholders} are used with .format().
T = {
    "it": {
        "header_sub": "Trascrivi video YouTube o audio locali, veloce con Groq o 100% offline",
        # Step 1 — backend
        "step1_title": "Come vuoi trascrivere?",
        "backend_local_name": "Locale",
        "backend_local_desc": "Privacy totale, offline. GPU consigliata.",
        "backend_groq_name": "Groq",
        "backend_groq_desc": "Velocissimo. L'audio viene inviato ai server Groq.",
        "model_label": "Modello locale",
        "model_base": "base — veloce, meno accurato",
        "model_small": "small — equilibrio consigliato ★",
        "model_medium": "medium — più accurato, più lento",
        "model_largev3": "large-v3 — massima accuratezza, molto lento",
        "model_turbo": "large-v3-turbo — quasi large, più rapido",
        "key_field_label": "Chiave API Groq",
        "load_key": "Carica chiave da file .txt",
        "limits_btn": "Mostra crediti API Groq",
        "limits_checking": "Controllo…",
        "get_key": "Ottieni una chiave →",
        "key_loaded": "✓ Chiave caricata da “{name}”",
        "key_none": "Nessun file caricato (in alternativa la chiave può stare nel file .env).",
        "pick_key_dialog": "Scegli il file .txt con la chiave Groq",
        # Step 2 — source
        "step2_title": "Cosa vuoi trascrivere?",
        "source_youtube_name": "YouTube",
        "source_youtube_desc": "Incolla l'URL di un video pubblico.",
        "source_local_name": "File locale",
        "source_local_desc": "Audio da telefono o PC (m4a, mp3, wav…).",
        "url_hint": "Incolla l'URL del video YouTube…",
        "load_info": "Carica info",
        "load_info_loading": "Carico…",
        "confirm_title": "Conferma il video",
        "confirm_question": "È questo il video che vuoi trascrivere?",
        "btn_confirm": "Conferma",
        "btn_cancel": "Annulla",
        "yt_confirmed": "✓ Video confermato: {title}",
        "pick_file": "Scegli file audio…",
        "pick_file_dialog": "Scegli un file audio o video",
        # Info box
        "info_channel": "Canale",
        "info_views": "Views",
        "info_date": "Data",
        "info_duration": "Durata",
        "info_chapters": "Capitoli",
        "info_likes": "Mi piace",
        "info_subs": "Iscritti",
        "info_category": "Categoria",
        "info_language": "Lingua audio",
        "info_file": "File",
        "chapters_some": "{n} sezioni",
        "chapters_none": "nessuno",
        # CTA + warning
        "cta_run": "Trascrivi",
        "cta_busy": "Elaborazione in corso…",
        "warn_title": "Manca qualcosa",
        "warn_prefix": "Per avviare la trascrizione serve:",
        "and": "e",
        "need_key": "caricare la chiave API Groq",
        "need_src_yt": "caricare e confermare il video YouTube (pulsante «Carica info»)",
        "need_src_local": "scegliere un file audio",
        # Progress
        "phase_word": "Fase",
        "phase_optional": "(opzionale)",
        "phase_default": "In corso…",
        "engine_groq": "Groq (cloud) · {model}",
        "engine_local": "Locale CPU · faster-whisper {model}",
        "engine_local_hint": "La trascrizione locale gira sulla CPU: può richiedere diversi minuti.",
        "phase_info": "Lettura informazioni",
        "phase_download": "Download audio",
        "phase_prepare": "Preparazione audio",
        "phase_transcribe": "Trascrizione",
        "phase_translate": "Traduzione in italiano",
        "phase_summarize": "Riassunto",
        "phase_visual": "Analisi visiva",
        "phase_export": "Esportazione / salvataggio",
        "saving_files": "Salvataggio dei file",
        # Output options card (translation / summary toggles)
        "opts_title": "Output aggiuntivi",
        "opt_translate_name": "Traduci in italiano",
        "opt_translate_desc": "Traduzione italiana in /traduzioni (Groq se hai la "
                              "chiave, altrimenti Ollama offline).",
        "opt_summary_name": "Crea riassunto",
        "opt_summary_desc": "Riassunto pulito per sezione in /riassunti "
                            "(Groq se hai la chiave, altrimenti Ollama locale).",
        "opt_visual_name": "Analisi visiva del video",
        "opt_visual_desc": "«Guarda» i fotogrammi ed estrae codice, formule e grafici a "
                           "schermo, nel riassunto + un documento con i frame. Più lento; "
                           "richiede Groq (più crediti) o un modello vision Ollama.",
        # Progress dialog (dedicated window)
        "prog_title": "Elaborazione in corso",
        "prog_steps_title": "Passaggi",
        "prog_plan_label": "Piano:",
        "ov_base": "trascrivo l'audio",
        "ov_translate": "lo traduco in italiano",
        "ov_summary": "creo il riassunto",
        "ov_visual": "analizzo i fotogrammi del video",
        "ov_save": "salvo i file (PDF incluso)",
        "ov_join": " e ",
        "narr_info": "Leggo le informazioni della sorgente e preparo l'elaborazione…",
        "narr_download": "Scarico la traccia audio dal video…",
        "narr_prepare": "Preparo l'audio e lo divido in blocchi per Groq…",
        "narr_transcribe": "Converto il parlato in testo, blocco per blocco…",
        "narr_export": "Salvo la trascrizione e genero il PDF…",
        "narr_translate": "Traduco il testo in italiano, sezione per sezione…",
        "narr_summarize": "Creo un riassunto pulito per ogni sezione…",
        "narr_visual": "Guardo i fotogrammi ed estraggo codice, formule e grafici…",
        "narr_done": "Quasi finito: completo gli ultimi salvataggi…",
        # Options dialog
        "opt_title": "Trascrizione completata",
        "opt_desc": "Il PDF verrà creato automaticamente. Poi indica dove salvare: "
                    "l'app creerà le sottocartelle (trascrizioni, traduzioni).",
        "opt_already_it": "Audio già in italiano: nessuna traduzione necessaria.",
        "opt_switch": "Traduci anche in italiano (usa Groq)",
        # "Video already transcribed" dialog
        "already_title": "Video già trascritto",
        "already_desc": "Questo video è già presente nella cartella results/. Cosa vuoi fare?",
        "opt_retranscribe": "Ritrascrivi tutto",
        "opt_retranscribe_desc": "Rifà la trascrizione da capo; i file esistenti verranno sostituiti.",
        "opt_only_translate": "Solo (ri)traduzione",
        "opt_only_translate_desc": "Riusa la trascrizione esistente e rigenera solo la traduzione "
                                   "(sovrascrive quella vecchia). Non rispende crediti di trascrizione.",
        # "Resume available" dialog
        "resume_title": "Ripresa disponibile",
        "resume_desc": "Una trascrizione di questo video si era interrotta. Cosa vuoi fare?",
        "resume_opt_resume": "Riprendi",
        "resume_opt_resume_desc": "Continua dal punto salvato (blocco {done}/{total}).",
        "resume_opt_resume_desc_time": "Continua dalla posizione salvata ({done} / {total}).",
        "resume_opt_restart": "Ricomincia da capo",
        "resume_opt_restart_desc": "Ignora il parziale e ritrascrive tutto da zero.",
        # Rate-limit-reached warning
        "ratelimit_title": "Crediti Groq esauriti",
        "ratelimit_msg": "I crediti gratuiti Groq per oggi sono terminati.\n\n"
                         "La trascrizione si è fermata a {done} su {total} ed è stata "
                         "salvata automaticamente.\n\n"
                         "Quando i crediti torneranno disponibili (di norma domani) riapri "
                         "questo video e scegli «Riprendi» per continuare da dove si è "
                         "interrotto. In alternativa puoi completarlo subito in locale.",
        "ratelimit_close": "Riprendo domani",
        "ratelimit_continue_local": "Continua ora in locale (CPU)",
        "engine_translate": "DeepL · traduzione",
        "opt_key_needed": "Per tradurre serve una chiave DeepL:",
        "btn_continue": "Continua e scegli cartella",
        "dir_dialog": "Scegli la cartella di destinazione",
        "groq_key_error": "Errore con la chiave Groq: {e}",
        # Result dialog
        "res_title": "Completato!",
        "res_engine": "Motore",
        "res_segments": "Segmenti",
        "res_words": "Parole",
        "res_sections": "Sezioni",
        "res_continuous": "testo continuo",
        "res_saved_in": "Salvato in:",
        "res_root": "(radice)",
        "btn_open_folder": "Apri cartella risultati",
        "btn_close": "Chiudi",
        # Credits / limits dialog
        "lim_title": "Crediti API Groq",
        "lim_free_note": "Letti dalle richieste già fatte (trascrizione, riassunto, "
                         "analisi visiva): aprire questa finestra NON contatta Groq "
                         "e non consuma alcun credito.",
        "lim_no_data": "Ancora nessun dato. Esegui una trascrizione, un riassunto o "
                       "un'analisi visiva: i crediti residui di ciascun modello "
                       "compariranno qui (senza spendere nulla per controllare).",
        "lim_role_transcription": "Trascrizione",
        "lim_role_summary": "Riassunto",
        "lim_role_vision": "Analisi visiva",
        "lim_role_other": "Altro",
        "lim_checked_at": "aggiornato alle {v}",
        "lim_kind_audio_seconds": "Audio (secondi)",
        "lim_kind_requests": "Richieste",
        "lim_kind_tokens": "Token",
        "lim_remaining": "{rem} / {lim} rimasti",
        "lim_remaining_only": "{rem} rimasti",
        "lim_reset_at": "si azzera {clock} (tra {dur})",
        "lim_reset_in": "si azzera tra {dur}",
        "lim_reset_today": "alle {hm}",
        "lim_reset_tomorrow": "domani alle {hm}",
        "lim_reset_date": "il {dm} alle {hm}",
        "lim_none": "Nessun dato sui limiti restituito da Groq.",
        "lim_unit_seconds": "secondi audio",
        # Credits in the result summary
        "res_credits": "Crediti Groq",
        "res_credits_used": "Audio trascritto",
        "res_credits_remaining_audio": "Audio residuo oggi",
        # Visual analysis in the result summary
        "res_visual": "Analisi visiva",
        "res_visual_count": "{n} fotogrammi con contenuto estratto",
        "btn_open_visual": "Apri analisi visiva",
        # Errors
        "err_title": "Errore",
        "err_unknown": "Errore sconosciuto.",
        "err_paste_url": "Incolla prima l'URL del video.",
        "err_choose_audio": "Scegli prima un file audio.",
        "err_unexpected": "Errore imprevisto: {e}",
        "err_save": "Errore nel salvataggio: {e}",
        "err_key_read": "Impossibile leggere il file della chiave: {e}",
        "err_key_invalid": "Il file selezionato non contiene una chiave valida.",
        "err_limits": "Errore nel controllo dei limiti: {e}",
        # Language selector + pre-run estimate
        "est_cost": "Costo stimato ~${c} · Groq {m}",
        "est_time": "Tempo stimato ~{t} su {d} · offline",
    },
    "en": {
        "header_sub": "Transcribe YouTube videos or local audio, fast with Groq or 100% offline",
        "step1_title": "How do you want to transcribe?",
        "backend_local_name": "Local",
        "backend_local_desc": "Full privacy, offline. GPU recommended.",
        "backend_groq_name": "Groq",
        "backend_groq_desc": "Very fast. Audio is sent to Groq servers.",
        "model_label": "Local model",
        "model_base": "base — fast, less accurate",
        "model_small": "small — recommended balance ★",
        "model_medium": "medium — more accurate, slower",
        "model_largev3": "large-v3 — top accuracy, very slow",
        "model_turbo": "large-v3-turbo — near large, faster",
        "key_field_label": "Groq API key",
        "load_key": "Load key from .txt file",
        "limits_btn": "Show Groq API credits",
        "limits_checking": "Checking…",
        "get_key": "Get a key →",
        "key_loaded": "✓ Key loaded from “{name}”",
        "key_none": "No file loaded (the key can also live in the .env file).",
        "pick_key_dialog": "Choose the .txt file with the Groq key",
        "step2_title": "What do you want to transcribe?",
        "source_youtube_name": "YouTube",
        "source_youtube_desc": "Paste the URL of a public video.",
        "source_local_name": "Local file",
        "source_local_desc": "Audio from phone or PC (m4a, mp3, wav…).",
        "url_hint": "Paste the YouTube video URL…",
        "load_info": "Load info",
        "load_info_loading": "Loading…",
        "confirm_title": "Confirm the video",
        "confirm_question": "Is this the video you want to transcribe?",
        "btn_confirm": "Confirm",
        "btn_cancel": "Cancel",
        "yt_confirmed": "✓ Video confirmed: {title}",
        "pick_file": "Choose audio file…",
        "pick_file_dialog": "Choose an audio or video file",
        "info_channel": "Channel",
        "info_views": "Views",
        "info_date": "Date",
        "info_duration": "Duration",
        "info_chapters": "Chapters",
        "info_likes": "Likes",
        "info_subs": "Subscribers",
        "info_category": "Category",
        "info_language": "Audio language",
        "info_file": "File",
        "chapters_some": "{n} sections",
        "chapters_none": "none",
        "cta_run": "Transcribe",
        "cta_busy": "Processing…",
        "warn_title": "Something's missing",
        "warn_prefix": "To start transcribing you need to:",
        "and": "and",
        "need_key": "load the Groq API key",
        "need_src_yt": "load and confirm the YouTube video (“Load info” button)",
        "need_src_local": "choose an audio file",
        "phase_word": "Phase",
        "phase_optional": "(optional)",
        "phase_default": "Working…",
        "engine_groq": "Groq (cloud) · {model}",
        "engine_local": "Local CPU · faster-whisper {model}",
        "engine_local_hint": "Local transcription runs on the CPU: it can take several minutes.",
        "phase_info": "Reading information",
        "phase_download": "Downloading audio",
        "phase_prepare": "Preparing audio",
        "phase_transcribe": "Transcribing",
        "phase_translate": "Translating to Italian",
        "phase_summarize": "Summarizing",
        "phase_visual": "Visual analysis",
        "phase_export": "Exporting / saving",
        "saving_files": "Saving files",
        # Output options card (translation / summary toggles)
        "opts_title": "Extra outputs",
        "opt_translate_name": "Translate to Italian",
        "opt_translate_desc": "Italian translation in /translations (Groq if you have a "
                              "key, otherwise offline Ollama).",
        "opt_summary_name": "Create summary",
        "opt_summary_desc": "Clean per-section summary in /summaries "
                            "(Groq if you have a key, otherwise local Ollama).",
        "opt_visual_name": "Visual analysis of the video",
        "opt_visual_desc": "«Looks» at the frames and extracts on-screen code, formulas "
                           "and charts, into the summary + a document with the frames. "
                           "Slower; needs Groq (more credits) or an Ollama vision model.",
        # Progress dialog (dedicated window)
        "prog_title": "Processing",
        "prog_steps_title": "Steps",
        "prog_plan_label": "Plan:",
        "ov_base": "transcribe the audio",
        "ov_translate": "translate it to Italian",
        "ov_summary": "create the summary",
        "ov_visual": "analyze the video frames",
        "ov_save": "save the files (PDF included)",
        "ov_join": " and ",
        "narr_info": "Reading the source info and getting ready…",
        "narr_download": "Downloading the audio track from the video…",
        "narr_prepare": "Preparing the audio and splitting it into chunks for Groq…",
        "narr_transcribe": "Turning speech into text, chunk by chunk…",
        "narr_export": "Saving the transcription and generating the PDF…",
        "narr_translate": "Translating the text to Italian, section by section…",
        "narr_summarize": "Creating a clean summary for each section…",
        "narr_visual": "Looking at the frames and extracting code, formulas and charts…",
        "narr_done": "Almost there: finishing the last saves…",
        "opt_title": "Transcription complete",
        "opt_desc": "The PDF will be created automatically. Then choose where to save: "
                    "the app will create the subfolders (transcriptions, translations).",
        "opt_already_it": "Audio already in Italian: no translation needed.",
        "opt_switch": "Also translate to Italian (uses Groq)",
        "already_title": "Video already transcribed",
        "already_desc": "This video is already in the results/ folder. What do you want to do?",
        "opt_retranscribe": "Re-transcribe everything",
        "opt_retranscribe_desc": "Redo the transcription from scratch; existing files will be replaced.",
        "opt_only_translate": "Translation only",
        "opt_only_translate_desc": "Reuse the existing transcription and regenerate only the translation "
                                   "(overwrites the old one). No transcription credits spent.",
        "resume_title": "Resume available",
        "resume_desc": "A transcription of this video was interrupted. What do you want to do?",
        "resume_opt_resume": "Resume",
        "resume_opt_resume_desc": "Continue from the saved point (chunk {done}/{total}).",
        "resume_opt_resume_desc_time": "Continue from the saved position ({done} / {total}).",
        "resume_opt_restart": "Start over",
        "resume_opt_restart_desc": "Discard the partial and re-transcribe from scratch.",
        "ratelimit_title": "Groq credits exhausted",
        "ratelimit_msg": "Today's free Groq credits are used up.\n\n"
                         "Transcription stopped at {done} of {total} and was saved "
                         "automatically.\n\n"
                         "When credits become available again (usually tomorrow), reopen "
                         "this video and choose “Resume” to continue from where it stopped. "
                         "Alternatively, you can finish it now locally.",
        "ratelimit_close": "I'll resume tomorrow",
        "ratelimit_continue_local": "Continue now, locally (CPU)",
        "engine_translate": "DeepL · translation",
        "opt_key_needed": "Translation requires a DeepL key:",
        "btn_continue": "Continue and choose folder",
        "dir_dialog": "Choose the destination folder",
        "groq_key_error": "Groq key error: {e}",
        "res_title": "Done!",
        "res_engine": "Engine",
        "res_segments": "Segments",
        "res_words": "Words",
        "res_sections": "Sections",
        "res_continuous": "continuous text",
        "res_saved_in": "Saved in:",
        "res_root": "(root)",
        "btn_open_folder": "Open results folder",
        "btn_close": "Close",
        "lim_title": "Groq API credits",
        "lim_free_note": "Read from requests you already made (transcription, summary, "
                         "visual analysis): opening this window does NOT contact Groq "
                         "and spends no credits.",
        "lim_no_data": "No data yet. Run a transcription, a summary or a visual "
                       "analysis: each model's remaining credits will show up here "
                       "(without spending anything to check).",
        "lim_role_transcription": "Transcription",
        "lim_role_summary": "Summary",
        "lim_role_vision": "Visual analysis",
        "lim_role_other": "Other",
        "lim_checked_at": "updated at {v}",
        "lim_kind_audio_seconds": "Audio (seconds)",
        "lim_kind_requests": "Requests",
        "lim_kind_tokens": "Tokens",
        "lim_remaining": "{rem} / {lim} left",
        "lim_remaining_only": "{rem} left",
        "lim_reset_at": "resets {clock} (in {dur})",
        "lim_reset_in": "resets in {dur}",
        "lim_reset_today": "at {hm}",
        "lim_reset_tomorrow": "tomorrow at {hm}",
        "lim_reset_date": "on {dm} at {hm}",
        "lim_none": "Groq returned no limit data.",
        "lim_unit_seconds": "audio seconds",
        "res_credits": "Groq credits",
        "res_credits_used": "Audio transcribed",
        "res_credits_remaining_audio": "Audio left today",
        "res_visual": "Visual analysis",
        "res_visual_count": "{n} frames with extracted content",
        "btn_open_visual": "Open visual analysis",
        "err_title": "Error",
        "err_unknown": "Unknown error.",
        "err_paste_url": "Paste the video URL first.",
        "err_choose_audio": "Choose an audio file first.",
        "err_unexpected": "Unexpected error: {e}",
        "err_save": "Error while saving: {e}",
        "err_key_read": "Cannot read the key file: {e}",
        "err_key_invalid": "The selected file does not contain a valid key.",
        "err_limits": "Error while checking limits: {e}",
        "est_cost": "Estimated cost ~${c} · Groq {m}",
        "est_time": "Estimated time ~{t} on {d} · offline",
    },
}


class EchoScriptApp:
    """Builds and manages the entire Flet interface.

    All transcription work is delegated to the engine; this class only owns the
    UI state, the widget tree and the orchestration of the background threads
    that call the engine and feed progress back into the controls."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page

        # --- application state ---
        self.lang = "it"            # "it" | "en" (interface language)
        self.backend = "local"      # "local" | "groq"
        self.source = "youtube"     # "youtube" | "local"
        self.local_path = None      # path of the chosen local file
        self.last_dir = None        # results folder (for "Open folder")
        self.last_thumb = None      # video cover (URL) for the summary
        self.busy = False           # True while a job is in progress
        self._run_enabled = False   # True when "Transcribe" can be enabled
        self.loaded_api_key = None  # Groq key read from a .txt file (or None) — transcription
        self.loaded_api_key_name = ""   # name of the file it was read from
        self._key_status_labels = []    # Groq status labels to refresh once a key loads
        self._yt_meta = None        # last YouTube meta loaded (for language re-fill)
        self._yt_ok = False         # True only after confirming the YouTube video
        self._local_meta = None     # last local-file meta loaded
        self._cur_phase = "info"    # current phase (for re-translating the label on lang change)
        self._plan = []             # phase sequence of the current run (for "Phase i/n")
        self._last_g = 0.0          # highest global progress reached (anti-regress bar)
        self._i18n = []             # [(control, attribute, key)] to re-translate

        # FIXED output folder: results/ next to the project (like the CLI). This
        # lets us check BEFORE transcribing whether the video is already done or
        # has a partial to resume, without asking for a folder every time.
        self.out_root = engine.RESULTS_DIR

        # --- file pickers (must live in page.overlay) ---
        self.file_picker = ft.FilePicker(on_result=self._on_file_picked)
        self.key_picker = ft.FilePicker(on_result=self._on_key_picked)
        page.overlay.extend([self.file_picker, self.key_picker])

        self._build_ui()

    # -------------------------------------------------------------- I18N HELPERS
    def t(self, key: str) -> str:
        """Return a string in the current language (fall back to Italian, then the key).

        Centralizing every lookup here is what makes runtime language switching
        possible without rebuilding the widget tree."""
        return T.get(self.lang, T["it"]).get(key) or T["it"].get(key, key)

    def _T(self, key: str, **kw) -> ft.Text:
        """Create a REGISTERED ft.Text whose value follows the current language.

        The control is recorded in self._i18n so _set_lang can rewrite its text
        in place when the user flips the language flag."""
        txt = ft.Text(self.t(key), **kw)
        self._i18n.append((txt, "value", key))
        return txt

    def _reg(self, obj, attr: str, key: str):
        """Register a textual attribute (text/label/hint_text…) for re-translation.

        Many controls are not ft.Text but still carry a translatable label; this
        lets _set_lang update any attribute on any control via setattr."""
        setattr(obj, attr, self.t(key))
        self._i18n.append((obj, attr, key))
        return obj

    def _set_lang(self, lang: str) -> None:
        """Switch the whole interface to 'lang' in place (no rebuild).

        Rewrites every registered static control, then refreshes the dynamic
        parts (model options, key status, info boxes, current phase label, CTA)
        that are not simple registered strings. A no-op if the language is
        unchanged, to avoid a pointless full-page update."""
        if lang == self.lang:
            return
        self.lang = lang
        self._style_lang_pills()
        # Re-translate every registered static control.
        for obj, attr, key in self._i18n:
            setattr(obj, attr, self.t(key))
        # Re-translate the dynamic parts.
        self._rebuild_model_options()
        self._refresh_key_status()
        self._refresh_info_boxes()
        self.prog_phase.value = self.t("phase_" + self._cur_phase) \
            if ("phase_" + self._cur_phase) in T[self.lang] else self.t("phase_default")
        self.cta_text.value = self.t("cta_busy") if self.busy else self.t("cta_run")
        self._update_run_state()
        self.page.update()

    # ---------------------------------------------------------------- UI BUILD
    def _build_ui(self) -> None:
        """Assemble the whole window once: theme, layout, dialogs and background.

        Called a single time from __init__. The modal dialogs are built here (up
        front) rather than on demand so their controls can be registered for
        i18n and reused; only their per-run CONTENT is filled later."""
        p = self.page
        p.title = "EchoScript"
        p.theme_mode = ft.ThemeMode.DARK
        p.bgcolor = BG
        p.padding = 0
        p.theme = ft.Theme(
            color_scheme_seed=GREEN, font_family="Segoe UI",
            scrollbar_theme=ft.ScrollbarTheme(
                thumb_visibility=True, track_visibility=False,
                thickness=8, radius=8,
                thumb_color={
                    ft.ControlState.HOVERED: GREEN,
                    ft.ControlState.DEFAULT: ft.Colors.with_opacity(0.40, GREEN),
                },
                track_color=ft.Colors.with_opacity(0.05, GREEN),
            ),
        )
        p.window.width = 1040
        p.window.height = 900
        p.window.min_width = 720
        p.window.min_height = 620
        p.window.title_bar_hidden = True
        p.window.title_bar_buttons_hidden = True
        p.window.on_event = self._on_window_event
        p.on_resized = self._on_resized
        p.window.center()

        # TWO-COLUMN layout: the two configuration steps side by side, so
        # everything fits on screen without a scrollbar.
        backend_card = self._step_backend()
        source_card = self._step_source()
        backend_card.expand = 1
        source_card.expand = 1
        # IDENTICAL fixed height on both cards: Flet 0.27 has no IntrinsicHeight,
        # and STRETCH inside a "tight" column would collapse them; a shared
        # height keeps them always equal whatever the state (Groq, file chosen,
        # etc.). The content stays anchored at the top.
        backend_card.height = CARD_HEIGHT
        source_card.height = CARD_HEIGHT
        self._steps_row = ft.Row(
            [backend_card, source_card], spacing=18,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        content = ft.Column(
            spacing=10,
            tight=True,
            # Scrollable as a safety net on very short windows, but the layout is
            # sized so the whole home fits on one screen without scrolling.
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                self._header(),
                self._steps_row,
                self._options_card(),
                self._cta_button(),
            ],
        )

        # Modal windows built separately (up front, then reused).
        self._build_progress_dialog()   # progress now lives in its own window
        self._build_error_dialog()
        self._build_warn_dialog()

        self._sync_select_visuals()

        pad = self._side_pad()
        self.content_holder = ft.Container(
            expand=True, alignment=ft.alignment.center, content=content,
            padding=ft.padding.only(left=pad, right=pad, top=12, bottom=14),
        )

        root = ft.Stack(
            expand=True,
            controls=[
                ft.Container(expand=True, bgcolor=BG),
                self._grid_layer(),
                ft.Column(
                    expand=True, spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[self._title_bar(), self.content_holder],
                ),
            ],
        )
        p.add(root)
        self._update_run_state()   # initial button state + warning
        self.page.update()
        self._start_grid()

    # --------------------------------------------------------------- TITLE BAR
    def _title_bar(self) -> ft.Control:
        """Custom title bar (drag + language + minimize/maximize/close).

        The native OS title bar is hidden (title_bar_hidden) to keep the dark
        look consistent, so we draw and wire our own window controls and wrap
        the bar in a WindowDragArea to keep the window movable."""
        self.max_icon = ft.Icon(ft.Icons.CROP_SQUARE_OUTLINED, size=15, color=MUTED)

        def win_button(icon_ctrl, on_click, hover_bg, hover_fg):
            """Build one window-control button with a hover highlight."""
            btn = ft.Container(
                width=46, height=32, border_radius=8, ink=True,
                alignment=ft.alignment.center, content=icon_ctrl, on_click=on_click,
                animate=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
            )

            def on_hover(e):
                hovering = e.data == "true"
                btn.bgcolor = hover_bg if hovering else None
                icon_ctrl.color = hover_fg if hovering else MUTED
                btn.update()

            btn.on_hover = on_hover
            return btn

        min_btn = win_button(
            ft.Icon(ft.Icons.REMOVE, size=16, color=MUTED),
            lambda e: self._minimize(),
            ft.Colors.with_opacity(0.12, GREEN), GREEN_HI)
        max_btn = win_button(
            self.max_icon, lambda e: self._toggle_max(),
            ft.Colors.with_opacity(0.12, GREEN), GREEN_HI)
        close_btn = win_button(
            ft.Icon(ft.Icons.CLOSE, size=17, color=MUTED),
            lambda e: self.page.window.close(),
            ft.Colors.with_opacity(0.85, DANGER), "#FFFFFF")

        brand = ft.Row(
            spacing=9, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=22, height=22, border_radius=7,
                    gradient=ft.LinearGradient(
                        begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                        colors=[GREEN_HI, GREEN_DK]),
                    alignment=ft.alignment.center,
                    content=ft.Icon(ft.Icons.GRAPHIC_EQ, color="#06140C", size=14)),
                ft.Text("EchoScript", size=13, weight=ft.FontWeight.W_600,
                        color=ft.Colors.with_opacity(0.85, TEXT)),
            ],
        )

        bar = ft.Container(
            height=44,
            bgcolor=ft.Colors.with_opacity(0.55, BG),
            border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.5, BORDER))),
            padding=ft.padding.only(left=16, right=8),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[brand, ft.Container(expand=True),
                          min_btn, max_btn, close_btn]),
        )
        return ft.WindowDragArea(bar, maximizable=True)

    def _lang_toggle(self) -> ft.Control:
        """Flag-based language selector (Italy / United Kingdom).

        The flags are DRAWN with Flet (no network images) so the toggle renders
        identically even offline and never waits on a download."""
        def flag_btn(code: str, flag: ft.Control) -> ft.Container:
            """Wrap a flag drawing in a clickable, animated pill."""
            return ft.Container(
                data=code, on_click=lambda e: self._set_lang(code),
                padding=3, border_radius=7, ink=True,
                animate=ft.Animation(140, ft.AnimationCurve.EASE_OUT),
                animate_opacity=140, content=flag,
                tooltip="Italiano" if code == "it" else "English",
            )
        self.lang_it = flag_btn("it", self._it_flag())
        self.lang_en = flag_btn("en", self._uk_flag())
        self._style_lang_pills()
        return ft.Row([self.lang_it, self.lang_en], spacing=8, tight=True)

    def _style_lang_pills(self) -> None:
        """Highlight the active flag (opaque + green ring), dim the other one."""
        for cont, code in ((self.lang_it, "it"), (self.lang_en, "en")):
            on = self.lang == code
            cont.opacity = 1.0 if on else 0.45
            cont.border = ft.border.all(2, GREEN_HI if on else ft.Colors.TRANSPARENT)
            cont.bgcolor = ft.Colors.with_opacity(0.10, GREEN) if on else None

    @staticmethod
    def _it_flag(w: int = 30, h: int = 20) -> ft.Control:
        """Italian tricolour: green / white / red, drawn as three stripes."""
        def stripe(color):
            return ft.Container(width=w / 3, height=h, bgcolor=color)
        return ft.Container(
            width=w, height=h, border_radius=3,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Row([stripe("#009246"), stripe("#FFFFFF"), stripe("#CE2B37")],
                           spacing=0),
        )

    @staticmethod
    def _uk_flag(w: int = 30, h: int = 20) -> ft.Control:
        """Stylized Union Jack (drawn on the canvas as layered lines/rects)."""
        white, red = "#FFFFFF", "#C8102E"
        pw = ft.Paint(stroke_width=4.5, color=white, style=ft.PaintingStyle.STROKE)
        pr = ft.Paint(stroke_width=1.8, color=red, style=ft.PaintingStyle.STROKE)
        fw = ft.Paint(color=white)
        fr = ft.Paint(color=red)
        shapes = [
            # White diagonals then red (St Andrew's/St Patrick's saltire).
            cv.Line(0, 0, w, h, paint=pw), cv.Line(w, 0, 0, h, paint=pw),
            cv.Line(0, 0, w, h, paint=pr), cv.Line(w, 0, 0, h, paint=pr),
            # White cross (St George) and then a red one on top.
            cv.Rect(w / 2 - 4.5, 0, 9, h, paint=fw),
            cv.Rect(0, h / 2 - 3, w, 6, paint=fw),
            cv.Rect(w / 2 - 2.5, 0, 5, h, paint=fr),
            cv.Rect(0, h / 2 - 1.5, w, 3, paint=fr),
        ]
        return ft.Container(
            width=w, height=h, border_radius=3, bgcolor="#012169",
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=cv.Canvas(shapes=shapes, width=w, height=h),
        )

    def _minimize(self) -> None:
        """Minimize the window (custom title bar replaces the OS button)."""
        self.page.window.minimized = True
        self.page.update()

    def _toggle_max(self) -> None:
        """Toggle maximize/restore from the custom title bar button."""
        self.page.window.maximized = not self.page.window.maximized
        self.page.update()

    def _on_window_event(self, e) -> None:
        """React to OS window events: swap the maximize icon, stop the background.

        We listen for maximize/unmaximize (which can also come from a double
        click on the drag area, not just our button) to keep the icon in sync,
        and for 'close' to signal the animation thread to exit cleanly."""
        data = getattr(e, "data", "")
        if data in ("maximize", "unmaximize"):
            maxed = data == "maximize"
            self.max_icon.name = (ft.Icons.FILTER_NONE if maxed
                                  else ft.Icons.CROP_SQUARE_OUTLINED)
            self.max_icon.size = 13 if maxed else 15
            self.page.update()
        elif data == "close":
            self._bg_stop = True

    # ------------------------------------------------------------ BACKGROUND FX
    def _side_pad(self) -> int:
        """Responsive side padding (~6% of width, clamped) so content stays centered."""
        w = self.page.width or self.page.window.width or 1040
        return int(max(20, min(180, w * 0.06)))

    def _on_resized(self, e=None) -> None:
        """Recompute the side padding when the window is resized."""
        pad = self._side_pad()
        self.content_holder.padding = ft.padding.only(left=pad, right=pad,
                                                       top=18, bottom=22)
        self.page.update()

    def _grid_layer(self) -> ft.Control:
        """Subtle, lightweight background: a dark gradient sky plus soft particles
        that drift slowly upward. No grid/skyline (professional look).

        Particle positions are stored as FRACTIONS of width/height so they scale
        with the window instead of having to be recomputed on every resize."""
        sky = ft.Container(
            expand=True,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_center, end=ft.alignment.bottom_center,
                colors=[BG, "#0B130E", BG],
                stops=[0.0, 0.55, 1.0]),
        )
        # Pre-computed particles (positions as fractions: they scale with the window).
        self._particles = [{"x": random.uniform(0, 1),
                            "sp": random.uniform(0.04, 0.10),
                            "ph": random.uniform(0, 1),
                            "r": random.uniform(1.0, 2.4)} for _ in range(26)]
        self._grid_canvas = cv.Canvas(expand=True)
        return ft.Stack([sky, self._grid_canvas], expand=True)

    def _start_grid(self) -> None:
        """Start the background animation on a daemon thread.

        Running it off the UI thread keeps the canvas breathing without ever
        blocking user interaction; the thread is a daemon so it dies with the app."""
        self._bg_stop = False
        threading.Thread(target=self._animate_grid, daemon=True).start()

    def _animate_grid(self) -> None:
        """Animate only the particles: light, slow, with a soft opacity breathing.

        Minimal cost (few shapes per frame). The loop exits when _bg_stop is set
        (window closing); a failed canvas.update() means the window was torn
        down, so we break silently rather than raise — Flet permits updating
        controls from this secondary thread."""
        t = 0.0
        while not getattr(self, "_bg_stop", False):
            W = self.page.width or self.page.window.width or 1040
            H = self.page.height or self.page.window.height or 900
            span = H * 1.1
            shapes: list = []
            for pt in self._particles:
                px = pt["x"] * W
                py = H - ((t * pt["sp"] + pt["ph"]) % 1.0) * span
                op = 0.20 * (0.5 + 0.5 * math.sin(t * 1.6 + pt["ph"] * 6.28))
                shapes.append(cv.Circle(px, py, pt["r"], paint=ft.Paint(
                    color=ft.Colors.with_opacity(op, GREEN_HI))))
            self._grid_canvas.shapes = shapes
            try:
                self._grid_canvas.update()
            except Exception:
                # The window was closed (event loop gone / canvas no longer
                # mounted): exit silently, this is not an error.
                break
            time.sleep(0.08)
            t += 0.08

    # --------------------------------------------------------------- COMPONENTS
    def _header(self) -> ft.Control:
        """App header: logo, title, localized subtitle and the language toggle."""
        logo = ft.Container(
            width=64, height=64, border_radius=18,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                colors=[GREEN_HI, GREEN_DK]),
            alignment=ft.alignment.center,
            shadow=ft.BoxShadow(blur_radius=24, spread_radius=-2,
                                color=ft.Colors.with_opacity(0.45, GREEN)),
            content=ft.Icon(ft.Icons.GRAPHIC_EQ, color="#06140C", size=34),
        )
        title = ft.Column(
            spacing=2,
            controls=[
                ft.Text("EchoScript", size=30, weight=ft.FontWeight.BOLD, color=TEXT),
                self._T("header_sub", size=13, color=MUTED),
            ],
        )
        return ft.Container(
            padding=ft.padding.only(bottom=2),
            content=ft.Row(
                [logo, title, ft.Container(expand=True), self._lang_toggle()],
                spacing=18, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

    def _card(self, *controls, **kwargs) -> ft.Container:
        """Generic surface card (rounded, bordered) wrapping a tight column.

        Factored out because both configuration steps share the exact same
        chrome; extra kwargs (e.g. the fixed height) are forwarded to the
        container. The inner column is scrollable so that, on a small window or
        when the card holds many fields (Groq + DeepL keys), content never clips."""
        return ft.Container(
            bgcolor=SURFACE, border=ft.border.all(1, BORDER), border_radius=16,
            padding=18,
            content=ft.Column(list(controls), spacing=11, tight=True,
                              scroll=ft.ScrollMode.AUTO),
            **kwargs,
        )

    def _card_title(self, step: str, text_key: str) -> ft.Control:
        """Card title row: a numbered badge plus a registered localized heading."""
        badge = ft.Container(
            width=26, height=26, border_radius=8,
            bgcolor=ft.Colors.with_opacity(0.15, GREEN),
            border=ft.border.all(1, ft.Colors.with_opacity(0.4, GREEN)),
            alignment=ft.alignment.center,
            content=ft.Text(step, size=13, weight=ft.FontWeight.BOLD, color=GREEN_HI),
        )
        return ft.Row(
            [badge, self._T(text_key, size=16, weight=ft.FontWeight.W_600, color=TEXT)],
            spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _select_card(self, group: str, key: str, icon: str, name_key: str,
                     desc_key: str, tag: str | None = None) -> ft.Container:
        """Build a clickable selectable option card (a radio-like tile).

        'group'/'key' are stashed in the control's data along with its check
        icon so a single handler (_on_select_card) can identify which option was
        picked and _sync_select_visuals can toggle the selected styling."""
        name_row = [self._T(name_key, size=14, weight=ft.FontWeight.W_600, color=TEXT)]
        if tag:
            name_row.append(ft.Container(
                bgcolor=ft.Colors.with_opacity(0.18, GREEN),
                border_radius=6, padding=ft.padding.symmetric(horizontal=7, vertical=1),
                content=ft.Text(tag, size=10, weight=ft.FontWeight.BOLD, color=GREEN_HI)))
        check = ft.Icon(ft.Icons.CHECK_CIRCLE, color=GREEN_HI, size=18, visible=False)

        return ft.Container(
            data={"group": group, "key": key, "check": check},
            on_click=self._on_select_card,
            border_radius=14, padding=13, bgcolor=SURFACE2,
            border=ft.border.all(1, BORDER),
            animate=ft.Animation(160, ft.AnimationCurve.EASE_OUT),
            ink=True, expand=True,
            content=ft.Column(
                spacing=4,
                controls=[
                    ft.Row([
                        ft.Container(
                            width=34, height=34, border_radius=9,
                            bgcolor=ft.Colors.with_opacity(0.10, GREEN),
                            alignment=ft.alignment.center,
                            content=ft.Icon(icon, color=GREEN_HI, size=19)),
                        ft.Container(expand=True),
                        check,
                    ]),
                    ft.Row(name_row, spacing=8),
                    self._T(desc_key, size=11, color=MUTED),
                ],
            ),
        )

    def _step_backend(self) -> ft.Control:
        """Step 1 card: choose the backend (local vs Groq) + its dependent fields.

        The local model dropdown and the Groq key loader are both created here
        but only one is shown at a time (see _sync_fields), so switching backend
        does not rebuild the card."""
        self.bc_local = self._select_card(
            "backend", "local", ft.Icons.LOCK_OUTLINE,
            "backend_local_name", "backend_local_desc")
        self.bc_groq = self._select_card(
            "backend", "groq", ft.Icons.BOLT,
            "backend_groq_name", "backend_groq_desc", tag="CLOUD")

        self.model_dd = ft.Dropdown(
            value="small",
            options=[ft.dropdown.Option(k, self.t(tk)) for k, tk in _LOCAL_MODELS],
            border_color=BORDER, focused_border_color=GREEN,
            color=TEXT, label_style=ft.TextStyle(color=MUTED),
            bgcolor=SURFACE2, filled=True, border_radius=10,
        )
        self._reg(self.model_dd, "label", "model_label")
        self.model_field = ft.Container(content=self.model_dd)

        self.key_field = ft.Container(
            visible=False,
            content=ft.Column(
                spacing=8,
                controls=[
                    self._T("key_field_label", size=13, color=MUTED,
                            weight=ft.FontWeight.W_500),
                    self._key_loader(),
                ],
            ),
        )

        return self._card(
            self._card_title("1", "step1_title"),
            ft.Row([self.bc_local, self.bc_groq], spacing=14),
            self.model_field,
            self.key_field,
        )

    def _rebuild_model_options(self) -> None:
        """Rewrite the model dropdown descriptions in the current language.

        The selected value is saved and restored because replacing the options
        list would otherwise reset the dropdown's current selection."""
        val = self.model_dd.value
        self.model_dd.options = [ft.dropdown.Option(k, self.t(tk)) for k, tk in _LOCAL_MODELS]
        self.model_dd.value = val

    # --- Groq API key loader from a .txt file (TRANSCRIPTION) --------------
    def _key_loader(self) -> ft.Control:
        """Build the Groq key-loading widget (load button + get-key link).

        The Groq key is used ONLY for cloud transcription now (translation uses
        DeepL, loaded separately). Its status label is appended to a list and
        refreshed wherever a key change must be reflected (see _refresh_key_status)."""
        status = ft.Text(
            self._key_status_text(), size=12,
            color=GREEN_HI if self.loaded_api_key else MUTED)
        self._key_status_labels.append(status)

        load_btn = ft.OutlinedButton(
            icon=ft.Icons.UPLOAD_FILE, on_click=lambda e: self._pick_key(),
            style=ft.ButtonStyle(
                color=GREEN_HI, side=ft.BorderSide(1, BORDER_HI),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=14, vertical=14)))
        self._reg(load_btn, "text", "load_key")

        get_btn = ft.TextButton(
            on_click=lambda e: self._open_url("https://console.groq.com/keys"),
            style=ft.ButtonStyle(color=GREEN_HI))
        self._reg(get_btn, "text", "get_key")

        # "Mostra crediti API Groq": reads the remaining transcription budget from
        # the Groq rate-limit headers (a tiny test request) and lists it in a dialog.
        self.credits_btn = ft.OutlinedButton(
            icon=ft.Icons.SAVINGS_OUTLINED, on_click=lambda e: self._show_credits(),
            style=ft.ButtonStyle(
                color=GREEN_HI, side=ft.BorderSide(1, BORDER_HI),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=14, vertical=14)))
        self._reg(self.credits_btn, "text", "limits_btn")

        return ft.Column(
            spacing=8,
            controls=[
                ft.Row([load_btn, get_btn, self.credits_btn], spacing=10, wrap=True),
                status,
            ],
        )

    def _key_status_text(self) -> str:
        """Status line under the Groq key loader: which file is loaded, or a hint."""
        if self.loaded_api_key:
            return self.t("key_loaded").format(name=self.loaded_api_key_name)
        return self.t("key_none")

    def _refresh_key_status(self) -> None:
        """Update every Groq key-status label after a key change/lang switch."""
        for lbl in self._key_status_labels:
            lbl.value = self._key_status_text()
            lbl.color = GREEN_HI if self.loaded_api_key else MUTED

    # --- Groq credits / rate limits --------------------------------------
    @staticmethod
    def _fmt_duration_short(seconds: float) -> str:
        """Compact human duration: '2h 5m', '3m 20s', '45s'."""
        s = int(round(seconds or 0))
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        parts = []
        if h:
            parts.append(f"{h}h")
        if m:
            parts.append(f"{m}m")
        if sec or not parts:
            parts.append(f"{sec}s")
        return " ".join(parts)

    def _reset_clock_label(self, iso: str | None) -> str:
        """Localized absolute reset instant from an ISO timestamp: 'alle HH:MM' if
        today, 'domani alle HH:MM' if tomorrow, otherwise 'il dd/mm alle HH:MM'.
        Empty string if 'iso' is missing/unparseable."""
        if not iso:
            return ""
        import datetime as _dt
        try:
            when = _dt.datetime.fromisoformat(iso)
        except Exception:
            return ""
        today = _dt.date.today()
        hm = when.strftime("%H:%M")
        if when.date() == today:
            return self.t("lim_reset_today").format(hm=hm)
        if when.date() == today + _dt.timedelta(days=1):
            return self.t("lim_reset_tomorrow").format(hm=hm)
        return self.t("lim_reset_date").format(dm=when.strftime("%d/%m"), hm=hm)

    def _fmt_reset(self, item: dict) -> str:
        """Localized 'resets <when> (in …)' line for one limit group, where <when>
        is the exact wall-clock instant (with the day when not today)."""
        sec = item.get("reset_seconds")
        if sec is None:
            return ""
        dur = self._fmt_duration_short(sec)
        clock = self._reset_clock_label(item.get("reset_at_iso"))
        if clock:
            return self.t("lim_reset_at").format(clock=clock, dur=dur)
        return self.t("lim_reset_in").format(dur=dur)

    def _fmt_limit_value(self, item: dict) -> str:
        """Localized 'remaining / limit' line; audio is shown as mm:ss durations."""
        rem, lim, kind = item.get("remaining"), item.get("limit"), item.get("kind")
        def one(v):
            if v is None:
                return "?"
            if kind == "audio_seconds":
                return tx._format_timestamp(v)
            return f"{int(v):,}".replace(",", ".")
        if lim is not None:
            return self.t("lim_remaining").format(rem=one(rem), lim=one(lim))
        return self.t("lim_remaining_only").format(rem=one(rem))

    def _show_credits(self) -> None:
        """Mostra i crediti Groq residui PER MODELLO.

        Letti dalla cache che le richieste reali (trascrizione, riassunto, analisi
        visiva) hanno già popolato: NON contatta Groq e NON consuma alcun credito,
        quindi è istantaneo (niente thread/rete) e cliccabile quanto si vuole. Se
        non è ancora stata fatta alcuna chiamata Groq, la cache è vuota e la
        finestra lo spiega."""
        self._hide_error()
        self._open_credits_dialog(engine.get_cached_credits())

    def _open_credits_dialog(self, models: list[dict]) -> None:
        """Build and open the credits dialog: a SECTION per Groq model (transcription,
        summary, vision), each with one card per limit group. Data comes from the
        passive cache — no API call, no credit spent (see _show_credits)."""
        rows: list[ft.Control] = [
            self._T_one(self.t("lim_free_note"), size=12, color=MUTED),
            ft.Divider(height=1, color=BORDER),
        ]
        if not models:
            # Cache ancora vuota: nessuna richiesta Groq fatta in questa sessione.
            rows.append(ft.Text(self.t("lim_no_data"), size=13, color=WARN, no_wrap=False))
        for m in models:
            role = m.get("role", "other")
            role_label = self.t(f"lim_role_{role}") if f"lim_role_{role}" in T[self.lang] else role
            # Intestazione del modello: ruolo + id modello + ora di aggiornamento.
            rows.append(ft.Column(spacing=1, tight=True, controls=[
                ft.Text(role_label, size=14, weight=ft.FontWeight.W_700, color=TEXT),
                ft.Text(f"{m.get('model', '')} · {self.t('lim_checked_at').format(v=m.get('checked_at', '—'))}",
                        size=11, color=MUTED),
            ]))
            items = m.get("items") or []
            if not items:
                rows.append(ft.Text(self.t("lim_none"), size=12, color=MUTED))
            for it in items:
                kind = it.get("kind", "")
                rows.append(ft.Container(
                    border_radius=12, padding=14, bgcolor=SURFACE2,
                    border=ft.border.all(1, BORDER),
                    content=ft.Row(
                        spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=38, height=38, border_radius=10,
                                alignment=ft.alignment.center,
                                bgcolor=ft.Colors.with_opacity(0.12, GREEN),
                                content=ft.Icon(self._credit_icon(kind), color=GREEN_HI, size=20)),
                            ft.Column(spacing=2, tight=True, expand=True, controls=[
                                ft.Text(self.t(f"lim_kind_{kind}") if f"lim_kind_{kind}" in T[self.lang] else kind,
                                        size=14, weight=ft.FontWeight.W_600, color=TEXT),
                                ft.Text(self._fmt_limit_value(it), size=13, color=GREEN_HI,
                                        weight=ft.FontWeight.W_600),
                                ft.Text(self._fmt_reset(it), size=11, color=MUTED) if self._fmt_reset(it)
                                else ft.Container(height=0),
                            ]),
                        ])))
        close = ft.FilledButton(
            self.t("btn_close"), icon=ft.Icons.CHECK,
            on_click=lambda e: self.page.close(self.credits_dialog),
            style=ft.ButtonStyle(bgcolor=GREEN, color="#06140C",
                                 shape=ft.RoundedRectangleBorder(radius=10),
                                 padding=ft.padding.symmetric(horizontal=18, vertical=16)))
        self.credits_dialog = ft.AlertDialog(
            modal=True, bgcolor=SURFACE, shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row([ft.Icon(ft.Icons.SAVINGS_OUTLINED, color=GREEN_HI, size=22),
                          ft.Text(self.t("lim_title"), size=18,
                                  weight=ft.FontWeight.W_600, color=TEXT)], spacing=10),
            content=ft.Container(
                width=440,
                content=ft.Column(rows, spacing=12, tight=True, scroll=ft.ScrollMode.AUTO)),
            actions=[close], actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.update()
        self.page.open(self.credits_dialog)

    @staticmethod
    def _credit_icon(kind: str) -> str:
        """Icon per limit group."""
        return {"audio_seconds": ft.Icons.GRAPHIC_EQ,
                "requests": ft.Icons.SWAP_VERT,
                "tokens": ft.Icons.TOKEN_OUTLINED}.get(kind, ft.Icons.SPEED)

    def _T_one(self, text: str, **kw) -> ft.Text:
        """A plain ft.Text (NOT registered for i18n): used for already-localized,
        formatted strings that are rebuilt each time the dialog opens."""
        return ft.Text(text, **kw)

    def _pick_key(self) -> None:
        """Open the file picker to choose the .txt holding the Groq key."""
        self._hide_error()
        self.key_picker.pick_files(
            dialog_title=self.t("pick_key_dialog"),
            allow_multiple=False, allowed_extensions=["txt"])

    def _on_key_picked(self, e: ft.FilePickerResultEvent) -> None:
        """File-picker callback: read the chosen file and extract a usable Groq key.

        Read with utf-8-sig so a BOM (common on Windows-saved .txt) is stripped.
        Failures and empty/invalid files surface a clear error instead of
        silently leaving the app keyless."""
        if not e.files:
            return
        path = e.files[0].path
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                raw = f.read()
        except Exception as ex:
            self._show_error(self.t("err_key_read").format(e=ex))
            return
        key = self._extract_key(raw)
        if not key:
            self._show_error(self.t("err_key_invalid"))
            return
        self.loaded_api_key = key
        self.loaded_api_key_name = os.path.basename(path)
        self._refresh_key_status()
        self._update_run_state()
        self.page.update()

    @staticmethod
    def _extract_key(raw: str) -> str:
        """Pull the API key out of a .txt that may be a plain key or .env-style.

        Skips blank lines and comments; if a line looks like KEY=value it keeps
        the value side, and strips surrounding quotes. Returns the first usable
        token, or '' if none is found."""
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                line = line.split("=", 1)[1]
            line = line.strip().strip('"').strip("'").strip()
            if line:
                return line
        return ""

    def _toggle_row(self, icon: str, name_key: str, desc_key: str,
                    switch: ft.Switch) -> ft.Control:
        """One option row: icon + localized name/description + a trailing switch."""
        return ft.Row(
            spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=34, height=34, border_radius=9,
                    bgcolor=ft.Colors.with_opacity(0.10, GREEN),
                    alignment=ft.alignment.center,
                    content=ft.Icon(icon, color=GREEN_HI, size=19)),
                ft.Column(spacing=1, tight=True, expand=True, controls=[
                    self._T(name_key, size=14, weight=ft.FontWeight.W_600, color=TEXT),
                    self._T(desc_key, size=11, color=MUTED),
                ]),
                switch,
            ])

    def _options_card(self) -> ft.Control:
        """Extra-output card: toggles for the Italian translation and the summary.

        Both default OFF so a plain transcription run is unchanged. Their value is
        read straight off the switches when a run starts (see _start_transcription)."""
        self.sw_translate = ft.Switch(
            value=False, active_color=GREEN, scale=0.9,
            on_change=lambda e: self.page.update())
        self.sw_summary = ft.Switch(
            value=False, active_color=GREEN, scale=0.9,
            on_change=lambda e: self.page.update())
        self.sw_visual = ft.Switch(
            value=False, active_color=GREEN, scale=0.9,
            on_change=lambda e: self.page.update())
        return self._card(
            self._card_title("3", "opts_title"),
            self._toggle_row(ft.Icons.TRANSLATE, "opt_translate_name",
                             "opt_translate_desc", self.sw_translate),
            ft.Divider(height=1, color=BORDER),
            self._toggle_row(ft.Icons.AUTO_STORIES, "opt_summary_name",
                             "opt_summary_desc", self.sw_summary),
            ft.Divider(height=1, color=BORDER),
            self._toggle_row(ft.Icons.VISIBILITY, "opt_visual_name",
                             "opt_visual_desc", self.sw_visual),
        )

    def _step_source(self) -> ft.Control:
        """Step 2 card: choose the source (YouTube URL vs local file) + its inputs.

        Both panels (URL field + confirm, and file picker + info box) are created
        here and toggled by _sync_fields, so switching source never rebuilds the card."""
        self.sc_youtube = self._select_card(
            "source", "youtube", ft.Icons.SMART_DISPLAY_OUTLINED,
            "source_youtube_name", "source_youtube_desc")
        self.sc_local = self._select_card(
            "source", "local", ft.Icons.MIC_NONE,
            "source_local_name", "source_local_desc")

        self.url_tf = ft.TextField(
            expand=True, border_color=BORDER, focused_border_color=GREEN,
            color=TEXT, bgcolor=SURFACE2, filled=True, border_radius=10,
            on_submit=lambda e: self._load_info(),
            on_change=lambda e: self._on_url_change(),
        )
        self._reg(self.url_tf, "hint_text", "url_hint")
        self.load_btn = ft.OutlinedButton(
            icon=ft.Icons.SEARCH, on_click=lambda e: self._load_info(),
            style=ft.ButtonStyle(
                color=GREEN_HI, side=ft.BorderSide(1, BORDER_HI),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=16, vertical=18)))
        self._reg(self.load_btn, "text", "load_info")
        # The video info appears in a confirmation window (see _show_yt_confirm).
        # Down here only a confirmation label remains.
        self.yt_confirmed = ft.Text("", size=12, color=GREEN_HI,
                                    weight=ft.FontWeight.W_500, visible=False,
                                    no_wrap=False)
        self.yt_panel = ft.Column(
            spacing=10,
            controls=[
                ft.Row([self.url_tf, self.load_btn], spacing=10),
                self.yt_confirmed,
            ],
        )

        self.pick_btn = ft.OutlinedButton(
            icon=ft.Icons.FOLDER_OPEN, on_click=lambda e: self._pick_file(),
            style=ft.ButtonStyle(
                color=GREEN_HI, side=ft.BorderSide(1, BORDER_HI),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=16, vertical=18)))
        self._reg(self.pick_btn, "text", "pick_file")
        self.file_box = self._info_box()
        self.local_panel = ft.Column(
            visible=False, spacing=12,
            controls=[self.pick_btn, self.file_box],
        )

        return self._card(
            self._card_title("2", "step2_title"),
            ft.Row([self.sc_youtube, self.sc_local], spacing=14),
            self.yt_panel,
            self.local_panel,
        )

    def _info_box(self) -> ft.Container:
        """Compact info card: cover on the left, data on the right.

        Its sub-controls (title, grid, thumbnail) are stashed in `data` so
        _fill_info_box can repopulate the same widget later instead of rebuilding it."""
        thumb = ft.Image(fit=ft.ImageFit.COVER, width=200, height=112, border_radius=8)
        thumb_wrap = ft.Container(
            visible=False, width=200, height=112, border_radius=8,
            border=ft.border.all(1, ft.Colors.with_opacity(0.25, GREEN)),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS, content=thumb,
        )
        title = ft.Text("", size=14, weight=ft.FontWeight.W_600, color=TEXT, no_wrap=False)
        grid = ft.Row(wrap=True, spacing=20, run_spacing=8)
        text_col = ft.Column([title, grid], spacing=10, tight=True, expand=True)
        return ft.Container(
            visible=False,
            bgcolor=ft.Colors.with_opacity(0.04, GREEN),
            border=ft.border.all(1, ft.Colors.with_opacity(0.18, GREEN)),
            border_radius=12, padding=14,
            content=ft.Row([thumb_wrap, text_col], spacing=14,
                           vertical_alignment=ft.CrossAxisAlignment.START),
            data={"title": title, "grid": grid, "thumb": thumb, "thumb_wrap": thumb_wrap},
        )

    def _fill_info_box(self, box: ft.Container, title: str, pairs: list,
                       thumbnail: str | None = None) -> None:
        """Populate an info box with a title, a list of (icon, label, value) rows
        and an optional cover, then make it visible.

        Reuses the controls cached in box.data so re-filling (e.g. on language
        change) does not allocate a new widget tree."""
        box.data["title"].value = title
        thumb, wrap = box.data["thumb"], box.data["thumb_wrap"]
        if thumbnail:
            thumb.src = thumbnail
            wrap.visible = True
        else:
            wrap.visible = False
        box.data["grid"].controls = [
            ft.Row(
                spacing=6, tight=True,
                controls=[
                    ft.Icon(icon, size=15, color=MUTED),
                    ft.Text(f"{label}:", size=12, color=MUTED),
                    ft.Text(str(value), size=12, color=TEXT, weight=ft.FontWeight.W_500),
                ],
            )
            for icon, label, value in pairs
        ]
        box.visible = True

    def _yt_pairs(self, meta: dict) -> list:
        """(icon, label, value) pairs for a YouTube video, in the current language.

        Optional metadata (likes, subscribers, category, language) appear only
        when present, so the info box never shows empty/unknown fields."""
        pairs = [
            (ft.Icons.PERSON_OUTLINE, self.t("info_channel"), meta["channel"]),
            (ft.Icons.VISIBILITY_OUTLINED, self.t("info_views"), tx._format_views(meta["views"])),
            (ft.Icons.CALENDAR_TODAY, self.t("info_date"), tx._format_upload_date(meta["upload_date"])),
            (ft.Icons.SCHEDULE, self.t("info_duration"), tx._format_duration(meta["duration"])),
        ]
        if meta.get("likes") is not None:
            pairs.append((ft.Icons.THUMB_UP_OUTLINED, self.t("info_likes"),
                          tx._format_views(meta["likes"])))
        if meta.get("subscribers") is not None:
            pairs.append((ft.Icons.GROUP_OUTLINED, self.t("info_subs"),
                          tx._format_views(meta["subscribers"])))
        if meta.get("category"):
            pairs.append((ft.Icons.LOCAL_OFFER_OUTLINED, self.t("info_category"),
                          meta["category"]))
        lang_name = self._lang_name(meta.get("detected_language") or meta.get("language"))
        if lang_name:
            pairs.append((ft.Icons.LANGUAGE, self.t("info_language"), lang_name))
        chapters = (self.t("chapters_some").format(n=len(meta["chapters"]))
                    if meta["chapters"] else self.t("chapters_none"))
        pairs.append((ft.Icons.LIST_ALT, self.t("info_chapters"), chapters))
        return pairs

    def _lang_name(self, code: str | None) -> str | None:
        """Readable (localized) name of a language. Accepts both ISO codes
        (faster-whisper: 'en') and full Whisper names (Groq: 'english'). None if absent.

        The dual-format handling exists because the two backends report the
        detected language differently; we normalize to a 2-letter code first."""
        if not code:
            return None
        c = code.split("-")[0].strip().lower()
        # Normalize Whisper's full language names to the 2-letter ISO code.
        full = {"italian": "it", "english": "en", "spanish": "es",
                "french": "fr", "german": "de"}
        c = full.get(c, c)
        names = {
            "it": {"it": "Italiano", "en": "Inglese", "es": "Spagnolo",
                   "fr": "Francese", "de": "Tedesco"},
            "en": {"it": "Italian", "en": "English", "es": "Spanish",
                   "fr": "French", "de": "German"},
        }
        return names.get(self.lang, names["it"]).get(c, code.upper())

    def _local_pairs(self, meta: dict, path: str) -> list:
        """(icon, label, value) pairs for a local file: file name, duration, estimate."""
        return [
            (ft.Icons.AUDIO_FILE, self.t("info_file"), os.path.basename(path)),
            (ft.Icons.SCHEDULE, self.t("info_duration"), tx._format_duration(meta["duration"])),
            (ft.Icons.SAVINGS_OUTLINED, "≈", self._estimate_text(meta)),
        ]

    def _estimate_text(self, meta: dict) -> str:
        """Localized pre-run estimate line (Groq cost or local time) for a source."""
        est = tx.estimate_job(meta, self.backend, self.model_dd.value)
        if est["backend"] == "groq":
            return self.t("est_cost").format(c=f"{est['cost_usd']:.3f}", m=tx.GROQ_MODEL)
        dev = "GPU" if est.get("device") == "cuda" else "CPU"
        return self.t("est_time").format(t=tx._format_duration(est["seconds"]), d=dev)

    def _estimate_chip(self, meta: dict) -> ft.Control:
        """A small highlighted row showing the pre-run estimate (used in dialogs)."""
        return ft.Container(
            border_radius=8, padding=ft.padding.symmetric(horizontal=10, vertical=8),
            bgcolor=ft.Colors.with_opacity(0.07, GREEN),
            content=ft.Row(spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                ft.Icon(ft.Icons.SAVINGS_OUTLINED, size=15, color=GREEN_HI),
                ft.Text(self._estimate_text(meta), size=12, color=TEXT, no_wrap=False),
            ]))

    def _refresh_info_boxes(self) -> None:
        """Rewrite already-loaded info in the new language (YouTube confirm label
        + local-file box).

        Only touches boxes that currently hold data, so a language switch before
        anything is loaded is a no-op."""
        if self._yt_meta and self.yt_confirmed.visible:
            self.yt_confirmed.value = self.t("yt_confirmed").format(
                title=self._yt_meta["title"])
        if self._local_meta and self.local_path:
            self._fill_info_box(self.file_box, self._local_meta["title"],
                                self._local_pairs(self._local_meta, self.local_path))

    def _build_warn_dialog(self) -> None:
        """Build (once) the amber modal that explains what is missing to start a run.

        It pops up on clicking "Transcribe" when the requirements are not met,
        rather than living as a permanent banner; only its bullet list (warn_body)
        is filled per click in _show_warn."""
        self._warn_prefix = self._T("warn_prefix", size=13, color=TEXT, no_wrap=False)
        self.warn_body = ft.Column(spacing=8, tight=True)
        self._warn_title = self._T("warn_title", size=18, weight=ft.FontWeight.W_600,
                                   color=WARN)
        close_btn = ft.FilledButton(
            icon=ft.Icons.CHECK,
            on_click=lambda e: self.page.close(self.warn_dialog),
            style=ft.ButtonStyle(
                bgcolor=WARN, color="#1A1206",
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=18, vertical=16)))
        self._reg(close_btn, "text", "btn_close")
        self.warn_dialog = ft.AlertDialog(
            modal=True, bgcolor=SURFACE,
            shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row([
                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=WARN, size=22),
                self._warn_title,
            ], spacing=10),
            content=ft.Container(
                width=440,
                content=ft.Column([self._warn_prefix, self.warn_body], spacing=12, tight=True)),
            actions=[close_btn],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def _missing_list(self) -> list:
        """List of what is missing to enable "Transcribe" (empty if all set)."""
        missing = []
        if not self._key_ready():
            missing.append(self.t("need_key"))
        if not self._source_ready():
            missing.append(self.t("need_src_yt") if self.source == "youtube"
                           else self.t("need_src_local"))
        return missing

    def _show_warn(self, items: list) -> None:
        """Show the warning with the missing requirements as a bullet list."""
        self.warn_body.controls = [
            ft.Row(spacing=10, vertical_alignment=ft.CrossAxisAlignment.START,
                   controls=[
                       ft.Container(padding=ft.padding.only(top=6),
                                    content=ft.Icon(ft.Icons.CIRCLE, size=7, color=WARN)),
                       ft.Text(item, size=13, color=TEXT, no_wrap=False, expand=True),
                   ])
            for item in items
        ]
        self.page.open(self.warn_dialog)

    def _cta_button(self) -> ft.Control:
        """Build the primary "Transcribe" call-to-action button (gradient pill).

        Stored on self so its label/icon/opacity can be toggled to reflect the
        busy state and whether a run is currently allowed."""
        self.cta_icon = ft.Icon(ft.Icons.AUTO_AWESOME, color="#06140C", size=22)
        self.cta_text = ft.Text(self.t("cta_run"), size=17, weight=ft.FontWeight.BOLD,
                                color="#06140C")
        self.cta = ft.Container(
            on_click=self._on_run,
            height=58, border_radius=14, ink=True, alignment=ft.alignment.center,
            gradient=ft.LinearGradient(
                begin=ft.alignment.center_left, end=ft.alignment.center_right,
                colors=[GREEN_HI, GREEN]),
            shadow=ft.BoxShadow(blur_radius=22, spread_radius=-4,
                                color=ft.Colors.with_opacity(0.5, GREEN)),
            animate_opacity=160,
            content=ft.Row([self.cta_icon, self.cta_text], spacing=10,
                           alignment=ft.MainAxisAlignment.CENTER),
        )
        return self.cta

    # Phases that can appear in the progress checklist, each with its icon.
    _PHASE_ICONS = {
        "info": ft.Icons.INFO_OUTLINE,
        "download": ft.Icons.DOWNLOADING,
        "prepare": ft.Icons.GRAPHIC_EQ,
        "transcribe": ft.Icons.RECORD_VOICE_OVER,
        "export": ft.Icons.SAVE_OUTLINED,
        "translate": ft.Icons.TRANSLATE,
        "summarize": ft.Icons.AUTO_STORIES,
    }

    def _build_progress_dialog(self) -> None:
        """Build (once) the dedicated, elegant progress WINDOW (a modal dialog).

        It shows: the engine badge, the current phase with a spinner + percentage,
        the global bar, a live detail line, a step-by-step CHECKLIST (built per run
        from the phase plan, so it mirrors the chosen options), and a short
        narration of what is happening / what comes next. The worker thread opens
        it via _show_progress(True) and closes it when done."""
        self.prog_phase = ft.Text(self.t("phase_default"), size=15,
                                  weight=ft.FontWeight.W_600, color=TEXT)
        # Phase counter on the right (e.g. "Phase 2/5"), in a green pill.
        self.prog_step = ft.Container(
            visible=False, border_radius=8,
            padding=ft.padding.symmetric(horizontal=10, vertical=3),
            bgcolor=ft.Colors.with_opacity(0.12, GREEN),
            border=ft.border.all(1, ft.Colors.with_opacity(0.35, GREEN)),
            content=ft.Text("", size=12, color=GREEN_HI, weight=ft.FontWeight.W_700))
        self.prog_pct = ft.Text("", size=14, color=GREEN_HI, weight=ft.FontWeight.BOLD)
        self.prog_bar = ft.ProgressBar(
            value=0, color=GREEN, bgcolor=SURFACE2, border_radius=8, height=8)
        self.prog_detail = ft.Text("", size=12, color=MUTED, no_wrap=False)
        # "Engine in use" badge (Groq cloud / Local CPU).
        self.prog_engine_icon = ft.Icon(ft.Icons.MEMORY, size=16, color=GREEN_HI)
        self.prog_engine_text = ft.Text("", size=12, weight=ft.FontWeight.W_700, color=GREEN_HI)
        self.prog_engine = ft.Container(
            border_radius=8, padding=ft.padding.symmetric(horizontal=10, vertical=5),
            content=ft.Row([self.prog_engine_icon, self.prog_engine_text], spacing=8,
                           tight=True))
        self.prog_engine_hint = ft.Text("", size=11, color=WARN, visible=False, no_wrap=False)

        # Step checklist + narration (filled per run by _init_progress).
        self.prog_steps_col = ft.Column(spacing=8, tight=True)
        self._step_ctrls = {}        # phase -> {"icon": ft.Icon, "label": ft.Text}
        self.prog_plan = ft.Text("", size=12, color=MUTED, no_wrap=False)
        self.prog_narration = ft.Text("", size=13, color=TEXT, no_wrap=False,
                                      weight=ft.FontWeight.W_500)
        narration_box = ft.Container(
            border_radius=12, padding=14,
            bgcolor=ft.Colors.with_opacity(0.05, GREEN),
            border=ft.border.all(1, ft.Colors.with_opacity(0.18, GREEN)),
            content=ft.Row(spacing=10, vertical_alignment=ft.CrossAxisAlignment.START,
                           controls=[
                               ft.Icon(ft.Icons.AUTO_AWESOME, size=16, color=GREEN_HI),
                               ft.Column([self.prog_narration, self.prog_plan],
                                         spacing=4, tight=True, expand=True),
                           ]))

        self.progress_dialog = ft.AlertDialog(
            modal=True, bgcolor=SURFACE, shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row([ft.Icon(ft.Icons.GRAPHIC_EQ, color=GREEN_HI, size=22),
                          self._T("prog_title", size=18, weight=ft.FontWeight.W_600,
                                  color=TEXT)], spacing=10),
            content=ft.Container(
                width=480,
                content=ft.Column(
                    spacing=14, tight=True, scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Row([self.prog_engine], tight=True),
                        self.prog_engine_hint,
                        ft.Row([
                            ft.ProgressRing(width=18, height=18, stroke_width=2.5, color=GREEN),
                            self.prog_phase,
                            ft.Container(expand=True),
                            self.prog_step,
                            self.prog_pct,
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                        self.prog_bar,
                        self.prog_detail,
                        ft.Divider(height=1, color=BORDER),
                        self._T("prog_steps_title", size=12, color=MUTED,
                                weight=ft.FontWeight.W_600),
                        self.prog_steps_col,
                        narration_box,
                    ],
                ),
            ),
        )

    def _join_human(self, items: list[str]) -> str:
        """Join phrases as 'a, b <join> c' using the localized final conjunction."""
        items = [s for s in items if s]
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return ", ".join(items[:-1]) + self.t("ov_join") + items[-1]

    def _init_progress(self, options: dict) -> None:
        """Prepare the progress window for a fresh run: build the step checklist
        from self._plan and compose the localized 'plan' sentence from the options.

        Called right before the dialog opens so the checklist mirrors exactly the
        phases (and optional translate/summary steps) that will actually run."""
        # Reset bar/labels.
        self.prog_bar.value = 0
        self.prog_pct.value = ""
        self.prog_detail.value = ""
        self.prog_narration.value = self.t("narr_info")

        # Build one checklist row per planned phase.
        self._step_ctrls = {}
        rows = []
        for ph in self._plan:
            icon = ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED, size=18, color=MUTED)
            label = ft.Text(self.t("phase_" + ph) if ("phase_" + ph) in T[self.lang]
                            else ph, size=13, color=MUTED)
            self._step_ctrls[ph] = {"icon": icon, "label": label}
            rows.append(ft.Row([icon, label], spacing=10,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER))
        self.prog_steps_col.controls = rows

        # Compose the 'plan' sentence from the chosen options.
        parts = [self.t("ov_base")]
        if options.get("visual"):
            parts.append(self.t("ov_visual"))
        if options.get("translate"):
            parts.append(self.t("ov_translate"))
        if options.get("summarize"):
            parts.append(self.t("ov_summary"))
        parts.append(self.t("ov_save"))
        sentence = self._join_human(parts)
        sentence = sentence[:1].upper() + sentence[1:] + "."
        self.prog_plan.value = f"{self.t('prog_plan_label')} {sentence}"

    def _update_steps(self, current_phase: str) -> None:
        """Refresh the checklist icons/colors: done = ✓, current = ●, pending = ○."""
        plan = self._plan
        cur_i = plan.index(current_phase) if current_phase in plan else -1
        for idx, ph in enumerate(plan):
            ctrl = self._step_ctrls.get(ph)
            if not ctrl:
                continue
            if cur_i >= 0 and idx < cur_i:
                ctrl["icon"].name = ft.Icons.CHECK_CIRCLE
                ctrl["icon"].color = GREEN
                ctrl["label"].color = MUTED
                ctrl["label"].weight = ft.FontWeight.W_400
            elif idx == cur_i:
                ctrl["icon"].name = ft.Icons.RADIO_BUTTON_CHECKED
                ctrl["icon"].color = GREEN_HI
                ctrl["label"].color = TEXT
                ctrl["label"].weight = ft.FontWeight.W_700
            else:
                ctrl["icon"].name = ft.Icons.RADIO_BUTTON_UNCHECKED
                ctrl["icon"].color = MUTED
                ctrl["label"].color = MUTED
                ctrl["label"].weight = ft.FontWeight.W_400

    def _set_engine_badge(self) -> None:
        """Update the engine badge to reflect the chosen backend.

        Local mode is tinted amber and shows a hint that CPU transcription can
        take minutes, so the wait does not look like a freeze."""
        if self.backend == "groq":
            self.prog_engine_icon.name = ft.Icons.CLOUD_OUTLINED
            self.prog_engine_icon.color = GREEN_HI
            self.prog_engine_text.value = self.t("engine_groq").format(model=tx.GROQ_MODEL)
            self.prog_engine_text.color = GREEN_HI
            self.prog_engine.bgcolor = ft.Colors.with_opacity(0.12, GREEN)
            self.prog_engine.border = ft.border.all(1, ft.Colors.with_opacity(0.35, GREEN))
            self.prog_engine_hint.visible = False
        else:
            # Local: amber tint + a warning that on CPU it can take minutes.
            self.prog_engine_icon.name = ft.Icons.COMPUTER
            self.prog_engine_icon.color = WARN
            self.prog_engine_text.value = self.t("engine_local").format(model=self.model_dd.value)
            self.prog_engine_text.color = WARN
            self.prog_engine.bgcolor = ft.Colors.with_opacity(0.12, WARN)
            self.prog_engine.border = ft.border.all(1, ft.Colors.with_opacity(0.35, WARN))
            self.prog_engine_hint.value = self.t("engine_local_hint")
            self.prog_engine_hint.visible = True

    def _build_error_dialog(self) -> None:
        """Build (once) the reusable red error modal; its message is set per use.

        A single shared dialog (rather than one per error) keeps the page overlay
        small; _show_error just fills the text and opens it."""
        self.err_text = ft.Text("", size=13, color=TEXT, selectable=True)
        self._err_title = self._T("err_title", size=18, weight=ft.FontWeight.W_600, color=DANGER)
        close_btn = ft.FilledButton(
            icon=ft.Icons.CHECK,
            on_click=lambda e: self.page.close(self.error_dialog),
            style=ft.ButtonStyle(
                bgcolor=DANGER, color="#1A0606",
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=18, vertical=16)))
        self._reg(close_btn, "text", "btn_close")
        self.error_dialog = ft.AlertDialog(
            modal=True, bgcolor=SURFACE,
            shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row([
                ft.Icon(ft.Icons.ERROR_OUTLINE, color=DANGER, size=22),
                self._err_title,
            ], spacing=10),
            content=ft.Container(width=440, content=self.err_text),
            actions=[close_btn],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    # ------------------------------------------------------------- SELECTION UI
    def _on_select_card(self, e: ft.ControlEvent) -> None:
        """Handle a click on a backend/source option card.

        Reads the group/key stored in the card's data to know what was chosen,
        then resyncs the selected visuals, the dependent fields and the run state.
        Ignored while busy so a selection cannot change mid-run."""
        if self.busy:
            return
        d = e.control.data
        if d["group"] == "backend":
            self.backend = d["key"]
        else:
            self.source = d["key"]
        self._sync_select_visuals()
        self._sync_fields()
        self._update_run_state()
        self.page.update()

    def _sync_select_visuals(self) -> None:
        """Repaint the four option cards so the selected one is highlighted."""
        pairs = [
            (self.bc_local, "backend", "local"),
            (self.bc_groq, "backend", "groq"),
            (self.sc_youtube, "source", "youtube"),
            (self.sc_local, "source", "local"),
        ]
        for cont, group, key in pairs:
            selected = (self.backend if group == "backend" else self.source) == key
            cont.border = ft.border.all(2 if selected else 1,
                                        BORDER_HI if selected else BORDER)
            cont.bgcolor = ft.Colors.with_opacity(0.08, GREEN) if selected else SURFACE2
            cont.data["check"].visible = selected

    def _sync_fields(self) -> None:
        """Show only the input fields relevant to the current backend/source."""
        self.model_field.visible = self.backend == "local"
        self.key_field.visible = self.backend == "groq"
        self.yt_panel.visible = self.source == "youtube"
        self.local_panel.visible = self.source == "local"

    # --------------------------------------------------------- RUN STATE / WARNING
    def _source_ready(self) -> bool:
        """True when the chosen source is ready to transcribe."""
        if self.source == "youtube":
            # The URL alone is not enough: the video must be loaded and CONFIRMED.
            return self._yt_ok
        return bool(self.local_path)

    def _key_ready(self) -> bool:
        """True when the Groq key requirement is satisfied."""
        # The key is mandatory only with the Groq backend (local is offline).
        return self.backend != "groq" or bool(self.loaded_api_key)

    def _update_run_state(self) -> None:
        """Enable/disable "Transcribe". The "what's missing" notice is a window
        that appears on click (see _on_run), not a fixed banner.

        Does nothing while busy so an in-flight run cannot re-enable the button."""
        if self.busy:
            return
        enabled = self._key_ready() and self._source_ready()
        self._run_enabled = enabled
        self.cta.opacity = 1.0 if enabled else 0.45

    # ------------------------------------------------------------------ ACTIONS
    def _open_url(self, url: str) -> None:
        """Open a URL in the default browser, swallowing any failure (best effort)."""
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _open_folder(self) -> None:
        """Open the last results folder in the OS file manager."""
        self._open_path(self.last_dir)

    def _open_path(self, path: str | None) -> None:
        """Open any file/folder in the OS (best effort).

        Uses os.startfile on Windows and a file:// URL elsewhere; failures are
        ignored since this is a convenience action, not part of the pipeline."""
        if not path:
            return
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                webbrowser.open("file://" + path)
        except Exception:
            pass

    def _on_url_change(self) -> None:
        """If the URL changes, a previous confirmation no longer holds: it must be reloaded."""
        self.yt_confirmed.visible = False
        self._yt_ok = False
        self._update_run_state()
        self.page.update()

    def _load_info(self) -> None:
        """Fetch YouTube metadata for the typed URL and show the confirm dialog.

        The network fetch runs on a background thread so the window stays
        responsive; the button shows a loading label meanwhile and is restored
        in 'finally' regardless of success or error."""
        url = (self.url_tf.value or "").strip()
        if not url:
            return
        self._hide_error()
        self.load_btn.text = self.t("load_info_loading")
        self.load_btn.disabled = True
        self.page.update()

        def work():
            """Background worker: fetch info, then open the confirm dialog or show an error."""
            try:
                meta = engine.get_video_info(url)
                self._show_yt_confirm(meta)
            except Exception as ex:
                self._show_error(str(ex))
            finally:
                self.load_btn.text = self.t("load_info")
                self.load_btn.disabled = False
                self.page.update()

        threading.Thread(target=work, daemon=True).start()

    def _show_yt_confirm(self, meta: dict) -> None:
        """Elegant window with cover + video data, asking for confirmation.

        Built on demand because its content is entirely derived from the fetched
        meta; requiring an explicit confirm avoids transcribing the wrong video
        (and, with Groq, spending credits on it)."""
        thumb = None
        if meta.get("thumbnail"):
            thumb = ft.Container(
                width=412, height=232, border_radius=10,
                border=ft.border.all(1, ft.Colors.with_opacity(0.25, GREEN)),
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=ft.Image(src=meta["thumbnail"], fit=ft.ImageFit.COVER,
                                 width=412, height=232),
            )

        rows = [
            ft.Row(spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                   controls=[
                       ft.Icon(icon, size=15, color=GREEN_HI),
                       ft.Text(f"{label}:", size=12, color=MUTED),
                       ft.Text(str(value), size=12, color=TEXT, weight=ft.FontWeight.W_500),
                   ])
            for icon, label, value in self._yt_pairs(meta)
        ]

        body = []
        if thumb:
            body.append(thumb)
        body.append(ft.Text(meta["title"], size=15, weight=ft.FontWeight.W_700,
                            color=TEXT, no_wrap=False))
        body.append(ft.Column(rows, spacing=6, tight=True))
        body.append(self._estimate_chip(meta))
        body.append(ft.Divider(height=1, color=BORDER))
        body.append(ft.Text(self.t("confirm_question"), size=13, color=MUTED))

        cancel_btn = ft.OutlinedButton(
            self.t("btn_cancel"), icon=ft.Icons.CLOSE,
            on_click=lambda e: self._yt_cancel(),
            style=ft.ButtonStyle(
                color=MUTED, side=ft.BorderSide(1, BORDER),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=16, vertical=16)))
        confirm_btn = ft.FilledButton(
            self.t("btn_confirm"), icon=ft.Icons.CHECK,
            on_click=lambda e: self._yt_confirm(meta),
            style=ft.ButtonStyle(
                bgcolor=GREEN, color="#06140C",
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=18, vertical=16)))

        self.yt_dialog = ft.AlertDialog(
            modal=True, bgcolor=SURFACE,
            shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row([
                ft.Icon(ft.Icons.SMART_DISPLAY_OUTLINED, color=GREEN_HI, size=22),
                ft.Text(self.t("confirm_title"), size=18,
                        weight=ft.FontWeight.W_600, color=TEXT),
            ], spacing=10),
            content=ft.Container(
                width=460,
                content=ft.Column(body, spacing=12, tight=True, scroll=ft.ScrollMode.AUTO),
            ),
            actions=[cancel_btn, confirm_btn],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(self.yt_dialog)

    def _yt_confirm(self, meta: dict) -> None:
        """Video confirmed: store it and enable "Transcribe"."""
        self._yt_meta = meta
        self._yt_ok = True
        self.last_thumb = meta.get("thumbnail")
        self.yt_confirmed.value = self.t("yt_confirmed").format(title=meta["title"])
        self.yt_confirmed.visible = True
        self.page.close(self.yt_dialog)
        self._update_run_state()
        self.page.update()

    def _yt_cancel(self) -> None:
        """Cancelled: clear the URL and confirmation so the user can enter another."""
        self._yt_meta = None
        self._yt_ok = False
        self.url_tf.value = ""
        self.yt_confirmed.visible = False
        self.page.close(self.yt_dialog)
        self._update_run_state()
        self.page.update()

    def _pick_file(self) -> None:
        """Open the file picker for a local audio/video file.

        Reuses the engine's AUDIO_EXTENSIONS set (minus the dots) as the filter
        so the GUI accepts exactly what the CLI/ffmpeg pipeline accepts."""
        self._hide_error()
        exts = sorted(e.lstrip(".") for e in tx.AUDIO_EXTENSIONS)
        self.file_picker.pick_files(
            dialog_title=self.t("pick_file_dialog"),
            allow_multiple=False, allowed_extensions=exts,
        )

    def _on_file_picked(self, e: ft.FilePickerResultEvent) -> None:
        """File-picker callback: record the local file and fill its info box."""
        if not e.files:
            return
        path = e.files[0].path
        self.local_path = path
        meta = tx.local_file_meta(path)
        self._local_meta = meta
        self._fill_info_box(self.file_box, meta["title"], self._local_pairs(meta, path))
        self._update_run_state()
        self.page.update()

    def _on_run(self, e: ft.ControlEvent) -> None:
        """Handle the main "Transcribe" click: validate, then branch on state.

        If requirements are unmet, show the missing-items warning instead of
        running. Before starting we run pre-checks to avoid wasting Groq credits:
        an existing transcription or a resumable partial each open a choice
        dialog rather than blindly re-transcribing."""
        if self.busy:
            return
        if not self._run_enabled:
            items = self._missing_list()
            if items:
                self._show_warn(items)
            return
        # Source + metadata already loaded/confirmed.
        if self.source == "youtube":
            src, meta = (self.url_tf.value or "").strip(), self._yt_meta
            if not src or not meta:
                self._show_error(self.t("err_paste_url"))
                return
        else:
            src, meta = self.local_path, self._local_meta
            if not src or not meta:
                self._show_error(self.t("err_choose_audio"))
                return

        # CHECKS before transcribing (to avoid wasting Groq credits):
        #  1) already transcribed in results/  -> ask what to do (list);
        #  2) partial present (Groq blocks, or local time) -> offer to resume;
        #  otherwise proceed normally.
        if tx.transcription_exists(self.out_root, meta["title"]):
            self._show_already_dialog(src, meta)
            return
        cp = (tx.load_checkpoint(meta) if self.backend == "groq"
              else tx.load_local_checkpoint(meta))
        if cp:
            self._show_resume_dialog(src, meta, cp)
            return
        self._start_transcription(src, meta, resume=False)

    # --- Choice dialogs (professional list) --------------------------------
    def _choice_dialog(self, icon_name, title: str, desc: str, options: list) -> None:
        """Open a dialog with a LIST of clickable choices (card-rows with icon,
        title and description). 'options' = [{icon,label,desc,color,action}];
        a Cancel button at the bottom.

        A mutable 'holder' captures the dialog so each row's lambda can close it
        before running its action — the dialog reference does not exist yet when
        the row handlers are built."""
        holder = {}

        def pick(action):
            """Close the dialog, then run the chosen option's action."""
            self.page.close(holder["dlg"])
            action()

        rows = []
        for o in options:
            col = o.get("color", GREEN)
            rows.append(ft.Container(
                on_click=(lambda a: lambda e: pick(a))(o["action"]),
                ink=True, border_radius=12, padding=14, bgcolor=SURFACE2,
                border=ft.border.all(1, BORDER),
                content=ft.Row(
                    spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=38, height=38, border_radius=10,
                            alignment=ft.alignment.center,
                            bgcolor=ft.Colors.with_opacity(0.12, col),
                            content=ft.Icon(o["icon"], color=col, size=20)),
                        ft.Column(spacing=2, tight=True, expand=True, controls=[
                            ft.Text(o["label"], size=14, weight=ft.FontWeight.W_600, color=TEXT),
                            ft.Text(o["desc"], size=12, color=MUTED, no_wrap=False),
                        ]),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, color=MUTED, size=18),
                    ])))
        cancel = ft.TextButton(
            self.t("btn_cancel"),
            on_click=lambda e: self.page.close(holder["dlg"]),
            style=ft.ButtonStyle(color=MUTED))
        dlg = ft.AlertDialog(
            modal=True, bgcolor=SURFACE, shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row([ft.Icon(icon_name, color=GREEN_HI, size=22),
                          ft.Text(title, size=18, weight=ft.FontWeight.W_600, color=TEXT)],
                         spacing=10),
            content=ft.Container(
                width=500,
                content=ft.Column([ft.Text(desc, size=13, color=MUTED),
                                   ft.Divider(height=1, color=BORDER), *rows],
                                  spacing=12, tight=True)),
            actions=[cancel], actions_alignment=ft.MainAxisAlignment.END,
        )
        holder["dlg"] = dlg
        self.page.open(dlg)

    def _show_already_dialog(self, src, meta: dict) -> None:
        """Video already in results/: offer to re-transcribe it from scratch."""
        self._choice_dialog(
            ft.Icons.HISTORY, self.t("already_title"), self.t("already_desc"),
            [
                {"icon": ft.Icons.REFRESH, "label": self.t("opt_retranscribe"),
                 "desc": self.t("opt_retranscribe_desc"), "color": GREEN,
                 "action": lambda: self._start_transcription(src, meta, resume=False)},
            ])

    def _show_resume_dialog(self, src, meta: dict, cp: dict) -> None:
        """A partial run exists: offer to resume from the checkpoint or start over.

        Resuming continues from the saved point (Groq: done chunks not re-spent;
        local: only the not-yet-transcribed tail is processed); starting over
        deletes the checkpoint first so the partial is not later mistaken for a
        resumable state."""
        is_local = "done_seconds" in cp
        if is_local:
            done_s = int(cp.get("done_seconds", 0))
        else:
            # Groq: i blocchi sono uniformi, quindi il minutaggio fatto =
            # blocchi completati × durata blocco (limitato alla durata totale).
            ch_s = cp.get("chunk_seconds") or tx.CHUNK_SECONDS
            done_s = int(cp.get("done_chunks", 0)) * ch_s
        dur = int(cp.get("duration", 0) or 0)
        if dur:
            done_s = min(done_s, dur)
        done = tx._format_timestamp(done_s)
        total = tx._format_timestamp(dur)
        resume_desc = self.t("resume_opt_resume_desc_time").format(done=done, total=total)

        def restart():
            """Discard the checkpoint (the right kind) and transcribe from scratch."""
            (tx.delete_local_checkpoint if is_local else tx.delete_checkpoint)(meta)
            self._start_transcription(src, meta, resume=False)

        self._choice_dialog(
            ft.Icons.HOURGLASS_BOTTOM, self.t("resume_title"), self.t("resume_desc"),
            [
                {"icon": ft.Icons.PLAY_ARROW, "label": self.t("resume_opt_resume"),
                 "desc": resume_desc,
                 "color": GREEN,
                 "action": lambda: self._start_transcription(src, meta, resume=True)},
                {"icon": ft.Icons.RESTART_ALT, "label": self.t("resume_opt_restart"),
                 "desc": self.t("resume_opt_restart_desc"), "color": WARN,
                 "action": restart},
            ])

    def _start_transcription(self, src, meta: dict, resume: bool = False) -> None:
        """Download + transcribe + save ONE source on a background thread.

        Everything runs off-thread to keep the window alive; the PDF export is
        always produced. On rate limit/error it routes to the dedicated handlers."""
        options = {
            "backend": self.backend, "model": self.model_dd.value,
            "api_key": self.loaded_api_key or "", "export": True,
            "source_kind": self.source,
            # Folder names follow the interface language (en -> English folders).
            "ui_lang": self.lang,
            # Extra outputs (off by default): Italian translation + per-section summary.
            "translate": self.sw_translate.value,
            "summarize": self.sw_summary.value,
            "visual": self.sw_visual.value,
        }
        self._plan = self._phase_plan(self.backend, self.source, options)
        self._last_g = 0.0
        self._hide_error()
        self._set_busy(True)
        self._set_engine_badge()
        self._init_progress(options)
        self._set_phase("info", None, None, "")
        self._show_progress(True)
        self.page.update()

        def work():
            """Background worker: transcribe, save all outputs, then show the summary."""
            try:
                meta2, segments, engine_label, client = engine.transcribe_only(
                    src, options, on_progress=self._on_progress, resume=resume)
                self.last_thumb = meta2.get("thumbnail")
                result = engine.save_results(
                    meta2, segments, engine_label, options, self.out_root,
                    client, on_progress=self._on_progress)
                self.prog_bar.value = 1.0
                self.prog_pct.value = "100%"
                self.page.update()
                self._show_progress(False)
                self._set_busy(False)
                self._render_result(result)
            except engine.RateLimitReached as ex:
                self._fail_ratelimit(ex, src, meta)
            except engine.EngineError as ex:
                self._fail(str(ex))
            except Exception as ex:
                self._fail(self.t("err_unexpected").format(e=ex))

        threading.Thread(target=work, daemon=True).start()

    def _fail_ratelimit(self, ex, src=None, meta: dict | None = None) -> None:
        """Groq credits exhausted: a dedicated (amber) notice, not a red error.

        The partial has already been saved by the engine, so the run can be
        resumed tomorrow when credits return ("Riprendo domani"), or finished
        right now on the local backend ("Continua ora in locale"). Treated apart
        from generic failures because it is an expected, recoverable condition
        (free-tier daily tokens), not a bug. The message reports the MINUTAGGIO
        reached, not the internal chunk count."""
        self._show_progress(False)
        self._set_busy(False)
        done = tx._format_timestamp(int(getattr(ex, "done_seconds", 0) or 0))
        total = tx._format_timestamp(int(getattr(ex, "total_seconds", 0) or 0))
        msg = self.t("ratelimit_msg").format(done=done, total=total)
        close = ft.OutlinedButton(
            self.t("ratelimit_close"), icon=ft.Icons.SCHEDULE,
            on_click=lambda e: self.page.close(self._rl_dialog),
            style=ft.ButtonStyle(color=MUTED,
                                 shape=ft.RoundedRectangleBorder(radius=10),
                                 padding=ft.padding.symmetric(horizontal=16, vertical=16)))
        actions = [close]
        # "Continua ora in locale" is offered only when we know which source to
        # finish (and only for Groq runs — local runs never hit this path).
        if src is not None and meta is not None:
            cont = ft.FilledButton(
                self.t("ratelimit_continue_local"), icon=ft.Icons.COMPUTER,
                on_click=lambda e: self._continue_local(src, meta),
                style=ft.ButtonStyle(bgcolor=WARN, color="#1A1206",
                                     shape=ft.RoundedRectangleBorder(radius=10),
                                     padding=ft.padding.symmetric(horizontal=18, vertical=16)))
            actions.append(cont)
        self._rl_dialog = ft.AlertDialog(
            modal=True, bgcolor=SURFACE, shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row([ft.Icon(ft.Icons.HOURGLASS_DISABLED, color=WARN, size=22),
                          ft.Text(self.t("ratelimit_title"), size=18,
                                  weight=ft.FontWeight.W_600, color=WARN)], spacing=10),
            content=ft.Container(width=460,
                                 content=ft.Text(msg, size=13, color=TEXT, no_wrap=False)),
            actions=actions, actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(self._rl_dialog)

    def _continue_local(self, src, meta: dict) -> None:
        """Finish a credit-exhausted Groq run on the LOCAL backend (CPU/GPU).

        Re-uses the saved partial: only the not-yet-transcribed tail is processed
        locally and merged with it. Switches the UI to the local backend so the
        engine badge and config screen stay consistent, then runs off-thread."""
        self.page.close(self._rl_dialog)
        # Switch to local so badges/cards/fields stay coherent if the user goes back.
        self.backend = "local"
        self._sync_select_visuals()
        self._sync_fields()

        options = {
            "backend": "local", "model": self.model_dd.value or "small",
            "api_key": self.loaded_api_key or "", "export": True,
            "source_kind": self.source,
            # Folder names follow the interface language (en -> English folders).
            "ui_lang": self.lang,
            # Keep the extra-output choices when finishing locally after a rate limit.
            "translate": self.sw_translate.value,
            "summarize": self.sw_summary.value,
            "visual": self.sw_visual.value,
        }
        # Local plan: no Groq "prepare" phase (info -> [download] -> transcribe -> export).
        self._plan = self._phase_plan("local", self.source, options)
        self._last_g = 0.0
        self._hide_error()
        self._set_busy(True)
        self._set_engine_badge()
        self._init_progress(options)
        self._set_phase("info", None, None, "")
        self._show_progress(True)
        self.page.update()

        def work():
            """Background worker: transcribe the remaining tail locally, then save."""
            try:
                meta2, segments, engine_label, _ = engine.continue_local_from_groq(
                    src, options, on_progress=self._on_progress)
                self.last_thumb = meta2.get("thumbnail")
                result = engine.save_results(
                    meta2, segments, engine_label, options, self.out_root,
                    None, on_progress=self._on_progress)
                self.prog_bar.value = 1.0
                self.prog_pct.value = "100%"
                self.page.update()
                self._show_progress(False)
                self._set_busy(False)
                self._render_result(result)
            except engine.EngineError as ex:
                self._fail(str(ex))
            except Exception as ex:
                self._fail(self.t("err_unexpected").format(e=ex))

        threading.Thread(target=work, daemon=True).start()

    # --------------------------------------------------------------- PROGRESS UI
    def _on_progress(self, phase, current, total, detail="") -> None:
        """Engine progress callback (runs on the worker thread).

        It is invoked from the background thread; Flet permits updating controls
        from there, so it simply refreshes the phase/bar and pushes a page update."""
        self._set_phase(phase, current, total, detail)
        self.page.update()

    @staticmethod
    def _phase_plan(backend: str, source_kind: str, options: dict | None = None) -> list:
        """Ordered sequence of run phases, used to number 'Phase i/n'.

        Context-dependent: local files skip the download, only Groq does the
        splitting ('prepare'); the optional translation/summary phases are added
        only when requested. A FIXED plan is what lets the global progress bar
        advance monotonically (see _set_phase)."""
        plan = ["info"]
        if source_kind != "local":
            plan.append("download")
        if backend == "groq":
            plan.append("prepare")
        plan.append("transcribe")
        plan.append("export")
        # The engine runs visual analysis, then translation/summary inside
        # save_results, AFTER writing the transcription, so they come last (in the
        # same order they execute: visual -> translate -> summarize).
        if options and options.get("visual"):
            plan.append("visual")
        if options and options.get("translate"):
            plan.append("translate")
        if options and options.get("summarize"):
            plan.append("summarize")
        return plan

    def _set_phase(self, phase, current, total, detail) -> None:
        """Update the phase label, detail line and the GLOBAL progress bar.

        Maps the engine's phase + (current/total) onto an overall fraction so the
        single bar reflects the whole run, not just one step."""
        self._cur_phase = phase
        key = "phase_" + phase
        label = self.t(key) if key in T[self.lang] else self.t("phase_default")
        self.prog_phase.value = label

        self.prog_detail.value = detail or ""

        # Live narration + checklist (only when a plan/dialog is active).
        narr_key = "narr_" + phase
        if narr_key in T[self.lang]:
            self.prog_narration.value = self.t(narr_key)
        if getattr(self, "_step_ctrls", None):
            self._update_steps(phase)

        # REAL global progress: each phase occupies a slice [i/n, (i+1)/n] of the
        # total; within the phase we interpolate with the actual progress (bytes,
        # chunk i/n, transcribed seconds, section i/n). When a phase has no known
        # progress (e.g. "loading model"), the bar STAYS at the start of its slice
        # instead of spinning in a loop: it only advances when work truly advances.
        # The bar never goes backwards because the plan is fixed.
        n = len(self._plan)
        if phase in self._plan and n:
            i = self._plan.index(phase)
            frac = max(0.0, min(1.0, current / total)) if (current is not None and total) else 0.0
            g = (i + frac) / n
            # Anti-regress: indeterminate mid-phase updates (e.g. "Extracting
            # audio") must not drop the bar. Keep the highest value reached.
            g = max(g, getattr(self, "_last_g", 0.0))
            self._last_g = g
            self.prog_bar.value = g
            self.prog_pct.value = f"{g * 100:.0f}%"
            self.prog_step.content.value = f"{self.t('phase_word')} {i + 1}/{n}"
            self.prog_step.visible = True
        else:
            self.prog_step.visible = False

    # ----------------------------------------------------------------- RESULT UI
    def _render_result(self, res: dict) -> None:
        """Build and open the final summary dialog from the engine's result dict.

        Built on demand because everything (cover, stats chips, warnings, the
        grouped file list) is derived from 'res'. Stores video_dir so the "Open
        folder" button works afterwards."""
        self.last_dir = res["video_dir"]

        def chip(icon, label, value):
            """One small stat chip: icon + label + value."""
            return ft.Row(
                spacing=6, tight=True,
                controls=[
                    ft.Icon(icon, size=15, color=GREEN_HI),
                    ft.Text(label, size=12, color=MUTED),
                    ft.Text(str(value), size=12, color=TEXT, weight=ft.FontWeight.W_600),
                ])

        body: list[ft.Control] = []

        if getattr(self, "last_thumb", None):
            body.append(ft.Container(
                width=360, height=202, border_radius=10,
                border=ft.border.all(1, ft.Colors.with_opacity(0.25, GREEN)),
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                content=ft.Image(src=self.last_thumb, fit=ft.ImageFit.COVER,
                                 width=360, height=202),
            ))

        if res.get("warnings"):
            body.append(ft.Container(
                border_radius=10, padding=12,
                bgcolor=ft.Colors.with_opacity(0.10, WARN),
                content=ft.Text("\n".join("⚠ " + w for w in res["warnings"]),
                                size=12, color=WARN)))

        body.append(ft.Row(
            wrap=True, spacing=20, run_spacing=8,
            controls=[
                chip(ft.Icons.MEMORY, self.t("res_engine"), res["engine_label"]),
                chip(ft.Icons.GRID_VIEW, self.t("res_segments"), res["segments"]),
                chip(ft.Icons.SUBJECT, self.t("res_words"), f"~{res['words']}"),
                chip(ft.Icons.LIST_ALT, self.t("res_sections"),
                     res["sections"] or self.t("res_continuous")),
            ]))

        body.append(ft.Container(
            bgcolor=ft.Colors.with_opacity(0.05, GREEN),
            border=ft.border.all(1, ft.Colors.with_opacity(0.2, GREEN)),
            border_radius=10, padding=12,
            content=ft.Column(spacing=4, tight=True, controls=[
                ft.Row([ft.Icon(ft.Icons.FOLDER_OPEN, size=15, color=GREEN_HI),
                        ft.Text(self.t("res_saved_in"), size=12, color=MUTED)], spacing=6),
                ft.Text(res["video_dir"], size=12, color=TEXT,
                        weight=ft.FontWeight.W_500, selectable=True),
            ])))

        body.append(ft.Divider(height=1, color=BORDER))

        groups: dict[str, list[str]] = {}
        for f in res.get("files", []):
            i = f.find("/")
            folder = f[:i] if i >= 0 else ""
            name = f[i + 1:] if i >= 0 else f
            groups.setdefault(folder, []).append(name)

        file_rows: list[ft.Control] = []
        for folder, names in groups.items():
            icon = ft.Icons.FOLDER
            file_rows.append(ft.Row([
                ft.Icon(icon, size=15, color=GREEN_HI),
                ft.Text(f"{folder}/" if folder else self.t("res_root"), size=13,
                        weight=ft.FontWeight.W_600, color=GREEN_HI),
            ], spacing=8))
            for n in names:
                file_rows.append(ft.Container(
                    padding=ft.padding.only(left=24),
                    content=ft.Row([
                        ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED, size=13, color=MUTED),
                        ft.Text(n, size=12, color=TEXT),
                    ], spacing=8)))
        body.append(ft.Column(file_rows, spacing=4, tight=True))

        # --- Groq credits used by this run (only for Groq cloud transcriptions) ---
        credits = res.get("credits")
        if credits:
            used = credits.get("audio_seconds_used") or 0
            # Crediti audio residui oggi, se Groq li ha riportati negli header.
            remaining_audio = None
            for it in (credits.get("limits") or []):
                if it.get("kind") == "audio_seconds" and it.get("remaining") is not None:
                    remaining_audio = it["remaining"]
                    break
            credit_chips = [chip(ft.Icons.GRAPHIC_EQ, self.t("res_credits_used"),
                                 tx._format_timestamp(used))]
            if remaining_audio is not None:
                credit_chips.append(chip(ft.Icons.SAVINGS_OUTLINED,
                                         self.t("res_credits_remaining_audio"),
                                         tx._format_timestamp(remaining_audio)))
            body.append(ft.Divider(height=1, color=BORDER))
            body.append(ft.Row([ft.Icon(ft.Icons.SAVINGS_OUTLINED, size=15, color=GREEN_HI),
                                 ft.Text(self.t("res_credits"), size=13,
                                         weight=ft.FontWeight.W_600, color=GREEN_HI)], spacing=8))
            body.append(ft.Row(wrap=True, spacing=20, run_spacing=8, controls=credit_chips))

        # --- Analisi visiva: conteggio + pulsante per aprire il documento dedicato ---
        visual = res.get("visual")
        if visual and visual.get("count"):
            self.last_visual_dir = visual.get("dir")
            body.append(ft.Divider(height=1, color=BORDER))
            body.append(ft.Container(
                bgcolor=ft.Colors.with_opacity(0.06, GREEN),
                border=ft.border.all(1, ft.Colors.with_opacity(0.25, GREEN)),
                border_radius=10, padding=12,
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Row(spacing=10, tight=True, controls=[
                            ft.Icon(ft.Icons.VISIBILITY, size=20, color=GREEN_HI),
                            ft.Column(spacing=1, tight=True, controls=[
                                ft.Text(self.t("res_visual"), size=13,
                                        weight=ft.FontWeight.W_600, color=TEXT),
                                ft.Text(self.t("res_visual_count").format(n=visual.get("count")),
                                        size=12, color=MUTED),
                            ]),
                        ]),
                        ft.OutlinedButton(
                            self.t("btn_open_visual"), icon=ft.Icons.IMAGE_OUTLINED,
                            on_click=lambda e: self._open_path(self.last_visual_dir),
                            style=ft.ButtonStyle(
                                color=GREEN_HI, side=ft.BorderSide(1, BORDER_HI),
                                shape=ft.RoundedRectangleBorder(radius=10),
                                padding=ft.padding.symmetric(horizontal=14, vertical=14))),
                    ])))

        open_btn = ft.OutlinedButton(
            self.t("btn_open_folder"), icon=ft.Icons.FOLDER_OPEN,
            on_click=lambda e: self._open_folder(),
            style=ft.ButtonStyle(
                color=GREEN_HI, side=ft.BorderSide(1, BORDER_HI),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=16, vertical=16)),
        )
        close_btn = ft.FilledButton(
            self.t("btn_close"), icon=ft.Icons.CHECK,
            on_click=lambda e: self.page.close(self.result_dialog),
            style=ft.ButtonStyle(
                bgcolor=GREEN, color="#06140C",
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=18, vertical=16)),
        )

        self.result_dialog = ft.AlertDialog(
            modal=True, bgcolor=SURFACE,
            shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row([
                ft.Icon(ft.Icons.TASK_ALT, color=GREEN_HI, size=22),
                ft.Text(self.t("res_title"), size=18, weight=ft.FontWeight.W_600, color=TEXT),
            ], spacing=10),
            content=ft.Container(
                width=460,
                content=ft.Column(body, spacing=14, tight=True, scroll=ft.ScrollMode.AUTO),
            ),
            actions=[open_btn, close_btn],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.update()
        self.page.open(self.result_dialog)

    # ---------------------------------------------------------------- UTILITIES
    def _show_progress(self, on: bool) -> None:
        """Open or close the dedicated progress window (modal dialog).

        The CTA button stays in place (shown busy) behind the modal; opening a
        separate window keeps the run's status front-and-center and uncluttered."""
        if on:
            self.page.open(self.progress_dialog)
        else:
            self._close_dialog(self.progress_dialog)

    def _set_busy(self, busy: bool) -> None:
        """Set the busy flag and reflect it on the CTA (label, icon, opacity).

        When clearing busy it defers to _update_run_state so the button's enabled
        state is recomputed rather than blindly re-enabled."""
        self.busy = busy
        self.cta_text.value = self.t("cta_busy") if busy else self.t("cta_run")
        self.cta_icon.name = ft.Icons.HOURGLASS_TOP if busy else ft.Icons.AUTO_AWESOME
        if busy:
            self.cta.opacity = 0.5
        else:
            self._update_run_state()

    def _close_dialog(self, dlg) -> None:
        """Close a dialog only if it is actually open: calling page.close() on an
        AlertDialog that was never shown triggers an assert ('must be added to the
        page first'). The getattr guard handles dialogs not yet built."""
        if dlg is not None and getattr(dlg, "open", False):
            self.page.close(dlg)

    def _fail(self, message: str) -> None:
        """Generic failure path: hide progress, clear busy and show the error modal."""
        self._show_progress(False)
        self._set_busy(False)
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        """Fill and open the shared error dialog (falls back to a generic message)."""
        self.err_text.value = message or self.t("err_unknown")
        self.page.open(self.error_dialog)

    def _hide_error(self) -> None:
        """Close the error dialog if it happens to be open."""
        self._close_dialog(getattr(self, "error_dialog", None))


def main(page: ft.Page) -> None:
    """Flet entry point: instantiate the app, which wires itself onto the page."""
    EchoScriptApp(page)


if __name__ == "__main__":
    ft.app(target=main)
