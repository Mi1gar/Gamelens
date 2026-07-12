import sys
import os
sys.path.append(os.getcwd())
from src.core.registry import GameRegistry
from src.core.engine import engine
import src.adapters.mock_adapter # Register Mock
import src.adapters.firewatch_adapter # Register Firewatch
import src.adapters.metro_adapter # Register Metro
import time
import threading

def verify():
    print("--- [VERIFY] Architectue Check ---")
    
    # 1. Check Registry
    games = GameRegistry.get_all_games()
    print(f"Registered Games: {[g['id'] for g in games]}")
    
    assert "mock_game" in [g['id'] for g in games], "Mock Game not registered"
    assert "firewatch" in [g['id'] for g in games], "Firewatch not registered"
    assert "metro_2033" in [g['id'] for g in games], "Metro 2033 not registered"
    
    # 2. Test Engine Startup with Mock
    print("\n--- [VERIFY] Starting Engine with Mock Game ---")
    engine.select_game("mock_game")
    
    # Hack: Inject a dummy callback to see output
    def on_sub(event):
        print(f"   >>> [UI RECEIVER] Got event: {event.text} (KeepAlive={event.keep_alive})")
        
    engine.on_subtitle_callback = on_sub
    
    engine.start()
    
    print("Engine started. Waiting 7 seconds for mock events...")
    time.sleep(7)
    
    engine.stop()
    print("Engine stopped.")
    
    # 3. Test Firewatch Instantiation (Dry Run)
    print("\n--- [VERIFY] Checking Firewatch Adapter load ---")
    fw = GameRegistry.get_adapter("firewatch")
    if fw:
        print(f"Firewatch Adapter loaded: {fw.DISPLAY_NAME}")
        print(f"Default Mode: {fw.modes['default'].name}")
    else:
        print("Failed to load Firewatch adapter")

if __name__ == "__main__":
    verify()
