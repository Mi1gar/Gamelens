"""Qwen2-VL subtitle classifier — verifies Florence-2 labels, removes noise."""
import os
import json
import time
import torch
from PIL import Image
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from config import PipelineConfig
from state_manager import StateManager


class QwenClassifier:
    """Use Qwen2-VL to verify whether detected text is actually a subtitle."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._model = None
        self._processor = None

    def load(self):
        if self._model is not None:
            return
        print("[QwenClassifier] Loading Qwen2-VL 2B (fp16)...")
        self._model = Qwen2VLForConditionalGeneration.from_pretrained(
            "Qwen/Qwen2-VL-2B-Instruct",
            dtype=torch.float16,
            device_map="auto",
        )
        self._processor = AutoProcessor.from_pretrained(
            "Qwen/Qwen2-VL-2B-Instruct",
        )
        print("[QwenClassifier] Ready!")

    def classify_frame(self, image_path: str, candidates: list[dict]) -> list[dict]:
        """Ask Qwen which candidate texts are subtitles.

        Args:
            image_path: path to frame image
            candidates: [{"text": str, "bbox": tuple}, ...]

        Returns only the candidates Qwen believes are subtitles.
        """
        if not candidates:
            return []
        if self._model is None:
            self.load()

        img = Image.open(image_path).convert("RGB")
        text_list = "\n".join(
            f'  [{i+1}] "{c["text"]}"' for i, c in enumerate(candidates)
        )

        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": img},
                {"type": "text", "text": (
                    "A text detector found these texts in this game screenshot:\n"
                    f"{text_list}\n\n"
                    "Which of these are subtitles/dialogue spoken by characters? "
                    "Subtitles: sentence-length, appear during conversations, "
                    "usually at screen bottom center. "
                    "NOT subtitles: credit names (ALL CAPS people names), "
                    "channel logos (MKIceAndFire), UI hints (Press X to...), "
                    "HUD elements, single words from signs, timestamps.\n\n"
                    "Answer with ONLY the numbers of subtitle texts, like: 1,3\n"
                    "If none are subtitles, answer: 0"
                )},
            ],
        }]

        prompt = self._processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
        inputs = self._processor(
            images=[img], text=prompt, return_tensors="pt",
        ).to(self._model.device)

        with torch.no_grad():
            gen = self._model.generate(**inputs, max_new_tokens=50)
        answer = self._processor.batch_decode(
            gen[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True,
        )[0]

        # Parse which numbers Qwen selected
        import re
        nums = re.findall(r'\d+', answer)
        keep_indices = set(
            int(n) - 1 for n in nums
            if 1 <= int(n) <= len(candidates)
        )

        return [candidates[i] for i in keep_indices if i < len(candidates)]

    def unload(self):
        """Free VRAM after use."""
        if self._model is not None:
            del self._model
            del self._processor
            self._model = None
            self._processor = None
            torch.cuda.empty_cache()


def run_classification(config: PipelineConfig, state: StateManager):
    """Post-process Florence-2 labels with Qwen2-VL verification."""
    texts_path = os.path.join(config.labeled_labels_dir, "texts.json")
    if not os.path.exists(texts_path):
        print("[QwenClassifier] No texts.json found. Run --label first.")
        return

    with open(texts_path, "r", encoding="utf-8") as f:
        texts_map = json.load(f)

    if not texts_map:
        print("[QwenClassifier] No labeled frames.")
        return

    # Load existing YOLO labels
    frame_data = {}
    for fname in sorted(os.listdir(config.labeled_labels_dir)):
        if not fname.endswith(".txt"):
            continue
        name = os.path.splitext(fname)[0]
        if name not in texts_map:
            continue
        label_path = os.path.join(config.labeled_labels_dir, fname)
        with open(label_path, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        bboxes = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 5:
                bboxes.append([float(p) for p in parts[1:5]])
        frame_data[name] = {
            "bboxes": bboxes,
            "texts": texts_map[name],
        }

    classifier = QwenClassifier(config)
    total = len(frame_data)
    kept = 0
    removed = 0
    start = time.time()

    new_texts_map = {}

    for i, (name, data) in enumerate(sorted(frame_data.items())):
        image_path = os.path.join(config.labeled_images_dir, f"{name}.png")
        if not os.path.exists(image_path):
            continue

        candidates = [
            {"text": t, "bbox": tuple(b)}
            for t, b in zip(data["texts"], data["bboxes"])
        ]
        results = classifier.classify_frame(image_path, candidates)

        if len(results) < len(candidates):
            removed += len(candidates) - len(results)

        if results:
            kept += 1
            # Rewrite YOLO label with only verified subtitles
            label_path = os.path.join(config.labeled_labels_dir, f"{name}.txt")
            with open(label_path, "w", encoding="utf-8") as f:
                for r in results:
                    x, y, w_box, h_box = r["bbox"]
                    f.write(f"0 {x:.6f} {y:.6f} {w_box:.6f} {h_box:.6f}\n")
            new_texts_map[name] = [r["text"] for r in results]

        if i % 10 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / max(elapsed, 0.1)
            eta = (total - i - 1) / max(rate, 0.01)
            print(f"[QwenClassifier] {i+1}/{total} ({100*(i+1)/total:.0f}%) "
                  f"rate={rate:.1f}/s kept={kept} removed={removed} eta={eta:.0f}s")

    # Update texts.json with verified-only texts
    with open(texts_path, "w", encoding="utf-8") as f:
        json.dump(new_texts_map, f, ensure_ascii=False)

    # Clean up empty label files
    for name in texts_map:
        if name not in new_texts_map:
            label_path = os.path.join(config.labeled_labels_dir, f"{name}.txt")
            if os.path.exists(label_path):
                os.remove(label_path)

    classifier.unload()

    elapsed = time.time() - start
    print(f"[QwenClassifier] Done. {kept} frames kept, {removed} texts removed "
          f"in {elapsed:.0f}s")
