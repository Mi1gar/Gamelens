"""Upload models to Firebase Storage + update Firestore version tracking.

Usage:
    python scripts/upload_models.py                # upload NLLB (first time)
    python scripts/upload_models.py --yolo         # upload YOLO model
    python scripts/upload_models.py --yolo --notes "Better RDR2 detection"

YOLO flow:
  1. Train new model -> models/Vision_C1P_03.pt
  2. python scripts/upload_models.py --yolo
  3. All users download new model on next launch (~5 MB, seconds)
"""
import argparse
import json
import os
import sys
import zipfile
import tempfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import firebase_admin
from firebase_admin import credentials, firestore as admin_firestore, storage
from google.cloud import firestore as gc_firestore

BUCKET_NAME = "gamelens-4fd98.firebasestorage.app"
MODEL_DIR = os.path.join(PROJECT_ROOT, "models")


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


def upload_nllb():
    """Zip and upload full NLLB-200 model dir."""
    src_dir = os.path.join(MODEL_DIR, "nllb-200-600m-ct2-int8")
    if not os.path.isdir(src_dir):
        print(f"Error: {src_dir} not found.")
        return

    _init()
    bucket = storage.bucket()

    zip_path = os.path.join(tempfile.gettempdir(), "nllb-200-600m-ct2-int8.zip")
    print("[Upload] Zipping NLLB model...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(src_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, os.path.dirname(src_dir))
                zf.write(fpath, arcname)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[Upload] Zip: {size_mb:.0f} MB")

    blob_path = "models/nllb-200-600m-ct2-int8.zip"
    blob = bucket.blob(blob_path)
    print(f"[Upload] Uploading to {blob_path}...")
    blob.upload_from_filename(zip_path)
    blob.make_public()
    os.remove(zip_path)

    print(f"[Upload] Done: {blob.public_url}")


def upload_yolo(model_path: str = "", notes: str = ""):
    """Upload YOLO model + update Firestore version tracker.

    Detects version from existing Firestore doc (auto-increment).
    """
    _init()
    db = admin_firestore.client()
    bucket = storage.bucket()

    # Find model file
    if not model_path:
        # Auto-detect: latest Vision_C1P_*.pt
        candidates = sorted(
            [f for f in os.listdir(MODEL_DIR) if f.startswith("Vision_C1P_") and f.endswith(".pt")],
            reverse=True,
        )
        if not candidates:
            print("Error: No Vision_C1P_*.pt found in models/. Specify --model-path.")
            return
        model_path = os.path.join(MODEL_DIR, candidates[0])

    if not os.path.exists(model_path):
        print(f"Error: {model_path} not found.")
        return

    model_name = os.path.basename(model_path)
    size_mb = os.path.getsize(model_path) / (1024 * 1024)

    # Get current version from Firestore + increment
    doc_ref = db.collection("models").document("yolo_subtitle")
    doc = doc_ref.get()
    current_version = 0
    if doc.exists:
        current_version = doc.to_dict().get("version", 0)

    new_version = current_version + 1

    # Upload model file
    blob_path = f"models/{model_name}"
    blob = bucket.blob(blob_path)
    print(f"[Upload] YOLO {model_name} ({size_mb:.1f} MB) -> {blob_path}")
    blob.upload_from_filename(model_path)
    blob.make_public()

    # Update Firestore
    doc_ref.set({
        "version": new_version,
        "model_name": model_name,
        "url": blob.public_url,
        "size_mb": round(size_mb, 1),
        "notes": notes,
        "updated_at": gc_firestore.SERVER_TIMESTAMP,
    })
    print(f"[Upload] Firestore /models/yolo_subtitle -> v{new_version}")
    print(f"[Upload] URL: {blob.public_url}")
    print(f"\nUsers will auto-download on next launch (~5 MB).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload models to Firebase")
    parser.add_argument("--yolo", action="store_true", help="Upload YOLO model")
    parser.add_argument("--model-path", default="", help="Path to .pt file")
    parser.add_argument("--notes", default="", help="Release notes")
    args = parser.parse_args()

    if args.yolo:
        upload_yolo(args.model_path, args.notes)
    else:
        upload_nllb()
