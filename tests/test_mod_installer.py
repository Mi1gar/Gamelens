# tests/test_mod_installer.py
"""Tests for ModInstaller — run with: python tests/test_mod_installer.py"""
import sys, os, json, tempfile, shutil, unittest, io
from unittest.mock import patch

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
        with open(zip_path, "rb") as fzip:
            mock_resp = io.BytesIO(fzip.read())
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

        with open(zip_path, "rb") as fzip:
            mock_resp = io.BytesIO(fzip.read())
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

        # Set up download mock
        zip_path = self._make_fake_zip({"data/game.str": "translated content"})
        with open(zip_path, "rb") as fzip:
            mock_resp = io.BytesIO(fzip.read())
        mock_urlopen.return_value.__enter__.return_value = mock_resp

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

    @patch("urllib.request.urlopen")
    @patch("core.mod_installer.ModInstaller.find_game_dir")
    def test_corrupt_zip(self, mock_find, mock_urlopen):
        """Returns False when downloaded file is not a valid zip."""
        mock_find.return_value = self.game_dir
        mock_resp = io.BytesIO(b"x" * 200)
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        result = mi.install(SAMPLE_MOD)

        self.assertFalse(result)

    def test_unsupported_install_type(self):
        """Returns False for unsupported install_type."""
        from core.mod_installer import ModInstaller
        mi = ModInstaller()
        mod = {"install_type": "symlink"}
        result = mi.install(mod)
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
