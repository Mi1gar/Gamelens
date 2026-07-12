"""Subtitle detector using ONNX Runtime — no PyTorch dependency.

Uses exported YOLO ONNX model with built-in NMS.
Output: (1, 300, 6) — max 300 detections × (x1, y1, x2, y2, conf, cls)
"""
import os
import numpy as np
import onnxruntime as ort

_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "models", "Vision_C1P_02.onnx",
)

# ONNX Runtime session cache (module-level singleton)
_session: ort.InferenceSession | None = None
_providers: list[str] = []


def _get_providers() -> list[str]:
    """Get available ONNX Runtime execution providers."""
    available = ort.get_available_providers()
    # Prefer GPU, fall back to CPU
    preferred = [
        "CUDAExecutionProvider",
        "TensorrtExecutionProvider",
        "CPUExecutionProvider",
    ]
    return [p for p in preferred if p in available]


def _get_active_model_path() -> str:
    """Get the best available YOLO model (updated or fallback)."""
    try:
        from engine.core.model_manager import get_yolo_model_path
        path = get_yolo_model_path()
        # If the updated model is .pt, fall back to .onnx
        if path.endswith(".pt"):
            onnx_path = path.replace(".pt", ".onnx")
            if os.path.exists(onnx_path):
                return onnx_path
        if os.path.exists(path):
            return path
    except Exception:
        pass
    return _MODEL_PATH


class SubtitleDetector:
    """YOLO-based subtitle region detector via ONNX Runtime.

    No PyTorch dependency — uses ONNX Runtime directly.
    Supports GPU (CUDA/TensorRT) and CPU fallback.
    """

    INPUT_SIZE = 512
    CONF_THRESHOLD = 0.12

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path or _get_active_model_path()
        self._loaded = False
        self._input_name = "images"
        self._output_name = "output0"

    def load(self) -> bool:
        if self._loaded:
            return True

        if not os.path.exists(self.model_path):
            print(f"[SubtitleDetector] Model not found: {self.model_path}")
            # Try .onnx fallback
            onnx_path = _MODEL_PATH
            if os.path.exists(onnx_path):
                print(f"[SubtitleDetector] Using fallback: {onnx_path}")
                self.model_path = onnx_path
            else:
                return False

        global _session, _providers
        if _session is None:
            _providers = _get_providers()
            print(f"[SubtitleDetector] ONNX providers: {_providers}")
            _session = ort.InferenceSession(
                self.model_path,
                providers=_providers,
            )
            # Cache input/output names
            self._input_name = _session.get_inputs()[0].name
            self._output_name = _session.get_outputs()[0].name

        self._loaded = True
        print(f"[SubtitleDetector] Model loaded ({os.path.basename(self.model_path)}).")
        return True

    def detect(self, img: np.ndarray) -> list[list[int]]:
        """Returns list of bbox [x1, y1, x2, y2] for detected subtitles.

        Args:
            img: numpy array from MSS capture (height, width, channels).
                 BGRA (4ch) or BGR (3ch).
        """
        if not self._loaded:
            return []

        h, w = img.shape[:2]

        # Preprocess
        import cv2
        # BGRA → RGB
        if len(img.shape) == 3 and img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Resize to 512x512 (stretch, matching training)
        img_resized = cv2.resize(img, (self.INPUT_SIZE, self.INPUT_SIZE))

        # Normalize [0, 255] → [0, 1]
        img_norm = img_resized.astype(np.float32) / 255.0

        # HWC → CHW → add batch dim: (1, 3, 512, 512)
        input_tensor = np.transpose(img_norm, (2, 0, 1))[np.newaxis, ...]

        # Inference
        outputs = _session.run(
            [self._output_name],
            {self._input_name: input_tensor},
        )
        detections = outputs[0]  # shape: (1, 300, 6)

        # Parse output
        # detections[0, :, :] = [x1, y1, x2, y2, conf, cls]
        bboxes = []
        for det in detections[0]:  # iterate over 300 predictions
            x1, y1, x2, y2, conf, cls_id = det
            if conf < self.CONF_THRESHOLD:
                continue
            if int(cls_id) != 0:  # class 0 = s-subtittle
                continue

            # Rescale from 512x512 back to original image size
            scale_x = w / self.INPUT_SIZE
            scale_y = h / self.INPUT_SIZE

            bboxes.append([
                int(x1 * scale_x),
                int(y1 * scale_y),
                int(x2 * scale_x),
                int(y2 * scale_y),
            ])

        return bboxes
