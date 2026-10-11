"""Werkzeug: ``python3 -m chimera.displays <befehl>``

    erkennen [--json]     Welche Anzeige steckt dran? (rc 0 gewählt, 1 nicht)
    liste                 bekannte Module mit Kurzdaten
    profil <typ>          display.json eines Moduls (JSON) -- liest der Installer
    kennung <dc> [rst]    ST7789-Kennung roh lesen (Messwerkzeug)
"""

from __future__ import annotations

import json
import sys

from . import registry


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "erkennen":
        from . import erkennen
        return erkennen.main(rest)
    if cmd == "liste":
        for typ, p in registry.profile().items():
            print(f"{typ:<12} {p.breite}x{p.hoehe} {p.farben:<9} {p.bildrate:>4g}/s  {p.darstellung:<18} {p.name}")
        return 0
    if cmd == "profil":
        if not rest:
            print("profil <typ>", file=sys.stderr)
            return 2
        try:
            print(json.dumps(registry.profil(rest[0]).roh, ensure_ascii=False, indent=2))
        except KeyError as exc:
            print(exc.args[0], file=sys.stderr)
            return 1
        return 0
    if cmd == "kennung":
        from . import st7789
        if not rest:
            print("kennung <dc> [rst]", file=sys.stderr)
            return 2
        rst = int(rest[1]) if len(rest) > 1 and rest[1] != "-" else None
        print(st7789.kennung_lesen(int(rest[0]), rst).hex())
        return 0
    print(f"unbekannter Befehl: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
