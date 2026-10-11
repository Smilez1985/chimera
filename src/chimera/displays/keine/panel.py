"""Kein Panel: zählt, was ankäme. Dasselbe wie ``NullPanel`` -- als Modul,
damit die Registry keine Sonderregel braucht."""

from __future__ import annotations

from pathlib import Path

from ..base import NullPanel, Profil

HIER = Path(__file__).resolve().parent


def profil() -> Profil:
    return Profil.aus_datei(HIER / "display.json")


class KeinePanel(NullPanel):
    def __init__(self, **kw) -> None:
        p = profil()
        super().__init__(width=kw.get("width", p.breite), height=kw.get("height", p.hoehe),
                         convert=kw.get("convert", True), fps=int(kw.get("fps", p.bildrate)))
        self.profil = p
