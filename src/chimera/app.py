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

#: Wo Chimera seine Sachen ablegt, wenn nichts anderes gesagt wird.
def _home() -> Path:
    return Path(os.environ.get("CHIMERA_HOME", Path.home() / ".chimera"))

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
    notes: list[str] = field(default_factory=list)
    _painter: threading.Thread | None = field(default=None, repr=False)
    _stop_paint: threading.Event = field(
        default_factory=threading.Event, repr=False)

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
            lines.append(f"Anzeige:    {type(self.panel).__name__} "
                         f"{self.panel.width}x{self.panel.height}, "
                         f"{self.panel.fps} Bilder/s")
        if self.renderer is not None:
            malt = self._painter is not None and self._painter.is_alive()
            lines.append("Renderer:   " + ("zeichnet" if malt
                                           else "bereit, zeichnet nicht"))
        return "\n".join(lines)

    # --- Türen ------------------------------------------------------------

    def ask(self, prompt: str, channel: Channel = DIRECT):
        """Durch die Standardtür fragen."""
        return self.session.ask(prompt, channel)

    def telegram(self):
        """Die Telegram-Tür öffnen — in *diese* Sitzung (Regel 5d)."""
        from .bot.telegram import from_env
        return from_env(self.session, on_state=self._on_state)

    def _on_state(self, what: str) -> None:
        """Den Zustand ans Gesicht melden.

        Kein ``getattr``-Raten und kein weites ``except``: ``face`` ist
        entweder ein ``Face`` — dann hat es ``show_state`` — oder ``None``
        (Regel 7b). Schlägt der Aufruf trotzdem fehl, ist das ein Fehler
        im Gesicht und gehört ins Protokoll, nicht in ein Schweigen
        (Regel 8a).
        """
        if self.face is None:
            return
        try:
            self.face.show_state(what)
        except Exception:                             # noqa: BLE001
            log.exception("Zustand %r konnte nicht angezeigt werden", what)

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

    face, renderer, panel = _try_face(notes) if with_face \
        else (None, None, None)

    work = root / "arbeit"
    work.mkdir(exist_ok=True)
    toolbox = Toolbox(work, face=face)

    memory = Memory(root / "gedaechtnis")
    install_memory(toolbox, memory)

    skills = _try_skills(root, notes)

    agent = Agent(registry, toolbox, skills=skills, memory=memory)
    session = Session(agent)

    chi = Chimera(home=root, session=session, registry=registry,
                  toolbox=toolbox, memory=memory, skills=skills,
                  face=face, renderer=renderer, panel=panel, notes=notes)
    # Erst jetzt verdrahten: Der Agent meldet seinen Zustand ans Gesicht.
    agent.on_state = chi._on_state
    return chi

#: Die mitgelieferte Mood-Bibliothek.
BUILTIN_MOODS = Path(__file__).resolve().parent.parent.parent / "data" / "moods-builtin.json"

def _try_face(notes: list[str]) -> tuple[object, object, object]:
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
        from .display.panel import NullPanel, open_panel
        from .mood.registry import Registry as MoodRegistry
        from .render.avatar import NoisyRenderer, State
    except ImportError as exc:
        notes.append(f"Gesicht: Baustein fehlt ({exc.name})")
        return None, None, None

    try:
        moods = MoodRegistry.load(BUILTIN_MOODS)
    except Exception as exc:                          # noqa: BLE001
        notes.append(f"Gesicht: Bibliothek nicht ladbar ({exc})")
        return None, None, None

    panel = open_panel()
    notes.append("Anzeige: keine gefunden — Gesicht läuft blind"
                 if isinstance(panel, NullPanel) else
                 f"Anzeige: {type(panel).__name__} "
                 f"{panel.width}x{panel.height}, {panel.fps} Bilder/s")

    # Ein Zustand für beide: Das Gesicht setzt Ausdrücke, der Renderer
    # liest sie. Zwei Zustände wären zwei Gesichter, von denen das falsche
    # gezeichnet wird.
    state = State()
    try:
        renderer = NoisyRenderer(state, panel)
    except Exception as exc:                          # noqa: BLE001
        notes.append(f"Renderer: nicht aufsetzbar ({exc}) — Gesicht "
                     "ohne Bild")
        return Face(moods, state), None, panel

    return Face(moods, state), renderer, panel

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
