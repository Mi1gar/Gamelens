"""Brutal cleanup: delete all obvious non-dialogue bboxes from all labels.

Usage:
    python clean_labels.py                  # default base_dir = .
    python clean_labels.py --base-dir D:\gamelens\pipeline
"""
import argparse
import json
import re
import os
import sys

# Ensure pipeline directory is importable
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import PipelineConfig


def clean_labels(config: PipelineConfig) -> dict:
    """Run brutal cleanup on all labeled frames.

    Returns stats dict: {"kept": int, "removed": int}
    """
    texts_path = os.path.join(config.labeled_labels_dir, "texts.json")
    labels_dir = config.labeled_labels_dir

    if not os.path.exists(texts_path):
        print(f"[CleanLabels] texts.json not found at {texts_path}")
        return {"kept": 0, "removed": 0}

    with open(texts_path, "r", encoding="utf-8") as f:
        texts_map = json.load(f)

    removed = 0
    kept = 0
    new_map = {}

    for name, texts in texts_map.items():
        label_path = os.path.join(labels_dir, f"{name}.txt")
        if not os.path.exists(label_path):
            continue
        with open(label_path, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")

        new_lines = []
        new_texts = []
        for line, text in zip(lines, texts):
            t = text.strip()
            delete = False

            # 1. Watermark patterns
            low = t.lower().replace(" ", "").replace(".", "")
            if any(w in low for w in ["iceandfire", "mkice", "kiceand", "miceand",
                                       "mklce", "micke", "mkand", "iceandf",
                                       "icean", "mkic", "mklo", "mkie"]):
                delete = True

            # 2. ALL CAPS single word 3-8 chars
            if not delete and t.isupper() and " " not in t and 3 <= len(t) <= 8:
                delete = True

            # 2b. MixedCase single word >= 4 chars = watermark fragment
            # Exception: words ending with ? or ! are dialogue
            # "." at end + ALL CAPS body = still watermark
            if not delete and " " not in t and len(t) >= 4:
                body = t.rstrip('.!?,;:')
                has_upper = any(c.isupper() for c in body)
                has_lower = any(c.islower() for c in body)
                if has_upper and has_lower and len(body) >= 3:
                    if not t.endswith(('?', '!')):
                        delete = True
            # 2c. ALL CAPS single word with dots (acronyms/garbage): "R.L.D.CODDS"
            if not delete and t.isupper() and '.' in t and len(t) >= 5:
                delete = True
            # 2d. ALL CAPS single word >= 9 chars = garbage
            if not delete and t.isupper() and " " not in t and len(t) >= 9:
                delete = True
            # 2e. URL-like / bracket garbage (short texts only)
            if not delete and ('[' in t or ']' in t or t.startswith('www.')):
                if len(t) < 30:
                    delete = True
                else:
                    t = t.replace('[', '').replace(']', '').strip()
                    print(f"  [FIXED] {name}: removed brackets -> \"{t[:60]}\"")
                    new_lines.append(line)
                    new_texts.append(t)
                    continue

            # 3. ALL CAPS multi-word (credit lines)
            if not delete and t.isupper() and len(t.split()) >= 2:
                delete = True

            # 4. Random-looking: 4+ consecutive consonants, all uppercase
            if not delete and t.isupper() and len(t) >= 4:
                consonants = sum(1 for c in t if c.isalpha() and c.lower() not in "aeiou")
                if consonants >= len(t) * 0.7:
                    delete = True

            # 5. Vehicle ID / plate patterns
            if not delete and re.match(r'^[A-Z]{2,5}[-\s]?\d{3,6}$', t):
                delete = True

            # 6. Text starting with garbage prefix (keep the dialogue part)
            if not delete and len(t) > 20:
                # Check if first word looks like an ID/plate: "ALC-0065 Shit, a dog..."
                first_word = t.split()[0] if t.split() else ""
                if re.match(r'^[A-Z\d][A-Z\d\-\.]{2,}$', first_word):
                    # Remove the garbage prefix
                    rest = " ".join(t.split()[1:])
                    if len(rest) > 10:
                        print(f"  [CLEANED] {name}: \"{first_word}\" -> \"{rest[:60]}\"")
                        t = rest
                        # Update text but keep bbox
                        new_lines.append(line)
                        new_texts.append(t)
                        continue

            # 7. Short numeric-heavy
            if not delete and len(t) < 12 and re.search(r'\d', t):
                alpha = sum(1 for c in t if c.isalpha())
                if alpha < len(t) * 0.5:
                    delete = True

            if delete:
                removed += 1
                print(f"  [DEL] {name}: \"{t[:60]}\"")
            else:
                new_lines.append(line)
                new_texts.append(t)

        if new_lines:
            with open(label_path, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines) + "\n")
            new_map[name] = new_texts
            kept += 1
        else:
            os.remove(label_path)

    with open(texts_path, "w", encoding="utf-8") as f:
        json.dump(new_map, f, ensure_ascii=False)

    print(f"\n[CleanLabels] Done. {kept} frames kept, {removed} texts deleted.")
    return {"kept": kept, "removed": removed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Brutal cleanup of non-dialogue bboxes from labels",
    )
    parser.add_argument("--base-dir", default=".",
                        help="Pipeline base directory (default: .)")
    args = parser.parse_args()

    config = PipelineConfig(base_dir=os.path.abspath(args.base_dir))
    clean_labels(config)
