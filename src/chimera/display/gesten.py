"""Tastengesten: fünf Absichten auf einer Taste — als reine Funktion der Zeit.

Die Seitentaste der Whisplay ist **eine** Leitung mit Flanken. Ein kurzer
Druck, ein gehaltener, ein sehr lange gehaltener und mehrere Drücke in Folge
sind verschiedene Absichten; die Bedeutung entsteht aus dem zeitlichen
Verlauf — hier.

| Geste | Bedingung |
|---|---|
| ``kurz`` | losgelassen vor 0,7 s, kein zweiter Druck im Klickfenster |
| ``lang`` | gehalten 0,7–2,0 s, beim Loslassen gemeldet |
| ``halten`` | 2,0 s gehalten — **während** die Taste unten ist gemeldet (Push-to-Talk: Aufnahme an) |
| ``halten_ende`` | Loslassen nach ``halten`` (Push-to-Talk: Aufnahme aus) |
| ``doppelt`` | zwei kurze Drücke im Klickfenster |
| ``dreifach`` | drei oder mehr kurze Drücke im Klickfenster |

**Regel 7d:** Die Erkennung ist eine reine Zustandsmaschine. Sie bekommt die
Zeit von außen (``t``) und gibt zurück, was erkannt wurde; sie schläft nicht
und kennt keinen Faden. Jeder Fall ist damit prüfbar, ohne zu warten.

Schwellen: ``0,7 s`` für „lang" und ``2,0 s`` für „halten" nach der Vorlage
(PiSugar ``whisplay-daemon``, Apache-2.0, HERKUNFT `docs/HERKUNFT.md`, Abschnitt „Der Daemon: warum wir ihn nicht übernehmen": dort
``BUTTON_LONG_PRESS_SEC = 0.7``; der Daemon kannte kein Halten, weil er nur
einmal je Loslassen handelte). Das **Klickfenster** ist bei uns 0,8 s statt
3,0 s: Die Vorlage zählte vier Klicks in drei Sekunden für „zurück"; bei uns
hängt an einem einzelnen kurzen Druck eine Aktion, und die darf nicht drei
Sekunden auf ihre Bestätigung warten.
"""

from __future__ import annotations

import threading
import time

#: Bis zu dieser Dauer (s) gilt ein Druck als kurz.
KURZ_MAX_S = 0.7
#: Ab dieser Dauer (s) gilt ein Druck als gehalten und wird „halten" (hold).
HALTEN_AB_S = 2.0
#: Fenster (s), in dem kurze Drücke zusammen gezählt werden.
KLICK_FENSTER_S = 0.8
#: Entprellung (s): Flanken, die dichter folgen, sind Mechanik, keine Absicht.
#: Am Gerät gemessen (23:01) erzeugte ein Druck bis zu drei Flanken; die alte
#: 5-ms-Abfrage hat das nebenbei verschluckt, Kantenereignisse nicht.
ENTPRELL_S = 0.03

KURZ = "kurz"
LANG = "lang"
HALTEN = "halten"
DOPPELT = "doppelt"
DREIFACH = "dreifach"
#: Ende eines Haltens — kein eigener Modus, sondern das Gegenstück zu
#: ``halten``: Ein Halten, das man nicht beenden kann, taugt nur zum
#: Auslösen (Neustart), nicht zum Sprechen. Push-to-Talk braucht beides:
#: ``halten`` = Aufnahme an, ``halten_ende`` = Aufnahme aus.
HALTEN_ENDE = "halten_ende"

#: Alle Gesten in der Reihenfolge, in der sie gemeldet werden können.
ALLE = (KURZ, LANG, HALTEN, DOPPELT, DREIFACH)


class Gesten:
    """Erkennt kurze, lange, gehaltene und mehrfache Drücke.

    Ablauf: ``taste(True, t)`` beim Drücken, ``taste(False, t)`` beim
    Loslassen, dazwischen ``tick(t)`` — der Aufrufer fragt über ``frist()``,
    wann der nächste ``tick`` fällig ist.
    """

    def __init__(self, *, kurz_max_s: float = KURZ_MAX_S,
                 halten_ab_s: float = HALTEN_AB_S,
                 fenster_s: float = KLICK_FENSTER_S,
                 entprell_s: float = ENTPRELL_S) -> None:
        self.kurz_max_s = float(kurz_max_s)
        self.halten_ab_s = float(halten_ab_s)
        self.fenster_s = float(fenster_s)
        self.entprell_s = float(entprell_s)
        self._letzte_flanke: float | None = None
        if not self.kurz_max_s < self.halten_ab_s:
            raise ValueError("kurz_max_s muss kleiner als halten_ab_s sein")
        self._unten_seit: float | None = None
        self._halten_gemeldet = False
        self._klicks = 0
        self._klick_frist: float | None = None

    # --- Zustand ----------------------------------------------------------

    @property
    def unten(self) -> bool:
        return self._unten_seit is not None

    @property
    def klicks(self) -> int:
        return self._klicks

    def zuruecksetzen(self) -> None:
        self._letzte_flanke = None
        self._unten_seit = None
        self._halten_gemeldet = False
        self._klicks = 0
        self._klick_frist = None

    # --- Zeit -------------------------------------------------------------

    def frist(self) -> float | None:
        """Wann der nächste ``tick`` fällig ist (monotone Zeit) — sonst None."""
        faellig = []
        if self._unten_seit is not None and not self._halten_gemeldet:
            faellig.append(self._unten_seit + self.halten_ab_s)
        if self._klick_frist is not None:
            faellig.append(self._klick_frist)
        return min(faellig) if faellig else None

    # --- Ereignisse -------------------------------------------------------

    def taste(self, gedrueckt: bool, t: float) -> list[str]:
        """Eine Flanke melden. Rückgabe: erkannte Gesten (meist leer)."""
        # Entprellen: Ein mechanischer Druck erzeugt mehrere Flanken in
        # wenigen Millisekunden. Ohne diese Sperre wird aus einem Druck
        # „dreifach" (am Gerät beobachtet).
        if self._letzte_flanke is not None and t - self._letzte_flanke < self.entprell_s:
            return []
        self._letzte_flanke = t

        if gedrueckt:
            if self._unten_seit is not None:
                return []          # Doppelmeldung/Prellen: schon unten
            self._unten_seit = t
            self._halten_gemeldet = False
            return []

        if self._unten_seit is None:
            return []              # Loslassen ohne Drücken: ignorieren
        dauer = t - self._unten_seit
        self._unten_seit = None

        if dauer >= self.halten_ab_s or self._halten_gemeldet:
            # „halten" lief schon (beim Halten gemeldet); kein Klick. Das
            # Gegenstück gehört dazu, sonst hätte Push-to-Talk kein Ende.
            self._halten_gemeldet = False
            self._klicks = 0
            self._klick_frist = None
            return [HALTEN_ENDE]

        if dauer >= self.kurz_max_s:
            # lang: 0,7 s bis 2,0 s — erst beim Loslassen entscheidbar, weil
            # dieselbe Taste beim Weiterhalten „halten" wird.
            self._klicks = 0
            self._klick_frist = None
            return [LANG]

        self._klicks += 1
        # Noch offen: Kommt im Fenster ein weiterer Druck, wird es doppelt
        # oder dreifach; sonst kurz. Die Entscheidung fällt in ``tick``.
        self._klick_frist = t + self.fenster_s
        return []

    def tick(self, t: float) -> list[str]:
        """Zeit ist vergangen: fällige Entscheidungen treffen."""
        ergebnis: list[str] = []
        if (self._unten_seit is not None and not self._halten_gemeldet
                and t >= self._unten_seit + self.halten_ab_s):
            self._halten_gemeldet = True
            ergebnis.append(HALTEN)
        if self._klick_frist is not None and t >= self._klick_frist:
            self._klick_frist = None
            klicks, self._klicks = self._klicks, 0
            if klicks == 1:
                ergebnis.append(KURZ)
            elif klicks == 2:
                ergebnis.append(DOPPELT)
            elif klicks >= 3:
                ergebnis.append(DREIFACH)
        return ergebnis


class GestenTakt:
    """Ruft ``Gesten.tick`` genau dann, wenn eine Entscheidung fällig ist.

    Die Erkennung selbst kennt keine Uhr (Regel 7d); hier ist der eine Ort,
    an dem gewartet wird — auf die Frist, nicht im Takt. Ein Faden, der
    schläft, kostet nichts.
    """

    def __init__(self, gesten: Gesten, abnehmer, *, name: str = "chimera-geste",
                 uhr=time.monotonic) -> None:
        self.gesten = gesten
        self.abnehmer = abnehmer
        self._uhr = uhr
        self._name = name
        self._ende = threading.Event()
        self._wecken = threading.Event()
        self._faden: threading.Thread | None = None

    def start(self) -> "GestenTakt":
        if self._faden is None:
            self._faden = threading.Thread(target=self._schleife, daemon=True,
                                           name=self._name)
            self._faden.start()
        return self

    def stop(self) -> None:
        self._ende.set()
        self._wecken.set()
        if self._faden is not None:
            self._faden.join(timeout=1.0)
            self._faden = None

    def anstoss(self) -> None:
        """Nach einer Flanke rufen: die Frist kann sich geändert haben."""
        self._wecken.set()

    def _schleife(self) -> None:
        while not self._ende.is_set():
            frist = self.gesten.frist()
            if frist is None:
                self._wecken.wait(0.5)
                self._wecken.clear()
                continue
            warte = frist - self._uhr()
            if warte > 0:
                self._wecken.wait(warte)
                self._wecken.clear()
                continue
            self._wecken.clear()
            for geste in self.gesten.tick(self._uhr()):
                self.abnehmer(geste)
