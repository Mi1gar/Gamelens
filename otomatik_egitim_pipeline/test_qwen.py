"""Test Qwen2-VL-2B — smart subtitle detection with bounding boxes."""
import torch, json, re, sys
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from PIL import Image

frame = sys.argv[1] if len(sys.argv) > 1 else "data/frames/frame_000100.png"

print("[Qwen2-VL] Loading model...")
model = Qwen2VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen2-VL-2B-Instruct", dtype=torch.float16, device_map="auto",
)
processor = AutoProcessor.from_pretrained("Qwen/Qwen2-VL-2B-Instruct")
print("[Qwen2-VL] Ready!")

img = Image.open(frame).convert("RGB")
w, h = img.size

messages = [{
    "role": "user",
    "content": [
        {"type": "image", "image": img},
        {"type": "text", "text": (
            f"This game screenshot is {w}x{h} pixels. "
            "Look for any text that looks like character dialogue or spoken lines "
            "(subtitles in a game). These are usually sentence-length, not single words.\n\n"
            "For each dialogue/subtitle found, estimate its bounding box in pixels "
            "as [x1, y1, x2, y2] and provide the text.\n"
            "Return ONLY a JSON array. Example:\n"
            '[{"bbox": [960, 950, 1460, 970], "text": "Hello world"}]\n\n'
            "If no dialogue is visible, return []"
        )},
    ],
}]

text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = processor(images=[img], text=text, return_tensors="pt").to(model.device)

print("\n[Qwen2-VL] Analyzing...")
with torch.no_grad():
    gen = model.generate(**inputs, max_new_tokens=512)
output = processor.batch_decode(
    gen[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
)[0]

print(f"\n{'='*60}")
print(f"Frame: {frame}")
print(f"Raw output:\n{output}")

# Try to parse JSON from output
try:
    m = re.search(r'\[.*\]', output, re.DOTALL)
    if m:
        data = json.loads(m.group())
        print(f"\nParsed {len(data)} subtitles:")
        for d in data:
            b = d["bbox"]
            print(f"  [{d['text'][:70]}]")
            print(f"    x1={b[0]} y1={b[1]} x2={b[2]} y2={b[3]}")
    else:
        print("  No JSON array found in output")
except Exception as e:
    print(f"  Parse error: {e}")
print(f"{'='*60}")
