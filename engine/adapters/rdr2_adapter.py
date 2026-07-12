import time
from typing import Optional, List, Dict, Any
from ..core.interfaces import BaseGameAdapter, SubtitleEvent, GameMode
from ..core.registry import GameRegistry
import numpy as np

@GameRegistry.register
class RDR2Adapter(BaseGameAdapter):
    GAME_ID = "rdr2"
    DISPLAY_NAME = "Red Dead Redemption 2"
    DESCRIPTION = "High-quality story-driven translation for RDR2. Optimized for cinematic subtitles."
    CAPABILITIES = {"dialogue": True, "journal": False, "notifications": False}

    def __init__(self, game_id: str = None):
        super().__init__(game_id)
        self._screen_w = 1920
        self._screen_h = 1080
        self._connected = False
        self._last_final_text = ""

    def connect(self) -> bool:
        # Detect actual monitor resolution at connect time
        try:
            import mss
            with mss.mss() as sct:
                if len(sct.monitors) > 1:
                    m = sct.monitors[1]
                    self._screen_w = m["width"]
                    self._screen_h = m["height"]
        except Exception:
            pass

        # YOLO mode: capture full screen dynamically
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
        
        # Validation
        if len(found_text) < 2:
            return None
            
        # Debouncing: Check if text is significantly different from last frame
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, self._last_final_text, found_text).ratio()
        
        # In cinematic games like RDR2, subtitles stick for a while.
        # High threshold to prevent flickering on OCR jitter.
        if similarity > 0.9:
             return None
             
        self._last_final_text = found_text
        
        print(f"[{self.DISPLAY_NAME}] Subtitle Detected: '{found_text[:50]}...'")
        
        return SubtitleEvent(
            text=found_text,
            start_time=meta['timestamp'],
            duration=5.0, # RDR2 subs are usually long
            is_original=True,
            layout=layout
        )
