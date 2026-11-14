"""Tests für „Verdichten mit Verweis" (DESIGN, Architekturregel 8d).

Was hier gemessen wird — und zwar am echten Code, nicht an einer
nachgebauten Formel:

1. Der Verweis nennt den **richtigen** Zeilenbereich aus ``verlauf.jsonl``.
2. Offene Punkte und Entscheidungen stehen **wörtlich** und **vollständig**
   im Fenster (Zahl gegen Gesamtzahl).
3. Die letzten Turns bleiben wörtlich — Verdichten ist kein Abschneiden.
4. Das Protokoll verliert **nichts**: nach dem Verdichten ist der alte
   Wortlaut noch lesbar, und zwar über ``nachlesen``.
5. Beim Verdichten wird **kein Modell** gefragt (0 Aufrufe).

Gegenprobe: ``python3 tests/gegenprobe_verdichten.py`` baut je Zusage eine
Verfälschung in eine Baumkopie und verlangt, dass dieser Test rot wird.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Für die Gegenprobe: gegen eine Baumkopie messen (Muster aus
# tests/test_freigabe_erinnerung.py) — sonst prüfte die Verfälschung nichts.
SRC = Path(os.environ.get("CHIMERA_SRC") or (ROOT / "src"))
sys.path.insert(0, str(SRC))

from chimera.ablage import Ablage, Verlauf  # noqa: E402
from chimera.agent.verdichten import (  # noqa: E402
    MARKE, RUNDEN_BEHALTEN, entscheidungen, fruehere_verweise,
    offene_punkte, schnittindex, verdichte)
from chimera.agent.tools import NACHLESEN_MAX, Toolbox  # noqa: E402

PASS = FAIL = 0


def ok(m):
    global PASS
    PASS += 1
    print(f"  ok    {m}")


def bad(m):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {m}")


def _kurz(x, n=200):
    r = repr(x)
    return r if len(r) <= n else r[:n] + f" … ({len(r)} Zeichen)"


def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {_kurz(want)}, bekam {_kurz(got)}")


def _ablage():
    td = tempfile.mkdtemp(prefix="chimera-verd-")
    return Ablage(td)


def _verlauf(ab, texte):
    """Verlauf mit echten Nachrichten füllen (jede schreibt eine Zeile)."""
    v = Verlauf(ab, ab.laden())
    for t in texte:
        rolle = "user" if t.startswith("U:") else "assistant"
        v.append({"role": rolle, "content": t.split(":", 1)[1].strip()})
    return v


def _ist_runde(m):
    return m.get("role") == "user" and not str(m.get("content") or "").startswith(
        ("Ergebnis von", "[Bisheriges Gespräch"))


def main():
    print("== Verweis auf die Fundstelle")
    ab = _ablage()
    v = _verlauf(ab, ["U: eins", "A: zwei", "U: drei", "A: vier",
                      "U: fuenf", "A: sechs", "U: sieben", "A: acht",
                      "U: neun", "A: zehn"])
    schnitt = schnittindex(list(v))
    von, bis = v.zeilenbereich(schnitt, abstand=len(v) - schnitt)
    check("Schnitt liegt auf einem Rundenbeginn", schnitt, 4)
    check("Bereich beginnt bei Zeile 1", von, 1)
    check("Bereich endet bei der 4. Nachricht", bis, 4)
    b = verdichte(list(v), von=von, bis=bis)
    check("Kopfzeile nennt den Bereich", MARKE + " Zeilen 1–4" in b.text, True)
    check("Kopfzeile nennt nachlesen", "nachlesen (von=1, bis=4)" in b.text, True)
    check("Bericht ist vollständig", b.vollstaendig, True)

    print("== Wörtlich und vollständig: offene Punkte")
    ab = _ablage()
    v = _verlauf(ab, ["U: Stand\n- [ ] Punkt A\n- [ ] Punkt B",
                      "A: verstanden", "U: weitere Frage",
                      "A: Antwort", "U: noch eine", "A: ja",
                      "U: letzte", "A: gut"])
    alle = offene_punkte(list(v))
    b = verdichte(list(v), von=1, bis=len(v))
    check("Quelle hat zwei offene Punkte", len(alle), 2)
    check("Verdichtung zählt beide", b.offene_punkte, 2)
    # Nicht „irgendwo im Text": Der Abschnittsanfang nennt den Wortlaut
    # ohnehin — geprüft wird der **eigene** Abschnitt (Lehre 14.11.).
    check("eigener Abschnitt für offene Punkte",
          "## Offene Punkte (2, wörtlich)" in b.text, True)
    check("Punkt A wörtlich", "\n- [ ] Punkt A" in b.text, True)
    check("Punkt B wörtlich", "\n- [ ] Punkt B" in b.text, True)

    print("== Wörtlich und vollständig: Entscheidungen")
    ab = _ablage()
    v = _verlauf(ab, ["U: Entscheidung: Wir nehmen Rust.",
                      "A: notiert", "U: frage", "A: antwort", "U: a", "A: b",
                      "U: c", "A: d"])
    b = verdichte(list(v), von=1, bis=8)
    check("Entscheidung gezählt", b.entscheidungen, 1)
    check("eigener Abschnitt für Entscheidungen",
          "## Entscheidungen (1, wörtlich)" in b.text, True)
    check("Entscheidung wörtlich", "\n- Wir nehmen Rust." in b.text, True)

    print("== Die letzten Turns bleiben wörtlich")
    ab = _ablage()
    v = _verlauf(ab, [f"U: frage {i}" if i % 2 == 0 else f"A: antwort {i}"
                      for i in range(10)])
    b = verdichte(list(v), von=1, bis=len(v))
    check("Kopf enthält nicht die letzten Runden", "antwort 9" in b.text, False)
    check("Bericht meldet die verdichteten Nachrichten", b.nachrichten, 4)
    check("drei Runden bleiben wörtlich", schnittindex(list(v)), 4)
    check("Runden-Vorgabe ist 3", RUNDEN_BEHALTEN, 3)

    print("== Das Protokoll verliert nichts, nachlesen holt den Wortlaut")
    ab = _ablage()
    v = _verlauf(ab, ["U: geheim 1 - [ ] wichtig", "A: ok",
                      "U: frage 2", "A: antwort 2", "U: frage 3", "A: antwort 3",
                      "U: frage 4", "A: antwort 4"])
    vorher = len(ab.lesen(ab.aktiv()))
    schnitt = schnittindex(list(v))
    von, bis = v.zeilenbereich(schnitt, abstand=len(v) - schnitt)
    b = verdichte(list(v), von=von, bis=bis)
    v.verdichten(b.text, len(v) - schnitt,
                 zeilen_von=b.zeilen_von, zeilen_bis=b.zeilen_bis)
    nachher = ab.lesen(ab.aktiv())
    check("Protokoll behält alle Nachrichten", len(nachher), vorher + 1)
    check("erste Nachricht noch da", nachher[0].get("inhalt"),
          "geheim 1 - [ ] wichtig")
    # Wörtlich geprüft, nicht gegen die Konstante aus demselben Modul:
    # sonst bliebe der Test grün, wenn die Marke gar nicht mehr gesetzt wird.
    check("Fenster beginnt mit der Verdichtung",
          v[0]["content"].startswith("[Bisheriges Gespräch"), True)
    check("Fenster: 1 Verdichtung + 6 wörtliche Nachrichten", len(v), 7)
    check("Verdichtung vermerkt die Fundstelle",
          (nachher[-1].get("zeilen_von"), nachher[-1].get("zeilen_bis")),
          (b.zeilen_von, b.zeilen_bis))

    tb = Toolbox(tempfile.mkdtemp(prefix="chimera-verd-tb-"), ablage=ab)
    text = tb.call("nachlesen", {"von": str(von), "bis": str(bis)})
    check("nachlesen liefert den Wortlaut", "geheim 1 - [ ] wichtig" in text, True)
    check("nachlesen nennt die Zeilen", f"Zeilen {von}-{bis}" in text, True)

    print("== Schnitt nie zwischen Werkzeugaufruf und Ergebnis")
    ab = _ablage()
    v = _verlauf(ab, ["U: frage 1", "A: antwort 1",
                      "U: frage 2", "A: antwort 2",
                      "U: frage 3", "A: antwort 3",
                      "U: frage 4", "A: antwort 4"])
    # Eine Werkzeugrunde: Aufruf in der Antwort, Ergebnis als Nutzer-Nachricht.
    v.append({"role": "assistant", "content": 'TOOL: status {}'})
    v.append({"role": "user", "content": "Ergebnis von status:\nCPU 5 %"})
    v.append({"role": "assistant", "content": "Alles ruhig."})
    b = verdichte(list(v), von=1, bis=len(v))
    # Am **Ergebnis** gemessen, nicht an der Hilfsfunktion: Nur so wird
    # eine Verfälschung in ``verdichte`` überhaupt sichtbar.
    schnitt = b.schnitt
    check("Schnitt liegt im Verlauf", schnitt < len(list(v)), True)
    check("Schnitt trifft eine echte Runde", _ist_runde(list(v)[schnitt]), True)
    check("Schnitt liegt nicht auf einem Werkzeugergebnis",
          str(list(v)[schnitt]["content"]).startswith("Ergebnis von"), False)
    check("kein Block endet mitten in der Werkzeugrunde",
          "Ergebnis von status" in b.text, False)
    check("Werkzeugergebnis ist nicht zerschnitten",
          "Ergebnis von status" in list(v)[-2]["content"], True)
    check("letzte Runde bleibt wörtlich (Text nicht im Kopf)", "Alles ruhig." in b.text, False)

    print("== Frühere Verdichtung: der Verweis bleibt")
    alt = ("[Bisheriges Gespräch — verdichtet] Zeilen 1–20 in verlauf.jsonl, 18 Nachrichten\n"
           "Den vollen Wortlaut holt das Werkzeug nachlesen (von=1, bis=20).\n\n"
           "- Zeilen 1–5 (5×, Nutzer, Chimera): irgendwas\n"
           "## Offene Punkte (1, wörtlich)\n- [ ] alten Punkt prüfen")
    verweise = fruehere_verweise([{"role": "user", "content": alt}])
    check("Verweis gesammelt", any("von=1, bis=20" in x for x in verweise), True)
    check("Abschnittszeile gesammelt", any("Zeilen 1–5" in x for x in verweise), True)
    ab = _ablage()
    v = _verlauf(ab, ["U: neu 1", "A: ok", "U: neu 2", "A: ok"])
    v.insert(0, {"role": "user", "content": alt})
    b = verdichte(list(v), von=1, bis=len(v))
    check("neuer Text nennt die frühere Verdichtung",
          "## Frühere Verdichtung" in b.text, True)
    check("alter Verweis überlebt", "von=1, bis=20" in b.text, True)
    check("alter offener Punkt überlebt", "alten Punkt prüfen" in b.text, True)

    print("== Grenzen von nachlesen")
    text = tb.call("nachlesen", {"von": "1", "bis": "10000"})
    # Die Obergrenze wird am Verhalten gemessen, nicht aus der Konstante
    # abgelesen: Bei „bis=10000" darf der Bereich nicht 10000 Zeilen umfassen.
    check("zu großer Bereich wird gekappt", "Zeilen 1-10000" in text, False)
    check("hoechstens %d Zeilen je Aufruf" % NACHLESEN_MAX,
          len(text.splitlines()) <= NACHLESEN_MAX + 2, True)
    check("von=0 abgelehnt", "ab 1" in tb.call("nachlesen", {"von": "0", "bis": "5"}), True)
    check("bis vor von abgelehnt",
          "liegt vor" in tb.call("nachlesen", {"von": "9", "bis": "3"}), True)
    check("Unsinn abgelehnt", "als Zahl" in tb.call("nachlesen", {"von": "abc"}), True)
    tb2 = Toolbox(tempfile.mkdtemp(prefix="chimera-verd-tb2-"))
    check("ohne Ablage gesagt, nicht geschwiegen",
          "Kein Sitzungsprotokoll" in tb2.call("nachlesen", {"von": "1", "bis": "2"}), True)
    leer = tb.call("nachlesen", {"von": "999", "bis": "1000"})
    check("leerer Bereich ist eine Auskunft", "steht nichts" in leer, True)

    print("== Kein Modell beim Verdichten")
    from chimera.agent.loop import Agent
    from chimera.agent.tools import Toolbox as TB

    class Reg:
        calls = 0
        context_window = 8192

        def resolve(self, task):
            return []

        def call(self, *a, **k):
            Reg.calls += 1
            raise AssertionError("Verdichten darf kein Modell fragen")

    ab = _ablage()
    v = _verlauf(ab, [f"U: frage {i}" if i % 2 == 0 else f"A: antwort {i}"
                      for i in range(12)])
    a = Agent(Reg(), TB(tempfile.mkdtemp(prefix="chimera-verd-3-")))
    a.history = v
    a._compact()
    check("kein Modellaufruf", Reg.calls, 0)
    check("verdichtet (Fenster kürzer)", len(a.history) < 12, True)
    check("Verdichtung trägt die Marke",
          a.history[0]["content"].startswith("[Bisheriges Gespräch"), True)

    print()
    print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
