"""Extract frames from videos with Canny edge pre-filter for subtitle candidates."""
import subprocess
import os
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
    if os.path.exists(config.candidates_path):
        with open(config.candidates_path, "r", encoding="utf-8") as f:
            all_candidates = [line.strip() for line in f if line.strip()]
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
