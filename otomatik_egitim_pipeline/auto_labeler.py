"""Florence-2 based automatic subtitle labeling."""
import os
import json
import re
import time
import shutil
import cv2
import numpy as np
import torch
from config import PipelineConfig
from state_manager import StateManager


def quad_to_yolo_bbox(quad_boxes: list, img_w: int, img_h: int) -> tuple:
    """Convert Florence-2 quad_boxes to normalized YOLO format.

    Accepts two formats:
    - Nested: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    - Flat:   [x1, y1, x2, y2, x3, y3, x4, y4]
    Returns: (x_center, y_center, width, height) all normalized 0-1
    """
    if len(quad_boxes) == 8 and not isinstance(quad_boxes[0], (list, tuple)):
        # Flat format: [x1, y1, x2, y2, x3, y3, x4, y4]
        xs = [quad_boxes[0], quad_boxes[2], quad_boxes[4], quad_boxes[6]]
        ys = [quad_boxes[1], quad_boxes[3], quad_boxes[5], quad_boxes[7]]
    else:
        # Nested format: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
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
    # Reject right-edge watermarks (entire box in right 18% of screen)
    x1 = x_center - width / 2
    if x1 > 0.82:
        return False
    return True


def is_credit_or_noise(text: str) -> bool:
    """Filter out credit lines, timestamps, and other non-subtitle text."""
    t = text.strip()
    # All-caps multi-word = credit line
    if t.isupper() and len(t.split()) >= 2:
        return True
    # Timestamps, version numbers, scores
    if re.match(r'^[\d\s\.\-\/:,]+$', t) and len(t) >= 6:
        return True
    # Credit keywords
    credit_kw = ['director', 'producer', 'artist', 'designer', 'engineer',
                 'programmer', 'manager', 'supervisor', 'technician',
                 'lead', 'principal', 'associate', 'animation', 'environment',
                 'cutscene', 'art director', 'technical']
    t_lower = t.lower()
    if any(kw in t_lower for kw in credit_kw) and len(t.split()) >= 2:
        return True
    return False


def merge_subtitle_bboxes(labels: list[dict], img_w: int, img_h: int) -> list[dict]:
    """Merge vertically-close bboxes that are part of the same multi-line subtitle.

    Two bboxes are merged if they overlap horizontally and are within
    ~5% of screen height vertically — indicating subtitle lines stacked together.
    """
    if len(labels) <= 1:
        return labels

    # Convert to (x1, y1, x2, y2) pixel coords for easier overlap calculation
    boxes = []
    for lb in labels:
        xc, yc, w, h = lb["bbox"]
        x1 = (xc - w / 2) * img_w
        y1 = (yc - h / 2) * img_h
        x2 = (xc + w / 2) * img_w
        y2 = (yc + h / 2) * img_h
        boxes.append([x1, y1, x2, y2, lb])

    max_vert_gap = img_h * 0.05  # 5% of screen height

    merged = []
    used = set()
    for i, b1 in enumerate(boxes):
        if i in used:
            continue
        x1, y1, x2, y2, lb1 = b1
        for j, b2 in enumerate(boxes):
            if j <= i or j in used:
                continue
            ox1, oy1, ox2, oy2, lb2 = b2
            # Check horizontal overlap
            h_overlap = max(0, min(x2, ox2) - max(x1, ox1))
            h_span = min(x2 - x1, ox2 - ox1)
            if h_span > 0 and h_overlap / h_span > 0.3:
                # Check vertical gap
                vert_gap = min(abs(y1 - oy2), abs(oy1 - y2))
                if vert_gap < max_vert_gap:
                    # Merge: union of both bboxes
                    mx1, my1 = min(x1, ox1), min(y1, oy1)
                    mx2, my2 = max(x2, ox2), max(y2, oy2)
                    mw = mx2 - mx1
                    mh = my2 - my1
                    mxc = (mx1 + mx2) / 2 / img_w
                    myc = (my1 + my2) / 2 / img_h
                    mw_n = mw / img_w
                    mh_n = mh / img_h
                    merged_text = lb1["text"] + " " + lb2["text"]
                    lb1 = {
                        "text": merged_text,
                        "bbox": (mxc, myc, mw_n, mh_n),
                    }
                    # Update box coordinates for further merging
                    x1, y1 = mx1, my1
                    x2, y2 = mx2, my2
                    used.add(j)
        merged.append(lb1)
        used.add(i)
    return merged


class AutoLabeler:
    """Florence-2 wrapper for automatic subtitle detection and labeling."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._model = None
        self._processor = None

    def unload(self):
        """Free all GPU memory."""
        if self._model is not None:
            del self._model
            del self._processor
            self._model = None
            self._processor = None
            import gc
            gc.collect()
            if hasattr(torch, 'cuda') and torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            print("[AutoLabeler] Model unloaded, VRAM freed.")

    def load(self):
        """Lazy-load Florence-2 model (called on first use)."""
        if self._model is not None:
            return

        print("[AutoLabeler] Loading Florence-2 base (fp16)...")
        from transformers import AutoProcessor, AutoModelForCausalLM

        self._model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,
            dtype=torch.float16,
            trust_remote_code=True,
            attn_implementation="eager",
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
            inputs["pixel_values"] = inputs["pixel_values"].to(dtype=torch.float16)

            with torch.no_grad():
                generated_ids = self._model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=1024,
                    num_beams=1,
                    do_sample=False,
                    use_cache=False,
                )

            # Use Florence-2 post_process_generation for structured output
            generated_text = self._processor.batch_decode(
                generated_ids, skip_special_tokens=False,
            )[0]
            result = self._processor.post_process_generation(
                generated_text,
                task="<OCR_WITH_REGION>",
                image_size=(img_w, img_h),
            )
            regions_data = result.get("<OCR_WITH_REGION>", {})

            # Handle two possible output formats from post_process_generation:
            # v1: list of dicts [{"quad_boxes": [...], "text": "..."}, ...]
            # v2: dict {"quad_boxes": [[...],...], "labels": ["...",...]}
            if isinstance(regions_data, list):
                quad_list = [r.get("quad_boxes", []) for r in regions_data]
                text_list = [r.get("text", "").strip() for r in regions_data]
            elif isinstance(regions_data, dict):
                quad_list = regions_data.get("quad_boxes", [])
                text_list = regions_data.get("labels", [])
            else:
                return []

            labels = []
            for quad, text in zip(quad_list, text_list):
                if not quad or not isinstance(text, str):
                    continue
                # Strip Florence-2 special tokens and whitespace
                text = text.replace("</s>", "").replace("<s>", "").strip()
                if len(text) < self.config.min_text_length:
                    continue
                if is_credit_or_noise(text):
                    continue

                bbox = quad_to_yolo_bbox(quad, img_w, img_h)
                if not passes_position_filter(bbox, img_w, img_h, self.config):
                    continue

                # Filter by confidence if available
                score = 1.0  # Florence-2 doesn't always provide scores
                if score < self.config.confidence_threshold:
                    continue

                labels.append({"text": text, "bbox": bbox})

            # Merge multi-line subtitles into single bboxes
            labels = merge_subtitle_bboxes(labels, img_w, img_h)

            del inputs, generated_ids
            return labels

        except json.JSONDecodeError:
            return []
        except Exception as e:
            print(f"[AutoLabeler] Error on {os.path.basename(image_path)}: {e}")
            return []

    def process_all(self, frame_list: list[str], state: StateManager):
        """Process all candidate frames and write YOLO labels."""
        os.makedirs(self.config.labeled_images_dir, exist_ok=True)
        os.makedirs(self.config.labeled_labels_dir, exist_ok=True)

        total = len(frame_list)
        start_time = time.time()
        texts_map: dict[str, list[str]] = {}  # frame_name -> list of texts

        # Resume: load already-labeled frames
        already_labeled: set[str] = set()
        texts_path = os.path.join(self.config.labeled_labels_dir, "texts.json")
        if os.path.exists(texts_path):
            with open(texts_path, "r", encoding="utf-8") as f:
                texts_map = json.load(f)
            already_labeled = set(texts_map.keys())

        for fname in os.listdir(self.config.labeled_labels_dir):
            if fname.endswith(".txt") and fname != "texts.json":
                already_labeled.add(os.path.splitext(fname)[0])

        labeled = len(already_labeled)
        empty = state.get_step("label").get("empty_count", 0)
        errors = state.get_step("label").get("error_count", 0)
        print(f"[AutoLabeler] Resume: {labeled} already labeled, "
              f"{total - labeled} remaining")

        state.set_step("label", status="in_progress", total=total,
                       processed=labeled, labeled_count=labeled,
                       empty_count=empty, error_count=errors)

        # TODO(v2): implement batched Florence-2 inference using self.config.batch_size
        processed_new = 0
        total_new = total - labeled  # frames that actually need processing
        print(f"[AutoLabeler] {total_new} frames to process, {labeled} already done")
        for i, fpath in enumerate(frame_list):
            fname = os.path.splitext(os.path.basename(fpath))[0]
            if fname in already_labeled:
                continue  # skip already processed frames

            # Lightweight GPU cache clear every 50 frames
            if processed_new % 50 == 0 and processed_new > 0:
                torch.cuda.empty_cache()

            # Reload model every 500 new frames to reset VRAM
            if processed_new > 0 and processed_new % 500 == 0:
                print(f"\n[AutoLabeler] Reloading model to free VRAM "
                      f"(processed {processed_new} new frames)...\n")
                self.unload()
                self.load()
            processed_new += 1

            if processed_new % 10 == 0 or processed_new == 1:
                elapsed = time.time() - start_time
                rate = processed_new / max(elapsed, 0.1)
                remaining = total_new - processed_new
                eta = remaining / max(rate, 0.01)
                print(f"[AutoLabeler] new={processed_new}/{total_new} "
                      f"({100*processed_new/total_new:.0f}%) "
                      f"rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

            results = self.label_frame(fpath)

            if results is None or len(results) == 0:
                empty += 1
                continue

            try:
                # Copy frame image to labeled dir (use shutil to avoid memory load)
                dst_img = os.path.join(
                    self.config.labeled_images_dir, f"{fname}.png",
                )
                if not os.path.exists(dst_img):
                    shutil.copy2(fpath, dst_img)

                # Write YOLO label file
                dst_label = os.path.join(
                    self.config.labeled_labels_dir, f"{fname}.txt",
                )
                with open(dst_label, "w", encoding="utf-8") as f:
                    for r in results:
                        x, y, w, h = r["bbox"]
                        f.write(f"0 {x:.6f} {y:.6f} {w:.6f} {h:.6f}\n")

                # Save recognized texts for review HTML display
                texts = [r["text"] for r in results]
                texts_map[fname] = texts

                labeled += 1
            except Exception as e:
                errors += 1
                print(f"[AutoLabeler] Write error {fname}: {e}")

            # Reload model every 500 frames to completely reset VRAM
            if i > 0 and i % 500 == 0 and not fname in already_labeled:
                print(f"\n[AutoLabeler] Reloading model to free VRAM...")
                self.unload()
                self.load()
                print(f"[AutoLabeler] Continuing...\n")


            if i % 20 == 0:
                state.set_step("label", status="in_progress",
                               processed=i + 1, labeled_count=labeled,
                               empty_count=empty, error_count=errors)

        # Save recognized texts for review display
        import json as _json
        texts_path = os.path.join(
            self.config.labeled_labels_dir, "texts.json",
        )
        with open(texts_path, "w", encoding="utf-8") as f:
            _json.dump(texts_map, f, ensure_ascii=False)

        state.set_step("label", status="done", processed=total,
                       labeled_count=labeled, empty_count=empty,
                       error_count=errors)
        elapsed = time.time() - start_time
        print(f"[AutoLabeler] Done. {labeled} labeled, {empty} empty, "
              f"{errors} errors in {elapsed:.0f}s")
