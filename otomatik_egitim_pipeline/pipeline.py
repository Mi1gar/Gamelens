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


def cmd_collect(config: PipelineConfig, state: StateManager,
                urls: list[str] | None = None):
    if urls:
        from video_collector import collect_from_urls
        collect_from_urls(config, state, urls)
    else:
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


def cmd_classify(config: PipelineConfig, state: StateManager):
    from qwen_classifier import run_classification
    run_classification(config, state)
    state.set_step("classify", status="done")


def cmd_filter(config: PipelineConfig, state: StateManager):
    from text_filter import run_text_filter
    run_text_filter(config)
    state.set_step("filter", status="done")


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
        icon = {"done": "[OK]", "in_progress": "[..]", "pending": "[--]"}.get(status, "[??]")
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
        ("classify", lambda: cmd_classify(config, state)),
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
        "classify": lambda: cmd_classify(config, state),
        "package": lambda: cmd_package(config, state),
    }
    if next_step in step_map:
        step_map[next_step]()


def main():
    parser = argparse.ArgumentParser(
        description="Game Lens - Auto-Labeling Pipeline",
    )
    parser.add_argument("--full", action="store_true",
                        help="Run complete pipeline")
    parser.add_argument("--collect", action="store_true",
                        help="Download videos from YouTube")
    parser.add_argument("--channel", type=str, default=None,
                        help="YouTube channel (@handle or URL)")
    parser.add_argument("--max-videos", type=int, default=50,
                        help="Max videos to download")
    parser.add_argument("--urls", type=str, default=None,
                        help="Text file with video URLs (one per line)")
    parser.add_argument("--extract", action="store_true",
                        help="Extract frames from videos")
    parser.add_argument("--label", action="store_true",
                        help="Label frames with Florence-2")
    parser.add_argument("--filter", action="store_true",
                        help="Remove OCR noise texts (heuristic)")
    parser.add_argument("--classify", action="store_true",
                        help="Verify labels with Qwen2-VL (smart filter)")
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

    # Load URLs from file if provided
    url_list = None
    if args.urls:
        with open(args.urls, "r", encoding="utf-8") as f:
            url_list = [line.strip() for line in f
                        if line.strip() and not line.strip().startswith("#")]

    state = StateManager(config.state_path)

    if args.status:
        cmd_status(config, state)
    elif args.full:
        cmd_full(config, state)
    elif args.collect:
        cmd_collect(config, state, urls=url_list)
    elif args.extract:
        cmd_extract(config, state)
    elif args.label:
        cmd_label(config, state)
    elif args.classify:
        cmd_classify(config, state)
    elif args.filter:
        cmd_filter(config, state)
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
