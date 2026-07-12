import os
import glob
import json
from typing import Dict, Optional

class SubtitleLoader:
    """
    Loads subtitle files from the 'import' directory.
    Supports .txt (line-by-line) and .csv (key,value or original,translation).
    
    This acts as the 'Offline Extraction' component of the Hybrid Architecture.
    """
    
    def __init__(self, import_dir: str = "import"):
        self.import_dir = os.path.abspath(import_dir)
        self.cache_file = os.path.join(self.import_dir, "_cache.json")
        self.data: Dict[str, str] = {}
        
    def set_root_path(self, path: str):
        """Sets the root path to scan for subtitles (Game Folder)"""
        if path and os.path.exists(path):
            self.import_dir = path
            print(f"[SubtitleLoader] Root path set to: {self.import_dir}")

    def load(self) -> Dict[str, str]:
        """
        Loads all subtitles. Checks cache first for speed.
        Returns a dict of {cleaned_original_text: translation}.
        """
        if not os.path.exists(self.import_dir):
            # If default import dir doesn't exist, just return empty
            # If game dir doesn't exist, we likely wouldn't be here
            return {}

        self.data = {}
        # Scan recursively might be better, but flat for now to be safe
        files = glob.glob(os.path.join(self.import_dir, "*"))
        
        print(f"[SubtitleLoader] Scanning {self.import_dir}...")
        
        for file in files:
            if file.endswith("README.txt") or file.endswith("_cache.json"):
                continue
                
            try:
                count = 0
                ext = os.path.splitext(file)[1].lower()
                
                # Support plain text extensions
                is_text = ext in ['.txt', '.lng']
                
                with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                    if ext == '.csv':
                        import csv
                        reader = csv.reader(f)
                        for row in reader:
                            if len(row) >= 1:
                                original = row[0].strip()
                                translation = row[1].strip() if len(row) > 1 else original 
                                if original:
                                    self._add(original, translation)
                                    count += 1
                    elif is_text:
                        # Assumes .txt or .lng is line-by-line raw text
                        for line in f:
                            text = line.strip()
                            if text and len(text) > 1:
                                self._add(text, text)
                                count += 1
                                
                if count > 0:
                    print(f"[SubtitleLoader] Loaded {count} lines from {os.path.basename(file)}")
                
            except Exception as e:
                print(f"[SubtitleLoader] Error loading {file}: {e}")
                
        print(f"[SubtitleLoader] Total loaded: {len(self.data)} unique phrases.")
        return self.data
        
    def _add(self, key: str, value: str):
        """Adds to registry with normalization key"""
        norm_key = key.lower().strip(".,!?\"' ")
        if norm_key:
            self.data[norm_key] = value

_loader_instance = None

def get_loader():
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = SubtitleLoader()
    return _loader_instance
