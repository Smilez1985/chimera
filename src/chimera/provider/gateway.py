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


#: Zugang und Kosten je Anbietertyp — **ein Ort** (Grundsatz „ein Feld, ein
#: Ort"): die Aufgabenkette wählt nach `cost` (5h), die Anzeige nennt
#: `access`, beide lesen hier. Aufgeführt ist nur, was das Gateway wirklich
#: bedient (`dienst::anbieter_finden` und der Modulverteiler in Rust).
TYP_KLASSEN = {
    "ollama": (Access.LOCAL, CostClass.FREE),
    "deepseek": (Access.API_KEY, CostClass.METERED),
}

#: Die Typen mit Chat-Modul im Gateway. `provider.setup` nimmt nur diese;
#: ein Eintrag anderen Typs wird benannt und übersprungen, nie geraten.
CHAT_TYPEN = tuple(TYP_KLASSEN)

#: Was für einen unbekannten Typ gilt. **Nicht** LOCAL/FREE: ein Anbieter,
#: dessen Kosten niemand kennt, gehört nicht in die billige Kette (5h) — die
#: vorsichtige Seite ist die richtige, weil sie nur Geld kostet, wenn jemand
#: den Eintrag ausdrücklich wählt.
FREMD_KLASSEN = (Access.API_KEY, CostClass.METERED)


def klassen_fuer(typ: str) -> tuple[Access, CostClass]:
    """`(access, cost)` für einen Anbietertyp — unbekannt heißt kostenpflichtig."""
    return TYP_KLASSEN.get((typ or "").strip().lower(), FREMD_KLASSEN)


class GatewayAnbieter(Connector):
    """Ein Anbieter, erreicht ueber das Gateway.

    Heisst nicht mehr ``GatewayOllama``: Seit 14.11. spricht derselbe
    Connector jeden Anbieter, den das Gateway bedient (Ollama und DeepSeek),
    und bekommt seine Kennung im Konstruktor. Der alte Name bleibt als
    Alias, damit Aufrufer und Tests nicht doppelt existieren muessen.
    """

    name = "ollama"
    #: Vorgabe für die Klassenzeile; der echte Wert kommt je Anbieter aus
    #: `klassen_fuer()` (14.11.: DeepSeek meldete hier LOCAL/FREE und
    #: sortierte damit in die billige Kette — auch für den bezahlten Schlüssel).
    access = Access.LOCAL
    cost = CostClass.FREE
    supports_tools = True
    supports_streaming = False

    #: **Angenommen, nicht gemessen.** Der echte Wert kommt aus dem Katalog des
    #: Gateways (`op: katalog_lesen`, dort steht, was `/api/show` gemeldet hat).
    #: Bis das gemessen ist, gilt dieser Wert -- und `fenster_angenommen`
    #: bleibt True, damit es niemand fuer eine Messung haelt (DESIGN 5a).
    context_window = 32_000
    fenster_angenommen = True

    PROBE_TTL = 30.0

    def __init__(self, default_model: str | None = None, *, pfad: str | None = None,
                 anbieter: str = "ollama", label: str | None = None,
                 typ: str | None = None):
        # Der Connector spricht **jeden** Anbieter, den das Gateway bedient
        # (14.11.): der Name kommt aus der Anbieterliste, nicht aus der
        # Klassenzeile. Vorher stand hier fest "ollama", und damit war
        # DeepSeek im Gespraech nicht erreichbar -- egal, was der Nutzer
        # waehlte.
        self.name = anbieter
        # Zugang und Kosten gehören zum **Typ**, nicht zur Kennung: derselbe
        # Connector bedient ollama (lokal, kostenlos) und deepseek (Schlüssel,
        # abgerechnet). Ohne Typ gilt der Typ der Kennung; ist auch die
        # unbekannt, bleibt es bei den vorsichtigen Klassen.
        self.access, self.cost = klassen_fuer(typ if typ is not None else anbieter)
        self._label = label
        # Keine Einstellung als Quelle (DESIGN 5n, "Das Modell kommt vom
        # Server", smilez 11.11.2026): `OLLAMA_MODEL` wird hier nicht mehr
        # gelesen. Ohne genanntes Modell waehlt das Gateway aus der Liste,
        # die der Server meldet -- nach dem gemessenen `tools`. Ein
        # `default_model` gilt nur, wenn der Aufrufer es ausdruecklich setzt.
        self.default_model = default_model or None
        #: Was das Gateway ohne weitere Frage nehmen wuerde (`op: modelle` ->
        #: `wahl`). Dieselbe Regel wie im Chat, dort entschieden -- hier wird
        #: sie nicht nachgebaut.
        self.gewaehlt: str | None = None
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
        if self._label:
            return self._label
        return f"{self.name} @ {self.host}" if self.host else f"{self.name} (Vorgabe)"

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
            a = anfragen({"op": "modelle", "anbieter": self.name}, pfad=self.pfad)
            if a.get("ok"):
                self._models = list(a.get("modelle", []))
                self.host = a.get("host", "")
                self.gewaehlt = a.get("wahl") or None
                self._grund = None
                ok = True
                self._fenster_holen()
            else:
                self._grund = (a.get("fehler") or {}).get("text")
        except LLMError as exc:
            self._grund = str(exc)
        self._probe = (jetzt, ok)
        return ok

    def _fenster_holen(self) -> None:
        """Das Kontextfenster des bedienenden Modells aus dem Katalog holen.

        Warum nicht fest: Ein 27B-Modell hat ein anderes Fenster als ein 3B.
        Ein fester Wert prueft die Schwellen gegen das falsche Modell -- und
        faellt nicht auf, weil er wie eine Messung aussieht (DESIGN 5a).
        Bleibt der Katalog leer, gilt der Vorgabewert weiter, und
        `fenster_angenommen` sagt das.
        """
        modell = self.gewaehlt or self.default_model or (self._models[0] if self._models else "")
        if not modell:
            return
        try:
            k = anfragen({"op": "katalog_lesen", "id": self.name}, pfad=self.pfad)
        except LLMError:
            return
        if not k.get("ok"):
            return
        # Der gespeicherte Katalog hat die Form {"stand": <s>, "modelle": {...}}
        # (daten::katalog_lesen). Flach zu lesen war ein Fehler: das Fenster
        # kam nie aus einer Messung, und die Attrappe im Test hatte die
        # falsche Form nachgebaut.
        eintrag = ((k.get("katalog") or {}).get("modelle") or {}).get(modell) or {}
        try:
            fenster = int(eintrag.get("kontext") or 0)
        except (TypeError, ValueError):
            return
        if fenster > 0:
            self.context_window = fenster
            self.fenster_angenommen = False

    def models(self) -> list[str]:
        if not self._models:
            self.is_available()
        return list(self._models)

    def call(self, prompt: str, history: list[dict],
             system: str | None = None, *, model: str | None = None,
             werkzeuge: list[dict] | None = None, **kw) -> str:
        anfrage = {
            "op": "chat", "anbieter": self.name,
            "modell": model or self.default_model or "",
            "system": system or "", "verlauf": list(history), "prompt": prompt,
        }
        # Werkzeuge im neutralen Format (Regel „Aufrufe, nicht Text“) -- das Gateway uebersetzt sie.
        if werkzeuge:
            anfrage["werkzeuge"] = list(werkzeuge)
        if kw.get("stream"):
            anfrage["stream"] = True
        # Denkstufe: neutral weitergereicht, das Gateway uebersetzt sie je
        # Anbieter (DESIGN, Modellwahl 14.11.).
        if kw.get("denken"):
            anfrage["denken"] = kw["denken"]
        try:
            a = anfragen(anfrage, warten=WARTEN_CHAT, pfad=self.pfad)
        except Unavailable:
            self._probe = (time.monotonic(), False)
            raise
        if not a.get("ok"):
            raise _fehler(a)
        self.host = a.get("host", self.host)
        # Ein Aufruf ohne Text ist gueltig (DESIGN, Regel „Aufrufe, nicht Text“): die Liste traegt ihn.
        self.letzte_werkzeuge = list(a.get("werkzeuge") or [])
        return a.get("text", "")


# Alter Name, gleiche Sache (14.11.): der Connector ist nicht mehr auf
# Ollama festgelegt. Wer ihn mit Vorgabe baut, bekommt weiterhin ollama.
GatewayOllama = GatewayAnbieter
