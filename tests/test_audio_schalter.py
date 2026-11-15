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
            # Wie das Gerät (am Pi gemessen 15.11.): `amixer -q … sget` gibt
            # NICHTS aus. Die Attrappe muss das nachbilden, sonst prüft ein
            # Test, dass ein leerer Wert als 80 % gelesen wird.
            if "-q" in argv:
                return 0, ""
            faehig = "volume volume-joined pswitch" if self.schalter \
                else "volume volume-joined"
            return 0, (f"Capabilities: {faehig}\n"
                       f"  Mono: {self.lautstaerke} [{self.lautstaerke}%]")
        # `sset <regler> <wert>` wirkt wie am Gerät: Der nächste `sget` liest
        # den neuen Wert. Ohne das bildet die Attrappe das Verhalten nicht
        # nach -- ein Test, der 60 setzt und 55 zurückbekommt, prüft nur sich
        # selbst.
        if "sset" in argv and argv[-1].endswith("%"):
            try:
                self.lautstaerke = int(argv[-1].rstrip("%"))
            except ValueError:
                pass
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

print("== 6c. Set and forget: die Lautstärke überlebt den Neustart")
import tempfile  # noqa: E402

from pathlib import Path as _P  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    pfad = _P(td) / "config" / "audio.json"
    a = Attrappe(lautstaerke=62)
    sch = AudioSchalter(ausfuehren=a, ablage=pfad)
    sch.lautsprecher(False)                 # merkt 62 % und legt es ab
    pruefe(pfad.is_file(), True, "Ablage geschrieben")
    # Neustart: neuer Schalter, kein gemessener Wert mehr in der Attrappe
    a2 = Attrappe(rc=1)                     # sget scheitert
    neu = AudioSchalter(ausfuehren=a2, ablage=pfad)
    neu.lautsprecher(True)
    pruefe(a2.letzter()[-2:], ["speaker", "62%"],
           "nach dem Neustart gilt die eingestellte Lautstärke, nicht 80 %")

print("== 6d. Lautstärke einstellen (Reiter Einstellungen, 15.11.)")
# Einstellen ist nicht Schalten: Ist der Kanal aus, bleibt er aus und der Wert
# wird nur gemerkt -- ein Regler, der den stummen Lautsprecher hörbar macht,
# wäre ein Nebeneffekt, den niemand bestellt hat.
with tempfile.TemporaryDirectory() as td:
    pfad = _P(td) / "config" / "audio.json"
    a = Attrappe(lautstaerke=80)
    sch = AudioSchalter(ausfuehren=a, ablage=pfad)
    sch.lautsprecher(False)                  # aus, merkt 80 %
    vorher = len(a.aufrufe)
    okk, meldung = sch.lautstaerke_setzen("lautsprecher", 35)
    pruefe(okk, True, "setzen im Aus gemeldet")
    pruefe("35" in meldung, True, "Meldung nennt den Wert")
    pruefe(len(a.aufrufe), vorher, "kein amixer-Aufruf, solange aus")
    pruefe(sch.lautstaerke("lautsprecher"), 35,
           "eingestellte Lautstärke bleibt sichtbar, obwohl aus")
    pruefe(pfad.is_file() and "35%" in pfad.read_text(encoding="utf-8"), True,
           "Wert liegt in der Ablage")
    # Einschalten wendet genau diesen Wert an -- nicht 80 %.
    sch.lautsprecher(True)
    pruefe(a.letzter()[-2:], ["speaker", "35%"], "an wendet den eingestellten Wert an")
    # Jetzt greift amixer wirklich.
    okk, _ = sch.lautstaerke_setzen("lautsprecher", 60)
    pruefe((okk, a.letzter()[-2:]), (True, ["speaker", "60%"]), "setzen im An schreibt")
    # Grenzen und Unsinn: abgelehnt, nichts geändert.
    for wert in (-1, 101, "laut", None, True):
        okk, _ = sch.lautstaerke_setzen("lautsprecher", wert)
        pruefe(okk, False, f"{wert!r} abgelehnt")
    pruefe(sch.lautstaerke("lautsprecher"), 60, "nach Ablehnungen unverändert")
    okk, _ = sch.lautstaerke_setzen("subwoofer", 50)
    pruefe(okk, False, "unbekannter Regler abgelehnt")
    # als_json: was die Seite braucht, in einem Stück.
    j = sch.als_json()
    pruefe(sorted(j), sorted(["mikrofon_an", "lautsprecher_an",
                              "lautstaerke_mikrofon", "lautstaerke_lautsprecher",
                              "karte", "letzter_fehler"]), "als_json nennt alle Felder")
    pruefe(j["lautstaerke_lautsprecher"], 60, "als_json: Lautstärke")
    # Ist der Kanal an und amixer scheitert, wird der Fehler nicht verschluckt.
    a.rc = 1
    okk, meldung = sch.lautstaerke_setzen("lautsprecher", 40)
    pruefe(okk, False, "scheiterndes amixer wird gemeldet")
    pruefe(bool(sch.letzter_fehler), True, "letzter_fehler gesetzt")

print("== 6e. Gemessen wird am Regler, nicht geraten (am Pi gemessen: -q sget schweigt)")
a = Attrappe(lautstaerke=80)
sch = AudioSchalter(ausfuehren=a)
sch.lautsprecher(True)                       # an; schreibt 80 %
a.lautstaerke = 73                           # jemand dreht mit alsamixer
pruefe(sch.lautstaerke("lautsprecher"), 73,
       "Lautstärke wird am Regler gemessen")
pruefe("-q" not in a.letzter(), True,
       "lesender Aufruf kommt ohne -q (sonst leere Ausgabe, stiller Erfolg)")

print("== 6f. _amixer gibt die Ausgabe zurück (sonst ist jede Messung leer)")
import os as _os  # noqa: E402
import stat as _stat  # noqa: E402
import tempfile as _tf  # noqa: E402
from chimera.audio_schalter import _amixer  # noqa: E402

with _tf.TemporaryDirectory() as td:
    # Eine Attrappe als ausführbare Datei im PATH: So läuft der ECHTE
    # Kindprozess-Weg (subprocess), nicht eine eingesetzte Funktion -- nur der
    # tut weh, wenn die Ausgabe verworfen wird.
    schein = _P(td) / "amixer"
    schein.write_text("#!/bin/sh\necho '  Mono: 55 [55%]'\nexit 0\n", encoding="utf-8")
    schein.chmod(schein.stat().st_mode | _stat.S_IEXEC)
    alt_path = _os.environ.get("PATH", "")
    _os.environ["PATH"] = f"{td}:{alt_path}"
    try:
        rc, text = _amixer(["amixer", "-c", "whisplaysound", "sget", "speaker"],
                           lesen=True)
    finally:
        _os.environ["PATH"] = alt_path
    pruefe(rc, 0, "Kindprozess-rc")
    pruefe("55%" in text, True, "Ausgabe des Kommandos kommt zurück")
    # Und der Wert, den der Schalter daraus liest.
    with _tf.TemporaryDirectory() as td2:
        _os.environ["PATH"] = f"{td}:{alt_path}"
        try:
            sch2 = AudioSchalter()
            sch2._lautsprecher_an = True
            pruefe(sch2.lautstaerke("lautsprecher"), 55,
                   "gemessene Lautstärke aus echter Prozessausgabe")
        finally:
            _os.environ["PATH"] = alt_path

print("== 6g. 0 % ist der Aus-Zustand, keine Einstellung (am Pi 15.11.)")
# Wer beim Ausschalten eine gemessene 0 % als „Einstellung" speichert, verliert
# die gewählte Lautstärke bei jedem Neustart im Aus -- und das Gerät bleibt
# beim Einschalten stumm.
with tempfile.TemporaryDirectory() as td:
    pfad = _P(td) / "config" / "audio.json"
    a = Attrappe(lautstaerke=0)              # Regler steht schon auf 0 %
    sch = AudioSchalter(ausfuehren=a, ablage=pfad)
    sch.lautsprecher(False)
    pruefe(sch._lautstaerke.get("lautsprecher"), None,
           "gemessene 0 % wird nicht als Einstellung gemerkt")
    pruefe(sch.lautstaerke("lautsprecher"), 80,
           "ohne bekannten Wert gilt die Vorgabe (was 'an' anwenden würde)")
    sch.lautsprecher(True)
    pruefe(a.letzter()[-2:], ["speaker", "80%"], "an wendet die Vorgabe an, nicht 0 %")
    # Eine alte Ablage mit 0 % (Fassung vor dem Fix) wird nicht übernommen.
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text('{"lautsprecher": "0%"}', encoding="utf-8")
    neu = AudioSchalter(ausfuehren=Attrappe(lautstaerke=0), ablage=pfad)
    pruefe(neu._lautstaerke.get("lautsprecher"), None, "0 % aus der Ablage ignoriert")

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
