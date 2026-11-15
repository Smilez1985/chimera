"""Der Audio-Schalter: hart aus, hart an — und ehrlich über Fehler.

Am Whisplay-HAT gibt es **keinen** Mute-Schalter (am Pi gemessen:
`amixer -c whisplaysound scontrols` zeigt nur `mic` und `speaker`, beide
„volume volume-joined"). „Aus" heißt deshalb Lautstärke 0 %, „an" der
gemerkte Wert.

Aufruf: python3 tests/test_audio_schalter.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(os.environ.get("CHIMERA_SRC") or ROOT / "src")))

from chimera.audio_schalter import AudioSchalter  # noqa: E402

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
    if ist == soll:
        ok(f"{was}: {ist!r}")
    else:
        bad(f"{was}: {ist!r} (erwartet {soll!r})")


class Attrappe:
    """``schalter`` steuert, ob ``sget`` einen Mute-Schalter meldet."""
    """Merkt Aufrufe; beantwortet `sget` wie das Gerät (``Mono: 55 [55%]``)."""

    def __init__(self, rc=0, lautstaerke=55, schalter=False):
        self.rc = rc
        self.lautstaerke = lautstaerke
        self.schalter = schalter
        self.aufrufe: list[list[str]] = []

    def __call__(self, argv, *, lesen: bool = False):
        self.aufrufe.append(list(argv))
        if self.rc != 0:
            return self.rc, "amixer: Fehler"
        if lesen:
            faehig = "volume volume-joined pswitch" if self.schalter \
                else "volume volume-joined"
            return 0, (f"Capabilities: {faehig}\n"
                       f"  Mono: {self.lautstaerke} [{self.lautstaerke}%]")
        return 0, ""

    def letzter(self) -> list[str]:
        return self.aufrufe[-1] if self.aufrufe else []


print("== 1. Aus heißt Lautstärke 0 % -- und der Wert wird gemerkt")
a = Attrappe(lautstaerke=55)
sch = AudioSchalter(ausfuehren=a)
pruefe(sch.mikrofon(False), False, "Mikrofon aus")
pruefe(a.letzter()[-2:], ["mic", "0%"], "letzter Aufruf setzt 0 %")
pruefe(sch.mikrofon(True), True, "Mikrofon an")
pruefe(a.letzter()[-2:], ["mic", "55%"], "zurück auf den gemerkten Wert")

print("== 2. Lautsprecher genauso")
a = Attrappe(lautstaerke=70)
sch = AudioSchalter(ausfuehren=a)
sch.lautsprecher(False)
pruefe(a.letzter()[-2:], ["speaker", "0%"], "Lautsprecher aus")
sch.lautsprecher(True)
pruefe(a.letzter()[-2:], ["speaker", "70%"], "zurück auf 70 %")

print("== 3. Ohne gemerkten Wert gilt die Vorgabe")
a = Attrappe(rc=1)                      # sget scheitert -> nichts gemerkt
sch = AudioSchalter(ausfuehren=a)
sch.lautsprecher(False)
a.rc = 0                                # jetzt geht das Setzen wieder
sch.lautsprecher(True)
pruefe(a.letzter()[-2:], ["speaker", "80%"], "Vorgabe 80 %")

print("== 4. Ein Fehler wird gesagt, nicht verschluckt")
a = Attrappe(rc=1)
sch = AudioSchalter(ausfuehren=a)
pruefe(sch.mikrofon(True), False, "Zustand bleibt aus")
pruefe(bool(sch.letzter_fehler), True, "Grund steht in letzter_fehler")
a.rc = 0
sch.mikrofon(True)
pruefe(sch.letzter_fehler, "", "nach Erfolg wieder leer")

print("== 5. mit_lautsprecher: an für den Ton, danach wieder aus")
a = Attrappe(lautstaerke=60)
sch = AudioSchalter(ausfuehren=a)
sch.lautsprecher(False)
with sch.mit_lautsprecher():
    pruefe(sch.zustand()["lautsprecher_an"], True, "im Block an")
pruefe(sch.zustand()["lautsprecher_an"], False, "danach aus")

print("== 6. alles_aus schaltet beide")
a = Attrappe()
sch = AudioSchalter(ausfuehren=a)
sch.alles_aus()
pruefe(sch.zustand(), {"mikrofon_an": False, "lautsprecher_an": False},
       "beide aus")

print("== 6b. Mit Mute-Schalter: schalten statt Lautstärke")
a = Attrappe(schalter=True)
sch = AudioSchalter(ausfuehren=a)
sch.lautsprecher(False)
pruefe(a.letzter()[-2:], ["speaker", "mute"], "Schalter benutzt (aus)")
sch.lautsprecher(True)
pruefe(a.letzter()[-2:], ["speaker", "unmute"], "Schalter benutzt (an)")
# Die Lautstärke bleibt unangetastet -- kein Sprung auf 80 %.
pruefe(any("0%" in " ".join(x) for x in a.aufrufe), False,
       "keine Lautstärke 0 % geschrieben")

print("== 7. Die Aufnahme läuft über das gemessene Gerät, nicht über Kanäle")
from chimera.audio_schalter import AUFNAHME_GERAET  # noqa: E402

# Das linke Mikro klirrt; die Auswahl steckt in der ALSA-Konfiguration des
# Installers (Modul 46, Messung `chimera.displays.mikro`) -- am chimera-pi
# steht dort seit 11.10.2026 „rechts". Eine zweite Auswahl im Code wäre eine
# zweite Wahrheit.
pruefe(AUFNAHME_GERAET, "chimera_mikro", "Aufnahmegerät")

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(0 if FAIL == 0 else 1)
