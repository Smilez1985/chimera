"""Ton eines Anzeigemoduls zur Laufzeit bereitstellen (Whisplay: WM8960/ES8389).

Warum zur Laufzeit und nicht in ``config.txt`` (smilez, 11.10.2026): Eine
SD-Karte wandert zwischen Boards. Mit ``dtparam=i2s=on`` sind GPIO18–21
PCM-Leitungen -- genau dort haengen beim GamePi13 das Backlight (19) und beim
E-Paper die Versorgung (18). Die Bootkonfiguration bleibt deshalb neutral
(spi, i2c_arm); erst wenn die Erkennung eine Whisplay festgestellt hat,
laedt der Boot-Abgleich als root die Overlays aus ``display.json`` (``ton``).

Gemessen chimera-pi 11.10.2026: ``dtparam i2s=on`` + ``dtoverlay
whisplay-soundcard`` -> rc 0, ALSA-Karte ``whisplaysound`` nach 2 s, Kernel
CONFIG_OF_OVERLAY=y/CONFIG_OF_CONFIGFS=y. Die Herstellerkonfiguration
(Mixer ``speaker``/``mic`` = 80, ``asound.conf`` mit dmix/dsnoop) stellt der
Installer her; hier wird nur geladen und nachgewiesen.

Nicht geladen wird, wenn die Karte schon da ist (Idempotenz) oder die
Overlay-Datei fehlt -- dann ist der Befund „Ton nicht eingerichtet", kein
Rateschluss.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .base import Profil


@dataclass
class TonBefund:
    karte: str
    da: bool
    geladen: list[str] = field(default_factory=list)   # was dieser Lauf lud
    fehler: list[str] = field(default_factory=list)
    hinweis: str = ""


def _root() -> str:
    return os.environ.get("CHIMERA_ROOT", "")


def alsa_karte_da(name: str) -> bool:
    try:
        return name.lower() in Path(_root() + "/proc/asound/cards").read_text(errors="ignore").lower()
    except OSError:
        return False


def overlay_datei(name: str) -> Path | None:
    for d in ("/boot/firmware/overlays", "/boot/overlays"):
        p = Path(_root() + f"{d}/{name}.dtbo")
        if p.is_file():
            return p
    return None


def overlays_geladen() -> list[str]:
    """Namen der zur Laufzeit geladenen Overlays (``dtoverlay -l``)."""
    if not shutil.which("dtoverlay"):
        return []
    try:
        r = subprocess.run(["dtoverlay", "-l"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    aus = []
    for z in r.stdout.splitlines():
        # "0:  dtparam  i2s=on" / "1:  whisplay-soundcard"
        teile = z.split(":", 1)
        if len(teile) == 2 and teile[0].strip().isdigit():
            aus.append(teile[1].strip())
    return aus


def bereitstellen(profil: Profil, *, warte_s: float = 5.0) -> TonBefund:
    """Overlays laden, bis die ALSA-Karte da ist. Nur als root sinnvoll."""
    ton = profil.ton or {}
    karte = str(ton.get("alsa_karte", ""))
    if not karte:
        return TonBefund("", False, hinweis="Modul hat keinen Ton")
    if alsa_karte_da(karte):
        return TonBefund(karte, True, hinweis="Karte bereits vorhanden")
    if _root():
        return TonBefund(karte, False, hinweis="CHIMERA_ROOT gesetzt -- es wird nichts geladen")
    if os.geteuid() != 0:
        return TonBefund(karte, False, fehler=["Overlays laden braucht root"])
    if not shutil.which("dtoverlay"):
        return TonBefund(karte, False, fehler=["dtoverlay fehlt (Paket raspi-utils-dt)"])

    b = TonBefund(karte, False)
    for name in ton.get("dtoverlay", []):
        if overlay_datei(str(name)) is None:
            b.fehler.append(f"Overlay-Datei {name}.dtbo fehlt -- Ton nicht eingerichtet (Installer Schritt 40)")
            return b
    schon = overlays_geladen()
    schritte = [["dtparam", p] for p in ton.get("dtparam", [])] + \
               [["dtoverlay", o] for o in ton.get("dtoverlay", [])]
    for befehl, arg in schritte:
        kennung = f"dtparam  {arg}" if befehl == "dtparam" else str(arg)
        if any(s.startswith(kennung) for s in schon):
            continue
        try:
            r = subprocess.run([befehl, str(arg)], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as exc:
            b.fehler.append(f"{befehl} {arg}: {exc}")
            return b
        if r.returncode != 0:
            b.fehler.append(f"{befehl} {arg}: rc {r.returncode} {r.stderr.strip()[:200]}")
            return b
        b.geladen.append(f"{befehl} {arg}")

    ende = time.monotonic() + warte_s
    while time.monotonic() < ende:
        if alsa_karte_da(karte):
            b.da = True
            break
        time.sleep(0.25)
    if not b.da:
        b.fehler.append(f"ALSA-Karte {karte} nach {warte_s:g} s nicht da")
    return b


def mixer_setzen(profil: Profil) -> list[str]:
    """Mixerwerte aus ``ton.mixer`` setzen (Herstellervorgabe 80/80). Liefert Fehler."""
    ton = profil.ton or {}
    karte, mixer = str(ton.get("alsa_karte", "")), ton.get("mixer", {})
    if not karte or not mixer:
        return []
    if not shutil.which("amixer"):
        return ["amixer fehlt (Paket alsa-utils)"]
    fehler = []
    for name, wert in mixer.items():
        try:
            r = subprocess.run(["amixer", "-q", "-c", karte, "cset", f"name={name}", str(wert)],
                               capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            fehler.append(f"amixer {name}: {exc}")
            continue
        if r.returncode != 0:
            fehler.append(f"amixer {name}={wert}: rc {r.returncode} {r.stderr.strip()[:120]}")
    return fehler
