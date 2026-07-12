"""Import reviewed CSV back to Firestore — bulk approve + delete.

Usage:
    python scripts/import_approved.py rdr2_pending.csv --game rdr2
    python scripts/import_approved.py rdr2_pending.csv --game rdr2 --reviewer Mi1gar

CSV format (from export_pending.py):
    hash, original, nllb_translated, report_count, your_translation

Actions based on 'your_translation' column:
  - Has text  → approve: move from raw → approved with this translation
  - "DELETE"  → delete: remove from raw (OCR noise / garbage / credit)
  - Empty     → skip: not reviewed yet
"""
import argparse
import csv
import os
import sys
import time

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


def import_approved(csv_path: str, game: str, reviewer: str = "unknown",
                    dry_run: bool = False):
    """Import reviewed CSV, approve/delete entries in Firestore."""
    _init()
    db = admin_firestore.client()
    from google.cloud import firestore as gc_firestore

    approved_ref = db.collection("games").document(game).collection("approved")
    raw_ref = db.collection("games").document(game).collection("raw")
    meta_ref = db.collection("games").document(game)

    # Read CSV
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    to_approve = []
    to_delete = []
    skipped = 0

    for row in rows:
        translation = row.get("your_translation", "").strip()
        if translation.upper() == "DELETE":
            to_delete.append(row)
        elif translation:
            to_approve.append(row)
        else:
            skipped += 1

    print(f"\n[{game}] Importing from {csv_path}:")
    print(f"  Approve: {len(to_approve)}")
    print(f"  Delete:  {len(to_delete)}")
    print(f"  Skip:    {skipped}")
    print(f"  Total:   {len(rows)}")

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        if to_approve:
            print("\nWould approve:")
            for r in to_approve[:5]:
                print(f'  "{r["original"][:60]}" -> "{r["your_translation"][:60]}"')
            if len(to_approve) > 5:
                print(f"  ... and {len(to_approve) - 5} more")
        return

    if not to_approve and not to_delete:
        print("  Nothing to do.")
        return

    # Confirm
    print(f"\nPress Enter to continue or Ctrl+C to cancel...")
    try:
        input()
    except KeyboardInterrupt:
        print("Cancelled.")
        return

    # Process approve
    approved_count = 0
    for chunk_start in range(0, len(to_approve), 500):
        chunk = to_approve[chunk_start:chunk_start + 500]
        batch = db.batch()
        for row in chunk:
            h = row["hash"]
            # Write to approved
            batch.set(approved_ref.document(h), {
                "original": row["original"].strip(),
                "translated": row["your_translation"].strip(),
                "reviewed_by": reviewer,
                "quality": "natural",
                "approved_at": gc_firestore.SERVER_TIMESTAMP,
            })
            # Delete from raw
            batch.delete(raw_ref.document(h))
        batch.commit()
        approved_count += len(chunk)
        print(f"  Approved: {approved_count}/{len(to_approve)}")

    # Process delete
    deleted_count = 0
    for chunk_start in range(0, len(to_delete), 500):
        chunk = to_delete[chunk_start:chunk_start + 500]
        batch = db.batch()
        for row in chunk:
            batch.delete(raw_ref.document(row["hash"]))
        batch.commit()
        deleted_count += len(chunk)
        print(f"  Deleted: {deleted_count}/{len(to_delete)}")

    # Update meta
    meta_ref.update({
        "approved_count": gc_firestore.Increment(approved_count),
        "raw_count": gc_firestore.Increment(-(approved_count + deleted_count)),
        "last_updated": gc_firestore.SERVER_TIMESTAMP,
    })

    print(f"\n[Done] {approved_count} approved, {deleted_count} deleted, "
          f"{skipped} skipped.")
    print(f"Users will receive new translations on next app launch.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import reviewed CSV to Firestore",
    )
    parser.add_argument("csv", help="CSV file to import")
    parser.add_argument("--game", required=True, help="Game slug")
    parser.add_argument("--reviewer", default="unknown",
                        help="Reviewer name (default: unknown)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only, no changes")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"Error: {args.csv} not found.")
        sys.exit(1)

    import_approved(args.csv, args.game, args.reviewer, args.dry_run)
