"""Welche Anzeige steckt dran? (DISPLAYS.md §4, DESIGN Regel 6e)

Jedes Modul bringt in ``display.json`` eine Prüfliste mit. Jede Prüfung
hat eine **Klasse**:

  pflicht       ohne Treffer kommt das Modul nicht in Frage
                (ST7789-Kennung mit der DC-Leitung des Boards)
  eindeutig     ein Treffer wählt das Modul -- wenn die Pflicht erfüllt ist
                (Codec am I2C-Bus: nur die Whisplay hat einen)
  eingerichtet  Overlay, Kernelmodul, ALSA-Karte: belegt nur, dass schon
                einmal installiert wurde -- wählt NICHT (smilez, 11.10.)
  rueckfall     „keine Anzeige", wenn nichts anderes passt

Gewählt wird automatisch nur, wenn **genau ein** Modul eindeutig ist.
Sonst werden die Kandidaten mit ihren Belegen gemeldet, und die
Einstellung ``CHIMERA_ANZEIGE`` entscheidet (Regel 10g: nicht raten).

Läuft als root VOR dem Dienst (Boot-Abgleich): Die Kennung braucht freie
Leitungen; ein laufender Dienst hält sie. Belegte Leitungen sind deshalb
ein eigener Befund (``belegt``), kein „kein Panel".

``CHIMERA_ROOT`` setzt alle Dateipfade um (Tests mit erfundener Wurzel).
Dort, wo Hardware angefasst würde (SPI, GPIO, I2C-Quick-Write), liefert
ein gesetztes ``CHIMERA_ROOT`` „nicht prüfbar" -- es sei denn, die
Attrappe liegt unter ``<root>/chimera-probe/<art>-<kennzeichen>``.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import i2c, registry, st7789
from .gpio import LeitungBelegt


@dataclass
class Beleg:
    typ: str
    klasse: str
    art: str
    treffer: bool | None       # None = nicht prüfbar
    text: str


@dataclass
class Befund:
    gewaehlt: str | None
    grund: str
    kandidaten: list[str]
    belegt: list[str]            # Module, deren Leitungen belegt waren
    belege: list[Beleg] = field(default_factory=list)
    einstellung: str | None = None

    def als_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, ensure_ascii=False, indent=2)


# --- Einzelprüfungen -------------------------------------------------------

def _root() -> str:
    return os.environ.get("CHIMERA_ROOT", "")


def _attrappe(art: str, kennzeichen: str) -> str | None:
    """In Tests: Inhalt einer Attrappendatei, sonst None."""
    r = _root()
    if not r:
        return None
    p = Path(r) / "chimera-probe" / f"{art}-{kennzeichen}"
    return p.read_text().strip() if p.is_file() else ""


def _lies(pfad: str) -> str:
    try:
        return Path(_root() + pfad).read_text(errors="ignore")
    except OSError:
        return ""


def pruefe_st7789_kennung(pr: dict) -> tuple[bool | None, str]:
    dc, rst, soll = int(pr["dc"]), pr.get("rst"), str(pr["wert"]).lower()
    att = _attrappe("st7789", f"dc{dc}")
    if att is not None:
        ist = att
    else:
        try:
            ist = st7789.kennung_lesen(dc, None if rst is None else int(rst),
                                       gpiochip=pr.get("gpiochip", "/dev/gpiochip0"),
                                       spi_bus=int(pr.get("spi_bus", 0)),
                                       spi_cs=int(pr.get("spi_cs", 0))).hex()
        except LeitungBelegt as exc:
            raise
        except OSError as exc:
            return None, f"ST7789 nicht prüfbar ({exc.strerror or exc})"
    if not ist:
        return None, "ST7789 nicht prüfbar (keine Antwort gelesen)"
    return ist == soll, f"ST7789-Kennung DC{dc}: {ist} (erwartet {soll})"


def pruefe_i2c_chip(pr: dict) -> tuple[bool | None, str]:
    bus = int(pr.get("bus", 1))
    adressen = [int(a, 0) if isinstance(a, str) else int(a) for a in pr["adressen"]]
    if not i2c.bus_da(bus, root=_root()):
        return None, f"I2C-Bus {bus} nicht aktiv (dtparam=i2c_arm=on fehlt?)"
    for a in adressen:
        att = _attrappe("i2c", f"{bus}-{a:02x}")
        if att is not None:
            if att == "1":
                return True, f"I2C {bus}: Chip 0x{a:02x} antwortet (Attrappe)"
            continue
        da = i2c.chip_da(bus, a, root=_root())
        if da:
            return True, f"I2C {bus}: Chip 0x{a:02x} antwortet"
        if da is None:
            return None, f"I2C {bus}: 0x{a:02x} nicht prüfbar (/dev/i2c-{bus} fehlt -- Modul i2c-dev?)"
    return False, f"I2C {bus}: keiner von {', '.join(f'0x{a:02x}' for a in adressen)} antwortet"


def pruefe_overlay(pr: dict) -> tuple[bool | None, str]:
    zeile = pr["wert"]
    for k in ("/boot/firmware/config.txt", "/boot/config.txt"):
        t = _lies(k)
        if t:
            da = any(z.strip() == zeile for z in t.splitlines())
            return da, f"{k}: {zeile} {'vorhanden' if da else 'fehlt'}"
    return None, "keine Bootkonfiguration gefunden"


def pruefe_alsa(pr: dict) -> tuple[bool | None, str]:
    t = _lies("/proc/asound/cards")
    da = pr["wert"].lower() in t.lower()
    return da, f"ALSA-Karte {pr['wert']} {'vorhanden' if da else 'fehlt'}"


def pruefe_kernelmodul(pr: dict) -> tuple[bool | None, str]:
    kver = _lies("/proc/sys/kernel/osrelease").strip() or os.uname().release
    basis = Path(_root() + f"/lib/modules/{kver}")
    if not basis.is_dir():
        return None, f"/lib/modules/{kver} fehlt"
    da = any(basis.rglob(f"{pr['wert']}*.ko*"))
    return da, f"Kernelmodul {pr['wert']}* {'gebaut' if da else 'nicht gebaut'}"


def pruefe_busy_pegel(pr: dict) -> tuple[bool | None, str]:
    """E-Paper: BUSY-Leitung nach Reset. Gemessen wird erst mit dem
    E-Paper-Modul; bis dahin ehrlich „nicht prüfbar"."""
    att = _attrappe("busy", str(pr.get("busy", "")))
    if att is not None and att != "":
        return att == "1", f"BUSY{pr.get('busy')} (Attrappe) = {att}"
    return None, "BUSY-Pegel: Prüfung noch nicht gebaut"


PRUEFUNGEN = {
    "st7789_kennung": pruefe_st7789_kennung,
    "i2c_chip": pruefe_i2c_chip,
    "overlay": pruefe_overlay,
    "alsa": pruefe_alsa,
    "kernelmodul": pruefe_kernelmodul,
    "busy_pegel": pruefe_busy_pegel,
    "immer": lambda pr: (True, "Rückfall"),
}


# --- Gesamtbild ----------------------------------------------------------

def erkennen(einstellung: str | None = None) -> Befund:
    einstellung = einstellung if einstellung is not None else os.environ.get("CHIMERA_ANZEIGE") or None
    profile = registry.profile()
    belege: list[Beleg] = []
    kandidaten: list[str] = []
    eindeutige: list[str] = []
    belegt: list[str] = []
    rueckfall: str | None = None

    for typ, p in profile.items():
        pflicht_ok: bool | None = True
        pflicht_da = False
        eindeutig = False
        try:
            for pr in p.erkennung:
                klasse, art = pr.get("klasse"), pr.get("art")
                f = PRUEFUNGEN.get(art)
                if f is None:
                    belege.append(Beleg(typ, klasse, art, None, f"unbekannte Prüfart {art!r}"))
                    continue
                if klasse == "rueckfall":
                    rueckfall = typ
                    continue
                treffer, text = f(pr)
                belege.append(Beleg(typ, klasse, art, treffer, text))
                if klasse == "pflicht":
                    pflicht_da = True
                    if treffer is False:
                        pflicht_ok = False
                    elif treffer is None and pflicht_ok is True:
                        pflicht_ok = None
                elif klasse == "eindeutig" and treffer is True:
                    eindeutig = True
        except LeitungBelegt as exc:
            belegt.append(typ)
            belege.append(Beleg(typ, "pflicht", "st7789_kennung", None, f"Leitung belegt: {exc}"))
            continue
        if pflicht_da and pflicht_ok is False:
            continue
        if pflicht_da and pflicht_ok is None and not eindeutig:
            continue
        if not pflicht_da and not eindeutig:
            continue
        kandidaten.append(typ)
        if eindeutig and pflicht_ok is True:
            eindeutige.append(typ)

    if einstellung:
        if einstellung in profile:
            return Befund(einstellung, "Einstellung CHIMERA_ANZEIGE", kandidaten, belegt, belege, einstellung)
        return Befund(None, f"CHIMERA_ANZEIGE={einstellung!r} ist kein bekanntes Modul "
                      f"({', '.join(sorted(profile))})", kandidaten, belegt, belege, einstellung)
    if belegt:
        return Befund(None, f"Leitungen belegt ({', '.join(belegt)}) -- läuft ein Dienst? "
                      "Erkennung vor dem Dienst ausführen.", kandidaten, belegt, belege)
    if len(eindeutige) == 1:
        return Befund(eindeutige[0], "eindeutiger Treffer", kandidaten, belegt, belege)
    if len(eindeutige) > 1:
        return Befund(None, f"mehrere eindeutige Treffer: {', '.join(eindeutige)}", kandidaten, belegt, belege)
    if len(kandidaten) == 1:
        # Genau ein Modul erfüllt die Pflicht, keines ist eindeutig: Das
        # ist der GamePi13-Fall (Kennung ja, kein Codec). Ein einziger
        # Kandidat ist kein Raten -- aber gemeldet wird es.
        return Befund(kandidaten[0], "einziger Kandidat (Pflicht erfüllt)", kandidaten, belegt, belege)
    if kandidaten:
        return Befund(None, f"mehrdeutig: {', '.join(kandidaten)} -- CHIMERA_ANZEIGE setzen",
                      kandidaten, belegt, belege)
    if rueckfall:
        return Befund(rueckfall, "nichts erkannt -- Rückfall", kandidaten, belegt, belege)
    return Befund(None, "nichts erkannt", kandidaten, belegt, belege)


def main(argv: list[str]) -> int:
    json_aus = "--json" in argv
    b = erkennen()
    if json_aus:
        print(b.als_json())
    else:
        for bl in b.belege:
            m = {True: "ja ", False: "nein", None: "?  "}[bl.treffer]
            print(f"  [{m}] {bl.typ:<10} {bl.klasse:<12} {bl.text}")
        print(f"Gewählt: {b.gewaehlt or '-'} ({b.grund})")
    return 0 if b.gewaehlt else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
