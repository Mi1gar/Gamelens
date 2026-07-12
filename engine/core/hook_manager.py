import time
import threading
import os
import re
from typing import Optional
import cv2
import numpy as np

from .interfaces import BaseGameAdapter, SubtitleEvent
from .vision import ScreenCapture
from .preprocessor import ImagePreprocessor
from .temporal_filter import TemporalFilter
from .subtitle_detector import SubtitleDetector
from .frame_collector import FrameCollector


class HookManager:
    """Main Visual Pipeline Driver.
    Flow: Capture -> YOLO Detect -> Crop -> Preprocess -> Line Split -> OCR -> Filter -> Translate -> Overlay
    """

    # Known YouTube watermark: MKIceAndFire channel logo
    # Only prefixed variants — bare "iceandfire" appears in normal phrases
    # like "police and fire" → "policeandfire" after cleaning
    _WM_VARIANTS = {'mkiceandfire', 'kiceandfire', 'mklceandfire', 'klceandfire'}

    def __init__(self):
        self.active_adapter: Optional[BaseGameAdapter] = None
        self.is_running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Core Components
        print("[HookManager] Initializing vision components...")
        self.vision = ScreenCapture()

        # RapidOCR — load after NVIDIA DLL registration (done by subtitle_detector)
        from rapidocr_onnxruntime import RapidOCR

        self.ocr_rec = RapidOCR(
            use_det=False, use_cls=False, rec_use_cuda=True,
        )
        print("[HookManager] RapidOCR rec-only initialized (GPU, ~4ms/line).")

        self.ocr_full = RapidOCR(
            use_det=True, use_cls=False,
            det_use_cuda=True, rec_use_cuda=True,
        )
        print("[HookManager] RapidOCR full OCR initialized (fallback).")

        # Watermark check — only the known YouTube channel logo
        self._wm_set = self._WM_VARIANTS

        self.temporal_filter = TemporalFilter()
        self.detector = SubtitleDetector()
        self._use_yolo = self.detector.load()

        # Frame Collector (dataset building)
        self.collector = FrameCollector(
            output_dir=os.path.join(os.getcwd(), "dataset_live")
        )
        self._collected_texts = []

        # TranslationService — lazy loaded
        self._translator = None

        # Overlay — set externally by run.py
        self.overlay = None

        self._frame_count = 0
        self._fps_target = 0.033  # 30 FPS

        # Text+position debounce: prevent OCR variants of SAME subtitle
        # Ring buffer of recent emits — position-based dedup for subtitle duration
        from collections import deque
        self._recent_emits = deque(maxlen=5)
        self._debounce_s = 4.0  # subtitles stay on screen 2-8s; 4s is a safe window
        self._debounce_pos_x = 80   # horizontal tolerance (px)
        self._debounce_pos_y = 40   # vertical tolerance (px)


    @property
    def translator(self):
        if self._translator is None:
            from engine.services.translation_service import TranslationService
            game_slug = ""
            if self.active_adapter:
                game_slug = self.active_adapter.GAME_ID
            self._translator = TranslationService(
                target_lang='tr', game_slug=game_slug,
            )
        return self._translator

    def set_active_adapter(self, adapter: BaseGameAdapter):
        if self.active_adapter:
            self.active_adapter.disconnect()
        self.active_adapter = adapter
        if self.active_adapter:
            self.active_adapter.connect()
            print(
                f"[HookManager] Active adapter: "
                f"{self.active_adapter.DISPLAY_NAME}"
            )
            # Update cloud translation DB for the new game
            if self._translator is not None:
                self._translator.set_game(self.active_adapter.GAME_ID)

    def start(self, callback_on_subtitle):
        if not self.active_adapter:
            print("[HookManager] No adapter selected.")
            return

        import sys
        self._log = open("hook_manager.log", "w", buffering=1)
        self._log.write(
            f"[HookManager] Starting... "
            f"adapter={self.active_adapter.DISPLAY_NAME}\n"
        )
        self._log.write(f"[HookManager] YOLO loaded={self._use_yolo}\n")
        self._log.flush()

        self.is_running = True
        self._stop_event.clear()
        self._frame_count = 0
        self._collected_texts = []
        self.temporal_filter.reset()

        mode = "YOLO" if self._use_yolo else "Adapter regions"
        print(
            f"[HookManager] Starting Pipeline "
            f"(Mode: {mode}, Target: 20 FPS)...",
            flush=True,
        )

        self._thread = threading.Thread(
            target=self._poll_loop, args=(callback_on_subtitle,), daemon=True,
        )
        self._thread.start()

    def stop(self):
        self.is_running = False
        self._stop_event.set()
        if self.active_adapter:
            self.active_adapter.disconnect()
        if self._thread:
            self._thread.join(timeout=3.0)

        if self._collected_texts:
            self.collector.save_texts(self._collected_texts)
            print(
                f"[HookManager] Saved {len(self._collected_texts)} "
                f"texts to dataset."
            )

        stats = self.collector.get_stats()
        print(
            f"[HookManager] Dataset: {stats['frames_saved']} frames "
            f"saved to {stats['output_dir']}"
        )
        print("[HookManager] Pipeline stopped.")

    def _poll_loop(self, callback):
        while self.is_running and not self._stop_event.is_set():
            start_time = time.time()
            if self.active_adapter and self.active_adapter.is_active:
                self._process_frame(callback)
            elapsed = time.time() - start_time
            time.sleep(max(0.0, self._fps_target - elapsed))

    def _process_frame(self, callback):
        self._frame_count += 1

        regions = self.active_adapter.get_regions()
        if not regions:
            return

        img = self.vision.capture_multi_region(regions)
        if img is None:
            return

        if self._use_yolo:
            self._process_with_yolo(img, callback)
        else:
            self._process_with_adapter(img, callback)

    # ── YOLO pipeline ──────────────────────────────────────────────

    def _process_with_yolo(self, img, callback):
        """YOLO-based detection with full filtering pipeline."""
        h, w = img.shape[:2]

        # Convert BGRA -> RGB for YOLO
        if len(img.shape) == 3 and img.shape[2] == 4:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        else:
            img_rgb = img

        bboxes = self.detector.detect(img_rgb)

        if not bboxes:
            return

        # Merge overlapping bboxes
        bboxes = self._merge_bboxes(bboxes)

        # Filter by screen position — subtitles are bottom-center
        bboxes = [b for b in bboxes if self._is_subtitle_region(b, w, h)]

        # Debug: track why bboxes/texts are rejected
        _dbg = {"yolo_boxes": len(bboxes), "ocr_empty": 0, "ocr_short": 0,
                "filter_tr": 0, "filter_wm": 0, "filter_credit": 0,
                "filter_ui": 0, "filter_alpha": 0, "filter_vowel": 0,
                "temporal_skip": 0, "debounce_skip": 0, "line_split_empty": 0}

        best_text = None
        best_tr = None
        best_bbox = None

        for x1, y1, x2, y2 in bboxes:
            x1, y1 = max(0, x1 - 6), max(0, y1 - 4)
            x2, y2 = min(w, x2 + 6), min(h, y2 + 4)

            crop = img[y1:y2, x1:x2]
            if crop.shape[0] < 8 or crop.shape[1] < 10:
                continue

            # OCR: preprocess -> split lines -> rec-only
            profile = self.active_adapter.get_ocr_profile()
            processed = ImagePreprocessor.process_for_ocr(crop, profile=profile)
            line_images = self._split_into_lines(processed)

            if not line_images:
                _dbg["line_split_empty"] += 1
                continue

            found_text = self._ocr_lines(line_images)
            if not found_text:
                _dbg["ocr_empty"] += 1
                continue
            if len(found_text) < 3:
                _dbg["ocr_short"] += 1
                self._log.write(f"[OCR_SHORT] {found_text[:80]}\n")
                continue

            # Filter: overlay feedback loop
            if self._is_turkish_text(found_text):
                _dbg["filter_tr"] += 1
                self._log.write(f"[TR] {found_text[:80]}\n")
                continue

            # Filter: watermark
            if self._is_watermark(found_text):
                _dbg["filter_wm"] += 1
                self._log.write(f"[WM] {found_text[:80]}\n")
                continue

            # Filter: credit lines
            if self._is_credit_line(found_text):
                _dbg["filter_credit"] += 1
                self._log.write(f"[CREDIT] {found_text[:80]}\n")
                continue

            # Filter: UI elements (HUD, controls)
            if self._is_ui_element(found_text):
                _dbg["filter_ui"] += 1
                self._log.write(f"[UI] {found_text[:80]}\n")
                continue

            # Quality filter: alpha ratio check
            alpha = sum(1 for c in found_text if c.isalpha())
            if len(found_text) > 10 and alpha / len(found_text) < 0.5:
                _dbg["filter_alpha"] += 1
                self._log.write(f"[ALPHA] {found_text[:80]}\n")
                continue

            # Quality filter: minimum meaningful content
            # Only reject truly tiny OCR noise fragments (< 3 chars)
            # Short utterances like "hey", "go", "no" are valid dialogue
            words = found_text.split()
            if len(found_text) < 3:
                _dbg["filter_vowel"] += 1
                self._log.write(f"[SHORT] {found_text[:80]}\n")
                continue
            # Single-word check: require at least 1 vowel for short words
            # (catches all-consonant OCR garbage like "Dhdw", "Wnm")
            if len(words) == 1:
                vowels = sum(1 for c in found_text if c.lower() in "aeiouy")
                if vowels < 1:
                    _dbg["filter_vowel"] += 1
                    self._log.write(f"[VOWEL] {found_text[:80]}\n")
                    continue

            # Temporal classification
            classification = self.temporal_filter.classify(
                found_text, zone_id=self.active_adapter.GAME_ID,
            )

            if classification in ("blacklisted", "sign"):
                _dbg["temporal_skip"] += 1
                continue

            if classification == "active":
                if self.overlay and best_tr:
                    self.overlay.queue_show(
                        best_tr, best_bbox[0], best_bbox[1],
                        best_bbox[2] - best_bbox[0],
                        best_bbox[3] - best_bbox[1],
                    )
                continue

            # classification == "emit": translate and show
            # Debounce: check ALL recent emits — position + text similarity
            # Same position + similar text = OCR variant of SAME subtitle → skip
            # Same position + different text = genuinely NEW subtitle → allow
            bw, bh = x2 - x1, y2 - y1
            cx, cy = x1 + bw // 2, y1 + bh // 2
            now_ts = time.time()

            is_debounced = False
            for prev in self._recent_emits:
                if (now_ts - prev["time"]) > self._debounce_s:
                    continue  # stale entry
                same_pos = (
                    abs(cx - prev["cx"]) < self._debounce_pos_x and
                    abs(cy - prev["cy"]) < self._debounce_pos_y
                )
                if not same_pos:
                    continue
                # Position matches — check if text is OCR variant of same subtitle
                from difflib import SequenceMatcher
                text_sim = SequenceMatcher(None, found_text.lower(), prev["text"]).ratio()
                if text_sim > 0.55:
                    is_debounced = True
                    break

            if is_debounced:
                _dbg["debounce_skip"] += 1
                continue  # OCR variant of already-emitted subtitle

            # Translate
            translated = self.translator.translate(found_text)

            # Keep longest (most complete) text
            if found_text and (
                best_text is None or len(found_text) > len(best_text)
            ):
                best_text = found_text
                best_tr = translated
                best_bbox = (x1, y1, x2, y2)

        if best_text:
            self.collector.save_frame(img, best_bbox, best_text)
            self._collected_texts.append({
                "text": best_text,
                "timestamp": time.time(),
                "frame": self._frame_count,
            })

            display = best_tr if best_tr else best_text
            print(f'[YOLO] "{best_text[:60]}"')
            if best_tr:
                print(f'       -> "{best_tr[:60]}"')

            # Show overlay
            if self.overlay:
                self.overlay.queue_show(
                    display, best_bbox[0], best_bbox[1],
                    best_bbox[2] - best_bbox[0],
                    best_bbox[3] - best_bbox[1],
                )

            # Track this emit in ring buffer (position+text dedup)
            bw = best_bbox[2] - best_bbox[0]
            bh = best_bbox[3] - best_bbox[1]
            self._recent_emits.append({
                "cx": best_bbox[0] + bw // 2,
                "cy": best_bbox[1] + bh // 2,
                "text": best_text.lower() if best_text else "",
                "time": time.time(),
            })

            # Dispatch to callback
            meta = {
                'timestamp': time.time(),
                'frame_count': self._frame_count,
                'zone': 'yolo',
            }
            event = self.active_adapter.process_raw_result(
                best_text, [], meta,
            )
            if event:
                callback(event)

        # Debug: log rejections every 60 frames when YOLO found bboxes
        if _dbg["yolo_boxes"] > 0 and self._frame_count % 60 == 0:
            total_dropped = sum(v for k, v in _dbg.items() if k != "yolo_boxes")
            if total_dropped > 0:
                msg = (
                    f"[DBG] frame={self._frame_count} bboxes={_dbg['yolo_boxes']} "
                    f"ocr_empty={_dbg['ocr_empty']} ocr_short={_dbg['ocr_short']} "
                    f"linesplit={_dbg['line_split_empty']} "
                    f"tr={_dbg['filter_tr']} wm={_dbg['filter_wm']} "
                    f"credit={_dbg['filter_credit']} ui={_dbg['filter_ui']} "
                    f"alpha={_dbg['filter_alpha']} vowel={_dbg['filter_vowel']} "
                    f"temporal={_dbg['temporal_skip']} debounce={_dbg['debounce_skip']}"
                )
                print(msg)
                self._log.write(msg + "\n")
                self._log.flush()

    # ── Bbox region filter ─────────────────────────────────────────

    @staticmethod
    def _is_subtitle_region(bbox, screen_w: int, screen_h: int) -> bool:
        """Reject bboxes outside the bottom-center subtitle area.

        Subtitles are always in the bottom ~40% of screen, centered.
        Rejects: minimap (right edge), HUD (top/edges), corner elements.
        """
        x1, y1, x2, y2 = bbox
        bw = x2 - x1
        bh = y2 - y1

        # Must be in bottom half of screen
        center_y = (y1 + y2) / 2
        if center_y < screen_h * 0.40:
            return False

        # Must not be entirely in right 20% (minimap area)
        if x1 > screen_w * 0.80:
            return False

        # Must not be entirely in left 5% (corner HUD)
        if x2 < screen_w * 0.05:
            return False

        # Subtitle box should be reasonably wide
        # YOLO is trained for subtitles — use a lenient minimum
        # "hey" at 1440p = ~80px, need to allow short dialogue
        if bw < screen_w * 0.02:  # ~50px at 2560px — filters HUD dots, not words
            return False

        # Height should be reasonable (1-8% of screen height)
        if bh < screen_h * 0.008 or bh > screen_h * 0.12:
            return False

        return True

    # ── Bbox merging ───────────────────────────────────────────────

    @staticmethod
    def _merge_bboxes(bboxes):
        """Merge overlapping bounding boxes (from live_test_optimized.py)."""
        if len(bboxes) <= 1:
            return bboxes

        merged = []
        used = set()
        for i, b1 in enumerate(bboxes):
            if i in used:
                continue
            x1, y1, x2, y2 = b1
            for j, b2 in enumerate(bboxes):
                if j <= i or j in used:
                    continue
                ox1, oy1 = max(x1, b2[0]), max(y1, b2[1])
                ox2, oy2 = min(x2, b2[2]), min(y2, b2[3])
                if ox1 < ox2 and oy1 < oy2:
                    area_i = (ox2 - ox1) * (oy2 - oy1)
                    area_b = min(
                        (x2 - x1) * (y2 - y1),
                        (b2[2] - b2[0]) * (b2[3] - b2[1]),
                    )
                    if area_i > area_b * 0.5:
                        x1, y1 = min(x1, b2[0]), min(y1, b2[1])
                        x2, y2 = max(x2, b2[2]), max(y2, b2[3])
                        used.add(j)
            merged.append((x1, y1, x2, y2))
            used.add(i)
        return merged

    # ── Line splitting ─────────────────────────────────────────────

    @staticmethod
    def _split_into_lines(binary):
        """Split binary subtitle image into individual text lines."""
        if binary.size == 0:
            return []

        h, w = binary.shape
        row_sums = np.sum(binary < 128, axis=1)
        max_sum = np.max(row_sums)
        if max_sum < 3:
            return [binary]

        threshold = max(3, max_sum * 0.12)
        text_rows = row_sums > threshold

        lines = []
        in_line = False
        start = 0
        for i in range(h):
            if text_rows[i] and not in_line:
                start = i
                in_line = True
            elif not text_rows[i] and in_line:
                y1, y2 = max(0, start - 3), min(h, i + 3)
                if y2 - y1 >= 8:
                    lines.append(binary[y1:y2, :])
                in_line = False
        if in_line:
            y1 = max(0, start - 3)
            if h - y1 >= 8:
                lines.append(binary[y1:h, :])

        return lines if lines else [binary]

    # ── OCR ────────────────────────────────────────────────────────

    def _ocr_lines(self, line_images):
        """Recognition-only OCR on each line, join results."""
        texts = []
        for line_img in line_images:
            try:
                result, _ = self.ocr_rec(line_img)
                if result and isinstance(result, list):
                    for item in result:
                        if isinstance(item, (list, tuple)) and len(item) >= 2:
                            text, score = str(item[0]), float(item[1])
                            if text and score > 0.5:
                                texts.append(text.strip())
            except Exception:
                pass
        return " ".join(texts)

    # ── Filters ────────────────────────────────────────────────────

    def _is_watermark(self, text: str) -> bool:
        """Check if text is the MKIceAndFire YouTube channel watermark.
        Only matches if watermark dominates the text (>50% of chars)."""
        t = text.lower().replace(' ', '').replace('-', '').replace('+', '')
        for w in self._wm_set:
            if w in t and len(w) > len(t) * 0.5:
                return True
        return False

    @staticmethod
    def _is_credit_line(text: str) -> bool:
        t = text.strip()
        if t.isupper() and len(t.split()) >= 3:
            return True
        if t.isupper() and len(t) > 20:
            return True
        credit_words = [
            'direction', 'systems', 'design', 'producer', 'director',
            'engineer', 'artist', 'programmer', 'developer', 'manager',
            'supervisor', 'coordinator', 'technician', 'support',
        ]
        t_lower = t.lower()
        return any(cw in t_lower for cw in credit_words)

    # Turkish-specific characters — if OCR returns these, it captured
    # our own overlay text (feedback loop via GDI capture).
    _TURKISH_CHARS = set("şŞğĞıİüÜöÖçÇ")

    @staticmethod
    def _is_turkish_text(text: str) -> bool:
        """Detect overlay feedback loop: English subtitles don't have TR chars."""
        return bool(set(text) & HookManager._TURKISH_CHARS)

    # YouTube / browser UI strings to filter (Turkish + English)
    _UI_PATTERNS = [
        # Turkish YouTube UI
        'paylaş', 'paylas', 'kaydedenler', 'kaydet', 'abone ol', 'abone',
        'beğen', 'begen', 'yorumlar', 'yorum', 'otomatik', 'oynatma',
        'sonraki video', 'sonraki', 'sıradaki', 'siradaki',
        'bildirim', 'kanal', 'abone', 'görüntüleme', 'goruntuleme',
        'izleme', 'paylaştır', 'paylastir',
        # English YouTube / video UI
        'subscribe', 'subscribed', 'watch later', 'share', 'save',
        'report', 'transcript', 'playback', 'playback speed',
        'captions', 'subtitles', 'quality', 'settings',
        'full game', 'walkthrough', 'gameplay', '4k 60fps',
        'no commentary', 'playthrough', 'lets play', "let's play",
        'all endings', 'cutscenes', 'cutscene', 'movie mode',
        # Live stream / chat UI
        'chat reply', 'chat', 'live chat', 'super chat',
        'membership', 'join', 'joined', 'donation',
    ]
    _UI_PATTERNS_SET = set(_UI_PATTERNS)

    @staticmethod
    def _is_ui_element(text: str) -> bool:
        t = text.strip()
        # Numeric HUD indicators
        if re.match(r'^[+\-]\d+\s*>?$', t):
            return True
        # Controller hints
        if re.search(
            r'(hold|press|tap|use|rotate)\s+[\(\[]?[A-Z0-9][\)\]]?',
            t.lower(),
        ):
            return True
        # Very short non-alpha
        if len(t) <= 3 and not t.isalpha():
            return True
        # YouTube / browser UI keywords
        t_lower = t.lower().replace(' ', '')
        for kw in HookManager._UI_PATTERNS_SET:
            if len(kw) >= 5 and kw.replace(' ', '') in t_lower:
                return True
        # Turkish UI text has TR chars in patterns not typical of EN subtitles
        tr_chars_in_text = sum(1 for c in t if c in HookManager._TURKISH_CHARS)
        total_alpha = sum(1 for c in t if c.isalpha())
        if tr_chars_in_text > 0 and tr_chars_in_text / max(1, total_alpha) > 0.1:
            # >10% Turkish characters = Turkish UI, not English subtitle
            return True
        return False

    # ── Fallback adapter path ──────────────────────────────────────

    def _process_with_adapter(self, img, callback):
        """Fallback: adapter-based hardcoded regions -> full OCR."""
        profile = self.active_adapter.get_ocr_profile()
        processed_img = ImagePreprocessor.process_for_ocr(img, profile=profile)
        ocr_results, _ = self.ocr_full(processed_img)

        found_text = ""
        if ocr_results:
            valid_results = [
                line for line in ocr_results if float(line[2]) > 0.6
            ]
            found_text = " ".join(
                [line[1] for line in valid_results]
            ).strip()

        if not found_text or len(found_text) < 3 or found_text.isdigit():
            return

        classification = self.temporal_filter.classify(
            found_text, zone_id=self.active_adapter.GAME_ID,
        )

        if classification != "emit":
            return

        meta = {
            'timestamp': time.time(),
            'frame_count': self._frame_count,
            'zone': 'primary',
        }
        event = self.active_adapter.process_raw_result(found_text, [], meta)
        if event:
            callback(event)
