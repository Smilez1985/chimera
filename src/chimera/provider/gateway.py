"""Anbieter hinter dem Gateway (DESIGN Regel 5n).

Der Dienst hat kein Netz und keine Schluessel. Er schickt eine JSON-Zeile
an ``/run/chimera/tor.sock`` und bekommt eine zurueck (Protokoll:
``rust/crates/gemein``, ``zeile``). Das Gateway ruft den Anbieter an.

Dieser Connector heisst weiter ``ollama``: Ketten, Anzeige und Zuordnung
aendern sich nicht, nur der Weg. Antwortet das Gateway nicht, ist der
Anbieter *nicht verfuegbar* -- die Registry faellt auf den naechsten
zurueck (Regel 5h). Ein stiller Umweg ueber eine eigene Verbindung
findet hier nicht statt.
"""

from __future__ import annotations

import json
import os
import socket
import time

from .base import Access, Connector, CostClass, LLMError, Unavailable

SOCKET = "/run/chimera/tor.sock"

#: Eine Antwortzeile darf so gross sein wie die Obergrenze im Gateway.
MAX_ZEILE = 4 * 1024 * 1024
#: Das Gateway haelt den Aufruf bis zu 300 s (kaltes grosses Modell);
#: der Dienst wartet etwas laenger, damit der Fehler vom Gateway kommt.
WARTEN_CHAT = 310.0
WARTEN_KURZ = 10.0


def socket_pfad() -> str:
    return os.environ.get("CHIMERA_TOR_SOCKET", SOCKET)


def anfragen(anfrage: dict, *, warten: float = WARTEN_KURZ,
             pfad: str | None = None) -> dict:
    """Eine Zeile hin, eine zurueck. Wirft ``Unavailable``, wenn das
    Gateway nicht erreichbar ist."""
    pfad = pfad or socket_pfad()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(warten)
    try:
        s.connect(pfad)
        s.sendall(json.dumps(anfrage, ensure_ascii=False).encode("utf-8") + b"\n")
        puffer = b""
        while not puffer.endswith(b"\n"):
            teil = s.recv(65536)
            if not teil:
                raise Unavailable("Das Gateway hat die Verbindung beendet.")
            puffer += teil
            if len(puffer) > MAX_ZEILE:
                raise LLMError("Antwort des Gateways zu gross.")
    except (OSError, socket.timeout) as exc:
        raise Unavailable(f"Gateway nicht erreichbar ({pfad}): {exc}") from exc
    finally:
        s.close()
    try:
        antwort = json.loads(puffer.decode("utf-8"))
    except ValueError as exc:
        raise LLMError(f"Antwort des Gateways ist kein JSON: {exc}") from exc
    if not isinstance(antwort, dict):
        raise LLMError("Antwort des Gateways ist kein Objekt.")
    return antwort


def erreichbar(pfad: str | None = None) -> bool:
    """Antwortet ein Gateway? Ein echter Aufruf, nicht ``os.path.exists``:
    Eine Socket-Datei kann ohne Lauscher liegen bleiben."""
    try:
        return anfragen({"op": "ping"}, warten=3.0, pfad=pfad).get("ok") is True
    except LLMError:
        return False


def _fehler(antwort: dict) -> LLMError:
    f = antwort.get("fehler") or {}
    code, text = f.get("code", "unbekannt"), f.get("text", "ohne Angabe")
    if code in ("nicht_eingerichtet", "nicht_erreichbar", "ausgelastet"):
        return Unavailable(text)
    return LLMError(f"{text} ({code})")


class GatewayOllama(Connector):
    """Ollama, erreicht ueber das Gateway."""

    name = "ollama"
    access = Access.LOCAL
    cost = CostClass.FREE
    supports_tools = True
    supports_streaming = False
    context_window = 32_000

    PROBE_TTL = 30.0

    def __init__(self, default_model: str | None = None, *, pfad: str | None = None):
        self.default_model = default_model or os.environ.get("OLLAMA_MODEL") or None
        self.pfad = pfad
        self.base_url = ""            # Der Dienst kennt die Adresse nicht.
        self.host = ""                # nur der Rechnername, fuer die Anzeige
        self._probe: tuple[float, bool] | None = None
        self._models: list[str] = []
        self._grund: str | None = None

    @property
    def configured(self) -> bool:
        return True                   # ob der Server eingetragen ist, weiss das Gateway

    @property
    def label(self) -> str:
        return f"ollama @ {self.host}" if self.host else "ollama (lokal)"

    def why_unavailable(self) -> str | None:
        if not self.is_available():
            return self._grund or "Ollama ist ueber das Gateway nicht erreichbar."
        return None

    def is_available(self) -> bool:
        jetzt = time.monotonic()
        if self._probe and jetzt - self._probe[0] < self.PROBE_TTL:
            return self._probe[1]
        ok = False
        try:
            a = anfragen({"op": "modelle", "anbieter": "ollama"}, pfad=self.pfad)
            if a.get("ok"):
                self._models = list(a.get("modelle", []))
                self.host = a.get("host", "")
                self._grund = None
                ok = True
            else:
                self._grund = (a.get("fehler") or {}).get("text")
        except LLMError as exc:
            self._grund = str(exc)
        self._probe = (jetzt, ok)
        return ok

    def models(self) -> list[str]:
        if not self._models:
            self.is_available()
        return list(self._models)

    def call(self, prompt: str, history: list[dict],
             system: str | None = None, *, model: str | None = None, **kw) -> str:
        anfrage = {
            "op": "chat", "anbieter": "ollama",
            "modell": model or self.default_model or "",
            "system": system or "", "verlauf": list(history), "prompt": prompt,
        }
        try:
            a = anfragen(anfrage, warten=WARTEN_CHAT, pfad=self.pfad)
        except Unavailable:
            self._probe = (time.monotonic(), False)
            raise
        if not a.get("ok"):
            raise _fehler(a)
        self.host = a.get("host", self.host)
        return a["text"]
