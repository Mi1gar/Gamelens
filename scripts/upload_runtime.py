"""Create ML runtime package for GameLens.

Usage:
    python scripts/upload_runtime.py                 # create + upload to Firebase
    python scripts/upload_runtime.py --local-only    # just create zip, don't upload
    python scripts/upload_runtime.py --output D:\runtime.zip  # custom output path

Upload the resulting zip anywhere (Google Drive, Dropbox, CDN).
Set the URL in runtime_url.txt before building the EXE.
"""
import os
import sys
import zipfile
import site
import tempfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import firebase_admin
from firebase_admin import credentials, storage

# Find the real site-packages (not Python root)
_sps = site.getsitepackages()
SITEPACKAGES = _sps[1] if len(_sps) > 1 and 'site-packages' in _sps[1] else _sps[0]
BUCKET_NAME = "gamelens-4fd98.firebasestorage.app"

PACKAGES = [
    # ONNX Runtime (YOLO inference + RapidOCR)
    "onnxruntime",
    # CTranslate2 (NLLB translation)
    "ctranslate2",
    # OpenCV (image preprocessing)
    "cv2",
    # RapidOCR (text recognition)
    "rapidocr_onnxruntime",
    "rapidocr",
]


def _init():
    key_path = os.environ.get(
        "GAMELENS_FIREBASE_KEY",
        os.path.join(PROJECT_ROOT, "firebase", "gamelens-firebase-key.json"),
    )
    cred = credentials.Certificate(key_path)
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(cred, {"storageBucket": BUCKET_NAME})


def upload_runtime():
    _init()
    bucket = storage.bucket()

    zip_path = os.path.join(tempfile.gettempdir(), "torch-runtime-windows.zip")

    print("[Upload] Creating torch runtime package...")
    total_size = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for pkg in PACKAGES:
            pkg_path = os.path.join(SITEPACKAGES, pkg)
            if not os.path.exists(pkg_path):
                print(f"  WARNING: {pkg} not found, skipping.")
                continue
            for root, _, files in os.walk(pkg_path):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    arcname = os.path.relpath(fpath, SITEPACKAGES)
                    zf.write(fpath, arcname)
                    total_size += os.path.getsize(fpath)

    zip_size = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[Upload] Package: {zip_size:.0f} MB (uncompressed: {total_size/1024/1024:.0f} MB)")

    blob_path = "runtime/torch-runtime-windows.zip"
    blob = bucket.blob(blob_path)
    print(f"[Upload] Uploading to {blob_path} ({zip_size:.0f} MB)...")
    blob.upload_from_filename(zip_path, timeout=1800)  # 30 min timeout
    blob.make_public()

    print(f"[Upload] Done: {blob.public_url}")
    os.remove(zip_path)
    print(f"\nUsers download this automatically on first launch.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Create ML runtime package")
    parser.add_argument("--local-only", action="store_true",
                        help="Only create zip, don't upload")
    parser.add_argument("--output", default="",
                        help="Custom output path for the zip")
    args = parser.parse_args()

    if args.local_only or args.output:
        # Just create the zip locally
        zip_path = args.output or os.path.join(
            tempfile.gettempdir(), "torch-runtime-windows.zip",
        )
        print(f"[Runtime] Creating package at {zip_path}...")
        total_size = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for pkg in PACKAGES:
                pkg_path = os.path.join(SITEPACKAGES, pkg)
                if not os.path.exists(pkg_path):
                    print(f"  WARNING: {pkg} not found, skipping.")
                    continue
                for root, _, files in os.walk(pkg_path):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        arcname = os.path.relpath(fpath, SITEPACKAGES)
                        zf.write(fpath, arcname)
                        total_size += os.path.getsize(fpath)
        zip_size = os.path.getsize(zip_path) / (1024 * 1024)
        print(f"[Runtime] Done: {zip_path} ({zip_size:.0f} MB)")
        print(f"[Runtime] Upload this file and set URL in runtime_url.txt")
    else:
        upload_runtime()
