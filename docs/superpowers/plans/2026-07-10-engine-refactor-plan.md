# Game Lens — Engine Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Engine mimarisini tamamla, tüm pipeline'ı tek bir çalıştırılabilir uygulama haline getir, ilk canlı testi yap.

**Architecture:** Engine pipeline (HookManager → YOLO → OCR → TemporalFilter → TranslationService → Overlay) tek bir tutarlı modül yapısına kavuşacak. Tkinter overlay bağımsız çalışacak. Tauri UI sidecar olarak Python engine'i spawn edecek.

**Tech Stack:** Python 3.11, RapidOCR, YOLOv8, CTranslate2/NLLB-200, MSS, Tkinter, Tauri + React

## Global Constraints

- Tüm Python modülleri `engine/` altında olmalı
- Model dosyaları `models/` dizininde
- NLLB-200 600M model kullanılacak (1.3B opsiyonel)
- Overlay: Tkinter, siyah şerit, Corbel font, altyazının altında
- Pipeline: Growing DB → TranslationMemory fuzzy → NLLB-200
- Feedback loop olmamalı (overlay orijinal altyazıyı kapatmamalı)
- Sistem PATH'ine Python 3.11 (`C:\Users\M_ilg\AppData\Local\Programs\Python\Python311\python.exe`) kayıtlı

---

## File Map

```
GameLens/
├── run.py                          ← NEW: ana giriş noktası
├── engine/
│   ├── __init__.py
│   ├── core/
│   │   ├── subtitle_detector.py    ← MODIFY: model path düzelt
│   │   ├── nllb_translator.py      ← MODIFY: 600M path, public API
│   │   ├── hook_manager.py         ← MODIFY: watermark/HUD filtreleri, bbox merge
│   │   └── ...
│   ├── services/
│   │   └── translation_service.py  ← NEW: birleşik çeviri servisi
│   └── overlay/
│       ├── __init__.py             ← NEW
│       └── subtitle_overlay.py     ← NEW: live_test'ten taşı
├── models/
│   └── yolo_subtitle.pt            ← (zaten burada)
└── ui/                             ← Phase 2'de güncellenecek
```

---

### Task 1: YOLO Model Path'ini Düzelt

**Files:**
- Modify: `engine/core/subtitle_detector.py:21`

**Interfaces:**
- Produces: `SubtitleDetector._MODEL_PATH` → `models/yolo_subtitle.pt`

- [ ] **Step 1: Fix model path constant**

Edit `engine/core/subtitle_detector.py`, line 21. Change:
```python
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "yolo_subtitle.pt")
```
To:
```python
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "models", "yolo_subtitle.pt")
```

- [ ] **Step 2: Verify path resolves correctly**

```powershell
cd D:\gammasoftware\GameLens
python -c "from engine.core.subtitle_detector import SubtitleDetector; d = SubtitleDetector(); print('Path:', d.model_path); import os; print('Exists:', os.path.exists(d.model_path))"
```

Expected output:
```
Path: D:\gammasoftware\GameLens\models\yolo_subtitle.pt
Exists: True
```

- [ ] **Step 3: Verify YOLO loads and detects**

```powershell
cd D:\gammasoftware\GameLens
python -c "
from engine.core.subtitle_detector import SubtitleDetector
d = SubtitleDetector()
ok = d.load()
print('Load OK:', ok)
print('Model loaded:', d._loaded)
"
```

Expected: `Load OK: True`, `Model loaded: True`

---

### Task 2: NLLB Translator Model Path'ini Düzelt ve API'yi Netleştir

**Files:**
- Modify: `engine/core/nllb_translator.py:10,57`

**Interfaces:**
- Produces: `nllb_translator.translate(text: str) -> str`
- Produces: `nllb_translator.is_loaded() -> bool`

- [ ] **Step 1: Fix model path to 600M**

Edit `engine/core/nllb_translator.py`, line 10. Change:
```python
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models", "nllb-200-1.3b-ct2-int8")
```
To:
```python
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models", "nllb-200-600m-ct2-int8")
```

- [ ] **Step 2: Verify NLLB loads and translates**

```powershell
cd D:\gammasoftware\GameLens
python -c "
from engine.core.nllb_translator import translate, is_loaded
result = translate('Hello')
print('Loaded:', is_loaded())
print('Result:', result)
"
```

Expected: `Loaded: True`, `Result: Merhaba` (warm-up + translation çalışmalı)

---

### Task 3: Birleşik TranslationService Oluştur

**Files:**
- Create: `engine/services/translation_service.py`
- (Replace: `engine/services/translator.py` — Google Translate olan)

**Interfaces:**
- Produces: `TranslationService(target_lang='tr')`
- Produces: `TranslationService.translate(text: str) -> str`
- Method chain: Growing DB → TranslationMemory.fuzzy → NLLB-200

- [ ] **Step 1: Create unified TranslationService**

Write `engine/services/translation_service.py`:

```python
"""Unified translation service: Growing DB → Memory (fuzzy) → NLLB-200."""
import os, json, time

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "dataset_live", "growing_memory.json")


class TranslationService:
    def __init__(self, target_lang: str = "tr"):
        self.target_lang = target_lang
        self._cache: dict[str, str] = {}
        self._new_entries = 0

        # Load growing memory from disk
        self._growing: dict[str, str] = {}
        if os.path.exists(_DB_PATH):
            try:
                with open(_DB_PATH, "r", encoding="utf-8") as f:
                    self._growing = json.load(f)
                print(f"[TranslationService] Loaded {len(self._growing)} growing entries.")
            except Exception:
                self._growing = {}

        # Lazy-load NLLB (don't load 600MB model until needed)
        self._nllb_loaded = False

    def _ensure_nllb(self):
        if self._nllb_loaded:
            return
        from engine.core.nllb_translator import translate as nllb_translate
        self._nllb_translate = nllb_translate
        # Trigger lazy load
        self._nllb_translate("Hello")
        self._nllb_loaded = True
        print("[TranslationService] NLLB-200 ready.")

    def translate(self, text: str) -> str:
        if not text or len(text.strip()) < 2:
            return ""

        clean = text.strip()

        # 0. In-memory cache
        if clean in self._cache:
            return self._cache[clean]

        # 1. Growing DB (0ms, built during gameplay)
        key = clean.lower()
        if key in self._growing:
            result = self._growing[key]
            self._cache[clean] = result
            return result

        # 2. Static TranslationMemory fuzzy match (0ms, Claude translations)
        try:
            from engine.core.manual_translations import TranslationMemory
            result = TranslationMemory.get_fuzzy(clean, cutoff=0.85)
            if result:
                self._cache[clean] = result
                return result
        except Exception:
            pass

        # 3. Text normalization (slang → formal English)
        try:
            from engine.core.text_cleaner import TextNormalizer
            clean = TextNormalizer.normalize(clean)
        except Exception:
            pass

        # 4. NLLB-200 GPU (35-60ms)
        try:
            self._ensure_nllb()
            result = self._nllb_translate(clean)
            if result:
                self._cache[clean] = result
                # Auto-add to growing DB
                self._add_to_db(clean, result)
                return result
        except Exception as e:
            print(f"[TranslationService] NLLB error: {e}")

        return ""

    def _add_to_db(self, original: str, translated: str):
        key = original.strip().lower()
        if key and key not in self._growing and translated:
            self._growing[key] = translated
            self._new_entries += 1
            try:
                os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
                with open(_DB_PATH, "w", encoding="utf-8") as f:
                    json.dump(self._growing, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    @property
    def stats(self) -> dict:
        return {
            "growing_entries": len(self._growing),
            "new_this_session": self._new_entries,
            "cache_size": len(self._cache),
        }
```

- [ ] **Step 2: Verify TranslationService initializes without NLLB load**

```powershell
cd D:\gammasoftware\GameLens
python -c "
from engine.services.translation_service import TranslationService
ts = TranslationService()
print('Growing entries:', len(ts._growing))
print('Stats:', ts.stats)
"
```

Expected: Growing entries > 0 (growing_memory.json'dan yüklenmeli)

- [ ] **Step 3: Verify TranslationService translates (will trigger NLLB lazy load)**

```powershell
cd D:\gammasoftware\GameLens
python -c "
from engine.services.translation_service import TranslationService
ts = TranslationService()
# Test growing DB hit
result = ts.translate('there.')
print('Growing DB hit:', result)
# Test NLLB fallback
result2 = ts.translate('This is a test sentence.')
print('NLLB translate:', result2)
print('Stats:', ts.stats)
"
```

Expected: Growing DB'den `Evet, işte.` dönmeli, NLLB'den yeni çeviri gelmeli.

---

### Task 4: Overlay'i Engine Altına Taşı

**Files:**
- Create: `engine/overlay/__init__.py`
- Create: `engine/overlay/subtitle_overlay.py`
- (Keep: `overlay/overlay.py` olduğu yerde, referans)

**Interfaces:**
- Produces: `SubtitleOverlay(monitor: dict)`
- Produces: `overlay.queue_show(text, x, y, w, h)`
- Produces: `overlay.run()` — starts Tkinter mainloop
- Produces: `overlay.is_visible -> bool`

- [ ] **Step 1: Create engine/overlay/__init__.py**

```powershell
cd D:\gammasoftware\GameLens
New-Item -ItemType Directory -Force engine\overlay
```

Write `engine/overlay/__init__.py`:
```python
from .subtitle_overlay import SubtitleOverlay
__all__ = ["SubtitleOverlay"]
```

- [ ] **Step 2: Create engine/overlay/subtitle_overlay.py**

Write `engine/overlay/subtitle_overlay.py` — copy from `yolotest/live_test_optimized.py` lines 193-303 (the SubtitleOverlay class), with these improvements:
- Use absolute imports
- Add proper type hints
- Accept monitor dict parameter

```python
"""Optimized subtitle overlay — black strip below original, no feedback loop."""
import tkinter as tk
import ctypes


class SubtitleOverlay:
    """Thin black strip + small white text positioned BELOW the original subtitle.
    
    Features:
    - WDA_EXCLUDEFROMCAPTURE (DXGI capture exclusion)
    - Position tolerance ±15px (absorbs YOLO bbox jitter)
    - Auto-hide after 4 seconds of no new subtitle
    - Corbel font, dynamic sizing (11-18px, ~40% of subtitle height)
    - Same text + same position = just refresh timer (no redraw)
    """
    
    def __init__(self, monitor: dict):
        self.mx = monitor["left"]
        self.my = monitor["top"]
        
        self.root = tk.Tk()
        self.root.withdraw()
        
        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.wm_attributes("-topmost", True)
        self.win.config(bg="#0a0a0a")
        self.win.attributes("-alpha", 0.90)
        
        self.win.update_idletasks()
        try:
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            print("  [Overlay] WDA_EXCLUDEFROMCAPTURE OK")
        except Exception as e:
            print(f"  [Overlay] WDA exclude failed: {e}")
        
        self.win.withdraw()
        self.lbl = tk.Label(
            self.win, text="",
            fg="#EAEAEA", bg="#0a0a0a",
            font=("Corbel", 14),
            justify="center", anchor="center",
        )
        self.lbl.pack(expand=True, fill="both", padx=10, pady=3)
        
        self._current: str = ""
        self._current_geo: str = ""
        self._hide_timer: str | None = None
        self._next: dict | None = None
        self._update()
    
    def queue_show(self, text: str, x: int, y: int, w: int, h: int):
        """Show black box below the original subtitle."""
        clean = text.strip().lower()
        
        # Position tolerance: ignore YOLO bbox jitter (±15px)
        if clean == self._current:
            try:
                cur_x = int(self._current_geo.split("+")[1])
                cur_y = int(self._current_geo.split("+")[2])
                new_x = self.mx + int(x) - 8
                new_y = self.my + int(y) + int(h) + 2
                if abs(cur_x - new_x) < 15 and abs(cur_y - new_y) < 15:
                    self._reset_timer()
                    return
            except (IndexError, ValueError):
                pass
        
        # Font size: ~40% of original subtitle height
        font_sz = max(11, min(18, int(h * 0.40)))
        font = ("Corbel", font_sz)
        
        # Measure actual text width
        dummy = tk.Label(self.root, text=text, font=font)
        text_w = dummy.winfo_reqwidth()
        dummy.destroy()
        
        # Box: compact, only as wide as needed
        box_w = max(int(w) + 16, text_w + 24)
        box_h = font_sz + 12
        
        sx = self.mx + int(x) - 8
        sy = self.my + int(y) + int(h) + 2
        geo = f"{box_w}x{box_h}+{sx}+{sy}"
        
        if clean == self._current and geo == self._current_geo:
            return
        
        self._next = {"text": text, "geo": geo, "font": font}
    
    def _update(self):
        if self._next:
            self._current = self._next["text"].strip().lower()
            self._current_geo = self._next["geo"]
            self.lbl.config(text=self._next["text"], font=self._next["font"])
            self.win.geometry(self._next["geo"])
            self.win.deiconify()
            self.win.lift()
            self._next = None
            self._reset_timer()
        self.root.after(50, self._update)
    
    @property
    def is_visible(self) -> bool:
        return self._current != ""
    
    def refresh(self):
        """Reset hide timer without changing content."""
        self._reset_timer()
    
    def _reset_timer(self):
        if self._hide_timer:
            self.root.after_cancel(self._hide_timer)
        self._hide_timer = self.root.after(4000, self._hide)
    
    def _hide(self):
        self.win.withdraw()
        self._current = ""
        self._current_geo = ""
    
    def run(self):
        """Start Tkinter mainloop — blocks until window closed."""
        self.root.mainloop()
    
    def stop(self):
        """Stop the overlay and close windows."""
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
```

- [ ] **Step 3: Verify overlay module imports**

```powershell
cd D:\gammasoftware\GameLens
python -c "from engine.overlay import SubtitleOverlay; print('Overlay imported OK')"
```

Expected: `Overlay imported OK`

---

### Task 5: HookManager Pipeline Entegrasyonu

**Files:**
- Modify: `engine/core/hook_manager.py:60-308`

**Interfaces:**
- Consumes: `TranslationService` from Task 3
- Consumes: `SubtitleOverlay` from Task 4
- Modifies: `HookManager._process_with_yolo()` — watermark/HUD/credit filtreleri, bbox merge, en uzun metin seçimi

- [ ] **Step 1: Read current HookManager to understand the integration points**

```powershell
cd D:\gammasoftware\GameLens
python -c "
from engine.core.hook_manager import HookManager
print('HookManager imports OK')
print('Methods:', [m for m in dir(HookManager) if not m.startswith('_')])
"
```

- [ ] **Step 2: Rewrite HookManager with full pipeline**

Rewrite `engine/core/hook_manager.py` with all filters from `live_test_optimized.py` integrated:

```python
import time, threading, os, json, re
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
    Flow: Capture → YOLO Detect → Crop → Preprocess → Line Split → OCR → Filter → Translate → Overlay
    """
    
    # Watermark + credits patterns (from live_test_optimized.py)
    WATERMARK_WORDS = [
        'iceandfire','ceandfire','leeandfire','kiceandfire','klceandfire','eandfire',
        'mkice','hugues st-pierre','seandfire','character','vehicle and prop art',
        'art direction','interior art','kathrin roessler','nick greco','michaelkane',
        'karmen coker','roessler','interiur aat','haractea','aaron garbut','aaron +',
        'aaron garbut','jody pileski','thomas diakomichalis','alex hadjadj',
        'graphics direction','motion design','art and technical','direltur',
        'andfre','klceandfre','mklceandfre','iceandfre','ceandfre',
        'st-pierre','st- pierre','hugues','diakomichalis','pileski','hadjadj',
        'ross wallace','sergei kuprejanov','jason bone','weapon and melee',
        'weapon and','melee systems','bone','kuprejanov','wallace',
        'aristen', 'umezawa', 'kentaro', 'nakamura', 'hiroshi',
        'koji', 'yamada', 'tanaka', 'sato', 'suzuki',
    ]
    
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
        
        self.ocr_rec = RapidOCR(use_det=False, use_cls=False, rec_use_cuda=True)
        print("[HookManager] RapidOCR rec-only initialized (GPU, ~4ms/line).")
        
        self.ocr_full = RapidOCR(use_det=True, use_cls=False, det_use_cuda=True, rec_use_cuda=True)
        print("[HookManager] RapidOCR full OCR initialized (fallback).")
        
        # Build watermark set for fast lookup
        self._wm_set = set(
            w.replace(' ','').replace('-','').replace('+','').lower()
            for w in self.WATERMARK_WORDS
        )
        
        self.temporal_filter = TemporalFilter()
        self.detector = SubtitleDetector()
        self._use_yolo = self.detector.load()
        
        # Frame Collector
        self.collector = FrameCollector(
            output_dir=os.path.join(os.getcwd(), "dataset_live")
        )
        self._collected_texts = []
        
        # TranslationService — lazy load
        self._translator = None
        
        # Overlay — set externally
        self.overlay = None
        
        self._frame_count = 0
        self._fps_target = 0.05  # 20 FPS
    
    @property
    def translator(self):
        if self._translator is None:
            from engine.services.translation_service import TranslationService
            self._translator = TranslationService()
        return self._translator
    
    def set_active_adapter(self, adapter: BaseGameAdapter):
        if self.active_adapter:
            self.active_adapter.disconnect()
        self.active_adapter = adapter
        if self.active_adapter:
            self.active_adapter.connect()
            print(f"[HookManager] Active adapter: {self.active_adapter.DISPLAY_NAME}")
    
    def start(self, callback_on_subtitle):
        if not self.active_adapter:
            print("[HookManager] No adapter selected.")
            return
        
        import sys
        self._log = open("hook_manager.log", "w", buffering=1)
        self._log.write(f"[HookManager] Starting... adapter={self.active_adapter.DISPLAY_NAME}\n")
        self._log.write(f"[HookManager] YOLO loaded={self._use_yolo}\n")
        self._log.flush()
        
        self.is_running = True
        self._stop_event.clear()
        self._frame_count = 0
        self._collected_texts = []
        self.temporal_filter.reset()
        
        mode = "YOLO" if self._use_yolo else "Adapter regions"
        print(f"[HookManager] Starting Pipeline (Mode: {mode}, Target: 20 FPS)...", flush=True)
        
        self._thread = threading.Thread(
            target=self._poll_loop, args=(callback_on_subtitle,), daemon=True
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
            print(f"[HookManager] Saved {len(self._collected_texts)} texts to dataset.")
        
        stats = self.collector.get_stats()
        print(f"[HookManager] Dataset: {stats['frames_saved']} frames saved to {stats['output_dir']}")
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
    
    def _process_with_yolo(self, img, callback):
        """YOLO-based detection with full filtering pipeline."""
        h, w = img.shape[:2]
        
        # Convert BGRA → RGB for YOLO
        if len(img.shape) == 3 and img.shape[2] == 4:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        else:
            img_rgb = img
        
        bboxes = self.detector.detect(img_rgb)
        
        if not bboxes:
            return
        
        # Merge overlapping bboxes
        bboxes = self._merge_bboxes(bboxes)
        
        best_text = None
        best_tr = None
        best_bbox = None
        
        for x1, y1, x2, y2 in bboxes:
            x1, y1 = max(0, x1 - 6), max(0, y1 - 4)
            x2, y2 = min(w, x2 + 6), min(h, y2 + 4)
            
            crop = img[y1:y2, x1:x2]
            if crop.shape[0] < 8 or crop.shape[1] < 10:
                continue
            
            # OCR: preprocess → split lines → rec-only
            profile = self.active_adapter.get_ocr_profile()
            processed = ImagePreprocessor.process_for_ocr(crop, profile=profile)
            line_images = self._split_into_lines(processed)
            
            if not line_images:
                continue
            
            found_text = self._ocr_lines(line_images)
            if not found_text or len(found_text) < 3:
                continue
            
            # Filter: watermark
            if self._is_watermark(found_text):
                continue
            
            # Filter: credit lines
            if self._is_credit_line(found_text):
                continue
            
            # Filter: UI elements
            if self._is_ui_element(found_text):
                continue
            
            # Quality filter: alpha ratio
            alpha = sum(1 for c in found_text if c.isalpha())
            if len(found_text) > 10 and alpha / len(found_text) < 0.5:
                continue
            
            # Temporal classification
            classification = self.temporal_filter.classify(
                found_text, zone_id=self.active_adapter.GAME_ID
            )
            
            if classification in ("blacklisted", "noise", "pending", "sign", "hud"):
                if classification == "active":
                    # Still on screen, refresh overlay
                    if self.overlay and best_tr:
                        self.overlay.queue_show(
                            best_tr, *best_bbox[:2],
                            best_bbox[2] - best_bbox[0], best_bbox[3] - best_bbox[1]
                        )
                continue
            
            # Translate
            translated = self.translator.translate(found_text)
            
            # Keep longest (most complete) text
            if found_text and (best_text is None or len(found_text) > len(best_text)):
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
            print(f"[YOLO] \"{best_text[:60]}\"")
            if best_tr:
                print(f"       → \"{best_tr[:60]}\"")
            
            # Show overlay
            if self.overlay:
                self.overlay.queue_show(
                    display, best_bbox[0], best_bbox[1],
                    best_bbox[2] - best_bbox[0], best_bbox[3] - best_bbox[1]
                )
            
            # Dispatch to callback
            meta = {
                'timestamp': time.time(),
                'frame_count': self._frame_count,
                'zone': 'yolo',
            }
            event = self.active_adapter.process_raw_result(best_text, [], meta)
            if event:
                callback(event)
    
    def _merge_bboxes(self, bboxes):
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
                    area_b = min((x2 - x1) * (y2 - y1), (b2[2] - b2[0]) * (b2[3] - b2[1]))
                    if area_i > area_b * 0.5:
                        x1, y1 = min(x1, b2[0]), min(y1, b2[1])
                        x2, y2 = max(x2, b2[2]), max(y2, b2[3])
                        used.add(j)
            merged.append((x1, y1, x2, y2))
            used.add(i)
        return merged
    
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
    
    def _is_watermark(self, text: str) -> bool:
        t = text.lower().replace(' ', '').replace('?', '').replace('+', '').replace('.', '').replace('-', '')
        if any(w in t for w in self._wm_set):
            return True
        for w in self._wm_set:
            if len(w) >= 5 and w[:4] in t:
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
    
    @staticmethod
    def _is_ui_element(text: str) -> bool:
        t = text.strip()
        if re.match(r'^[+\-]\d+\s*>?$', t):
            return True
        if re.search(r'(hold|press|tap|use|rotate)\s+[\(\[]?[A-Z0-9][\)\]]?', t.lower()):
            return True
        if len(t) <= 3 and not t.isalpha():
            return True
        return False
    
    def _process_with_adapter(self, img, callback):
        """Fallback: adapter-based hardcoded regions → OCR."""
        profile = self.active_adapter.get_ocr_profile()
        processed_img = ImagePreprocessor.process_for_ocr(img, profile=profile)
        ocr_results, _ = self.ocr_full(processed_img)
        
        found_text = ""
        if ocr_results:
            valid_results = [line for line in ocr_results if float(line[2]) > 0.6]
            found_text = " ".join([line[1] for line in valid_results]).strip()
        
        if not found_text or len(found_text) < 3 or found_text.isdigit():
            return
        
        classification = self.temporal_filter.classify(
            found_text, zone_id=self.active_adapter.GAME_ID
        )
        
        if classification != "emit":
            return
        
        meta = {'timestamp': time.time(), 'frame_count': self._frame_count, 'zone': 'primary'}
        event = self.active_adapter.process_raw_result(found_text, [], meta)
        if event:
            callback(event)
```

- [ ] **Step 3: Verify HookManager imports and initializes**

```powershell
cd D:\gammasoftware\GameLens
python -c "
from engine.core.hook_manager import HookManager
hm = HookManager()
print('YOLO loaded:', hm._use_yolo)
print('HookManager init OK')
"
```

Expected: `YOLO loaded: True`, `HookManager init OK`

---

### Task 6: Ana Giriş Noktası (run.py)

**Files:**
- Create: `run.py`

**Interfaces:**
- Produces: CLI entrypoint with `--game`, `--monitor` args
- Spawns: Tkinter overlay thread + HookManager pipeline thread

- [ ] **Step 1: Create run.py**

Write `run.py` at project root:

```python
#!/usr/bin/env python
"""Game Lens — Real-time game subtitle translator.
Usage:
    python run.py --game rdr2 --monitor 1
    python run.py --game metro_2033
    python run.py --list-games
"""
import sys, os, time, threading, argparse

# Ensure project root is on path
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# Register NVIDIA DLLs early
import site, glob
for sp in site.getsitepackages():
    for p in ['nvidia/cudnn/bin', 'nvidia/cublas/bin', 'nvidia/cuda_runtime/bin']:
        for d in glob.glob(os.path.join(sp, p)):
            if os.path.isdir(d):
                try:
                    os.add_dll_directory(d)
                except Exception:
                    pass
                os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')


def list_games():
    """Print all registered game adapters."""
    from engine.core.registry import GameRegistry
    # Force import adapters to trigger registration
    import engine.adapters.rdr2_adapter
    import engine.adapters.metro_adapter
    
    games = GameRegistry.get_all_games()
    print("\nAvailable games:")
    print("-" * 50)
    for g in games:
        print(f"  {g['id']:20s} — {g['name']}")
        if g.get('description'):
            print(f"  {'':20s}   {g['description']}")
    print()


def run_game(game_id: str, monitor_idx: int = 1):
    """Start the translation pipeline for a specific game."""
    import mss
    from engine.core.registry import GameRegistry
    from engine.core.hook_manager import HookManager
    from engine.overlay import SubtitleOverlay
    
    # Force import adapters
    import engine.adapters.rdr2_adapter
    import engine.adapters.metro_adapter
    
    # Get monitor info
    with mss.mss() as sct:
        if monitor_idx >= len(sct.monitors):
            print(f"Error: Monitor {monitor_idx} not found. Available: 1-{len(sct.monitors)-1}")
            return
        monitor = sct.monitors[monitor_idx]
    
    print(f"\n{'='*60}")
    print(f"Game Lens — {game_id.upper()}")
    print(f"Monitor {monitor_idx}: {monitor['width']}x{monitor['height']}")
    print(f"{'='*60}\n")
    
    # Get adapter
    adapter = GameRegistry.get_adapter(game_id)
    if not adapter:
        print(f"Error: Game '{game_id}' not found.")
        list_games()
        return
    
    # Create overlay (on main thread, Tkinter requires it)
    overlay = SubtitleOverlay(monitor)
    
    # Create HookManager
    hook_mgr = HookManager()
    hook_mgr.overlay = overlay
    hook_mgr.set_active_adapter(adapter)
    
    # Simple callback — just log
    def on_subtitle(event):
        pass  # Overlay is already updated directly by HookManager
    
    # Start pipeline in background
    hook_mgr.start(on_subtitle)
    
    print(f"\nPipeline running. Overlay will appear below subtitles.")
    print(f"Close the overlay window to stop.\n")
    
    try:
        overlay.run()  # Blocks until window closed
    except KeyboardInterrupt:
        print("\nShutting down...")
    
    hook_mgr.stop()
    print("Game Lens stopped.")


def main():
    parser = argparse.ArgumentParser(description="Game Lens — Real-time Game Subtitle Translator")
    parser.add_argument("--game", "-g", type=str, help="Game ID (e.g. rdr2, metro_2033)")
    parser.add_argument("--monitor", "-m", type=int, default=1, help="Monitor index (default: 1)")
    parser.add_argument("--list-games", "-l", action="store_true", help="List available games")
    args = parser.parse_args()
    
    if args.list_games:
        list_games()
        return
    
    if not args.game:
        parser.print_help()
        print("\nTip: Use --list-games to see available games.")
        return
    
    run_game(args.game, args.monitor)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI works**

```powershell
cd D:\gammasoftware\GameLens
python run.py --list-games
```

Expected: List of registered games (RDR2, Metro 2033)

---

### Task 7: Tauri UI — Python Sidecar Entegrasyonu

**Files:**
- Create: `engine/sidecar_api.py`
- Modify: `ui/src-tauri/src/lib.rs`
- Modify: `ui/src-tauri/src/main.rs`

- [ ] **Step 1: Create Python sidecar API**

Write `engine/sidecar_api.py`:

```python
"""Sidecar API for Tauri UI communication.
Receives commands via command-line args, outputs JSON to stdout.
Usage: python engine/sidecar_api.py --list-games
       python engine/sidecar_api.py --run rdr2 --monitor 1
"""
import sys, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Register NVIDIA DLLs
import site, glob
for sp in site.getsitepackages():
    for p in ['nvidia/cudnn/bin', 'nvidia/cublas/bin', 'nvidia/cuda_runtime/bin']:
        for d in glob.glob(os.path.join(sp, p)):
            if os.path.isdir(d):
                try: os.add_dll_directory(d)
                except: pass


def cmd_list_games():
    """Output JSON array of available games."""
    import engine.adapters.rdr2_adapter
    import engine.adapters.metro_adapter
    from engine.core.registry import GameRegistry
    games = GameRegistry.get_all_games()
    print(json.dumps({"type": "games", "data": games}))


def cmd_run(args):
    """Start pipeline for a game (non-blocking info)."""
    print(json.dumps({
        "type": "status",
        "data": {
            "status": "starting",
            "game": args.get("game", "unknown"),
            "message": "Pipeline starting, overlay will appear on game screen.",
        }
    }))


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"type": "error", "data": "No command"}))
        return
    
    cmd = sys.argv[1]
    
    if cmd == "--list-games":
        cmd_list_games()
    elif cmd == "--run":
        game = sys.argv[2] if len(sys.argv) > 2 else "rdr2"
        monitor = sys.argv[3] if len(sys.argv) > 3 else "1"
        cmd_run({"game": game, "monitor": int(monitor)})
    else:
        print(json.dumps({"type": "error", "data": f"Unknown command: {cmd}"}))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update Tauri Rust backend**

Modify `ui/src-tauri/src/lib.rs`:

```rust
use std::process::Command;

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[tauri::command]
fn list_games() -> String {
    let output = Command::new("python")
        .args(["engine/sidecar_api.py", "--list-games"])
        .current_dir("..")
        .output()
        .expect("Failed to execute Python sidecar");
    
    String::from_utf8_lossy(&output.stdout).to_string()
}

#[tauri::command]
fn start_game(game_id: String, monitor: u32) -> String {
    // Spawn detached — the Python process runs independently
    std::process::Command::new("python")
        .args(["run.py", "--game", &game_id, "--monitor", &monitor.to_string()])
        .current_dir("..")
        .spawn()
        .expect("Failed to start game pipeline");
    
    format!("{{\"status\": \"started\", \"game\": \"{}\"}}", game_id)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![greet, list_games, start_game])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

- [ ] **Step 3: Verify Tauri compiles**

```powershell
cd D:\gammasoftware\GameLens\ui
npm run tauri build 2>&1 | Select-Object -Last 10
```

Expected: Build succeeds (or at least `cargo check` passes).

---

### Task 8: Entegrasyon Testi

**Files:**
- Test: `run.py --game rdr2` (RDR2 oyunu açıkken)

- [ ] **Step 1: Verify all imports work end-to-end**

```powershell
cd D:\gammasoftware\GameLens
python -c "
from engine.core.subtitle_detector import SubtitleDetector
from engine.core.hook_manager import HookManager
from engine.core.nllb_translator import translate as nllb
from engine.core.temporal_filter import TemporalFilter
from engine.core.preprocessor import ImagePreprocessor
from engine.core.registry import GameRegistry
from engine.overlay import SubtitleOverlay
from engine.services.translation_service import TranslationService
print('ALL IMPORTS OK')
"
```

- [ ] **Step 2: Test OCR + NLLB pipeline with a still frame**

```powershell
cd D:\gammasoftware\GameLens
python -c "
import cv2, os, time
import numpy as np

# Test frame (use existing capture if available)
test_files = ['test_capture.png', 'rdr2_test_capture.png', 'firewatch_test_capture.png']
test_img = None
for f in test_files:
    if os.path.exists(f):
        test_img = cv2.imread(f)
        print(f'Using test image: {f}')
        break

if test_img is None:
    print('No test image found, skipping frame test.')
    exit(0)

from engine.core.subtitle_detector import SubtitleDetector
from engine.core.preprocessor import ImagePreprocessor
from rapidocr_onnxruntime import RapidOCR

detector = SubtitleDetector()
detector.load()

ocr = RapidOCR(use_det=False, use_cls=False, rec_use_cuda=True)

img_rgb = cv2.cvtColor(test_img, cv2.COLOR_BGR2RGB)
bboxes = detector.detect(img_rgb)
print(f'YOLO detections: {len(bboxes)}')

for x1, y1, x2, y2 in bboxes:
    crop = test_img[y1:y2, x1:x2]
    processed = ImagePreprocessor.process_for_ocr(crop, profile='subtitle')
    
    # Split lines
    h, w = processed.shape[:2]
    row_sums = np.sum(processed < 128, axis=1)
    max_sum = np.max(row_sums)
    threshold = max(3, max_sum * 0.12)
    text_rows = row_sums > threshold
    
    lines = []
    in_line = False
    start = 0
    for i in range(h):
        if text_rows[i] and not in_line:
            start = i; in_line = True
        elif not text_rows[i] and in_line:
            y1, y2 = max(0, start - 3), min(h, i + 3)
            if y2 - y1 >= 8:
                lines.append(processed[y1:y2, :])
            in_line = False
    if in_line:
        y1 = max(0, start - 3)
        if h - y1 >= 8:
            lines.append(processed[y1:h, :])
    
    texts = []
    for limg in lines:
        result, _ = ocr(limg)
        if result and isinstance(result, list):
            for item in result:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    t, s = str(item[0]), float(item[1])
                    if t and s > 0.5:
                        texts.append(t.strip())
    
    ocr_text = ' '.join(texts)
    print(f'OCR: \"{ocr_text}\"')
    
    # Translate
    from engine.services.translation_service import TranslationService
    ts = TranslationService()
    tr = ts.translate(ocr_text)
    print(f'TR:  \"{tr}\"')
    print(f'Stats: {ts.stats}')
"
```

- [ ] **Step 3: Run live test with RDR2**

```powershell
cd D:\gammasoftware\GameLens
python run.py --game rdr2
```

Manual verification checklist:
- [ ] Overlay window appears on correct monitor
- [ ] YOLO detects subtitles within 1-2 seconds of dialog
- [ ] Turkish translation appears below original subtitle
- [ ] No feedback loop (original subtitle stays visible)
- [ ] Watermarks and credits are filtered out
- [ ] Overlay disappears after ~4 seconds of no subtitles
- [ ] Close overlay window stops pipeline cleanly

---

### Task 9: Cleanup

**Files:**
- Remove/reference: `yolotest/live_test_optimized.py` (add deprecation comment)
- Remove: `engine/services/translator.py` (old Google Translate service)

- [ ] **Step 1: Mark old files as deprecated**

Add to top of `yolotest/live_test_optimized.py`:
```python
# DEPRECATED: This file is replaced by run.py + engine/ architecture.
# Kept for reference. Use: python run.py --game rdr2
```

- [ ] **Step 2: Remove Google Translate service**

```powershell
cd D:\gammasoftware\GameLens
# Rename to .bak instead of delete for safety
Move-Item engine/services/translator.py engine/services/translator_google.py.bak
```

- [ ] **Step 3: Final verification — full pipeline import chain**

```powershell
cd D:\gammasoftware\GameLens
python run.py --list-games
```

Expected: Clean list of available games without errors.
