import time
import threading
from typing import Optional
from .hook_manager import HookManager
from .registry import GameRegistry
from .interfaces import BaseGameAdapter, SubtitleEvent

class DublajEngine:
    """
    The Core Engine that runs the dubbing pipeline.
    Decoupled from the UI.
    """
    def __init__(self):
        self.hook_manager = HookManager()
        self.is_running = False
        self._logic_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # State
        self.active_game_id: Optional[str] = None
        self.active_mode: Optional[str] = None
        self._mod_installed = False

        # Callbacks (UI listeners)
        self.on_subtitle_callback = None
        self.on_status_change_callback = None
        
        self.initialize()

    def initialize(self):
        print("[Engine] Initializing...")
        # Load Translation Service
        from .translator import TranslationService
        self.translator = TranslationService(target_lang='tr')
        pass

    def select_game(self, game_id: str):
        print(f"[Engine] Selecting game: {game_id}")
        self.active_game_id = game_id

        # ── Catalog check: try mod install first ──
        from .catalog_manager import CatalogManager
        catalog = CatalogManager()
        mod = catalog.check(game_id, lang="tr")

        if mod:
            print(f"[Engine] Catalog match: {mod.get('version')}. Installing mod...")
            from .mod_installer import ModInstaller
            installer = ModInstaller()
            success = installer.install(mod)
            if success:
                print("[Engine] Mod installed successfully. OCR pipeline not needed.")
                self._mod_installed = True
                if self.on_status_change_callback:
                    self.on_status_change_callback("mod_installed")
                return
            else:
                print("[Engine] Mod install failed. Falling back to OCR pipeline.")
        # ── End catalog check ──

        # Original flow: load adapter and prepare pipeline
        from .registry import GameRegistry
        adapter = GameRegistry.get_adapter(game_id)

        if adapter:
            print(f"[Engine] Loading Adapter: {adapter.DISPLAY_NAME}")
            self.hook_manager.set_active_adapter(adapter)
        else:
            print(f"[Engine] ERROR: Could not load adapter for {game_id}")
        
    def set_mode(self, mode_name: str):
         print(f"[Engine] Setting mode: {mode_name}")
         self.active_mode = mode_name
         if self.hook_manager.active_adapter:
             self.hook_manager.active_adapter.set_mode(mode_name)

    def start(self):
        if self.is_running:
            return

        if self._mod_installed:
            print("[Engine] Mod already installed. OCR pipeline skipped.")
            if self.on_status_change_callback:
                self.on_status_change_callback("mod_installed")
            return

        print("[Engine] Starting Pipeline...")
        self.is_running = True
        self._stop_event.clear()
        
        # Start Logic Loop
        self._logic_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._logic_thread.start()
        
        if self.on_status_change_callback:
            self.on_status_change_callback("running")

    def stop(self):
        if not self.is_running:
            return

        print("[Engine] Stopping Pipeline...")
        self.is_running = False
        self._stop_event.set()
        
        # Stop Hook Manager
        self.hook_manager.stop()
        
        if self._logic_thread:
            self._logic_thread.join(timeout=2.0)
            
        if self.on_status_change_callback:
            self.on_status_change_callback("stopped")

    def _run_loop(self):
        # 1. Resolve Adapter
        adapter_cls = None
        
        if self.active_game_id:
             adapter = GameRegistry.get_adapter(self.active_game_id)
        else:
             # Auto-detect not yet implemented in Registry fully, 
             # but HookManager has some logic. Refactor later.
             # For MVP, we need explicit selection.
             print("[Engine] No game selected. Waiting...")
             return

        if not adapter:
            print(f"[Engine] Error: Could not instantiate adapter for {self.active_game_id}")
            self.is_running = False
            return

        # 2. Configure HookManager
        # We inject the specific adapter instance into HookManager
        # or we tell HookManager to use this adapter.
        # Current HookManager logic uses 'detect_game'. We need to override it.
        # Let's update HookManager to accept an adapter.
        
        print(f"[Engine] Loading Adapter: {adapter.DISPLAY_NAME}")
        self.hook_manager.set_active_adapter(adapter)
        
        if self.active_mode:
            adapter.set_mode(self.active_mode)
            
        # 3. Start Hook Manager
        # We pass our internal handler which forwards to UI
        self.hook_manager.start(self._internal_subtitle_handler)
        
        # Keep alive loop (if needed, or let HookManager thread do it)
        # HookManager spawns its own thread. We just wait here or monitor.
        while self.is_running and not self._stop_event.is_set():
            time.sleep(1)

    def _internal_subtitle_handler(self, event: SubtitleEvent):
        # 1. Processing (Translation)
        if event.text and not event.keep_alive:
            # We have text, let's translate it
            if hasattr(self, 'translator'):
                original = event.text
                translated = self.translator.translate(original)
                print(f"[Translation] '{original[:20]}...' -> '{translated[:20]}...'")
                
                # Update event text to show translation on Overlay
                event.text = translated
        
        # 2. Forward to UI/Overlay
        if self.on_subtitle_callback:
            self.on_subtitle_callback(event)

# Global Singleton
engine = DublajEngine()
