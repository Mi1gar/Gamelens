# engine/core/catalog_manager.py
"""Catalog Manager — fetches mod catalog from GitHub with local caching."""
import json
import os
import time
import urllib.request
from typing import Optional

_CATALOG_URL = "https://raw.githubusercontent.com/Mi1gar/gamelens-catalog/main/catalog.json"
_CACHE_PATH = "cache/catalog.json"
_CACHE_TTL = 86400  # 24 hours

_catalog_cache: Optional[dict] = None
_cache_mtime: float = 0.0


class CatalogManager:
    """Queries the curated mod catalog for available subtitle translations."""

    def check(self, game_id: str, lang: str = "tr") -> Optional[dict]:
        """Return mod entry dict if catalog has a mod for (game_id, lang), else None.

        Returns dict with keys: lang, version, install_type, files, download_url, download_size_mb.
        """
        catalog = self._load()
        if not catalog:
            return None

        game = catalog.get("games", {}).get(game_id)
        if not game:
            return None

        for mod in game.get("mods", []):
            if mod.get("lang") == lang:
                return mod

        return None

    def list_games(self) -> list[dict]:
        """Return all available games with their mod info.

        Each entry: {"game_id": str, "name": str, "lang": str, "version": str}.
        """
        catalog = self._load()
        if not catalog:
            return []

        results = []
        for game_id, game in catalog.get("games", {}).items():
            for mod in game.get("mods", []):
                results.append({
                    "game_id": game_id,
                    "name": game.get("name", game_id),
                    "lang": mod.get("lang", "?"),
                    "version": mod.get("version", "?"),
                })
        return results

    def _load(self) -> Optional[dict]:
        """Load catalog: web first, fall back to cache. Returns None if nothing available."""
        global _catalog_cache, _cache_mtime

        # 1. Try downloading from GitHub
        try:
            raw = self._fetch_url(_CATALOG_URL)
            catalog = json.loads(raw)
            print(f"[CatalogManager] Loaded from web. "
                  f"Version: {catalog.get('version')}, "
                  f"Games: {len(catalog.get('games', {}))}")
            self._save_cache(raw)
            _catalog_cache = catalog
            _cache_mtime = time.time()
            return catalog
        except Exception as e:
            print(f"[CatalogManager] Web fetch failed: {e}")

        # 2. Try local cache
        if _catalog_cache is not None:
            if time.time() - _cache_mtime < _CACHE_TTL:
                print("[CatalogManager] Using in-memory cache.")
                return _catalog_cache
            elif time.time() - _cache_mtime < _CACHE_TTL * 2:
                # Within 2x TTL, use stale cache rather than nothing
                print("[CatalogManager] Cache TTL expired, using stale cache (web unavailable).")
                return _catalog_cache

        # 3. Try disk cache
        try:
            if os.path.exists(_CACHE_PATH):
                mtime = os.path.getmtime(_CACHE_PATH)
                if time.time() - mtime < _CACHE_TTL * 2:
                    with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                        _catalog_cache = json.load(f)
                    _cache_mtime = mtime
                    print("[CatalogManager] Loaded from disk cache.")
                    return _catalog_cache
        except Exception as e:
            print(f"[CatalogManager] Cache read failed: {e}")

        print("[CatalogManager] No catalog available (offline, no cache).")
        return None

    @staticmethod
    def _fetch_url(url: str, timeout: float = 10.0) -> str:
        """Fetch URL contents as string."""
        req = urllib.request.Request(url, headers={"User-Agent": "GameLens/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    @staticmethod
    def _save_cache(raw_json: str):
        """Persist raw catalog JSON to disk cache."""
        try:
            os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
            with open(_CACHE_PATH, "w", encoding="utf-8") as f:
                f.write(raw_json)
        except Exception as e:
            print(f"[CatalogManager] Cache write failed: {e}")

    @staticmethod
    def clear_cache():
        """Clear all caches. Useful for testing or forced refresh."""
        global _catalog_cache, _cache_mtime
        _catalog_cache = None
        _cache_mtime = 0.0
        if os.path.exists(_CACHE_PATH):
            try:
                os.remove(_CACHE_PATH)
            except Exception:
                pass
