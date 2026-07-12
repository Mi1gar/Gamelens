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


def collect_from_urls(config: PipelineConfig,
                      state: StateManager,
                      urls: list[str]) -> list[str]:
    """Download videos from a list of direct URLs (no channel scanning).

    Args:
        config: PipelineConfig
        state: StateManager
        urls: List of video URLs (YouTube, etc.)

    Returns list of downloaded file paths.
    """
    os.makedirs(config.videos_dir, exist_ok=True)

    if not urls:
        print("[VideoCollector] No URLs provided.")
        return []

    print(f"[VideoCollector] {len(urls)} direct URL(s) to download.")

    downloaded = []
    failed = []

    for i, url in enumerate(urls):
        url = url.strip()
        if not url or url.startswith("#"):  # skip empty lines and comments
            continue
        print(f"[VideoCollector] [{i + 1}/{len(urls)}] {url[:80]}...")
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
                capture_output=False,
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

    paths = []
    for fname in os.listdir(config.videos_dir):
        fpath = os.path.join(config.videos_dir, fname)
        if os.path.isfile(fpath) and os.path.getsize(fpath) > 1024:
            paths.append(fpath)
    return paths
