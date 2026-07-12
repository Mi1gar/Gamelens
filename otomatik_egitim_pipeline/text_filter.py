"""LLM-based text filter: uses Ollama + Llama 3.2 to classify subtitle vs noise."""
import json
import os
import re
import requests
from config import PipelineConfig

OLLAMA_URL = "http://localhost:11434/api/generate"


def _heuristic_check(text: str) -> bool:
    """Check if text looks like a real subtitle."""
    t = text.strip()
    if len(t) < 2:
        return False
    # Must have vowels
    vowels = sum(1 for c in t.lower() if c in "aeiou")
    if vowels < 1:
        return False
    # ALL CAPS multi-word = credit line
    if t.isupper() and len(t.split()) >= 2:
        return False
    # Short ALL CAPS single word (3-7 chars) = HUD/watermark fragment
    if t.isupper() and ' ' not in t and 3 <= len(t) <= 7:
        return False
    # Watermark patterns
    lower = t.lower().replace(" ", "").replace(".", "")
    if any(w in lower for w in ["iceandfire", "mkice", "kiceandfire"]):
        return False
    # Must be mostly alphabetic
    alpha = sum(1 for c in t if c.isalpha())
    if alpha < len(t) * 0.45:
        return False
    return True


def _definitely_garbage(text: str) -> bool:
    """Check if text is OBVIOUSLY not a subtitle — no LLM can override this."""
    t = text.strip().lower().replace(" ", "")
    # Numeric + unit pattern: "1.30m", "A51m", "9:91in", "85km", "+32tn"
    if re.search(r'[\d][\d.]*\s*[mk]?(m|km|tn|th|in|cm|mm|st|nd|rd|h)\b', text.strip().lower()):
        return True
    # Pure timestamps/distances: "+ 32tn", "1:35m", "1/200km"
    if re.match(r'^[+\-]?\s*[\d.,:;/]+\s*[mk]?(m|km|h|tn)?$', text.strip()):
        return True
    # Watermark patterns (any variant of MKIceAndFire)
    wm_patterns = ["iceandfire", "mkice", "kiceandfire", "miceandfire",
                   "mkiceand", "iceandf", "icean", "iceand",
                   "mklce", "micke", "mkand", "iceand"]
    if any(w in t for w in wm_patterns):
        return True
    # Vehicle IDs / plate numbers: "LIC-0086", "LUX-006", "5M00003"
    if re.match(r'^[A-Z]{2,5}[-\s]?\d{3,6}$', text.strip()):
        return True
    # Short numeric-heavy text: "22min", "+72inh", "-56thin", "259m"
    t = text.strip()
    if len(t) < 12 and re.search(r'\d', t) and not re.search(r'[.!?]', t):
        if sum(1 for c in t if c.isalpha()) < len(t) * 0.6:
            return True
    return False


def _ask_llm(prompt: str) -> str:
    """Send a prompt to Ollama, return response text."""
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": "llama3.2:1b",
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 30, "temperature": 0},
            },
            timeout=30,
        )
        return resp.json().get("response", "").strip()
    except Exception as e:
        print(f"  [LLM offline, using heuristic] {str(e)[:60]}")
        return "HEURISTIC"  # Signal to use fallback


def is_subtitle_batch(texts: list[str], game: str = "") -> list[bool]:
    """Ask LLM to classify multiple texts as subtitle or not.

    Returns list of bool (True = keep as subtitle).
    """
    if not texts:
        return []

    game_hint = f" from {game}" if game else ""
    numbered = "\n".join(f'  [{i+1}] "{t}"' for i, t in enumerate(texts))

    prompt = (
        f"These texts were detected in a video game screenshot{game_hint}.\n\n"
        f"{numbered}\n\n"
        "Which of these are character dialogue/subtitles? Dialogue means: "
        "sentences spoken by characters during conversations or cutscenes, "
        "usually at the bottom of the screen.\n\n"
        "NOT dialogue: credit names (ALL CAPS), HUD text (BULLET, HEALTH), "
        "watermarks (MKIceAndFire), UI hints (Press X), single words from "
        "signs, garbled OCR text, random characters.\n\n"
        "Answer with ONLY the numbers of dialogue texts, like: 1,3,5\n"
        "If none are dialogue, answer: none"
    )

    answer = _ask_llm(prompt)

    if answer == "HEURISTIC":
        return [_heuristic_check(t) for t in texts]

    print(f"    LLM: {answer}")

    # Parse numbers from answer
    import re
    nums = re.findall(r'\d+', answer)
    indices = set(int(n) - 1 for n in nums if 1 <= int(n) <= len(texts))

    return [i in indices for i in range(len(texts))]


def run_text_filter(config: PipelineConfig):
    """Filter labeled texts with Ollama LLM."""
    texts_path = os.path.join(config.labeled_labels_dir, "texts.json")
    if not os.path.exists(texts_path):
        print("[TextFilter] No texts.json found. Run --label first.")
        return

    with open(texts_path, "r", encoding="utf-8") as f:
        texts_map = json.load(f)

    removed = 0
    kept_frames = 0
    new_texts_map = {}
    total = len(texts_map)

    for i, (name, texts) in enumerate(sorted(texts_map.items())):
        label_path = os.path.join(config.labeled_labels_dir, f"{name}.txt")
        if not os.path.exists(label_path):
            continue

        with open(label_path, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")

        # Three-tier filter:
        # 1. _definitely_garbage → hard delete, no LLM can save
        # 2. _heuristic_check → keep unless LLM says delete
        # 3. LLM → only consulted for borderline cases
        definite_no = [_definitely_garbage(t) for t in texts]
        heuristic = [_heuristic_check(t) for t in texts]

        # If all pass heuristics: keep all, no LLM needed
        if all(heuristic):
            keep_flags = [True] * len(texts)
        elif all(definite_no[i] or not heuristic[i] for i in range(len(texts))):
            # All either definitely garbage or fail heuristic
            # Only ask LLM about borderline ones (fail heuristic but not definitely garbage)
            borderline = [i for i in range(len(texts))
                         if not definite_no[i] and not heuristic[i]]
            if borderline:
                llm_results = is_subtitle_batch(texts)
                keep_flags = []
                for i in range(len(texts)):
                    if heuristic[i]:
                        keep_flags.append(True)
                    elif definite_no[i]:
                        keep_flags.append(False)  # hard delete
                    else:
                        llm_keep = i < len(llm_results) and llm_results[i]
                        if llm_keep:
                            print(f"  [LLM SAVED] {name}: \"{texts[i][:60]}\"")
                        keep_flags.append(llm_keep)
            else:
                keep_flags = heuristic  # all fails are hard garbage
        else:
            # Mixed — some pass heuristic, some borderline, some garbage
            borderline = [i for i in range(len(texts))
                         if not definite_no[i] and not heuristic[i]]
            if borderline:
                llm_results = is_subtitle_batch(texts)
                keep_flags = []
                for i in range(len(texts)):
                    if heuristic[i] or definite_no[i]:
                        keep_flags.append(heuristic[i])
                    else:
                        llm_keep = i < len(llm_results) and llm_results[i]
                        if llm_keep:
                            print(f"  [LLM SAVED] {name}: \"{texts[i][:60]}\"")
                        keep_flags.append(llm_keep)
            else:
                keep_flags = heuristic

        new_lines = []
        new_texts = []
        for line, text, keep in zip(lines, texts, keep_flags):
            if keep:
                new_lines.append(line)
                new_texts.append(text)
            else:
                removed += 1
                print(f"  [NOISE] {name}: \"{text[:70]}\"")

        if new_lines:
            with open(label_path, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines) + "\n")
            new_texts_map[name] = new_texts
            kept_frames += 1
        else:
            os.remove(label_path)

        if (i + 1) % 20 == 0:
            print(f"[TextFilter] {i+1}/{total} kept={kept_frames} removed={removed}")

    with open(texts_path, "w", encoding="utf-8") as f:
        json.dump(new_texts_map, f, ensure_ascii=False)

    print(f"[TextFilter] Done. {kept_frames} frames kept, {removed} texts removed.")
