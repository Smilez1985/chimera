#!/usr/bin/env python3
"""Tests für die Ruhe-Bildrate (DESIGN Regel 7a, Ergänzung 3.11.2026).

Warum: Am Pi gemessen kostete der Zeichner im Leerlauf 29,7 % eines Kerns bei
577 Schreibaufrufen je Sekunde. Der Grund war nicht der Transport, sondern die
Bildrate: Das Gesicht schwingt in Ruhe (sway 2,2 px), dadurch ist jedes Bild
flächig anders — 44 bis 60 % der Pixel je Rahmen, gemessen über 20 Rahmen.

Vorgabe smilez (3.11.): Ruhe mit **2 Bildern/s**, volle Rate nur als „Blitz"
bei Blinzeln, Sprechen, Zustandswechsel. Damit das bei 2 Bildern/s nicht
einfriert, hängt das Blinzeln an der Uhr statt an der Bildzahl.

Geprüft wird die echte Bibliothek; das Panel ist eine Attrappe, die nur
zählt, wie oft gezeichnet wurde.
"""

import os
import sys
import time
import threading
from pathlib import Path

SRC = Path(os.environ.get("CHIMERA_SRC")
           or Path(__file__).resolve().parent.parent / "src")
sys.path.insert(0, str(SRC))

from chimera.render import avatar as A  # noqa: E402
from chimera.render.avatar import NoisyRenderer, State  # noqa: E402

PASS = FAIL = 0

def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")

def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")

def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


class ZaehlPanel:
    """Attrappe: nimmt Bilder an und zählt sie, sonst nichts."""

    width = 240
    height = 280
    fps = 15

    def __init__(self):
        self.bilder = 0
        self.letztes = None

    def show(self, img):
        self.bilder += 1
        self.letztes = img

    def backlight(self, *a, **k):        # noqa: D401
        pass


def bilder_in(sekunden, *, ruhe_fps=None, mood=None, bei=None):
    """Lässt die echte Schleife laufen und zählt die gezeichneten Bilder."""
    p = ZaehlPanel()
    r = NoisyRenderer(State(), p, ruhe_fps=ruhe_fps, thermal_path="")
    if mood:
        r.state.mood_name = mood
    stop = threading.Event()
    if bei:
        bei(r)
    faden = threading.Thread(target=r.run, args=(stop,), daemon=True)
    faden.start()
    time.sleep(sekunden)
    # Stand VOR dem Halt: ``run()`` schickt beim Beenden ein schwarzes
    # Abschaltbild, das zählt hier nicht mit (sonst wäre „Ruhe 0" nie 0).
    waehrend = p.bilder
    stop.set()
    faden.join(timeout=5)
    return waehrend, p.bilder


print("== 1. Ruhe-Bildrate folgt dem Panel ==")
p = ZaehlPanel()
r = NoisyRenderer(State(), p, thermal_path="")
check("Vorgabe: 2 Bilder/s in Ruhe", r.RUHE_FPS, 2)
check("volle Rate bleibt 15", r.TARGET_FPS, 15)
check("Ruhe-Zeit", round(r.RUHE_FRAME_TIME, 3), 0.5)

r0 = NoisyRenderer(State(), ZaehlPanel(), target_fps=1, thermal_path="")
check("Ruhe wird nie schneller als das Panel", r0.RUHE_FPS, 1)

# Die Ruhe-Rate ist eine Eigenschaft des Panels (Regel 7a) — wer sie nicht
# setzt, bekommt die Vorgabe der Basisklasse.
from chimera.displays.base import Panel as _Panel  # noqa: E402
check("Panel traegt die Ruhe-Rate", _Panel.ruhe_fps, 2)

class StillPanel(ZaehlPanel):
    ruhe_fps = 0

r_null = NoisyRenderer(State(), StillPanel(), thermal_path="")
check("Panel ohne Ruhe-Rate: nicht zeichnen", r_null.RUHE_FPS, 0)

r00 = NoisyRenderer(State(), ZaehlPanel(), ruhe_fps=0, thermal_path="")
check("Ruhe 0 heißt: nicht zeichnen", r00.RUHE_FRAME_TIME, 0.0)

r99 = NoisyRenderer(State(), ZaehlPanel(), ruhe_fps=99, thermal_path="")
check("zu hohe Ruhe-Rate wird gekappt", r99.RUHE_FPS, 15)


print("== 2. Wann die volle Rate gilt ==")
p = ZaehlPanel()
r = NoisyRenderer(State(), p, thermal_path="")
r.naechstes_blinzeln = time.monotonic() + 60.0
check("IDLE in Ruhe: keine volle Rate", r._volle_rate(), False)

r.state.mood_name = "SPEAK"
check("beim Sprechen: volle Rate", r._volle_rate(), True)
r.state.mood_name = "TALK"
check("beim Reden: volle Rate", r._volle_rate(), True)

r.state.mood_name = "IDLE"
r.naechstes_blinzeln = time.monotonic() + 60.0
r.wecken(0.5)
check("nach wecken(): volle Rate", r._volle_rate(), True)
time.sleep(0.55)
check("nach Ablauf wieder Ruhe", r._volle_rate(), False)

# Blinzeln (mit Vorlauf) — sonst verschluckt die Ruhe es.
r.naechstes_blinzeln = time.monotonic() + 0.01
check("kurz vor dem Blinzeln: volle Rate", r._volle_rate(), True)
r.naechstes_blinzeln = time.monotonic() + 60.0
r.blink_beginn = time.monotonic()
r.blink_ende = time.monotonic() + 0.3
r.is_blinking = True
check("während des Blinzelns: volle Rate", r._volle_rate(), True)
r.is_blinking = False
r.blink_ende = 0.0


print("== 3. Blinzeln hängt an der Uhr, nicht an der Bildzahl ==")
p = ZaehlPanel()
r = NoisyRenderer(State(), p, thermal_path="")
jetzt = time.monotonic()
r.naechstes_blinzeln = jetzt - 0.01     # fällig
r.blink_ende = 0.0
r.render()
check("Blinzeln beginnt", r.is_blinking, True)
dauer = r.blink_ende - r.blink_beginn
check("Dauer in Sekunden (0,20–0,47 s)",
      A.BLINK_DAUER_MIN - 1e-9 <= dauer <= A.BLINK_DAUER_MAX + 1e-9, True)
check("nächster Abstand ist geplant", r.naechstes_blinzeln > r.blink_ende, True)

# Am Ende: Auge wieder offen, danach ein neuer Abstand von 3,0–8,7 s.
time.sleep(dauer + 0.05)
r.render()
check("nach der Dauer: wieder offen", r.is_blinking, False)
rest = r.naechstes_blinzeln - time.monotonic()
check("nächster Blink in 3,0–8,7 s",
      A.BLINK_PAUSE_MIN - 0.2 <= rest <= A.BLINK_PAUSE_MAX + 0.2, True)

# Der alte Zustand: Dauer in Bildern. Bei 2 Bildern/s wäre ein
# Drei-Bilder-Blinzeln 1,5 s lang — das ist der Fehler, den dieser Test sucht.
r2 = NoisyRenderer(State(), ZaehlPanel(), thermal_path="")
r2.naechstes_blinzeln = time.monotonic() - 0.01
r2.blink_ende = 0.0
r2.render()
check("kein bildweises Blinzeln", (r2.blink_ende - r2.blink_beginn) < 0.5, True)


print("== 4. Die Schleife zeichnet in Ruhe wirklich langsamer ==")
ruhe, ruhe_gesamt = bilder_in(1.2, ruhe_fps=2)
# Grosszuegige Grenzen: auf einem langsamen CI-Laeufer duerfen es
# weniger Bilder sein -- der Abstand zu 15/s muss aber bleiben.
check("Ruhe: 1–5 Bilder in 1,2 s (nicht 15/s)", 1 <= ruhe <= 5, True)
check("Ruhe: das Abschaltbild kommt obendrauf", ruhe_gesamt, ruhe + 1)

wach, _ = bilder_in(1.2, ruhe_fps=2, mood="SPEAK")
check("Sprechen: 8–22 Bilder in 1,2 s", 8 <= wach <= 22, True)

# Die Ruhe-Schleife schlaeft genau bis zum Blinzelbeginn (sonst waere das
# Blinzeln bei 0,5 s Bildabstand halb vorbei). Also muss sie hier von
# selbst frueher aufwachen und dann mit voller Rate zeichnen.
blinzelt, _ = bilder_in(0.6, ruhe_fps=2, bei=lambda r: setattr(
    r, "naechstes_blinzeln", time.monotonic() + 0.1))
check("geplantes Blinzeln weckt die Schleife (4–12 Bilder)", 4 <= blinzelt <= 12, True)

still, still_gesamt = bilder_in(0.6, ruhe_fps=0, bei=lambda r: setattr(
    r, "naechstes_blinzeln", time.monotonic() + 60))
check("Ruhe 0: während des Laufs kein Bild", still, 0)
check("Ruhe 0: nur das Abschaltbild", still_gesamt, 1)

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
