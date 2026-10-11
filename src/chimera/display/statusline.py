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

from ..arbiter import Arbiter, Slot  # Slot: Grundinhalt als Rueckfall

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
    # Grau, aber hell genug fuer das Panel: (120, 120, 120) war nach dem
    # Software-Dimming des Renderers am Geraet kaum vom Schwarz zu trennen.
    "leerlauf":     Stil(vordergrund=(170, 170, 170)),
}

# Schriften, die auf dem Zielgeraet liegen (DietPi/Debian: fonts-dejavu-core).
# Fehlt jede, bleibt Pillows eingebaute Schrift -- in der gewuenschten Groesse,
# wenn Pillow das kann (ab 10.1), sonst die kleine Bitmapschrift.
SCHRIFTEN: tuple[str, ...] = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

def _schrift_laden(groesse: int):
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    for pfad in SCHRIFTEN:
        try:
            return ImageFont.truetype(pfad, groesse)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=groesse)
    except TypeError:  # Pillow < 10.1 kennt keine Groesse
        return ImageFont.load_default()


class StatusLine:
    """Hält die Statuszeile und zeichnet den Gewinner.

    Aufruf:

        sl = StatusLine(hoehe=40)
        sl.melden("agentenstatus", "denkt nach", jetzt_ms=t, laufzeit_ms=800)
        sl.zeichnen(bild, jetzt_ms=t)
    """

    def __init__(self, *, hoehe: int = 40, schrift=None, grundtext=None) -> None:
        self.hoehe = int(hoehe)
        # Ohne Vorgabe die Schrift selbst laden, passend zur Zeilenhoehe.
        # Pillows eingebaute Bitmapschrift ist rund 10 px hoch -- auf dem
        # Whisplay (1,69", 240 px) am Geraet nicht zu sehen (smilez,
        # 11.10.2026: "Statusleiste sehe ich nicht").
        self._schrift = schrift if schrift is not None else _schrift_laden(
            max(10, int(self.hoehe * 0.45)))
        # Grundinhalt (DESIGN §5: "Mood-Name, Akku, Agent-Zustand"): eine
        # Funktion ohne Argument, die den Text liefert. Er steht, wenn keine
        # Quelle etwas meldet -- vorher blieb die Zeile ohne Meldung leer,
        # und ohne Sprachmodell meldete nie jemand etwas.
        self._grundtext = grundtext
        self._arbiter = Arbiter(reihenfolge=REIHENFOLGE)
        # Fertig gezeichneter Streifen und wofuer er gilt (siehe zeichnen()).
        self._streifen = None
        self._streifen_schluessel = None

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
        g = self._gewinner(jetzt_ms)
        return None if g is None else str(g.inhalt)

    def quelle(self, jetzt_ms: int) -> str | None:
        g = self._gewinner(jetzt_ms)
        return None if g is None else g.quelle

    def _gewinner(self, jetzt_ms: int):
        """Gewinner des Verwalters -- oder der Grundinhalt als ``leerlauf``.

        Der Grundinhalt ist kein Eintrag im Verwalter, sondern der Rueckfall,
        wenn dort niemand steht. Er laeuft so nicht ab und muss nicht erneuert
        werden; jede Meldung verdraengt ihn, weil sie im Verwalter steht.
        Eine Meldung der Quelle ``leerlauf`` selbst geht vor (sie steht im
        Verwalter).
        """
        g = self._arbiter.gewinner(jetzt_ms)
        if g is not None or self._grundtext is None:
            return g
        try:
            text = self._grundtext()
        except Exception:
            # Ein kaputter Grundtext darf kein Bild aufhalten (Regel 8a:
            # sichtbar wird es daran, dass die Zeile leer bleibt).
            return None
        if not text:
            return None
        return Slot(quelle="leerlauf", prioritaet=QUELLEN["leerlauf"], inhalt=str(text))

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
        g = self._gewinner(jetzt_ms)
        if g is None:
            return bild

        stil = STILE.get(g.quelle, Stil())
        breite, hoehe = bild.size
        oben = hoehe - self.hoehe

        # Puffer (11.10.2026): Der Text aendert sich selten, das Bild 15-mal
        # je Sekunde. Gemessen am chimera-pi: neu rendern 1,67 ms je Bild,
        # fertigen Streifen einkopieren 0,04 ms. Neu gezeichnet wird nur, wenn
        # sich Text, Quelle oder Bildgroesse aendern. Der Puffer gilt nur mit
        # deckendem Hintergrund -- ohne ihn muss der Text auf das Bild selbst.
        if stil.hintergrund is not None:
            schluessel = (g.quelle, str(g.inhalt), breite, self.hoehe, bild.mode)
            if self._streifen is None or self._streifen_schluessel != schluessel:
                try:
                    from PIL import Image
                except ImportError:
                    return bild
                streifen = Image.new(bild.mode, (breite, self.hoehe), stil.hintergrund)
                self._text_zeichnen(streifen, 0, g, stil)
                self._streifen, self._streifen_schluessel = streifen, schluessel
            bild.paste(self._streifen, (0, oben))
            return bild

        try:
            from PIL import ImageDraw
        except ImportError:
            # Ohne Pillow wird nicht gezeichnet. Das ist kein Fehler des
            # Aufrufers und darf ihn nicht abbrechen -- aber es wird auch
            # nicht so getan, als sei etwas passiert.
            return bild
        self._text_zeichnen(bild, oben, g, stil)
        return bild

    def _text_zeichnen(self, bild, oben: int, g, stil: "Stil") -> None:
        """Hintergrund (falls deckend) und Text ab Zeile ``oben`` zeichnen."""
        from PIL import ImageDraw
        breite = bild.size[0]
        zeichner = ImageDraw.Draw(bild)

        # Der Hintergrund wird in beiden Fällen gleich gezeichnet -- die
        # Zeile bekommt ihren Balken, ob nun das ganze Bild neu entsteht
        # oder nur sie. `nur_zeile` ändert, was der AUFRUFER vorher tut
        # (Gesicht zeichnen oder nicht), nicht was hier passiert.
        #
        # Hier standen erst zwei Zweige mit identischem Inhalt. Das sah nach
        # einer Unterscheidung aus, die es nicht gibt.
        if stil.hintergrund is not None:
            zeichner.rectangle([0, oben, breite, oben + self.hoehe], fill=stil.hintergrund)

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
