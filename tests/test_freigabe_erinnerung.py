"""Der Ton erinnert an offene Freigaben (DESIGN, "Kein Ablauf mehr — der Ton
erinnert"; Entscheidung smilez, 13.11.2026).

Was geprüft wird:

* **Wann** es klingelt — rein, mit vorgegebener Uhr. Erster Ton erst **nach**
  dem Abstand (wer gerade freigegeben hat, soll nicht im selben Moment einen
  Ton bekommen), dann wiederholt, und nach einer Pause nicht nachgeholt.
* **Wer** erinnert: nur offene Freigaben; geschlossene werden vergessen, eine
  neue Freigabe beginnt wieder mit vollem Abstand.
* **Wie laut die Datei ist**: das WAV wird wirklich geschrieben (16 Bit, mono,
  richtige Rate) — eine Erinnerung ohne Ton wäre stiller Erfolg.
* **Was ``aplay`` bekommt**: feste ``argv`` mit ``-D <geraet>``; ein Fehler
  wird gemeldet, nicht geworfen (der Dienst soll weiterlaufen).

Gegenprobe: `python3 tests/gegenprobe_freigabe_erinnerung.py`.
"""

from __future__ import annotations

import os
import sys
import wave
from pathlib import Path

HIER = Path(__file__).resolve().parent.parent
# CHIMERA_SRC laesst die Gegenprobe eine veraenderte Kopie pruefen, ohne den
# echten Quellbaum anzufassen.
SRC = Path(os.environ.get("CHIMERA_SRC") or HIER / "src")
sys.path.insert(0, str(SRC))

from chimera.freigabe_erinnerung import (  # noqa: E402
    ABSTAND_MIN, ABSTAND_VORGABE, Erinnerung, abspielen, klingeln, ton_bauen,
)

ok = fail = 0


def pruef(name: str, ist, soll) -> None:
    global ok, fail
    if ist == soll:
        ok += 1
        print(f"  ok    {name}")
    else:
        fail += 1
        print(f"  FAIL  {name} -- erwartet {soll!r}, bekam {ist!r}")


def wahr(name: str, ist) -> None:
    pruef(name, bool(ist), True)


def offen(**eintraege) -> dict:
    return {"werkzeuge": {k: dict(v, modus=v.get("modus", "offen")) for k, v in eintraege.items()}}


def main() -> int:
    J = 1_700_000_000

    # --- Wann ------------------------------------------------------------
    e = Erinnerung()
    pruef("erster Tick klingelt nicht", e.tick(offen(ssh={}), J), [])
    pruef("kurz vor dem Abstand still", e.tick(offen(ssh={}), J + ABSTAND_VORGABE - 1), [])
    pruef("nach der Vorgabe faellig", e.tick(offen(ssh={}), J + ABSTAND_VORGABE), ["ssh"])
    pruef("danach wieder still", e.tick(offen(ssh={}), J + ABSTAND_VORGABE + 1), [])
    pruef("dann wieder nach dem Abstand", e.tick(offen(ssh={}), J + 2 * ABSTAND_VORGABE), ["ssh"])

    # Nachholen: eine Stunde Stillstand ergibt EINEN Ton, nicht zwoelf.
    e = Erinnerung()
    e.tick(offen(ssh={}), J)
    pruef("nach langer Pause einmal", e.tick(offen(ssh={}), J + 3600), ["ssh"])
    pruef("und dann erst wieder nach Abstand", e.tick(offen(ssh={}), J + 3600 + 299), [])

    # Eigener Abstand des Eintrags.
    e = Erinnerung()
    e.tick(offen(ssh={"erinnern_alle": 120}), J)
    pruef("eigener Abstand: 119 s still", e.tick(offen(ssh={"erinnern_alle": 120}), J + 119), [])
    pruef("eigener Abstand: 120 s Ton", e.tick(offen(ssh={"erinnern_alle": 120}), J + 120), ["ssh"])

    # --- Wer -------------------------------------------------------------
    e = Erinnerung()
    pruef("Positivliste erinnert nicht", e.tick(offen(ssh={"modus": "positivliste"}), J + 10_000), [])
    e = Erinnerung()
    e.tick(offen(ssh={}, web_abruf={}), J)
    pruef("zwei offene: beide", e.tick(offen(ssh={}, web_abruf={}), J + ABSTAND_VORGABE), ["ssh", "web_abruf"])

    # Geschlossen: vergessen -- und neu geoeffnet wieder mit vollem Abstand.
    e = Erinnerung()
    e.tick(offen(ssh={}), J)
    pruef("geschlossen erinnert nicht", e.tick(offen(ssh={"modus": "positivliste"}), J + ABSTAND_VORGABE), [])
    pruef("neu geoeffnet: erst still", e.tick(offen(ssh={}), J + ABSTAND_VORGABE + 1), [])
    pruef("neu geoeffnet: nach Abstand", e.tick(offen(ssh={}), J + 2 * ABSTAND_VORGABE + 1), ["ssh"])

    # Zu kurz und kaputt gesetzt: die Grenze gilt, nicht der Eintrag.
    e = Erinnerung()
    e.tick(offen(ssh={"erinnern_alle": 10}), J)
    pruef("zu kurz wird auf das Minimum gehoben", e.tick(offen(ssh={"erinnern_alle": 10}), J + ABSTAND_MIN - 1), [])
    pruef("zu kurz klingelt beim Minimum", e.tick(offen(ssh={"erinnern_alle": 10}), J + ABSTAND_MIN), ["ssh"])
    e = Erinnerung()
    pruef("kaputter Wert faellt auf die Vorgabe", e.offene(offen(ssh={"erinnern_alle": "viel"})), {"ssh": ABSTAND_VORGABE})
    pruef("fehlender Wert faellt auf die Vorgabe", e.offene(offen(ssh={})), {"ssh": ABSTAND_VORGABE})

    # Unbekannte Formen sind still, nicht toedlich.
    pruef("kein Objekt ergibt nichts", Erinnerung().tick({}, J), [])
    pruef("Werkzeuge fehlen", Erinnerung().tick({"werkzeuge": None}, J), [])
    pruef("Eintrag ist kein Objekt", Erinnerung().tick({"werkzeuge": {"ssh": "offen"}}, J), [])

    # --- Ton -------------------------------------------------------------
    import tempfile

    ordner = Path(tempfile.mkdtemp(prefix="chimera-test-ton-"))
    ziel = ordner / "t.wav"
    ton_bauen(ziel)
    wahr("WAV wurde geschrieben", ziel.is_file() and ziel.stat().st_size > 1000)
    with wave.open(str(ziel), "rb") as w:
        pruef("ein Kanal", w.getnchannels(), 1)
        pruef("16 Bit", w.getsampwidth(), 2)
        pruef("Rate", w.getframerate(), 44100)
        rahmen = w.getnframes()
    pruef("Laenge passt zur Dauer", abs(rahmen - int(0.18 * 44100)) <= 2, True)

    # aplay-Aufruf: feste argv, kein Shell-Aufruf.
    gerufen = []

    class R:
        returncode = 0
        stderr = ""

    def lauf(befehl):
        gerufen.append(befehl)
        return R()

    pruef("abspielen meldet keinen Fehler", abspielen(ziel, lauf=lauf), "")
    pruef("aplay bekommt feste argv", gerufen, [["aplay", "-q", "-D", "default", str(ziel)]])
    pruef("Gerat ist waehlbar", abspielen(ziel, geraet="plughw:1", lauf=lauf), "")
    pruef("Gerat in der argv", gerufen[-1][:4], ["aplay", "-q", "-D", "plughw:1"])

    class Kaputt:
        returncode = 2
        stderr = "audio open error: No such device"

    fehler = abspielen(ziel, lauf=lambda _b: Kaputt())
    wahr("aplay-Fehler wird gemeldet", "No such device" in fehler)

    def wirft(_b):
        raise OSError("kein aplay")

    wahr("fehlendes aplay wird gemeldet", "nicht ausfuehrbar" in abspielen(ziel, lauf=wirft))

    # Ein Ton fuer mehrere Werkzeuge, nicht mehrere Toene.
    gerufen.clear()
    pruef("klingeln meldet keinen Fehler", klingeln(["ssh", "web_abruf"], pfad=ziel, lauf=lauf), "")
    pruef("genau ein Ton", len(gerufen), 1)
    pruef("nichts faellig: kein Ton", klingeln([], pfad=ziel, lauf=lauf), "")
    pruef("weiterhin ein Ton", len(gerufen), 1)

    # --- Der Op-Name ist nicht erfunden ----------------------------------
    # **Am Gerät gefunden (13.11., 21:20):** Der Dienst fragte
    # ``freigaben_lesen``, das Gateway kennt nur ``freigabe_lesen`` — die
    # Erinnerung hätte dort nie geklingelt, und dieser Test war grün, weil
    # die Attrappe auf jeden Namen antwortete. Ein Testdoppel, das nicht
    # prüft, WAS gefragt wird, prüft nur sich selbst.
    import re

    from chimera import app as app_modul
    from chimera import freigabe_erinnerung as fe
    from chimera.provider import gateway as gw

    app_quelle = (SRC / "chimera" / "app.py").read_text(encoding="utf-8")
    dienst_quelle = (HIER / "rust" / "crates" / "tor" / "src" / "dienst.rs").read_text(encoding="utf-8")
    gefragt = re.findall(r'anfragen\(\{"op": "([a-z_]+)"', app_quelle)
    wahr("app.py fragt ueberhaupt eine Op", gefragt)
    for op in gefragt:
        wahr(f"Op '{op}' steht im Gateway (dienst.rs)", f'"{op}" =>' in dienst_quelle)

    # Und die Antwort wird wirklich verarbeitet, nicht nur angefragt.
    gesehen = []

    def falsches_gateway(anfrage, **_k):
        gesehen.append(anfrage)
        return {"ok": True, "freigaben": {"werkzeuge": {
            "ssh": {"modus": "offen", "seit": J - 600, "erinnern_alle": 60}}}}

    alt_anfragen = gw.anfragen
    alt_klingeln = fe.klingeln
    gespielt = []
    gw.anfragen = falsches_gateway
    fe.klingeln = lambda namen, **_k: gespielt.append(list(namen)) or ""
    try:
        chi = app_modul.Chimera.__new__(app_modul.Chimera)
        chi.erinnerung = Erinnerung()
        chi.ton_pfad = ziel
        pruef("erste Frage erinnert noch nicht", chi.erinnere(jetzt=J), [])
        pruef("nach dem Abstand erinnert es", chi.erinnere(jetzt=J + 60), ["ssh"])
        pruef("Op Name wie im Gateway", gesehen[0].get("op"), gefragt[0])
        pruef("ein Ton gespielt", gespielt, [["ssh"]])
    finally:
        gw.anfragen = alt_anfragen
        fe.klingeln = alt_klingeln

    # --- Verdrahtet, nicht nur gebaut ------------------------------------
    # Regel: "Gebaut ist erst, wenn verdrahtet ist." Der Dienst muss die
    # Erinnerung im Takt wirklich aufrufen -- ein Modul ohne Aufrufer ist ein
    # offenes Ende.
    from chimera import __main__ as dienst_modul

    alt_takt = dienst_modul.ANBIETER_TAKT_S
    dienst_modul.ANBIETER_TAKT_S = 0.01
    import chimera.sitzung_socket as ss

    alt_aus = ss.aus_umgebung
    ss.aus_umgebung = lambda _sitzung, _env: None
    gerufen.clear()

    class FalscherDienst:
        class registry:  # noqa: N801
            available = staticmethod(lambda: True)

        renderer = None
        session = object()

        def __init__(self):
            self.stop = None

        def start_display(self):
            return False

        def paint_once(self):
            pass

        def anbieter_melden(self):
            pass

        def erinnere(self):
            gerufen.append(1)
            if len(gerufen) >= 3:
                self.stop.set()

    import threading

    falsch = FalscherDienst()
    stop = threading.Event()
    falsch.stop = stop
    # Notbremse: Wird `erinnere` nicht gerufen (die Mutation, die dieser Test
    # fangen soll), setzt niemand das Stop-Ereignis -- der Dienst liefe ewig.
    notbremse = threading.Timer(10.0, stop.set)
    notbremse.start()
    try:
        rc = dienst_modul.dienst(falsch, stop=stop, env={})
    finally:
        notbremse.cancel()
    pruef("Dienst endet sauber", rc, 0)
    pruef("Dienst ruft die Erinnerung im Takt", len(gerufen) >= 3, True)
    dienst_modul.ANBIETER_TAKT_S = alt_takt
    ss.aus_umgebung = alt_aus

    print(f"\nErgebnis: {ok} ok, {fail} FAIL")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
