"""Hybrid: Florence-2 finds bboxes, Qwen2-VL classifies ALL at once per frame."""
import torch, json, re, sys
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from PIL import Image
from auto_labeler import AutoLabeler
from config import PipelineConfig

frame = sys.argv[1] if len(sys.argv) > 1 else "data/frames/frame_000001.png"

# Step 1: Florence-2 finds ALL text
print("[Step 1] Florence-2 finding text regions...")
c = PipelineConfig(base_dir=".")
c.min_text_length = 1
fl = AutoLabeler(c)
results = fl.label_frame(frame)
print(f"  Found {len(results)} texts")

if not results:
    print("  No text found, done.")
    sys.exit(0)

text_list = "\n".join(f'  [{i+1}] "{r["text"]}"' for i, r in enumerate(results))
print(text_list)

# Step 2: Qwen2-VL classifies all at once
print("\n[Step 2] Qwen2-VL classifying...")
model = Qwen2VLForConditionalGeneration.from_pretrained(
    "Qwen/Qwen2-VL-2B-Instruct", dtype=torch.float16, device_map="auto",
)
processor = AutoProcessor.from_pretrained("Qwen/Qwen2-VL-2B-Instruct")
img = Image.open(frame).convert("RGB")

messages = [{
    "role": "user",
    "content": [
        {"type": "image", "image": img},
        {"type": "text", "text": (
            "A text detector found these texts in this game screenshot:\n"
            f"{text_list}\n\n"
            "Which of these are subtitles/dialogue spoken by characters? "
            "Subtitles are sentence-length, appear temporarily at screen bottom "
            "during conversations. NOT subtitles: credit names, channel logos, "
            "UI hints, HUD elements, single words from signs.\n\n"
            "Answer with ONLY the numbers of subtitle texts, like: 1,3,5\n"
            "If none are subtitles, answer: none"
        )},
    ],
}]

prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = processor(images=[img], text=prompt, return_tensors="pt").to(model.device)

with torch.no_grad():
    gen = model.generate(**inputs, max_new_tokens=50)
answer = processor.batch_decode(
    gen[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True
)[0]

print(f"  Qwen answer: {answer}")

# Parse numbers
nums = re.findall(r'\d+', answer)
indices = set(int(n) - 1 for n in nums if 1 <= int(n) <= len(results))

print(f"\n{'='*60}")
print(f"Verdict: {len(indices)}/{len(results)} are subtitles")
for i in sorted(indices):
    print(f"  ✅ [{results[i]['text'][:80]}]")
for i, r in enumerate(results):
    if i not in indices:
        print(f"  ❌ [{r['text'][:60]}]")
