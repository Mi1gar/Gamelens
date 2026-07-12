"""Sidecar API for Tauri UI communication.

Receives commands via command-line args, outputs JSON to stdout.

Usage:
    python engine/sidecar_api.py --list-games
    python engine/sidecar_api.py --run rdr2 --monitor 1
"""
import sys
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Register NVIDIA DLLs (needed if sidecar spawns the full pipeline)
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


def cmd_list_games():
    """Output JSON array of available games."""
    import engine.adapters.rdr2_adapter  # noqa: F401
    import engine.adapters.metro_adapter  # noqa: F401
    import engine.adapters.gta5_adapter  # noqa: F401
    from engine.core.registry import GameRegistry

    games = GameRegistry.get_all_games()
    print(json.dumps({"type": "games", "data": games}))


def cmd_run(args):
    """Return status for starting a game (actual pipeline is run.py)."""
    print(json.dumps({
        "type": "status",
        "data": {
            "status": "starting",
            "game": args.get("game", "unknown"),
            "monitor": args.get("monitor", 1),
            "message": (
                "Pipeline starting, overlay will appear on game screen."
            ),
        },
    }))


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"type": "error", "data": "No command"}))
        return

    cmd = sys.argv[1]

    if cmd == "--list-games":
        cmd_list_games()
    elif cmd == "--run":
        game = sys.argv[2] if len(sys.argv) > 2 else "rdr2"
        monitor = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        cmd_run({"game": game, "monitor": monitor})
    else:
        print(json.dumps({
            "type": "error",
            "data": f"Unknown command: {cmd}",
        }))


if __name__ == "__main__":
    main()
