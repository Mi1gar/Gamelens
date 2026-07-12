from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import time

@dataclass
class PipelineMetrics:
    """
    Centralized metrics for a single subtitle event processing.
    """
    event_id: str
    capture_latency: float = 0.0 # Time from game emit to our hook receiving
    translation_latency: float = 0.0
    tts_latency: float = 0.0
    total_latency: float = 0.0
    
    def __str__(self):
        return (f"[Metrics] Total: {self.total_latency:.0f}ms | "
                f"Trans: {self.translation_latency:.0f}ms | "
                f"TTS: {self.tts_latency:.0f}ms")

@dataclass
class SubtitleEvent:
    text: str
    start_time: float
    duration: float
    speaker: Optional[str] = None
    # AR Layout: List of dicts {'text':Str, 'box':[x,y,w,h], 'zone': 'center'|'bottom'}
    layout: Optional[list] = None
    is_original: bool = True
    keep_alive: bool = False # If True, don't translate/process, just refresh overlay timeout
    # Metrics tracking
    metrics: Optional[PipelineMetrics] = None

@dataclass
class GameMode:
    """
    Drives the behavior of the engine for a specific game state.
    """
    name: str # e.g. "Dialogue", "Journal"
    auto: bool = True # If True, continously poll. If False, might trigger on keypress (future).
    
    # Vision / OCR Config
    regions: List[tuple] = field(default_factory=list) # List of (x,y,w,h) relative or absolute
    ocr_profile: str = "subtitle" # 'subtitle', 'document', 'fast'
    
    # Logic Config
    debounce_ms: int = 200
    similarity_threshold: float = 0.85
    
    # Metadata
    description: str = ""

class BaseGameAdapter(ABC):
    """
    Abstract Base Class for all Game Adapters.
    Includes metadata and mode management for proper UI integration.
    """
    
    # Static Metadata for Registry Inspection (No instantiation required)
    GAME_ID: str = "unknown"
    DISPLAY_NAME: str = "Unknown Game"
    DESCRIPTION: str = ""
    ICON_PATH: Optional[str] = None
    CAPABILITIES: Dict[str, bool] = {} # e.g. {"dialogue": True}
    
    def __init__(self, game_id: Optional[str] = None):
        # Allow override, but default to class ID
        self.game_id = game_id or self.GAME_ID
        self.is_connected = False
        
        # Mode Management
        self.modes: Dict[str, GameMode] = {}
        self.current_mode_name: str = "default"
        self._current_mode: Optional[GameMode] = None 
        
        # Mode Management
        self.modes: Dict[str, GameMode] = {}
        self.current_mode_name: str = "default"
        self._current_mode: Optional[GameMode] = None

    @property
    def current_mode(self) -> GameMode:
        if not self._current_mode:
            # Fallback to defaults if not set
            return GameMode(name="fallback")
        return self._current_mode

    def set_mode(self, mode_name: str):
        """
        Switch the active operating mode.
        """
        if mode_name in self.modes:
            self.current_mode_name = mode_name
            self._current_mode = self.modes[mode_name]
            print(f"[{self.DISPLAY_NAME}] Switched to mode: {mode_name}")
        else:
            print(f"[{self.DISPLAY_NAME}] Warning: Mode '{mode_name}' not defined.")

    @abstractmethod
    def connect(self) -> bool:
        """
        Prepare the adapter (load configs, assets).
        """
        pass

    @abstractmethod
    def disconnect(self):
        """
        Cleanup.
        """
        pass

    @abstractmethod
    def get_regions(self) -> List[tuple]:
        """
        Returns a list of regions (x, y, w, h) to capture for the current mode.
        """
        pass

    @abstractmethod
    def get_ocr_profile(self) -> str:
        """
        Returns the OCR profile name to use (e.g. 'subtitle', 'metro_orange').
        """
        pass

    @abstractmethod
    def process_raw_result(self, text: str, layout: List[Dict[str, Any]], meta: Dict[str, Any]) -> Optional[SubtitleEvent]:
        """
        Post-process the raw OCR result.
        
        Args:
            text: Single string of all found text (joined).
            layout: List of dicts describing individual text blocks.
            meta: Metadata including 'timestamp', 'frame_count', 'zone_id'.
            
        Returns:
            SubtitleEvent if valid content is found, else None.
        """
        pass

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """
        Check if the game is still considered active.
        """
        pass 
