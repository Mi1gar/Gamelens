"""Visualize Florence-2 detected subtitle regions on a frame."""
import cv2
import sys
from auto_labeler import AutoLabeler
from config import PipelineConfig

frame_path = sys.argv[1] if len(sys.argv) > 1 else "data/frames/frame_000100.png"
output_path = sys.argv[2] if len(sys.argv) > 2 else "debug_bbox.png"

c = PipelineConfig(base_dir=".")
l = AutoLabeler(c)
result = l.label_frame(frame_path)

img = cv2.imread(frame_path)
img_h, img_w = img.shape[:2]

for r in result:
    xc, yc, w, h = r["bbox"]
    x1 = int((xc - w/2) * img_w)
    y1 = int((yc - h/2) * img_h)
    x2 = int((xc + w/2) * img_w)
    y2 = int((yc + h/2) * img_h)

    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
    cv2.putText(img, r["text"][:50], (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

cv2.imwrite(output_path, img)
print(f"Saved to: {output_path}")
print(f"Regions: {len(result)}")
for r in result:
    print(f"  [{r['text'][:60]}]")
