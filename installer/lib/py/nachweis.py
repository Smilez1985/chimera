"""Nachweis von Schritt 50 in EINEM Python-Start.

Aufruf (installer/steps/50-python.sh, pruef_ok):
    <venv-python> nachweis.py [--anzeige <typ>] [--] <anforderung> ...

Drei Pruefungen, dieselben wie vorher in drei Starts:
  1. Abhaengigkeiten mit Version (pydep.fehlend) -- erfuellt?
  2. Anzeigemodul ladbar (registry.panel_klasse), OHNE das Panel zu oeffnen
     -- nur wenn --anzeige gesetzt ist.
  3. Das Modul selbst: `python -m chimera --pruefen --offline` mit
     CHIMERA_ANZEIGE=keine (kein Netz, kein Panel), Exitcode zaehlt.

Getrennt kostete das am chimera-pi 2,6 s (warm) bzw. 4,7 s (kalt), in
einem Start 1,7 s bzw. 3,8 s: Jeder Start laedt Interpreter und chimera
erneut.

Ausgabe: je Pruefung eine Zeile "ok <was>" bzw. "FEHLT <was>: <grund>".
rc 0 alles erfuellt, 1 etwas fehlt, 2 Aufruf falsch.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))


def _argumente(argv: list[str]) -> tuple[str, list[str]] | None:
    anzeige, anf = "", []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--anzeige":
            if i + 1 >= len(argv):
                return None
            anzeige = argv[i + 1]
            i += 2
            continue
        if a == "--":
            anf.extend(argv[i + 1:])
            break
        anf.append(a)
        i += 1
    return anzeige, anf


def main(argv: list[str]) -> int:
    args = _argumente(argv)
    if args is None:
        print("Aufruf: nachweis.py [--anzeige <typ>] [--] <anforderung> ...", file=sys.stderr)
        return 2
    anzeige, anforderungen = args
    rc = 0

    # 1. Abhaengigkeiten -- dieselbe Messung wie lib/python.sh pydep_fehlend.
    sys.path.insert(0, HIER)
    import pydep  # noqa: E402  (liegt neben dieser Datei)
    fehlt = pydep.fehlend(anforderungen)
    if fehlt:
        for z in fehlt:
            print(f"FEHLT Abhaengigkeit: {z}")
        rc = 1
    else:
        print(f"ok Abhaengigkeiten ({len(anforderungen)})")

    # 2. Anzeigemodul -- laden, nicht oeffnen (das belegte die Leitungen
    # des laufenden Dienstes).
    if anzeige:
        try:
            from chimera.displays import registry
            registry.panel_klasse(anzeige)
            print(f"ok Anzeigemodul {anzeige}")
        except Exception as exc:                       # noqa: BLE001
            print(f"FEHLT Anzeigemodul {anzeige}: {type(exc).__name__}: {exc}")
            rc = 1

    # 3. Das Modul selbst. CHIMERA_ANZEIGE wird VOR dem Import gesetzt;
    # chimera liest es erst beim Oeffnen des Panels, aber nichts soll
    # davon abhaengen, wann.
    os.environ["CHIMERA_ANZEIGE"] = "keine"
    try:
        from chimera.__main__ import main as chimera_main
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            m_rc = chimera_main(["--pruefen", "--offline"])
    except SystemExit as exc:
        m_rc = exc.code if isinstance(exc.code, int) else 1
    except Exception as exc:                           # noqa: BLE001
        print(f"FEHLT Modul chimera: {type(exc).__name__}: {exc}")
        return 1
    if m_rc:
        print(f"FEHLT Modul chimera: --pruefen rc {m_rc}")
        rc = 1
    else:
        print("ok Modul chimera (--pruefen --offline)")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
