import re

class TextNormalizer:
    """
    Advanced Text Normalization Engine for Game/Movie Subtitles.
    Transforms street slang, dialects, and OCR errors into Formal English
    to maximize Machine Translation (Argos/Marian) quality.
    """
    
    # 1. Basic Contractions & Street Slang
    SLANG_MAP = {
        r"\bgonna\b": "going to",
        r"\bwanna\b": "want to",
        r"\bgotta\b": "have to",
        r"\blemme\b": "let me",
        r"\bgimme\b": "give me",
        r"\boutta\b": "out of",
        r"\bkinda\b": "kind of",
        r"\bsorta\b": "sort of",
        r"\binnit\b": "is it not",
        r"\bdunno\b": "do not know",
        r"\bc'mon\b": "come on",
        r"\bcmon\b": "come on",
        r"\bcos\b": "because",
        r"\bcoz\b": "because",
        r"\bcause\b": "because",
        r"\bbout\b": "about",
        r"\btil\b": "until",
        r"\btill\b": "until",
        r"\b'em\b": "them",
        r"\bem\b": "them",
        r"\bya\b": "you",
        r"\byer\b": "your",
        r"\bnah\b": "no",
        r"\byeah\b": "yes",
        r"\byep\b": "yes",
        r"\baye\b": "yes",
        r"\bnope\b": "no",
        r"\bain't\b": "is not",     # Context dependent, but 'is not' covers most
        r"\bimma\b": "I will",
        r"\bi'ma\b": "I will",
        r"\by'all\b": "you all",
        r"\bhol'\b": "hold",
        r"\bsec\b": "second",
        r"\bbro\b": "brother",
        r"\bsis\b": "sister",
        r"\bdude\b": "friend",  # Helps translation context
        r"\bpal\b": "friend",
        r"\bmate\b": "friend",
        r"\bdamn\b": "curse", # Often implies raw emotion, 'lanet' translation is fine
        r"\bgoddammit\b": "damn it",
        r"\bmusta\b": "must have",
        r"\bshoulda\b": "should have",
        r"\bwoulda\b": "would have",
        r"\bcoulda\b": "could have",
        r"\bhell of a\b": "great",
        r"\bson of a bitch\b": "bastard", 
        r"\bsonuvabitch\b": "bastard",
        r"\bgotcha\b": "I understand",
        r"\bgetcha\b": "get you",
        r"\bwhatcha\b": "what do you",
        r"\bdontcha\b": "do you not",
        r"\bsee ya\b": "goodbye",
        r"\blookin'\b": "looking",
        r"\btrus'\b": "trust",
        r"\bgangsta\b": "gangster",
        r"\bmakin'\b": "making",
        r"\btalkin'\b": "talking",
        r"\bwalkin'\b": "walking",
        r"\brunin'\b": "running",
        r"\brunnin'\b": "running",
        r"\bcomin'\b": "coming",
        r"\bdoin'\b": "doing",
        r"\bnothin'\b": "nothing",
        r"\bsomethin'\b": "something",
        r"\beverythin'\b": "everything",
        r"\ball right\b": "alright",
        r"\balrite\b": "alright",
        r"\baight\b": "alright",
        r"\biight\b": "alright",
        r"\bLets\b": "Let's", # Fix "Hadis" translation error from "Lets move"
    }
    
    # 2. Contextual Phrase Repairs (Better Translation Targets)
    IDIOM_MAP = {
        r"\bwhat the hell\b": "what is happening",
        r"\bget out of here\b": "leave immediately",
        r"\bshut up\b": "be quiet",
        r"\bshut your mouth\b": "be quiet",
        r"\bpiss off\b": "go away",
        r"\bfuck off\b": "go away",
        r"\bcome on, move\b": "hurry up",
        r"\blet's roll\b": "let us go",
        r"\bwatch out\b": "be careful",
        r"\bheads up\b": "attention",
        r"\bmy bad\b": "my mistake",
        r"\bno way\b": "impossible",
        r"\byou kidding\?\b": "are you joking?",
        r"\bfair enough\b": "acceptable",
        r"\bnever mind\b": "forget it",
        r"\bget lost\b": "go away", 
        r"\balright\b": "okay", 
        r"\bton o\b": "ton of",
        r"\bshit\b": "damn",
        r"\bfire at will\b": "shoot freely", # "Ateş olacak" -> "Serbest atış"
        r"\bgive me a hand\b": "help me", # "El ver" -> "Yardım et"
        r"\broger\b": "understood", # "Roger" -> "Anlaşıldı"
        r"\bcome in\b": "respond", # Radio: "Come in Ulman" -> "Cevap ver Ulman"
        # r"\bover\b": "", # REMOVED - was breaking "blow over", "come over" etc.
        r"\bget a fix\b": "locate", # "Fix" -> "Konumla/Bul"
        r"\bwatch your backs\b": "look out behind you", # "Arkanızı kollayın"
        r"\bhold the line\b": "hold position", # "Hattı tut" -> "Mevziyi koru"
        r"\bthat's affirmative\b": "yes", # "Bu olumlu" -> "Evet/Anlaşıldı"
        r"\bform a circle\b": "make a circle", # Simplification
    }
    
    # Specific OCR Corrections (Game Specific)
    OCR_FIXES = {
        r"\bmmo\b": "ammo",
        r"\bknowl\b": "know",
        r"\bill\b": "I'll", 
        r"\bhowmuch\b": "how much",
        r"\bhowmuchyou\b": "how much you",
        r"\bgotchal\b": "gotcha",
        r"\bauxilary\b": "auxiliary",
        r"\bauxilaryhand\b": "auxiliary hand",
        r"\bandmed\b": "and med", # "andmed packs"
        r"\bose crates\b": "those crates", # "ose crates"
        r"\bdver\b": "Over", # "dver" -> "Over"
        r"\blne\b": "line", # "Hold the lne" -> "line"
        r"\bthah\b": "than", # "tougher thah" -> "than"
        r"\bhrt\b": "hit", # "hrt the surface" -> "hit"
        r"\bf ow\b": "follow", # "F ow me" -> "follow"
        r"\blisten'\b": "listen", # "listen'" -> "listen"
        r"\bShitl\b": "Shit", # "Shitl" -> "Shit"
        r"\blbrary\b": "library", # "lbrary" -> "library"
        r"\bAnu ka\b": "", # Gibberish removal
        # Common OCR digit/letter confusion
        r"\b1\b": "I",          # "Arthur and 1" -> "Arthur and I"
        r"\b0\b": "O",          # "C0ME" -> "COME"
        r"\b5\b": "S",          # "5TOP" -> "STOP"
        # Common OCR letter confusion (thin/serif fonts)
        r"\bfo\b": "to",        # "listen fo me" -> "listen to me"
        r"\bTenny\b": "Jenny",  # J->T confusion
        r"\bcholce\b": "choice", # c<->o swap
        # Missing space: "I" + common verb merges (OCR spacing errors)
        r"\bIloved\b": "I loved",
        r"\bIcan\b": "I can",
        r"\bIwill\b": "I will",
        r"\bIhave\b": "I have",
        r"\bIdid\b": "I did",
        r"\bIwas\b": "I was",
        r"\bIjust\b": "I just",
        r"\bIdont\b": "I do not",
        r"\bIknow\b": "I know",
        r"\bIthink\b": "I think",
        r"\bIneed\b": "I need",
        r"\bIsee\b": "I see",
        r"\bIwant\b": "I want",
        r"\bIgot\b": "I got",
        r"\bIam\b": "I am",
        r"\bIdidnt\b": "I did not",
        r"\bIcant\b": "I can not",
        r"\bIm\b": "I am",
        # 1 + verb → I + verb (OCR: "1loved" → "I loved")
        r"\b1loved\b": "I loved",
        r"\b1can\b": "I can",
        r"\b1will\b": "I will",
        r"\b1have\b": "I have",
        r"\b1did\b": "I did",
        r"\b1was\b": "I was",
        r"\b1just\b": "I just",
        r"\b1dont\b": "I do not",
        r"\b1know\b": "I know",
        r"\b1need\b": "I need",
        r"\b1want\b": "I want",
        r"\b1got\b": "I got",
        r"\b1am\b": "I am",
        r"\b1m\b": "I am",
        # Common OCR letter confusion in thin fonts
        r"\bbuslness\b": "business",
        r"\bslde\b": "side",
        r"\brlght\b": "right",
        r"\btalling\b": "tailing",
        r"\bmlght\b": "might",
        r"\bflght\b": "fight",
    }

    # Names that should NOT be translated (Entity Protection)
    PROPER_NAMES = {
        "artyom", "miller", "khan", "hunter", "bourbon", "ulmans", "ulman",
        "polis", "sparta", "ranger", "dark one", "d6", "melnik", "sasha", 
        "pavel", "anna", "lesnitsky", "corbut"
    }

    @staticmethod
    def normalize(text: str) -> str:
        if not text:
            return ""
            
        clean = text.strip()
        
        # --- 0. Pre-cleaning (Casing & Repetitions) ---
        # Convert ALL CAPS to Sentence case (Helps translation models significantly)
        # e.g. "FORM A CIRCLE" -> "Form a circle"
        if text.isupper() and len(text) > 4:
            clean = text.capitalize()
        else:
            clean = text
            
        # Remove direct repetitions (e.g. "Over Over", "Run Run")
        # Matches repeated words/phrases with spaces
        clean = re.sub(r'\b(.+?)( \1\b)+', r'\1', clean, flags=re.IGNORECASE)

        # --- 1. Strong OCR Cleaning ---
        # Remove UI Prompts: "(Esc)", "(Space)", "[E]"
        clean = re.sub(r'\([A-Za-z0-9]+\)', '', clean)
        clean = re.sub(r'\[[A-Za-z0-9]+\]', '', clean)

        # Fix attached words: "Hello.World" -> "Hello. World"
        clean = re.sub(r'([a-z])\.([A-Z])', r'\1. \2', clean)
        
        # Fix pipe/l confusion: "| like" -> "I like"
        # Use simple space lookup since \b fails on symbols
        clean = re.sub(r' \| ', ' I ', clean)
        clean = re.sub(r'^\| ', 'I ', clean) # Start of line
        
        # Fix "l" standing alone as "I": " l don't" -> " I don't"
        clean = re.sub(r'\s+l\s+', ' I ', clean)
        # Fix "1" as "I" if followed by apostrophe: "1'm" -> "I'm"
        clean = re.sub(r'\b1\'m\b', "I'm", clean)
        clean = re.sub(r'\b1\'ll\b', "I'll", clean)
        
        # --- 2b. Specific OCR Fixes ---
        for pattern, replacement in TextNormalizer.OCR_FIXES.items():
            clean = re.sub(pattern, replacement, clean, flags=re.IGNORECASE)

        # Fix "Ill" attached to words: "Illdraw" -> "I'll draw"
        # Look for "Ill" followed by lowercase letter
        clean = re.sub(r"\bIll([a-z]+)", r"I'll \1", clean)

        # --- 2c. Slang Expansion (Case Insensitive) ---
        for pattern, replacement in TextNormalizer.SLANG_MAP.items():
            clean = re.sub(pattern, replacement, clean, flags=re.IGNORECASE)

        # Fix -in' endings manually if map missed (talkin' -> talking)
        # Regex: word ending in in' followed by space or end
        clean = re.sub(r"(\w+)in'(?=\s|$|\.|!)", r"\1ing", clean, flags=re.IGNORECASE)

        # --- 3. Idiom Simplification ---
        for pattern, replacement in TextNormalizer.IDIOM_MAP.items():
            clean = re.sub(pattern, replacement, clean, flags=re.IGNORECASE)
            
        # --- 4. Final Polish ---
        # Remove repeated punctuation: "???" -> "?"
        clean = re.sub(r'\?+', '?', clean)
        clean = re.sub(r'\!+', '!', clean)
        
        # --- 5. Entity Protection (Capitalization) ---
        for name in TextNormalizer.PROPER_NAMES:
            pattern = r'\b' + re.escape(name) + r'\b'
            clean = re.sub(pattern, name.capitalize(), clean, flags=re.IGNORECASE)
            
        return clean
