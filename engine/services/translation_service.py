"""Unified translation service: Local DB → Memory → NLLB-200.

One-time cloud sync at game startup, then fully offline during gameplay.
"""
import os
import json
import time
import threading


_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "dataset_live", "growing_memory.json"
)
_SYNC_META_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "dataset_live", "sync_meta.json"
)


class TranslationService:
    """Three-tier translation with one-time cloud sync.

    Game startup:
      1. Check sync_meta.json — is local DB in sync with cloud?
      2. If not → pull ALL approved translations from CloudDB → merge into local DB
      3. Save sync timestamp — subsequent startups skip sync (instant)

    Gameplay (fully offline):
      0. In-memory cache (0ms)
      1. Local Growing DB (0ms) — now includes cloud-approved entries
      2. TranslationMemory fuzzy match (0ms)
      3. NLLB-200 GPU (35-60ms)

    New NLLB translations during gameplay:
      - Saved to local growing DB (instant)
      - Submitted to CloudDB raw for review (async, non-blocking)
    """

    def __init__(self, target_lang: str = "tr", game_slug: str = ""):
        self.target_lang = target_lang
        self.game_slug = game_slug
        self._cache: dict[str, str] = {}
        self._new_entries = 0
        self._synced_this_session = False

        # Load growing memory from disk
        self._growing: dict[str, str] = {}
        if os.path.exists(_DB_PATH):
            try:
                with open(_DB_PATH, "r", encoding="utf-8") as f:
                    self._growing = json.load(f)
                print(
                    f"[TranslationService] Loaded {len(self._growing)} "
                    f"local entries."
                )
            except Exception:
                self._growing = {}

        # Load sync metadata
        self._sync_meta: dict = {}
        if os.path.exists(_SYNC_META_PATH):
            try:
                with open(_SYNC_META_PATH, "r", encoding="utf-8") as f:
                    self._sync_meta = json.load(f)
            except Exception:
                self._sync_meta = {}

        # Cloud DB (optional — requires Firebase service account key)
        self._cloud = None
        self._cloud_enabled = False
        if game_slug:
            self._init_cloud(game_slug)

        # Lazy-load NLLB (don't load 600MB model until needed)
        self._nllb_loaded = False
        self._nllb_translate = None

    def _init_cloud(self, game_slug: str):
        """Initialize cloud connection for a game (no sync yet)."""
        try:
            from engine.core.cloud_translations import CloudTranslationDB

            self._cloud = CloudTranslationDB(game_slug)
            self._cloud_enabled = True
        except (FileNotFoundError, ImportError, ValueError) as e:
            print(
                f"[TranslationService] Cloud DB unavailable: {e}. "
                f"Running offline."
            )

    def set_game(self, game_slug: str):
        """Set active game and sync from cloud (once per session)."""
        if game_slug == self.game_slug and self._synced_this_session:
            return

        self.game_slug = game_slug
        self._cloud = None
        self._cloud_enabled = False
        self._synced_this_session = False

        self._init_cloud(game_slug)

        # One-time sync: if cloud has approved translations we don't have
        if self._cloud_enabled:
            self.sync_from_cloud()

    def sync_from_cloud(self) -> int:
        """Pull all approved translations from CloudDB into local DB.

        Only syncs if local DB is out of date (checked via sync_meta.json).
        This is a ONE-TIME operation per game version — subsequent calls
        check the sync timestamp and skip if already synced.

        Returns number of new entries added.
        """
        if not self._cloud_enabled or not self._cloud:
            return 0

        # Check if already synced
        game_meta = self._sync_meta.get(self.game_slug, {})
        last_sync = game_meta.get("last_sync", 0)
        cloud_stats = self._cloud.get_stats()
        cloud_approved = cloud_stats.get("approved_count", 0)

        if cloud_approved == 0:
            print(
                f"[TranslationService] Cloud has no approved entries for "
                f"'{self.game_slug}'. Nothing to sync."
            )
            self._synced_this_session = True
            return 0

        if last_sync > 0 and cloud_approved == game_meta.get("cloud_approved_count", 0):
            print(
                f"[TranslationService] Local DB already in sync with cloud "
                f"({cloud_approved} entries). Skipping sync."
            )
            self._synced_this_session = True
            return 0

        # Pull all approved from cloud
        print(
            f"[TranslationService] Syncing from cloud for '{self.game_slug}'..."
        )
        t0 = time.time()
        approved = self._cloud.get_all_approved()
        new_count = 0

        for entry in approved:
            key = entry["original"].strip().lower()
            if not key:
                continue
            # Overwrite: cloud-approved always beats NLLB
            if key not in self._growing or self._growing[key] != entry["translated"]:
                if key in self._growing:
                    # Overwriting a local NLLB entry with human-reviewed version
                    pass
                self._growing[key] = entry["translated"]
                new_count += 1

        # Save local DB + sync metadata
        self._save_db()
        self._sync_meta[self.game_slug] = {
            "last_sync": time.time(),
            "cloud_approved_count": cloud_approved,
            "synced_count": new_count,
        }
        self._save_sync_meta()

        elapsed = time.time() - t0
        print(
            f"[TranslationService] Sync complete: {new_count} new entries "
            f"in {elapsed:.1f}s ({len(approved)} total from cloud)."
        )
        self._synced_this_session = True
        return new_count

    def _save_sync_meta(self):
        """Persist sync metadata to disk."""
        try:
            os.makedirs(os.path.dirname(_SYNC_META_PATH), exist_ok=True)
            with open(_SYNC_META_PATH, "w", encoding="utf-8") as f:
                json.dump(self._sync_meta, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _ensure_nllb(self):
        if self._nllb_loaded:
            return
        from engine.core.nllb_translator import translate as nllb_translate

        self._nllb_translate = nllb_translate
        # Trigger lazy load + warm-up
        self._nllb_translate("Hello")
        self._nllb_loaded = True
        print("[TranslationService] NLLB-200 ready.")

    def translate(self, text: str) -> str:
        """Translate English text to Turkish.

        Returns empty string if text is too short or all tiers fail.
        """
        if not text or len(text.strip()) < 2:
            return ""

        clean = text.strip()

        # 0. In-memory cache
        if clean in self._cache:
            return self._cache[clean]

        # 1. Growing DB (0ms) — includes cloud-synced entries
        key = clean.lower()
        if key in self._growing:
            result = self._growing[key]
            self._cache[clean] = result
            return result

        # 2. Static TranslationMemory fuzzy match (0ms)
        try:
            from engine.core.manual_translations import TranslationMemory

            result = TranslationMemory.get_fuzzy(clean, cutoff=0.85)
            if result:
                self._cache[clean] = result
                return result
        except Exception:
            pass

        # 3. Text normalization (slang → formal English)
        try:
            from engine.core.text_cleaner import TextNormalizer

            clean = TextNormalizer.normalize(clean)
        except Exception:
            pass

        # 4. NLLB-200 GPU
        try:
            self._ensure_nllb()
            result = self._nllb_translate(clean)
            if result:
                self._cache[clean] = result
                # Only add quality subtitles to DB (prevent garbage accumulation)
                if self._is_quality(clean):
                    self._add_to_db(clean, result)
                    # Submit to CloudDB raw for review (async, non-blocking)
                    self._submit_to_cloud_raw(clean, result)
                return result
        except Exception as e:
            print(f"[TranslationService] NLLB error: {e}")

        return ""

    @staticmethod
    def _is_quality(text: str) -> bool:
        """Check if text looks like a real English subtitle (not OCR noise)."""
        t = text.strip()
        words = t.split()
        if len(words) < 2:
            return False
        alpha = sum(1 for c in t if c.isalpha())
        if alpha < len(t) * 0.45:
            return False
        if len(t) > 120:
            return False
        weird = sum(
            1 for c in t
            if not c.isalpha() and not c.isspace()
            and c not in "'.,!?-:;\""
        )
        if weird > len(t) * 0.03:
            return False
        if t[0].isdigit():
            return False
        # Don't store Turkish feedback loop text
        tr_chars = set("şŞğĞıİüÜöÖçÇ")
        if bool(set(t) & tr_chars):
            return False
        return True

    def _add_to_db(self, original: str, translated: str):
        key = original.strip().lower()
        if key and key not in self._growing and translated:
            self._growing[key] = translated
            self._new_entries += 1
            self._save_db()

    def _save_db(self):
        """Persist growing memory to disk."""
        try:
            os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
            with open(_DB_PATH, "w", encoding="utf-8") as f:
                json.dump(self._growing, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _submit_to_cloud_raw(self, original: str, translated: str):
        """Submit NLLB translation to CloudDB raw collection for review.

        Runs in a background thread to avoid blocking the pipeline.
        Fails silently — cloud submission is fire-and-forget.
        """
        if not self._cloud_enabled:
            return
        try:
            t = threading.Thread(
                target=self._cloud.submit_raw,
                args=(original, translated),
                kwargs={"source": "nllb-600m"},
                daemon=True,
            )
            t.start()
        except Exception:
            pass  # never block the pipeline for cloud writes

    def sync_approved_from_cloud(self) -> int:
        """Pull all approved translations from CloudDB into local DB.

        Returns count of new entries added.
        Call this at game startup or periodically.
        """
        if not self._cloud_enabled:
            return 0

        count = 0
        try:
            # We don't have a "get all approved" yet — add it to CloudTranslationDB
            pending = self._cloud.get_pending(limit=0)  # just check connection
            # For now, individual lookups during gameplay handle sync naturally.
            # Batch sync will be added in Phase 3 (review dashboard).
        except Exception as e:
            print(f"[TranslationService] Cloud sync error: {e}")
        return count

    @property
    def stats(self) -> dict:
        cloud_stats = {}
        if self._cloud_enabled:
            try:
                cloud_stats = self._cloud.get_stats()
            except Exception:
                cloud_stats = {"approved_count": "err", "raw_count": "err"}
        return {
            "growing_entries": len(self._growing),
            "new_this_session": self._new_entries,
            "cache_size": len(self._cache),
            "cloud_enabled": self._cloud_enabled,
            "cloud_approved": cloud_stats.get("approved_count", 0),
            "cloud_pending": cloud_stats.get("raw_count", 0),
        }
