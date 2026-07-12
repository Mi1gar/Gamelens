"""Screen capture using DXGI Desktop Duplication API (dxcam).

DXGI respects WDA_EXCLUDEFROMCAPTURE — the overlay window is invisible
to capture, preventing the feedback loop. Also faster than GDI (60+ FPS).
"""
import numpy as np
from typing import Tuple
import dxcam


class ScreenCapture:
    """High-performance DXGI screen capture.

    Uses dxcam (DirectX Desktop Duplication) instead of MSS/GDI.
    Benefits: respects WDA_EXCLUDEFROMCAPTURE, 60+ FPS, RGB output.
    Fallback to MSS if dxcam fails.
    """

    def __init__(self):
        self._camera = None
        self._use_dxgi = True

        try:
            self._camera = dxcam.create()
            print("[Vision] DXGI capture ready (overlay excluded from capture).")
        except Exception as e:
            print(f"[Vision] DXGI failed ({e}), falling back to GDI.")
            self._use_dxgi = False

    def capture_region(
        self, region: Tuple[int, int, int, int]
    ) -> np.ndarray:
        """Capture a screen region.

        Args:
            region: (left, top, width, height)

        Returns:
            numpy array in BGR format (compatible with existing pipeline).
        """
        left, top, width, height = region

        if self._use_dxgi and self._camera is not None:
            try:
                # dxcam grabs the whole screen or a region
                frame = self._camera.grab(region=(left, top, left + width, top + height))
                if frame is not None:
                    # dxcam returns numpy array in RGB format
                    import cv2
                    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            except Exception:
                pass  # fall through to GDI

        # GDI fallback (MSS)
        import mss
        monitor = {
            "left": int(left),
            "top": int(top),
            "width": int(width),
            "height": int(height),
        }
        with mss.mss() as sct:
            sct_img = sct.grab(monitor)
            img = np.array(sct_img)
            import cv2
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def capture_multi_region(
        self, regions: list[Tuple[int, int, int, int]]
    ) -> np.ndarray | None:
        """Capture multiple regions and stitch vertically.

        Args:
            regions: List of (left, top, width, height)

        Returns:
            Stitched BGR image, or None if capture fails.
        """
        images = []
        for reg in regions:
            img = self.capture_region(reg)
            if img is not None:
                images.append(img)

        if not images:
            return None

        max_width = max(img.shape[1] for img in images)
        padded = []
        for img in images:
            h, w = img.shape[:2]
            if w < max_width:
                pad = np.zeros((h, max_width - w, 3), dtype=img.dtype)
                img = np.hstack([img, pad])
            padded.append(img)

        return np.vstack(padded)

    def save_snapshot(self, img: np.ndarray, filename: str = "snapshot.png"):
        import cv2
        cv2.imwrite(filename, img)
