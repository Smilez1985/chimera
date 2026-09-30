"""Die Statuszeile am unteren Rand (Regel 7c/7d).

Das Panel ist 240x280, das Gesicht rechnet gegen die kurze Seite. Die
unteren Zeilen bleiben frei -- der Renderer setzt das Gesicht dafür schon
etwas höher als die geometrische Mitte (``FACE_CY = 0.44``).

Dieses Modul entscheidet **nicht**, wer angezeigt wird. Das macht der
gemeinsame Verwalter (:mod:`chimera.arbiter`), der auch die LED auflöst.
Hier steht nur, was Chimeras Quellen sind, wie sie gewichtet werden und
wie der Gewinner zu Pixeln wird.

Warum die Trennung: Die Auflösungsregeln sind für LED und Text dieselben
(Architekturregel 7c). Zwei Umsetzungen derselben Regeln driften
auseinander, sobald eine davon einen Sonderfall bekommt.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..arbiter import Arbiter, Slot

__all__ = ["QUELLEN", "REIHENFOLGE", "StatusLine", "Stil"]

# --- Quellenkatalog ---------------------------------------------------------
#
# Abstände von mindestens 10, damit eine neue Quelle dazwischenpasst, ohne
# dass alle anderen umnummeriert werden müssen (Regel 7c). Geprüft wird das
# von `Arbiter.abstaende_pruefen` -- eine Zusage, die niemand prüft, ist
# eine Absichtserklärung.
#
# Die Auswahl ist Chimeras, nicht die der Vorlage: HATFaces hat Quellen für
# Gateway-Befehle und Plugin-Hinweise, beides gibt es hier nicht. Dafür hat
# Chimera etwas, das dort fehlt -- der Anbieter kann ausfallen, weil das
# Sprachmodell außerhalb des Geräts läuft (Regel 5).
QUELLEN: dict[str, int] = {
    "abschaltung":   100,  # geordnetes Herunterfahren
    "hitze":          90,  # Temperaturwarnung, mit Erneuerungsbedingung
    "anbieter_weg":   80,  # Ollama/Anthropic nicht erreichbar
    "antwort":        60,  # kurzer Text aus dem Gespräch
    "agentenstatus":  50,  # denkt / hört / antwortet
    "akku":           30,  # PiSugar unter Schwelle
    "leerlauf":       10,  # Beschriftung, wenn sonst nichts ansteht
}

# Dritte Auflösungsstufe: Bei gleicher Priorität und gleichem Zeitstempel
# entscheidet diese Reihenfolge. Ohne sie wäre das Ergebnis nicht
# reproduzierbar.
REIHENFOLGE: tuple[str, ...] = tuple(
    sorted(QUELLEN, key=lambda q: (-QUELLEN[q], q))
)


@dataclass(frozen=True)
class Stil:
    """Wie die Zeile aussieht. Pro Quelle wählbar.

    Absichtlich klein gehalten: Was hier nicht steht, kann auch nicht
    auseinanderlaufen. Die Vorlage hat Typewriter-Effekte, Laufschrift und
    Sprechblasen -- das ist Aufwand, der sich erst lohnt, wenn jemand ihn
    vermisst.
    """

    vordergrund: tuple[int, int, int] = (230, 230, 230)
    hintergrund: tuple[int, int, int] | None = (0, 0, 0)
    mittig: bool = True


STILE: dict[str, Stil] = {
    "abschaltung":  Stil(vordergrund=(255, 120, 120)),
    "hitze":        Stil(vordergrund=(255, 190, 90)),
    "anbieter_weg": Stil(vordergrund=(255, 190, 90)),
    "leerlauf":     Stil(vordergrund=(120, 120, 120)),
}


class StatusLine:
    """Hält die Statuszeile und zeichnet den Gewinner.

    Aufruf:

        sl = StatusLine(hoehe=40)
        sl.melden("agentenstatus", "denkt nach", jetzt_ms=t, laufzeit_ms=800)
        sl.zeichnen(bild, jetzt_ms=t)
    """

    def __init__(self, *, hoehe: int = 40, schrift=None) -> None:
        self.hoehe = int(hoehe)
        self._schrift = schrift
        self._arbiter = Arbiter(reihenfolge=REIHENFOLGE)

        # Die Abstände werden beim Bauen geprüft, nicht beim Prüflauf: Ein
        # falsch einsortierter Katalog soll auffallen, sobald jemand ihn
        # anfasst -- nicht erst, wenn zufällig ein Test läuft.
        beanstandungen = Arbiter.abstaende_pruefen(QUELLEN)
        if beanstandungen:
            raise ValueError(
                "Quellenkatalog verletzt die Abstandsregel:\n  "
                + "\n  ".join(beanstandungen)
            )

    # --- Eintragen --------------------------------------------------------

    def melden(
        self,
        quelle: str,
        text: str,
        *,
        jetzt_ms: int,
        laufzeit_ms: int | None = None,
        erneuern=None,
    ) -> None:
        """Etwas anzuzeigen geben. Verdrängt die vorherige Meldung derselben
        Quelle.

        Unbekannte Quellen werden abgelehnt, statt mit einer erfundenen
        Priorität zu laufen. Eine geratene Priorität wäre genau die Art
        stiller Fehler, bei der die Zeile später "manchmal" falsch ist.
        """
        if quelle not in QUELLEN:
            raise KeyError(
                f"unbekannte Quelle: {quelle!r} -- "
                f"bekannt sind: {', '.join(sorted(QUELLEN))}"
            )
        self._arbiter.setzen(
            Slot(
                quelle=quelle,
                prioritaet=QUELLEN[quelle],
                inhalt=str(text),
                laufzeit_ms=laufzeit_ms,
                erneuern=erneuern,
            ),
            jetzt_ms,
        )

    def zuruecknehmen(self, quelle: str) -> bool:
        return self._arbiter.loeschen(quelle)

    # --- Abfragen ---------------------------------------------------------

    def text(self, jetzt_ms: int) -> str | None:
        """Was gerade angezeigt werden soll -- oder ``None``."""
        g = self._arbiter.gewinner(jetzt_ms)
        return None if g is None else str(g.inhalt)

    def quelle(self, jetzt_ms: int) -> str | None:
        g = self._arbiter.gewinner(jetzt_ms)
        return None if g is None else g.quelle

    # --- Zeichnen ---------------------------------------------------------

    def zeichnen(self, bild, jetzt_ms: int, *, nur_zeile: bool = False):
        """Die Zeile in den unteren Rand von ``bild`` zeichnen.

        Gibt das Bild zurück -- auch unverändert, wenn nichts anliegt. Ein
        Rückgabewert ``None`` im Leerfall würde jeden Aufrufer zwingen, den
        Sonderfall zu behandeln.

        ``nur_zeile`` sagt, dass der Aufrufer das Gesicht diesmal nicht neu
        gezeichnet hat (Sparmodus im Hitzefall). Für das Zeichnen der Zeile
        selbst ändert das nichts -- der Schalter steht hier, damit der
        Aufrufer seine Absicht mitgeben kann und später eine Teilübertragung
        daran anknüpfen kann.

        Die SPI-Übertragung ist der Engpass: 28,1 von 39,3 ms je Bild,
        gemessen auf dem Zero 2 W. Wer nur die unteren 40 von 280 Zeilen
        überträgt, spart den größten Posten. **Das ist noch nicht gebaut** --
        `panel.py` schreibt immer das ganze Bild. Steht als offener Punkt in
        der Roadmap, damit es nicht als erledigt gilt (Regel 10h).
        """
        g = self._arbiter.gewinner(jetzt_ms)
        if g is None:
            return bild

        stil = STILE.get(g.quelle, Stil())
        breite, hoehe = bild.size
        oben = hoehe - self.hoehe

        try:
            from PIL import ImageDraw
        except ImportError:
            # Ohne Pillow wird nicht gezeichnet. Das ist kein Fehler des
            # Aufrufers und darf ihn nicht abbrechen -- aber es wird auch
            # nicht so getan, als sei etwas passiert.
            return bild

        zeichner = ImageDraw.Draw(bild)

        # Der Hintergrund wird in beiden Fällen gleich gezeichnet -- die
        # Zeile bekommt ihren Balken, ob nun das ganze Bild neu entsteht
        # oder nur sie. `nur_zeile` ändert, was der AUFRUFER vorher tut
        # (Gesicht zeichnen oder nicht), nicht was hier passiert.
        #
        # Hier standen erst zwei Zweige mit identischem Inhalt. Das sah nach
        # einer Unterscheidung aus, die es nicht gibt.
        if stil.hintergrund is not None:
            zeichner.rectangle([0, oben, breite, hoehe], fill=stil.hintergrund)

        text = str(g.inhalt)
        schrift = self._schrift
        if stil.mittig:
            try:
                links, o, rechts, u = zeichner.textbbox((0, 0), text, font=schrift)
                x = max(0, (breite - (rechts - links)) // 2)
                y = oben + max(0, (self.hoehe - (u - o)) // 2)
            except Exception:
                x, y = 4, oben + 4
        else:
            x, y = 4, oben + 4

        zeichner.text((x, y), text, fill=stil.vordergrund, font=schrift)
        return bild
