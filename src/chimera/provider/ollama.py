"""Ollama im eigenen Netz.

Eigener Anbieter, kein Sonderfall einer Vermittlungsschicht (Regel 5c).
Sonst lässt sich nicht unterscheiden, ob der Server weg ist oder ein
Zugang fehlt — und genau diese Unterscheidung braucht der Rückfall.

**Keine Voraussetzung** (Regel 5h): Fehlt der Server, meldet sich der
Anbieter als nicht verfügbar, die Aufgabe fällt auf ihr nächstes Ziel
zurück, und sonst passiert nichts.

Aus dem eigenen Fork von openclawgotchi übernommen (Idee, nicht Code):
Der Platzhalter aus der Beispielkonfiguration wird als „nicht gesetzt"
behandelt statt in einen Verbindungsfehler zu laufen.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from .base import Access, Connector, CostClass, LLMError, Unavailable

log = logging.getLogger(__name__)

#: Werte, die in Beispielkonfigurationen stehen und nichts bedeuten.
PLACEHOLDERS = {
    "", "http://ollama-server:11434", "ollama-server",
    "http://localhost:11434/CHANGEME", "http://ip:11434",
    "http://dein-server:11434",
}


class OllamaConnector(Connector):
    name = "ollama"
    access = Access.LOCAL
    cost = CostClass.FREE
    supports_tools = True
    supports_streaming = True
    context_window = 32_000          # modellabhängig; Voreinstellung

    #: So lange gilt eine Verfügbarkeitsprüfung. Die Registry fragt bei
    #: jedem Rückfall -- ohne Zwischenspeicher wäre das eine Netzabfrage
    #: je Aufruf.
    PROBE_TTL = 30.0

    def __init__(self, base_url: str | None = None,
                 default_model: str | None = None, *, timeout: float = 120.0):
        self.base_url = (base_url or os.environ.get("OLLAMA_API_BASE", "")).strip().rstrip("/")
        self.default_model = default_model or os.environ.get("OLLAMA_MODEL") or None
        self.timeout = timeout
        self._probe: tuple[float, bool] | None = None
        self._models: list[str] = []

    # --- Zustand ----------------------------------------------------------

    @property
    def configured(self) -> bool:
        """Ist überhaupt eine echte Adresse hinterlegt?"""
        return bool(self.base_url) and self.base_url not in PLACEHOLDERS

    def why_unavailable(self) -> str | None:
        """Klartext für die Übersicht — statt eines Verbindungsfehlers."""
        if not self.base_url:
            return "OLLAMA_API_BASE ist nicht gesetzt."
        if self.base_url in PLACEHOLDERS:
            return (f"OLLAMA_API_BASE steht noch auf dem Platzhalter "
                    f"({self.base_url}) — echte Adresse eintragen.")
        if not self.is_available():
            return f"{self.base_url} antwortet nicht."
        return None

    def is_available(self) -> bool:
        if not self.configured:
            return False
        now = time.monotonic()
        if self._probe and now - self._probe[0] < self.PROBE_TTL:
            return self._probe[1]
        ok = False
        try:
            self._models = self._fetch_models()
            ok = True
        except Exception as exc:
            log.debug("Ollama nicht erreichbar: %s", exc)
        self._probe = (now, ok)
        return ok

    def models(self) -> list[str]:
        if not self._models and self.is_available():
            pass          # is_available füllt die Liste
        return list(self._models)

    # --- Netz -------------------------------------------------------------

    def _get(self, path: str, timeout: float):
        req = urllib.request.Request(f"{self.base_url}{path}")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _fetch_models(self) -> list[str]:
        data = self._get("/api/tags", timeout=4.0)
        return [m["name"] for m in data.get("models", []) if "name" in m]

    def call(self, prompt: str, history: list[dict],
             system: str | None = None, *, model: str | None = None,
             **kw) -> str:
        if not self.configured:
            raise Unavailable(self.why_unavailable() or "nicht eingerichtet")

        use = model or self.default_model
        if not use:
            # Kein Modell genannt und keines voreingestellt: das erste
            # vorhandene nehmen ist besser als abzubrechen -- aber es wird
            # gesagt, nicht stillschweigend getan.
            found = self.models()
            if not found:
                raise Unavailable("Kein Modell angegeben und keines gefunden.")
            use = found[0]
            log.info("Ollama: kein Modell angegeben, nehme %s", use)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        body = json.dumps({
            "model": use,
            "messages": messages,
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/chat", data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise LLMError(f"Ollama antwortet {exc.code}: {exc.reason}") from exc
        except Exception as exc:
            self._probe = (time.monotonic(), False)
            raise Unavailable(f"Ollama nicht erreichbar: {exc}") from exc

        text = (data.get("message") or {}).get("content", "")
        if not text:
            raise LLMError("Ollama lieferte eine leere Antwort.")
        return text


def discover(hosts=None, port: int = 11434, timeout: float = 1.0) -> list[str]:
    """Ollama im Netz suchen — für die Ersteinrichtung.

    Liefert erreichbare Adressen. Sucht nur an naheliegenden Stellen; ein
    Netzscan wäre unhöflich und dauert zu lange.
    """
    cands = list(hosts) if hosts else []
    if not cands:
        cands = ["localhost", "127.0.0.1", "ollama.local", "ollama"]
        gw = os.environ.get("OLLAMA_HOST")
        if gw:
            cands.insert(0, gw)

    found = []
    for host in cands:
        url = host if host.startswith("http") else f"http://{host}:{port}"
        try:
            with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout):
                found.append(url)
        except Exception:
            continue
    return found
