"""Anzeigemodule finden und öffnen.

Ein Modul ist ein Ordner neben dieser Datei mit ``display.json`` und
``panel.py``. Die Registry liest den Ordner, nicht eine Liste -- wer ein
Panel hinzufügt, legt einen Ordner an (DISPLAYS.md §5, wie bei den Moods).

``panel.py`` muss eine Klasse mit Endung ``Panel`` exportieren, die ohne
Pflichtargumente konstruierbar ist, und ``profil()``.
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path

from .base import Panel, Profil

log = logging.getLogger(__name__)
HIER = Path(__file__).resolve().parent


def modul_ordner() -> list[Path]:
    """Alle Ordner mit ``display.json``, alphabetisch."""
    return sorted(p.parent for p in HIER.glob("*/display.json"))


def typen() -> list[str]:
    return [o.name for o in modul_ordner()]


def profile() -> dict[str, Profil]:
    out: dict[str, Profil] = {}
    for o in modul_ordner():
        try:
            p = Profil.aus_datei(o / "display.json")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            log.warning("Anzeigemodul %s unlesbar: %s", o.name, exc)
            continue
        if p.typ != o.name:
            # Ordnername und Typ müssen übereinstimmen, sonst zeigt
            # state/anzeige auf einen Namen, den niemand findet.
            log.warning("Anzeigemodul %s: typ=%r passt nicht zum Ordner", o.name, p.typ)
            continue
        out[p.typ] = p
    return out


def profil(typ: str) -> Profil:
    p = profile().get(typ)
    if p is None:
        raise KeyError(f"Anzeigemodul unbekannt: {typ!r} (bekannt: {', '.join(typen())})")
    return p


def panel_klasse(typ: str) -> type[Panel]:
    profil(typ)  # unbekannt → KeyError mit Liste
    mod = importlib.import_module(f"{__package__}.{typ}.panel")
    klassen = [v for k, v in vars(mod).items()
               if isinstance(v, type) and issubclass(v, Panel) and k.endswith("Panel")
               and v.__module__ == mod.__name__]
    if len(klassen) != 1:
        raise ImportError(f"{typ}/panel.py muss genau eine *Panel-Klasse exportieren, "
                          f"hat {len(klassen)}")
    return klassen[0]


def oeffne(typ: str, **kw) -> Panel:
    return panel_klasse(typ)(**kw)
