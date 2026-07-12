"""Upload a new release EXE to Firebase Storage + update Firestore.

Usage:
    python scripts/upload_release.py dist/GameLens-0.2.0.exe --notes "Changelog"
    python scripts/upload_release.py dist/GameLens-0.2.0.exe --channel beta

This script:
  1. Reads version.json to get current version
  2. Uploads EXE to Firebase Storage: releases/GameLens-X.Y.Z.exe
  3. Makes it publicly accessible (signed URL)
  4. Updates Firestore /releases/stable with version + URL + metadata
"""
import argparse
import hashlib
import json
import os
import sys
import time

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import firebase_admin
from firebase_admin import credentials, firestore as admin_firestore
from firebase_admin import storage
from google.cloud import firestore


def _init():
    key_path = os.environ.get(
        "GAMELENS_FIREBASE_KEY",
        os.path.join(PROJECT_ROOT, "firebase", "gamelens-firebase-key.json"),
    )
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred, {
        "storageBucket": "gamelens-4fd98.firebasestorage.app",
    })


def _get_version():
    with open(os.path.join(PROJECT_ROOT, "version.json"), "r") as f:
        return json.load(f)


def _sha256_hex(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def upload(exe_path: str, notes: str = "", channel: str = "stable"):
    """Upload EXE to Firebase Storage and update Firestore."""
    version = _get_version()
    _init()

    db = admin_firestore.client()
    bucket = storage.bucket()

    # 1. Upload EXE
    exe_name = f"GameLens-{version['version']}.exe"
    blob_path = f"releases/{exe_name}"
    blob = bucket.blob(blob_path)

    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    print(f"[Upload] {exe_name} ({size_mb:.1f} MB)")
    print(f"[Upload] Computing hash...")
    checksum = _sha256_hex(exe_path)

    blob.upload_from_filename(exe_path)
    blob.make_public()
    print(f"[Upload] OK: {blob.public_url}")

    # 2. Update Firestore
    release = {
        "version": version["version"],
        "build": version.get("build", 1),
        "url": blob.public_url,
        "size_mb": round(size_mb, 1),
        "checksum": checksum,
        "notes": notes,
        "channel": channel,
        "published_at": firestore.SERVER_TIMESTAMP,
    }

    db.collection("releases").document(channel).set(release)
    print(f"[Upload] Firestore /releases/{channel} updated.")
    print(f"[Upload] Version: {version['version']} (build {version['build']})")
    print(f"[Upload] SHA256: {checksum[:16]}...")

    # 3. Bump version.json build number
    version["build"] = version.get("build", 1) + 1
    with open(os.path.join(PROJECT_ROOT, "version.json"), "w") as f:
        json.dump(version, f, indent=2)
    print(f"[Upload] Local version bumped to build {version['build']}.")
    print(f"\n[Done] Users will receive update on next app launch.")


def status():
    """Check current release status."""
    _init()
    db = admin_firestore.client()
    doc = db.collection("releases").document("stable").get()
    if doc.exists:
        data = doc.to_dict()
        print(f"Stable release: v{data['version']} (build {data['build']})")
        print(f"URL: {data['url']}")
        print(f"Size: {data.get('size_mb', '?')} MB")
        print(f"Published: {data.get('published_at', '?')}")
    else:
        print("No stable release published yet.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload GameLens release")
    parser.add_argument("exe_path", nargs="?", help="Path to EXE file")
    parser.add_argument("--notes", default="", help="Release notes")
    parser.add_argument("--channel", default="stable", help="Release channel")
    parser.add_argument("--status", action="store_true",
                        help="Show current release status")
    args = parser.parse_args()

    if args.status:
        status()
    elif args.exe_path:
        if not os.path.exists(args.exe_path):
            print(f"Error: {args.exe_path} not found.")
            sys.exit(1)
        upload(args.exe_path, notes=args.notes, channel=args.channel)
    else:
        parser.print_help()
        print("\nExamples:")
        print("  python scripts/upload_release.py dist/GameLens-0.2.0.exe")
        print("  python scripts/upload_release.py dist/GameLens-0.2.0.exe --notes 'Fixed RDR2 crashes'")
        print("  python scripts/upload_release.py --status")
