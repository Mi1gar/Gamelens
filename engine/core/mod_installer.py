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

        # 2. Download + install files
        zip_path = None
        try:
            zip_path = self._download(mod["download_url"])
            if not zip_path:
                return False

            for file_entry in mod.get("files", []):
                dest = file_entry["to"].replace("{game_dir}", game_dir)
                self._install_file(zip_path, file_entry["from"], dest)
        except Exception as e:
            print(f"[ModInstaller] Install failed: {e}")
            return False
        finally:
            if zip_path is not None:
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
        tmp = None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GameLens/1.0"})
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
                shutil.copyfileobj(resp, tmp)
                tmp.close()
        except Exception as e:
            print(f"[ModInstaller] Download failed: {e}")
            if tmp is not None:
                try:
                    os.remove(tmp.name)
                except Exception:
                    pass
            return None

        if tmp is None or os.path.getsize(tmp.name) < 100:
            print("[ModInstaller] Downloaded file too small, likely invalid.")
            if tmp is not None:
                try:
                    os.remove(tmp.name)
                except Exception:
                    pass
            return None

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
