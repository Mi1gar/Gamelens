import difflib

# Manual overrides for accurate quality and 0ms latency on common phrases
# Key: Normalized English text (lowercase)
# Value: Pre-defined Turkish translation
_DATA = {
    "rog": "Anlaşıldı",
    "roger": "Anlaşıldı",
    "copy": "Anlaşıldı",
    "copy that": "Anlaşıldı",
    "understood": "Anlaşıldı",
    "affirmative": "Olumlu",
    "negative": "Olumsuz",
    "stay calm": "Sakin olun",
    "don't move": "Kımıldama",
    "watch out": "Dikkat et",
    "fire at will": "Serbest atış",
    "hold fire": "Ateş kes",
    "hold your fire": "Ateşi kesin",
    "cease fire": "Ateş kes",
    "reload": "Şarjör değiştiriyorum",
    "reloading": "Şarjör değiştiriyorum",
    "contact": "Temas var",
    "enemy down": "Düşman etkisiz",
    "target down": "Hedef etkisiz",
    "tango down": "Düşman indirildi",
    "got him": "Onu hakladım",
    "form a circle": "Çember oluşturun",
    "watch your backs": "Arkanızı kollayın",
    "watch your backs, boys": "Arkanızı kollayın beyler",
    "hold the line": "Hattı koruyun",
    "hold position": "Mevziyi koruyun",
    "run": "Kaç",
    "help me": "Yardım edin",
    "i'm hit": "Vuruldum",
    "man down": "Vurulan var",
    "medic": "Sıhhiye",
    "follow me": "Beni takip et",
    "let's go": "Gidelim",
    "let's move": "Hadi",
    "move out": "İlerleyin",
    "clear": "Temiz",
    "all clear": "Bölge temiz",
    "shit": "Lanet olsun",
    "damn": "Lanet olsun",
    "damn it": "Lanet olsun",
    "what the hell": "Neler oluyor?",
    "get out of here": "Buradan git",
    "leave me alone": "Beni yalnız bırak",
    "thank you": "Teşekkürler",
    "thanks": "Sağ ol",
    "sorry": "Üzgünüm",
    "stop": "Dur",
    "wait": "Bekle",
    "here they come": "Geliyorlar",
    "incoming": "Geliyorlar",
    "demons": "İblisler",
    "load your weapon": "Silahını doldur",
    "check your ammo": "Cephaneni kontrol et",
}

# Integrate Hybrid Subtitle Loader
try:
    from .subtitle_loader import get_loader
    print("[TranslationMemory] Loading imported subtitles...")
    imported_data = get_loader().load()
    if imported_data:
        print(f"[TranslationMemory] Merging {len(imported_data)} imported phrases into Hybrid Memory.")
        _DATA.update(imported_data)
except Exception as e:
    print(f"[TranslationMemory] Warning: Failed to load imports: {e}")

class TranslationMemory:
    """
    Fuzzy matching engine for pre-defined translations.
    Allows for O(1) or O(N) lookup depending on implementation, ensuring
    0ms latency for known phrases even with slight OCR errors.
    """
    
    @staticmethod
    def get_exact(text: str):
        """O(1) Exact lookup"""
        return _DATA.get(text.lower().strip(".,!?"))

    @staticmethod
    def get_fuzzy(text: str, cutoff=0.85):
        """
        O(N) Fuzzy lookup using SequenceMatcher.
        Useful for catching OCR typos like "Fiire at will".
        """
        clean = text.lower().strip(".,!?")
        
        # 1. Exact match fast-path
        if clean in _DATA:
            return _DATA[clean]
            
        # 2. Fuzzy match
        # get_close_matches returns list, take top 1
        matches = difflib.get_close_matches(clean, _DATA.keys(), n=1, cutoff=cutoff)
        
        if matches:
            best_match = matches[0]
            # Debug print could go here
            return _DATA[best_match]
            
        return None

