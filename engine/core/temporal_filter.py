import time
import hashlib
from typing import Optional, Tuple

class TemporalFilter:
    """
    Distinguishes subtitles (transient, meaningful) from environment text
    (signs, HUD, wall text) by analyzing temporal stability.

    - Subtitle: appears suddenly, changes with dialogue, gone in 2-8 seconds
    - Sign/wall text: static, may scroll but same text persists for minutes
    - HUD element: rapidly changing numbers/indicators, caught by text validator anyway
    - OCR noise: appears for 1-2 frames then vanishes
    """

    def __init__(self):
        self._entries: dict = {}          # key → entry
        self._blacklist: set = set()       # permanently ignored hashes
        self._zone_blacklist: set = set()  # permanently ignored screen zones
        self._last_cleanup = time.time()
        self._cleanup_interval = 30.0      # clean every 30s
        self._max_entry_age = 15.0         # forget entries older than 15s

    def _make_key(self, text: str, zone_id: str = "primary") -> str:
        # Strip punctuation for fuzzy matching (catches OCR variants)
        import re
        clean = re.sub(r'[.,!?;:\'\"\s]+', '', text.lower())
        return hashlib.md5(f"{clean[:40]}|{zone_id}".encode()).hexdigest()

    def _make_zone_key(self, x: int, y: int, w: int, h: int) -> str:
        # Quantize position to 20px grid to group nearby text blocks
        qx, qy = x // 20, y // 20
        return f"{qy}_{qx}"

    def classify(self, text: str, confidence: float = 0.0,
                 zone_id: str = "primary", position: Optional[Tuple[int, int, int, int]] = None
                 ) -> str:
        """
        Returns one of: 'emit', 'pending', 'noise', 'sign', 'hud', 'blacklisted'
        """
        self._cleanup_if_needed()

        # 1. Check zone blacklist first (environment text region)
        if position:
            zone_key = self._make_zone_key(*position)
            if zone_key in self._zone_blacklist:
                return "blacklisted"

        # 2. Check text+zone hash blacklist
        key = self._make_key(text, zone_id)
        if key in self._blacklist:
            return "blacklisted"

        now = time.time()

        # 3. First time seeing this text — emit immediately
        # Other filters (region, TR chars, UI, vowel, quality) handle noise.
        if key not in self._entries:
            self._entries[key] = {
                "first_seen": now,
                "last_seen": now,
                "count": 1,
                "text": text,
                "confidence": confidence,
                "position": position,
                "emitted": True,
            }
            return "emit"

        # 4. Update existing entry — already emitted, track as "active"
        entry = self._entries[key]
        entry["last_seen"] = now
        entry["count"] += 1

        duration = now - entry["first_seen"]

        # Environment text: same text visible > 8 seconds → blacklist
        if duration > 8.0:
            self._blacklist.add(key)
            if position:
                self._zone_blacklist.add(self._make_zone_key(*position))
            self._entries.pop(key, None)
            return "sign"

        return "active"  # still on screen, already emitted

    def is_blacklisted(self, text: str, zone_id: str = "primary") -> bool:
        key = self._make_key(text, zone_id)
        return key in self._blacklist

    def get_blacklist_count(self) -> int:
        return len(self._blacklist)

    def reset(self):
        self._entries.clear()
        self._blacklist.clear()
        self._zone_blacklist.clear()

    def _cleanup_if_needed(self):
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now

        expired = [
            k for k, e in self._entries.items()
            if now - e["last_seen"] > self._max_entry_age
        ]
        for k in expired:
            self._entries.pop(k, None)
