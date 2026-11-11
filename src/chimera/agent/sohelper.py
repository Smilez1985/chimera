"""Der Weg des Agenten zum Ausführer (DESIGN, Regel „Wer prüft, führt aus").

Der Dienst führt **nichts** mehr selbst aus: `run_command`, `read_file`,
`write_file` und `list_dir` gehen als eine JSON-Zeile an den Socket von
`chimera-sohelper`, und was zurückkommt, ist das Ergebnis. Prüfung und
Ausführung liegen damit in einem Prozess, den der Agent nicht ändern kann.

**Kein Rückfall.** Ist der Ausführer nicht erreichbar, wird nichts
ausgeführt; das Modell bekommt den Grund genannt. Ein stiller Rückfall auf
den alten Weg würde die Trennung aufheben, sobald etwas klemmt — und genau
dann zählt sie.

Das Protokoll ist dasselbe wie beim Gateway: eine Zeile hin, eine zurück
(`gemein::zeile`), Obergrenze 4 MiB.
"""

from __future__ import annotations

import json
import os
import socket as _socket
from pathlib import Path

#: Wo der Socket im Betrieb liegt (systemd, Socket-Aktivierung).
STANDARD_SOCKET = "/run/chimera/sohelper.sock"

#: Obergrenze einer Antwortzeile — wie `gemein::zeile::MAX_BYTES`.
MAX_BYTES = 4 * 1024 * 1024


class AusfuehrerFehler(RuntimeError):
    """Der Ausführer ist nicht erreichbar oder antwortet unbrauchbar."""


class Ausfuehrer:
    """Ein Client für genau einen Socket. Verbindet je Frage neu."""

    def __init__(self, pfad: str | Path | None = None, *, frist: float | None = None):
        self.pfad = Path(
            pfad
            or os.environ.get("CHIMERA_SOHELPER_SOCKET")
            or STANDARD_SOCKET
        )
        # Die Frist muss über der des Ausführers liegen (Grenzen.timeout,
        # 120 s): sonst bricht der Client ab, während der Befehl noch läuft.
        self.frist = frist if frist is not None else 180.0

    def fragen(self, op: str, **felder) -> dict:
        """Eine Anfrage schicken und die Antwort deuten.

        Wirft :class:`AusfuehrerFehler`, wenn keine Verbindung zustande
        kommt oder die Antwort keine Zeile JSON ist.
        """
        anfrage = {"op": op, **felder}
        zeile = (json.dumps(anfrage, ensure_ascii=False) + "\n").encode()

        try:
            with _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM) as s:
                s.settimeout(self.frist)
                s.connect(str(self.pfad))
                s.sendall(zeile)
                roh = b""
                while not roh.endswith(b"\n"):
                    teil = s.recv(65536)
                    if not teil:
                        break
                    roh += teil
                    if len(roh) > MAX_BYTES:
                        raise AusfuehrerFehler("Antwort länger als 4 MiB")
        except OSError as exc:
            raise AusfuehrerFehler(str(exc)) from exc

        if not roh:
            raise AusfuehrerFehler("keine Antwort")
        try:
            antwort = json.loads(roh.decode("utf-8", "replace"))
        except ValueError as exc:
            raise AusfuehrerFehler(f"Antwort nicht lesbar: {exc}") from exc
        if not isinstance(antwort, dict):
            raise AusfuehrerFehler("Antwort ist kein Objekt")
        return antwort
