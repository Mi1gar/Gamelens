"""Model manager — NLLB download + YOLO updates via Firebase.

Both models are checked at app startup:
  - NLLB-200 (594 MB): downloaded once on first launch
  - YOLO subtitle detector (~5 MB): checked for updates each launch

YOLO updates are separate from app updates — no EXE rebuild needed.
Upload a new YOLO model via: python scripts/upload_models.py --yolo
"""
import json
import os
import sys
import zipfile
import urllib.request

# ── Paths ──

MODEL_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "models",
)
RUNTIME_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "GameLens", "runtime",
)

# ── NLLB-200 ──

NLLB_MODEL_DIR = os.path.join(MODEL_DIR, "nllb-200-600m-ct2-int8")
NLLB_MODEL_FILE = os.path.join(NLLB_MODEL_DIR, "model.bin")

# ── ML Runtime (all GPU/ML libs, downloaded on first launch) ──
# Includes: torch, onnxruntime, ctranslate2, cv2, ultralytics,
#           rapidocr, transformers, nvidia CUDA, and more
#
# URL priority:
#   1. environment variable GAMELENS_RUNTIME_URL
#   2. bundled runtime_url.txt file
#   3. default (Firebase Storage)

RUNTIME_CHECK_FILE = os.path.join(RUNTIME_DIR, "torch", "__init__.py")

_RUNTIME_URL_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "runtime_url.txt",
)

_DEFAULT_RUNTIME_URL = (
    "https://storage.googleapis.com/gamelens-4fd98.firebasestorage.app/"
    "runtime/torch-runtime-windows.zip"
)


def _get_runtime_url() -> str:
    """Get the runtime download URL (checks multiple sources)."""
    # 1. Environment variable override
    url = os.environ.get("GAMELENS_RUNTIME_URL")
    if url:
        return url
    # 2. Bundled config file
    if os.path.exists(_RUNTIME_URL_FILE):
        try:
            with open(_RUNTIME_URL_FILE, "r") as f:
                url = f.read().strip()
                if url and not url.startswith("#"):
                    return url
        except Exception:
            pass
    # 3. Default
    return _DEFAULT_RUNTIME_URL
_DEFAULT_NLLB_URL = (
    "https://storage.googleapis.com/gamelens-4fd98.firebasestorage.app/"
    "models/nllb-200-600m-ct2-int8.zip"
)

_NLLB_URL_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "nllb_url.txt",
)


def _get_nllb_url() -> str:
    url = os.environ.get("GAMELENS_NLLB_URL")
    if url:
        return url
    if os.path.exists(_NLLB_URL_FILE):
        try:
            with open(_NLLB_URL_FILE, "r") as f:
                url = f.read().strip()
                if url and not url.startswith("#"):
                    return url
        except Exception:
            pass
    return _DEFAULT_NLLB_URL

# ── YOLO ──

YOLO_LOCAL_VERSION_PATH = os.path.join(MODEL_DIR, ".yolo_version")
YOLO_FIRESTORE_DOC = "models/yolo_subtitle"


# ── NLLB ──

def is_nllb_installed() -> bool:
    return os.path.exists(NLLB_MODEL_FILE)


def download_nllb(progress_callback=None) -> bool:
    """Download NLLB model from Firebase Storage (one-time, ~600 MB)."""
    if is_nllb_installed():
        print("[ModelManager] NLLB model already installed.")
        return True

    print("[ModelManager] NLLB model not found. Downloading (~600 MB, one-time)...")
    os.makedirs(MODEL_DIR, exist_ok=True)

    zip_path = os.path.join(MODEL_DIR, "nllb_download.zip")
    try:
        _download_file(_get_nllb_url(), zip_path, progress_callback)
        print("[ModelManager] Extracting...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(MODEL_DIR)
        os.remove(zip_path)

        if is_nllb_installed():
            size_mb = os.path.getsize(NLLB_MODEL_FILE) / (1024 * 1024)
            print(f"[ModelManager] NLLB installed ({size_mb:.0f} MB).")
            return True
        else:
            print("[ModelManager] Error: model.bin not found after extract.")
            return False
    except Exception as e:
        print(f"[ModelManager] NLLB download failed: {e}")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return False


# ── YOLO ──

def _get_local_yolo_version() -> int:
    """Read local YOLO version (0 if unknown)."""
    if os.path.exists(YOLO_LOCAL_VERSION_PATH):
        try:
            with open(YOLO_LOCAL_VERSION_PATH, "r") as f:
                return json.load(f).get("version", 0)
        except Exception:
            pass
    return 0


def _get_remote_yolo_version() -> dict | None:
    """Query Firestore for latest YOLO model."""
    try:
        import firebase_admin
        from firebase_admin import firestore as admin_firestore

        try:
            firebase_admin.get_app()
        except ValueError:
            return None  # offline — no update check

        db = admin_firestore.client()
        doc = db.collection("models").document("yolo_subtitle").get()
        if doc.exists:
            return doc.to_dict()
    except Exception:
        pass
    return None


def check_yolo_update(auto_download: bool = True) -> dict:
    """Check if a newer YOLO model is available.

    Returns dict with update info. Downloads if auto_download=True.
    """
    local_ver = _get_local_yolo_version()
    remote = _get_remote_yolo_version()

    if remote is None:
        return {"update_available": False, "local_version": local_ver,
                "reason": "offline"}

    remote_ver = remote.get("version", 0)

    if remote_ver <= local_ver:
        return {"update_available": False, "local_version": local_ver,
                "remote_version": remote_ver}

    # Update available!
    info = {
        "update_available": True,
        "local_version": local_ver,
        "remote_version": remote_ver,
        "model_name": remote.get("model_name", "Vision_C1P_0x.pt"),
        "url": remote.get("url", ""),
        "notes": remote.get("notes", ""),
    }

    if not auto_download or not info["url"]:
        return info

    # Download new YOLO model
    yolo_path = os.path.join(MODEL_DIR, info["model_name"])
    print(f"[ModelManager] YOLO update: v{local_ver} -> v{remote_ver}")
    print(f"[ModelManager] Downloading {info['model_name']} (~5 MB)...")

    try:
        _download_file(info["url"], yolo_path)
        # Save version
        with open(YOLO_LOCAL_VERSION_PATH, "w") as f:
            json.dump({"version": remote_ver, "model": info["model_name"]}, f)
        print(f"[ModelManager] YOLO updated to v{remote_ver}.")
        info["downloaded"] = True
    except Exception as e:
        print(f"[ModelManager] YOLO download failed: {e}")
        info["downloaded"] = False

    return info


def get_yolo_model_path() -> str:
    """Get path to the active YOLO model.

    Returns the updated model path if available, falls back to bundled.
    """
    # Check if we have a version-tracked model
    if os.path.exists(YOLO_LOCAL_VERSION_PATH):
        try:
            with open(YOLO_LOCAL_VERSION_PATH, "r") as f:
                meta = json.load(f)
            model_name = meta.get("model", "")
            path = os.path.join(MODEL_DIR, model_name)
            if os.path.exists(path):
                return path
        except Exception:
            pass

    # Fallback: bundled model
    fallback = os.path.join(MODEL_DIR, "Vision_C1P_02.pt")
    return fallback


# ── Torch Runtime ──

def is_runtime_installed() -> bool:
    """Check if ML runtime is available."""
    return os.path.exists(RUNTIME_CHECK_FILE)


def install_runtime(progress_callback=None) -> bool:
    """Download ML runtime (one-time, ~2-3 GB)."""
    if is_runtime_installed():
        print("[ModelManager] ML runtime already installed.")
        return True

    print("[ModelManager] ML runtime not found. Downloading (~2-3 GB, one-time)...")
    os.makedirs(RUNTIME_DIR, exist_ok=True)

    zip_path = os.path.join(RUNTIME_DIR, "runtime.zip")
    try:
        _download_file(_get_runtime_url(), zip_path, progress_callback)
        print("[ModelManager] Extracting runtime...")
        import zipfile
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(RUNTIME_DIR)
        os.remove(zip_path)

        if is_runtime_installed():
            if RUNTIME_DIR not in sys.path:
                sys.path.insert(0, RUNTIME_DIR)
            print("[ModelManager] ML runtime installed.")
            return True
        else:
            print("[ModelManager] Error: runtime not found after extract.")
            return False
    except Exception as e:
        print(f"[ModelManager] Runtime download failed: {e}")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return False


# ── Helpers ──

def _download_file(url: str, dest: str, progress_callback=None):
    """Download with optional progress reporting."""
    response = urllib.request.urlopen(url)
    total = int(response.headers.get("content-length", 0))
    downloaded = 0
    chunk_size = 1024 * 1024  # 1 MB chunks

    with open(dest, "wb") as f:
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_callback and total > 0:
                pct = int(downloaded / total * 100)
                mb_done = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                progress_callback(pct, mb_done, mb_total)


# ── Startup check ──

def ensure_models() -> bool:
    """Ensure all models and runtime are available. Call at app startup.

    Returns True if everything is ready.
    Must be called BEFORE any torch/engine imports!
    """
    # ML runtime (must be first — everything depends on it)
    if not is_runtime_installed():
        print("[ModelManager] ML runtime required. Downloading...")
        if not install_runtime():
            print("[ModelManager] FATAL: ML runtime download failed.")
            return False
    elif RUNTIME_DIR not in sys.path:
        sys.path.insert(0, RUNTIME_DIR)

    # YOLO must exist (bundled in EXE as fallback)
    yolo = get_yolo_model_path()
    if not os.path.exists(yolo):
        print(f"[ModelManager] ERROR: YOLO model not found at {yolo}")
        return False
    print(f"[ModelManager] YOLO: {os.path.basename(yolo)}")

    # Check for YOLO update
    yolo_update = check_yolo_update(auto_download=True)
    if yolo_update.get("update_available"):
        if yolo_update.get("downloaded"):
            print(f"[ModelManager] YOLO updated to v{yolo_update['remote_version']}")
        else:
            print("[ModelManager] YOLO update available but download failed. "
                  "Using current model.")

    # NLLB is optional
    if not is_nllb_installed():
        print("[ModelManager] NLLB not installed. Translation: local DB only.")
    else:
        print("[ModelManager] NLLB: ready.")

    return True


if __name__ == "__main__":
    def progress(pct, done, total):
        print(f"\r  {pct}% ({done:.0f}/{total:.0f} MB)", end="", flush=True)

    print(f"Model dir: {MODEL_DIR}")
    print(f"NLLB installed: {is_nllb_installed()}")
    print(f"YOLO path: {get_yolo_model_path()}")
    print(f"YOLO local version: {_get_local_yolo_version()}")

    if not is_nllb_installed():
        print("\nDownloading NLLB model...")
        download_nllb(progress)

    print("\nChecking YOLO update...")
    info = check_yolo_update(auto_download=False)
    print(json.dumps(info, indent=2))
