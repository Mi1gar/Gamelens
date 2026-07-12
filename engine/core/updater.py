"""Self-update system: check Firestore for new versions, download + install.

Flow:
  1. App startup → check_update()
  2. If cloud version > local → download new EXE → spawn updater.bat → exit
  3. updater.bat replaces old EXE → launches new version

Firestore schema:
  /releases/stable/
    version: "0.2.0"
    build: 5
    url: "https://storage.googleapis.com/gamelens-4fd98.firebasestorage.app/releases/GameLens-0.2.0.exe"
    size_mb: 45.2
    notes: "Fixed RDR2 adapter, added GTA5 support"
    published_at: Timestamp
"""
import json
import os
import sys
import subprocess
import tempfile

# Paths
_VERSION_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "version.json",
)


def _get_local_version() -> dict:
    """Read local version.json (bundled in EXE)."""
    if not os.path.exists(_VERSION_PATH):
        return {"version": "0.0.0", "build": 0, "channel": "dev"}
    with open(_VERSION_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_remote_version() -> dict | None:
    """Query Firestore /releases/stable for latest version."""
    try:
        import firebase_admin
        from firebase_admin import firestore as admin_firestore
        from firebase_admin import credentials

        # Try using existing Firebase app, or init a new one
        try:
            app = firebase_admin.get_app()
        except ValueError:
            key_path = os.environ.get(
                "GAMELENS_FIREBASE_KEY",
                os.path.join(os.path.dirname(__file__), "..", "..",
                             "firebase", "gamelens-firebase-key.json"),
            )
            if os.path.exists(key_path):
                cred = credentials.Certificate(key_path)
                firebase_admin.initialize_app(cred)

        db = admin_firestore.client()
        doc = db.collection("releases").document("stable").get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        print(f"[Updater] Cannot check remote version: {e}")
    return None


def check_update(auto_install: bool = True) -> dict:
    """Check for updates. Returns {"update_available": bool, ...}.

    If auto_install=True and update is available, downloads and
    triggers the install, then exits the process.
    """
    local = _get_local_version()
    remote = _get_remote_version()

    if remote is None:
        return {
            "update_available": False,
            "local_version": local["version"],
            "local_build": local["build"],
            "error": "Cannot reach update server",
        }

    local_build = local.get("build", 0)
    remote_build = remote.get("build", 0)

    result = {
        "update_available": remote_build > local_build,
        "local_version": local["version"],
        "local_build": local_build,
        "remote_version": remote.get("version", "?"),
        "remote_build": remote_build,
        "notes": remote.get("notes", ""),
    }

    if not result["update_available"]:
        return result

    if not auto_install:
        return result

    # Download and install
    print(f"\n[Updater] New version available: {remote['version']} "
          f"(build {remote_build})")
    print(f"[Updater] Current: {local['version']} (build {local_build})")
    print(f"[Updater] Notes: {remote.get('notes', 'N/A')}")

    url = remote.get("url")
    if not url:
        print("[Updater] No download URL in release. Skipping.")
        result["error"] = "No download URL"
        return result

    success = _download_and_install(url, remote)
    result["installed"] = success
    return result


def _download_and_install(url: str, release: dict) -> bool:
    """Download new EXE, write updater script, exit."""
    import urllib.request

    app_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
        else os.getcwd()
    new_exe = os.path.join(tempfile.gettempdir(), "GameLens_update.exe")
    batch_file = os.path.join(tempfile.gettempdir(), "gamelens_updater.bat")

    try:
        # Download
        print(f"[Updater] Downloading {release.get('size_mb', '?')} MB...")
        urllib.request.urlretrieve(url, new_exe)
        print(f"[Updater] Downloaded to {new_exe}")

        # Find current EXE path
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
        else:
            print("[Updater] Not running as EXE — skipping self-replace.")
            print(f"[Updater] New version downloaded to: {new_exe}")
            return True

        # Write updater batch script
        batch = (
            f'@echo off\r\n'
            f'echo GameLens Updater\r\n'
            f'timeout /t 2 /nobreak >nul\r\n'
            f'echo Installing update...\r\n'
            f'move /Y "{new_exe}" "{current_exe}"\r\n'
            f'if %ERRORLEVEL% EQU 0 (\r\n'
            f'    echo Update complete! Restarting...\r\n'
            f'    start "" "{current_exe}"\r\n'
            f') else (\r\n'
            f'    echo Update failed. Please reinstall manually.\r\n'
            f'    pause\r\n'
            f')\r\n'
            f'del "%~f0"\r\n'
        )
        with open(batch_file, "w") as f:
            f.write(batch)

        print(f"[Updater] Launching updater and exiting...")
        subprocess.Popen(
            ["cmd", "/c", batch_file],
            creationflags=subprocess.CREATE_NO_WINDOW
            if sys.platform == "win32" else 0,
        )
        sys.exit(0)

    except Exception as e:
        print(f"[Updater] Download failed: {e}")
        return False


if __name__ == "__main__":
    # Standalone check (run directly for testing)
    result = check_update(auto_install=False)
    print(json.dumps(result, indent=2))
