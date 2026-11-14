"""Die Verteilung des Statusbereichs auf Bänder — eine reine Funktion.

Kein Pixel, kein Pillow, keine Zeit: Eingabe ist die verfügbare Höhe und die
Liste der Felder, Ausgabe sind Bänder. Damit lässt sich die Regel prüfen,
ohne ein Panel zu öffnen (Regel „Anzeigefelder").

**Die Zusage ist die Summe, nicht die Absicht:** Die Bänder sind
überschneidungsfrei und liegen vollständig im Bereich — nachrechenbar, nicht
nur behauptet.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Band", "verteile", "Platzfehler"]


class Platzfehler(ValueError):
    """Der Bereich ist zu klein für die Felder, die bleiben **müssen**."""


@dataclass(frozen=True)
class Band:
    """Ein Feld mit seinem Streifen: ``oben`` (Zeile) und ``hoehe`` (Zeilen)."""

    feld: object
    oben: int
    hoehe: int
    gekuerzt: bool = False      # Höhe unter dem Wunsch (aber über dem Minimum)

    @property
    def unten(self) -> int:
        return self.oben + self.hoehe


def verteile(hoehe: int, felder) -> list[Band]:
    """Bänder von oben nach unten, in der Reihenfolge der Priorität.

    Regeln, in dieser Reihenfolge:

    1. Felder, die nichts zu zeigen haben (``sichtbar(kontext)`` sagt nein),
       bekommen kein Band. Das muss der Aufrufer vorher filtern — hier gilt:
       was übergeben wird, will gezeigt werden.
    2. Reicht die Höhe für alle Wünsche, bekommt jedes Feld seinen Wunsch;
       der Rest verteilt sich **gleichmäßig** auf alle (kein Feld wird
       allein fett).
    3. Reicht sie nicht, wird zuerst das Feld mit der **kleinsten
       Priorität** gekürzt (Priorität wie im Arbiter: kleinere Zahl zuerst),
       bis auf seine Mindesthöhe, dann das nächste.
    4. Reicht es dann noch nicht, fällt das Feld mit der kleinsten
       Priorität **ganz** weg — nicht halb gezeichnet. Das wird nicht
       verschwiegen: der Aufrufer bekommt die Liste der weggelassenen
       Felder über :func:`verteile_mit_befund`.
    5. Bleibt am Ende Platz übrig (weil alle gekürzt sind), bekommt ihn das
       Feld mit der **höchsten** Priorität — dort steht der Text, der
       Lesbarkeit am meisten braucht.
    """
    return verteile_mit_befund(hoehe, felder)[0]


def verteile_mit_befund(hoehe: int, felder):
    """Wie :func:`verteile`, dazu die Namen der weggelassenen Felder."""
    liste = sorted(felder, key=lambda f: (f.prioritaet, f.name))
    hoehe = int(hoehe)
    if hoehe <= 0 or not liste:
        return [], [f.name for f in liste]

    wunsch = [max(int(f.mindestens), int(f.wunsch)) for f in liste]
    mindest = [max(1, int(f.mindestens)) for f in liste]
    weg: list[str] = []

    # 3./4.: **Erst ganze Felder weglassen, dann kürzen.** Ein Feld, das nur
    # noch halb so hoch ist wie gewünscht, ist nicht mehr lesbar — dann lieber
    # gar nicht. Von der kleinsten Priorität nach oben (höhere Zahl zuerst),
    # bis die Wünsche der übrigen passen. Das wichtigste Feld bleibt immer;
    # es wird erst gekürzt, wenn es allein noch zu groß ist.
    reihenfolge = sorted(range(len(liste)), key=lambda i: (-liste[i].prioritaet, liste[i].name))
    for i in reihenfolge:
        if sum(wunsch) <= hoehe:
            break
        if sum(1 for w in wunsch if w > 0) <= 1:
            break
        wunsch[i] = 0
        weg.append(liste[i].name)

    # 5.: Kürzen, was übrig ist und nicht passt (dann ist es das wichtigste
    # Feld allein). Nie unter die Mindesthöhe -- reicht auch die nicht, ist
    # der Bereich zu klein (Platzfehler statt halb gezeichnet).
    while sum(wunsch) > hoehe:
        luft = [(i, wunsch[i] - mindest[i]) for i in reihenfolge if wunsch[i] - mindest[i] > 0]
        if not luft:
            break
        i, spielraum = luft[0]
        wunsch[i] -= min(spielraum, sum(wunsch) - hoehe)

    if sum(wunsch) > hoehe:
        # Selbst die Mindesthöhen passen nicht: das ist kein Layoutfehler,
        # den man stillschweigend hinnehmen darf.
        raise Platzfehler(
            f"Statusbereich {hoehe} Zeilen reicht nicht für die Mindesthöhen "
            f"({', '.join(f'{liste[i].name}={wunsch[i]}' for i in range(len(liste)) if wunsch[i])})")

    # 2.: gleichmäßig verteilen, was übrig ist.
    rest = hoehe - sum(wunsch)
    offen = [i for i in range(len(liste)) if wunsch[i] > 0]
    while rest > 0 and offen:
        schritt = max(1, rest // len(offen))
        for i in offen:
            if rest <= 0:
                break
            zugabe = min(schritt, rest)
            wunsch[i] += zugabe
            rest -= zugabe

    baender: list[Band] = []
    oben = 0
    for i, f in enumerate(liste):
        if wunsch[i] <= 0:
            continue
        baender.append(Band(feld=f, oben=oben, hoehe=wunsch[i],
                            gekuerzt=wunsch[i] < int(f.wunsch)))
        oben += wunsch[i]
    return baender, weg
