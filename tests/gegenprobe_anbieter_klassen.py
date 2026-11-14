"""Gegenprobe zu „Zugang und Kosten je Anbieter" (ROADMAP 14.11.).

Vier Zusagen werden in einer Kopie des Quellbaums verfaelscht; der Test muss
an der genannten Stelle rot werden:
  1. DeepSeek ist abgerechnet, nicht lokal-kostenlos.
  2. Ein unbekannter Typ gilt als abgerechnet (nicht in der billigen Kette).
  3. Der Connector nimmt die Klassen aus dem **Typ**, nicht aus der Zeile.
  4. Nur Typen mit Chat-Modul werden aufgenommen.

Die echte Datei bleibt unberuehrt.

Aufruf: python3 tests/gegenprobe_anbieter_klassen.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = HIER.parent
GATEWAY = ROOT / "src" / "chimera" / "provider" / "gateway.py"
SETUP = ROOT / "src" / "chimera" / "provider" / "setup.py"
TEST = HIER / "test_gateway_provider.py"

MUTATIONEN = [
    ("deepseek-kostenlos", GATEWAY,
     '    "deepseek": (Access.API_KEY, CostClass.METERED),',
     '    "deepseek": (Access.LOCAL, CostClass.FREE),',
     "deepseek wird abgerechnet"),
    ("unbekannt-kostenlos", GATEWAY,
     "FREMD_KLASSEN = (Access.API_KEY, CostClass.METERED)",
     "FREMD_KLASSEN = (Access.LOCAL, CostClass.FREE)",
     "unbekannter Typ gilt als abgerechnet"),
    ("typ-ignoriert", GATEWAY,
     "        self.access, self.cost = klassen_fuer(typ if typ is not None else anbieter)",
     "        self.access, self.cost = Access.LOCAL, CostClass.FREE",
     "deepseek laeuft ueber einen Schluessel"),
    ("jeder-typ-erlaubt", SETUP,
     "            if typ not in gateway.CHAT_TYPEN:",
     "            if False:",
     "Typ ohne Chat-Modul wird benannt"),
]


def lauf(datei: Path, inhalt: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        baum = Path(tmp) / "projekt"
        shutil.copytree(ROOT / "src", baum / "src")
        (baum / "tests").mkdir(exist_ok=True)
        shutil.copy(TEST, baum / "tests" / "test_gateway_provider.py")
        ziel = baum / datei.relative_to(ROOT)
        ziel.write_text(inhalt, encoding="utf-8")
        return subprocess.run([sys.executable, str(baum / "tests" / "test_gateway_provider.py")],
                              capture_output=True, text=True, timeout=300)


def main() -> int:
    pass_ = fail = 0

    def ok(m: str) -> None:
        nonlocal pass_
        pass_ += 1
        print(f"  ok    {m}")

    def bad(m: str) -> None:
        nonlocal fail
        fail += 1
        print(f"  FAIL  {m}")

    print("=== Gegenprobe Anbieter-Klassen ===")

    basis = lauf(GATEWAY, GATEWAY.read_text(encoding="utf-8"))
    if basis.returncode == 0:
        ok("unveraendert gruen")
    else:
        bad("unveraendert schon rot -- Gegenprobe nicht aussagekraeftig")
        print(basis.stdout[-800:])

    for name, datei, muster, ersatz, pruefpunkt in MUTATIONEN:
        original = datei.read_text(encoding="utf-8")
        if muster not in original:
            bad(f"{name}: Muster nicht gefunden")
            continue
        p = lauf(datei, original.replace(muster, ersatz, 1))
        if p.returncode == 0:
            bad(f"{name}: Test blieb gruen")
            continue
        treffer = [z for z in p.stdout.splitlines() if z.strip().startswith("FAIL")]
        if any(pruefpunkt in z for z in treffer):
            ok(f"{name}: rot bei '{pruefpunkt}'")
        else:
            bad(f"{name}: rot, aber nicht bei '{pruefpunkt}'")
            print("\n".join(treffer[:4]))

    print(f"\nErgebnis: {pass_} ok, {fail} FAIL")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
