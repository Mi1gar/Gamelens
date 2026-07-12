import re

class TextValidator:
    """
    Heuristic filters to validate OCR results.
    """
    
    @staticmethod
    def is_valid_text(text: str) -> bool:
        if not text:
            return False
            
        # 1. Length Check
        if len(text) < 4: 
            return False # Too short to be a valid subtitle usually
            
        # 2. Alphabet Ratio (Avoids "11.1..11_")
        # Count letters
        alpha_count = sum(c.isalpha() for c in text)
        if alpha_count / len(text) < 0.4: # Relaxed from 0.5
            # Less than 40% letters -> Likely noise/HP bar/Ammo count
            return False
            
        # 3. Average Word Length (Avoids "i l i l u l")
        words = text.split()
        if not words:
            return False
            
        avg_len = sum(len(w) for w in words) / len(words)
        if avg_len < 2.0: # Relaxed from 2.5
            # Average word length too small -> Likely noise
            return False
            
        # 4. Consonant/Vowel ratio (Basic gibberish check)
        # "lluilltulll" -> mostly consonants.
        # This is complex for all languages, but for English/Turkish:
        # If a word is 8+ chars and has no vowels, it's suspicious.
        # Let's stick to regex valid patterns.
        
        # 5. Game UI control hints filter
        # "Use RB to slow", "Tap to ride", "Press X to", "Hold A to"
        if re.search(r'\b(Use|Tap|Press|Hold)\s+(\w+\s+)?to\b', text, re.IGNORECASE):
            return False
        # "Use i to follow", "Use (i to follow" — with special chars
        if re.search(r'\bUse\s+[\(\[\w]+\s+to\b', text, re.IGNORECASE):
            return False

        # 6. Watermark / YouTube title filter
        # Long ALL CAPS (watermarks, video titles)
        if len(text) > 50 and text.isupper():
            return False
        # Very long text (likely watermark/banner regardless of case)
        if len(text) > 80:
            return False
        # YouTube-style title with mixed case but too long to be subtitle
        if len(text) > 60 and re.search(r'\b(4K|60FPS|Gameplay|Walkthrough|FULL GAME|1080p)\b', text, re.IGNORECASE):
            return False

        # 7. Garbage pattern check
        # Repeated small chars
        if re.search(r'(.)\1\1\1', text): # 4 repeating chars
            return False

        # 8. [REMOVED] Common Word Check & Dictionary Density
        # This was too strict for game dialogue with varied vocabulary.
        # It was causing valid sentences like "Guards under lockdown" to be dropped
        # because those words weren't in the tiny 150-word vocab.
        # We will rely on length, avg_word_length, and alpha checks.
                
        # 7. Vertical Noise Check (Corrugated textures)

        # 7. Vertical Noise Check (Corrugated textures)
        # Strings like "lI1 ll lI" -> High variance of vertical chars
        vertical_chars = set("il1|!/()[]")
        vertical_count = sum(1 for c in text.lower() if c in vertical_chars)
        if len(text) > 10 and (vertical_count / len(text) > 0.4):
            # If > 40% of chars are vertical sticks, it's likely fence/grate noise
            return False
            
        return True

    @staticmethod
    def cleanup_text(text: str) -> str:
        # Remove pipe chars often confused with I or l
        # But 'I' is valid.
        text = text.replace('|', 'I') 
        # Fix common OCR weirdness
        text = re.sub(r'\s+', ' ', text).strip()
        return text
