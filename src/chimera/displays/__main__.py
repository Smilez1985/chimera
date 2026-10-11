"""Werkzeug: ``python3 -m chimera.displays <befehl>``

    erkennen [--json]     Welche Anzeige steckt dran? (rc 0 gewählt, 1 nicht)
    liste                 bekannte Module mit Kurzdaten
    profil <typ>          display.json eines Moduls (JSON) -- liest der Installer
    ton <typ> [--json]    Ton des Moduls zur Laufzeit bereitstellen (root):
                          Overlays laden, Mixer setzen, ALSA-Karte nachweisen
                          (rc 0 Karte da, 1 nicht, 2 Modul ohne Ton/unbekannt)
    kennung <dc> [rst]    ST7789-Kennung roh lesen (Messwerkzeug)
    mikro [--json]        Mikrofone messen (Testtoene ueber den Lautsprecher):
                          beide | links | rechts | keins
                          (rc 0 mind. eins brauchbar, 1 keins, 2 Messung gescheitert)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

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
    if cmd == "ton":
        from . import ton
        args = [a for a in rest if not a.startswith("--")]
        if not args:
            print("ton <typ> [--json]", file=sys.stderr)
            return 2
        try:
            p = registry.profil(args[0])
        except KeyError as exc:
            print(exc.args[0], file=sys.stderr)
            return 2
        if not (p.ton or {}).get("alsa_karte"):
            print(f"{args[0]}: Modul ohne Ton", file=sys.stderr)
            return 2
        b = ton.bereitstellen(p)
        if b.da:
            b.fehler.extend(ton.mixer_setzen(p))
        if "--json" in rest:
            print(json.dumps(asdict(b), ensure_ascii=False, indent=2))
        else:
            for g in b.geladen:
                print(f"  geladen: {g}")
            for f in b.fehler:
                print(f"  FEHLER: {f}", file=sys.stderr)
            print(f"Ton {b.karte}: {'da' if b.da else 'nicht da'}"
                  f"{' -- ' + b.hinweis if b.hinweis else ''}")
        return 0 if b.da and not b.fehler else 1
    if cmd == "mikro":
        from . import mikro
        return mikro.main(rest)
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
