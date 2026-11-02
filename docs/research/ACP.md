# Research: ACP — drei Protokolle mit demselben Kürzel

Stand 2.11.2026. Quellen am 2.11.2026 gelesen: `agentclientprotocol.com`
(Spezifikation v1, Entwurf v2, RFDs, Bibliotheksseite, Registry),
`agentcommunicationprotocol.dev`, die Repos `agx-dev/acp` und
`agent-context-protocol/agent-context-protocol`, die offizielle Ankündigung
von Android Studio Rabbit 2 (`developer.android.com`) und zwei Einrichtungs-
artikel. Der Vergleich mit MCP steht in `docs/research/ACP-MCP.md`.
Entscheidung und Regeln stehen in `docs/DESIGN.md` (Regel „ACP“), Vorhaben in
`docs/ROADMAP.md`.

*Research: three protocols that share the abbreviation ACP. English summary at
the end.*

---

## 1. Anlass und eine Klärung

Vorgabe smilez (2.11.): ACP ist eine **Pflicht-Schnittstelle**. Der in Rust
geschriebene MCP/MQTT-Server soll zugleich ein ACP-Server sein. Genannt wurde
„Agent Context Protocol“. Dazu kam ein Hinweis auf Android Studio Rabbit 2.
**Entschieden:** Der ACP-Server wird gebaut, mit einer Transportschicht, damit
eine IDE das Gateway ansprechen kann. Der MQTT-Broker ist ein eigenes Vorhaben
(Regel „MQTT“); MQTT stammt aus PaKaChi-SM (Quelle, privat), nicht aus woa-l.

**Das Kürzel gehört drei verschiedenen Protokollen.** Das ist keine
Spitzfindigkeit: Welches gemeint ist, entscheidet, was gebaut wird.

| | Agent **Client** Protocol | Agent **Communication** Protocol | Agent **Context** Protocol |
|---|---|---|---|
| Wofür | Editor, IDE oder App spricht mit einem **Agenten** | Agent spricht mit Agent (REST) | Agent-Speicher als Standard; zweites Projekt: Agent-zu-Agent mit DAG |
| Herkunft | Zed Industries, JetBrains | IBM, BeeAI | zwei kleine Einzelprojekte |
| Stand | v1 stabil, v2 im Entwurf, Rust-Bibliothek 3.6.0 | **aufgegangen in A2A** (Linux Foundation) | Spezifikation v0.1 bzw. Forschungscode |
| Verbreitung | über 40 Agenten, Android Studio, JetBrains, Zed | als Standard ersetzt | gering |
| Wire | JSON-RPC 2.0 über **stdio** (HTTP im Entwurf) | REST, OpenAPI | JSON-RPC 2.0 über stdio |
| Unser Bedarf | **ja: das ist die gemeinte Pflicht** | nein | Ideen für das Gedächtnis |

Wo dieses Dokument „ACP“ ohne Zusatz schreibt, meint es den **Agent Client
Protocol**, denn nur er ist weit verbreitet, aktuell und beschreibt, was
smilez braucht (ein Editor spricht mit Chimera als Agent).

## 2. Agent Client Protocol

### 2.1 Was es ist

„Standardisiert die Kommunikation zwischen Code-Editoren/IDEs und Coding-
Agenten, für lokale wie entfernte Fälle.“ Ohne ihn müsste jeder Editor jeden
Agenten einzeln anbinden und jeder Agent editorspezifische Schnittstellen
bauen. Er ist der „LSP der Agenten“, und er wurde bewusst an MCP angelehnt.

### 2.2 Aufbau

- **JSON-RPC 2.0**, zwei Nachrichtenarten: *Methoden* (Anfrage und Antwort) und
  *Benachrichtigungen* (einseitig). **Beide Seiten** rufen Methoden auf.
- **Der Client startet den Agenten als Unterprozess**; Nachrichten laufen über
  `stdin` und `stdout`, eine je Zeile, ohne Zeilenumbruch im Inhalt. `stderr`
  ist für Protokolle. Der Agent darf nichts anderes auf `stdout` schreiben.
- Mehrere Sitzungen je Verbindung („mehrere Gedankengänge zugleich“).
- **MCP-freundlich:** MCP-Typen werden wiederverwendet; der Client reicht dem
  Agenten die Liste seiner MCP-Server (`mcpServers`), und der Agent verbindet
  sich selbst.

### 2.3 Ablauf

1. **`initialize`:** Version und Fähigkeiten austauschen. Der Client nennt
   `clientCapabilities` (`fs.readTextFile`, `fs.writeTextFile`, `terminal`,
   `auth.terminal`), der Agent `agentCapabilities` (`loadSession`,
   `promptCapabilities`: Bild, Audio, eingebetteter Kontext, MCP-Unterstützung).
2. **Anmeldung** (`authenticate`), wenn der Agent es verlangt.
3. **`session/new`** oder **`session/load`**; dabei Arbeitsverzeichnis und MCP-
   Server mitgeben.
4. **`session/prompt`:** Der Client schickt die Nutzereingabe. Der Agent meldet
   Fortschritt per **`session/update`** (Plan, Textstücke der Antwort, Werkzeug-
   aufrufe mit Status), fragt bei Bedarf **`session/request_permission`**,
   nutzt die Dateizugriffe und Terminals des **Clients**, und beendet den
   Zug mit einer Antwort samt `stopReason`.
5. **`session/cancel`** bricht ab.

Weitere Teile: Sitzungsliste, Löschen, Modi, Konfigurationsoptionen, Slash-
Befehle, Elicitation (strukturierte Rückfragen), Plan, Erweiterungen über
`_meta`.

### 2.4 Sicherheitsmodell (wörtlich relevant für Chimera)

- Der Agent läuft **mit den Rechten seines Prozesses**; ACP sandboxt nicht.
- Alles, was der Agent schreibt (Texte, URIs, Pfade), gilt als **nicht
  vertrauenswürdig**; Dateien, Webseiten und Werkzeugergebnisse beeinflussen
  seine Ausgabe.
- **Berechtigungsanfragen sind beratend:** Der Agent führt seine Operationen
  selbst aus und muss die Entscheidung des Nutzers einhalten.
- `clientInfo` und `agentInfo` sind **selbstberichtet** und dürfen nicht für
  Sicherheitsentscheidungen dienen; der Client erkennt den Agenten an seiner
  eigenen Startkonfiguration.
- Ein Agent mit mehreren Nutzern **muss** Sitzungsliste, Laden und Rückfragen
  auf den Besitzer der Sitzung beschränken.
- Keine Zugangsdaten in `_meta`.

### 2.5 Transport

**Heute nur stdio** (Pflicht: „SOLLTEN stdio unterstützen“). Eine **entfernte**
Variante ist als Entwurf (RFD) beschrieben: Streamable HTTP mit langlebigen
GET-Strömen (einer je Verbindung, einer je Sitzung) und POST für Anfragen,
**HTTP/2 verlangt**, dazu WebSocket auf demselben Endpunkt; die Cookie-
Unterstützung ist Pflicht. Beschlossen ist das nicht.

### 2.6 Bibliotheken und Verbreitung

- Rust-Crate **`agent-client-protocol` 3.6.0** (Stand 28.10.2026, rund 5,8
  Millionen Abrufe), mit den Merkmalen `Agent` und `Client`; Zed nutzt sie.
  Weitere Bibliotheken: Kotlin, Java, Python, TypeScript.
- **Über 40 Agenten**, darunter Claude Agent (über Zeds Adapter), Codex CLI,
  Gemini CLI, Copilot, Cursor, Goose, OpenCode, Kimi, Mistral Vibe, OpenClaw,
  Hermes Agent. Eine **Registry** listet Agenten, die Anmeldung unterstützen.
- Entwurf **„Configurable LLM Providers“**: Der Client kann dem Agenten über
  `providers/list`, `providers/set`, `providers/disable` eigene Modellwege
  (Proxy, Gateway, selbst betriebene Modelle) vorgeben.

## 3. Android Studio Rabbit 2 (die Websuche)

- **Rabbit 2 (2026.2.2)** ging am **28.10.2026** in den stabilen Kanal, zum
  Android Dev Summit. Die Ankündigung nennt **„Bring Your Own Agent“ (BYOA)**:
  über 40 ACP-Agenten laufen in der IDE, darunter Claude Agent, Codex, Junie
  und Google Antigravity, mit Zugriff auf Emulator, Build-System, Logcat und
  **Android-Skills**.
- Einrichtung: Agentenfenster öffnen oder **Settings > Tools > AI > Agents**,
  einen Agenten aus der **Registry** wählen, anmelden, Prompt senden. Dazu ein
  Skill-Manager, KI-Codereview und Android-CLI (`android init`, `android skills`).
- Folgerung für Chimera: **Eine IDE, die ACP spricht, kann Chimera ansprechen,
  sobald Chimera ein ACP-Agent ist.** Die Anbindung geht dort über die
  Agenten-Registry; ein eigener Eintrag ist die Voraussetzung. Wie genau ein
  selbst gebauter Agent ohne Registry eingetragen wird, steht in den gelesenen
  Quellen **nicht** und ist offen.
- Sicherheitshinweis der Quellen: Die Anbindung schafft eine gemeinsame
  Vertrauensgrenze aus Projekt, Agent, Modell und Werkzeugen; Shell-Zugriff
  und Emulator sind mächtig. Das deckt sich mit dem Sicherheitsmodell oben.

## 4. Agent Communication Protocol (IBM/BeeAI)

REST/OpenAPI, Agent-zu-Agent: Manifest, Erkennung, „Run“ mit Lebenszyklus,
Sitzungen, Artefakte, `await`, hohe Verfügbarkeit. **Aufgegangen in A2A** unter
der Linux Foundation; die eigene Seite trägt den Hinweis „ACP is now part of
A2A“. Für Chimera **kein Ziel**. Interessant bleibt der Gedanke eines
„MCP-Adapters“, der einen Agenten als MCP-Werkzeug sichtbar macht.

## 5. Agent Context Protocol (zwei Projekte)

**`agx-dev/acp`** (Juli 2026, Apache 2.0, Rust, **ein Commit**, rund 10 000
Zeilen): Spezifikation für **Agent-Gedächtnis** in vier Schichten (episodisch,
semantisch, Kontextgraph, prozedural), mit Methoden wie `acp.memory.store`,
`acp.memory.recall`, `acp.version.snapshot`, `acp.skill.register`. Läuft als
**MCP-Server über stdio**; „Layer 4“ über MCP, A2A und WebMCP. Formal nicht
verbreitet (Spezifikation v0.1).

**`agent-context-protocol/agent-context-protocol`** (Mai 2025, MIT, Python,
**ein Commit**): Forschungsprojekt für Mehr-Agenten-Systeme mit einem DAG,
Nachrichtenformen (`AGENT_REQUEST`, `AGENT_RESPONSE`, `ASSISTANCE_REQUEST`) und
Fehlercodes 601 bis 607. Kein Server; die Last liegt in Prompts. Nutzt MCP als
Client.

**Für Chimera:** nichts davon wird Schnittstelle. Zwei Ideen sind lesenswert und
gehören zum Gedächtnis (Regel „Gedächtnis verdichtet sich nach oben“): die vier
Schichten und der Versionsstand des Zustands (Snapshot, Wiederherstellen).

## 6. Folgerungen für Chimera

1. **Gemeint ist der Agent Client Protocol.** Er ist die Pflicht-Schnittstelle:
   Editoren und IDEs (Zed, JetBrains, Android Studio) sprechen damit mit einem
   Agenten.
2. **Chimera wird der Agent, nicht der Client.** Es nimmt Prompts entgegen, meldet
   Fortschritt und beendet Züge. Das passt zu `Session` und zum Ereignisstrom
   (Regel „Ein Kanal, eine Hauptsitzung“).
3. **Der Transport ist die Frage:** ACP-stdio erwartet, dass der **Client den
   Agenten startet**. Chimera läuft aber als Dienst auf dem Pi, die IDE auf
   einem anderen Rechner. Dafür braucht es einen **Vermittler**, der lokal per
   stdio startet und die Verbindung zum Pi herstellt (SSH oder HTTP), oder den
   Entwurf für HTTP/WebSocket, sobald er beschlossen ist.
4. **Der Agent bleibt hinter dem Gateway** (Regel „Gateway“): Der ACP-Zugang ist
   eine **Tür** wie Telegram und die Weboberfläche, mit Anmeldung, Positivliste
   und nur im eigenen Netz.
5. **Ein Zug ist ein Turn in der Hauptsitzung.** Eine ACP-Sitzung bildet sich auf
   die Hauptsitzung ab (kein zweiter Verlauf).

## 7. Offen

- Wie ein eigener Agent in Android Studio ohne Registry eingetragen wird (nicht
  gelesen; zu klären an einer installierten IDE).
- Ob der HTTP-Transport als Standard kommt und in welcher Form.
- Ob Chimera als Agent die Client-Fähigkeiten nutzt (Dateien lesen, Terminal):
  Auf einem Gerät ohne Arbeitsverzeichnis des Clients wohl nicht.
- Der Umfang der ersten Fassung: nur `initialize`, `session/new`,
  `session/prompt`, `session/update`, `session/cancel` (Mindestumfang).

---

## English summary

The abbreviation ACP names three protocols: the **Agent Client Protocol** (Zed
and JetBrains; editors talk to coding agents; JSON-RPC over stdio, HTTP in
draft; Rust crate 3.6.0; over 40 agents; used by Android Studio Rabbit 2),
the **Agent Communication Protocol** (IBM/BeeAI; REST; now merged into A2A) and
two small **Agent Context Protocol** projects (agent memory; a multi-agent
DAG research code). smilez' requirement means the Client Protocol: an editor or
IDE talks to Chimera as an agent. Chimera is the agent, reached through a door
in the gateway; the open question is transport, because ACP expects the client
to start the agent as a subprocess while Chimera runs as a service on the Pi.
