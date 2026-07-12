import time
from typing import Optional
from ..core.interfaces import BaseGameAdapter, SubtitleEvent
from ..core.vision import ScreenCapture
from ..core.preprocessor import ImagePreprocessor
from rapidocr_onnxruntime import RapidOCR
import numpy as np

from ..core.registry import GameRegistry
from ..core.interfaces import GameMode

@GameRegistry.register
class FirewatchAdapter(BaseGameAdapter):
    GAME_ID = "firewatch"
    DISPLAY_NAME = "Firewatch"
    DESCRIPTION = "Forest mystery adventure. Supports dialogue and choices."
    CAPABILITIES = {"dialogue": True, "journal": False}

    """
    Adapter for Firewatch.
    Strategy: Vision (OCR)
    Zones:
      1. Center (Choices/Narration)
      2. Bottom (Subtitles)
    """
    def __init__(self, game_id: str = None):
        super().__init__(game_id)
        
        self.modes = {
            "default": GameMode(
                name="Standard",
                auto=True,
                regions=[(384, 300, 1152, 400), (384, 864, 1152, 162)], # Center + Bottom
                ocr_profile="firewatch_colored" 
            )
        }
        
        # Explicit default
        self.set_mode("default")
        
        self._connected = False
        self._last_final_text = ""
        self._last_time = 0
        
        self.region_center = (384, 300, 1152, 400) 
        self.region_bottom = (384, 864, 1152, 162)
        
        self.suppressed_texts = [] 

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
        # Return regions based on current mode
        return self.current_mode.regions

    def get_ocr_profile(self) -> str:
        return self.current_mode.ocr_profile

    def process_raw_result(self, text: str, layout: list, meta: dict) -> Optional[SubtitleEvent]:
        # 'text' is the raw joined text from generic OCR.
        # Firewatch logic needs specific layout parsing to separate choices vs subtitles,
        # but for MVP cleanup, we can rely on the joined text if it's "OK", or use layout re-logic.
        
        # The original logic sorted by Y and X to stitch lines.
        # RapidOCR's default result might not be perfectly sorted if we just joined it blindly in HookManager.
        # However, for now, let's assume HookManager sends us valid 'layout' data (the raw result list).
        
        # We need to re-implement the "Row Grouping" logic here if we want to maintain high quality formatting.
        # But for this 'Clean Architecture' step, let's use the provided text and just do validation.
        
        if not text:
            return None
            
        found_text = text.strip()
        
        # Simple Validation
        if len(found_text) < 2:
            return None
            
        # 1. Similarity for Event Debouncing (Adapter Level)
        # HookManager handles Hash check loop-skipping, but we might still want fuzzy check here
        # to prevent "Run" vs "Run." flickering updates.
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, self._last_final_text, found_text).ratio()
        
        if similarity > 0.8:
            # Same text - maybe send KeepAlive?
            # HookManager's hash check handles exact matches.
            # If we are here, it means text changed slightly (e.g. OCR noise).
            # If it's very similar, we can ignore it to prevent flicker.
             return None
             
        self._last_final_text = found_text
        
        # Calculate Layout for AR Overlay
        # (Simplified: Just use the bounding box of the whole text or pass generic)
        # Ideally we reconstruct the detailed boxes from 'layout' param.
        # For now, we return valid text.
        
        print(f"[{self.DISPLAY_NAME}] Processed: '{found_text}'")
        
        return SubtitleEvent(
            text=found_text,
            start_time=meta['timestamp'],
            duration=4.0,
            is_original=True,
            layout=[] # We can implement detailed layout parsing later
        )

    def register_suppressed_text(self, text: str):
        self.suppressed_texts.append(text)
        if len(self.suppressed_texts) > 5:
            self.suppressed_texts.pop(0)
