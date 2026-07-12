"""Quick check: run Florence-2 on a single frame and show results."""
from auto_labeler import AutoLabeler
from config import PipelineConfig
import sys

frame = sys.argv[1] if len(sys.argv) > 1 else "data/frames/frame_000050.png"

c = PipelineConfig(base_dir=".")
l = AutoLabeler(c)
result = l.label_frame(frame)

print(f"Frame: {frame}")
print(f"Regions found: {len(result)}")
print("-" * 50)
for i, r in enumerate(result):
    t = r["text"]
    b = r["bbox"]
    print(f"  [{i+1}] Text: {t}")
    print(f"      Bbox: x={b[0]:.3f} y={b[1]:.3f} w={b[2]:.3f} h={b[3]:.3f}")
