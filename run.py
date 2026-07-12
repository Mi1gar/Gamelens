#!/usr/bin/env python
"""Game Lens — Real-time game subtitle translator.

Usage:
    python run.py --game rdr2 --monitor 1
    python run.py --game metro_2033
    python run.py --list-games
"""
import sys
import os
import time
import threading
import argparse

# Ensure project root is on path
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# Register NVIDIA DLLs early (before any torch/onnx import)
import site
import glob

for sp in site.getsitepackages():
    for p in ['nvidia/cudnn/bin', 'nvidia/cublas/bin',
              'nvidia/cuda_runtime/bin']:
        for d in glob.glob(os.path.join(sp, p)):
            if os.path.isdir(d):
                try:
                    os.add_dll_directory(d)
                except Exception:
                    pass
                os.environ['PATH'] = (
                    d + os.pathsep + os.environ.get('PATH', '')
                )


def list_games():
    """Print all registered game adapters."""
    from engine.core.registry import GameRegistry
    # Force import adapters to trigger registration
    import engine.adapters.rdr2_adapter  # noqa: F401
    import engine.adapters.metro_adapter  # noqa: F401
    import engine.adapters.gta5_adapter  # noqa: F401

    games = GameRegistry.get_all_games()
    print("\nAvailable games:")
    print("-" * 50)
    for g in games:
        print(f"  {g['id']:20s} — {g['name']}")
        if g.get('description'):
            print(f"  {'':20s}   {g['description']}")
    print()


def run_game(game_id: str, monitor_idx: int = 1):
    """Start the translation pipeline for a specific game."""
    import mss
    from engine.core.registry import GameRegistry
    from engine.core.hook_manager import HookManager
    from engine.overlay import SubtitleOverlay

    # Force import adapters
    import engine.adapters.rdr2_adapter  # noqa: F401
    import engine.adapters.metro_adapter  # noqa: F401
    import engine.adapters.gta5_adapter  # noqa: F401

    # Get monitor info
    with mss.mss() as sct:
        if monitor_idx >= len(sct.monitors):
            print(
                f"Error: Monitor {monitor_idx} not found. "
                f"Available: 1-{len(sct.monitors) - 1}"
            )
            return
        monitor = sct.monitors[monitor_idx]

    print(f"\n{'='*60}")
    print(f"Game Lens — {game_id.upper()}")
    print(f"Monitor {monitor_idx}: {monitor['width']}x{monitor['height']}")
    print(f"{'='*60}\n")

    # Get adapter
    adapter = GameRegistry.get_adapter(game_id)
    if not adapter:
        print(f"Error: Game '{game_id}' not found.")
        list_games()
        return

    # Create overlay (on main thread, Tkinter requires it)
    overlay = SubtitleOverlay(monitor)

    # Create HookManager
    hook_mgr = HookManager()
    hook_mgr.overlay = overlay
    hook_mgr.set_active_adapter(adapter)

    # Simple callback — overlay is already updated directly by HookManager
    def on_subtitle(event):
        pass

    # Start pipeline in background
    hook_mgr.start(on_subtitle)

    print("\nPipeline running. Overlay will appear below subtitles.")
    print("Close the overlay window to stop.\n")

    try:
        overlay.run()  # Blocks until window closed
    except KeyboardInterrupt:
        print("\nShutting down...")

    hook_mgr.stop()
    print("Game Lens stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Game Lens — Real-time Game Subtitle Translator",
    )
    parser.add_argument(
        "--game", "-g", type=str,
        help="Game ID (e.g. rdr2, metro_2033)",
    )
    parser.add_argument(
        "--monitor", "-m", type=int, default=1,
        help="Monitor index (default: 1)",
    )
    parser.add_argument(
        "--list-games", "-l", action="store_true",
        help="List available games",
    )
    parser.add_argument(
        "--skip-update", action="store_true",
        help="Skip update check on startup",
    )
    parser.add_argument(
        "--no-splash", action="store_true",
        help="Skip splash screen (console mode)",
    )
    args = parser.parse_args()

    # ── Splash Screen ──
    splash = None
    if not args.no_splash:
        from engine.core.splash import show_splash
        splash = show_splash()
        splash.set_status("Baslatiliyor...")

    # ── OTA Update Check ──
    if not args.skip_update and getattr(sys, 'frozen', False):
        if splash:
            splash.set_status("Guncelleme kontrol ediliyor...")
        try:
            from engine.core.updater import check_update
            result = check_update(auto_install=True)
            if result.get("error"):
                print(f"[run] Update check: {result['error']}")
        except Exception as e:
            print(f"[run] Update check failed: {e}")

    # ── Model + Runtime Check ──
    try:
        from engine.core.model_manager import ensure_models

        def startup_progress(pct, done, total):
            if splash:
                splash.set_progress(pct, done, total)

        if splash:
            splash.set_status("ML kutuphaneleri kontrol ediliyor...")

        if not ensure_models(progress_callback=startup_progress):
            if splash:
                splash.set_status("HATA: Indirme basarisiz. Interneti kontrol edin.")
                import time
                time.sleep(5)
                splash.close()
            return
    except Exception as e:
        if splash:
            splash.set_status(f"Hata: {e}")
            import time
            time.sleep(3)
            splash.close()
        return

    if args.list_games:
        list_games()
        return

    if not args.game:
        parser.print_help()
        print("\nTip: Use --list-games to see available games.")
        return

    run_game(args.game, args.monitor)


if __name__ == "__main__":
    main()
