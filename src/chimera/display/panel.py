"""Fassade der Bildausgabe — das Treiberpaket ``chimera.displays`` nach außen.

Bis 11.10.2026 lag hier der Whisplay-Treiber samt Herstellerimport
(``whisplay.WhisplayBoard``). Der ist ins Treiberpaket umgezogen
(``src/chimera/displays/``, erkennbar über ``display.json`` je Modul); diese
Datei hält nur die vertraute Eintrittsstelle für ``app.py`` und die Tests
(DISPLAYS.md `docs/DISPLAYS.md`, Abschnitt „Aufbau"). Ein neues Panel ist seitdem ein Ordner unter
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
    """(typ, quelle) der eingestellten Anzeige, ohne zu raten.

    Die Wurzel ist **"/"**, es sei denn ein Test setzt ``CHIMERA_ROOT``.
    Vorher stand hier ``os.environ.get("CHIMERA_ROOT", "")`` — dann hing der
    Pfad am Arbeitsverzeichnis des Aufrufers. Am Gerät (12.11.2026) war das
    der Grund, warum das Fortschrittsgesicht des Installers nie zu sehen war:
    der Zeichner startete aus ``/tmp``, sah die Einstellung nicht und zeichnete
    in ein NullPanel.
    """
    env = os.environ.get("CHIMERA_ANZEIGE", "").strip()
    if env:
        return env, "CHIMERA_ANZEIGE"
    wurzel = os.environ.get("CHIMERA_ROOT") or "/"
    pfad = Path(wurzel) / "opt/chimera/state/anzeige"
    try:
        wert = pfad.read_text(encoding="utf-8").strip()
    except PermissionError:
        return None, f"{pfad} unlesbar (Dienstnutzer darf state/ nicht lesen)"
    except OSError:
        return None, f"{pfad} nicht lesbar"
    if wert:
        return wert, "state/anzeige"
    return None, f"{pfad} ist leer"


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
        # Eine belegte Leitung ist kein Defekt, sondern eine Warteschlange:
        # Beim Installerlauf hält der Fortschrittsbalken das Panel, während
        # Schritt 98-service den Dienst startet (am Pi 15.11.2026: „[Errno 16]
        # Leitung belegt auf /dev/gpiochip0: [27, 4]"). Vorher fiel der Dienst
        # dann dauerhaft auf NullPanel und das Panel blieb dunkel, obwohl der
        # Zeichner Sekunden später endete. Jetzt wird nachgeholt.
        if not isinstance(exc, OSError):
            # Kein Warten hilft, wenn das Modul selbst nicht lädt oder
            # kaputt ist — das ist ein Defekt, kein Belegtsein (Regel 8a).
            log.error("Anzeige %s aus %s nicht zu öffnen (%s) — Gesicht "
                      "läuft blind.", typ, quelle, exc)
            p = NullPanel(**{k: v for k, v in kw.items()
                             if k in ("width", "height", "convert", "fps")})
            p.hinweis = f"Anzeige {typ} ({quelle}) nicht zu öffnen: {exc}"
            return p
        try:
            prof = registry.profil(typ)
        except Exception as fehler_profil:              # noqa: BLE001
            # Ohne Profil gibt es nichts nachzuholen: Dann ist der Typ
            # unbekannt oder sein Modul kaputt — ein Fehler, kein Warten.
            log.error("Anzeige %s aus %s nicht zu öffnen (%s; kein Profil: %s) "
                      "— Gesicht läuft blind.", typ, quelle, exc, fehler_profil)
            p = NullPanel(**{k: v for k, v in kw.items()
                             if k in ("width", "height", "convert", "fps")})
            p.hinweis = f"Anzeige {typ} ({quelle}) nicht zu öffnen: {exc}"
            return p
        from ..displays.nachhol import NachholPanel
        log.warning("Anzeige %s aus %s nicht zu öffnen (%s) — wird nachgeholt.",
                    typ, quelle, exc)
        return NachholPanel(typ, quelle, exc, profil=prof)
