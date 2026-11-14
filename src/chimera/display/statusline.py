"""Der Statusbereich am unteren Rand (Regeln 7c, 7d, „Anzeigefelder").

Das Panel ist 240×280, das Gesicht rechnet gegen die kurze Seite. Die
unteren Zeilen bleiben frei -- der Renderer setzt das Gesicht dafür schon
etwas höher als die geometrische Mitte (``FACE_CY = 0.44``).

**Zwei getrennte Fragen, zwei Zuständigkeiten:**

- *Wer* angezeigt wird, entscheidet der gemeinsame Verwalter
  (:mod:`chimera.arbiter`) — dieselben Regeln wie für die LED (7c). Das ist
  die Meldungsquelle, ein Platz je Quelle, drei Auflösungsstufen.
- *Wo und wie* es steht, entscheidet die Liste der **Felder**
  (:mod:`chimera.display.felder`, :mod:`chimera.display.layout`). Jedes Feld
  bekommt ein Band und zeichnet nur darin; ein neues Feld ist eine neue
  Datei (Regel „Anzeigefelder").

Dieses Modul hält beide zusammen: es nimmt Meldungen an, holt beim Zeichnen
die sichtbaren Felder, verteilt die Höhe und legt den fertigen Streifen
unten ins Bild. Der Streifen wird gepuffert -- Text ändert sich selten, das
Bild 15-mal je Sekunde.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..arbiter import Arbiter, Slot          # Slot: Grundinhalt als Rueckfall
from . import felder as feldliste
from .layout import verteile_mit_befund

log = logging.getLogger("chimera.display.statusline")

__all__ = ["QUELLEN", "REIHENFOLGE", "StatusLine", "Stil", "STILE"]

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
    """Wie der Text einer Meldungsquelle aussieht.

    Absichtlich klein gehalten: Was hier nicht steht, kann auch nicht
    auseinanderlaufen. Die **Höhe** steht hier nicht mehr -- die gehört dem
    Feld (Regel „Anzeigefelder").
    """

    vordergrund: tuple[int, int, int] = (230, 230, 230)


STILE: dict[str, Stil] = {
    "abschaltung":  Stil(vordergrund=(255, 120, 120)),
    "hitze":        Stil(vordergrund=(255, 190, 90)),
    "anbieter_weg": Stil(vordergrund=(255, 190, 90)),
    # Grau, aber hell genug fuer das Panel: (120, 120, 120) war nach dem
    # Software-Dimming des Renderers am Geraet kaum vom Schwarz zu trennen.
    "leerlauf":     Stil(vordergrund=(170, 170, 170)),
}


class StatusLine:
    """Hält den Statusbereich und zeichnet ihn aus Feldern.

    Aufruf:

        sl = StatusLine(hoehe=40)
        sl.melden("agentenstatus", "denkt nach", jetzt_ms=t, laufzeit_ms=800)
        sl.zeichnen(bild, jetzt_ms=t, kontext={"modell": "deepseek-flash"})
    """

    def __init__(self, *, hoehe: int = 40, schrift=None, grundtext=None,
                 felder=None) -> None:
        self.hoehe = int(hoehe)
        # ``schrift`` bleibt angenommen, damit alte Aufrufer nicht brechen;
        # benutzt wird sie nicht mehr: Die Größe folgt der Bandhöhe.
        self._schrift = schrift
        # Grundinhalt (DESIGN §5.1: „Mood-Name, Akku, Agent-Zustand"): eine
        # Funktion ohne Argument, die den Ausdrucksnamen liefert. Er steht,
        # wenn keine Quelle etwas meldet.
        self._grundtext = grundtext
        #: Zusätzliche Werte für die Felder (Modell, Anbieter, Akku …).
        #: Der Dienst setzt hier eine Funktion ein; die Statuszeile fragt
        #: sie je Bild, damit die Anzeige nicht altert.
        self.kontext_quelle = None
        self._arbiter = Arbiter(reihenfolge=REIHENFOLGE)

        # Fertig gezeichneter Streifen und wofür er gilt.
        self._streifen = None
        self._streifen_schluessel = None

        # Die Felder kommen aus dem Verzeichnis (ein Feld = eine Datei).
        # ``felder`` überschreibt sie -- für Tests und für ein Gerät, das
        # bewusst weniger zeigen soll.
        if felder is None:
            self._felder = feldliste.alle()
        else:
            self._felder = list(felder)
        # Was beim Laden schiefging, wird behalten und beim ersten Zeichnen
        # ins Protokoll gegeben -- nicht verschluckt (Regel 8a).
        self.ladeprobleme = list(feldliste.ladeprobleme)

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

    def kontext(self, jetzt_ms: int, zusatz: dict | None = None) -> dict:
        """Was die Felder zu sehen bekommen.

        ``text`` (Gewinner des Verwalters) und ``mood`` (Ausdrucksname) sind
        hier gesetzt; alles Weitere -- Modell, Akku, Provider -- kommt vom
        Aufrufer. Ein Feld liest nur, was es braucht.
        """
        g = self._gewinner(jetzt_ms)
        werte: dict = {}
        if self.kontext_quelle is not None:
            try:
                werte.update(self.kontext_quelle() or {})
            except Exception:                  # noqa: BLE001
                # Eine kaputte Quelle darf kein Bild anhalten -- und sie
                # wird benannt, nicht verschluckt.
                log.exception("Statusbereich: kontext_quelle gescheitert")
        werte.update(zusatz or {})
        werte["text"] = "" if g is None else str(g.inhalt)
        werte["quelle"] = "" if g is None else str(g.quelle)
        stil = STILE.get("" if g is None else g.quelle, Stil())
        werte.setdefault("farbe", stil.vordergrund)
        if self._grundtext is not None and "mood" not in werte:
            try:
                werte["mood"] = str(self._grundtext() or "")
            except Exception:                  # noqa: BLE001
                werte["mood"] = ""
        return werte

    def zeichnen(self, bild, jetzt_ms: int, *, nur_zeile: bool = False,
                 kontext: dict | None = None):
        """Die Felder in den unteren Rand von ``bild`` zeichnen.

        Gibt das Bild zurück -- auch unverändert, wenn kein Feld etwas zu
        zeigen hat. Ein Rückgabewert ``None`` im Leerfall würde jeden
        Aufrufer zwingen, den Sonderfall zu behandeln.

        ``nur_zeile`` sagt, dass der Aufrufer das Gesicht diesmal nicht neu
        gezeichnet hat (Sparmodus im Hitzefall). Für das Zeichnen selbst
        ändert das nichts.

        Die SPI-Übertragung ist der Engpass: 28,1 von 39,3 ms je Bild,
        gemessen auf dem Zero 2 W. Wer nur die unteren Zeilen überträgt,
        spart den größten Posten. **Das ist noch nicht gebaut** -- `panel.py`
        schreibt immer das ganze Bild (ROADMAP, Regel 10h).
        """
        if self.ladeprobleme:
            for grund in self.ladeprobleme:
                log.warning("Feld: %s", grund)
            self.ladeprobleme = []

        werte = self.kontext(jetzt_ms, kontext)
        sichtbar = [f for f in self._felder if _sichtbar(f, werte)]
        baender, weg = verteile_mit_befund(self.hoehe, sichtbar)
        if weg:
            log.info("Statusbereich: kein Platz für %s", ", ".join(weg))
        if not baender:
            return bild

        breite, hoehe = bild.size
        oben = hoehe - self.hoehe

        from PIL import Image
        schluessel = (
            bild.mode, breite, hoehe,
            tuple((b.feld.name, b.oben, b.hoehe) for b in baender),
            tuple(sorted((k, str(v)) for k, v in werte.items())),
        )
        if self._streifen is None or self._streifen_schluessel != schluessel:
            streifen = Image.new(bild.mode, (breite, self.hoehe), (0, 0, 0))
            for band in baender:
                flaeche = _flaeche(streifen, band)
                try:
                    band.feld.zeichnen(flaeche, werte)
                except Exception:              # noqa: BLE001
                    # Ein kaputtes Feld darf das Bild nicht anhalten --
                    # aber es wird benannt, nicht verschluckt.
                    log.exception("Feld %r konnte nicht zeichnen", band.feld.name)
            self._streifen, self._streifen_schluessel = streifen, schluessel
        bild.paste(self._streifen, (0, oben))
        return bild


def _sichtbar(feld, werte: dict) -> bool:
    """Fragt das Feld, ob es etwas zu zeigen hat -- und stürzt dabei nicht ab."""
    try:
        return bool(feld.sichtbar(werte))
    except Exception:                          # noqa: BLE001
        log.exception("Feld %r: sichtbar() gescheitert", feld.name)
        return False


def _flaeche(streifen, band):
    from .feld import Flaeche
    return Flaeche(streifen, band.oben, band.hoehe)
