# Mod Catalog System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a curated mod catalog system that auto-installs existing subtitle mods for supported games, falling back to the OCR pipeline only when no mod is available.

**Architecture:** Two new modules — `CatalogManager` fetches a JSON catalog from GitHub with local caching; `ModInstaller` downloads mod zips, locates game install directories, and copies files with automatic backup. `DublajEngine.select_game()` checks the catalog before starting the OCR pipeline.

**Tech Stack:** Python 3.11 stdlib (`urllib`, `json`, `zipfile`, `shutil`, `os`), `winreg` for Steam detection, tkinter `filedialog` for manual directory selection.

## Global Constraints

- Python 3.11, no new pip dependencies
- Follow existing code patterns in `engine/core/` (module-level logging with `print()`, no classes unless stateful)
- Catalog URL: `https://raw.githubusercontent.com/gammasoftware/gamelens-catalog/main/catalog.json`
- Cache directory: `cache/` relative to project root
- Cache TTL: 86400 seconds (24 hours)
- First version: `install_type: "file_copy"` only
- Graceful fallback to OCR pipeline on ANY failure

---

### Task 1: CatalogManager — GitHub Katalog Çekme + Local Cache

**Files:**
- Create: `engine/core/catalog_manager.py`
- Create: `tests/test_catalog_manager.py`

**Interfaces:**
- Produces: `CatalogManager.check(game_id: str, lang: str = "tr") -> Optional[dict]`
- Produces: `CatalogManager.list_games() -> list[dict]`
- Produces: `CatalogManager.clear_cache() -> None`

- [ ] **Step 1: Create directory structure and test file**

```bash
mkdir -p D:\gammasoftware\GameLens\tests
```

- [ ] **Step 2: Write the test file**

```python
# tests/test_catalog_manager.py
"""Tests for CatalogManager — run with: python tests/test_catalog_manager.py"""
import sys, os, json, time, tempfile, unittest
from unittest.mock import patch, Mock

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
        cm._cache_mtime = time.time()  # pretend cache is fresh
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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd D:\gammasoftware\GameLens && python tests/test_catalog_manager.py
```

Expected: ImportError / ModuleNotFoundError — `catalog_manager.py` doesn't exist yet.

- [ ] **Step 4: Write CatalogManager implementation**

```python
# engine/core/catalog_manager.py
"""Catalog Manager — fetches mod catalog from GitHub with local caching."""
import json
import os
import time
import urllib.request
from typing import Optional

_CATALOG_URL = "https://raw.githubusercontent.com/gammasoftware/gamelens-catalog/main/catalog.json"
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd D:\gammasoftware\GameLens && python tests/test_catalog_manager.py
```

Expected: 5 tests pass, OK.

- [ ] **Step 6: Commit**

```bash
cd D:\gammasoftware\GameLens && git add engine/core/catalog_manager.py tests/test_catalog_manager.py && git commit -m "feat: add CatalogManager for GitHub-based mod catalog" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: ModInstaller — Mod İndirme + Oyun Klasörü Bulma + Dosya Kopyalama

**Files:**
- Create: `engine/core/mod_installer.py`
- Create: `tests/test_mod_installer.py`

**Interfaces:**
- Consumes: `CatalogManager.check()` return dict (the mod entry)
- Produces: `ModInstaller.install(mod: dict) -> bool`
- Produces: `ModInstaller.find_game_dir(mod: dict) -> Optional[str]`
- Produces: `ModInstaller.uninstall(mod: dict, game_dir: str) -> bool`

- [ ] **Step 1: Write the test file**

```python
# tests/test_mod_installer.py
"""Tests for ModInstaller — run with: python tests/test_mod_installer.py"""
import sys, os, json, tempfile, shutil, unittest
from unittest.mock import patch, Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

SAMPLE_MOD = {
    "lang": "tr",
    "version": "1.0",
    "install_type": "file_copy",
    "download_url": "https://example.com/mod.zip",
    "files": [
        {"from": "data/game.str", "to": "{game_dir}/data/game.str"}
    ],
    "download_size_mb": 3.2,
}

SAMPLE_MOD_MULTI_FILE = {
    "lang": "tr",
    "version": "1.0",
    "install_type": "file_copy",
    "download_url": "https://example.com/mod.zip",
    "files": [
        {"from": "game.str", "to": "{game_dir}/data/game.str"},
        {"from": "fonts/tr.otf", "to": "{game_dir}/fonts/tr.otf"},
    ],
    "download_size_mb": 5.0,
}


class TestModInstaller(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.game_dir = os.path.join(self.tmp, "game")
        os.makedirs(os.path.join(self.game_dir, "data"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_fake_zip(self, files: dict):
        """Create a zip file with given {filename: content} mapping."""
        import zipfile
        zip_path = os.path.join(self.tmp, "mod.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for fname, content in files.items():
                zf.writestr(fname, content)
        return zip_path

    @patch("urllib.request.urlopen")
    @patch("core.mod_installer.ModInstaller.find_game_dir")
    def test_install_single_file(self, mock_find, mock_urlopen):
        """Install a mod with one file — copies correctly, backs up original."""
        mock_find.return_value = self.game_dir

        # Create a fake "original" file that should get backed up
        original_path = os.path.join(self.game_dir, "data", "game.str")
        with open(original_path, "w", encoding="utf-8") as f:
            f.write("original content")

        # Create fake zip
        zip_path = self._make_fake_zip({"data/game.str": "translated content"})

        # Mock download to return our fake zip
        mock_resp = Mock()
        mock_resp.read.return_value = open(zip_path, "rb").read()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        result = mi.install(SAMPLE_MOD)

        self.assertTrue(result)

        # Check backup was created
        backup_path = original_path + ".backup"
        self.assertTrue(os.path.exists(backup_path))
        with open(backup_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "original content")

        # Check new content was written
        with open(original_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "translated content")

    @patch("urllib.request.urlopen")
    @patch("core.mod_installer.ModInstaller.find_game_dir")
    def test_install_multi_file(self, mock_find, mock_urlopen):
        """Install a mod with multiple files — all files are placed correctly."""
        mock_find.return_value = self.game_dir

        # Create fonts dir
        os.makedirs(os.path.join(self.game_dir, "fonts"), exist_ok=True)

        zip_path = self._make_fake_zip({
            "game.str": "new text",
            "fonts/tr.otf": "font data",
        })

        mock_resp = Mock()
        mock_resp.read.return_value = open(zip_path, "rb").read()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        result = mi.install(SAMPLE_MOD_MULTI_FILE)

        self.assertTrue(result)
        self.assertTrue(os.path.exists(os.path.join(self.game_dir, "data", "game.str")))
        self.assertTrue(os.path.exists(os.path.join(self.game_dir, "fonts", "tr.otf")))

    @patch("urllib.request.urlopen")
    @patch("core.mod_installer.ModInstaller.find_game_dir")
    def test_skip_if_backup_exists(self, mock_find, mock_urlopen):
        """If .backup already exists, skip the file (don't overwrite a user-modified file)."""
        mock_find.return_value = self.game_dir

        dest = os.path.join(self.game_dir, "data", "game.str")
        backup = dest + ".backup"
        with open(dest, "w") as f: f.write("already modded")
        with open(backup, "w") as f: f.write("original backup")

        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        result = mi.install(SAMPLE_MOD)

        # Should succeed but NOT overwrite
        self.assertTrue(result)
        with open(dest, "r") as f:
            self.assertEqual(f.read(), "already modded")

    @patch("core.mod_installer.ModInstaller.find_game_dir")
    def test_game_dir_not_found(self, mock_find):
        """Returns False when game directory cannot be located."""
        mock_find.return_value = None

        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        result = mi.install(SAMPLE_MOD)

        self.assertFalse(result)

    @patch("urllib.request.urlopen")
    @patch("core.mod_installer.ModInstaller.find_game_dir")
    def test_download_fails(self, mock_find, mock_urlopen):
        """Returns False when mod zip download fails."""
        mock_find.return_value = self.game_dir
        mock_urlopen.side_effect = OSError("Connection refused")

        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        result = mi.install(SAMPLE_MOD)

        self.assertFalse(result)

    def test_uninstall_restores_backup(self):
        """uninstall() restores .backup files and removes mod files."""
        # Setup: create a file + its backup
        dest = os.path.join(self.game_dir, "data", "game.str")
        backup = dest + ".backup"
        with open(dest, "w") as f: f.write("modded")
        with open(backup, "w") as f: f.write("original")

        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        result = mi.uninstall(SAMPLE_MOD, self.game_dir)

        self.assertTrue(result)
        with open(dest, "r") as f:
            self.assertEqual(f.read(), "original")
        self.assertFalse(os.path.exists(backup))

    def test_uninstall_no_backup(self):
        """uninstall() returns False when no .backup files exist."""
        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        result = mi.uninstall(SAMPLE_MOD, self.game_dir)

        self.assertFalse(result)


class TestGameDirDetection(unittest.TestCase):

    @patch("core.mod_installer._find_steam_dir")
    def test_steam_found(self, mock_steam):
        """When Steam registry has the game, use that path."""
        mock_steam.return_value = "C:/Steam/steamapps/common/RDR2"
        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        result = mi.find_game_dir({"steam_appid": "1174180"})
        self.assertEqual(result, "C:/Steam/steamapps/common/RDR2")

    @patch("core.mod_installer._find_steam_dir")
    @patch("core.mod_installer._find_epic_dir")
    def test_epic_fallback(self, mock_epic, mock_steam):
        """When Steam fails, try Epic."""
        mock_steam.return_value = None
        mock_epic.return_value = "C:/Epic Games/RDR2"
        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        result = mi.find_game_dir({"steam_appid": "1174180", "epic_appname": "Heather"})
        self.assertEqual(result, "C:/Epic Games/RDR2")

    @patch("core.mod_installer._find_steam_dir")
    @patch("core.mod_installer._find_epic_dir")
    def test_all_fail_returns_none(self, mock_epic, mock_steam):
        """When all platform lookups fail, return None."""
        mock_steam.return_value = None
        mock_epic.return_value = None
        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        result = mi.find_game_dir({"steam_appid": "1174180"})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:\gammasoftware\GameLens && python tests/test_mod_installer.py
```

Expected: ImportError — `mod_installer.py` doesn't exist yet.

- [ ] **Step 3: Write ModInstaller implementation**

```python
# engine/core/mod_installer.py
"""Mod Installer — downloads and installs subtitle mod files with backup."""
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from typing import Optional


def _find_steam_dir(appid: str) -> Optional[str]:
    """Find a Steam game's install directory via Windows registry."""
    import winreg
    key_paths = [
        f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Steam App {appid}",
        f"SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Steam App {appid}",
    ]
    for kp in key_paths:
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, kp) as key:
                    value, _ = winreg.QueryValueEx(key, "InstallLocation")
                    if os.path.isdir(value):
                        return value
            except OSError:
                continue
    return None


def _find_epic_dir(appname: str) -> Optional[str]:
    """Find an Epic Games install directory from LauncherInstalled.dat."""
    epic_data = os.path.join(
        os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
        "Epic", "UnrealEngineLauncher", "LauncherInstalled.dat",
    )
    if not os.path.exists(epic_data):
        return None
    try:
        with open(epic_data, "r", encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("InstallationList", []):
            if entry.get("AppName") == appname:
                loc = entry.get("InstallLocation", "")
                if os.path.isdir(loc):
                    return loc
    except Exception:
        pass
    return None


def _search_common_dirs(search_dirs: list[str]) -> Optional[str]:
    """Search common install locations for a game folder name."""
    roots = [
        os.path.expandvars(r"C:\Program Files (x86)\Steam\steamapps\common"),
        os.path.expandvars(r"C:\Program Files\Steam\steamapps\common"),
        r"D:\Steam\steamapps\common",
        r"E:\Steam\steamapps\common",
        os.path.expandvars(r"C:\Program Files\Epic Games"),
        os.path.expandvars(r"C:\Program Files"),
        os.path.expandvars(r"C:\Program Files (x86)"),
        r"D:\Games",
        r"E:\Games",
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for entry in os.listdir(root):
            entry_lower = entry.lower().replace(" ", "")
            for sd in search_dirs:
                if sd.lower().replace(" ", "") in entry_lower:
                    full = os.path.join(root, entry)
                    if os.path.isdir(full):
                        return full
    return None


class ModInstaller:
    """Handles downloading and installing subtitle mod packages."""

    def find_game_dir(self, mod: dict) -> Optional[str]:
        """Try to locate the game's install directory.

        Checks in order: Steam registry → Epic Games → common directories.
        Returns None if not found.
        """
        # 1. Steam
        if "steam_appid" in mod:
            result = _find_steam_dir(mod["steam_appid"])
            if result:
                print(f"[ModInstaller] Found via Steam: {result}")
                return result

        # 2. Epic
        if "epic_appname" in mod:
            result = _find_epic_dir(mod["epic_appname"])
            if result:
                print(f"[ModInstaller] Found via Epic: {result}")
                return result

        # 3. Search common dirs
        if "search_dirs" in mod:
            result = _search_common_dirs(mod["search_dirs"])
            if result:
                print(f"[ModInstaller] Found via search: {result}")
                return result

        return None

    def install(self, mod: dict) -> bool:
        """Download and install a subtitle mod.

        Args:
            mod: Mod entry dict from catalog, with keys:
                 download_url, files, install_type.

        Returns:
            True if installation succeeded, False otherwise.
        """
        if mod.get("install_type") != "file_copy":
            print(f"[ModInstaller] Unsupported install_type: {mod.get('install_type')}")
            return False

        # 1. Find game directory
        game_dir = self.find_game_dir(mod)
        if not game_dir:
            print("[ModInstaller] Game directory not found. Skipping.")
            return False

        # 2. Download zip
        zip_path = self._download(mod["download_url"])
        if not zip_path:
            return False

        # 3. Install files
        try:
            for file_entry in mod.get("files", []):
                dest = file_entry["to"].replace("{game_dir}", game_dir)
                self._install_file(zip_path, file_entry["from"], dest)
        finally:
            # 4. Cleanup temp zip
            try:
                os.remove(zip_path)
            except Exception:
                pass

        print(f"[ModInstaller] Successfully installed mod v{mod.get('version', '?')} to {game_dir}")
        return True

    def uninstall(self, mod: dict, game_dir: str) -> bool:
        """Restore original files from .backup copies.

        Args:
            mod: Mod entry dict from catalog.
            game_dir: Path to the game's install directory.

        Returns:
            True if at least one file was restored.
        """
        restored = 0
        for file_entry in mod.get("files", []):
            dest = file_entry["to"].replace("{game_dir}", game_dir)
            backup = dest + ".backup"
            if os.path.exists(backup):
                try:
                    shutil.copy2(backup, dest)
                    os.remove(backup)
                    restored += 1
                except Exception as e:
                    print(f"[ModInstaller] Uninstall error for {dest}: {e}")

        if restored > 0:
            print(f"[ModInstaller] Restored {restored} file(s) from backup.")
            return True

        print("[ModInstaller] No backup files found to restore.")
        return False

    @staticmethod
    def _download(url: str) -> Optional[str]:
        """Download mod zip to a temp file. Returns path or None."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GameLens/1.0"})
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = resp.read()
        except Exception as e:
            print(f"[ModInstaller] Download failed: {e}")
            return None

        if not data or len(data) < 100:
            print("[ModInstaller] Downloaded file too small, likely invalid.")
            return None

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        tmp.write(data)
        tmp.close()
        return tmp.name

    @staticmethod
    def _install_file(zip_path: str, from_path: str, dest: str):
        """Extract a single file from zip to destination with backup."""
        # Bail if already modded (backup exists — user may have edited)
        backup = dest + ".backup"
        if os.path.exists(backup):
            print(f"[ModInstaller] Backup exists, skipping: {dest}")
            return

        # Backup original if present
        if os.path.exists(dest):
            shutil.copy2(dest, backup)
            print(f"[ModInstaller] Backed up: {dest} -> {backup}")

        # Create destination directory if needed
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        # Extract from zip
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Find the file in the zip (may have leading directory)
            for name in zf.namelist():
                if name == from_path or name.endswith("/" + from_path) or name.endswith("\\" + from_path):
                    with zf.open(name) as src:
                        with open(dest, "wb") as dst:
                            dst.write(src.read())
                    print(f"[ModInstaller] Installed: {from_path} -> {dest}")
                    return

        print(f"[ModInstaller] Warning: '{from_path}' not found in zip.")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:\gammasoftware\GameLens && python tests/test_mod_installer.py
```

Expected: 8 tests pass, OK.

- [ ] **Step 5: Commit**

```bash
cd D:\gammasoftware\GameLens && git add engine/core/mod_installer.py tests/test_mod_installer.py && git commit -m "feat: add ModInstaller for automated subtitle mod deployment" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: DublajEngine Entegrasyonu — select_game()'de Catalog Kontrolü

**Files:**
- Modify: `engine/core/engine.py:36-51`

**Interfaces:**
- Consumes: `CatalogManager.check(game_id, lang)` from Task 1
- Consumes: `ModInstaller.install(mod)` from Task 2

- [ ] **Step 1: Read the current select_game method to confirm exact code**

File: `engine/core/engine.py`, lines 36-51.

- [ ] **Step 2: Modify select_game() to add catalog check**

Replace the `select_game` method in `engine/core/engine.py`:

```python
# engine/core/engine.py — lines 36-51, replace with:

    def select_game(self, game_id: str):
        print(f"[Engine] Selecting game: {game_id}")
        self.active_game_id = game_id

        # ── Catalog check: try mod install first ──
        from .catalog_manager import CatalogManager
        catalog = CatalogManager()
        mod = catalog.check(game_id, lang="tr")

        if mod:
            print(f"[Engine] Catalog match: {mod.get('version')}. Installing mod...")
            from .mod_installer import ModInstaller
            installer = ModInstaller()
            success = installer.install(mod)
            if success:
                print("[Engine] Mod installed successfully. OCR pipeline not needed.")
                if self.on_status_change_callback:
                    self.on_status_change_callback("mod_installed")
                return
            else:
                print("[Engine] Mod install failed. Falling back to OCR pipeline.")
        # ── End catalog check ──

        # Original flow: load adapter and prepare pipeline
        from .registry import GameRegistry
        adapter = GameRegistry.get_adapter(game_id)

        if adapter:
            print(f"[Engine] Loading Adapter: {adapter.DISPLAY_NAME}")
            self.hook_manager.set_active_adapter(adapter)
        else:
            print(f"[Engine] ERROR: Could not load adapter for {game_id}")
```

- [ ] **Step 3: Verify the file is syntactically correct**

```bash
cd D:\gammasoftware\GameLens && python -c "import engine.core.engine; print('OK')"
```

Expected: `OK` (NLLB model yükleme logları gelebilir ama hata olmamalı).

- [ ] **Step 4: Manual integration test — catalog check with no internet**

```bash
cd D:\gammasoftware\GameLens && python -c "
from engine.core.catalog_manager import CatalogManager
cm = CatalogManager()
# With no internet and no cache, should return None gracefully
result = cm.check('rdr2')
print('Result:', result)
# Should print None — OCR fallback path works
"
```

Expected: `Result: None`

- [ ] **Step 5: Commit**

```bash
cd D:\gammasoftware\GameLens && git add engine/core/engine.py && git commit -m "feat: integrate catalog check into Engine.select_game()" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: GitHub Katalog Reposu Oluşturma (Manuel — Kod Değil)

Bu task programatik değil, manuel. GitHub'da `gamelens-catalog` reposu oluşturulmalı.

**Files (GitHub reposunda):**
- `catalog.json` (boş başlangıç kataloğu)
- `README.md` (mod ekleme talimatları)
- `mods/` dizini (boş)

- [ ] **Step 1: Create initial catalog.json**

```json
{
  "version": "1.0",
  "updated": "2026-07-11",
  "games": {}
}
```

- [ ] **Step 2: Create README.md**

```markdown
# GameLens Catalog

Curated subtitle mod index for [Game Lens](https://github.com/gammasoftware/GameLens).

## Adding a mod

1. Fork this repo
2. Add the mod `.zip` to `mods/`
3. Add the game entry to `catalog.json` (see format below)
4. Open a PR

### Catalog entry format

```json
{
  "game_id": {
    "name": "Game Name",
    "steam_appid": "123456",
    "epic_appname": "AppName",
    "search_dirs": ["Game Folder Name"],
    "mods": [
      {
        "lang": "tr",
        "version": "1.0",
        "install_type": "file_copy",
        "files": [
          {
            "from": "path/in/zip/file.str",
            "to": "{game_dir}/relative/path/file.str"
          }
        ],
        "download_url": "https://raw.githubusercontent.com/gammasoftware/gamelens-catalog/main/mods/game_tr_v1.0.zip",
        "download_size_mb": 3.2,
        "notes": "Installation notes."
      }
    ]
  }
}
```
```

- [ ] **Step 3: Push to GitHub and verify raw URL works**

Repo: `https://github.com/gammasoftware/gamelens-catalog`
Raw catalog: `https://raw.githubusercontent.com/gammasoftware/gamelens-catalog/main/catalog.json`

- [ ] **Step 4: Verify end-to-end from Game Lens side**

```bash
cd D:\gammasoftware\GameLens && python -c "
from engine.core.catalog_manager import CatalogManager
cm = CatalogManager()
result = cm.check('rdr2')
print('Catalog check:', result)
games = cm.list_games()
print('Available games:', games)
"
```

Expected: `Catalog check: None` (RDR2 henüz eklenmedi), `Available games: []` — sistem çalışıyor, sadece katalog boş.

---

### Görev Özeti

| # | Task | Yeni Dosyalar | Değişen Dosyalar |
|---|------|--------------|-----------------|
| 1 | CatalogManager | `engine/core/catalog_manager.py`, `tests/test_catalog_manager.py` | — |
| 2 | ModInstaller | `engine/core/mod_installer.py`, `tests/test_mod_installer.py` | — |
| 3 | Engine entegrasyonu | — | `engine/core/engine.py:36-51` |
| 4 | GitHub repo | Manuel — `gamelens-catalog` reposu | — |
