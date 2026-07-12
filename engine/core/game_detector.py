import os
import winreg
from typing import Optional

class GameDetector:
    """
    Detects the installation of Metro 2033 Redux.
    Strategy:
    1. Steam Registry Auto-Detect.
    2. Manual Selection Validation.
    """
    
    STEAM_APP_ID = "286690" # Metro 2033 Redux App ID
    GAME_EXE = "metro.exe"
    
    @staticmethod
    def auto_detect() -> Optional[str]:
        """
        Attempts to find the game path via Steam Registry.
        Returns absolute path if found and validated, else None.
        """
        path = GameDetector._check_steam_registry()
        if path and GameDetector.validate_path(path):
            print(f"[GameDetector] Found via Steam: {path}")
            return path
        return None

    @staticmethod
    def _check_steam_registry() -> Optional[str]:
        try:
            # Look in HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 286690
            # Or usually Steam stores library folders in a VDF, but registry is easiest for main install.
            # Alternative: HKLM\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 286690
            
            key_path = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Steam App {GameDetector.STEAM_APP_ID}"
            
            # Check 64-bit registry view (Wow6432Node) usually for Steam on 64-bit Windows
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Steam App {GameDetector.STEAM_APP_ID}") as key:
                    path, _ = winreg.QueryValueEx(key, "InstallLocation")
                    return path
            except FileNotFoundError:
                pass
                
            # Check 32-bit registry view
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                    path, _ = winreg.QueryValueEx(key, "InstallLocation")
                    return path
            except FileNotFoundError:
                pass
                
        except Exception as e:
            print(f"[GameDetector] Registry check failed: {e}")
            
        return None

    @staticmethod
    def validate_path(path: str) -> bool:
        """
        Checks if the folder looks like a valid Metro 2033 Redux directory.
        Strictly checks for file existence, NOT license/DRM.
        """
        if not path or not os.path.exists(path):
            return False
            
        required_files = [GameDetector.GAME_EXE, "content.vfx"]
        
        for file in required_files:
            file_path = os.path.join(path, file)
            if not os.path.exists(file_path):
                # print(f"[GameDetector] Missing signature file: {file}")
                return False
                
        return True
