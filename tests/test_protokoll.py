"""Tests für das Dienstprotokoll (``chimera.protokoll``, DESIGN 10r).

Geprüft wird der echte Code: Handler an einen eigenen Logger, echte
Dateien in einem Temp-Ordner. Gegenproben am Ende: der alte Zustand
(Standard-Namer ``.log.1``, kein Deckel) wird hergestellt, und die
zugehörige Prüfung muss dann scheitern.
"""
import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import chimera.protokoll as pr  # noqa: E402
import chimera.__main__ as cm  # noqa: E402

PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


def frischer_logger(name):
    lg = logging.getLogger(f"test.{name}")
    lg.handlers.clear(); lg.propagate = False; lg.setLevel(logging.INFO)
    return lg


def schliessen(lg):
    for h in list(lg.handlers):
        h.close(); lg.removeHandler(h)


print("=== Dienstprotokoll ===")

with tempfile.TemporaryDirectory() as tmp:
    ram = Path(tmp) / "run" / "chimera" / "logs" / "productive"

    # 1. Datei je Start, im RAM-Ordner, mit Zeitstempel im Namen.
    lg = frischer_logger("a")
    p = pr.datei_einrichten({"CHIMERA_LOG_RAM": str(ram)},
                            jetzt=1791676800.0, logger=lg)
    check("Datei liegt im RAM-Ordner", p is not None and p.parent == ram, True)
    check("Name dienst-<zeit>.log",
          p is not None and p.name.startswith("dienst-") and p.suffix == ".log", True)
    lg.info("hallo vom dienst")
    for h in lg.handlers: h.flush()
    check("Zeile steht in der Datei", "hallo vom dienst" in p.read_text(), True)
    schliessen(lg)

    # 2. Zweiter Start -> eigene Datei, die erste bleibt.
    lg = frischer_logger("b")
    p2 = pr.datei_einrichten({"CHIMERA_LOG_RAM": str(ram)},
                             jetzt=1791676800.0 + 61, logger=lg)
    check("zweiter Start: andere Datei", p2 != p, True)
    check("erste Datei bleibt", p.exists(), True)
    schliessen(lg)

    # 3. Deckel: Stuecke tragen .log am Ende (sonst sieht log_sync sie nicht),
    #    und es bleiben hoechstens STUECKE + 1 Dateien.
    alt = pr.GROESSE
    pr.GROESSE = 2000
    try:
        lg = frischer_logger("c")
        p3 = pr.datei_einrichten({"CHIMERA_LOG_RAM": str(ram / "deckel")},
                                 jetzt=1791676800.0, logger=lg)
        for i in range(400):
            lg.info("zeile %04d %s", i, "x" * 40)
        schliessen(lg)
    finally:
        pr.GROESSE = alt
    dateien = sorted(x.name for x in (ram / "deckel").iterdir())
    check("alle Stuecke enden auf .log",
          all(n.endswith(".log") for n in dateien), True)
    check("Stueckzahl gedeckelt", len(dateien), pr.STUECKE + 1)
    gesamt = sum((ram / "deckel" / n).stat().st_size for n in dateien)
    check("Gesamtgroesse gedeckelt", gesamt <= (pr.STUECKE + 1) * 2000 + 200, True)
    check("Stueck heisst dienst-<zeit>.1.log",
          any(n.endswith(".1.log") for n in dateien), True)

    # 4. Ohne CHIMERA_LOG_RAM: kein Handler, kein Fehler.
    lg = frischer_logger("d")
    check("ohne CHIMERA_LOG_RAM: None", pr.datei_einrichten({}, logger=lg), None)
    check("ohne CHIMERA_LOG_RAM: kein Handler", lg.handlers, [])

    # 5. Ziel nicht anlegbar -> None, kein Abbruch.
    sperre = Path(tmp) / "ist-datei"
    sperre.write_text("x")
    lg = frischer_logger("e")
    check("Ziel nicht anlegbar: None, kein Abbruch",
          pr.datei_einrichten({"CHIMERA_LOG_RAM": str(sperre / "sub")}, logger=lg),
          None)

# 6. main --dienst richtet die Datei ein, ohne --dienst nicht.
gerufen = []
alt_build, alt_dienst, alt_datei = cm.build, cm.dienst, cm.datei_einrichten


class Geraet:
    notes = []
    def status(self): return ""
    def stop_display(self): pass


try:
    cm.build = lambda **kw: Geraet()
    cm.dienst = lambda chi, **kw: 0
    cm.datei_einrichten = lambda *a, **kw: gerufen.append("datei")
    cm.main(["--dienst", "--offline"])
    check("--dienst richtet die Datei ein", gerufen, ["datei"])
    gerufen.clear()
    cm.main(["--pruefen", "--offline"])
    check("--pruefen richtet keine Datei ein", gerufen, [])
finally:
    cm.build, cm.dienst, cm.datei_einrichten = alt_build, alt_dienst, alt_datei

# --- Gegenproben ----------------------------------------------------------
def stuecke(namer, groesse):
    """Wie Fall 3, mit einstellbarem Namer und Deckel. Liefert Dateinamen."""
    alt_g, alt_n = pr.GROESSE, pr._namer
    pr.GROESSE, pr._namer = groesse, namer
    try:
        with tempfile.TemporaryDirectory() as tmp:
            lg = frischer_logger("gp")
            pr.datei_einrichten({"CHIMERA_LOG_RAM": tmp}, jetzt=0.0, logger=lg)
            for i in range(400):
                lg.info("zeile %04d %s", i, "x" * 40)
            schliessen(lg)
            return sorted(x.name for x in Path(tmp).iterdir())
    finally:
        pr.GROESSE, pr._namer = alt_g, alt_n

# G1: Standard-Namer (dienst-X.log.1) -> Stuecke enden nicht auf .log.
n = stuecke(lambda name: name, 2000)
check("Gegenprobe: ohne Namer fallen Stuecke aus *.log",
      all(x.endswith(".log") for x in n), False)
# G2: ohne Deckel (maxBytes=0) -> eine einzige, wachsende Datei.
n = stuecke(pr._namer, 0)
check("Gegenprobe: ohne Deckel nur eine Datei", len(n), 1)

print(f"\nErgebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
