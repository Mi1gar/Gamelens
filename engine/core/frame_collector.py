import os
import cv2
import json
import time
import hashlib

class FrameCollector:
    """
    Saves frames + bbox + OCR text when subtitle is detected.
    Builds a dataset for YOLO fine-tuning and translation memory.
    """
    def __init__(self, output_dir="dataset"):
        self.output_dir = os.path.abspath(output_dir)
        self.images_dir = os.path.join(self.output_dir, "images")
        self.labels_dir = os.path.join(self.output_dir, "labels")
        self._texts = {}
        self._frame_count = 0
        self._saved_count = 0
        self._enabled = True
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.labels_dir, exist_ok=True)

    def save_frame(self, img, bbox, text):
        if not self._enabled:
            return
        if not text or len(text) < 3:
            return

        self._frame_count += 1

        # Dedup: skip if same text was saved recently (5 frame window)
        key = text.lower().strip(".,!?\"' ")
        if key in self._texts:
            last_saved = self._texts[key]
            if self._frame_count - last_saved < 10:
                return

        h, w = img.shape[:2]
        x1, y1, x2, y2 = bbox

        # Save image
        img_name = f"frame_{self._frame_count:06d}.png"
        img_path = os.path.join(self.images_dir, img_name)
        cv2.imwrite(img_path, img)

        # Save YOLO label (normalized)
        x_center = ((x1 + x2) / 2) / w
        y_center = ((y1 + y2) / 2) / h
        bw = (x2 - x1) / w
        bh = (y2 - y1) / h
        label = f"1 {x_center:.6f} {y_center:.6f} {bw:.6f} {bh:.6f}"

        label_name = f"frame_{self._frame_count:06d}.txt"
        label_path = os.path.join(self.labels_dir, label_name)
        with open(label_path, "w") as f:
            f.write(label)

        self._texts[key] = self._frame_count
        self._saved_count += 1

    def save_texts(self, texts_with_timestamps):
        """Save OCR extracted texts to a JSON file."""
        texts_path = os.path.join(self.output_dir, "ocr_texts.json")
        with open(texts_path, "w", encoding="utf-8") as f:
            json.dump(texts_with_timestamps, f, ensure_ascii=False, indent=2)

    def get_stats(self):
        return {
            "frames_processed": self._frame_count,
            "frames_saved": self._saved_count,
            "output_dir": self.output_dir,
        }

    def disable(self):
        self._enabled = False

    def enable(self):
        self._enabled = True
