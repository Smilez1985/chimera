# Research: Agent Client Protocol und MCP im Vergleich

Stand 2.11.2026. Quellen: Spezifikation von `agentclientprotocol.com` (v1) und
`modelcontextprotocol.io` (Revision **2026-07-28**), beide am 2.11.2026
gelesen. Zu den drei Protokollen mit dem Kürzel ACP siehe
`docs/research/ACP.md`; hier ist mit ACP stets der **Agent Client Protocol**
gemeint. Folgerungen stehen in `docs/DESIGN.md` (Regel „ACP“).

*Research: Agent Client Protocol versus MCP. English summary at the end.*

---

## 1. Kurz

| | MCP | ACP (Client Protocol) |
|---|---|---|
| Wer spricht mit wem | **Modell/Agent ↔ Werkzeug und Daten** | **Editor/Client ↔ Agent** |
| Was wird geliefert | Werkzeuge, Ressourcen, Prompts | Nutzereingabe, Plan, Antwort, Werkzeugstatus |
| Richtung der Anfragen | **Client fragt, Server antwortet**; Server initiiert keine Anfragen (Revision 2026-07-28) | **Beide Seiten** rufen Methoden auf |
| Zustand | **ohne Sitzung** im Protokoll (seit 2026-07-28) | **Sitzungen** gehören zum Kern (`session/new`, `load`) |
| Wire | JSON-RPC 2.0 | JSON-RPC 2.0 |
| Transport | stdio **und** Streamable HTTP (POST, eigener Endpunkt) | **nur stdio** (HTTP/WebSocket im Entwurf) |
| Wer startet wen | stdio: Client startet Server; HTTP: Server ist eigener Prozess | Client startet den Agenten als Unterprozess |
| Zielgruppe | jede Anwendung, die Werkzeuge anbinden will | Editoren, IDEs, Oberflächen |
| Das Wort dafür | „USB-C für Werkzeuge“ | „LSP für Agenten“ |

**Sie ergänzen sich, sie ersetzen sich nicht.** Ein Editor spricht ACP mit dem
Agenten; der Agent spricht MCP mit seinen Werkzeugen. ACP reicht dem Agenten
sogar die MCP-Server des Clients durch (`mcpServers` in `session/new`).

## 2. Was gleich ist

- **JSON-RPC 2.0**, UTF-8, zwei Nachrichtenarten: Anfrage mit Antwort und
  Benachrichtigung.
- **Newline-getrennte Nachrichten über stdio.** MCP schreibt es selbst: Eigene
  Transporte über Unix-Sockets oder TCP *sollen* den stdio-Rahmen
  wiederverwenden. ACP ordnet es genauso an.
- **Fähigkeiten werden ausgehandelt**, nicht angenommen (`initialize` bei
  ACP; bei MCP trägt künftig jede Anfrage Version und Fähigkeiten im Rumpf).
- **ACP verwendet MCP-Typen** (Inhaltsblöcke, Werkzeugaufrufe) wieder.
- **Beide verlangen Vorsicht** vor Inhalten, die der Gegenüber liefert: MCP
  verlangt die Prüfung des `Origin`-Kopfs gegen DNS-Rebinding und lokales
  Binden; ACP erklärt jeden Agententext zu nicht vertrauenswürdiger Eingabe.

## 3. Was sich unterscheidet

### 3.1 Richtung und Zustand

**MCP (2026-07-28)** ist zustandslos geworden: Der Client beginnt jede
Interaktion, der Server antwortet, und **Server stellen keine Anfragen mehr**.
Was früher eine Rückfrage des Servers war (Sampling, Elicitation, Roots), wird
**in die Antwort eingebettet** („Multi Round-Trip Requests“). Der GET-Strom ist
entfallen; dauerhafte Änderungsmeldungen laufen über eine Anfrage
`subscriptions/listen`.

**ACP** ist ein Gespräch: Der Agent ruft **beim Client** an (`fs/read_text_file`,
`terminal/create`, `session/request_permission`) und schickt laufend
`session/update`. Der Zug endet erst mit der Antwort auf `session/prompt`.

**Folge für den Bau:** Ein ACP-Server braucht einen **offenen, doppelseitigen
Kanal** je Verbindung. Ein MCP-Server in der neuen Fassung braucht das nicht
und kommt mit POST und Antwortstrom aus. Beide auf **demselben** Endpunkt zu
sprechen, geht nicht ohne Weiteres (siehe 4).

### 3.2 Transport

| | MCP | ACP |
|---|---|---|
| stdio | ja | ja, **einziger** festgelegter |
| HTTP | Streamable HTTP, ein Endpunkt, POST | Entwurf: HTTP/2 mit GET-Strömen und POST **oder** WebSocket |
| Zuverlässiger Bytestrom (Unix-Socket, TCP) | „soll stdio-Rahmen nutzen“ | eigener Transport erlaubt, Rahmen und Ablauf müssen erhalten bleiben |

### 3.3 Wer trägt die Anmeldung

MCP hat ein eigenes Autorisierungsverfahren für HTTP (OAuth). ACP hat
`authenticate` für agentenseitige Verfahren und eine Registry für Agenten, die
Anmeldung unterstützen. Bei stdio erbt der Agent die Rechte seines Prozesses.

## 4. Kann ein MCP-Server zugleich ACP-Server sein?

**Auf der Protokollebene: ja, mit Arbeit. Auf einem Endpunkt: nein, besser
nicht.**

- **Gleiche Grundlage:** beide JSON-RPC 2.0, beide mit Zeilenrahmen über
  stdio, **keine kollidierenden Methodennamen** (MCP: `tools/list`,
  `tools/call`, `resources/*`; ACP: `initialize`, `session/*`, `fs/*`,
  `terminal/*`). Ein Programm *kann* beide Wörterbücher kennen.
- **Aber `initialize` heißt in beiden gleich** und meint Verschiedenes. In der
  aktuellen MCP-Revision gibt es überdies kein `initialize` mehr (Fähigkeiten
  stecken in jeder Anfrage). Ein Server müsste an der **ersten Nachricht** raten,
  wer anruft. Das ist fragil.
- **Die Aufgaben sind verschieden.** ACP-Server heißt: *ich bin der Agent*.
  MCP-Server heißt: *ich biete Werkzeuge*. Chimera ist beides, aber in
  **verschiedenen Rollen**: als Agent (ACP) für die IDE, als Werkzeuganbieter
  (MCP) für andere Agenten.
- **Die Transporte passen nicht zusammen:** ACP braucht heute stdio, MCP-HTTP
  einen POST-Endpunkt. Der Entwurf für ACP über HTTP wäre ein **zweiter,
  anderer** HTTP-Vertrag (GET-Ströme, HTTP/2, WebSocket).
- **Das Sicherheitsmodell ist verschieden.** Wer MCP anbietet, gibt
  *Werkzeuge* frei; wer ACP anbietet, gibt *den Agenten selbst* frei. Beides an
  einer Tür mit einem Token zu mischen, verwischt, wofür das Token gilt.

**Besser:** **ein Prozess, zwei getrennte Türen.** Gemeinsam sind
`Session` und Gateway-Logik; getrennt sind die Eingänge.

```
IDE (Zed, JetBrains, Android Studio) ─ACP─►  Tür "acp"  ┐
andere Agenten (woa-l, Claude Code)  ─MCP─►  Tür "mcp"  ├─► Gateway-Logik ─► Hauptsitzung
Telegram, Web                                Türen      ┘
```

## 5. Was das für den Rust-Bau bedeutet

- **Eine Bibliothek gibt es schon:** die Rust-Crate `agent-client-protocol`
  3.6.0 (Apache-2.0, Rust 1.88, rund 400 kB) mit den Merkmalen `Agent` und
  `Client`. **Geprüft am 2.11.:** 16 normale Abhängigkeiten, darunter `futures`
  und `futures-concurrency`, optional `async-io`, `async-process`, `blocking`.
  Unser Gateway läuft bewusst **ohne Laufzeit** (`tiny_http`, Threads, Regel
  „Rust, klein“, `MemoryMax=10M`). Ob die Crate ohne eine Laufzeit nutzbar ist
  und wie viel sie im Binary wiegt, ist **nicht gemessen**. Der Mindestumfang
  (fünf Methoden, JSON-RPC mit Zeilenrahmen) ist klein genug, um ihn mit
  `serde_json` selbst zu bauen; das ist die Alternative, falls die Crate zu
  schwer ist.
- **Wir bauen keinen vollständigen Agenten nach ACP, sondern den Mindestumfang:**
  `initialize`, `session/new`, `session/prompt`, `session/update`,
  `session/cancel`. Alles andere (Dateien, Terminals, Modi) ist optional und
  fällt weg, solange Chimera kein Arbeitsverzeichnis des Clients nutzt.
- **Transport:** Auf dem Pi läuft Chimera als Dienst, die IDE woanders. ACP-stdio
  verlangt, dass der Client den Agenten startet. Das geht nur mit einem
  **Vermittler** auf dem Rechner der IDE (startet lokal, spricht per SSH oder
  HTTP mit dem Pi) oder mit dem HTTP-Entwurf, wenn er beschlossen ist.
- **Der MQTT-Teil** der Frage ist ein **dritter** Weg und gehört nicht in dieses
  Protokollpaar: MQTT ist Publish/Subscribe für Geräte. Er hat mit ACP und MCP
  nichts gemeinsam außer dem Wunsch nach einer Schnittstelle.

## 6. Offen

- Ob die Crate `agent-client-protocol` für den Pi taugt.
- Wie sich die Zugriffsrechte der Tür „acp“ von denen der Tür „mcp“ trennen
  (Positivliste je Tür).
- Ob und wann MCP auf die zustandslose Fassung wechselt, die woa-l heute noch
  nutzt: Der Briefkasten (Regel „Briefkasten“) spricht die ältere Form.

---

## English summary

MCP connects a model or agent to tools and data; ACP (the Client Protocol)
connects an editor to an agent. Both use JSON-RPC 2.0 with newline framing
over stdio and complement each other: ACP even hands the client's MCP servers to
the agent. They differ in direction (MCP 2026-07-28 is stateless and
client-initiated; ACP is a two-way session), in transport (MCP has stdio and
Streamable HTTP; ACP has only stdio, with HTTP in draft) and in what a grant
means (tools versus the agent itself). One process can speak both, but not on one
endpoint: `initialize` clashes and the trust models differ. Recommended: one
process, two separate doors that share the session and gateway logic.
