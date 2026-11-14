"""Eigene Moods ablegen — zwei Quellen, eine Reihenfolge (DESIGN 3.3b).

Der Agent darf Ausdrücke erfinden und behalten. Damit das nicht in einer
offenen Tür endet, stehen hier die Grenzen an **einer** Stelle: Namensform,
Schutz des Eingebauten, Regel 2 (Validierung), Obergrenze der Bibliothek.

Die Bibliothek selbst (``registry.py``) bleibt zuständig für Nummern,
Herkunft und Aufräumen; dieses Modul verdrahtet sie mit einer Datei und
einem Namen aus dem Modell.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .registry import Registry

#: Ein Name ist ein Feld, kein Pfad — trotzdem geprüft: Das Modell schreibt
#: ihn, und was ein Modell schreibt, ist Eingabe (Regel 5p).
NAME_RE = re.compile(r"^[A-Z0-9_-]{1,24}$")

#: Tiefer als das wird nicht gemischt. Ein Modell, das 40 Ebenen schickt,
#: baut keine Form, sondern eine Tiefenbombe.
MAX_TIEFE = 6


class AblageFehler(ValueError):
    """Der Wunsch ist nicht erfüllbar — und es wird gesagt, warum."""


def pruefname(name) -> str:
    """Den Namen in die Form bringen, in der er gespeichert wird."""
    text = str(name or "").strip().upper().replace(" ", "_")
    if not NAME_RE.match(text):
        raise AblageFehler(
            f"Name {name!r} passt nicht: 1–24 Zeichen aus A–Z, 0–9, _ und -")
    return text


def _tiefe(wert, ebene: int = 0) -> int:
    """Wie tief ist ein JSON-Gebilde verschachtelt?"""
    if isinstance(wert, dict) and wert:
        return max(_tiefe(v, ebene + 1) for v in wert.values())
    if isinstance(wert, list) and wert:
        return max(_tiefe(v, ebene + 1) for v in wert)
    return ebene


def _mischen(ziel: dict, quelle: dict) -> dict:
    """``quelle`` in ``ziel`` mischen, ohne die Vorlage zu verändern.

    Verschachtelte Objekte werden gemischt, Listen und Zahlen ersetzt: Eine
    Farbe ``[10, 20, 30]`` ist ein Wert, kein Feld zum Auffüllen.
    """
    for key, wert in quelle.items():
        if isinstance(wert, dict) and isinstance(ziel.get(key), dict):
            ziel[key] = _mischen(ziel[key], wert)
        else:
            ziel[key] = copy.deepcopy(wert)
    return ziel


def bauen(registry: Registry, name: str, von: str = "",
          felder: dict | None = None) -> dict:
    """Einen neuen Mood aus Vorbild und/oder Feldern bauen.

    Ohne beides gibt es keinen Ausdruck — erfunden wird aus etwas, nicht aus
    dem Nichts (DESIGN 3.3b, „Vorbild statt Schema").
    """
    ziel = pruefname(name)
    if felder is not None and not isinstance(felder, dict):
        raise AblageFehler("'felder' muss ein JSON-Objekt sein")
    if felder and _tiefe(felder) > MAX_TIEFE:
        raise AblageFehler("Felder zu tief verschachtelt (mehr als "
                           f"{MAX_TIEFE} Ebenen)")

    roh: dict = {}
    quelle = str(von or "").strip()
    if quelle:
        eintrag = registry.find(quelle)
        if eintrag is None:
            raise AblageFehler(
                f"Vorbild {quelle!r} ist nicht in der Bibliothek — die Liste "
                "gibt das Werkzeug 'moods'")
        roh = copy.deepcopy(eintrag.mood)

    if not roh and not felder:
        raise AblageFehler(
            "Ohne 'von' (Vorbild) und ohne 'felder' gibt es nichts zu "
            "bauen. Nenne einen vorhandenen Ausdruck als Vorbild oder die "
            "Felder, die geändert werden sollen.")

    if felder:
        roh = _mischen(roh or {}, felder)
    roh["name"] = ziel
    return roh


def anlegen(registry: Registry, pfad: str | Path, name: str, *,
            von: str = "", felder: dict | None = None):
    """Einen Ausdruck aufnehmen, prüfen und speichern.

    Rückgabe ``(Entry, Report)``. Ein eingebauter Ausdruck wird **nicht**
    überschrieben: Er ist ein Beispiel, kein Platz zum Ablegen.
    """
    ziel = pruefname(name)
    vorhanden = registry.find(ziel)
    if vorhanden is not None and vorhanden.protected:
        raise AblageFehler(
            f"{ziel} ist eingebaut und bleibt, wie es ist. Nimm einen "
            "anderen Namen oder leite mit 'von' einen eigenen ab.")

    roh = bauen(registry, ziel, von=von, felder=felder)
    eintrag, bericht = registry.add(roh, origin="generated", name=ziel)
    registry.save(pfad, nur_eigene=True)
    return eintrag, bericht


def entfernen(registry: Registry, pfad: str | Path, name: str) -> str:
    """Einen vom Agenten angelegten Ausdruck löschen. Eingebaute nie."""
    ziel = pruefname(name)
    eintrag = registry.find(ziel)
    if eintrag is None:
        raise AblageFehler(f"{ziel} ist nicht in der Bibliothek")
    if eintrag.protected:
        raise AblageFehler(f"{ziel} ist eingebaut und wird nicht gelöscht")
    registry.remove(ziel)
    registry.save(pfad, nur_eigene=True)
    return ziel


def lade(mitgeliefert: str | Path, eigene: str | Path, *,
         capacity: int = 200) -> tuple[Registry, list[str]]:
    """Beide Quellen laden: erst die mitgelieferte, dann die eigene.

    Rückgabe ``(Registry, Hinweise)``. Ein kaputter **eigener** Bestand ist
    ein Befund, kein Startabbruch — das Gesicht ist Beiwerk des Dienstes
    (DESIGN 3.3b). Eine kaputte mitgelieferte Datei bleibt dagegen ein
    Fehler: Ohne sie gäbe es kein Gesicht, und stillschweigend blind zu
    laufen wäre die falsche Antwort.
    """
    reg = Registry.load(mitgeliefert, capacity=capacity)
    hinweise: list[str] = []

    p = Path(eigene)
    if not p.exists():
        return reg, hinweise
    try:
        eigene_reg = Registry.load(p, capacity=capacity)
    except Exception as exc:                         # noqa: BLE001 — Befund
        hinweise.append(f"Moods: eigener Bestand nicht lesbar ({exc}) — "
                        "nur die eingebauten")
        return reg, hinweise

    uebernommen = 0
    for eintrag in eigene_reg.entries():
        # Die Herkunft aus der Datei gilt; ein mitgelieferter Name mit
        # gleichem Wort bleibt geschützt (Registry.add behält 'builtin').
        reg.add(eintrag.mood, origin=eintrag.origin)
        uebernommen += 1
    if uebernommen:
        hinweise.append(f"Moods: {uebernommen} eigene(r) Ausdruck/Ausdrücke "
                        f"aus {p.name}")
    return reg, hinweise
