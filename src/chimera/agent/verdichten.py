"""Verdichten mit Verweis — mechanisch, ohne Modell.

Bis zum 14.11.2026 ließ ``Agent._compact`` ein billiges Modell fünf Sätze
zusammenfassen und warf den Rest weg. Das kostet einen Aufruf je Verdichtung,
erfindet bei Prosa und macht den Verlust unsichtbar: Was fehlte, merkte
niemand — es war einfach nicht mehr im Fenster.

`docs/DESIGN.md` (Architekturregel 8d, „Verdichten im Lauf") verlangt etwas
anderes: **Gelöscht wird nichts.** Ins Fenster kommen

* eine Zusammenfassung **mit Verweis** auf die Zeilen in `verlauf.jsonl`,
* die **offenen Punkte wörtlich**,
* die **Entscheidungen wörtlich**,
* die letzten Turns wörtlich (die bleiben in der Liste, hier nicht Sache).

Was hier steht, ist die reine Entscheidung: aus Nachrichten einen Text
bauen, der die Fundstellen nennt. Kein Netz, kein Modell, kein Zustand —
damit ist es prüfbar, und der Test kann einen Verlust rot machen
(GLOBAL: Summe gegen Gesamtzahl).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Die Marke, an der ein verdichteter Abschnitt im Fenster erkennbar ist.
MARKE = "[Bisheriges Gespräch — verdichtet]"

#: ``- [ ] etwas zu tun`` — dieselbe Form, die das Gedächtnis führt.
_OFFEN = re.compile(r"^\s*(?:[-*+]\s*)?\[ \]\s*(\S.*?)\s*$", re.MULTILINE)

#: ``Entscheidung: …`` — auch fett oder mit Aufzählungszeichen davor.
_ENTSCHEIDUNG = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:\*\*)?Entscheidung(?:en)?(?:\*\*)?\s*:\s*(\S.*?)\s*$",
    re.MULTILINE)

#: Rollen, wie sie im Verlauf vorkommen.
_KURZ = {"user": "Nutzer", "assistant": "Chimera", "tool": "Werkzeug",
         "system": "System"}


def _inhalt(m: dict) -> str:
    c = m.get("content")
    if isinstance(c, list):                     # Werkzeugergebnisse u. Ä.
        c = " ".join(str(x) for x in c)
    return str(c or "")


def offene_punkte(nachrichten: list[dict]) -> list[str]:
    """Alle ``- [ ]`` einer Nachrichtenfolge, wörtlich und in Reihenfolge."""
    out: list[str] = []
    for m in nachrichten:
        out.extend(x.strip() for x in _OFFEN.findall(_inhalt(m)))
    return out


def entscheidungen(nachrichten: list[dict]) -> list[str]:
    """Alle ``Entscheidung:``-Zeilen, wörtlich und in Reihenfolge."""
    out: list[str] = []
    for m in nachrichten:
        out.extend(x.strip() for x in _ENTSCHEIDUNG.findall(_inhalt(m)))
    return out


#: So viele **Runden** bleiben wörtlich im Fenster (Papier OPENMINIS-MUSTER
#: §2.3, Punkt 7: „letzte 3 Nutzer-Runden wörtlich"). Eine Runde beginnt bei
#: einer Nutzer-Nachricht; ein Werkzeugergebnis („Ergebnis von …") und eine
#: frühere Verdichtung beginnen keine Runde — sonst schnitte das Verdichten
#: zwischen Aufruf und Ergebnis und der Zusammenhang wäre sinnentstellt.
RUNDEN_BEHALTEN = 3

#: Woran ein Werkzeugergebnis im Verlauf erkennbar ist (``loop.py``).
ERGEBNIS = "Ergebnis von "


def _ist_rundenbeginn(m: dict) -> bool:
    if m.get("role") != "user":
        return False
    t = _inhalt(m).lstrip()
    return not (t.startswith(ERGEBNIS) or t.startswith("[Bisheriges Gespräch"))


def schnittindex(nachrichten: list[dict], runden: int = RUNDEN_BEHALTEN) -> int:
    """Ab welchem Index die letzten ``runden`` Runden beginnen.

    ``len(nachrichten)`` heißt: keine Runde gefunden — dann bleibt alles
    wörtlich (nichts wird verdichtet, lieber gar nicht als falsch).
    """
    if runden <= 0:
        return len(nachrichten)
    gesehen = 0
    for i in range(len(nachrichten) - 1, -1, -1):
        if _ist_rundenbeginn(nachrichten[i]):
            gesehen += 1
            if gesehen == runden:
                return i
    return len(nachrichten)


def fruehere_verweise(nachrichten: list[dict]) -> list[str]:
    """Die Fundstellen früherer Verdichtungen — wörtlich.

    Wird eine verdichtete Zusammenfassung erneut verdichtet, darf ihr
    **Verweis** nicht verschwinden: Er ist die einzige Spur zu den ganz
    alten Zeilen. Übernommen werden die Zeilen, die eine Fundstelle nennen
    („Zeilen a–b", „nachlesen (von=…)"), nicht die Prosa dazwischen.
    """
    out: list[str] = []
    for m in nachrichten:
        t = _inhalt(m)
        if not t.lstrip().startswith("[Bisheriges Gespräch"):
            continue
        for zeile in t.splitlines():
            z = zeile.strip()
            if z.startswith("- ") and ("Zeilen " in z or "nachlesen" in z):
                out.append(z)
            elif "nachlesen (von=" in z:
                out.append("- " + z)
    return out


@dataclass(frozen=True)
class Bericht:
    """Was beim Verdichten herauskam — und ob es vollständig ist."""

    text: str
    zeilen_von: int
    zeilen_bis: int
    nachrichten: int
    offene_punkte: int
    entscheidungen: int
    ausgelassen: int = 0        # Abschnitte, die der Grenze zum Opfer fielen
    schnitt: int = 0            # Index, ab dem wörtlich bleibt (Rundengrenze)

    @property
    def vollstaendig(self) -> bool:
        """Wahr, wenn kein Abschnitt beschnitten wurde."""
        return not self.ausgelassen


@dataclass
class _Block:
    von: int
    bis: int
    rollen: list[str] = field(default_factory=list)
    anfang: str = ""


def _bloecke(nachrichten: list[dict], von: int, bis: int, groesse: int) -> list[_Block]:
    """Nachrichten in Blöcke teilen, jeder mit seiner Zeilenspanne."""
    genau = (bis - von + 1) == len(nachrichten)
    bloecke: list[_Block] = []
    for i in range(0, len(nachrichten), groesse):
        teil = nachrichten[i:i + groesse]
        if genau:
            a = von + i
            b = von + i + len(teil) - 1
        else:
            # Kein exakter Zeilenbezug (z. B. Fenster ohne Ablage): dann
            # werden die Nummern als Nachrichten-Nummern benannt, nicht
            # als Zeilen — lieber ungenau gesagt als genau gelogen.
            a = i + 1
            b = i + len(teil)
        rollen = [_KURZ.get(m.get("role", ""), m.get("role", "?")) for m in teil]
        anfang = ""
        for m in teil:
            t = " ".join(_inhalt(m).split())
            if t:
                anfang = t[:80] + ("…" if len(t) > 80 else "")
                break
        bloecke.append(_Block(a, b, rollen, anfang))
    return bloecke


def verdichte(nachrichten: list[dict], *, von: int = 1, bis: int = 0,
              runden: int = RUNDEN_BEHALTEN, blockgroesse: int = 5,
              grenze: int = 4000) -> Bericht:
    """Aus Nachrichten einen Text mit Fundstellen bauen.

    ``von``/``bis`` sind die Zeilennummern in ``verlauf.jsonl``, die die
    übergebenen Nachrichten dort einnehmen. Passen sie nicht zur Anzahl,
    wird auf Nachrichten-Nummern ausgewichen und im Text gesagt.

    ``runden`` Runden am Ende gelten als „bleiben wörtlich im Fenster"; die
    Runde ist die Einheit, nicht die Nachricht (Papier OPENMINIS-MUSTER
    §2.3): Ein Schnitt mitten zwischen Werkzeugaufruf und Ergebnis wäre
    sinnentstellend. Der Schnitt liegt **immer** auf einem Rundenbeginn.
    """
    schnitt = schnittindex(nachrichten, runden)
    kopf = list(nachrichten)[:schnitt]
    if bis <= 0:
        bis = von + len(nachrichten) - 1
    if not kopf:
        return Bericht("", von, bis, 0, 0, 0, 0, schnitt)

    punkte = offene_punkte(kopf)
    entscheide = entscheidungen(kopf)
    verweise = fruehere_verweise(kopf)
    bloecke = _bloecke(kopf, von, bis, max(1, blockgroesse))
    genau = (bis - von + 1) == len(kopf)

    kopfzeile = (f"{MARKE} Zeilen {bloecke[0].von}–{bloecke[-1].bis} in "
                 f"verlauf.jsonl, {len(kopf)} Nachrichten"
                 if genau else
                 f"{MARKE} {len(kopf)} ältere Nachrichten (ohne Zeilenbezug)")
    zeilen = [kopfzeile,
              "Den vollen Wortlaut holt das Werkzeug nachlesen "
              f"(von={bloecke[0].von}, bis={bloecke[-1].bis}).", ""]

    def abschnitte(b: list[_Block], knapp: bool) -> list[str]:
        out = []
        for x in b:
            rollen = ", ".join(sorted(set(x.rollen)))
            if knapp or not x.anfang:
                out.append(f"- Zeilen {x.von}–{x.bis} ({len(x.rollen)}×, {rollen})")
            else:
                out.append(f"- Zeilen {x.von}–{x.bis} ({len(x.rollen)}×, "
                           f"{rollen}): {x.anfang}")
        return out

    koerper = abschnitte(bloecke, False)
    ausgelassen = 0
    rest = grenze - len("\n".join(zeilen + koerper))
    rest -= len("\n".join(punkte + entscheide)) + 200
    if rest < 0:
        koerper = abschnitte(bloecke, True)     # erst kürzen, dann auslassen
        rest = grenze - len("\n".join(zeilen + koerper))
        rest -= len("\n".join(punkte + entscheide)) + 200
    if rest < 0 and koerper:
        # Nur so viele Abschnitte zeigen, wie Platz haben — und sagen, wie
        # viele fehlen. Ein stiller Schnitt wäre die Fehlerart, die dieses
        # Verfahren gerade vermeiden soll.
        platz = max(1, len(koerper) + rest // 90)
        ausgelassen = len(koerper) - platz
        koerper = koerper[:platz] + [
            f"- … {ausgelassen} weitere Abschnitte bis Zeile {bloecke[-1].bis} "
            f"(nachlesen von={bloecke[platz].von})"]
    zeilen.extend(koerper)

    if verweise:
        # Der Verweis auf die ganz alten Zeilen darf nicht mit der alten
        # Zusammenfassung verschwinden — sonst führt keine Spur mehr dorthin.
        zeilen += ["", f"## Frühere Verdichtung ({len(verweise)} Verweise, wörtlich)"]
        zeilen.extend(verweise)

    if punkte:
        zeilen += ["", f"## Offene Punkte ({len(punkte)}, wörtlich)"]
        for p in punkte:
            zeilen.append(f"- [ ] {p}")
    if entscheide:
        zeilen += ["", f"## Entscheidungen ({len(entscheide)}, wörtlich)"]
        for e in entscheide:
            zeilen.append(f"- {e}")

    # Offene Punkte und Entscheidungen werden **nie** beschnitten — sie sind
    # der Grund, warum überhaupt verdichtet wird. Passt der Text dadurch
    # nicht in die Grenze, ist das kein Fehler, sondern eine Auskunft:
    # ``grenze`` gilt nur für die Abschnittsliste.
    return Bericht("\n".join(zeilen), bloecke[0].von, bloecke[-1].bis,
                   len(kopf), len(punkte), len(entscheide), ausgelassen,
                   schnitt)
