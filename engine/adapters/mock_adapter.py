from typing import Optional
from ..core.interfaces import BaseGameAdapter, SubtitleEvent, GameMode
from ..core.registry import GameRegistry
import time
import random

@GameRegistry.register
class MockGameAdapter(BaseGameAdapter):
    GAME_ID = "mock_game"
    DISPLAY_NAME = "Mock Game (Test)"
    DESCRIPTION = "A simulated game for testing the pipeline."
    CAPABILITIES = {"dialogue": True, "journal": True}
    
    def __init__(self, game_id: str = None):
        super().__init__(game_id)
        # Define Modes
        self.modes = {
            "default": GameMode(
                name="Dialogue", 
                auto=True,
                regions=[(100, 100, 400, 100)], # Dummy region
                ocr_profile="subtitle"
            ),
            "journal": GameMode(name="Journal", auto=False)
        }
        self.set_mode("default")
        self.is_connected = False
        
    def connect(self) -> bool:
        print("[Mock] Connected to simulated process.")
        self.is_connected = True
        return True

    def disconnect(self):
        print("[Mock] Disconnected.")
        self.is_connected = False

    @property
    def is_active(self) -> bool:
        return self.is_connected

    def get_regions(self) -> list:
        return self.current_mode.regions

    def get_ocr_profile(self) -> str:
        return self.current_mode.ocr_profile

    def process_raw_result(self, text: str, layout: list, meta: dict) -> Optional[SubtitleEvent]:
        # Simulate successful detection occasionally
        # Since we are mocking, the "Capture" might be black screen in real life if we don't mock ScreenCapture too.
        # But `HookManager` now uses real `ScreenCapture`.
        # So running this with real screen capture might actually OCR the screen!
        
        if not text:
             return None
             
        # Mock logic: Accept anything
        print(f"[Mock] Processed: {text}")
        
        return SubtitleEvent(
            text=text,
            start_time=meta['timestamp'],
            duration=3.0,
            is_original=True
        )
