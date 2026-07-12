# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for GameLens — one EXE build."""

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).absolute()

# ── Hidden imports (dynamic imports PyInstaller can't detect) ──
hiddenimports = [
    # ML frameworks
    'torch', 'torchvision', 'torchaudio',
    'onnxruntime', 'onnxruntime.transformers',
    'ctranslate2',
    'ultralytics', 'ultralytics.nn',
    'rapidocr_onnxruntime',
    # NLP
    'transformers', 'tokenizers',
    'sentencepiece',
    # Firebase
    'firebase_admin', 'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.storage',
    'google.api_core',
    'grpc', 'grpc._cython',
    # Screen capture
    'dxcam', 'mss',
    # Image processing
    'cv2', 'PIL', 'numpy',
    # UI
    'tkinter',
    # Game adapters (dynamic import)
    'engine.adapters.rdr2_adapter',
    'engine.adapters.metro_adapter',
    'engine.adapters.gta5_adapter',
    'engine.adapters.firewatch_adapter',
    # Engine modules (all dynamic imports)
    'engine.core', 'engine.core.hook_manager',
    'engine.core.subtitle_detector', 'engine.core.preprocessor',
    'engine.core.temporal_filter', 'engine.core.text_cleaner',
    'engine.core.translator', 'engine.core.nllb_translator',
    'engine.core.manual_translations', 'engine.core.game_detector',
    'engine.core.subtitle_loader', 'engine.core.catalog_manager',
    'engine.core.mod_installer', 'engine.core.registry',
    'engine.core.interfaces', 'engine.core.cloud_translations',
    'engine.core.updater',
    'engine.services', 'engine.services.translation_service',
    'engine.overlay', 'engine.overlay.subtitle_overlay',
]

# ── Data files (bundled with EXE) ──
datas = [
    # Version file (for OTA updates)
    (str(ROOT / 'version.json'), '.'),
    # Runtime download URLs (configurable per release)
    (str(ROOT / 'runtime_url.txt'), '.'),
    (str(ROOT / 'nllb_url.txt'), '.'),
    # Logo (for splash screen)
    (str(ROOT / 'icons' / 'logo' / 'gamelens_logo.png'), 'icons/logo'),
    # YOLO model (tiny, 5 MB — always bundled)
    (str(ROOT / 'models' / 'Vision_C1P_02.pt'), 'models'),
    # ONNX model (YOLO exported, ~9 MB)
    (str(ROOT / 'models' / 'Vision_C1P_02.onnx'), 'models'),
    # Import dialogues
    (str(ROOT / 'import'), 'import'),
    # Growing DB (if exists)
]

# NLLB-200 model NOT bundled — downloaded on first launch from Firebase Storage
# Size: 594 MB. Keeps EXE small (~150 MB) and updates fast.
# See engine/core/model_manager.py for the download logic.

# Add growing_memory.json if it exists
growing_db = ROOT / 'dataset_live' / 'growing_memory.json'
if growing_db.exists():
    datas.append((str(growing_db), 'dataset_live'))

# Add sync_meta.json if it exists
sync_meta = ROOT / 'dataset_live' / 'sync_meta.json'
if sync_meta.exists():
    datas.append((str(sync_meta), 'dataset_live'))

# Add manual translations if exists
manual = ROOT / 'engine' / 'core' / 'manual_overrides.json'
if manual.exists():
    datas.append((str(manual), 'engine/core'))

# Add Firebase key if packaging with app (NOT recommended for production)
# firebase_key = ROOT / 'firebase' / 'gamelens-firebase-key.json'
# if firebase_key.exists():
#     datas.append((str(firebase_key), 'firebase'))


# ── PyInstaller config ──
a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test', 'unittest', 'pytest', 'coverage',
        'matplotlib', 'jupyter', 'ipykernel', 'notebook',
        'tensorflow', 'tensorboard', 'tf_keras', 'keras',
        # ── Runtime package (downloaded on first launch) ──
        'onnxruntime', 'onnxruntime.transformers',
        'ctranslate2',
        'cv2', 'opencv_python',
        'rapidocr_onnxruntime', 'rapidocr',
        # ── No longer used (YOLO now ONNX Runtime, no torch needed) ──
        'torch', 'torchvision', 'torchaudio',
        'ultralytics', 'timm',
        'nvidia',
        # ── Only needed for training pipeline, not live app ──
        'transformers', 'tokenizers', 'sentencepiece',
        # ── Other heavy unused ──
        'numba', 'llvmlite',
        'sklearn', 'scipy',
        'spacy', 'thinc', 'blis',
        'librosa', 'soundfile', 'soxr', 'audioread', 'pydub',
        'pygame',
        'fastapi', 'uvicorn', 'starlette', 'websockets',
        'pydantic', 'anyio', 'sniffio', 'watchfiles',
        'yt_dlp',
        'rich', 'prompt_toolkit', 'pygments',
        'sympy', 'mpmath', 'networkx',
        'requests_toolbelt',
        'IPython', 'ipython', 'traitlets',
        'wandb', 'mlflow', 'clearml',
        'einops',
        'nltk',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GameLens',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'icons' / 'logo' / 'gamelens_logo.ico'),
)

# ── Size estimates ──
# YOLO model: ~5 MB
# Python + deps: ~150 MB
# Total EXE: ~150 MB (NLLB model downloaded separately on first launch)
print("\n" + "=" * 60)
print("GameLens PyInstaller spec ready.")
print("Expected EXE size: ~150 MB")
print("NLLB-200 model (594 MB) will be downloaded on first launch.")
print("")
print("To build:")
print("  pyinstaller GameLens.spec")
print("")
print("To upload after build:")
print("  python scripts/upload_release.py dist/GameLens.exe")
print("=" * 60)
