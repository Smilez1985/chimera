"""Auflösung konkurrierender Anzeigequellen (Architekturregel 7c).

Mehrere Stellen wollen dasselbe Ausgabegerät bespielen: Die Statuszeile
zeigt Agentenzustand, Temperaturwarnung und Anbieterausfall; die LED zeigt
Stimmung, Sprechen und Alarm. Wer gewinnt, entscheidet dieser Verwalter --
und zwar derselbe für beide.

**Ein Verwalter, zwei Nutzer.** Die Vorlage (HATFaces) spezifiziert dasselbe
Muster zweimal und nennt das ausdrücklich "nur Stil-Analogie, keine
Code-Kopplung". Für Chimera ist das die falsche Wahl: Zwei Stellen, die
dieselbe Auflösungslogik unabhängig umsetzen, driften auseinander, sobald
eine davon einen Sonderfall bekommt.

Die Unterschiede zwischen LED und Text liegen in der *Darstellung* (Farben
mischen gegen Glyphen zeichnen), nicht in der *Auflösung*. Darum kennt
dieses Modul weder Farben noch Text -- es entscheidet nur, wer dran ist.

Was hier absichtlich NICHT passiert:

* Kein eigener Zeitgeber. Die Zeit kommt von außen (Regel 7d). Damit ist
  jede Entscheidung prüfbar, ohne zu warten.
* Kein Zeichnen. Der Gewinner wird zurückgegeben, gezeichnet wird woanders.
* Keine Warteschlange je Quelle. Pro Quelle gibt es genau einen Platz --
  ein neuer Eintrag verdrängt den alten. Damit kann keine Quelle die
  Auflösung fluten.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable

__all__ = ["Slot", "Arbiter", "MIN_ABSTAND"]

# Prioritäten werden in Zehnerschritten vergeben, damit eine neue Quelle
# dazwischen passt, ohne dass alle anderen umnummeriert werden müssen.
#
# Das Gegenbeispiel steht in der eigenen Blaupause: Die Regelnummern sind
# in Einfügereihenfolge gewachsen, darum steht `10k` heute zwischen `10b`
# und `10c`. Eine Ordnung, die nicht mehr ordnet.
MIN_ABSTAND = 10


@dataclass(frozen=True)
class Slot:
    """Ein Anzeigewunsch einer Quelle.

    Unveränderlich: Ein "Update" ist ein neuer Slot derselben Quelle, der
    den alten verdrängt. Das erspart die Frage, ob ein Slot sich unter der
    Hand geändert hat, während jemand ihn hielt.

    ``inhalt`` ist absichtlich unbestimmt (``Any``). Für die Statuszeile
    steht dort Text, für die LED eine Farbe. Der Verwalter fasst es nie an.

    ``laufzeit_ms`` ist ``None`` für Einträge, die bleiben, bis sie
    verdrängt oder gelöscht werden.

    ``erneuern`` ist der Weg für anhaltende Zustände: kurze Laufzeit plus
    eine Bedingung, die sie zurücksetzt. Ein Alarm mit 4 Sekunden und der
    Bedingung "solange zu heiß" erlischt von selbst, wenn die Bedingung
    wegfällt. Der Gegenentwurf -- lange Laufzeit plus explizites Löschen --
    hinterlässt einen Eintrag, sobald jemand das Löschen vergisst.
    """

    quelle: str
    prioritaet: int
    inhalt: Any = None
    muster: str = "fest"
    laufzeit_ms: int | None = None
    gesetzt_ms: int = 0
    erneuern: Callable[[], bool] | None = None
    marken: dict[str, str] = field(default_factory=dict)

    def abgelaufen(self, jetzt_ms: int) -> bool:
        """Ist dieser Slot zum Zeitpunkt ``jetzt_ms`` verfallen?

        Ein Slot ohne Laufzeit verfällt nie. Einer mit Erneuerungsbedingung
        verfällt nur, wenn die Bedingung nicht mehr zutrifft.
        """
        if self.laufzeit_ms is None:
            return False
        if jetzt_ms - self.gesetzt_ms < self.laufzeit_ms:
            return False
        if self.erneuern is not None:
            try:
                if self.erneuern():
                    return False
            except Exception:
                # Eine kaputte Bedingung darf den Verwalter nicht anhalten.
                # Sie zählt als "trifft nicht mehr zu" -- der Slot verfällt,
                # statt für immer stehen zu bleiben. Lieber eine Anzeige zu
                # wenig als eine, die nicht mehr weggeht.
                return True
        return True


class Arbiter:
    """Hält je Quelle einen Slot und sagt, wer gerade gewinnt.

    Aufruf:

        a = Arbiter()
        a.setzen(Slot("temperatur", 90, "zu heiss", laufzeit_ms=4000), jetzt)
        gewinner = a.gewinner(jetzt)
    """

    def __init__(self, *, reihenfolge: tuple[str, ...] = ()) -> None:
        """``reihenfolge`` entscheidet bei Gleichstand.

        Sie ist die dritte und letzte Stufe der Auflösung und darum keine
        Zierde: Ohne sie hängt das Ergebnis bei zwei gleich alten Slots
        gleicher Priorität davon ab, in welcher Reihenfolge das Wörterbuch
        durchlaufen wird. Ein Fehler, der sich so verhält, lässt sich nicht
        nachstellen.

        Quellen, die nicht in der Liste stehen, kommen danach -- nach Namen
        sortiert, damit auch dieser Fall festgelegt ist.
        """
        self._slots: dict[str, Slot] = {}
        self._reihenfolge = reihenfolge

    # --- Eintragen und entfernen -----------------------------------------

    def setzen(self, slot: Slot, jetzt_ms: int) -> None:
        """Einen Slot eintragen. Verdrängt den vorherigen derselben Quelle."""
        if slot.gesetzt_ms == 0:
            slot = replace(slot, gesetzt_ms=jetzt_ms)
        self._slots[slot.quelle] = slot

    def loeschen(self, quelle: str) -> bool:
        """Einen Slot entfernen. Gibt zurück, ob es einen gab."""
        return self._slots.pop(quelle, None) is not None

    def leeren(self) -> None:
        self._slots.clear()

    # --- Abfragen ---------------------------------------------------------

    def __len__(self) -> int:
        return len(self._slots)

    def __contains__(self, quelle: object) -> bool:
        return quelle in self._slots

    def aktive(self, jetzt_ms: int) -> list[Slot]:
        """Alle nicht verfallenen Slots, in Gewinnreihenfolge.

        Räumt dabei die verfallenen weg -- das ist der einzige Ort, an dem
        aufgeräumt wird. Ein eigener Aufräumlauf wäre ein zweiter Zeitgeber
        (Regel 7d).
        """
        verfallen = [q for q, s in self._slots.items() if s.abgelaufen(jetzt_ms)]
        for q in verfallen:
            del self._slots[q]
        return sorted(self._slots.values(), key=self._rang)

    def gewinner(self, jetzt_ms: int) -> Slot | None:
        """Der Slot, der gerade angezeigt werden soll -- oder ``None``."""
        aktive = self.aktive(jetzt_ms)
        return aktive[0] if aktive else None

    # --- Auflösung --------------------------------------------------------

    def _rang(self, slot: Slot) -> tuple:
        """Sortierschlüssel: kleiner gewinnt.

        Drei Stufen, in dieser Reihenfolge:

        1. höchste Priorität
        2. jüngster Zeitstempel -- bei gleicher Priorität gewinnt der
           neuere Wunsch, sonst könnte ein alter Eintrag einen frischen
           derselben Wichtigkeit blockieren
        3. feste Quellenreihenfolge -- macht das Ergebnis reproduzierbar
        """
        try:
            idx = self._reihenfolge.index(slot.quelle)
        except ValueError:
            # Unbekannte Quellen hinten, untereinander nach Namen. Auch
            # der Rest ist damit festgelegt statt zufällig.
            idx = len(self._reihenfolge)
        return (-slot.prioritaet, -slot.gesetzt_ms, idx, slot.quelle)

    # --- Selbstprüfung ----------------------------------------------------

    @staticmethod
    def abstaende_pruefen(prioritaeten: dict[str, int]) -> list[str]:
        """Prüft, ob die Prioritäten weit genug auseinanderliegen.

        Gibt die Beanstandungen als Liste zurück, leer heißt in Ordnung.

        Warum das eine Funktion ist und kein Kommentar: Eine Zusage, die
        niemand prüft, ist eine Absichtserklärung. Die Abstände schrumpfen
        beim Einfügen neuer Quellen, und zwar unbemerkt -- genau wie bei
        den Regelnummern.
        """
        beanstandungen: list[str] = []

        doppelt: dict[int, list[str]] = {}
        for name, p in prioritaeten.items():
            doppelt.setdefault(p, []).append(name)
        for p, namen in sorted(doppelt.items()):
            if len(namen) > 1:
                beanstandungen.append(
                    f"Priorität {p} mehrfach vergeben: {', '.join(sorted(namen))}"
                )

        werte = sorted(set(prioritaeten.values()))
        for a, b in zip(werte, werte[1:]):
            if b - a < MIN_ABSTAND:
                beanstandungen.append(
                    f"Abstand {b - a} zwischen {a} und {b} ist kleiner als "
                    f"{MIN_ABSTAND} -- dazwischen passt keine neue Quelle mehr"
                )
        return beanstandungen
