"""Der Zusammenbau — hier wird aus Bausteinen ein Gerät.

Bis hierher gab es Anbieter, Werkzeuge, Skills, Gedächtnis, ein Gesicht
und eine Sitzung, aber keine Stelle, die sie verbindet. Ein Modul, das
niemand aufruft, ist nicht fertig (Regel 10h) — das hier ist der Aufruf.

Bewusst **ohne Hardware**: Das Gesicht wird angeschlossen, wenn ein Panel
da ist, und weggelassen, wenn nicht. Dasselbe gilt für Anbieter (Regel 5h)
und Bedienschnittstellen. Was fehlt, wird gemeldet, nicht erzwungen — und
was läuft, läuft auf einem Entwicklungsrechner genauso wie auf dem Pi.

Aufruf:

    python3 -m chimera            # ein Gespräch im Terminal
    python3 -m chimera --telegram # zusätzlich die Telegram-Tür
    python3 -m chimera --pruefen  # nur zeigen, was da ist
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .agent.face import Face
from .agent.loop import Agent
from .agent.memory import Memory, install_tools as install_memory
from .agent.session import DIRECT, Channel, Session
from .agent.skills import SkillStore
from .agent.tools import Toolbox
from .provider.setup import autoconfigure

log = logging.getLogger(__name__)

#: Wie lange die LED einen Tastendruck quittiert (ms): drei Blitze des
#: Musters ``blink_schnell`` (240 ms je Blitz). 300 ms -- ein einziger,
#: kaum sichtbarer Aufheller -- war am Geraet zu kurz (smilez, 11.10.2026).
TASTE_QUITTUNG_MS = 720

#: Wo Chimera seine Sachen ablegt, wenn nichts anderes gesagt wird.
def _home() -> Path:
    return Path(os.environ.get("CHIMERA_HOME", Path.home() / ".chimera"))

#: So lange muss es still sein, bevor die Umgebung von selbst etwas tut.
#: Direkt nach einer Frage zu gähnen fällt auf -- es wirkt unhöflich, nicht
#: lebendig (smilez, 15.11.2026: „warum kommt yawn bei ‚Work auf Bing
#: prüfen'?").
RUHE_NACH_TURN_S = 300.0


@dataclass
class Chimera:
    """Das zusammengebaute Gerät."""

    home: Path
    session: Session
    registry: object
    toolbox: Toolbox
    memory: Memory | None = None
    skills: SkillStore | None = None
    # Die drei Teile der Anzeige, getrennt gehalten statt in einem
    # namenlosen ``object`` (Regel 7b): Das Gesicht setzt Ausdrücke, der
    # Renderer zeichnet sie, das Panel gibt sie aus. Wer sie zusammenwirft,
    # kann später nicht sagen, welches Stück fehlt.
    face: Face | None = None
    renderer: object = None
    panel: object = None
    # Statuszeile und LED: je EIN Exemplar, das der Renderer zeichnet und
    # das hier befuellt wird (Regel 7b/7c). ``None``, wenn es keinen
    # Renderer gibt.
    statusline: object = None
    led: object = None
    notes: list[str] = field(default_factory=list)
    _painter: threading.Thread | None = field(default=None, repr=False)
    # Tastengesten (5 Modi auf einer Taste): Die Erkennung ist eine reine
    # Zustandsmaschine (Regel 7d), der Taktgeber weckt sie zur richtigen
    # Zeit. Beides nur vorhanden, wenn das Panel eine Taste hat.
    gesten: object = None
    _gesten_takt: object = field(default=None, repr=False)
    _stop_paint: threading.Event = field(
        default_factory=threading.Event, repr=False)
    # Der Ton erinnert an offene Freigaben (DESIGN, "Kein Ablauf mehr — der
    # Ton erinnert"): seit 13.11. laufen Freigaben nicht mehr ab.
    erinnerung: object = None
    #: Eigens gehaltener Tonpfad, damit nicht jeder Aufruf neu rechnet.
    ton_pfad: object = None
    #: Selbsttaetige Aktionen (DESIGN, Regel „Ambiente"): ein Ausdruck, der
    #: gelegentlich von selbst kommt -- morgens Kaffee, abends ein Zug.
    #: Die Entscheidung ist eine reine Funktion (``agent/ambiente.py``), der
    #: Dienst ruft sie in seinem 30-s-Takt. Kein zweiter Faden.
    ambiente: object = None
    #: Mikrofon und Lautsprecher, hart geschaltet (smilez, 15.11.2026):
    #: aus, solange nichts sie braucht. Die Symbole oben lesen hier.
    audio: object = None

    # --- Auskunft ---------------------------------------------------------

    def status(self) -> str:
        """Was da ist und was nicht — in einem Absatz."""
        lines = [f"Ablage:     {self.home}"]

        available = [c.label for c in self.registry.available()]
        lines.append("Anbieter:   " + (", ".join(available) or "keiner erreichbar"))

        tasks = self.registry.tasks()
        if tasks:
            for name, group in sorted(tasks.items()):
                chain = " → ".join(str(t) for t in group.order())
                lines.append(f"  {name:<15} {chain}")

        lines.append("Werkzeuge:  " + ", ".join(self.toolbox.names()))
        if self.skills is not None:
            usable = self.skills.usable()
            lines.append(f"Skills:     {len(usable)} nutzbar "
                         f"von {len(self.skills.all())}")
        lines.append("Gesicht:    " + ("angeschlossen" if self.face
                                       else "keine Anzeige"))
        if self.panel is not None:
            art = (self.panel.profil.typ
                   if getattr(self.panel, "profil", None) is not None
                   else type(self.panel).__name__)
            lines.append(f"Anzeige:    {art} {self.panel.width}x{self.panel.height}, "
                         f"{self.panel.fps} Bilder/s"
                         + ("" if self.panel.bereit else " (blind)"))
        if self.renderer is not None:
            malt = self._painter is not None and self._painter.is_alive()
            lines.append("Renderer:   " + ("zeichnet" if malt
                                           else "bereit, zeichnet nicht"))
        return "\n".join(lines)

    # --- Türen ------------------------------------------------------------

    def ask(self, prompt: str, channel: Channel = DIRECT, *,
            anbieter: str = "", modell: str = "", denken: str = ""):
        """Durch die Standardtür fragen.

        ``anbieter``/``modell``/``denken`` sind die ausdrückliche Wahl der
        Tür (``wahl.json``) und gehen unverändert an die Sitzung: Eine
        ausdrückliche Wahl fällt dort nicht auf einen anderen Anbieter
        zurück.
        """
        # Jede Frage gilt als Anwesenheit: Solange jemand mit dem Gerät
        # spricht, soll es nicht von selbst gähnen (smilez, 15.11.2026:
        # *„warum kommt yawn bei ‚Work auf Bing prüfen'?"* — die Frage war
        # gerade beendet, die Umgebung sah „still" und würfelte).
        import time as _zeit
        self._letzte_aktivitaet = _zeit.monotonic()
        try:
            return self.session.ask(prompt, channel, anbieter=anbieter,
                                    modell=modell, denken=denken)
        finally:
            self._letzte_aktivitaet = _zeit.monotonic()

    def telegram(self):
        """Die Telegram-Tür öffnen — in *diese* Sitzung (Regel 5d)."""
        from .bot.telegram import from_env
        return from_env(self.session, on_state=self._on_state)

    def _led_melden(self, zustand: str, sekunden: float = 3.0) -> bool:
        """Einen Installer-Ausgang auf die LED legen.

        Gedacht fuer den Fall, in dem der Installer nichts zu tun hatte: Dann
        laeuft der Dienst weiter und haelt die Pins -- der Installer kann die
        LED nicht selbst setzen, er sagt es dem Dienst (Vorgabe smilez, 3.11.:
        "wenn kein Update gefunden wurde, muss es trotzdem gruen werden").

        Jeder Ausgang hat Farbe **und** Muster (``INSTALLER_ZUSTAENDE``); die
        Laufzeit ist die Anzeigedauer, danach faellt die LED auf den
        Grundzustand zurueck (Regel 7c: kurze Laufzeit statt Loeschen).
        """
        from .display.led import INSTALLER_ZUSTAENDE
        eintrag = INSTALLER_ZUSTAENDE.get(zustand)
        if self.led is None or eintrag is None:
            return False
        farbe, muster = eintrag
        import time as _t
        jetzt = int(_t.monotonic() * 1000)
        try:
            self.led.melden("installer", jetzt_ms=jetzt,
                            laufzeit_ms=int(max(0.5, sekunden) * 1000),
                            farbe=farbe, muster=muster)
        except (KeyError, ValueError):
            log.warning("LED-Zustand %r nicht meldbar", zustand)
            return False
        return True

    def _gesicht_setzen(self, name: str) -> bool:
        """Einen Ausdruck setzen, ohne die Sitzung zu bedienen.

        Gedacht fuer die Update-Anzeige des Installers: Er laeuft, waehrend
        die Dienste gleich angehalten werden, und braucht eine Anzeige, die
        den Zustand zeigt und stehen bleibt.
        """
        if self.face is None:
            return False
        try:
            self.face.set_by_name(name, hard=True)
            return True
        except KeyError:
            log.warning("Gesicht %r gibt es nicht", name)
            return False

    # --- Avatar-Einstellungen und Vorschau --------------------------------
    #
    # Eine Brücke für den Sitzungs-Socket (DESIGN, Regel
    # „Avatar-Einstellungen"): Der Browser fragt das Gateway, das Gateway
    # fragt hier. Der Dienst ist der einzige Schreiber der Ablage, weil er
    # den Renderer besitzt.

    def avatar(self):
        """Die Einstellungs-Ablage, so wie der Renderer sie liest."""
        if self.face is None:
            return None
        return getattr(self.face.state, "rt", None)

    def avatar_lesen(self) -> dict | None:
        abl = self.avatar()
        return abl.als_json() if abl is not None else None

    def avatar_setzen(self, feld: str, wert) -> tuple[bool, str]:
        abl = self.avatar()
        if abl is None:
            return (False, "keine Avatar-Ablage — Gesicht nicht aufgesetzt")
        return abl.setzen(feld, wert)

    def ausdruecke(self) -> list[dict]:
        """Was sich vorführen lässt: Name, eigene Dauer, Art.

        Die Art („Dauerzustand" / „eigene Dauer") rechnet dieselbe Funktion,
        die auch die Vorschau plant (``render.einstellungen.vorschau``) —
        eine Ankündigung, zwei Stellen wären zwei Wahrheiten.
        """
        if self.face is None:
            return []
        from .render.einstellungen import vorschau
        liste = []
        for eintrag in self.face.moods.entries():
            dauer, grund = vorschau(eintrag.mood)
            liste.append({
                "name": eintrag.name,
                "dauer_s": float(eintrag.mood.get("dauer_s") or 0),
                "dauerzustand": dauer is not None,
                "vorschau_s": 0.0 if dauer is None else float(dauer),
                "grund": grund,
            })
        return sorted(liste, key=lambda x: x["name"])

    def vorschau(self, name: str) -> dict:
        """Einen Ausdruck einmal vorführen (DESIGN, „Avatar-Einstellungen").

        Die Dauer kommt aus ``render.einstellungen.vorschau``: eigene Dauer →
        läuft einmal ganz (``dauer=None``), Dauerzustand → 30 s. Der Ablauf
        danach ist der des Renderers (``mood_bis``) — kein zweiter Timer.
        """
        if self.face is None:
            return {"ok": False, "fehler": "keine Anzeige angeschlossen"}
        from .render.einstellungen import vorschau as planen
        try:
            eintrag = self.face.moods.find(name)
        except Exception:                             # noqa: BLE001
            eintrag = None
        if eintrag is None:
            return {"ok": False, "fehler": f"unbekannter Ausdruck {name!r}"}
        dauer, grund = planen(eintrag.mood)
        try:
            gesetzt = self.face.set_by_name(eintrag.name, hard=True, dauer=dauer)
        except KeyError as exc:
            return {"ok": False, "fehler": f"unbekannter Ausdruck: {exc}"}
        return {"ok": True, "gesetzt": gesetzt.get("name", eintrag.name),
                "dauer_s": 0.0 if dauer is None else float(dauer),
                "grund": grund}

    def _status_kontext(self) -> dict:
        """Was die Kennwerte im Statusbereich zeigen: Modell und Anbieter.

        Gelesen wird der **letzte** Umlauf der Sitzung -- das ist die Wahrheit
        über das, was gerade geantwortet hat. Vor dem ersten Umlauf steht
        nichts, dann zeigt das Feld nur den Ausdruck (Regel „Anzeigefelder").
        """
        turns = getattr(self.session, "turns", None)
        letzter = (turns(limit=1) or [None])[0] if callable(turns) else None
        modell = getattr(letzter, "model", "") if letzter is not None else ""
        anbieter = getattr(letzter, "provider", "") if letzter is not None else ""
        # Obere Leiste (smilez, 15.11.2026): Temperatur mit Ampel und die
        # zwei Sprachsymbole. Die Temperatur wird **hier** gelesen und
        # zwischengespeichert, nicht je Bild: ein Dateizugriff pro Bild
        # waere auf dem Zero 2 W Messaufwand ohne Nutzen (30 s reichen).
        return {"modell": modell or "", "anbieter": anbieter or "",
                "temperatur": self._temperatur(),
                # Echte Schalter, keine Platzhalter (smilez, 15.11.2026):
                # aus, solange sie nichts braucht -- dann durchgestrichen.
                **self._audio_zustand()}

    def _audio_zustand(self) -> dict:
        """Die zwei Sprachsymbole — aus dem Schalter, nicht geraten."""
        schalter = self.audio
        if schalter is None:
            return {"mikrofon_an": False, "lautsprecher_an": False}
        try:
            return dict(schalter.zustand())
        except Exception:                      # noqa: BLE001
            log.exception("Audio-Zustand nicht lesbar")
            return {"mikrofon_an": False, "lautsprecher_an": False}

    # --- Audio-Einstellungen (Reiter „Einstellungen", 15.11.) -------------
    #
    # Dieselbe Brücke wie beim Avatar: Das Gateway fragt hier, geschaltet
    # wird hier (DESIGN, Regel „Einstellungen am Gerät"). Der Dienst besitzt
    # den Schalter — ein zweiter am Gateway wäre ein zweiter Zustand.

    def audio_lesen(self) -> dict | None:
        """Zustand und Lautstärken für die Seite (``None`` = kein Schalter)."""
        schalter = self.audio
        if schalter is None:
            return None
        return schalter.als_json()

    def audio_setzen(self, feld: str, wert, was: str = "") -> dict:
        """``mikrofon``/``lautsprecher`` schalten, ``lautstaerke`` einstellen.

        Der Wert wird hier geprüft, nicht im Gateway: Die Grenzen (0..100,
        zwei Regler) stehen dort, wo das Kommando läuft.
        """
        schalter = self.audio
        if schalter is None:
            return {"ok": False, "fehler": "kein Audio-Schalter — ohne Gerät "
                                           "gibt es nichts zu schalten"}
        if feld in ("mikrofon", "lautsprecher"):
            an = wert if isinstance(wert, bool) else None
            if an is None:
                return {"ok": False, "fehler": f"{feld}: erwartet an/aus "
                                               f"(Wahrheitswert), bekam {wert!r}"}
            gilt = schalter.mikrofon(an) if feld == "mikrofon" else schalter.lautsprecher(an)
            return {"ok": True, "meldung": f"{feld} {'an' if gilt else 'aus'}",
                    "audio": schalter.als_json()}
        if feld == "lautstaerke":
            regler = str(was or "").strip().lower()
            if regler not in ("mikrofon", "lautsprecher"):
                return {"ok": False, "fehler": "lautstaerke braucht was=mikrofon "
                                               "oder was=lautsprecher"}
            ok, meldung = schalter.lautstaerke_setzen(regler, wert)
            return {"ok": ok, "meldung": meldung,
                    "audio": schalter.als_json()}
        return {"ok": False, "fehler": f"unbekanntes Feld {feld!r} — erlaubt: "
                                       "mikrofon, lautsprecher, lautstaerke"}

    #: Zwischenspeicher der Temperatur (Ablage `_temp_*`).
    _temp_wert: float | None = None
    _temp_zeit: float = 0.0

    def _temperatur(self) -> float | None:
        """Die CPU-Temperatur in Grad Celsius, höchstens alle 30 s gelesen.

        Quelle ist die Thermosonde des SoC (`thermal_zone0`), nicht ein
        Schätzwert. Fehlt sie (Sandkasten, anderes Gerät), gibt es ``None``
        — dann zeigt die obere Leiste nur die Sprachsymbole, statt zu lügen.
        """
        import time as _uhr

        jetzt = _uhr.monotonic()
        if self._temp_wert is not None and jetzt - self._temp_zeit < 30.0:
            return self._temp_wert
        pfad = Path("/sys/class/thermal/thermal_zone0/temp")
        try:
            roh = pfad.read_text(encoding="ascii").strip()
            self._temp_wert = round(float(roh) / 1000.0, 1)
        except (OSError, ValueError):
            self._temp_wert = None
        self._temp_zeit = jetzt
        return self._temp_wert

    #: Wann zuletzt jemand etwas gefragt hat (monotone Uhr). Die Umgebung
    #: handelt erst, wenn das eine Weile her ist (RUHE_NACH_TURN_S).
    _letzte_aktivitaet: float = 0.0

    #: Letzter Grund, aus dem der Verbrauch nicht abgelegt werden konnte —
    #: ein Merker, damit die Warnung nicht bei jedem Turn wiederholt wird.
    _verbrauch_fehler: str = ""

    def _verbrauch_melden(self, turn) -> None:
        """Den Verbrauch eines Umlaufs an das Gateway geben.

        Der Tag kommt von hier (Ortszeit des Geraets), nicht vom Gateway:
        ein Server rechnet keine Zeitzone aus einer Ziffernfolge.
        """
        import time as _uhr
        from .provider import gateway as _gw
        tag = _uhr.strftime("%Y-%m-%d", _uhr.localtime())
        anfrage = {
            "op": "verbrauch_notieren", "tag": tag,
            "anbieter": turn.provider or "", "modell": turn.model or "",
        }
        for feld in ("eingabe", "ausgabe", "cache_neu", "cache_treffer", "denken"):
            wert = (turn.verbrauch or {}).get(feld)
            if isinstance(wert, int) and not isinstance(wert, bool):
                anfrage[feld] = wert
        antwort = _gw.anfragen(anfrage, warten=3.0)
        # Ein gesendetes Op ist kein abgelegter Wert (Lehre vom Pi,
        # 15.11.2026: `state/verbrauch` war nicht schreibbar, das Gateway
        # sagte es auch -- nur gehoert hatte es niemand).
        if antwort.get("ok") is not True:
            grund = str((antwort.get("fehler") or {}).get("text")
                        or antwort.get("fehler") or "ohne Grund")
            if grund != self._verbrauch_fehler:
                self._verbrauch_fehler = grund
                log.warning("Verbrauch wird nicht abgelegt: %s", grund)
        else:
            self._verbrauch_fehler = ""

    def _on_state(self, what: str) -> None:
        """Den Zustand ans Gesicht melden.

        Kein ``getattr``-Raten und kein weites ``except``: ``face`` ist
        entweder ein ``Face`` — dann hat es ``show_state`` — oder ``None``
        (Regel 7b). Schlägt der Aufruf trotzdem fehl, ist das ein Fehler
        im Gesicht und gehört ins Protokoll, nicht in ein Schweigen
        (Regel 8a).
        """
        if self.face is not None:
            try:
                self.face.show_state(what)
            except Exception:                         # noqa: BLE001
                log.exception("Zustand %r konnte nicht angezeigt werden", what)
        try:
            zustand_melden(what, statusline=self.statusline, led=self.led)
        except Exception:                             # noqa: BLE001
            log.exception("Zustand %r: Statuszeile/LED nicht gemeldet", what)

    def anbieter_melden(self, jetzt_ms: int | None = None) -> bool:
        """Anbieterausfall an die Statuszeile geben (Quelle ``anbieter_weg``).

        Gerufen vom Dienst in SEINEM Faden, nicht im Renderertakt: Die
        Pruefung kann ins Netz gehen (Ollama), und ein Netzzeitlimit im
        Renderer liesse das Gesicht stehen. Gibt zurueck, ob ein Anbieter
        erreichbar ist.

        Nur die Zeile, nicht die LED: Ein Dauerblinken bei einem Geraet, das
        bewusst ohne Sprachmodell laeuft, ist eine eigene Entscheidung
        (ROADMAP), keine Nebenwirkung dieser Meldung.
        """
        import time as _t
        jetzt = int(_t.monotonic() * 1000) if jetzt_ms is None else jetzt_ms
        try:
            da = bool(self.registry.available())
        except Exception:                             # noqa: BLE001
            log.exception("Anbieterpruefung fehlgeschlagen")
            da = False
        if self.statusline is not None:
            if da:
                self.statusline.zuruecknehmen("anbieter_weg")
            else:
                self.statusline.melden("anbieter_weg", "kein Sprachmodell", jetzt_ms=jetzt)
        return da

    def _on_taste(self, gedrueckt: bool) -> None:
        """Flanke der Seitentaste -- hier wird daraus eine Geste.

        Die Taste kennt nur unten/oben; was gemeint ist (kurz, lang, halten,
        doppelt, dreifach), entscheidet :class:`chimera.display.gesten.Gesten`
        aus dem zeitlichen Verlauf (Regel 7d). Bedeutung der Gesten: DESIGN
        `docs/DESIGN.md`, Abschnitt „Umgebungshören im Ruhezustand" -- ein Druck beendet das Umgebungshoeren und beginnt das
        Gespraech; Push-to-Talk haengt an ``halten``/``halten_ende`` und
        wartet auf den Audio-Prozess (ROADMAP Phase 5). Bis dahin: sichtbar
        quittieren und protokollieren, nicht schweigen.
        """
        import time as _t
        # Sofort quittieren: Ein Druck, der 0,8 s lang nichts zeigt (so
        # lange braucht die Entscheidung "kurz"), fuehlt sich kaputt an.
        # Die Geste kommt danach -- sie sagt, WAS gemeint war.
        if gedrueckt and self.led is not None:
            # Muster "quittung" (dunkel -> weiss -> dunkel): Ein fester
            # Weisston hob sich am Geraet nicht vom blauen Grundglow ab --
            # smilez sah nur "heller, bleibt blau" (11.10.2026).
            self.led.melden("taste", jetzt_ms=int(_t.monotonic() * 1000),
                            laufzeit_ms=TASTE_QUITTUNG_MS)
        if self.gesten is None:
            return
        for geste in self.gesten.taste(bool(gedrueckt), _t.monotonic()):
            self._geste(geste)
        if self._gesten_takt is not None:
            self._gesten_takt.anstoss()

    def _geste(self, art: str) -> None:
        """Eine erkannte Geste melden -- und spaeter ausfuehren.

        Die Bedeutung haengt an DESIGN `docs/DESIGN.md`, Abschnitt „Umgebungshören im Ruhezustand": kurz beendet das
        Umgebungshoeren, lang beginnt das Gespraech, halten ist
        Push-to-Talk (``halten_ende`` beendet es), doppelt und dreifach
        sind fuer Abbrechen/Zurueck vorgesehen. Bis der Audio-Prozess
        steht (ROADMAP Phase 5), wird protokolliert, nicht geschwiegen.
        """
        log.info("Taste: Geste \u201e%s\u201c", art)

    # --- Anzeige ----------------------------------------------------------

    def start_display(self) -> bool:
        """Den Renderer als Faden starten (Regel 7a).

        Ein Faden, kein Prozess: Der Renderer zeichnet mit Pillow und
        wandelt mit numpy um (das die globale Sperre freigibt) — gemessen
        2,5 ms von 66,7 ms Budget. Ein eigener Prozess würde den
        Bildspeicher über eine Prozessgrenze schieben und auf 512 MB einen
        zweiten Python-Heap kosten, ohne etwas zu gewinnen. Anders als
        Audio (Regel 5g), das wirklich rechnet.

        Gibt zurück, ob gezeichnet wird. Bei einem Panel ohne Bildrate
        (E-Ink) wird kein Faden gestartet — dort löst der Zustandswechsel
        das Bild aus, nicht die Uhr.
        """
        if self.renderer is None:
            return False
        if self._painter is not None and self._painter.is_alive():
            return True
        if not getattr(self.renderer, "TARGET_FPS", 0):
            log.info("Panel ohne Bildrate — es wird auf Anstoss gezeichnet.")
            return False

        self._stop_paint.clear()
        self._painter = threading.Thread(
            target=self.renderer.run, args=(self._stop_paint,),
            name="renderer", daemon=True)
        self._painter.start()
        return True

    def stop_display(self, timeout: float = 2.0) -> None:
        """Den Renderer anhalten und das Panel freigeben."""
        if self._gesten_takt is not None:
            self._gesten_takt.stop()
            self._gesten_takt = None
        self._stop_paint.set()
        if self._painter is not None:
            self._painter.join(timeout)
            if self._painter.is_alive():
                log.warning("Renderer haelt nicht an — Faden bleibt liegen.")
            self._painter = None
        if self.panel is not None:
            try:
                self.panel.close()
            except Exception as exc:                  # noqa: BLE001
                log.debug("Panel schliessen ging nicht: %s", exc)

    def ambient_takt(self, jetzt: float | None = None) -> str | None:
        """Gelegentlich von selbst etwas zeigen (DESIGN, Regel „Ambiente").

        Laeuft im 30-s-Takt des Dienstes. Faellig ist etwas nur, wenn der
        Agent **wirklich** nichts tut: kein laufender Auftrag, kein laufender
        endlicher Ausdruck. Das ist dieselbe Bedingung wie beim ehrlichen
        Zustand (Regel „Sprechgesicht" Punkt 10) -- das Display soll nicht
        rauchen, waehrend es arbeitet.

        Rueckgabe: der gezeigte Ausdruck oder ``None``.
        """
        import time as _zeit

        from .agent.ambiente import Ambiente

        if self.face is None:
            return None
        if self.session is not None and getattr(self.session, "busy", False):
            return None
        # Erst wenn eine Weile niemand etwas wollte. Ein Gerät, das mitten im
        # Gespräch gähnt, ist nicht lebendig, sondern unhöflich.
        jetzt = _zeit.monotonic()
        if self._letzte_aktivitaet and jetzt - self._letzte_aktivitaet < RUHE_NACH_TURN_S:
            return None
        if self.ambiente is None:
            self.ambiente = Ambiente()
        wahl = self.ambiente.tick(
            stunde=_zeit.localtime().tm_hour,
            frei=True,
            haelt=bool(getattr(self.face, "laeuft", False)),
            vorhanden=set(self.face.moods.names()),
        )
        if wahl is None:
            return None
        try:
            self.face.set_by_name(wahl)
        except KeyError as exc:            # Bibliothek geaendert: kein Absturz
            log.debug("Ambiente-Ausdruck %r nicht setzbar: %s", wahl, exc)
            return None
        return wahl

    def erinnere(self, jetzt: int | None = None) -> list[str]:
        """An offene Freigaben erinnern: fragen, entscheiden, einen Ton.

        Fragt **das Gateway** (``op: freigabe_lesen``) -- die Datei gehoert
        dem Gateway, der Dienst liest sie nicht selbst (Regel 10g). Ist das
        Gateway nicht erreichbar, wird nicht erinnert und **nicht** geworfen:
        Der Dienst soll weiterlaufen.

        Rueckgabe: die Werkzeuge, die gerade erinnert haben (leer = nichts).
        """
        import time as _zeit

        from .provider import gateway
        from .provider.base import LLMError

        if self.erinnerung is None:
            return []
        try:
            a = gateway.anfragen({"op": "freigabe_lesen"}, warten=5.0)
        except LLMError as exc:
            log.debug("Freigaben nicht lesbar, keine Erinnerung: %s", exc)
            return []
        if a.get("ok") is not True:
            log.debug("Freigaben nicht lesbar: %s", a.get("fehler"))
            return []
        jetzt = int(_zeit.time()) if jetzt is None else int(jetzt)
        faellig = self.erinnerung.tick(a.get("freigaben") or {}, jetzt)
        if faellig:
            from . import freigabe_erinnerung as fe
            if self.ton_pfad is None:
                self.ton_pfad = Path(tempfile.gettempdir()) / "chimera-erinnerung.wav"
                if not Path(self.ton_pfad).is_file():
                    fe.ton_bauen(Path(self.ton_pfad))
            fe.klingeln(faellig, pfad=Path(self.ton_pfad))
        return faellig

    def paint_once(self) -> None:
        """Ein einzelnes Bild ausgeben.

        Für Panels ohne Bildrate der normale Weg, für die anderen eine
        Möglichkeit, ohne laufenden Faden etwas zu sehen.
        """
        if self.renderer is not None:
            self.renderer.show()

def build(*, probe_network: bool = True, home: Path | None = None,
          with_face: bool = True) -> Chimera:
    """Alles zusammensetzen, was vorhanden ist.

    Scheitert nicht an fehlenden Teilen: Ohne Anbieter bleibt das Gerät
    benutzbar (Gesicht, Mischen, Variieren), ohne Panel läuft es blind,
    ohne Skills eben ohne Skills. Was fehlt, steht in ``notes``.
    """
    root = Path(home) if home else _home()
    root.mkdir(parents=True, exist_ok=True)

    registry, notes = autoconfigure(probe_network=probe_network)

    face, renderer, panel = _try_face(notes, root) if with_face \
        else (None, None, None)
    statusline, led = _try_zeile_und_led(renderer, panel, notes)

    work = root / "arbeit"
    work.mkdir(exist_ok=True)
    # Die Ablage vor der Toolbox: ``nachlesen`` braucht sie (DESIGN 8d).
    from .ablage import Ablage, Verlauf
    ablage = Ablage(root / "sitzungen-ablage")
    toolbox = Toolbox(work, face=face, ablage=ablage)

    memory = Memory(root / "gedaechtnis")
    install_memory(toolbox, memory)

    skills = _try_skills(root, notes)

    agent = Agent(registry, toolbox, skills=skills, memory=memory)
    # Verlauf auf der Platte (Regel 8d): übersteht Neustarts.
    agent.history = Verlauf(ablage, ablage.laden())
    session = Session(agent, ablage=ablage)

    from .freigabe_erinnerung import Erinnerung
    chi = Chimera(home=root, session=session, registry=registry,
                  toolbox=toolbox, memory=memory, skills=skills,
                  face=face, renderer=renderer, panel=panel,
                  statusline=statusline, led=led, notes=notes,
                  erinnerung=Erinnerung())
    # Mikrofon und Lautsprecher (smilez, 15.11.2026): Es gibt am HAT keinen
    # Schalter, nur Lautstaerken -- „aus" heisst 0 %, „an" der gemerkte Wert.
    # Angelegt wird er hier, ausgeschaltet beim Dienststart (`alles_aus`).
    try:
        from .audio_schalter import AudioSchalter
        # „Set and forget": Die Lautstärke liegt in `config/audio.json` und
        # überlebt Neustarts; geschaltet wird danach nur noch an/aus.
        chi.audio = AudioSchalter(ablage=root / "config" / "audio.json")
    except Exception as exc:                      # noqa: BLE001
        notes.append(f"Audio-Schalter: nicht aufsetzbar ({exc})")
    # Erst jetzt verdrahten: Der Agent meldet seinen Zustand ans Gesicht.
    agent.on_state = chi._on_state
    # Die Kennwerte des Statusbereichs (Modell, Anbieter) kommen aus der
    # laufenden Sitzung -- nicht aus einer zweiten Quelle, die altert.
    if chi.statusline is not None:
        chi.statusline.kontext_quelle = chi._status_kontext
    # Und die Anzeige ist ueber den Sitzungs-Socket erreichbar (Operation
    # "gesicht"): Damit setzt der Installer das Update-Gesicht, bevor er die
    # Dienste anhaelt.
    session.gesicht_setzen = chi._gesicht_setzen
    # Und die Avatar-Einstellungen samt Vorschau (Operationen
    # `avatar_lesen`, `avatar_setzen`, `ausdruecke`, `vorschau`): Der
    # Browser kommt nur über das Gateway herein, geschrieben wird hier
    # (DESIGN, Regel „Avatar-Einstellungen").
    session.avatar_bruecke = chi
    # Und die Audio-Einstellungen (Operationen `audio_lesen`, `audio_setzen`):
    # Der Schalter gehoert dem Dienst, das Gateway reicht nur durch.
    session.audio_bruecke = chi
    # Und der Verbrauch jedes Umlaufs geht ans Gateway, das die Ablage
    # fuehrt (state/ gehoert chimera-tor, DESIGN „Verbrauch" 15.11.2026).
    session.verbrauch_melden = chi._verbrauch_melden
    # Und die LED (Operation "led"): Damit meldet der Installer auch dann
    # seinen Ausgang, wenn er den Dienst gar nicht angehalten hat.
    session.led_melden = chi._led_melden
    # Die Taste, wenn das Panel eine hat (Whisplay). Ein Panel ohne Taste
    # hat die Methode nicht -- dann gibt es nichts zu verdrahten.
    if panel is not None and hasattr(panel, "bei_taste"):
        from .display.gesten import Gesten, GestenTakt
        chi.gesten = Gesten()
        panel.bei_taste(chi._on_taste)
        # Der Taktgeber entscheidet faellige Gesten (kurz erst am Ende des
        # Klickfensters, halten waehrend des Drueckens) -- ein Faden, der
        # auf die Frist wartet und sonst schlaeft.
        chi._gesten_takt = GestenTakt(chi.gesten, chi._geste).start()
        notes.append("Taste: verdrahtet (kurz/lang/halten/doppelt/dreifach)")
    return chi

#: Die mitgelieferte Mood-Bibliothek.
BUILTIN_MOODS = Path(__file__).resolve().parent.parent.parent / "data" / "moods-builtin.json"

def _try_face(notes: list[str], root) -> tuple[object, object, object]:
    """Gesicht, Renderer und Panel aufsetzen — und alle drei behalten.

    Die drei gehören zusammen und werden hier verdrahtet (Regel 7b): Das
    Panel wird geöffnet und **weitergegeben**, nicht nur befragt; der
    Renderer bekommt es übergeben und baut sich keines selbst; das Gesicht
    schreibt in denselben Zustand, den der Renderer zeichnet.

    Vorher endete das Panel in einer lokalen Variablen und fiel aus dem
    Gültigkeitsbereich — auf dem Gerät hätte das den SPI-Bus belegt, ohne
    ein Bild auszugeben.

    Rückgabe ``(face, renderer, panel)``; jedes davon kann ``None`` sein,
    wenn der Baustein fehlt. Ein Gerät ohne Anzeige macht trotzdem ein
    Gesicht — es sieht nur keiner (``NullPanel``).
    """
    try:
        from .agent.face import Face
        from .display.panel import open_panel
        from .mood.ablage import lade as mood_laden
        from .render.avatar import NoisyRenderer, State
    except ImportError as exc:
        notes.append(f"Gesicht: Baustein fehlt ({exc.name})")
        return None, None, None

    # Zwei Quellen, eine Reihenfolge (DESIGN 3.3b): erst die mitgelieferte
    # Bibliothek, dann die eigenen Ausdrücke des Agenten daneben.
    eigene_moods = Path(root) / "moods.json"
    try:
        moods, hinweise = mood_laden(BUILTIN_MOODS, eigene_moods)
        notes.extend(hinweise)
    except Exception as exc:                          # noqa: BLE001
        notes.append(f"Gesicht: Bibliothek nicht ladbar ({exc})")
        return None, None, None

    panel = open_panel()
    if not panel.bereit:
        # Der Unterschied zwischen „keine eingestellt", „ließ sich nicht
        # öffnen" und „Leitung war belegt, wird nachgeholt" muss in der
        # Statuszeile stehen, sonst sieht ein Defekt wie Absicht aus
        # (Regel 8a).
        notes.append(f"Anzeige: blind — {panel.hinweis}" if panel.hinweis
                     else "Anzeige: keine eingestellt — Gesicht läuft blind")
    else:
        typ = panel.profil.typ if panel.profil is not None else type(panel).__name__
        notes.append(f"Anzeige: {typ} {panel.width}x{panel.height}, "
                     f"{panel.fps} Bilder/s")

    # Ein Zustand für beide: Das Gesicht setzt Ausdrücke, der Renderer
    # liest sie. Zwei Zustände wären zwei Gesichter, von denen das falsche
    # gezeichnet wird.
    state = State()
    # Avatar-Einstellungen (DESIGN, Regel „Avatar-Einstellungen"): Frisur,
    # Haarfarbe und Kontrast liegen in `einstellungen/avatar.json` und
    # erreichen den Renderer über `state.rt` — dieselbe Naht, die aus dem
    # Noisy-Port übrig war und bisher leer blieb. Fehlt die Ablage, gilt die
    # Vorgabe; das wird gesagt, nicht verschwiegen.
    try:
        from .render.einstellungen import Avatar
        avatar = Avatar(Path(root) / "einstellungen" / "avatar.json")
        state.rt = avatar
        for hinweis in avatar.als_json()["hinweise"]:
            notes.append(f"Avatar: {hinweis}")
    except Exception as exc:                          # noqa: BLE001
        notes.append(f"Avatar-Einstellungen: nicht lesbar ({exc}) — Vorgaben")
    try:
        from .display.spiegel import Spiegel
        renderer = NoisyRenderer(state, panel, spiegel=Spiegel())
    except Exception as exc:                          # noqa: BLE001
        notes.append(f"Renderer: nicht aufsetzbar ({exc}) — Gesicht "
                     "ohne Bild")
        return Face(moods, state, ablage=eigene_moods), None, panel

    return Face(moods, state, ablage=eigene_moods), renderer, panel

#: Agentenzustand -> (Text der Statuszeile, LED-Quelle oder None). Eine
#: Tabelle fuer beide Darstellungen, damit Zeile und LED nicht
#: auseinanderlaufen (Regel 7c). Zustaende ohne Eintrag werden nicht
#: gemeldet -- dann gilt der Grundzustand.
ZUSTAENDE: dict[str, tuple[str, str | None]] = {
    "hoert":    ("hoert zu", "hoert"),
    "denkt":    ("denkt nach", "agentenstatus"),
    "arbeitet": ("arbeitet", "agentenstatus"),
    "spricht":  ("spricht", "spricht"),
    "verwirrt": ("verwirrt", "agentenstatus"),
    "fehler":   ("Fehler", "agentenstatus"),
}


def zustand_melden(what: str, *, statusline=None, led=None, jetzt_ms: int | None = None) -> None:
    """Einen Agentenzustand an Statuszeile und LED geben.

    ``wartet`` nimmt beide Meldungen zurueck (Grundzustand). Laufzeit: 30 s
    als Netz -- ein Zustand, den niemand zuruecknimmt, verfaellt, statt
    fuer immer zu leuchten (Regel 7c, "kurze Laufzeit statt Loeschen").
    """
    import time as _t
    jetzt = int(_t.monotonic() * 1000) if jetzt_ms is None else jetzt_ms
    if what == "wartet":
        if statusline is not None:
            statusline.zuruecknehmen("agentenstatus")
        if led is not None:
            for q in ("hoert", "agentenstatus", "spricht"):
                led.zuruecknehmen(q)
        return
    eintrag = ZUSTAENDE.get(what)
    if eintrag is None:
        return
    text, led_quelle = eintrag
    if statusline is not None:
        statusline.melden("agentenstatus", text, jetzt_ms=jetzt, laufzeit_ms=30_000)
    if led is not None and led_quelle is not None:
        # Ein neuer Zustand verdraengt die anderen Agenten-Zustaende der LED;
        # sonst bliebe "hoert" stehen, waehrend er laengst spricht.
        for q in ("hoert", "agentenstatus", "spricht"):
            if q != led_quelle:
                led.zuruecknehmen(q)
        led.melden(led_quelle, jetzt_ms=jetzt, laufzeit_ms=30_000)


def _try_zeile_und_led(renderer, panel, notes: list[str]):
    """Statuszeile und LED anlegen und dem Renderer GEBEN (Regel 7b).

    Vorher baute niemand eine Statuszeile: ``renderer.statusline`` blieb
    ``None``, die 40 Zeilen unten blieben leer -- gebaut, getestet, nie
    angeschlossen. Die Zeile braucht Platz unter dem Gesicht (Hoehe >
    Breite); auf einem quadratischen Panel gibt es keine.
    """
    if renderer is None:
        return None, None
    statusline = None
    try:
        from .display.statusline import StatusLine
        breite = int(getattr(panel, "width", 0) or 0)
        hoehe = int(getattr(panel, "height", 0) or 0)
        if hoehe - breite >= 30:
            # Grundinhalt = Name des Ausdrucks (DESIGN `docs/DESIGN.md`, Abschnitt „Renderer"). Gelesen aus dem
            # Zustand, den der Renderer zeichnet -- keine zweite Quelle.
            zustand = getattr(renderer, "state", None)
            statusline = StatusLine(
                hoehe=hoehe - breite,
                grundtext=lambda: getattr(zustand, "mood_name", "") or "")
            renderer.statusline = statusline
    except Exception as exc:                          # noqa: BLE001
        notes.append(f"Statuszeile: nicht aufsetzbar ({exc})")
    led = None
    try:
        from .display.led import LedVerwalter
        led = LedVerwalter()
        renderer.led = led
    except Exception as exc:                          # noqa: BLE001
        notes.append(f"LED: nicht aufsetzbar ({exc})")
    return statusline, led


def _try_skills(root: Path, notes: list[str]) -> SkillStore | None:
    """Skills aus der Ablage und aus dem Repo lesen."""
    dirs = [root / "skills"]
    mitgeliefert = Path(__file__).resolve().parent.parent.parent / "skills"
    if mitgeliefert.is_dir():
        dirs.append(mitgeliefert)
    try:
        store = SkillStore(*dirs)
    except Exception as exc:                          # noqa: BLE001
        notes.append(f"Skills: nicht lesbar ({exc})")
        return None
    if not store.all():
        notes.append(f"Skills: keine gefunden (erwartet in {dirs[0]})")
    return store
