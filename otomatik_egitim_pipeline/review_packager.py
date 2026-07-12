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
    # Load recognized texts (for review display)
    texts_path = os.path.join(labels_dir, "texts.json")
    texts_map = {}
    if os.path.exists(texts_path):
        with open(texts_path, "r", encoding="utf-8") as f:
            texts_map = json.load(f)

    frames = []
    for fname in sorted(os.listdir(images_dir)):
        if fname.lower().endswith(('.png', '.jpg', '.jpeg')):
            name = os.path.splitext(fname)[0]
            label_file = os.path.join(labels_dir, f"{name}.txt")
            bboxes = _parse_yolo_label(label_file)
            frame_entry = {
                "name": name,
                "labels": bboxes,
            }
            # Include recognized texts if available
            if name in texts_map:
                frame_entry["texts"] = texts_map[name]
            frames.append(frame_entry)

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

    # Read template and inject frames data directly (no fetch() — works with file://)
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    frames_json = json.dumps(frames, ensure_ascii=False)
    html = html.replace("__FRAMES_DATA__", frames_json)
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
    print(f"[ReviewPackager] >> Send this zip to your reviewer!")
    print(f"[ReviewPackager]    1. They extract the zip")
    print(f"[ReviewPackager]    2. Open review.html in browser")
    print(f"[ReviewPackager]    3. Review frames, click Export")
    print(f"[ReviewPackager]    4. Send review_results.json back to you")

    # Clean up package directory (keep only zip)
    shutil.rmtree(pkg_dir)

    return zip_path
