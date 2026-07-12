"""
NLLB-200 600M distilled + CTranslate2 INT8 translator.
EN->TR quality: BLEU ~40-45 vs Argos BLEU ~25-30.
Speed: ~35-60ms on RTX 5070 (INT8 CUDA).
"""
import os
import re
import ctranslate2

_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models", "nllb-200-600m-ct2-int8")

_translator = None
_tokenizer = None
_tgt_token = None
_cache = {}


def _load():
    """Lazy-load CTranslate2 model + HF tokenizer (called on first translate)."""
    global _translator, _tokenizer, _tgt_token

    if _translator is not None:
        return

    model_dir = os.path.abspath(_MODEL_DIR)
    print(f"[NLLB] Loading from: {model_dir}")

    # HF tokenizer (adds source lang prefix automatically)
    from transformers import AutoTokenizer
    _tokenizer = AutoTokenizer.from_pretrained(
        model_dir,
        src_lang="eng_Latn",
        tgt_lang="tur_Latn",
    )

    # Target language token for decoder prefix
    _tgt_token = _tokenizer.convert_ids_to_tokens(
        _tokenizer.convert_tokens_to_ids("tur_Latn")
    )

    # CTranslate2 model (INT8, CUDA)
    for device, ct in [("cuda", "int8"), ("cpu", "int8")]:
        try:
            _translator = ctranslate2.Translator(
                model_dir, device=device, compute_type=ct,
            )
            print(f"[NLLB] {device.upper()} + {ct.upper()} enabled")
            break
        except Exception as e:
            print(f"[NLLB] {device} failed: {e}")

    # Warm-up
    translate("Hello")
    print("[NLLB] Ready.")


def translate(text: str) -> str:
    """Translate English text to Turkish. Returns empty string on failure."""
    if not text or len(text.strip()) < 2:
        return ""

    clean = text.strip()

    if clean in _cache:
        return _cache[clean]

    if _translator is None:
        try:
            _load()
        except Exception as e:
            print(f"[NLLB] Load failed: {e}")
            return ""

    try:
        # Encode with HF tokenizer (auto-adds eng_Latn prefix)
        encoded = _tokenizer(clean)["input_ids"]
        source_tokens = _tokenizer.convert_ids_to_tokens(encoded)

        result = _translator.translate_batch(
            [source_tokens],
            target_prefix=[[_tgt_token]],
            beam_size=1,
            max_decoding_length=256,
        )

        tokens = result[0].hypotheses[0]

        # Strip target language prefix token
        if tokens and tokens[0] == _tgt_token:
            tokens = tokens[1:]

        output_ids = _tokenizer.convert_tokens_to_ids(tokens)
        output = _tokenizer.decode(output_ids, skip_special_tokens=True)

        # Clean: strip leading "- " NLLB sometimes generates
        output = output.strip()
        output = re.sub(r'^-\s+', '', output)

        _cache[clean] = output
        return output

    except Exception as e:
        print(f"[NLLB] Error: {e}")
        return ""


def is_loaded() -> bool:
    return _translator is not None
