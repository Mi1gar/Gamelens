"""Export pending translations from CloudDB raw as CSV for offline review.

Usage:
    python scripts/export_pending.py rdr2 -o rdr2_pending.csv
    python scripts/export_pending.py rdr2 --min-reports 5
    python scripts/export_pending.py rdr2 --limit 200

CSV format:
    hash, original, nllb_translated, report_count, your_translation

Edit 'your_translation' column, then use import_approved.py to upload.
  - Fill in your natural Turkish translation → will be approved
  - Type DELETE → will be deleted from raw (OCR noise / garbage)
  - Leave empty → skipped (not reviewed yet)
"""
import argparse
import csv
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import firebase_admin
from firebase_admin import credentials, firestore as admin_firestore


def _init():
    key_path = os.environ.get(
        "GAMELENS_FIREBASE_KEY",
        os.path.join(PROJECT_ROOT, "firebase", "gamelens-firebase-key.json"),
    )
    cred = credentials.Certificate(key_path)
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(cred)


def export_pending(game: str, output: str, min_reports: int = 1,
                   limit: int = 0):
    """Export pending translations to CSV."""
    _init()
    db = admin_firestore.client()
    raw_ref = db.collection("games").document(game).collection("raw")

    # Get stats first
    meta = db.collection("games").document(game).get().to_dict() or {}
    print(f"\n[{game}] Firestore status:")
    print(f"  Raw (pending): {meta.get('raw_count', '?')}")
    print(f"  Approved: {meta.get('approved_count', '?')}")

    # Query pending, sorted by report_count desc
    from google.cloud import firestore as gc_firestore
    query = (raw_ref
             .order_by("report_count", direction=gc_firestore.Query.DESCENDING))
    if limit > 0:
        query = query.limit(limit)

    docs = query.get()

    rows = []
    for doc in docs:
        data = doc.to_dict()
        rc = data.get("report_count", 0)
        if rc < min_reports:
            continue
        rows.append({
            "hash": doc.id,
            "original": data.get("original", ""),
            "nllb_translated": data.get("translated", ""),
            "report_count": rc,
            "your_translation": "",  # to be filled by reviewer
        })

    if not rows:
        print(f"  No pending entries with report_count >= {min_reports}.")
        return

    # Write CSV
    with open(output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "hash", "original", "nllb_translated", "report_count",
            "your_translation",
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Exported {len(rows)} entries to {output}")
    print(f"\nNext steps:")
    print(f"  1. Open {output} in Excel / VS Code")
    print(f"  2. Fill in 'your_translation' column with natural Turkish")
    print(f"  3. Type DELETE in 'your_translation' for noise/garbage")
    print(f"  4. Save CSV")
    print(f"  5. Run: python scripts/import_approved.py {output} --game {game}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export pending translations for offline review",
    )
    parser.add_argument("game", help="Game slug (rdr2, gta5, metro, etc.)")
    parser.add_argument("-o", "--output", default="",
                        help="Output CSV path (default: {game}_pending.csv)")
    parser.add_argument("--min-reports", type=int, default=1,
                        help="Minimum report_count (default: 1)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max entries (default: 0 = unlimited)")
    args = parser.parse_args()

    output = args.output or f"{args.game}_pending.csv"
    export_pending(args.game, output, args.min_reports, args.limit)
