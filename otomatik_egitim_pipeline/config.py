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
    subtitle_region_ratio: float = 0.82  # bottom 18% of screen

    # ── Florence-2 ──
    model_name: str = "microsoft/Florence-2-base"
    confidence_threshold: float = 0.6
    device: str = "cuda"
    batch_size: int = 4

    # ── Position filter ──
    min_y_ratio: float = 0.82         # bbox must be in bottom 18% (subtitle area)
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
