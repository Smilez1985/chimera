"""Gegenprobe zur Chat-Wahl der Türen (`tests/test_chat_wahl.py`).

Jede Zusage wird in einer Kopie des Quellbaums verfaelscht; der Test muss an
der genannten Stelle rot werden. Die echte Datei bleibt unberuehrt.

Geprüft werden die zwei tragenden Zusagen:
  * Die Tür liest die Wahl wirklich (und nur die drei Felder) -- nicht "irgendwas".
  * Eine abgelehnte Wahl wird gemeldet, nicht verschluckt.

Aufruf: python3 tests/gegenprobe_chat_wahl.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
ROOT = HIER.parent
WAHL = ROOT / "src" / "chimera" / "chat_wahl.py"
MAIN = ROOT / "src" / "chimera" / "__main__.py"
TEST = HIER / "test_chat_wahl.py"

# Je Mutation: Name, Datei, Muster, Ersatz, Pruefpunkt im Test.
MUTATIONEN = [
    ("auftrag-ignoriert-die-wahl", WAHL,
     "        return lesen(pfad=pfad)",
     "        return {}",
     "auftrag liest die Wahl"),
    ("lesen-nimmt-alles", WAHL,
     "    return {f: wahl[f] for f in FELDER\n            if isinstance(wahl.get(f), str) and wahl[f]}",
     "    return dict(wahl)",
     "stream gehoert nicht zur Chat-Wahl"),
    ("ablehnung-wird-leer", WAHL,
     "    raise WahlFehler(fehler.get(\"text\") or \"unbekannter Grund\",\n"
     "                     fehler.get(\"code\") or \"\")",
     "    return {}",
     "kaputte Datei still als leer behandelt"),
    ("leerer-wert-geht-gar-nicht-raus", WAHL,
     "    _antwort({\"op\": \"wahl_feld_setzen\", \"feld\": feld, \"wert\": wert}, pfad)",
     "    if wert:\n        _antwort({\"op\": \"wahl_feld_setzen\", \"feld\": feld, \"wert\": wert}, pfad)",
     "leerer Wert löscht"),
    ("cli-deutet-none-als-leer", MAIN,
     "        if wert is None:",
     "        if not wert:",
     "'' löscht das Feld"),
    ("cli-frage-ohne-wahl", MAIN,
     "        turn = chi.ask(args.frage, TERMINAL, **chat_wahl.auftrag())",
     "        turn = chi.ask(args.frage, TERMINAL)",
     "die Frage bekam die Wahl"),
    ("cli-laeuft-trotz-ablehnung", MAIN,
     "    if not _wahl_setzen(args):\n        return 2",
     "    _wahl_setzen(args)",
     "rc 2 bei abgelehnter Wahl"),
]


def lauf(datei: Path, inhalt: str) -> subprocess.CompletedProcess:
    """Den Test gegen eine Kopie des Baums laufen lassen."""
    with tempfile.TemporaryDirectory() as tmp:
        baum = Path(tmp) / "projekt"
        shutil.copytree(ROOT / "src", baum / "src")
        (baum / "tests").mkdir(exist_ok=True)
        shutil.copy(TEST, baum / "tests" / "test_chat_wahl.py")
        ziel = baum / datei.relative_to(ROOT)
        ziel.write_text(inhalt, encoding="utf-8")
        return subprocess.run([sys.executable, str(baum / "tests" / "test_chat_wahl.py")],
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

    print("=== Gegenprobe Chat-Wahl ===")

    basis = lauf(WAHL, WAHL.read_text(encoding="utf-8"))
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
