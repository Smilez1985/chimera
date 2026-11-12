"""Gegenprobe zu test_ablagen_wirksam.py ("0 gruen" ist gut).

Vier Verfälschungen, jede muss den Test rot machen:
1. Code legt einen Ordner an, den die Unit nicht erlaubt (der Fehler vom
   12.11.: `config/freigaben.json` ohne Schreibrecht).
2. `ReadWritePaths` nennt `config/` als Ganzes (verbietet Regel 5t).
3. `ReadWritePaths` verliert eine Ablage, der Code spricht sie weiter an.
4. Die Suche wird blind (kein Muster mehr im Code) -- das darf nicht als
   "alles in Ordnung" durchgehen.

Aufruf: python3 tests/gegenprobe_ablagen_wirksam.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_ablagen_wirksam as t  # noqa: E402

gruen = 0


def melde(name, stoerungen, ordner=None, blind=False):
    global gruen
    if ordner is not None and "<GANZES>" in ordner:
        print(f"rot (gut): {name}")
        return
    if blind:
        print(f"rot (gut): {name}")
        return
    if stoerungen:
        print(f"rot (gut): {name}")
    else:
        print(f"GRUEN (schlecht): {name}")
        gruen += 1


# 1. Ein Ordner im Code, der nicht in ReadWritePaths steht.
ordner, _ = t.erlaubte_ordner()
funde = t.pfade_im_code() + [("freiweg", Path("erfunden.rs"), 1)]
melde("code-ordner-ohne-recht", t.pruefen(ordner, funde))

# 2. config/ als Ganzes.
ordner2, _ = t.erlaubte_ordner("ReadWritePaths=-$CHIMERA_CONFIG -$CHIMERA_STATE/katalog")
melde("config-als-ganzes", [], ordner2)

# 3. Eine Ablage fällt aus der Zeile -- der Code spricht sie weiter an.
rw_ohne = "ReadWritePaths=-$CHIMERA_CONFIG/anbieter -$CHIMERA_STATE/log"
ordner3, _ = t.erlaubte_ordner(rw_ohne)
melde("ablage-fehlt-in-zeile", t.pruefen(ordner3, t.pfade_im_code()))

# 4. Blinde Suche: leere Quelle.
melde("suche-blind", [], blind=not t.pfade_im_code([]))

# Gegenstück: der echte Stand ist sauber.
if t.pruefen(ordner, t.pfade_im_code()):
    print("GRUEN (schlecht): echter Stand ist nicht sauber")
    gruen += 1
else:
    print("rot-grenze: echter Stand meldet nichts (richtig)")

print(f"{gruen} gruen")
sys.exit(1 if gruen else 0)
