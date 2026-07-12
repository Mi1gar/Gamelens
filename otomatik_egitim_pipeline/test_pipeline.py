"""Integration test for the auto-labeling pipeline.

Tests each module independently with minimal/synthetic data.
Does NOT require GPU or internet -- uses mock data.
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
    # Use normpath for Windows-friendly comparison
    assert os.path.normpath(c.data_dir) == os.path.normpath("/test/data")
    assert os.path.normpath(c.videos_dir) == os.path.normpath("/test/data/videos")
    assert c.train_split == 0.8
    assert c.seed == 42
    print("  [PASS] PipelineConfig")


def test_state_manager():
    """Test StateManager CRUD operations."""
    from state_manager import StateManager
    tmp = tempfile.mktemp(suffix=".json")
    try:
        s = StateManager(tmp)
        # Initial state -- all steps pending, first one is "collect"
        assert s.get_step("collect")["status"] == "pending"
        assert s.get_next_step() == "collect"

        # Set in_progress -- get_next_step still returns "collect" (not done yet)
        s.set_step("collect", status="in_progress", downloaded=["a.mp4"])
        assert s.get_step("collect")["downloaded"] == ["a.mp4"]
        assert s.get_next_step() == "collect"
        assert not s.is_step_done("collect")

        # Mark done -- next step advances to "extract"
        s.set_step("collect", status="done")
        assert s.is_step_done("collect")
        assert s.get_next_step() == "extract"
        print("  [PASS] StateManager")
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
    print("  [PASS] Bbox conversion")


def test_prefilter():
    """Test Canny edge pre-filter."""
    from frame_extractor import _has_subtitle_candidate, _safe_video_name
    from config import PipelineConfig
    c = PipelineConfig()
    # Lower threshold for synthetic test frames (real subtitles produce
    # higher edge density than a single putText call)
    c.edge_density_threshold = 0.001

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
    print("  [PASS] Pre-filter")


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
        print("  [PASS] Label parsing")
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
        yaml_path = os.path.join(config.output_dir, "data.yaml")
        assert os.path.exists(yaml_path)

        # Check train/val split
        train_img_dir = os.path.join(config.output_dir, "train", "images")
        val_img_dir = os.path.join(config.output_dir, "val", "images")
        train_imgs = os.listdir(train_img_dir)
        val_imgs = os.listdir(val_img_dir)
        assert len(train_imgs) + len(val_imgs) == 4

        # Check rejected
        rejected_imgs = os.listdir(config.rejected_dir)
        assert len(rejected_imgs) == 1

        print("  [PASS] Review importer")
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
        print(f"  [PASS] Packager ({os.path.getsize(zip_path)} bytes)")
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
    print("  [PASS] Review HTML template")


if __name__ == "__main__":
    print("Auto-Labeling Pipeline -- Integration Tests\n")
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
            print(f"  [FAIL] {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    if failed:
        print(f"FAILED: {failed}/{len(tests)} tests failed")
        sys.exit(1)
    else:
        print(f"PASSED: {len(tests)}/{len(tests)} tests passed")
        sys.exit(0)
