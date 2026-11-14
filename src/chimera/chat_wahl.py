"""Die Chat-Wahl — Anbieter, Modell, Denkstufe — fuer die Tueren im Dienst.

Die Ablage gehoert dem Gateway (``config/wahl/wahl.json``). Hier wird sie nur
gelesen und ueber ``wahl_lesen`` / ``wahl_feld_setzen`` geaendert: die Regeln
(gültige Kennung, bekannte Denkstufe, leeren Wert loeschen) stehen in
``rust/crates/tor/src/daten.rs``. Eine zweite Prüfung an dieser Stelle liefe
auseinander und wäre bei jeder neuen Denkstufe falsch (DESIGN, „ein Feld, ein
Ort").

Ohne erreichbares Gateway gibt es keine Wahl: Dann gilt die Reihenfolge des
Anbieters (5h). Ein stiller Rueckfall auf ein geratenes Modell findet nicht
statt -- ``lesen`` sagt, dass es nicht ging.
"""

from __future__ import annotations

import logging

from .provider.base import LLMError, Unavailable
from .provider.gateway import anfragen

log = logging.getLogger("chimera.wahl")

#: Die Felder einer Chat-Wahl, in dieser Reihenfolge. Dieselben Namen wie in
#: ``wahl.json`` und in der Sitzung (``Session.ask``).
FELDER = ("anbieter", "modell", "denken")

#: Eine Antwort des Gateways auf `wahl_lesen` kommt aus dem Speicher, nicht
#: aus dem Netz -- kurz warten genuegt.
WARTEN = 5.0


class WahlFehler(LLMError):
    """Das Gateway hat die Wahl abgelehnt (oder konnte sie nicht lesen).

    ``code`` ist der Code des Dienstes (``wert_ungueltig``,
    ``feld_unbekannt``, ``wahl_kaputt``) -- der Aufrufer gibt ihn weiter,
    statt ihn zu erraten.
    """

    def __init__(self, text: str, code: str = ""):
        super().__init__(text)
        self.text = text
        self.code = code


def _antwort(anfrage: dict, pfad: str | None) -> dict:
    """Eine Anfrage ans Gateway und die Antwort prüfen.

    ``Unavailable`` heisst: kein Gateway. Alles andere mit ``ok: false`` ist
    eine Ablehnung und wird als :class:`WahlFehler` gemeldet.
    """
    antwort = anfragen(anfrage, warten=WARTEN, pfad=pfad)
    if antwort.get("ok") is True:
        return antwort
    fehler = antwort.get("fehler") or {}
    raise WahlFehler(fehler.get("text") or "unbekannter Grund",
                     fehler.get("code") or "")


def lesen(*, pfad: str | None = None) -> dict[str, str]:
    """Die gespeicherte Wahl, nur die gesetzten Felder.

    Ein Feld, das nicht in der Datei steht, fehlt auch im Ergebnis -- so
    kommt ``lesen()`` unverändert als Schlüsselwörter für ``Session.ask``
    durch.
    """
    wahl = _antwort({"op": "wahl_lesen"}, pfad).get("wahl") or {}
    if not isinstance(wahl, dict):
        raise WahlFehler("wahl.json ist kein Objekt", "wahl_kaputt")
    return {f: wahl[f] for f in FELDER
            if isinstance(wahl.get(f), str) and wahl[f]}


def setzen(feld: str, wert: str, *, pfad: str | None = None) -> None:
    """Ein Feld der Wahl setzen. Leerer Wert **löscht** es (wie im Web)."""
    if feld not in FELDER:
        raise ValueError(f"{feld!r} ist keine Chat-Wahl (bekannt: {FELDER})")
    _antwort({"op": "wahl_feld_setzen", "feld": feld, "wert": wert}, pfad)


def auftrag(*, pfad: str | None = None) -> dict[str, str]:
    """Die Wahl als Schlüsselwörter für eine Frage -- ohne Gateway leer.

    Gedacht für jede Frage einer Tür: Was in ``wahl.json`` steht, gilt für
    sie. Ist das Gateway weg, steht dort nichts, und die Reihenfolge des
    Anbieters entscheidet (5h) -- das ist kein Fehler, aber auch nichts,
    was man verschweigen müsste: es steht im Protokoll.
    """
    try:
        return lesen(pfad=pfad)
    except Unavailable as exc:
        log.debug("Keine Wahl (Gateway nicht erreichbar): %s", exc)
        return {}
