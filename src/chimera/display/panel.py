"""Fassade der Bildausgabe — das Treiberpaket ``chimera.displays`` nach außen.

Bis 11.10.2026 lag hier der Whisplay-Treiber samt Herstellerimport
(``whisplay.WhisplayBoard``). Der ist ins Treiberpaket umgezogen
(``src/chimera/displays/``, erkennbar über ``display.json`` je Modul); diese
Datei hält nur die vertraute Eintrittsstelle für ``app.py`` und die Tests
(DISPLAYS.md §5). Ein neues Panel ist seitdem ein Ordner unter
``displays/``, nicht eine Zeile hier.

Woher der Typ kommt (Regel 10g — nicht raten):

1. ``CHIMERA_ANZEIGE`` in der Umgebung — so überreicht später der
   systemd-Treiber ``chimera@<typ>.service`` die Erkennung aus
   ``chimera-hardware.service`` an den Dienst (Übergabe-Punkt 4).
2. ``state/anzeige`` — was der Installer (Schritt 40) festgehalten hat.
   Die Datei liegt unter ``state/`` (root:root 700): Der Dienstnutzer
   darf sie **nicht lesen**, das ist beabsichtigt (DESIGN, Pfadschema).
   Lesbar ist sie nur für root — etwa beim Installer-Nachweis.
3. nichts — Chimera läuft blind. Kein Auto-Probe: Der Dienst erkennt
   nicht nochmal (Regel 6e), er zeigt, was ihm gesagt wurde.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from ..displays import NullPanel, Panel, Profil, to_rgb565  # noqa: F401
from ..displays import registry

log = logging.getLogger(__name__)

__all__ = ["NullPanel", "Panel", "Profil", "to_rgb565", "open_panel"]


def _einstellung() -> tuple[str | None, str]:
    """(typ, quelle) der eingestellten Anzeige, ohne zu raten."""
    env = os.environ.get("CHIMERA_ANZEIGE", "").strip()
    if env:
        return env, "CHIMERA_ANZEIGE"
    pfad = Path(os.environ.get("CHIMERA_ROOT", "")) / "opt/chimera/state/anzeige"
    try:
        wert = pfad.read_text(encoding="utf-8").strip()
    except PermissionError:
        return None, "state/anzeige unlesbar (Dienstnutzer darf state/ nicht lesen)"
    except OSError:
        return None, "keine Einstellung"
    if wert:
        return wert, "state/anzeige"
    return None, "keine Einstellung"


def open_panel(kind: str = "auto", **kw) -> Panel:
    """Panel öffnen. ``auto`` folgt der Einstellung, ohne selbst zu prüfen."""
    typ, quelle = (kind, "Argument") if kind != "auto" else _einstellung()

    if typ is None:
        log.info("Keine Anzeige eingestellt (%s) — Gesicht läuft blind.", quelle)
        return NullPanel(**{k: v for k, v in kw.items()
                            if k in ("width", "height", "convert", "fps")})

    try:
        panel = registry.oeffne(typ, **kw)
        log.info("Anzeige %s (Quelle: %s).", typ, quelle)
        return panel
    except Exception as exc:
        if kind != "auto":
            raise
        # Bewusst kein stilles Weitermachen mit falscher Größe oder halb
        # belegten Leitungen: es gibt kein Bild, und der Grund ist ablesbar
        # (Regel 8a — der Unterschied zwischen „läuft blind" und „kaputt").
        log.error("Anzeige %s aus %s nicht zu öffnen (%s) — Gesicht läuft blind.",
                  typ, quelle, exc)
        p = NullPanel(**{k: v for k, v in kw.items()
                         if k in ("width", "height", "convert", "fps")})
        p.hinweis = f"Anzeige {typ} ({quelle}) nicht zu öffnen: {exc}"
        return p
