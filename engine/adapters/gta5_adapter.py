import time
from typing import Optional, List, Dict, Any
from ..core.interfaces import BaseGameAdapter, SubtitleEvent, GameMode
from ..core.registry import GameRegistry
import numpy as np

@GameRegistry.register
class GTA5Adapter(BaseGameAdapter):
    GAME_ID = "gta5"
    DISPLAY_NAME = "Grand Theft Auto V"
    DESCRIPTION = "Open-world action-adventure. Subtitles: white, bottom-center. HUD-heavy."
    CAPABILITIES = {"dialogue": True, "notifications": False, "phone": False}

    def __init__(self, game_id: str = None):
        super().__init__(game_id)
        self._screen_w = 1920
        self._screen_h = 1080
        self._connected = False
        self._last_final_text = ""

    def connect(self) -> bool:
        try:
            import mss
            with mss.mss() as sct:
                if len(sct.monitors) > 1:
                    m = sct.monitors[1]
                    self._screen_w = m["width"]
                    self._screen_h = m["height"]
        except Exception:
            pass

        self.modes = {
            "default": GameMode(
                name="YOLO Full Screen",
                auto=True,
                regions=[(0, 0, self._screen_w, self._screen_h)],
                ocr_profile="subtitle",
            )
        }
        self.set_mode("default")
        print(f"[{self.DISPLAY_NAME}] Connected. Screen: {self._screen_w}x{self._screen_h}.")
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False

    @property
    def is_active(self) -> bool:
        return self._connected

    def get_regions(self) -> List[tuple]:
        return self.current_mode.regions

    def get_ocr_profile(self) -> str:
        return self.current_mode.ocr_profile

    def process_raw_result(self, text: str, layout: List[Dict[str, Any]], meta: Dict[str, Any]) -> Optional[SubtitleEvent]:
        if not text:
            return None

        found_text = text.strip()
        if len(found_text) < 2:
            return None

        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, self._last_final_text, found_text).ratio()
        if similarity > 0.9:
            return None

        self._last_final_text = found_text
        print(f"[{self.DISPLAY_NAME}] Subtitle Detected: '{found_text[:50]}...'")

        return SubtitleEvent(
            text=found_text,
            start_time=meta['timestamp'],
            duration=5.0,
            is_original=True,
            layout=layout,
        )
