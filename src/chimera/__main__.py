"""Chimera starten.

    python3 -m chimera              # Gespräch im Terminal
    python3 -m chimera --telegram   # zusätzlich die Telegram-Tür
    python3 -m chimera --pruefen    # nur zeigen, was da ist
    python3 -m chimera -f "Frage"   # eine Frage, eine Antwort

Beide Türen führen in dieselbe Sitzung (Regel 5d): Was per Telegram
besprochen wurde, weiß der Agent auch im Terminal.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading

from .agent.session import Channel
from .app import build

#: Das Terminal ist eine Tür wie jede andere.
TERMINAL = Channel("terminal", mode="text")

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="chimera", description="Ein Agent, der ein Gesicht macht.")
    ap.add_argument("-f", "--frage", help="Eine Frage stellen und aufhören")
    ap.add_argument("--telegram", action="store_true",
                    help="Die Telegram-Tür öffnen")
    ap.add_argument("--pruefen", action="store_true",
                    help="Nur zeigen, was vorhanden ist")
    ap.add_argument("--offline", action="store_true",
                    help="Nicht im Netz nach Anbietern suchen")
    ap.add_argument("-v", "--ausfuehrlich", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.ausfuehrlich else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s")

    chi = build(probe_network=not args.offline)
    # Ab hier ist ein Panel moeglicherweise offen. Jeder Ausstieg muss es
    # freigeben, auch der fruehe -- sonst bleibt der SPI-Bus belegt
    # (Regel 7b).
    try:
        return _lauf(chi, args)
    finally:
        chi.stop_display()


def _lauf(chi, args) -> int:
    for note in chi.notes:
        print(note)
    print()
    print(chi.status())
    print()

    if args.pruefen:
        return 0

    if not chi.registry.available():
        print("Kein Sprachmodell erreichbar — ohne eines gibt es kein "
              "Gespräch.\nZum Einrichten siehe oben.", file=sys.stderr)
        return 2

    # Das Gesicht zeichnen lassen, bevor gearbeitet wird: Wer davor steht,
    # soll sehen, dass das Gerät wach ist (Regel 7a/10h).
    if chi.start_display():
        print("Gesicht zeichnet.")
    elif chi.renderer is not None:
        chi.paint_once()
        print("Gesicht einmalig gezeichnet (Panel ohne Bildrate).")

    if args.frage:
        turn = chi.ask(args.frage, TERMINAL)
        print(turn.text)
        return 1 if turn.error else 0

    bot = None
    if args.telegram:
        try:
            bot = chi.telegram()
        except ValueError as exc:
            print(f"Telegram nicht eingerichtet: {exc}", file=sys.stderr)
            return 2
        threading.Thread(target=bot.run, daemon=True,
                         name="telegram").start()
        print("Telegram läuft mit. Dieselbe Sitzung, dieselbe Erinnerung.")
        print()

    try:
        return _gespraech(chi)
    finally:
        if bot is not None:
            bot.stop()

def _gespraech(chi) -> int:
    """Das Terminal als Tür. Leere Zeile oder Strg-D beendet."""
    print("Schreib etwas. Leere Zeile beendet.")
    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            return 0
        turn = chi.ask(prompt, TERMINAL)
        print(turn.text)
        print()

if __name__ == "__main__":
    sys.exit(main())
