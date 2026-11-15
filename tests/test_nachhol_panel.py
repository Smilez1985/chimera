"""Die Anzeige, die beim Start belegt war, wird nachgeholt (15.11.2026).

Fund am Pi: Beim Installerlauf startet ``98-service`` den Agenten, während der
Fortschrittsbalken des Installers das Panel hält. Der Dienst bekam
``[Errno 16] Leitung belegt auf /dev/gpiochip0: [27, 4]``, fiel auf
``NullPanel`` und blieb **dauerhaft dunkel** — obwohl der Zeichner zwei
Sekunden später endete.

Geprüft wird ``NachholPanel`` selbst (keine Nachbildung der Entscheidung) und
``open_panel`` aus ``chimera/display/panel.py`` mit einem echten
Anzeigemodul-Profil. Nur das Öffnen der Leitung ist eine Attrappe: die
Hardware gibt es hier nicht.

Aufruf: python3 tests/test_nachhol_panel.py [--gegenprobe]
"""
from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera.displays import registry  # noqa: E402
from chimera.displays.base import NullPanel, Panel  # noqa: E402
from chimera.displays.nachhol import NachholPanel  # noqa: E402

GEGENPROBE = "--gegenprobe" in sys.argv
PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def pruefe(ist, soll, was):
    (ok if ist == soll else bad)(f"{was}: {ist!r}" + ("" if ist == soll
                                                      else f" (erwartet {soll!r})"))


class Uhr:
    """Einsetzbare Uhr — der Plan wird ohne Warten geprüft."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def vor(self, sekunden: float) -> None:
        self.t += sekunden


class Belegt(OSError):
    """Was die Leitung im Fehlerfall meldet (wie das Gerät)."""

    def __init__(self) -> None:
        super().__init__(f"[Errno {errno.EBUSY}] Leitung belegt auf "
                         f"/dev/gpiochip0: [27, 4]")


class Attrappe(Panel):
    """Ein Panel, das nur mitschreibt, was man ihm zeigt."""

    def __init__(self) -> None:
        self.bilder = 0
        self.licht = []
        self.farben = []

    def show(self, image) -> None:
        self.pruefe_groesse(image)
        self.bilder += 1

    def backlight(self, percent: int) -> None:
        self.licht.append(percent)

    def led(self, r: int, g: int, b: int) -> None:
        self.farben.append((r, g, b))


class Leitung:
    """Öffnen, das erst nach ``frei_nach`` Versuchen gelingt."""

    def __init__(self, frei_nach: int | None = None) -> None:
        self.versuche = 0
        self.frei_nach = frei_nach          # None = nie frei
        self.panel = Attrappe()

    def __call__(self, typ: str):
        self.versuche += 1
        if self.frei_nach is None or self.versuche <= self.frei_nach:
            raise Belegt()
        return self.panel


def bild(breite: int, hoehe: int, farbe=(10, 20, 30)):
    from PIL import Image
    return Image.new("RGB", (breite, hoehe), farbe)


def neu(plan=(2.0, 2.0, 5.0), uhr=None, leitung=None, typ="whisplay"):
    uhr = uhr or Uhr()
    leitung = leitung or Leitung()
    profil = registry.profil(typ)
    p = NachholPanel(typ, "CHIMERA_ANZEIGE", Belegt(), profil=profil,
                     abstaende=plan, uhr=uhr, oeffnen=leitung)
    return p, uhr, leitung, profil


print("== 1. Zustand vor dem ersten Versuch")
p, uhr, leitung, profil = neu()
pruefe(p.bereit, False, "bereit")
pruefe(p.width, profil.breite, "Breite aus dem Profil")
pruefe(p.height, profil.hoehe, "Höhe aus dem Profil")
pruefe(p.fps, int(profil.bildrate), "Bildrate aus dem Profil")
pruefe("nachgeholt" in p.hinweis, True, "hinweis nennt das Nachholen")
pruefe("27, 4" in p.hinweis, True, "hinweis nennt den Grund")
pruefe(p.versuche, 0, "noch kein Versuch")

print("== 2. Belegte Leitung: Bild wird verworfen, nicht gezeichnet")
p, uhr, leitung, profil = neu(plan=(2.0, 2.0, 5.0))
p.show(bild(profil.breite, profil.hoehe))
pruefe(p.versuche, 1, "erster Versuch beim ersten Bild")
pruefe(p.verworfen, 1, "Bild verworfen")
pruefe(leitung.panel.bilder, 0, "nichts auf dem Glas")
pruefe(p.bereit, False, "bereit bleibt falsch")

print("== 3. Der Plan hält den Abstand ein")
p.show(bild(profil.breite, profil.hoehe))
pruefe(leitung.versuche, 1, "kein zweiter Versuch vor Ablauf")
uhr.vor(1.9)
p.show(bild(profil.breite, profil.hoehe))
pruefe(leitung.versuche, 1, "1,9 s sind zu früh")
uhr.vor(0.2)
p.show(bild(profil.breite, profil.hoehe))
pruefe(leitung.versuche, 2, "nach 2,0 s wird es erneut versucht")

print("== 4. Leitung frei: Bild geht durch")
p, uhr, leitung, profil = neu(plan=(2.0, 2.0, 5.0), leitung=Leitung(frei_nach=2))
p.show(bild(profil.breite, profil.hoehe))          # Versuch 1: belegt
pruefe(p.bereit, False, "nach dem ersten Versuch noch blind")
uhr.vor(2.1)
p.show(bild(profil.breite, profil.hoehe, (200, 0, 0)))   # Versuch 2: belegt
pruefe(p.bereit, False, "nach dem zweiten Versuch noch blind")
uhr.vor(2.1)
p.show(bild(profil.breite, profil.hoehe, (0, 0, 200)))   # Versuch 3: frei
pruefe(p.bereit, True, "nach dem dritten Versuch bereit")
pruefe(p.hinweis, "", "hinweis geräumt")
pruefe(leitung.panel.bilder, 2,
       "verworfenes Bild nachgeholt + das aktuelle")
leitung.panel.bilder = 0
p.show(bild(profil.breite, profil.hoehe))
pruefe(leitung.panel.bilder, 1, "danach zeichnet das echte Panel")

print("== 5. Das zuletzt verworfene Bild wird sofort gezeichnet")
p, uhr, leitung, profil = neu(plan=(2.0,), leitung=Leitung(frei_nach=1))
p.show(bild(profil.breite, profil.hoehe, (1, 2, 3)))      # verworfen
pruefe(leitung.panel.bilder, 0, "noch nichts")
uhr.vor(2.1)
p.backlight(40)                                            # weckt den Versuch
pruefe(p.bereit, True, "mit dem Öffnen bereit")
pruefe(leitung.panel.bilder, 1, "verworfenes Bild wird nachgeholt")

print("== 6. Licht und LED gehen nach")
p, uhr, leitung, profil = neu(plan=(2.0,), leitung=Leitung(frei_nach=1))
p.show(bild(profil.breite, profil.hoehe))
p.backlight(35)
p.led(0, 255, 0)
pruefe(leitung.panel.licht, [], "kein Licht, solange blind")
uhr.vor(2.1)
p.show(bild(profil.breite, profil.hoehe))
pruefe(leitung.panel.licht, [35], "Licht nachgezogen")
pruefe(leitung.panel.farben, [(0, 255, 0)], "LED nachgezogen")

print("== 7. Nach erschöpftem Plan: weiter im letzten Abstand, mit Warnung")
p, uhr, leitung, profil = neu(plan=(1.0, 1.0), leitung=Leitung(frei_nach=None))
for _ in range(4):
    p.show(bild(profil.breite, profil.hoehe))
    uhr.vor(1.1)
pruefe(p.versuche, 4, "vier Versuche")
pruefe("nicht zu bekommen" in p.hinweis, True, "hinweis sagt es")
pruefe(p.bereit, False, "bleibt blind")
leitung.versuche = 0
uhr.vor(-1.1)                               # zurück auf den letzten Versuch
p.show(bild(profil.breite, profil.hoehe))
pruefe(leitung.versuche, 0, "kurz vor dem nächsten Versuch: keiner")
uhr.vor(1.05)
p.show(bild(profil.breite, profil.hoehe))
pruefe(leitung.versuche, 1, "nach Ablauf wieder versucht")
leitung.frei_nach = 0                       # jetzt ist die Leitung frei
uhr.vor(1.1)
p.show(bild(profil.breite, profil.hoehe))
pruefe(p.bereit, True, "auch nach dem Plan kommt es noch herein")
pruefe(p.hinweis, "", "hinweis danach geräumt")

print("== 8. open_panel: belegt heißt nachholen, unbrauchbar heißt blind")
from chimera.display import panel as fassade  # noqa: E402

echt_oeffne = registry.oeffne


def belegt(typ, **kw):
    raise Belegt()


def kaputt(typ, **kw):
    raise ImportError("whisplay: Modul fehlt")


os.environ["CHIMERA_ANZEIGE"] = "whisplay"
registry.oeffne = belegt
try:
    fassade.registry.oeffne = belegt
    p1 = fassade.open_panel()
    pruefe(isinstance(p1, NachholPanel), True, "belegte Anzeige → NachholPanel")
    pruefe(p1.bereit, False, "und noch blind")
    pruefe(p1.width, profil.breite, "Maße stimmen trotzdem")
    fassade.registry.oeffne = kaputt
    p2 = fassade.open_panel()
    pruefe(isinstance(p2, NullPanel), True, "unbekanntes/defektes Modul → NullPanel")
    pruefe(p2.bereit, False, "NullPanel ist nie bereit")
    os.environ["CHIMERA_ANZEIGE"] = "gibtesnicht"
    p3 = fassade.open_panel()
    pruefe(isinstance(p3, NachholPanel), False,
           "unbekannter Typ wird nicht nachgeholt")
    pruefe("gibtesnicht" in p3.hinweis, True, "Grund steht im hinweis")
finally:
    registry.oeffne = echt_oeffne
    fassade.registry.oeffne = echt_oeffne
    os.environ.pop("CHIMERA_ANZEIGE", None)

print("== 9. Panel ohne Anzeige zählt weiter (NullPanel unverändert)")
n = NullPanel(240, 280)
n.show(bild(240, 280))
pruefe(n.frames, 1, "zählt das Bild")
pruefe(n.bereit, False, "zeigt es aber nicht")

print(f"\n{PASS} ok, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
