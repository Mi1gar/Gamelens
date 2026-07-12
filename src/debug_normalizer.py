import sys
import os
sys.path.append(os.getcwd())

from src.core.text_cleaner import TextNormalizer

sentences = [
    "I'm gonna get 'em all!",
    "C'mon Artyom, we gotta move!",
    "Dunno whatcha talkin' bout.",
    "Hey dude, watch out!",
    "Ain't no way I'm goin' down there.",
    "Shut up and gimme the ammo.",
    "H.u.n.t.e.r was here 1'm sure.", # OCR test
    "It's | to use for covers.", # OCR test
    "Yo pal, that looks like a hell of a fight.",
    "Lemme see if I can fix this shit."
]

print(f"{'ORIGINAL':<40} | {'NORMALIZED':<40}")
print("-" * 85)

for s in sentences:
    norm = TextNormalizer.normalize(s)
    print(f"{s:<40} | {norm:<40}")
