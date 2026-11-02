"""Gegenprobe zu test_regelnamen.py: der Test muss rot werden, wenn

1. jemand eine neue nummerierte Regel anlegt,
2. jemand eine Regel umbenennt, ohne sie aus dem Altbestand zu nehmen.

Aufruf: python3 tests/gegenprobe_regelnamen.py   ("0 gruen" ist gut)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_regelnamen as t  # noqa: E402

text = t.DESIGN.read_text(encoding="utf-8")
gruen = 0


def erwarte_rot(name, neu_text):
    global gruen
    neu, weg = t.pruefen(neu_text, t.ALTBESTAND)
    if neu or weg:
        print(f"rot (gut): {name}")
    else:
        print(f"GRUEN (schlecht): {name}")
        gruen += 1


erwarte_rot("neue-nummer", text + "\n### Architekturregel 99z \u2014 Neue Regel mit Nummer\n")
erwarte_rot("umbenannt-ohne-liste", text.replace("### Architekturregel 5n \u2014", "### Regel \u201eGateway\u201c \u2014", 1))
erwarte_rot("nummer-ohne-bindestrich-variante", text + "\n### Architekturregel 100 \u2014 x\n")
# Gegenstueck: der unveraenderte Text ist sauber
neu, weg = t.pruefen(text, t.ALTBESTAND)
if neu or weg:
    print("GRUEN (schlecht): unveraenderter Text ist nicht sauber", neu, weg)
    gruen += 1
else:
    print("rot (gut) entfaellt: unveraenderter Text ist sauber")
print(f"== {gruen} gruen ==")
sys.exit(1 if gruen else 0)
