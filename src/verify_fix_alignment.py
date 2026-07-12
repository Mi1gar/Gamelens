
import sys
import os

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.adapters.firewatch_adapter import FirewatchAdapter
from src.core.interfaces import SubtitleEvent

# Mock Layout for RapidOCR result
# [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
# Let's simulate a text box at (10, 10) in the stitched image
# Height 40px (y1=10, y2=50) -> Center local = 30
# If it's in Top Region (Center Region), Screen Y Center = RegionTop (300) + 30 = 330
# Expected Top-Left Y = 330 - (40/2) = 310

mock_ocr_result = [
    [
        [[10, 10], [100, 10], [100, 50], [10, 50]], # Box
        "Hello World",                               # Text
        0.99                                         # Confidence
    ]
]

class MockOCREngine:
    def __call__(self, img):
        return mock_ocr_result, 0.1

def test_fix():
    print("Testing FirewatchAdapter coordinate fix...")
    adapter = FirewatchAdapter()
    
    # Mock the OCR engine
    adapter.ocr_engine = MockOCREngine()
    
    # Mock vision capture to return valid image (dimensions don't strictly matter for logic, just not None)
    # We mock capture_multi_region to return a dummy array
    import numpy as np
    adapter.vision.capture_multi_region = lambda x: np.zeros((100, 100, 3), dtype=np.uint8)
    
    # Fake connection
    adapter._connected = True
    
    event = adapter.poll_subtitle()
    
    if not event:
        print("FAIL: No event detected")
        return

    layout = event.layout
    if not layout:
        print("FAIL: No layout in event")
        return
        
    box = layout[0]['box']
    print(f"Detected Box: {box}")
    # box = [x, y, w, h]
    
    # Expected:
    # Local Center Y = 30
    # Region Center Y = 300
    # Screen Center Y = 330
    # Height = 40
    # Expected Top-Left Y = 310
    
    expected_y = 310
    expected_h = 40
    
    if box[1] == expected_y and box[3] == expected_h:
        print("SUCCESS: Coordinate calculation is correct (Top-Left Y).")
    else:
        print(f"FAIL: Expected Y={expected_y}, H={expected_h}. Got Y={box[1]}, H={box[3]}")
        print("Note: If Y is 330, it's still calculating Center.")

if __name__ == "__main__":
    test_fix()
