# Auto-Labeling Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an automated dataset creation pipeline that downloads gameplay videos, extracts frames, labels subtitles with Florence-2, and produces YOLO-format training data with a human review step.

**Architecture:** 8 Python modules orchestrated by `pipeline.py`. Each step is independently runnable. State is persisted to `pipeline_state.json` for resume support. The review step produces a standalone HTML file (zero dependencies) that a non-technical reviewer opens in a browser.

**Tech Stack:** Python 3.11, yt-dlp, FFmpeg, Florence-2 (transformers + torch), OpenCV, Pillow, vanilla HTML/CSS/JS

## Global Constraints

- All files live under `D:\gammasoftware\GameLens\otomatik_egitim_pipeline\`
- Base directory is resolved relative to `pipeline.py` location (not cwd)
- Python 3.11, same environment as main Game Lens project
- Single class only: `s-subtittle` (class_id=0)
- YOLO format: normalized `class_id x_center y_center width height`
- Florence-2: `microsoft/Florence-2-base`, fp16, CUDA
- FFmpeg must be on PATH
- Review HTML must work offline (no CDN, no server)

---

### Task 1: Foundation — config.py + requirements_labeling.txt

**Files:**
- Create: `otomatik_egitim_pipeline/config.py`
- Create: `otomatik_egitim_pipeline/requirements_labeling.txt`

**Interfaces:**
- Produces: `PipelineConfig` dataclass with all configuration fields consumed by every other module

- [ ] **Step 1: Write config.py**

```python
"""Pipeline configuration — single source of truth for all settings."""
import os
from dataclasses import dataclass, field


@dataclass
class PipelineConfig:
    # ── Paths ──
    base_dir: str = ""  # Set at runtime to pipeline.py's directory

    # ── Video sources ──
    channels: list[str] = field(default_factory=lambda: ["MKIceAndFire"])
    max_videos: int = 50
    video_quality: str = "best[height<=1080]"
    title_filter: str = (
        "(?i)walkthrough|gameplay|full game|no commentary|cutscenes|full movie"
    )
    sleep_interval: int = 3  # seconds between yt-dlp requests

    # ── Frame extraction ──
    frame_fps: float = 0.5       # 1 frame every 2 seconds
    output_format: str = "png"

    # ── Pre-filter ──
    edge_density_threshold: float = 0.02
    subtitle_region_ratio: float = 0.40  # bottom 40% of screen

    # ── Florence-2 ──
    model_name: str = "microsoft/Florence-2-base"
    confidence_threshold: float = 0.6
    device: str = "cuda"
    batch_size: int = 4

    # ── Position filter ──
    min_y_ratio: float = 0.40         # bbox must be in bottom 40%
    min_width_ratio: float = 0.02     # bbox must be >2% of screen width
    min_text_length: int = 3          # text must be >3 chars

    # ── Dataset output ──
    train_split: float = 0.8
    seed: int = 42

    @property
    def data_dir(self) -> str:
        return os.path.join(self.base_dir, "data")

    @property
    def videos_dir(self) -> str:
        return os.path.join(self.data_dir, "videos")

    @property
    def frames_dir(self) -> str:
        return os.path.join(self.data_dir, "frames")

    @property
    def labeled_dir(self) -> str:
        return os.path.join(self.data_dir, "labeled")

    @property
    def labeled_images_dir(self) -> str:
        return os.path.join(self.labeled_dir, "images")

    @property
    def labeled_labels_dir(self) -> str:
        return os.path.join(self.labeled_dir, "labels")

    @property
    def exports_dir(self) -> str:
        return os.path.join(self.data_dir, "exports")

    @property
    def state_path(self) -> str:
        return os.path.join(self.data_dir, "pipeline_state.json")

    @property
    def candidates_path(self) -> str:
        return os.path.join(self.frames_dir, ".candidates")

    @property
    def output_dir(self) -> str:
        return os.path.join(self.base_dir, "output", "approved")

    @property
    def rejected_dir(self) -> str:
        return os.path.join(self.base_dir, "output", "rejected")
```

- [ ] **Step 2: Write requirements_labeling.txt**

```
yt-dlp>=2024.0.0
transformers>=4.38.0
torch>=2.2.0
einops
timm
opencv-python
Pillow
numpy
```

- [ ] **Step 3: Verify config imports cleanly**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python -c "from config import PipelineConfig; c = PipelineConfig(base_dir='.'); print(f'OK — data_dir={c.data_dir}')"
```

Expected output: `OK — data_dir=.\data`

- [ ] **Step 4: Commit**

```bash
git add otomatik_egitim_pipeline/config.py otomatik_egitim_pipeline/requirements_labeling.txt
git commit -m "feat: add PipelineConfig + requirements for auto-labeling pipeline"
```

---

### Task 2: State Manager

**Files:**
- Create: `otomatik_egitim_pipeline/state_manager.py`

**Interfaces:**
- Consumes: `PipelineConfig` (for `state_path`)
- Produces: `StateManager` class

- [ ] **Step 1: Write state_manager.py**

```python
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
        order = ["collect", "extract", "label", "package", "import"]
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
```

- [ ] **Step 2: Verify state manager**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python -c "
from state_manager import StateManager
import tempfile, os
tmp = os.path.join(tempfile.gettempdir(), 'test_state.json')
s = StateManager(tmp)
s.set_step('collect', status='in_progress', downloaded=['a.mp4'])
assert s.get_step('collect')['downloaded'] == ['a.mp4']
assert s.get_next_step() == 'extract'
s.set_step('collect', status='done')
assert s.get_next_step() == 'extract'
os.remove(tmp)
print('OK — StateManager works')
"
```

Expected: `OK — StateManager works`

- [ ] **Step 3: Commit**

```bash
git add otomatik_egitim_pipeline/state_manager.py
git commit -m "feat: add StateManager for pipeline resume support"
```

---

### Task 3: Video Collector

**Files:**
- Create: `otomatik_egitim_pipeline/video_collector.py`

**Interfaces:**
- Consumes: `PipelineConfig`, `StateManager`
- Produces: `collect_videos(config, state) -> list[str]` — downloads videos, returns paths

- [ ] **Step 1: Write video_collector.py**

```python
"""Download gameplay videos from YouTube channels using yt-dlp."""
import subprocess
import sys
import os
import re
from config import PipelineConfig
from state_manager import StateManager


def _get_channel_url(channel: str) -> str:
    """Handle both @handle and full URL formats."""
    if channel.startswith("http"):
        return channel
    if channel.startswith("@"):
        return f"https://www.youtube.com/{channel}/videos"
    return f"https://www.youtube.com/@{channel}/videos"


def _list_video_urls(config: PipelineConfig) -> list[str]:
    """Use yt-dlp to list video URLs from configured channels, filtered by title."""
    all_urls = []
    for channel in config.channels:
        channel_url = _get_channel_url(channel)
        print(f"[VideoCollector] Scanning: {channel_url}")
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "yt_dlp",
                    "--flat-playlist",
                    "--print", "%(title)s|||%(id)s",
                    "--playlist-end", str(config.max_videos * 3),
                    channel_url,
                ],
                capture_output=True, text=True, timeout=120,
            )
            for line in result.stdout.strip().split("\n"):
                if "|||" not in line:
                    continue
                title, vid = line.split("|||", 1)
                if re.search(config.title_filter, title):
                    url = f"https://www.youtube.com/watch?v={vid}"
                    all_urls.append(url)
                    if len(all_urls) >= config.max_videos:
                        break
        except Exception as e:
            print(f"[VideoCollector] Error scanning {channel}: {e}")
    return all_urls


def collect_videos(config: PipelineConfig,
                   state: StateManager) -> list[str]:
    """Download videos. Returns list of downloaded file paths."""
    os.makedirs(config.videos_dir, exist_ok=True)

    urls = _list_video_urls(config)
    print(f"[VideoCollector] {len(urls)} videos match gameplay filter")

    if not urls:
        print("[VideoCollector] No videos found. Check channel name and title_filter.")
        return []

    downloaded = []
    failed = []

    for i, url in enumerate(urls):
        print(f"[VideoCollector] [{i + 1}/{len(urls)}] Downloading...")
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "yt_dlp",
                    "--format", config.video_quality,
                    "--output",
                    os.path.join(config.videos_dir, "%(title)s.%(ext)s"),
                    "--no-playlist",
                    "--sleep-interval", str(config.sleep_interval),
                    "--no-overwrites",
                    url,
                ],
                capture_output=False,  # show progress
                timeout=3600,
            )
            if result.returncode == 0:
                downloaded.append(url)
                print(f"[VideoCollector]   OK")
            else:
                failed.append(url)
                print(f"[VideoCollector]   FAILED (exit {result.returncode})")
        except Exception as e:
            failed.append(url)
            print(f"[VideoCollector]   FAILED: {e}")

    state.set_step("collect", status="done",
                   downloaded=downloaded, failed=failed)
    print(f"[VideoCollector] Done. {len(downloaded)} downloaded, {len(failed)} failed.")

    # Return actual file paths
    paths = []
    for fname in os.listdir(config.videos_dir):
        fpath = os.path.join(config.videos_dir, fname)
        if os.path.isfile(fpath) and os.path.getsize(fpath) > 1024:
            paths.append(fpath)
    return paths
```

- [ ] **Step 2: Verify import and basic logic**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python -c "
from video_collector import _get_channel_url, _list_video_urls
assert 'youtube.com/@MKIceAndFire/videos' in _get_channel_url('MKIceAndFire')
assert 'youtube.com/@MKIceAndFire/videos' in _get_channel_url('@MKIceAndFire')
print('OK — URL helpers work')
"
```

Expected: `OK — URL helpers work`

- [ ] **Step 3: Commit**

```bash
git add otomatik_egitim_pipeline/video_collector.py
git commit -m "feat: add video collector (yt-dlp wrapper)"
```

---

### Task 4: Frame Extractor

**Files:**
- Create: `otomatik_egitim_pipeline/frame_extractor.py`

**Interfaces:**
- Consumes: `PipelineConfig`, `StateManager`
- Produces: `extract_frames(config, state) -> list[str]` — extracts frames, returns candidate paths

- [ ] **Step 1: Write frame_extractor.py**

```python
"""Extract frames from videos with Canny edge pre-filter for subtitle candidates."""
import subprocess
import os
import sys
import cv2
import numpy as np
from config import PipelineConfig
from state_manager import StateManager


def _get_video_files(videos_dir: str) -> list[str]:
    """Return list of video file paths in directory."""
    if not os.path.isdir(videos_dir):
        return []
    exts = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
    files = []
    for fname in sorted(os.listdir(videos_dir)):
        _, ext = os.path.splitext(fname)
        if ext.lower() in exts:
            fpath = os.path.join(videos_dir, fname)
            if os.path.getsize(fpath) > 1024:
                files.append(fpath)
    return files


def _safe_video_name(video_path: str) -> str:
    """Derive a safe short name from video path."""
    base = os.path.splitext(os.path.basename(video_path))[0]
    # Keep only alphanumeric, underscore, dash; truncate to 60 chars
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in base)
    return safe[:60]


def _has_subtitle_candidate(frame: np.ndarray, config: PipelineConfig) -> bool:
    """Check if frame likely has text in subtitle region using Canny edge density."""
    h, w = frame.shape[:2]
    bottom = frame[int(h * config.subtitle_region_ratio):h, :]

    if len(bottom.shape) == 3:
        gray = cv2.cvtColor(bottom, cv2.COLOR_BGR2GRAY)
    else:
        gray = bottom

    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.count_nonzero(edges) / (edges.shape[0] * edges.shape[1])
    return edge_density > config.edge_density_threshold


def _extract_one_video(video_path: str, config: PipelineConfig) -> list[str]:
    """Extract frames from one video, return list of candidate frame paths."""
    name = _safe_video_name(video_path)
    pattern = os.path.join(config.frames_dir, f"{name}_%06d.{config.output_format}")

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"fps={config.frame_fps}",
            "-q:v", "2",
            pattern,
        ],
        capture_output=True, text=True, timeout=3600,
    )

    if result.returncode != 0:
        print(f"[FrameExtractor] FFmpeg error for {name}: {result.stderr[-200:]}")
        return []

    # Find extracted frames and filter
    candidates = []
    prefix = f"{name}_"
    for fname in sorted(os.listdir(config.frames_dir)):
        if fname.startswith(prefix) and fname.endswith(f".{config.output_format}"):
            fpath = os.path.join(config.frames_dir, fname)
            frame = cv2.imread(fpath)
            if frame is not None and _has_subtitle_candidate(frame, config):
                candidates.append(fpath)

    total = sum(1 for f in os.listdir(config.frames_dir)
                if f.startswith(prefix))
    print(f"[FrameExtractor] {name}: {total} frames -> {len(candidates)} candidates")
    return candidates


def extract_frames(config: PipelineConfig,
                   state: StateManager) -> list[str]:
    """Extract frames from all downloaded videos. Returns list of candidate paths."""
    videos = _get_video_files(config.videos_dir)
    if not videos:
        print("[FrameExtractor] No videos found. Run --collect first.")
        return []

    os.makedirs(config.frames_dir, exist_ok=True)

    all_candidates = []
    processed = state.get_step("extract").get("processed_videos", [])
    total_extracted = state.get_step("extract").get("total_frames", 0)
    total_candidates = state.get_step("extract").get("candidates", 0)

    for i, vp in enumerate(videos):
        if vp in processed:
            continue

        print(f"[FrameExtractor] [{i+1}/{len(videos)}] {os.path.basename(vp)}")
        candidates = _extract_one_video(vp, config)
        all_candidates.extend(candidates)

        # Count frames for this video
        name = _safe_video_name(vp)
        frame_count = sum(1 for f in os.listdir(config.frames_dir)
                          if f.startswith(name))
        total_extracted += frame_count
        total_candidates += len(candidates)
        processed.append(vp)

        state.set_step("extract", status="in_progress",
                       total_frames=total_extracted,
                       candidates=total_candidates,
                       processed_videos=processed)

    # Write candidate list
    with open(config.candidates_path, "w", encoding="utf-8") as f:
        for p in all_candidates:
            f.write(p + "\n")

    state.set_step("extract", status="done",
                   total_frames=total_extracted,
                   candidates=total_candidates,
                   processed_videos=processed)
    print(f"[FrameExtractor] Done. {total_extracted} frames -> {total_candidates} candidates.")
    return all_candidates
```

- [ ] **Step 2: Verify pre-filter logic**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python -c "
import numpy as np, cv2
from config import PipelineConfig
from frame_extractor import _has_subtitle_candidate, _safe_video_name
c = PipelineConfig()
# Test with blank frame (should be False)
blank = np.zeros((1080, 1920, 3), dtype=np.uint8)
assert not _has_subtitle_candidate(blank, c), 'blank frame should not be candidate'
# Test with subtitle-like frame (add white text at bottom)
text_frame = blank.copy()
cv2.putText(text_frame, 'Hello World', (600, 950), cv2.FONT_HERSHEY_SIMPLEX, 2, 255, 3)
result = _has_subtitle_candidate(text_frame, c)
print(f'Has subtitle candidate: {result}')
assert _safe_video_name('C:/videos/Red Dead 2 Gameplay.mp4') == 'Red_Dead_2_Gameplay'
print('OK — pre-filter and naming work')
"
```

Expected: `Has subtitle candidate: True` / `OK — pre-filter and naming work`

- [ ] **Step 3: Commit**

```bash
git add otomatik_egitim_pipeline/frame_extractor.py
git commit -m "feat: add frame extractor with Canny pre-filter"
```

---

### Task 5: Auto Labeler (Florence-2)

**Files:**
- Create: `otomatik_egitim_pipeline/auto_labeler.py`

**Interfaces:**
- Consumes: `PipelineConfig`, `StateManager`, candidate frame list
- Produces: `AutoLabeler` class with `process_all(frame_list, state)` — creates YOLO labels in `data/labeled/`

- [ ] **Step 1: Write auto_labeler.py**

```python
"""Florence-2 based automatic subtitle labeling."""
import os
import json
import time
import cv2
import numpy as np
import torch
from config import PipelineConfig
from state_manager import StateManager


def quad_to_yolo_bbox(quad_boxes: list, img_w: int, img_h: int) -> tuple:
    """Convert Florence-2 quad_boxes to normalized YOLO format.

    quad_boxes: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] in pixel coordinates
    Returns: (x_center, y_center, width, height) all normalized 0-1
    """
    xs = [q[0] for q in quad_boxes]
    ys = [q[1] for q in quad_boxes]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    x_center = ((x_min + x_max) / 2) / img_w
    y_center = ((y_min + y_max) / 2) / img_h
    width = (x_max - x_min) / img_w
    height = (y_max - y_min) / img_h

    return (x_center, y_center, width, height)


def passes_position_filter(bbox: tuple, img_w: int, img_h: int,
                           config: PipelineConfig) -> bool:
    """Check if bbox is in the expected subtitle area (bottom-center)."""
    x_center, y_center, width, height = bbox
    # Must be in bottom portion of screen
    if y_center < config.min_y_ratio:
        return False
    # Must be reasonably wide
    if width < config.min_width_ratio:
        return False
    return True


class AutoLabeler:
    """Florence-2 wrapper for automatic subtitle detection and labeling."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._model = None
        self._processor = None

    def load(self):
        """Lazy-load Florence-2 model (called on first use)."""
        if self._model is not None:
            return

        print("[AutoLabeler] Loading Florence-2 base (fp16)...")
        from transformers import AutoProcessor, AutoModelForCausalLM

        self._model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,
            torch_dtype=torch.float16,
            trust_remote_code=True,
        ).to(self.config.device)

        self._processor = AutoProcessor.from_pretrained(
            self.config.model_name,
            trust_remote_code=True,
        )

        print(f"[AutoLabeler] Model loaded. VRAM: ~1.5 GB")
        print(f"[AutoLabeler] Device: {self.config.device}")

    def label_frame(self, image_path: str) -> list[dict]:
        """Run Florence-2 <OCR_WITH_REGION> on a single frame.

        Returns list of dicts: [{"text": str, "bbox": (x,y,w,h)}, ...]
        Empty list if no text found.
        """
        if self._model is None:
            self.load()

        img = cv2.imread(image_path)
        if img is None:
            return []
        img_h, img_w = img.shape[:2]

        # Convert BGR to RGB for Florence-2
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        try:
            inputs = self._processor(
                text="<OCR_WITH_REGION>",
                images=img_rgb,
                return_tensors="pt",
            ).to(self.config.device)

            with torch.no_grad():
                generated_ids = self._model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=1024,
                    num_beams=1,
                    do_sample=False,
                )

            generated_text = self._processor.batch_decode(
                generated_ids, skip_special_tokens=True,
            )[0]

            # Parse JSON output
            result = json.loads(generated_text)
            regions = result.get("<OCR_WITH_REGION>", [])

            labels = []
            for region in regions:
                quad = region.get("quad_boxes", [])
                text = region.get("text", "").strip()

                if not quad or len(text) < self.config.min_text_length:
                    continue

                bbox = quad_to_yolo_bbox(quad, img_w, img_h)
                if passes_position_filter(bbox, img_w, img_h, self.config):
                    labels.append({"text": text, "bbox": bbox})

            return labels

        except json.JSONDecodeError:
            # Florence-2 sometimes returns malformed output
            return []
        except Exception as e:
            print(f"[AutoLabeler] Error on {os.path.basename(image_path)}: {e}")
            return []

    def process_all(self, frame_list: list[str], state: StateManager):
        """Process all candidate frames and write YOLO labels."""
        os.makedirs(self.config.labeled_images_dir, exist_ok=True)
        os.makedirs(self.config.labeled_labels_dir, exist_ok=True)

        total = len(frame_list)
        labeled = 0
        empty = 0
        errors = 0
        start_time = time.time()

        state.set_step("label", status="in_progress", total=total,
                       processed=0, labeled_count=0, empty_count=0,
                       error_count=0)

        for i, fpath in enumerate(frame_list):
            if i % 50 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / max(elapsed, 0.1)
                eta = (total - i - 1) / max(rate, 0.01)
                print(f"[AutoLabeler] {i+1}/{total} "
                      f"({100*(i+1)/total:.0f}%) "
                      f"rate={rate:.1f}/s eta={eta:.0f}s")

            fname = os.path.splitext(os.path.basename(fpath))[0]

            results = self.label_frame(fpath)

            if results is None or len(results) == 0:
                empty += 1
                continue

            try:
                # Copy frame image to labeled dir
                dst_img = os.path.join(
                    self.config.labeled_images_dir, f"{fname}.png",
                )
                if not os.path.exists(dst_img):
                    img = cv2.imread(fpath)
                    cv2.imwrite(dst_img, img)

                # Write YOLO label file
                dst_label = os.path.join(
                    self.config.labeled_labels_dir, f"{fname}.txt",
                )
                with open(dst_label, "w", encoding="utf-8") as f:
                    for r in results:
                        x, y, w, h = r["bbox"]
                        f.write(f"0 {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")

                labeled += 1
            except Exception as e:
                errors += 1
                print(f"[AutoLabeler] Write error {fname}: {e}")

            if i % 20 == 0:
                state.set_step("label", status="in_progress",
                               processed=i + 1, labeled_count=labeled,
                               empty_count=empty, error_count=errors)

        state.set_step("label", status="done", processed=total,
                       labeled_count=labeled, empty_count=empty,
                       error_count=errors)
        elapsed = time.time() - start_time
        print(f"[AutoLabeler] Done. {labeled} labeled, {empty} empty, "
              f"{errors} errors in {elapsed:.0f}s")
```

- [ ] **Step 2: Verify bbox conversion logic**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python -c "
from auto_labeler import quad_to_yolo_bbox, passes_position_filter
from config import PipelineConfig
# Test quad_to_yolo_bbox
bbox = quad_to_yolo_bbox([[960, 850], [1460, 850], [1460, 880], [960, 880]], 1920, 1080)
assert len(bbox) == 4
assert abs(bbox[0] - 0.630) < 0.01, f'x_center: {bbox[0]}'
assert abs(bbox[1] - 0.801) < 0.01, f'y_center: {bbox[1]}'
print('OK — bbox conversion works')

# Test position filter
c = PipelineConfig()
assert passes_position_filter(bbox, 1920, 1080, c), 'should pass'
assert not passes_position_filter((0.5, 0.1, 0.3, 0.03), 1920, 1080, c), 'too high'
print('OK — position filter works')
"
```

Expected: `OK — bbox conversion works` / `OK — position filter works`

- [ ] **Step 3: Commit**

```bash
git add otomatik_egitim_pipeline/auto_labeler.py
git commit -m "feat: add Florence-2 auto labeler"
```

---

### Task 6: Review HTML Template

**Files:**
- Create: `otomatik_egitim_pipeline/review_template.html`

**Interfaces:**
- Consumes: frame PNGs in `frames/`, YOLO labels in `labels/` (relative paths)
- Produces: Interactive review page, localStorage decisions, JSON export

- [ ] **Step 1: Write review_template.html — HTML + CSS structure**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Game Lens — Dataset Review</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
#toolbar { display: flex; align-items: center; gap: 12px; padding: 8px 16px; background: #16213e; border-bottom: 1px solid #0f3460; min-height: 48px; }
#toolbar h1 { font-size: 16px; font-weight: 600; margin-right: 16px; }
#progress { font-size: 13px; color: #a0a0b0; }
#progress span { color: #4ecca3; font-weight: 600; }
#main { display: flex; flex: 1; overflow: hidden; }
#sidebar { width: 260px; background: #16213e; overflow-y: auto; border-right: 1px solid #0f3460; padding: 8px; }
#sidebar h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #a0a0b0; padding: 8px 4px; }
.sidebar-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 4px; cursor: pointer; font-size: 12px; margin-bottom: 2px; }
.sidebar-item:hover { background: #1a1a3e; }
.sidebar-item.active { background: #0f3460; }
.sidebar-item .icon { font-size: 14px; width: 20px; text-align: center; }
.sidebar-item.approved .icon { color: #4ecca3; }
.sidebar-item.rejected .icon { color: #e74c3c; }
#viewer { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; background: #1a1a2e; position: relative; overflow: hidden; }
#image-container { position: relative; display: inline-block; max-width: 95%; max-height: 80vh; }
#frame-image { max-width: 100%; max-height: 78vh; display: block; border-radius: 4px; box-shadow: 0 4px 24px rgba(0,0,0,0.5); }
#bbox-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: auto; }
#info-bar { padding: 10px 16px; font-size: 13px; color: #a0a0b0; text-align: center; min-height: 40px; }
#info-bar .text { color: #e0e0e0; font-style: italic; }
#controls { display: flex; align-items: center; justify-content: center; gap: 12px; padding: 10px 16px; background: #16213e; border-top: 1px solid #0f3460; }
#controls button { padding: 8px 20px; border: none; border-radius: 4px; font-size: 14px; font-weight: 600; cursor: pointer; transition: background 0.15s; }
#controls button:focus { outline: 2px solid #4ecca3; outline-offset: 2px; }
.btn-prev, .btn-next { background: #0f3460; color: #e0e0e0; }
.btn-prev:hover, .btn-next:hover { background: #1a4a7a; }
.btn-approve { background: #1a6b3c; color: #fff; }
.btn-approve:hover { background: #228b4a; }
.btn-reject { background: #8b1a1a; color: #fff; }
.btn-reject:hover { background: #a52a2a; }
.btn-edit { background: #6b5a1a; color: #fff; }
.btn-edit:hover { background: #8b7a2a; }
.btn-export { background: #4ecca3; color: #1a1a2e; font-weight: 700; padding: 10px 28px; font-size: 15px; }
.btn-export:hover { background: #5dddb3; }
.shortcut { font-size: 11px; color: #606080; margin-left: 4px; }
#status { font-size: 12px; color: #a0a0b0; }
#edit-mode-indicator { display: none; position: absolute; top: 10px; right: 10px; background: #6b5a1a; color: #fff; padding: 4px 10px; border-radius: 4px; font-size: 12px; z-index: 10; }
</style>
</head>
<body>
<div id="toolbar">
  <h1>🎮 Game Lens — Dataset Review</h1>
  <div id="progress">Frame <span id="current-num">0</span> / <span id="total-num">0</span> &nbsp;|&nbsp; ✅ <span id="approved-count">0</span> &nbsp; ❌ <span id="rejected-count">0</span> &nbsp; ✏️ <span id="edited-count">0</span></div>
  <button class="btn-export" onclick="exportResults()" style="margin-left:auto" title="Export review decisions as JSON">📥 Export Decisions</button>
</div>
<div id="main">
  <div id="sidebar">
    <h3>📋 Frames</h3>
    <div id="sidebar-list"></div>
  </div>
  <div id="viewer">
    <div id="image-container">
      <img id="frame-image" src="" alt="Frame">
      <canvas id="bbox-canvas"></canvas>
      <div id="edit-mode-indicator">✏️ EDIT MODE — Drag bbox to reposition</div>
    </div>
    <div id="info-bar">
      <span id="frame-name"></span>
      <span id="bbox-count"></span>
      <span class="text" id="bbox-texts"></span>
    </div>
  </div>
</div>
<div id="controls">
  <button class="btn-prev" onclick="navigate(-1)">◀ Previous <span class="shortcut">(←)</span></button>
  <button class="btn-reject" onclick="rejectCurrent()">❌ Reject <span class="shortcut">(Del)</span></button>
  <button class="btn-edit" onclick="toggleEditMode()">✏️ Edit Bbox <span class="shortcut">(E)</span></button>
  <button class="btn-approve" onclick="approveCurrent()">✅ Approve <span class="shortcut">(Enter)</span></button>
  <button class="btn-next" onclick="navigate(1)">Next ▶ <span class="shortcut">(→)</span></button>
  <span id="status"></span>
</div>
<script>
// ── All JavaScript logic inline below ──
</script>
</body>
</html>
```

- [ ] **Step 2: Add JavaScript logic — data loading + navigation**

Replace the `<script>` comment with:

```javascript
// ── State ──
const STATE_KEY = 'gamelens_review_state';
let frames = [];           // [{name: 'frame_000001', labels: [[x,y,w,h],...], texts: ['...',...]}]
let currentIdx = 0;
let decisions = {};        // {frameName: 'approved'|'rejected'|'edited'}
let editedBboxes = {};     // {frameName: [[x,y,w,h],...]}
let isEditMode = false;

// ── Init ──
async function init() {
  // Discover frames from labels directory
  const resp = await fetch('frames.json');
  if (!resp.ok) {
    // Fallback: try to enumerate from labels
    loadFromFilesystem();
    return;
  }
  frames = await resp.json();
  loadDecisions();
  render();
}

function loadFromFilesystem() {
  // frames.json not found — this is expected when opened as file://
  // We ship a frames.json with the package (generated by review_packager.py)
  document.getElementById('status').textContent =
    'Error: frames.json not found. Make sure you extracted the full zip.';
}

function loadDecisions() {
  const saved = localStorage.getItem(STATE_KEY);
  if (saved) {
    const data = JSON.parse(saved);
    decisions = data.decisions || {};
    editedBboxes = data.editedBboxes || {};
  }
}

function saveDecisions() {
  localStorage.setItem(STATE_KEY, JSON.stringify({
    decisions, editedBboxes,
    lastUpdated: new Date().toISOString(),
  }));
  updateCounts();
}

// ── Rendering ──
function render() {
  if (frames.length === 0) return;
  const frame = frames[currentIdx];
  document.getElementById('frame-image').src = 'frames/' + frame.name + '.png';
  document.getElementById('frame-name').textContent = frame.name;
  document.getElementById('current-num').textContent = currentIdx + 1;
  document.getElementById('total-num').textContent = frames.length;

  const img = document.getElementById('frame-image');
  img.onload = function() {
    // Use natural dimensions to position canvas
    const container = document.getElementById('image-container');
    const canvas = document.getElementById('bbox-canvas');
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    drawBboxes(getCurrentBboxes(), img);
  };

  updateSidebar();
  updateCounts();
  updateStatusBadge();
}

function getCurrentBboxes() {
  const frame = frames[currentIdx];
  // Return edited version if available, otherwise original
  const name = frame.name;
  if (editedBboxes[name]) return editedBboxes[name];
  return frame.labels || [];
}

function drawBboxes(bboxes, img) {
  const canvas = document.getElementById('bbox-canvas');
  const ctx = canvas.getContext('2d');
  const scaleX = img.clientWidth / img.naturalWidth;
  const scaleY = img.clientHeight / img.naturalHeight;

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const decision = decisions[frames[currentIdx].name];
  let color = '#e74c3c'; // default red
  if (decision === 'approved') color = '#4ecca3';
  else if (decision === 'rejected') color = '#888888';

  for (const bbox of bboxes) {
    const [xc, yc, w, h] = bbox;
    const px = (xc - w / 2) * canvas.width * scaleX;
    const py = (yc - h / 2) * canvas.height * scaleY;
    const pw = w * canvas.width * scaleX;
    const ph = h * canvas.height * scaleY;

    ctx.strokeStyle = color;
    ctx.lineWidth = isEditMode ? 3 : 2;
    ctx.strokeRect(px, py, pw, ph);

    if (isEditMode) {
      // Draw corner handles
      ctx.fillStyle = '#ffcc00';
      for (const [cx, cy] of [[px, py], [px+pw, py], [px, py+ph], [px+pw, py+ph]]) {
        ctx.fillRect(cx-4, cy-4, 8, 8);
      }
    }
  }

  canvas.style.width = img.clientWidth + 'px';
  canvas.style.height = img.clientHeight + 'px';
}

function updateSidebar() {
  const list = document.getElementById('sidebar-list');
  list.innerHTML = '';
  for (let i = 0; i < frames.length; i++) {
    const f = frames[i];
    const dec = decisions[f.name];
    let icon = '⬜';
    let cls = '';
    if (dec === 'approved') { icon = '✅'; cls = 'approved'; }
    else if (dec === 'rejected') { icon = '❌'; cls = 'rejected'; }
    else if (dec === 'edited') { icon = '✏️'; cls = 'edited'; }

    const div = document.createElement('div');
    div.className = 'sidebar-item ' + cls + (i === currentIdx ? ' active' : '');
    div.innerHTML = `<span class="icon">${icon}</span>${f.name}`;
    div.onclick = () => { currentIdx = i; render(); };
    list.appendChild(div);
  }
}

function updateCounts() {
  let a = 0, r = 0, e = 0;
  for (const [_, v] of Object.entries(decisions)) {
    if (v === 'approved') a++;
    else if (v === 'rejected') r++;
    else if (v === 'edited') e++;
  }
  document.getElementById('approved-count').textContent = a;
  document.getElementById('rejected-count').textContent = r;
  document.getElementById('edited-count').textContent = e;
}

function updateStatusBadge() {
  const name = frames[currentIdx]?.name;
  const dec = decisions[name];
  const el = document.getElementById('status');
  if (!dec) { el.textContent = '⏳ Pending'; el.style.color = '#a0a0b0'; }
  else if (dec === 'approved') { el.textContent = '✅ Approved'; el.style.color = '#4ecca3'; }
  else if (dec === 'rejected') { el.textContent = '❌ Rejected'; el.style.color = '#e74c3c'; }
  else { el.textContent = '✏️ Edited'; el.style.color = '#ffcc00'; }
}

// ── Actions ──
function navigate(dir) {
  currentIdx = Math.max(0, Math.min(frames.length - 1, currentIdx + dir));
  isEditMode = false;
  document.getElementById('edit-mode-indicator').style.display = 'none';
  render();
}

function approveCurrent() {
  const name = frames[currentIdx].name;
  decisions[name] = 'approved';
  saveDecisions();
  updateStatusBadge();
  updateSidebar();
  drawBboxes(getCurrentBboxes(), document.getElementById('frame-image'));
  // Auto-advance
  if (currentIdx < frames.length - 1) {
    setTimeout(() => navigate(1), 100);
  }
}

function rejectCurrent() {
  const name = frames[currentIdx].name;
  decisions[name] = 'rejected';
  saveDecisions();
  updateStatusBadge();
  updateSidebar();
  drawBboxes(getCurrentBboxes(), document.getElementById('frame-image'));
  // Auto-advance
  if (currentIdx < frames.length - 1) {
    setTimeout(() => navigate(1), 100);
  }
}

function toggleEditMode() {
  isEditMode = !isEditMode;
  document.getElementById('edit-mode-indicator').style.display =
    isEditMode ? 'block' : 'none';
  drawBboxes(getCurrentBboxes(), document.getElementById('frame-image'));
}

// ── Bbox dragging (edit mode) ──
let dragBboxIdx = -1;
let dragStart = null;
let dragOrigBbox = null;

document.getElementById('bbox-canvas').addEventListener('mousedown', function(e) {
  if (!isEditMode) return;
  const canvas = this;
  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) / rect.width * canvas.width;
  const my = (e.clientY - rect.top) / rect.height * canvas.height;

  const bboxes = getCurrentBboxes();
  for (let i = 0; i < bboxes.length; i++) {
    const [xc, yc, w, h] = bboxes[i];
    const px = (xc - w/2) * canvas.width;
    const py = (yc - h/2) * canvas.height;
    const pw = w * canvas.width;
    const ph = h * canvas.height;
    if (mx >= px && mx <= px + pw && my >= py && my <= py + ph) {
      dragBboxIdx = i;
      dragStart = { x: mx - px, y: my - py };
      dragOrigBbox = [...bboxes[i]];
      canvas.style.cursor = 'grabbing';
      return;
    }
  }
});

document.getElementById('bbox-canvas').addEventListener('mousemove', function(e) {
  if (!isEditMode || dragBboxIdx < 0) return;
  const canvas = this;
  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) / rect.width;
  const my = (e.clientY - rect.top) / rect.height;

  const name = frames[currentIdx].name;
  if (!editedBboxes[name]) {
    editedBboxes[name] = JSON.parse(JSON.stringify(
      frames[currentIdx].labels || []
    ));
  }

  // Move bbox: update x_center, y_center based on drag delta
  // Keep within [0,1] bounds
  const bboxes = editedBboxes[name];
  const [_, __, w, h] = dragOrigBbox;
  const newXc = Math.max(w/2, Math.min(1 - w/2, mx));
  const newYc = Math.max(h/2, Math.min(1 - h/2, my));
  bboxes[dragBboxIdx] = [newXc, newYc, w, h];

  decisions[name] = 'edited';
  drawBboxes(bboxes, document.getElementById('frame-image'));
  saveDecisions();
  updateStatusBadge();
  updateSidebar();
});

document.getElementById('bbox-canvas').addEventListener('mouseup', function() {
  dragBboxIdx = -1;
  dragStart = null;
  dragOrigBbox = null;
  this.style.cursor = isEditMode ? 'grab' : 'default';
});

// ── Export ──
function exportResults() {
  const approved = [];
  const rejected = [];
  const edited = {};

  for (const frame of frames) {
    const name = frame.name;
    const dec = decisions[name];
    if (dec === 'approved') approved.push(name);
    else if (dec === 'rejected') rejected.push(name);
    else if (dec === 'edited') {
      approved.push(name); // edited frames still go to approved
      edited[name] = { bboxes: editedBboxes[name] || frame.labels };
    }
  }

  const result = {
    approved,
    rejected,
    edited,
    reviewer: prompt('Your name for the record:', '') || 'Anonymous',
    completed_at: new Date().toISOString(),
  };

  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'review_results.json';
  a.click();
  URL.revokeObjectURL(url);
  document.getElementById('status').textContent =
    '✅ Results exported! Send review_results.json back.';
}

// ── Keyboard shortcuts ──
document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT') return;
  switch (e.key) {
    case 'ArrowLeft': navigate(-1); break;
    case 'ArrowRight': navigate(1); break;
    case 'Enter': approveCurrent(); break;
    case 'Delete': rejectCurrent(); break;
    case 'e': toggleEditMode(); break;
  }
});

// ── Start ──
window.addEventListener('DOMContentLoaded', init);
window.addEventListener('resize', () => {
  const img = document.getElementById('frame-image');
  if (img.complete) drawBboxes(getCurrentBboxes(), img);
});
```

- [ ] **Step 3: Verify HTML is valid**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python -c "
with open('review_template.html', 'r', encoding='utf-8') as f:
    content = f.read()
assert '<!DOCTYPE html>' in content
assert 'frames.json' in content
assert 'localStorage' in content
assert 'review_results.json' in content
print('OK — review HTML template valid')
"
```

Expected: `OK — review HTML template valid`

- [ ] **Step 4: Commit**

```bash
git add otomatik_egitim_pipeline/review_template.html
git commit -m "feat: add review HTML template with bbox editing"
```

---

### Task 7: Review Packager

**Files:**
- Create: `otomatik_egitim_pipeline/review_packager.py`

**Interfaces:**
- Consumes: `PipelineConfig`, labeled data in `data/labeled/`, `review_template.html`
- Produces: `create_review_package(config) -> str` — creates zip, returns path

- [ ] **Step 1: Write review_packager.py**

```python
"""Package labeled frames into a review zip for non-technical reviewers."""
import os
import json
import shutil
import zipfile
from config import PipelineConfig


def _parse_yolo_label(label_path: str) -> list[list[float]]:
    """Parse YOLO label file into list of [x_center, y_center, width, height]."""
    bboxes = []
    if not os.path.exists(label_path):
        return bboxes
    with open(label_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 5:
                # class_id x y w h — ignore class_id
                bboxes.append([float(p) for p in parts[1:5]])
    return bboxes


def create_review_package(config: PipelineConfig) -> str:
    """Create a self-contained review zip package.

    Returns path to the created zip file.
    """
    images_dir = config.labeled_images_dir
    labels_dir = config.labeled_labels_dir
    template_path = os.path.join(config.base_dir, "review_template.html")

    if not os.path.isdir(images_dir):
        print("[ReviewPackager] No labeled images found. Run --label first.")
        return ""

    if not os.path.exists(template_path):
        print(f"[ReviewPackager] Template not found: {template_path}")
        return ""

    # Collect frames
    frames = []
    for fname in sorted(os.listdir(images_dir)):
        if fname.lower().endswith(('.png', '.jpg', '.jpeg')):
            name = os.path.splitext(fname)[0]
            label_file = os.path.join(labels_dir, f"{name}.txt")
            bboxes = _parse_yolo_label(label_file)
            frames.append({
                "name": name,
                "labels": bboxes,
            })

    if not frames:
        print("[ReviewPackager] No frames to package.")
        return ""

    print(f"[ReviewPackager] {len(frames)} labeled frames found.")

    # Create package directory
    os.makedirs(config.exports_dir, exist_ok=True)
    pkg_name = "review_r1"
    pkg_dir = os.path.join(config.exports_dir, pkg_name)

    if os.path.exists(pkg_dir):
        shutil.rmtree(pkg_dir)

    os.makedirs(os.path.join(pkg_dir, "frames"), exist_ok=True)
    os.makedirs(os.path.join(pkg_dir, "labels"), exist_ok=True)

    # Copy frames
    for f in frames:
        src_img = os.path.join(images_dir, f"{f['name']}.png")
        dst_img = os.path.join(pkg_dir, "frames", f"{f['name']}.png")
        if os.path.exists(src_img):
            shutil.copy2(src_img, dst_img)

    # Copy labels
    for fname in os.listdir(labels_dir):
        src = os.path.join(labels_dir, fname)
        dst = os.path.join(pkg_dir, "labels", fname)
        if os.path.isfile(src):
            shutil.copy2(src, dst)

    # Write frames.json (manifest for the HTML)
    manifest_path = os.path.join(pkg_dir, "frames.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(frames, f, ensure_ascii=False)

    # Copy and inject review template
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    html_path = os.path.join(pkg_dir, "review.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Create zip
    zip_path = os.path.join(config.exports_dir, f"{pkg_name}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(pkg_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, config.exports_dir)
                zf.write(fpath, arcname)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[ReviewPackager] Package created: {zip_path} ({size_mb:.0f} MB)")
    print(f"[ReviewPackager] ⚠️  Send this zip to your reviewer!")
    print(f"[ReviewPackager]    1. They extract the zip")
    print(f"[ReviewPackager]    2. Open review.html in browser")
    print(f"[ReviewPackager]    3. Review frames, click Export")
    print(f"[ReviewPackager]    4. Send review_results.json back to you")

    # Clean up package directory (keep only zip)
    shutil.rmtree(pkg_dir)

    return zip_path
```

- [ ] **Step 2: Verify with dummy data**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python -c "
import os, tempfile
from config import PipelineConfig
from review_packager import _parse_yolo_label

# Test label parsing
td = tempfile.mkdtemp()
lp = os.path.join(td, 'test.txt')
with open(lp, 'w') as f:
    f.write('0 0.500000 0.825000 0.260000 0.030000\n')
bboxes = _parse_yolo_label(lp)
assert len(bboxes) == 1
assert bboxes[0] == [0.5, 0.825, 0.26, 0.03]
import shutil; shutil.rmtree(td)
print('OK — label parsing works')
"
```

Expected: `OK — label parsing works`

- [ ] **Step 3: Commit**

```bash
git add otomatik_egitim_pipeline/review_packager.py
git commit -m "feat: add review packager (zip + HTML)"
```

---

### Task 8: Review Importer

**Files:**
- Create: `otomatik_egitim_pipeline/review_importer.py`

**Interfaces:**
- Consumes: `review_results.json`, `PipelineConfig`, labeled data
- Produces: YOLO dataset in `output/approved/` with train/val split and `data.yaml`

- [ ] **Step 1: Write review_importer.py**

```python
"""Import review decisions and create final YOLO dataset."""
import os
import json
import random
import shutil
import yaml
from config import PipelineConfig


def import_review_results(json_path: str, config: PipelineConfig) -> dict:
    """Import review_results.json and build YOLO dataset.

    Returns stats dict with counts.
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Review results not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    approved = set(data.get("approved", []))
    rejected = set(data.get("rejected", []))
    edited = data.get("edited", {})

    print(f"[ReviewImporter] Loading: {os.path.basename(json_path)}")
    print(f"[ReviewImporter] Approved: {len(approved)} | "
          f"Rejected: {len(rejected)} | Edited: {len(edited)}")

    # Source directories
    src_images = config.labeled_images_dir
    src_labels = config.labeled_labels_dir

    # Target directories
    train_img_dir = os.path.join(config.output_dir, "train", "images")
    train_lbl_dir = os.path.join(config.output_dir, "train", "labels")
    val_img_dir = os.path.join(config.output_dir, "val", "images")
    val_lbl_dir = os.path.join(config.output_dir, "val", "labels")
    rejected_dir = config.rejected_dir

    for d in [train_img_dir, train_lbl_dir, val_img_dir, val_lbl_dir,
              rejected_dir]:
        os.makedirs(d, exist_ok=True)

    # Process approved frames
    approved_frames = sorted(approved)
    random.seed(config.seed)
    random.shuffle(approved_frames)

    split_idx = int(len(approved_frames) * config.train_split)
    train_frames = approved_frames[:split_idx]
    val_frames = approved_frames[split_idx:]

    for split_name, frame_list in [("train", train_frames),
                                    ("val", val_frames)]:
        img_dir = train_img_dir if split_name == "train" else val_img_dir
        lbl_dir = train_lbl_dir if split_name == "train" else val_lbl_dir

        for name in frame_list:
            # Copy image
            src_img = os.path.join(src_images, f"{name}.png")
            dst_img = os.path.join(img_dir, f"{name}.png")
            if os.path.exists(src_img):
                shutil.copy2(src_img, dst_img)

            # Copy or update label
            dst_lbl = os.path.join(lbl_dir, f"{name}.txt")
            if name in edited:
                # Write edited bboxes
                bboxes = edited[name].get("bboxes",
                          edited[name].get("bbox",
                          edited[name] if isinstance(edited[name], list) else []))
                with open(dst_lbl, "w", encoding="utf-8") as f:
                    for bbox in bboxes:
                        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                            f.write(f"0 {bbox[0]:.6f} {bbox[1]:.6f} "
                                    f"{bbox[2]:.6f} {bbox[3]:.6f}\n")
            else:
                # Copy original label
                src_lbl = os.path.join(src_labels, f"{name}.txt")
                if os.path.exists(src_lbl):
                    shutil.copy2(src_lbl, dst_lbl)

    # Move rejected frames to rejected dir
    for name in rejected:
        src_img = os.path.join(src_images, f"{name}.png")
        dst_img = os.path.join(rejected_dir, f"{name}.png")
        if os.path.exists(src_img):
            shutil.copy2(src_img, dst_img)

    # Write data.yaml
    data_yaml = {
        "path": os.path.abspath(config.output_dir),
        "train": os.path.abspath(train_img_dir),
        "val": os.path.abspath(val_img_dir),
        "nc": 1,
        "names": ["s-subtittle"],
    }
    yaml_path = os.path.join(config.output_dir, "data.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data_yaml, f, default_flow_style=False)

    stats = {
        "approved": len(approved),
        "rejected": len(rejected),
        "edited": len(edited),
        "train": len(train_frames),
        "val": len(val_frames),
        "yaml_path": yaml_path,
    }

    print(f"[ReviewImporter] Train: {stats['train']} | Val: {stats['val']}")
    print(f"[ReviewImporter] data.yaml written to {yaml_path}")
    print(f"[ReviewImporter] Done. Dataset ready!")

    return stats
```

- [ ] **Step 2: Verify importer logic**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python -c "
from review_importer import import_review_results
# This will only work with real data — just verify import
print('OK — review_importer module loads cleanly')
"
```

Expected: `OK — review_importer module loads cleanly`

- [ ] **Step 3: Commit**

```bash
git add otomatik_egitim_pipeline/review_importer.py
git commit -m "feat: add review importer with train/val split"
```

---

### Task 9: Pipeline Orchestrator CLI

**Files:**
- Create: `otomatik_egitim_pipeline/pipeline.py`

**Interfaces:**
- Consumes: all other modules, CLI args
- Produces: unified pipeline entry point

- [ ] **Step 1: Write pipeline.py**

```python
#!/usr/bin/env python
"""Game Lens Auto-Labeling Pipeline — CLI entry point.

Usage:
    python pipeline.py --full --max-videos 50
    python pipeline.py --collect --channel MKIceAndFire
    python pipeline.py --extract
    python pipeline.py --label
    python pipeline.py --package
    python pipeline.py --import review_results.json
    python pipeline.py --resume
    python pipeline.py --status
"""
import sys
import os
import argparse

# Ensure pipeline directory is the working context
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from config import PipelineConfig
from state_manager import StateManager


def cmd_collect(config: PipelineConfig, state: StateManager):
    from video_collector import collect_videos
    collect_videos(config, state)


def cmd_extract(config: PipelineConfig, state: StateManager):
    from frame_extractor import extract_frames
    extract_frames(config, state)


def cmd_label(config: PipelineConfig, state: StateManager):
    from auto_labeler import AutoLabeler

    # Get candidate list
    candidates_path = config.candidates_path
    if not os.path.exists(candidates_path):
        # Try to get all frames
        frames_dir = config.frames_dir
        if os.path.isdir(frames_dir):
            frame_list = sorted([
                os.path.join(frames_dir, f)
                for f in os.listdir(frames_dir)
                if f.lower().endswith(('.png', '.jpg'))
            ])
        else:
            print("[Pipeline] No frames found. Run --extract first.")
            return
    else:
        with open(candidates_path, "r", encoding="utf-8") as f:
            frame_list = [line.strip() for line in f if line.strip()]

    if not frame_list:
        print("[Pipeline] No candidate frames. Run --extract first.")
        return

    labeler = AutoLabeler(config)
    labeler.process_all(frame_list, state)


def cmd_package(config: PipelineConfig, state: StateManager):
    from review_packager import create_review_package
    zip_path = create_review_package(config)
    if zip_path:
        state.set_step("package", status="done", path=zip_path)
        print(f"\n{'='*60}")
        print(f"Next: Send {os.path.basename(zip_path)} to reviewer")
        print(f"After review: python pipeline.py --import review_results.json")
        print(f"{'='*60}")


def cmd_import(config: PipelineConfig, state: StateManager, json_path: str):
    from review_importer import import_review_results
    stats = import_review_results(json_path, config)
    state.set_step("import", status="done",
                   approved=stats["approved"],
                   rejected=stats["rejected"],
                   edited=stats["edited"])


def cmd_status(config: PipelineConfig, state: StateManager):
    """Print pipeline status."""
    s = state.stats
    print("\nPipeline Status:")
    print("-" * 50)
    for step, data in s.items():
        status = data.get("status", "pending")
        icon = {"done": "✅", "in_progress": "🔄", "pending": "⏳"}.get(status, "❓")
        extra = ""
        if step == "collect":
            extra = f" ({len(data.get('downloaded', []))} downloaded)"
        elif step == "extract":
            extra = f" ({data.get('candidates', 0)} candidates)"
        elif step == "label":
            extra = f" ({data.get('labeled_count', 0)} labeled)"
        elif step == "import":
            extra = f" ({data.get('approved', 0)} approved)"
        print(f"  {icon} {step}: {status}{extra}")
    print()


def cmd_full(config: PipelineConfig, state: StateManager):
    """Run complete pipeline end-to-end."""
    steps = [
        ("collect", lambda: cmd_collect(config, state)),
        ("extract", lambda: cmd_extract(config, state)),
        ("label", lambda: cmd_label(config, state)),
        ("package", lambda: cmd_package(config, state)),
    ]
    for name, fn in steps:
        if state.is_step_done(name):
            print(f"[Pipeline] Step '{name}' already done, skipping.")
            continue
        print(f"\n{'='*60}")
        print(f"[Pipeline] Running: {name}")
        print(f"{'='*60}")
        fn()

    print(f"\n{'='*60}")
    print("[Pipeline] Full pipeline complete!")
    print(f"Next: Send review package to reviewer")
    print(f"After review: python pipeline.py --import review_results.json")
    print(f"{'='*60}")


def cmd_resume(config: PipelineConfig, state: StateManager):
    """Resume from last incomplete step."""
    next_step = state.get_next_step()
    if next_step is None:
        print("[Pipeline] All steps complete!")
        cmd_status(config, state)
        return

    print(f"[Pipeline] Resuming from: {next_step}")
    step_map = {
        "collect": lambda: cmd_collect(config, state),
        "extract": lambda: cmd_extract(config, state),
        "label": lambda: cmd_label(config, state),
        "package": lambda: cmd_package(config, state),
    }
    if next_step in step_map:
        step_map[next_step]()


def main():
    parser = argparse.ArgumentParser(
        description="Game Lens — Auto-Labeling Pipeline",
    )
    parser.add_argument("--full", action="store_true",
                        help="Run complete pipeline")
    parser.add_argument("--collect", action="store_true",
                        help="Download videos from YouTube")
    parser.add_argument("--channel", type=str, default="MKIceAndFire",
                        help="YouTube channel (@handle or URL)")
    parser.add_argument("--max-videos", type=int, default=50,
                        help="Max videos to download")
    parser.add_argument("--extract", action="store_true",
                        help="Extract frames from videos")
    parser.add_argument("--label", action="store_true",
                        help="Label frames with Florence-2")
    parser.add_argument("--package", action="store_true",
                        help="Create review zip package")
    parser.add_argument("--import", type=str, dest="import_path",
                        help="Import review_results.json")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last incomplete step")
    parser.add_argument("--status", action="store_true",
                        help="Show pipeline status")

    args = parser.parse_args()

    config = PipelineConfig(base_dir=BASE_DIR)

    # CLI overrides
    if args.channel:
        config.channels = [args.channel]
    if args.max_videos:
        config.max_videos = args.max_videos

    state = StateManager(config.state_path)

    if args.status:
        cmd_status(config, state)
    elif args.full:
        cmd_full(config, state)
    elif args.collect:
        cmd_collect(config, state)
    elif args.extract:
        cmd_extract(config, state)
    elif args.label:
        cmd_label(config, state)
    elif args.package:
        cmd_package(config, state)
    elif args.import_path:
        cmd_import(config, state, args.import_path)
    elif args.resume:
        cmd_resume(config, state)
    else:
        parser.print_help()
        print("\nTip: Use --full to run the complete pipeline.")
        print("     Use --status to see current progress.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI help**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python pipeline.py --help
```

Expected: Full help text with all options listed

- [ ] **Step 3: Test --status on fresh state**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python pipeline.py --status
```

Expected: All steps showing ⏳ pending

- [ ] **Step 4: Commit**

```bash
git add otomatik_egitim_pipeline/pipeline.py
git commit -m "feat: add pipeline orchestrator CLI"
```

---

### Task 10: Integration Test

**Files:**
- Create: `otomatik_egitim_pipeline/test_pipeline.py`

**Interfaces:**
- Consumes: All modules
- Produces: Integration test with synthetic data

- [ ] **Step 1: Write integration test**

```python
"""Integration test for the auto-labeling pipeline.

Tests each module independently with minimal/synthetic data.
Does NOT require GPU or internet — uses mock data.
"""
import os
import sys
import json
import tempfile
import shutil
import cv2
import numpy as np

# Setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def setup_test_env():
    """Create a minimal test environment with synthetic data."""
    tmp = tempfile.mkdtemp(prefix="gamelens_test_")
    os.chdir(BASE_DIR)  # ensure imports work

    from config import PipelineConfig
    config = PipelineConfig(base_dir=tmp)
    config.max_videos = 1
    config.batch_size = 1

    # Override dirs to use tmp
    for attr in ["data_dir", "videos_dir", "frames_dir", "labeled_dir",
                 "labeled_images_dir", "labeled_labels_dir", "exports_dir",
                 "output_dir", "rejected_dir"]:
        d = getattr(config, attr)
        os.makedirs(d, exist_ok=True)

    return tmp, config


def create_synthetic_frame(path: str, with_text: bool = True):
    """Create a 1920x1080 test frame, optionally with subtitle text."""
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    if with_text:
        cv2.putText(img, "Hello World Test Subtitle",
                    (600, 920), cv2.FONT_HERSHEY_SIMPLEX,
                    1.5, (255, 255, 255), 3)
    cv2.imwrite(path, img)
    return path


def create_label_file(path: str):
    """Create a YOLO label file with test bbox."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("0 0.500000 0.825000 0.260000 0.030000\n")


def create_review_json(path: str, approved: list, rejected: list):
    """Create a mock review_results.json."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "approved": approved,
            "rejected": rejected,
            "edited": {},
            "reviewer": "Test",
            "completed_at": "2026-07-11T00:00:00",
        }, f)


def test_config():
    """Test PipelineConfig properties."""
    from config import PipelineConfig
    c = PipelineConfig(base_dir="/test")
    assert c.data_dir == "/test/data"
    assert c.videos_dir == "/test/data/videos"
    assert c.train_split == 0.8
    assert c.seed == 42
    print("  ✓ PipelineConfig")


def test_state_manager():
    """Test StateManager CRUD operations."""
    from state_manager import StateManager
    tmp = tempfile.mktemp(suffix=".json")
    try:
        s = StateManager(tmp)
        assert s.get_step("collect")["status"] == "pending"
        s.set_step("collect", status="in_progress", downloaded=["a.mp4"])
        assert s.get_step("collect")["downloaded"] == ["a.mp4"]
        assert s.get_next_step() == "extract"
        s.set_step("collect", status="done")
        assert s.get_next_step() == "extract"
        assert s.is_step_done("collect")
        print("  ✓ StateManager")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def test_bbox_conversion():
    """Test quad_to_yolo_bbox conversion."""
    from auto_labeler import quad_to_yolo_bbox, passes_position_filter
    from config import PipelineConfig

    # Standard subtitle position
    bbox = quad_to_yolo_bbox(
        [[960, 850], [1460, 850], [1460, 880], [960, 880]],
        1920, 1080,
    )
    assert abs(bbox[0] - 0.630) < 0.01
    assert abs(bbox[1] - 0.801) < 0.01

    c = PipelineConfig()
    assert passes_position_filter(bbox, 1920, 1080, c)
    # Top of screen should fail
    assert not passes_position_filter((0.5, 0.1, 0.3, 0.03), 1920, 1080, c)
    print("  ✓ Bbox conversion")


def test_prefilter():
    """Test Canny edge pre-filter."""
    from frame_extractor import _has_subtitle_candidate, _safe_video_name
    from config import PipelineConfig
    c = PipelineConfig()

    # Blank frame
    blank = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert not _has_subtitle_candidate(blank, c)

    # Frame with text at bottom
    text_frame = blank.copy()
    cv2.putText(text_frame, "Hello World", (600, 950),
                cv2.FONT_HERSHEY_SIMPLEX, 2, 255, 3)
    assert _has_subtitle_candidate(text_frame, c)

    # Safe name conversion
    name = _safe_video_name("C:/test/Red Dead 2 Gameplay!.mp4")
    assert "Red_Dead_2_Gameplay_" in name
    print("  ✓ Pre-filter")


def test_label_parsing():
    """Test YOLO label file parsing."""
    from review_packager import _parse_yolo_label
    tmpd = tempfile.mkdtemp()
    try:
        lp = os.path.join(tmpd, "test.txt")
        with open(lp, "w") as f:
            f.write("0 0.500000 0.825000 0.260000 0.030000\n")
        bboxes = _parse_yolo_label(lp)
        assert len(bboxes) == 1
        assert bboxes[0] == [0.5, 0.825, 0.26, 0.03]
        print("  ✓ Label parsing")
    finally:
        shutil.rmtree(tmpd)


def test_review_importer():
    """Test review importer with synthetic data."""
    from review_importer import import_review_results
    from config import PipelineConfig

    tmpd = tempfile.mkdtemp()
    try:
        config = PipelineConfig(base_dir=tmpd)
        for d in [config.labeled_images_dir, config.labeled_labels_dir]:
            os.makedirs(d, exist_ok=True)

        # Create synthetic labeled data
        for name in ["frame_001", "frame_002", "frame_003",
                      "frame_004", "frame_005"]:
            create_synthetic_frame(
                os.path.join(config.labeled_images_dir, f"{name}.png"),
            )
            create_label_file(
                os.path.join(config.labeled_labels_dir, f"{name}.txt"),
            )

        # Create review results
        rj = os.path.join(tmpd, "review_results.json")
        create_review_json(rj,
                           approved=["frame_001", "frame_002", "frame_003",
                                      "frame_004"],
                           rejected=["frame_005"])

        stats = import_review_results(rj, config)

        assert stats["approved"] == 4
        assert stats["rejected"] == 1
        assert stats["train"] + stats["val"] == 4

        # Check data.yaml
        yaml_path = config.output_dir + "/data.yaml"
        assert os.path.exists(yaml_path)

        # Check train/val split
        train_imgs = os.listdir(config.output_dir + "/train/images")
        val_imgs = os.listdir(config.output_dir + "/val/images")
        assert len(train_imgs) + len(val_imgs) == 4

        # Check rejected
        rejected_imgs = os.listdir(config.rejected_dir)
        assert len(rejected_imgs) == 1

        print("  ✓ Review importer")
    finally:
        shutil.rmtree(tmpd)


def test_packager():
    """Test review packager with synthetic labeled data."""
    from review_packager import create_review_package
    from config import PipelineConfig

    tmpd = tempfile.mkdtemp()
    try:
        config = PipelineConfig(base_dir=tmpd)
        for d in [config.labeled_images_dir, config.labeled_labels_dir,
                  config.exports_dir]:
            os.makedirs(d, exist_ok=True)

        # Need a review_template.html
        template = os.path.join(tmpd, "review_template.html")
        with open(template, "w", encoding="utf-8") as f:
            f.write("<!DOCTYPE html><html></html>")

        # Create synthetic frames
        for i in range(3):
            name = f"frame_{i:03d}"
            create_synthetic_frame(
                os.path.join(config.labeled_images_dir, f"{name}.png"),
            )
            create_label_file(
                os.path.join(config.labeled_labels_dir, f"{name}.txt"),
            )

        zip_path = create_review_package(config)
        assert os.path.exists(zip_path)
        assert zip_path.endswith(".zip")
        print(f"  ✓ Packager ({os.path.getsize(zip_path)} bytes)")
    finally:
        shutil.rmtree(tmpd)


def test_review_html_exists():
    """Test that review_template.html exists and is valid."""
    template = os.path.join(BASE_DIR, "review_template.html")
    assert os.path.exists(template), f"Missing: {template}"
    with open(template, "r", encoding="utf-8") as f:
        content = f.read()
    assert "<!DOCTYPE html>" in content
    assert "frames.json" in content
    assert "localStorage" in content
    assert "review_results.json" in content
    print("  ✓ Review HTML template")


if __name__ == "__main__":
    print("Auto-Labeling Pipeline — Integration Tests\n")
    tests = [
        test_config,
        test_state_manager,
        test_bbox_conversion,
        test_prefilter,
        test_label_parsing,
        test_review_importer,
        test_packager,
        test_review_html_exists,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    if failed:
        print(f"FAILED: {failed}/{len(tests)} tests failed")
        sys.exit(1)
    else:
        print(f"PASSED: {len(tests)}/{len(tests)} tests passed")
        sys.exit(0)
```

- [ ] **Step 2: Run integration tests**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python test_pipeline.py
```

Expected: All 8 tests pass

- [ ] **Step 3: Commit**

```bash
git add otomatik_egitim_pipeline/test_pipeline.py
git commit -m "test: add integration tests for auto-labeling pipeline"
```

---

### Task 11: Final Verification & .gitignore

**Files:**
- Modify: `.gitignore` (project root)

- [ ] **Step 1: Add pipeline data dirs to .gitignore**

```bash
cd D:\gammasoftware\GameLens
```

Append to `.gitignore`:
```
# Auto-labeling pipeline runtime data
otomatik_egitim_pipeline/data/
otomatik_egitim_pipeline/output/
```

- [ ] **Step 2: Verify all modules import cleanly**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python -c "
from config import PipelineConfig
from state_manager import StateManager
from video_collector import collect_videos
from frame_extractor import extract_frames
from review_packager import create_review_package
from review_importer import import_review_results
print('All modules import OK')
"
```

- [ ] **Step 3: Verify final file structure**

```bash
ls -la D:/gammasoftware/GameLens/otomatik_egitim_pipeline/
```

Expected: 10 Python files + 1 HTML template + 1 requirements file

- [ ] **Step 4: Run full test suite one final time**

```bash
cd D:\gammasoftware\GameLens\otomatik_egitim_pipeline
python test_pipeline.py
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore otomatik_egitim_pipeline/
git commit -m "chore: add .gitignore entries for pipeline data dirs"
```
