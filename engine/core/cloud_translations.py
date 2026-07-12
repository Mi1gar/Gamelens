"""Firebase Firestore cloud translation database.

Two-tier architecture:
  raw/      — Players WRITE (NLLB translations), reviewers READ+DELETE
  approved/ — Players READ (human-reviewed), reviewers WRITE

Usage:
    cloud = CloudTranslationDB("rdr2")
    result = cloud.lookup("you need horses?")
    if result is None:
        # ... run NLLB ...
        cloud.submit_raw("you need horses?", "Atlara ihtiyacin var mi?")

Review workflow:
    cloud.get_pending(limit=50, min_reports=5)  # top pending items
    cloud.approve(text_hash, original, translated)  # promote to approved
    cloud.reject(text_hash)  # delete from raw (OCR noise)
"""
import hashlib
import json
import os
import time
from typing import Optional

import firebase_admin
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore as admin_firestore
from google.cloud import firestore  # for Increment, SERVER_TIMESTAMP, Query

# ── Firebase initialization ──

_firebase_app = None
_firestore_client = None


def _init_firebase():
    """Lazy-init Firebase Admin SDK. Call once on first use."""
    global _firebase_app, _firestore_client
    if _firestore_client is not None:
        return

    # Try service account key from environment, then from file
    key_path = os.environ.get(
        "GAMELENS_FIREBASE_KEY",
        os.path.join(os.path.dirname(__file__), "..", "..",
                     "firebase", "gamelens-firebase-key.json"),
    )

    if not os.path.exists(key_path):
        raise FileNotFoundError(
            f"Firebase key not found at {key_path}. "
            "Set GAMELENS_FIREBASE_KEY env var or place the key file in firebase/."
        )

    cred = credentials.Certificate(key_path)
    _firebase_app = firebase_admin.initialize_app(cred)
    _firestore_client = admin_firestore.client()
    print("[CloudDB] Firebase initialized.")


# ── Helpers ──

def _hash_text(text: str) -> str:
    """Stable hash for subtitle text.

    NOT normalized — preserves exact string for hash.
    "You need horses?" and "you need horses?" produce different hashes.
    This is intentional: OCR variations are visible in review.
    """
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def _normalize(text: str) -> str:
    """Normalize for lookup matching."""
    return text.strip().lower()


# ── Main class ──

class CloudTranslationDB:
    """Firestore-backed translation database for one game."""

    def __init__(self, game_slug: str):
        _init_firebase()
        self.game = game_slug
        self.db = _firestore_client
        self._raw_ref = self.db.collection("games").document(game_slug).collection("raw")
        self._approved_ref = self.db.collection("games").document(game_slug).collection("approved")
        self._meta_ref = self.db.collection("games").document(game_slug)
        self._local_cache: dict[str, str] = {}  # in-memory hot cache

    # ── Read path (player-facing) ──

    def lookup(self, text: str) -> Optional[str]:
        """Look up approved translation. Returns translated text or None.

        Checks in-memory cache first, then Firestore approved collection.
        Does NOT query raw — players never see unapproved translations.
        """
        key = _normalize(text)
        if key in self._local_cache:
            return self._local_cache[key]

        try:
            h = _hash_text(text)
            doc = self._approved_ref.document(h).get()
            if doc.exists:
                data = doc.to_dict()
                translated = data.get("translated", "")
                self._local_cache[key] = translated
                return translated
        except Exception as e:
            print(f"[CloudDB] Lookup error: {e}")

        return None

    def lookup_batch(self, texts: list[str]) -> dict[str, Optional[str]]:
        """Batch lookup for multiple texts. More efficient than N single calls.

        Returns dict mapping original text → translated text (or None).
        """
        if not texts:
            return {}

        results = {}
        needs_fetch = []

        for t in texts:
            key = _normalize(t)
            if key in self._local_cache:
                results[t] = self._local_cache[key]
            else:
                needs_fetch.append((t, _hash_text(t)))

        if needs_fetch:
            try:
                for text, h in needs_fetch:
                    doc = self._approved_ref.document(h).get()
                    if doc.exists:
                        translated = doc.to_dict().get("translated", "")
                        results[text] = translated
                        self._local_cache[_normalize(text)] = translated
                    else:
                        results[text] = None
            except Exception as e:
                print(f"[CloudDB] Batch lookup error: {e}")
                for text, _ in needs_fetch:
                    if text not in results:
                        results[text] = None

        return results

    # ── Write path (player-facing) ──

    def submit_raw(self, original: str, translated: str,
                   ocr_confidence: float = 0.0,
                   source: str = "nllb-600m") -> bool:
        """Submit NLLB translation to raw collection for review.

        Uses Firestore merge + increment to track report_count.
        Safe to call repeatedly — same text just increments counter.
        """
        try:
            h = _hash_text(original)
            ref = self._raw_ref.document(h)

            # Ensure document exists (no-op if it already does)
            ref.set({
                "original": original.strip(),
                "translated": translated.strip(),
                "source": source,
                "ocr_confidence": ocr_confidence,
                "last_seen": firestore.SERVER_TIMESTAMP,
            }, merge=True)

            # Increment counters atomically (must be separate update call)
            ref.update({
                "report_count": firestore.Increment(1),
                "last_seen": firestore.SERVER_TIMESTAMP,
            })

            # Update game meta counter
            self._meta_ref.set({
                "game_name": self.game,
            }, merge=True)
            self._meta_ref.update({
                "raw_count": firestore.Increment(1),
                "last_updated": firestore.SERVER_TIMESTAMP,
            })

            return True
        except Exception as e:
            print(f"[CloudDB] Submit error: {e}")
            return False

    def submit_raw_batch(self, entries: list[dict]) -> int:
        """Batch submit multiple translations. Returns count of successful writes.

        entries: [{"original": str, "translated": str, "ocr_confidence": float}, ...]
        """
        success = 0
        for chunk_start in range(0, len(entries), 500):
            try:
                batch = self.db.batch()
                for entry in entries[chunk_start:chunk_start + 500]:
                    h = _hash_text(entry["original"])
                    batch.set(self._raw_ref.document(h), {
                        "original": entry["original"].strip(),
                        "translated": entry["translated"].strip(),
                        "source": entry.get("source", "nllb-600m"),
                        "ocr_confidence": entry.get("ocr_confidence", 0.0),
                        "report_count": firestore.Increment(1),
                        "last_seen": firestore.SERVER_TIMESTAMP,
                    }, merge=True)
                batch.commit()
                success += min(500, len(entries) - chunk_start)
            except Exception as e:
                print(f"[CloudDB] Batch submit error: {e}")
        return success

    # ── Review path (reviewer-facing) ──

    def get_pending(self, limit: int = 50, min_reports: int = 1) -> list[dict]:
        """Get pending translations from raw, sorted by report_count (descending).

        Used by the review dashboard to prioritize popular untranslated text.
        """
        try:
            query = (self._raw_ref
                     .order_by("report_count", direction=firestore.Query.DESCENDING)
                     .limit(limit))
            docs = query.get()

            results = []
            for doc in docs:
                data = doc.to_dict()
                if data.get("report_count", 0) >= min_reports:
                    results.append({
                        "hash": doc.id,
                        "original": data.get("original", ""),
                        "translated": data.get("translated", ""),
                        "source": data.get("source", ""),
                        "report_count": data.get("report_count", 0),
                        "ocr_confidence": data.get("ocr_confidence", 0.0),
                    })
            return results
        except Exception as e:
            print(f"[CloudDB] Get pending error: {e}")
            return []

    def get_stats(self) -> dict:
        """Get game translation stats for the review dashboard."""
        try:
            meta = self._meta_ref.get().to_dict() or {}
            return {
                "raw_count": meta.get("raw_count", 0),
                "approved_count": meta.get("approved_count", 0),
                "last_updated": meta.get("last_updated", None),
            }
        except Exception:
            return {"raw_count": 0, "approved_count": 0, "last_updated": None}

    def get_all_approved(self) -> list[dict]:
        """Get ALL approved translations for this game.

        Used for one-time sync to local DB at game startup.
        Returns list of {"original": str, "translated": str} dicts.
        """
        try:
            docs = self._approved_ref.get()
            results = []
            for doc in docs:
                data = doc.to_dict()
                results.append({
                    "original": data.get("original", ""),
                    "translated": data.get("translated", ""),
                })
            return results
        except Exception as e:
            print(f"[CloudDB] get_all_approved error: {e}")
            return []

    def approve(self, text_hash: str, original: str, translated: str,
                reviewer: str = "unknown") -> bool:
        """Move from raw to approved. Writes approved, deletes raw."""
        try:
            # Write to approved
            self._approved_ref.document(text_hash).set({
                "original": original.strip(),
                "translated": translated.strip(),
                "reviewed_by": reviewer,
                "quality": "natural",
                "approved_at": firestore.SERVER_TIMESTAMP,
            })

            # Delete from raw
            self._raw_ref.document(text_hash).delete()

            # Update meta
            self._meta_ref.update({
                "approved_count": firestore.Increment(1),
                "raw_count": firestore.Increment(-1),
            })

            # Warm local cache
            self._local_cache[_normalize(original)] = translated
            return True
        except Exception as e:
            print(f"[CloudDB] Approve error: {e}")
            return False

    def approve_batch(self, entries: list[dict], reviewer: str = "unknown") -> int:
        """Batch approve multiple entries. Returns success count."""
        success = 0
        for chunk_start in range(0, len(entries), 500):
            try:
                batch = self.db.batch()
                for entry in entries[chunk_start:chunk_start + 500]:
                    h = entry["hash"]
                    batch.set(self._approved_ref.document(h), {
                        "original": entry["original"].strip(),
                        "translated": entry["translated"].strip(),
                        "reviewed_by": reviewer,
                        "quality": "natural",
                        "approved_at": firestore.SERVER_TIMESTAMP,
                    })
                    batch.delete(self._raw_ref.document(h))
                batch.commit()
                success += min(500, len(entries) - chunk_start)
            except Exception as e:
                print(f"[CloudDB] Batch approve error: {e}")
        return success

    def reject(self, text_hash: str) -> bool:
        """Delete from raw — OCR noise, credit text, or garbage."""
        try:
            self._raw_ref.document(text_hash).delete()
            self._meta_ref.update({
                "raw_count": firestore.Increment(-1),
            })
            return True
        except Exception as e:
            print(f"[CloudDB] Reject error: {e}")
            return False

    # ── Firebase credential distribution ──

    @staticmethod
    def auth_token_for_user() -> Optional[str]:
        """Generate a Firebase Auth custom token for a player.

        Used when distributing the app: players get an anonymous token
        that allows raw writes but NOT approved writes (enforced by rules).

        For now, returns None — players use unauthenticated writes to raw.
        Auth will be added in Phase 2 when we scale.
        """
        return None  # Anonymous access for Phase 1
