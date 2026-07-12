from ..core.registry import GameRegistry
from ..core.interfaces import BaseGameAdapter, GameMode, SubtitleEvent
from ..core.vision import ScreenCapture
from ..core.preprocessor import ImagePreprocessor
from typing import Optional
from rapidocr_onnxruntime import RapidOCR
import time

@GameRegistry.register
class MetroAdapter(BaseGameAdapter):
    GAME_ID = "metro_2033"
    DISPLAY_NAME = "Metro 2033 Redux"
    DESCRIPTION = "Post-apocalyptic FPS. Subtitles are Orange, Bottom-Center."
    CAPABILITIES = {"dialogue": True, "journal": False} 

    def __init__(self, game_id: str = None):
        super().__init__(game_id)
        
        # Region Estimation based on screenshot (1920x1080)
        # Expanded to support multi-line subtitles
        self.region_bottom = (300, 720, 1320, 360)
        
        self.modes = {
            "default": GameMode(
                name="Dialogue",
                auto=True,
                regions=[self.region_bottom],
                ocr_profile="metro_orange" # Using optimized Orange text profile
            )
        }
        
        self.set_mode("default")
        self._connected = False
        self._last_final_text = ""

    def connect(self) -> bool:
        print(f"[{self.DISPLAY_NAME}] Connected. Configuration Loaded.")
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False

    @property
    def is_active(self) -> bool:
        return self._connected
    
    def get_regions(self) -> list:
        return self.current_mode.regions

    def get_ocr_profile(self) -> str:
        return self.current_mode.ocr_profile

    def process_raw_result(self, text: str, layout: list, meta: dict) -> Optional[SubtitleEvent]:
        # Metro 2033 specific post-processing
        
        if not text:
            return None
            
        from ..core.validator import TextValidator
        
        clean_text = TextValidator.cleanup_text(text)
        if not TextValidator.is_valid_text(clean_text):
            return None

        # Fuzzy Deduplication (Anti-Jitter)
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, clean_text, self._last_final_text).ratio()
        
        if similarity > 0.85:
             return None # Duplicate
             
        self._last_final_text = clean_text
        
        print(f"[{self.DISPLAY_NAME}] Detected: {clean_text}")
        
        return SubtitleEvent(
            text=clean_text,
            start_time=meta['timestamp'],
            duration=4.0,
            is_original=True,
            layout=layout # Pass raw layout for now, or adapt if needed
        )
