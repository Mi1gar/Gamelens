# tests/test_catalog_manager.py
"""Tests for CatalogManager — run with: python tests/test_catalog_manager.py"""
import sys, os, json, time, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

FAKE_CATALOG = {
    "version": "1.0",
    "updated": "2026-07-11",
    "games": {
        "rdr2": {
            "name": "Red Dead Redemption 2",
            "steam_appid": "1174180",
            "mods": [{"lang": "tr", "version": "1.0", "download_url": "https://example.com/rdr2.zip", "files": []}]
        }
    }
}


class TestCatalogManager(unittest.TestCase):

    def setUp(self):
        # Point cache to temp dir so tests don't touch real cache
        self.tmp = tempfile.mkdtemp()
        import core.catalog_manager as cm
        cm._CACHE_PATH = os.path.join(self.tmp, "catalog.json")
        cm._catalog_cache = None
        cm._cache_mtime = 0.0

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        import core.catalog_manager as cm
        cm._catalog_cache = None

    @patch("urllib.request.urlopen")
    def test_load_from_web_success(self, mock_urlopen):
        """When internet is available, load catalog from GitHub."""
        mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(FAKE_CATALOG).encode()
        from core.catalog_manager import CatalogManager
        cm = CatalogManager()
        result = cm.check("rdr2")
        self.assertIsNotNone(result)
        self.assertEqual(result["version"], "1.0")
        self.assertEqual(result["lang"], "tr")

    @patch("urllib.request.urlopen")
    def test_load_from_cache_when_offline(self, mock_urlopen):
        """When internet fails, use cached catalog from disk."""
        # Pre-populate cache
        from core.catalog_manager import _CACHE_PATH
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(FAKE_CATALOG, f)

        # Now simulate network failure
        mock_urlopen.side_effect = OSError("No internet")
        from core.catalog_manager import CatalogManager
        cm = CatalogManager()
        import core.catalog_manager as cm_mod
        cm_mod._cache_mtime = time.time()  # pretend cache is fresh
        result = cm.check("rdr2")
        self.assertIsNotNone(result)
        self.assertEqual(result["lang"], "tr")

    @patch("urllib.request.urlopen")
    def test_game_not_in_catalog(self, mock_urlopen):
        """Returns None for games not in catalog."""
        mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(FAKE_CATALOG).encode()
        from core.catalog_manager import CatalogManager
        cm = CatalogManager()
        result = cm.check("witcher3")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_lang_not_found(self, mock_urlopen):
        """Returns None when game exists but requested language doesn't."""
        mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(FAKE_CATALOG).encode()
        from core.catalog_manager import CatalogManager
        cm = CatalogManager()
        result = cm.check("rdr2", lang="fr")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_list_games(self, mock_urlopen):
        """list_games() returns all game entries with name and lang info."""
        mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps(FAKE_CATALOG).encode()
        from core.catalog_manager import CatalogManager
        cm = CatalogManager()
        games = cm.list_games()
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["game_id"], "rdr2")
        self.assertEqual(games[0]["lang"], "tr")


if __name__ == "__main__":
    unittest.main()
