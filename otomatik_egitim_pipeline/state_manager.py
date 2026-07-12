"""Persistent state tracking for pipeline resume support."""
import json
import os
import time
from typing import Optional


class StateManager:
    """Read/write pipeline_state.json for step tracking and resume."""

    def __init__(self, state_path: str):
        self._path = state_path
        self._data: dict = self._load()

    def _load(self) -> dict:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "collect": {"status": "pending", "downloaded": [], "failed": []},
            "extract": {"status": "pending", "total_frames": 0, "candidates": 0,
                        "processed_videos": []},
            "label": {"status": "pending", "processed": 0, "total": 0,
                      "labeled_count": 0, "empty_count": 0, "error_count": 0},
            "package": {"status": "pending", "path": "", "frame_count": 0},
            "import": {"status": "pending", "approved": 0, "rejected": 0,
                       "edited": 0},
        }

    def save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get_step(self, step: str) -> dict:
        if step not in self._data:
            self._data[step] = {"status": "pending"}
        return self._data[step]

    def set_step(self, step: str, **kwargs):
        if step not in self._data:
            self._data[step] = {}
        self._data[step].update(kwargs)
        self.save()

    def is_step_done(self, step: str) -> bool:
        return self._data.get(step, {}).get("status") == "done"

    def get_next_step(self) -> Optional[str]:
        """Return the first step that isn't done, or None if all done."""
        order = ["collect", "extract", "label", "classify", "package", "import"]
        for step in order:
            if not self.is_step_done(step):
                return step
        return None

    @property
    def stats(self) -> dict:
        return {
            "collect": self._data.get("collect", {}),
            "extract": self._data.get("extract", {}),
            "label": self._data.get("label", {}),
            "import": self._data.get("import", {}),
        }
