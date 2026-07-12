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

    with open(json_path, "r", encoding="utf-8-sig") as f:
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
