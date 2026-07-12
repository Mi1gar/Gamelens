"""HTTP API server — bridges the React UI to the Python engine.

Start with: python engine/http_api.py
Then open:  http://localhost:1420

The engine runs as a SUBPROCESS (python run.py). This keeps the overlay
in its own clean Python process — proven to work with fullscreen apps.
"""

import json
import sys
import os
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# Register NVIDIA DLLs
import site, glob
for sp in site.getsitepackages():
    for p in ['nvidia/cudnn/bin', 'nvidia/cublas/bin',
              'nvidia/cuda_runtime/bin']:
        for d in glob.glob(os.path.join(sp, p)):
            if os.path.isdir(d):
                try: os.add_dll_directory(d)
                except: pass

import engine.adapters.rdr2_adapter  # noqa
import engine.adapters.metro_adapter  # noqa
import engine.adapters.gta5_adapter  # noqa
from engine.core.registry import GameRegistry

# Engine subprocess handle
_engine_proc: subprocess.Popen | None = None
_active_game: str | None = None

PYTHON = sys.executable  # same Python that runs this script


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send({})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/games":
            self._send(GameRegistry.get_all_games())
        elif path == "/api/status":
            self._send({
                "running": _engine_proc is not None and _engine_proc.poll() is None,
                "game": _active_game,
            })
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        global _engine_proc, _active_game
        path = urlparse(self.path).path

        if path.startswith("/api/start/"):
            game_id = path.split("/api/start/")[1]
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}
            monitor_idx = body.get("monitor", 1)

            if not GameRegistry.get_adapter(game_id):
                return self._send({"error": f"Game '{game_id}' not found"}, 404)

            # Kill existing engine if running
            if _engine_proc and _engine_proc.poll() is None:
                _engine_proc.kill()
                _engine_proc.wait()

            # Spawn engine as subprocess — overlay gets its own main thread
            cmd = [PYTHON, "run.py", "--game", game_id, "--monitor", str(monitor_idx)]
            _engine_proc = subprocess.Popen(
                cmd,
                cwd=ROOT,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            _active_game = game_id
            print(f"  [API] Started: {game_id} on monitor {monitor_idx} (pid={_engine_proc.pid})")
            self._send({"status": "started", "game": game_id, "monitor": monitor_idx})

        elif path == "/api/stop":
            if _engine_proc and _engine_proc.poll() is None:
                _engine_proc.kill()
                _engine_proc.wait()
                print(f"  [API] Stopped: {_active_game}")
            _active_game = None
            self._send({"status": "stopped"})

        else:
            self._send({"error": "not found"}, 404)


def main():
    print(f"\n{'='*50}")
    print(f"  Game Lens API")
    print(f"  HTTP: http://localhost:9876")
    print(f"  UI:   http://localhost:1420")
    print(f"  Python: {PYTHON}")
    print(f"{'='*50}\n")

    server = HTTPServer(("127.0.0.1", 9876), APIHandler)
    print("  Ready.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if _engine_proc and _engine_proc.poll() is None:
            _engine_proc.kill()


if __name__ == "__main__":
    main()
