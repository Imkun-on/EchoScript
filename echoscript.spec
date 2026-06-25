# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
#  PyInstaller spec for EchoScript — desktop GUI (one-folder build).
# =============================================================================
#  Build:  pyinstaller echoscript.spec --noconfirm
#  Output: dist/EchoScript/EchoScript.exe  (+ the _internal/ folder)
#
#  Bundles: the Flet GUI, the shared engine, the Groq + local (faster-whisper)
#  backends, and ffmpeg/ffprobe (found in PATH at build time) so the .exe is
#  self-contained. PyTorch is intentionally EXCLUDED: faster-whisper runs on
#  ctranslate2 (CPU) and the optional GPU auto-detect degrades gracefully.
#
#  NB: local Whisper model weights are NOT bundled; faster-whisper downloads
#  them from HuggingFace on first use (cached afterwards).
# =============================================================================
import os
import shutil
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.getcwd())

# --- Bundle ffmpeg + ffprobe (resolved from PATH at build time) -------------
binaries = []
for _tool in ("ffmpeg", "ffprobe"):
    _path = shutil.which(_tool)
    if _path:
        binaries.append((_path, "."))   # placed in the bundle root (on PATH at runtime)

# --- Collect data files / hidden imports for the heavy packages -------------
datas = []
hiddenimports = ["transcriber", "engine"]
for _pkg in ("flet", "flet_desktop", "faster_whisper", "av", "ctranslate2",
             "onnxruntime", "tokenizers", "huggingface_hub", "yt_dlp",
             "groq", "fpdf", "rich"):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        pass

a = Analysis(
    ["gui/main.py"],
    pathex=[ROOT, os.path.join(ROOT, "core")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "tkinter", "matplotlib", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EchoScript",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EchoScript",
)
