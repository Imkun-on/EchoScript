# =============================================================================
#  EchoScript — GUI desktop (Flet)
# =============================================================================
#  Interfaccia grafica nativa costruita interamente con Flet. Pilota l'engine
#  headless (core/engine.py), lo stesso usato dalla CLI: qui non c'è alcuna
#  logica di trascrizione, solo presentazione e orchestrazione.
#
#  Il lavoro pesante (download / trascrizione / traduzione / salvataggio) gira
#  in un thread in background; l'engine riporta l'avanzamento tramite una
#  callback `on_progress(phase, current, total, detail)` con cui aggiorniamo la
#  barra di progresso. Flet consente l'aggiornamento dei controlli da un thread
#  secondario, quindi la finestra non si blocca mai.
#
#  Lingua dell'interfaccia: italiano (default) o inglese, selezionabile dalla
#  barra del titolo. Tutte le stringhe rivolte all'utente passano da self.t().
#
#  Palette: verde + nero con sfumature smeraldo (look professionale, dark).
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
# Rendi importabili l'engine e gli helper "puri" condivisi con la CLI.
for _p in (os.path.join(_PROJECT_ROOT, "core"), _PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import flet as ft
import flet.canvas as cv  # disegno vettoriale per lo sfondo animato (griglia)

import engine            # core/engine.py
import transcriber as tx  # riuso dei formatter puri (durata, views, ecc.)


# === PALETTE (verde / nero + sfumature smeraldo) ===========================
BG        = "#0A0F0C"   # sfondo finestra: nero con velo verde
SURFACE   = "#111A14"   # card
SURFACE2  = "#16221B"   # superficie selezionata / in evidenza
BORDER    = "#243329"   # bordo neutro
BORDER_HI = "#2F8F57"   # bordo verde (stato selezionato)
GREEN     = "#22C55E"   # primario
GREEN_HI  = "#4ADE80"   # accento brillante
GREEN_DK  = "#15803D"   # verde profondo (gradiente)
TEXT      = "#E8F1EB"   # testo principale
MUTED     = "#8A9A90"   # testo secondario
DANGER    = "#F87171"
WARN      = "#FBBF24"

# Altezza condivisa dalle due card di configurazione, così restano sempre
# identiche a prescindere dal contenuto (vedi _build_ui). Dimensionata per il
# caso più alto (backend Groq col caricatore chiave).
CARD_HEIGHT = 360

# Modelli locali offerti nel menu a tendina (chiave modello whisper -> chiave i18n).
_LOCAL_MODELS = [
    ("base",           "model_base"),
    ("small",          "model_small"),
    ("medium",         "model_medium"),
    ("large-v3",       "model_largev3"),
    ("large-v3-turbo", "model_turbo"),
]

# === STRINGHE LOCALIZZATE (it = default, en) ================================
# Ogni testo rivolto all'utente è qui sotto. self.t("chiave") restituisce la
# versione nella lingua corrente; quelle con {segnaposto} si usano con .format().
T = {
    "it": {
        "header_sub": "Trascrivi e traduci video YouTube o audio locali, veloce con Groq o 100% offline",
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
        "limits_btn": "Controlla limiti API",
        "limits_checking": "Controllo…",
        "get_key": "Ottieni una chiave →",
        "key_loaded": "✓ Chiave caricata da “{name}”",
        "key_none": "Nessun file caricato (in alternativa la chiave può stare nel file .env).",
        "pick_key_dialog": "Scegli il file .txt con la chiave Groq",
        # Step 2 — sorgente
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
        # CTA + avviso
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
        "phase_export": "Esportazione / salvataggio",
        "saving_files": "Salvataggio dei file",
        # Dialog opzioni
        "opt_title": "Trascrizione completata",
        "opt_desc": "Il PDF verrà creato automaticamente. Poi indica dove salvare: "
                    "l'app creerà le sottocartelle (trascrizioni, traduzioni).",
        "opt_already_it": "Audio già in italiano: nessuna traduzione necessaria.",
        "opt_switch": "Traduci anche in italiano (usa Groq)",
        # Dialog "video già trascritto"
        "already_title": "Video già trascritto",
        "already_desc": "Questo video è già presente nella cartella results/. Cosa vuoi fare?",
        "opt_retranscribe": "Ritrascrivi tutto",
        "opt_retranscribe_desc": "Rifà la trascrizione da capo; i file esistenti verranno sostituiti.",
        "opt_only_translate": "Solo (ri)traduzione",
        "opt_only_translate_desc": "Riusa la trascrizione esistente e rigenera solo la traduzione "
                                   "(sovrascrive quella vecchia). Non rispende crediti di trascrizione.",
        # Dialog "ripresa disponibile"
        "resume_title": "Ripresa disponibile",
        "resume_desc": "Una trascrizione di questo video si era interrotta. Cosa vuoi fare?",
        "resume_opt_resume": "Riprendi",
        "resume_opt_resume_desc": "Continua dal punto salvato (blocco {done}/{total}).",
        "resume_opt_restart": "Ricomincia da capo",
        "resume_opt_restart_desc": "Ignora il parziale e ritrascrive tutto da zero.",
        # Avviso limite raggiunto
        "ratelimit_title": "Limite Groq raggiunto",
        "ratelimit_msg": "Trascritti {done}/{total} blocchi. Il progresso è stato salvato: "
                         "riapri questo video più tardi (quando tornano i crediti) e scegli «Riprendi».",
        "engine_translate": "Groq · traduzione",
        "opt_key_needed": "Per tradurre serve una chiave Groq:",
        "btn_continue": "Continua e scegli cartella",
        "dir_dialog": "Scegli la cartella di destinazione",
        "groq_key_error": "Errore con la chiave Groq: {e}",
        # Dialog risultato
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
        # Dialog limiti
        "lim_title": "Limiti API Groq",
        "lim_model": "Modello: {m}",
        "lim_desc": "Valori del momento per il modello di traduzione (è il suo "
                    "limite giornaliero di token a bloccare la traduzione).",
        "lim_tokens": "Token rimanenti",
        "lim_requests": "Richieste rimanenti",
        "lim_reset": "si azzera tra {v}",
        "lim_no_window": "finestra non indicata",
        "lim_retry": "⚠ Limite raggiunto: riprova tra {v} s.",
        # Errori
        "err_title": "Errore",
        "err_unknown": "Errore sconosciuto.",
        "err_paste_url": "Incolla prima l'URL del video.",
        "err_choose_audio": "Scegli prima un file audio.",
        "err_unexpected": "Errore imprevisto: {e}",
        "err_save": "Errore nel salvataggio: {e}",
        "err_key_read": "Impossibile leggere il file della chiave: {e}",
        "err_key_invalid": "Il file selezionato non contiene una chiave valida.",
        "err_limits": "Errore nel controllo dei limiti: {e}",
    },
    "en": {
        "header_sub": "Transcribe and translate YouTube videos or local audio, fast with Groq or 100% offline",
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
        "limits_btn": "Check API limits",
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
        "phase_export": "Exporting / saving",
        "saving_files": "Saving files",
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
        "resume_opt_restart": "Start over",
        "resume_opt_restart_desc": "Discard the partial and re-transcribe from scratch.",
        "ratelimit_title": "Groq limit reached",
        "ratelimit_msg": "Transcribed {done}/{total} chunks. Progress was saved: reopen this video "
                         "later (when credits return) and choose “Resume”.",
        "engine_translate": "Groq · translation",
        "opt_key_needed": "Translation requires a Groq key:",
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
        "lim_title": "Groq API limits",
        "lim_model": "Model: {m}",
        "lim_desc": "Current values for the translation model (its daily token "
                    "limit is what blocks translation).",
        "lim_tokens": "Tokens remaining",
        "lim_requests": "Requests remaining",
        "lim_reset": "resets in {v}",
        "lim_no_window": "window not specified",
        "lim_retry": "⚠ Limit reached: retry in {v}s.",
        "err_title": "Error",
        "err_unknown": "Unknown error.",
        "err_paste_url": "Paste the video URL first.",
        "err_choose_audio": "Choose an audio file first.",
        "err_unexpected": "Unexpected error: {e}",
        "err_save": "Error while saving: {e}",
        "err_key_read": "Cannot read the key file: {e}",
        "err_key_invalid": "The selected file does not contain a valid key.",
        "err_limits": "Error while checking limits: {e}",
    },
}


class EchoScriptApp:
    """Costruisce e gestisce l'intera interfaccia Flet."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page

        # --- stato dell'applicazione ---
        self.lang = "it"            # "it" | "en" (lingua dell'interfaccia)
        self.backend = "local"      # "local" | "groq"
        self.source = "youtube"     # "youtube" | "local"
        self.local_path = None      # percorso del file locale scelto
        self.last_dir = None        # cartella dei risultati (per "Apri cartella")
        self.last_thumb = None      # copertina del video (URL) per il riepilogo
        self.busy = False           # True mentre un'elaborazione è in corso
        self._run_enabled = False   # True quando "Trascrivi" è abilitabile
        self._pending = None        # risultato della fase 1, in attesa di salvataggio
        self.loaded_api_key = None  # chiave Groq letta da file .txt (o None)
        self.loaded_api_key_name = ""   # nome del file da cui è stata letta
        self._key_status_labels = []    # etichette di stato da aggiornare al caricamento
        self._yt_meta = None        # ultimo meta YouTube caricato (per re-fill in lingua)
        self._yt_ok = False         # True solo dopo aver confermato il video YouTube
        self._local_meta = None     # ultimo meta file locale caricato
        self._detected_lang = None  # lingua audio rilevata (per proporre la traduzione)
        self._cur_phase = "info"    # fase corrente (per ritradurre al cambio lingua)
        self._plan = []             # sequenza di fasi del run corrente (per "Fase i/n")
        self._last_g = 0.0          # avanzamento globale raggiunto (barra anti-ritorno)
        self._i18n = []             # [(controllo, attributo, chiave)] da ritradurre

        # Cartella di output FISSA: results/ accanto al progetto (come la CLI).
        # Così possiamo controllare PRIMA di trascrivere se il video è già fatto
        # o se c'è un parziale da riprendere, senza chiedere la cartella ogni volta.
        self.out_root = engine.RESULTS_DIR

        # --- file pickers (vanno in page.overlay) ---
        self.file_picker = ft.FilePicker(on_result=self._on_file_picked)
        self.key_picker = ft.FilePicker(on_result=self._on_key_picked)
        page.overlay.extend([self.file_picker, self.key_picker])

        self._build_ui()

    # -------------------------------------------------------------- I18N HELPERS
    def t(self, key: str) -> str:
        """Stringa nella lingua corrente (fallback su italiano, poi sulla chiave)."""
        return T.get(self.lang, T["it"]).get(key) or T["it"].get(key, key)

    def _T(self, key: str, **kw) -> ft.Text:
        """Crea un ft.Text registrato: il suo valore segue la lingua corrente."""
        txt = ft.Text(self.t(key), **kw)
        self._i18n.append((txt, "value", key))
        return txt

    def _reg(self, obj, attr: str, key: str):
        """Registra un attributo testuale (text/label/hint_text…) da ritradurre."""
        setattr(obj, attr, self.t(key))
        self._i18n.append((obj, attr, key))
        return obj

    def _set_lang(self, lang: str) -> None:
        if lang == self.lang:
            return
        self.lang = lang
        self._style_lang_pills()
        # Ritraduci tutti i controlli statici registrati.
        for obj, attr, key in self._i18n:
            setattr(obj, attr, self.t(key))
        # Ritraduci le parti dinamiche.
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

        # Layout a DUE COLONNE: i due step di configurazione affiancati, così
        # tutto entra nello schermo senza barra di scorrimento.
        backend_card = self._step_backend()
        source_card = self._step_source()
        backend_card.expand = 1
        source_card.expand = 1
        # Altezza fissa IDENTICA sulle due card: in Flet 0.27 non esiste
        # IntrinsicHeight e lo STRETCH dentro una colonna "tight" le farebbe
        # collassare; un'altezza condivisa le tiene sempre uguali, qualunque sia
        # lo stato (Groq, file scelto, ecc.). Il contenuto resta in alto.
        backend_card.height = CARD_HEIGHT
        source_card.height = CARD_HEIGHT
        self._steps_row = ft.Row(
            [backend_card, source_card], spacing=18,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        content = ft.Column(
            spacing=16,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                self._header(),
                self._steps_row,
                self._cta_button(),
                self._progress_card(),
            ],
        )

        # Finestre modali costruite a parte.
        self._build_options_dialog()
        self._build_error_dialog()
        self._build_warn_dialog()

        self._sync_select_visuals()

        pad = self._side_pad()
        self.content_holder = ft.Container(
            expand=True, alignment=ft.alignment.center, content=content,
            padding=ft.padding.only(left=pad, right=pad, top=18, bottom=22),
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
        self._update_run_state()   # stato iniziale del pulsante + avviso
        self.page.update()
        self._start_grid()

    # --------------------------------------------------------------- TITLE BAR
    def _title_bar(self) -> ft.Control:
        """Barra del titolo su misura (drag + lingua + minimizza/ingrandisci/chiudi)."""
        self.max_icon = ft.Icon(ft.Icons.CROP_SQUARE_OUTLINED, size=15, color=MUTED)

        def win_button(icon_ctrl, on_click, hover_bg, hover_fg):
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
        """Selettore lingua a bandiere (Italia / Regno Unito). Le bandiere sono
        disegnate con Flet (niente immagini di rete: funziona anche offline)."""
        def flag_btn(code: str, flag: ft.Control) -> ft.Container:
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
        """Evidenzia la bandiera attiva (piena + anello verde), attenua l'altra."""
        for cont, code in ((self.lang_it, "it"), (self.lang_en, "en")):
            on = self.lang == code
            cont.opacity = 1.0 if on else 0.45
            cont.border = ft.border.all(2, GREEN_HI if on else ft.Colors.TRANSPARENT)
            cont.bgcolor = ft.Colors.with_opacity(0.10, GREEN) if on else None

    @staticmethod
    def _it_flag(w: int = 30, h: int = 20) -> ft.Control:
        """Tricolore italiano: verde / bianco / rosso."""
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
        """Union Jack stilizzata (disegnata con il canvas)."""
        white, red = "#FFFFFF", "#C8102E"
        pw = ft.Paint(stroke_width=4.5, color=white, style=ft.PaintingStyle.STROKE)
        pr = ft.Paint(stroke_width=1.8, color=red, style=ft.PaintingStyle.STROKE)
        fw = ft.Paint(color=white)
        fr = ft.Paint(color=red)
        shapes = [
            # Diagonali bianche poi rosse (croce di Sant'Andrea/Patrizio).
            cv.Line(0, 0, w, h, paint=pw), cv.Line(w, 0, 0, h, paint=pw),
            cv.Line(0, 0, w, h, paint=pr), cv.Line(w, 0, 0, h, paint=pr),
            # Croce bianca (San Giorgio) e poi rossa sopra.
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
        self.page.window.minimized = True
        self.page.update()

    def _toggle_max(self) -> None:
        self.page.window.maximized = not self.page.window.maximized
        self.page.update()

    def _on_window_event(self, e) -> None:
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
        w = self.page.width or self.page.window.width or 1040
        return int(max(20, min(180, w * 0.06)))

    def _on_resized(self, e=None) -> None:
        pad = self._side_pad()
        self.content_holder.padding = ft.padding.only(left=pad, right=pad,
                                                       top=18, bottom=22)
        self.page.update()

    def _grid_layer(self) -> ft.Control:
        """Sfondo sobrio e leggero: cielo a gradiente scuro + particelle soffuse
        che salgono lentamente. Niente griglia/skyline (look professionale)."""
        sky = ft.Container(
            expand=True,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_center, end=ft.alignment.bottom_center,
                colors=[BG, "#0B130E", BG],
                stops=[0.0, 0.55, 1.0]),
        )
        # Particelle precalcolate (posizioni come frazioni: scalano con la finestra).
        self._particles = [{"x": random.uniform(0, 1),
                            "sp": random.uniform(0.04, 0.10),
                            "ph": random.uniform(0, 1),
                            "r": random.uniform(1.0, 2.4)} for _ in range(26)]
        self._grid_canvas = cv.Canvas(expand=True)
        return ft.Stack([sky, self._grid_canvas], expand=True)

    def _start_grid(self) -> None:
        self._bg_stop = False
        threading.Thread(target=self._animate_grid, daemon=True).start()

    def _animate_grid(self) -> None:
        """Anima solo le particelle: leggere, lente, con un soffuso respiro di
        opacità. Costo minimo (poche forme per frame)."""
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
                # La finestra è stata chiusa (event loop chiuso / canvas non più
                # montato): usciamo in silenzio, non è un errore.
                break
            time.sleep(0.08)
            t += 0.08

    # --------------------------------------------------------------- COMPONENTS
    def _header(self) -> ft.Control:
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
        return ft.Container(
            bgcolor=SURFACE, border=ft.border.all(1, BORDER), border_radius=16,
            padding=22, content=ft.Column(list(controls), spacing=14, tight=True),
            **kwargs,
        )

    def _card_title(self, step: str, text_key: str) -> ft.Control:
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
        name_row = [self._T(name_key, size=15, weight=ft.FontWeight.W_600, color=TEXT)]
        if tag:
            name_row.append(ft.Container(
                bgcolor=ft.Colors.with_opacity(0.18, GREEN),
                border_radius=6, padding=ft.padding.symmetric(horizontal=7, vertical=1),
                content=ft.Text(tag, size=10, weight=ft.FontWeight.BOLD, color=GREEN_HI)))
        check = ft.Icon(ft.Icons.CHECK_CIRCLE, color=GREEN_HI, size=20, visible=False)

        return ft.Container(
            data={"group": group, "key": key, "check": check},
            on_click=self._on_select_card,
            border_radius=14, padding=16, bgcolor=SURFACE2,
            border=ft.border.all(1, BORDER),
            animate=ft.Animation(160, ft.AnimationCurve.EASE_OUT),
            ink=True, expand=True,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Row([
                        ft.Container(
                            width=40, height=40, border_radius=10,
                            bgcolor=ft.Colors.with_opacity(0.10, GREEN),
                            alignment=ft.alignment.center,
                            content=ft.Icon(icon, color=GREEN_HI, size=22)),
                        ft.Container(expand=True),
                        check,
                    ]),
                    ft.Row(name_row, spacing=8),
                    self._T(desc_key, size=12, color=MUTED),
                ],
            ),
        )

    def _step_backend(self) -> ft.Control:
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
        """Riscrive le descrizioni del menu modelli nella lingua corrente."""
        val = self.model_dd.value
        self.model_dd.options = [ft.dropdown.Option(k, self.t(tk)) for k, tk in _LOCAL_MODELS]
        self.model_dd.value = val

    # --- Caricatore della chiave Groq da file .txt -------------------------
    def _key_loader(self) -> ft.Control:
        status = ft.Text(
            self._key_status_text(), size=12,
            color=GREEN_HI if self.loaded_api_key else MUTED)
        self._key_status_labels.append(status)

        limits_btn = ft.OutlinedButton(
            icon=ft.Icons.SPEED,
            style=ft.ButtonStyle(
                color=GREEN_HI, side=ft.BorderSide(1, BORDER_HI),
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=14, vertical=14)))
        self._reg(limits_btn, "text", "limits_btn")
        limits_btn.on_click = lambda e: self._check_limits(limits_btn)

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

        return ft.Column(
            spacing=8,
            controls=[
                ft.Row([load_btn, limits_btn, get_btn], spacing=10, wrap=True),
                status,
            ],
        )

    def _key_status_text(self) -> str:
        if self.loaded_api_key:
            return self.t("key_loaded").format(name=self.loaded_api_key_name)
        return self.t("key_none")

    def _refresh_key_status(self) -> None:
        for lbl in self._key_status_labels:
            lbl.value = self._key_status_text()
            lbl.color = GREEN_HI if self.loaded_api_key else MUTED

    def _pick_key(self) -> None:
        self._hide_error()
        self.key_picker.pick_files(
            dialog_title=self.t("pick_key_dialog"),
            allow_multiple=False, allowed_extensions=["txt"])

    def _on_key_picked(self, e: ft.FilePickerResultEvent) -> None:
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

    # --- Controllo dei limiti d'uso dell'API Groq --------------------------
    def _check_limits(self, btn: ft.OutlinedButton) -> None:
        self._hide_error()
        btn.text = self.t("limits_checking")
        btn.disabled = True
        self.page.update()

        def work():
            try:
                info = engine.get_rate_limits(self.loaded_api_key or None)
                self._show_limits_dialog(info)
            except engine.EngineError as ex:
                self._show_error(str(ex))
            except Exception as ex:
                self._show_error(self.t("err_limits").format(e=ex))
            finally:
                btn.text = self.t("limits_btn")
                btn.disabled = False
                self.page.update()

        threading.Thread(target=work, daemon=True).start()

    def _show_limits_dialog(self, info: dict) -> None:
        def fmt(v) -> str:
            return str(v) if v not in (None, "") else "—"

        def metric(icon, label, remaining, limit, reset):
            value = fmt(remaining)
            if limit not in (None, ""):
                value += f" / {limit}"
            line2 = (self.t("lim_reset").format(v=reset) if reset not in (None, "")
                     else self.t("lim_no_window"))
            return ft.Row(
                spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=40, height=40, border_radius=10,
                        bgcolor=ft.Colors.with_opacity(0.10, GREEN),
                        alignment=ft.alignment.center,
                        content=ft.Icon(icon, color=GREEN_HI, size=20)),
                    ft.Column(spacing=2, tight=True, controls=[
                        ft.Text(label, size=12, color=MUTED),
                        ft.Text(value, size=16, color=TEXT, weight=ft.FontWeight.W_700),
                        ft.Text(line2, size=11, color=MUTED),
                    ]),
                ])

        rows: list[ft.Control] = [
            metric(ft.Icons.TOKEN, self.t("lim_tokens"),
                   info.get("remaining_tokens"), info.get("limit_tokens"),
                   info.get("reset_tokens")),
            ft.Divider(height=1, color=BORDER),
            metric(ft.Icons.REPEAT, self.t("lim_requests"),
                   info.get("remaining_requests"), info.get("limit_requests"),
                   info.get("reset_requests")),
        ]
        if info.get("retry_after") not in (None, ""):
            rows.append(ft.Container(
                border_radius=8, padding=10,
                bgcolor=ft.Colors.with_opacity(0.10, WARN),
                content=ft.Text(self.t("lim_retry").format(v=info["retry_after"]),
                                size=12, color=WARN)))

        dlg = ft.AlertDialog(
            modal=True, bgcolor=SURFACE,
            shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row([
                ft.Icon(ft.Icons.SPEED, color=GREEN_HI, size=22),
                ft.Text(self.t("lim_title"), size=18, weight=ft.FontWeight.W_600, color=TEXT),
            ], spacing=10),
            content=ft.Container(
                width=420,
                content=ft.Column(spacing=14, tight=True, controls=[
                    ft.Text(self.t("lim_model").format(m=info.get("model", "?")),
                            size=12, color=MUTED),
                    ft.Text(self.t("lim_desc"), size=12, color=MUTED),
                    ft.Divider(height=1, color=BORDER),
                    *rows,
                ]),
            ),
            actions=[ft.FilledButton(
                self.t("btn_close"), icon=ft.Icons.CHECK,
                on_click=lambda e: self.page.close(dlg),
                style=ft.ButtonStyle(
                    bgcolor=GREEN, color="#06140C",
                    shape=ft.RoundedRectangleBorder(radius=10),
                    padding=ft.padding.symmetric(horizontal=18, vertical=16)))],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(dlg)

    def _step_source(self) -> ft.Control:
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
        # Le info del video appaiono in una finestra di conferma (vedi
        # _show_yt_confirm). Qui sotto resta solo un'etichetta di conferma.
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
        """Card informativa compatta: copertina a sinistra, dati a destra."""
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
        """Coppie (icona, etichetta, valore) per un video YouTube, nella lingua
        corrente. I metadati opzionali (like, iscritti, categoria) compaiono solo
        se presenti."""
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
        """Nome leggibile (localizzato) di una lingua. Accetta sia i codici ISO
        (faster-whisper: 'en') sia i nomi interi (Groq: 'english'). None se assente."""
        if not code:
            return None
        c = code.split("-")[0].strip().lower()
        # Normalizza i nomi interi di Whisper al codice ISO a 2 lettere.
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
        return [
            (ft.Icons.AUDIO_FILE, self.t("info_file"), os.path.basename(path)),
            (ft.Icons.SCHEDULE, self.t("info_duration"), tx._format_duration(meta["duration"])),
        ]

    def _refresh_info_boxes(self) -> None:
        """Riscrive nella nuova lingua le info già caricate (etichetta di conferma
        YouTube + box del file locale)."""
        if self._yt_meta and self.yt_confirmed.visible:
            self.yt_confirmed.value = self.t("yt_confirmed").format(
                title=self._yt_meta["title"])
        if self._local_meta and self.local_path:
            self._fill_info_box(self.file_box, self._local_meta["title"],
                                self._local_pairs(self._local_meta, self.local_path))

    def _build_options_dialog(self) -> None:
        self.opt_translate = ft.Switch(
            value=False, active_color=GREEN,
            label_style=ft.TextStyle(color=TEXT, size=14),
            on_change=lambda e: self._refresh_prompt_key(),
        )
        self._reg(self.opt_translate, "label", "opt_switch")
        # Nota mostrata quando l'audio è già in italiano (niente switch traduzione).
        self.opt_lang_note = ft.Row(
            visible=False, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[ft.Icon(ft.Icons.INFO_OUTLINE, color=GREEN_HI, size=18),
                      self._T("opt_already_it", size=12, color=MUTED)])
        self.prompt_key_panel = ft.Container(
            visible=False,
            padding=ft.padding.only(left=4, top=2),
            content=ft.Column(
                spacing=6,
                controls=[
                    self._T("opt_key_needed", size=12, color=MUTED),
                    self._key_loader(),
                ],
            ),
        )
        self.prompt_error = ft.Container(
            visible=False, border_radius=8, padding=10,
            bgcolor=ft.Colors.with_opacity(0.10, DANGER),
            content=ft.Text("", size=12, color=DANGER, selectable=True),
        )
        continue_btn = ft.FilledButton(
            icon=ft.Icons.ARROW_FORWARD, on_click=self._confirm_options,
            style=ft.ButtonStyle(
                bgcolor=GREEN, color="#06140C",
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=20, vertical=18)))
        self._reg(continue_btn, "text", "btn_continue")
        self._opt_title = self._T("opt_title", size=18, weight=ft.FontWeight.W_600, color=TEXT)
        self.options_dialog = ft.AlertDialog(
            modal=True, bgcolor=SURFACE,
            shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, color=GREEN_HI, size=22),
                self._opt_title,
            ], spacing=10),
            content=ft.Container(
                width=460,
                content=ft.Column(
                    spacing=14, tight=True,
                    controls=[
                        self._T("opt_desc", size=13, color=MUTED),
                        ft.Divider(height=1, color=BORDER),
                        self.opt_translate,
                        self.opt_lang_note,
                        self.prompt_key_panel,
                        self.prompt_error,
                    ],
                ),
            ),
            actions=[continue_btn],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def _build_warn_dialog(self) -> None:
        """Finestra modale (arancione) che spiega cosa manca per avviare il run.
        Appare al clic su «Trascrivi» quando i requisiti non sono soddisfatti;
        non resta fissa in pagina."""
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
        """Elenco di cosa manca per abilitare «Trascrivi» (vuoto se tutto a posto)."""
        missing = []
        if not self._key_ready():
            missing.append(self.t("need_key"))
        if not self._source_ready():
            missing.append(self.t("need_src_yt") if self.source == "youtube"
                           else self.t("need_src_local"))
        return missing

    def _show_warn(self, items: list) -> None:
        """Mostra l'avviso con i requisiti mancanti come elenco puntato."""
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

    def _progress_card(self) -> ft.Control:
        self.prog_phase = ft.Text(self.t("phase_default"), size=15,
                                  weight=ft.FontWeight.W_600, color=TEXT)
        # Contatore di fase a destra (es. "Fase 2/5"), in pillola verde.
        self.prog_step = ft.Container(
            visible=False, border_radius=8,
            padding=ft.padding.symmetric(horizontal=10, vertical=3),
            bgcolor=ft.Colors.with_opacity(0.12, GREEN),
            border=ft.border.all(1, ft.Colors.with_opacity(0.35, GREEN)),
            content=ft.Text("", size=12, color=GREEN_HI, weight=ft.FontWeight.W_700))
        self.prog_pct = ft.Text("", size=14, color=GREEN_HI, weight=ft.FontWeight.BOLD)
        self.prog_bar = ft.ProgressBar(
            value=0, color=GREEN, bgcolor=SURFACE2, border_radius=8, height=8)
        self.prog_detail = ft.Text("", size=12, color=MUTED)
        # Badge "motore in uso" (Groq cloud / Locale CPU): così è sempre chiaro
        # con cosa si sta trascrivendo (il locale su CPU è lento).
        self.prog_engine_icon = ft.Icon(ft.Icons.MEMORY, size=16, color=GREEN_HI)
        self.prog_engine_text = ft.Text("", size=12, weight=ft.FontWeight.W_700, color=GREEN_HI)
        self.prog_engine = ft.Container(
            border_radius=8, padding=ft.padding.symmetric(horizontal=10, vertical=5),
            content=ft.Row([self.prog_engine_icon, self.prog_engine_text], spacing=8,
                           tight=True))
        self.prog_engine_hint = ft.Text("", size=11, color=WARN, visible=False, no_wrap=False)
        self.progress = ft.Container(
            visible=False,
            bgcolor=SURFACE, border=ft.border.all(1, BORDER),
            border_radius=16, padding=22,
            content=ft.Column(
                spacing=12,
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
                ],
            ),
        )
        return self.progress

    def _set_engine_badge(self) -> None:
        """Aggiorna il badge del motore in uso in base al backend scelto."""
        if self.backend == "groq":
            self.prog_engine_icon.name = ft.Icons.CLOUD_OUTLINED
            self.prog_engine_icon.color = GREEN_HI
            self.prog_engine_text.value = self.t("engine_groq").format(model=tx.GROQ_MODEL)
            self.prog_engine_text.color = GREEN_HI
            self.prog_engine.bgcolor = ft.Colors.with_opacity(0.12, GREEN)
            self.prog_engine.border = ft.border.all(1, ft.Colors.with_opacity(0.35, GREEN))
            self.prog_engine_hint.visible = False
        else:
            # Locale: tinta ambra + avviso che su CPU può richiedere minuti.
            self.prog_engine_icon.name = ft.Icons.COMPUTER
            self.prog_engine_icon.color = WARN
            self.prog_engine_text.value = self.t("engine_local").format(model=self.model_dd.value)
            self.prog_engine_text.color = WARN
            self.prog_engine.bgcolor = ft.Colors.with_opacity(0.12, WARN)
            self.prog_engine.border = ft.border.all(1, ft.Colors.with_opacity(0.35, WARN))
            self.prog_engine_hint.value = self.t("engine_local_hint")
            self.prog_engine_hint.visible = True

    def _build_error_dialog(self) -> None:
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
        self.model_field.visible = self.backend == "local"
        self.key_field.visible = self.backend == "groq"
        self.yt_panel.visible = self.source == "youtube"
        self.local_panel.visible = self.source == "local"

    def _refresh_prompt_key(self) -> None:
        need = (bool(self.opt_translate.value)
                and (not self._pending or self._pending.get("client") is None))
        self.prompt_key_panel.visible = need
        self.page.update()

    # --------------------------------------------------------- RUN STATE / AVVISO
    def _source_ready(self) -> bool:
        if self.source == "youtube":
            # Non basta l'URL: serve aver caricato e CONFERMATO il video.
            return self._yt_ok
        return bool(self.local_path)

    def _key_ready(self) -> bool:
        # La chiave è obbligatoria solo col backend Groq (il locale è offline).
        return self.backend != "groq" or bool(self.loaded_api_key)

    def _update_run_state(self) -> None:
        """Abilita/disabilita «Trascrivi». L'avviso su cosa manca è una finestra
        che compare al clic (vedi _on_run), non un banner fisso."""
        if self.busy:
            return
        enabled = self._key_ready() and self._source_ready()
        self._run_enabled = enabled
        self.cta.opacity = 1.0 if enabled else 0.45

    # ------------------------------------------------------------------ ACTIONS
    def _open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _open_folder(self) -> None:
        if not self.last_dir:
            return
        try:
            if os.name == "nt":
                os.startfile(self.last_dir)  # type: ignore[attr-defined]
            else:
                webbrowser.open("file://" + self.last_dir)
        except Exception:
            pass

    def _on_url_change(self) -> None:
        """Se l'URL cambia, una conferma precedente non vale più: va ricaricato."""
        self.yt_confirmed.visible = False
        self._yt_ok = False
        self._update_run_state()
        self.page.update()

    def _load_info(self) -> None:
        url = (self.url_tf.value or "").strip()
        if not url:
            return
        self._hide_error()
        self.load_btn.text = self.t("load_info_loading")
        self.load_btn.disabled = True
        self.page.update()

        def work():
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
        """Finestra elegante con copertina + dati del video, che chiede conferma."""
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
        """Video confermato: lo memorizziamo e abilitiamo «Trascrivi»."""
        self._yt_meta = meta
        self._yt_ok = True
        self.last_thumb = meta.get("thumbnail")
        self.yt_confirmed.value = self.t("yt_confirmed").format(title=meta["title"])
        self.yt_confirmed.visible = True
        self.page.close(self.yt_dialog)
        self._update_run_state()
        self.page.update()

    def _yt_cancel(self) -> None:
        """Annullato: ripuliamo URL e conferma così l'utente può inserirne un altro."""
        self._yt_meta = None
        self._yt_ok = False
        self.url_tf.value = ""
        self.yt_confirmed.visible = False
        self.page.close(self.yt_dialog)
        self._update_run_state()
        self.page.update()

    def _pick_file(self) -> None:
        self._hide_error()
        exts = sorted(e.lstrip(".") for e in tx.AUDIO_EXTENSIONS)
        self.file_picker.pick_files(
            dialog_title=self.t("pick_file_dialog"),
            allow_multiple=False, allowed_extensions=exts,
        )

    def _on_file_picked(self, e: ft.FilePickerResultEvent) -> None:
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
        if self.busy:
            return
        if not self._run_enabled:
            items = self._missing_list()
            if items:
                self._show_warn(items)
            return
        # Sorgente + metadati già caricati/confermati.
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

        # CONTROLLI prima di trascrivere (per non sprecare crediti Groq):
        #  1) già trascritto in results/  -> chiedi cosa fare (elenco);
        #  2) parziale presente (solo Groq) -> offri la ripresa;
        #  altrimenti procedi normalmente.
        if tx.transcription_exists(self.out_root, meta["title"]):
            self._show_already_dialog(src, meta)
            return
        cp = tx.load_checkpoint(meta) if self.backend == "groq" else None
        if cp:
            self._show_resume_dialog(src, meta, cp)
            return
        self._start_transcription(src, meta, resume=False)

    # --- Dialoghi di scelta (elenco professionale) -------------------------
    def _choice_dialog(self, icon_name, title: str, desc: str, options: list) -> None:
        """Apre un dialog con un ELENCO di scelte cliccabili (righe-card con
        icona, titolo e descrizione). 'options' = [{icon,label,desc,color,action}];
        in basso un pulsante Annulla."""
        holder = {}

        def pick(action):
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
        self._choice_dialog(
            ft.Icons.HISTORY, self.t("already_title"), self.t("already_desc"),
            [
                {"icon": ft.Icons.REFRESH, "label": self.t("opt_retranscribe"),
                 "desc": self.t("opt_retranscribe_desc"), "color": GREEN,
                 "action": lambda: self._start_transcription(src, meta, resume=False)},
                {"icon": ft.Icons.TRANSLATE, "label": self.t("opt_only_translate"),
                 "desc": self.t("opt_only_translate_desc"), "color": GREEN_HI,
                 "action": lambda: self._start_translate_only(meta)},
            ])

    def _show_resume_dialog(self, src, meta: dict, cp: dict) -> None:
        done, total = cp.get("done_chunks", 0), cp.get("total_chunks", 0)

        def restart():
            tx.delete_checkpoint(meta)
            self._start_transcription(src, meta, resume=False)

        self._choice_dialog(
            ft.Icons.HOURGLASS_BOTTOM, self.t("resume_title"), self.t("resume_desc"),
            [
                {"icon": ft.Icons.PLAY_ARROW, "label": self.t("resume_opt_resume"),
                 "desc": self.t("resume_opt_resume_desc").format(done=done, total=total),
                 "color": GREEN,
                 "action": lambda: self._start_transcription(src, meta, resume=True)},
                {"icon": ft.Icons.RESTART_ALT, "label": self.t("resume_opt_restart"),
                 "desc": self.t("resume_opt_restart_desc"), "color": WARN,
                 "action": restart},
            ])

    def _start_transcription(self, src, meta: dict, resume: bool = False) -> None:
        options = {
            "backend": self.backend, "model": self.model_dd.value,
            "api_key": self.loaded_api_key or "", "translate": False,
            "export": False, "source_kind": self.source,
        }
        self._plan = self._phase_plan(self.backend, self.source, translate=True)
        self._last_g = 0.0
        self._hide_error()
        self._set_busy(True)
        self._set_engine_badge()
        self._set_phase("info", None, None, "")
        self._show_progress(True)
        self.page.update()

        def work():
            try:
                meta2, segments, engine_label, client = engine.transcribe_only(
                    src, options, on_progress=self._on_progress, resume=resume)
                self._pending = {
                    "meta": meta2, "segments": segments,
                    "engine_label": engine_label, "client": client, "options": options,
                }
                self.last_thumb = meta2.get("thumbnail")
                lang = (meta2.get("detected_language") or "").lower()
                self._detected_lang = lang
                italian = lang.startswith("it")
                self._show_progress(False)
                self.opt_translate.visible = not italian
                self.opt_lang_note.visible = italian
                self.opt_translate.value = not italian
                self.prompt_error.visible = False
                self.prompt_key_panel.visible = (not italian) and (client is None)
                self._set_busy(False)
                self.page.update()
                self.page.open(self.options_dialog)
            except engine.RateLimitReached as ex:
                self._fail_ratelimit(ex)
            except engine.EngineError as ex:
                self._fail(str(ex))
            except Exception as ex:
                self._fail(self.t("err_unexpected").format(e=ex))

        threading.Thread(target=work, daemon=True).start()

    def _start_translate_only(self, meta: dict) -> None:
        """Sola ri-traduzione di una trascrizione esistente (no ri-trascrizione)."""
        self._plan = ["translate", "export"]
        self._last_g = 0.0
        self._hide_error()
        self._set_busy(True)
        # Badge: la traduzione usa sempre Groq.
        self.prog_engine_icon.name = ft.Icons.TRANSLATE
        self.prog_engine_icon.color = GREEN_HI
        self.prog_engine_text.value = self.t("engine_translate")
        self.prog_engine_text.color = GREEN_HI
        self.prog_engine.bgcolor = ft.Colors.with_opacity(0.12, GREEN)
        self.prog_engine.border = ft.border.all(1, ft.Colors.with_opacity(0.35, GREEN))
        self.prog_engine_hint.visible = False
        self._set_phase("translate", None, None, "")
        self._show_progress(True)
        self.page.update()

        def work():
            try:
                client = engine.make_groq_client(self.loaded_api_key or None)
                result = engine.translate_existing(
                    self.out_root, meta["title"], client, on_progress=self._on_progress)
                self.last_thumb = meta.get("thumbnail")
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

    def _confirm_options(self, e: ft.ControlEvent) -> None:
        p = self._pending
        if not p:
            return
        p["options"]["translate"] = bool(self.opt_translate.value)
        p["options"]["export"] = True  # PDF sempre generato (richiesta utente)

        if p["options"]["translate"] and p["client"] is None:
            self.prompt_error.visible = False
            try:
                p["client"] = engine.make_groq_client(self.loaded_api_key or None)
            except engine.EngineError as ex:
                self._prompt_show_error(str(ex))
                return
            except Exception as ex:
                self._prompt_show_error(self.t("groq_key_error").format(e=ex))
                return

        self.page.close(self.options_dialog)
        self._do_save(self.out_root)

    def _prompt_show_error(self, msg: str) -> None:
        self.prompt_error.content.value = msg
        self.prompt_error.visible = True
        self.prompt_key_panel.visible = True
        self.page.update()

    def _do_save(self, out_root: str) -> None:
        """Salva tutti gli output nella cartella di output (results/)."""
        if not self._pending:
            return
        self._set_busy(True)
        # Prima fase del salvataggio: traduzione (se scelta) o esportazione.
        first = "translate" if self._pending["options"]["translate"] else "export"
        self._set_phase(first, None, None,
                        "" if first == "translate" else self.t("saving_files"))
        self._show_progress(True)
        self.page.update()

        def work():
            p = self._pending
            try:
                result = engine.save_results(
                    p["meta"], p["segments"], p["engine_label"], p["options"],
                    out_root, p["client"], on_progress=self._on_progress)
                self._pending = None
                # Completato: porta la barra al 100% prima di mostrare il riepilogo.
                self.prog_bar.value = 1.0
                self.prog_pct.value = "100%"
                self.page.update()
                self._show_progress(False)
                self._set_busy(False)
                self._render_result(result)
            except Exception as ex:
                self._fail(self.t("err_save").format(e=ex))

        threading.Thread(target=work, daemon=True).start()

    def _fail_ratelimit(self, ex) -> None:
        """Limite Groq raggiunto: avviso dedicato (non un errore rosso). Il
        parziale è già stato salvato dal motore: si potrà riprendere dopo."""
        self._show_progress(False)
        self._set_busy(False)
        msg = self.t("ratelimit_msg").format(done=ex.done, total=ex.total)
        close = ft.FilledButton(
            self.t("btn_close"), icon=ft.Icons.CHECK,
            on_click=lambda e: self.page.close(self._rl_dialog),
            style=ft.ButtonStyle(bgcolor=WARN, color="#1A1206",
                                 shape=ft.RoundedRectangleBorder(radius=10),
                                 padding=ft.padding.symmetric(horizontal=18, vertical=16)))
        self._rl_dialog = ft.AlertDialog(
            modal=True, bgcolor=SURFACE, shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Row([ft.Icon(ft.Icons.HOURGLASS_DISABLED, color=WARN, size=22),
                          ft.Text(self.t("ratelimit_title"), size=18,
                                  weight=ft.FontWeight.W_600, color=WARN)], spacing=10),
            content=ft.Container(width=460,
                                 content=ft.Text(msg, size=13, color=TEXT, no_wrap=False)),
            actions=[close], actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(self._rl_dialog)

    # --------------------------------------------------------------- PROGRESS UI
    def _on_progress(self, phase, current, total, detail="") -> None:
        self._set_phase(phase, current, total, detail)
        self.page.update()

    @staticmethod
    def _phase_plan(backend: str, source_kind: str, translate: bool) -> list:
        """Sequenza ordinata delle fasi del run, per numerare 'Fase i/n'.

        Dipende dal contesto: i file locali saltano il download, solo Groq fa lo
        splitting ('prepare'), la traduzione è una fase opzionale."""
        plan = ["info"]
        if source_kind != "local":
            plan.append("download")
        if backend == "groq":
            plan.append("prepare")
        plan.append("transcribe")
        if translate:
            plan.append("translate")
        plan.append("export")
        return plan

    def _set_phase(self, phase, current, total, detail) -> None:
        self._cur_phase = phase
        key = "phase_" + phase
        label = self.t(key) if key in T[self.lang] else self.t("phase_default")
        if phase == "translate":
            label += " " + self.t("phase_optional")  # la traduzione è opzionale
        self.prog_phase.value = label

        self.prog_detail.value = detail or ""

        # Avanzamento GLOBALE e reale: ogni fase occupa una fetta [i/n, (i+1)/n]
        # del totale; dentro la fase interpoliamo con il progresso vero (byte,
        # blocco i/n, secondi trascritti, sezione i/n). Quando una fase non ha un
        # progresso noto (es. "carico modello"), la barra RESTA ferma all'inizio
        # della sua fetta invece di girare in loop: avanza solo quando avanza
        # davvero. La barra non torna mai indietro perché il piano è fisso.
        n = len(self._plan)
        if phase in self._plan and n:
            i = self._plan.index(phase)
            frac = max(0.0, min(1.0, current / total)) if (current is not None and total) else 0.0
            g = (i + frac) / n
            # Anti-ritorno: aggiornamenti indeterminati a metà fase (es. "Estraggo
            # audio") non devono far scendere la barra. Tiene il valore più alto.
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
        self.last_dir = res["video_dir"]

        def chip(icon, label, value):
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
            icon = ft.Icons.TRANSLATE if folder == "traduzioni" else ft.Icons.FOLDER
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
        """Mostra la barra di avanzamento al posto del pulsante (stesso slot)."""
        self.progress.visible = on
        self.cta.visible = not on

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.cta_text.value = self.t("cta_busy") if busy else self.t("cta_run")
        self.cta_icon.name = ft.Icons.HOURGLASS_TOP if busy else ft.Icons.AUTO_AWESOME
        if busy:
            self.cta.opacity = 0.5
        else:
            self._update_run_state()

    def _close_dialog(self, dlg) -> None:
        """Chiude un dialog solo se è davvero aperto: chiamare page.close() su un
        AlertDialog mai mostrato fa un assert ('must be added to the page first')."""
        if dlg is not None and getattr(dlg, "open", False):
            self.page.close(dlg)

    def _fail(self, message: str) -> None:
        self._show_progress(False)
        self._close_dialog(getattr(self, "options_dialog", None))
        self._set_busy(False)
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self.err_text.value = message or self.t("err_unknown")
        self.page.open(self.error_dialog)

    def _hide_error(self) -> None:
        self._close_dialog(getattr(self, "error_dialog", None))


def main(page: ft.Page) -> None:
    EchoScriptApp(page)


if __name__ == "__main__":
    ft.app(target=main)
