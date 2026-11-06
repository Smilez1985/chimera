# Messung: ACP-Bibliothek gegen eigenen Mindestumfang (6.11.2026)

**Frage (ROADMAP, Phase ACP):** Die Rust-Crate `agent-client-protocol`
(Roadmap-Stand 3.6.0, inzwischen 5.0.0) hängt an `futures`/`tokio`; das
Gateway läuft ohne Laufzeit. Messen, ob sich die Crate lohnt — oder ob
Chimera den Mindestumfang mit `serde_json` selbst baut (DESIGN, Regel „ACP",
Punkt 7).

## Aufbau

Zwei Programme, **derselbe Vertrag**: JSON-RPC 2.0 mit Zeilenrahmen, auf
`initialize` mit einer gültigen Antwort antworten, sonst nichts. Beide lesen
stdin bis EOF und schreiben nach stdout.

- **A** — `Agent.builder().name(..).on_receive_request(initialize)`
  `.connect_to(Stdio::new())` mit der Crate (Features `stdio`, plus `tokio`
  mit `rt-multi-thread`), Beispiel aus der Crate selbst.
- **B** — eigener Zeilenrahmen: Zeile lesen, `serde_json` parsen, `id`
  erkennen, Antwort schreiben. Kein `async`, keine Laufzeit.

Gemessen in der Sandbox (aarch64, musl, wie das Zielgerät), Release-Profil,
Binärdatei gestrippt. Die Quellen liegen im Repo unter
`tools/messungen/acp-zeilenrahmen/` (beide Varianten, `messen.sh`, README mit
der Anleitung zum Nachmessen).

## Ergebnis

| Messgröße | A — Crate 5.0.0 | A — Crate 3.6.0 | B — `serde_json` |
|---|---|---|---|
| Binärdatei, gestrippt | 2 169 104 B (2,07 MB) | 2 300 296 B (2,19 MB) | **528 728 B (516 kB)** |
| 20 000 Anfragen durch den Zeilenrahmen | 5 034 ms | 3 794 ms | **370 ms** |
| Speicher im Ruhezustand (wartet auf Eingabe) | 984 kB RSS, 10 Fäden | 860 kB RSS, 10 Fäden | **424 kB RSS, 1 Faden** |
| Start bis zur ersten Antwort (Mittel aus 5) | 105 ms | 112 ms | **26 ms** |

Alle drei Programme beantworten dieselbe Anfrage mit demselben `result` —
der Vergleich ist also gleiche Arbeit, nicht gleicher Name.

## Was die Zahlen sagen

1. **Die Crate kostet das Vier- bis Dreizehnfache an Platz, Speicher und
   Zeit** — für 14 Anfragen je Sekunde, die der Mindestumfang kennt
   (5 034 ms / 20 000 = 251 µs je Anfrage gegen 18 µs selbst gebaut).
   Für ein Gerät mit 462 MB und einen Agenten, der im Leerlauf unter 1 %
   bleiben soll, ist das der falsche Preis.
2. **Sie bringt eine Laufzeit mit, die das Gateway nicht hat.** `tokio` mit
   `rt-multi-thread` heißt zehn Fäden statt einem — in einem Prozess, der
   heute synchron und ohne Laufzeit läuft. Diese Entscheidung wäre nicht
   rückholbar, ohne den Agenten umzubauen.
3. **Die 2 MB sind nicht das Problem, die 13 Fäden Zeit schon.** Ein Paket
   auf einer 18-GB-Karte kostet nichts; 4,7 Sekunden zusätzlich auf 20 000
   Nachrichten merkt man, wenn eine IDE streamt und jeder `session/update`
   durch denselben Weg geht.
4. **Die neuere Fassung ist nicht besser:** 5.0.0 ist schneller als 3.6.0
   in der Größe (2,07 gegen 2,19 MB), aber langsamer im Durchsatz
   (5 034 gegen 3 794 ms). Beide bleiben weit über dem eigenen Zeilenrahmen.

## Entscheidung

**Der Mindestumfang wird selbst gebaut, mit `serde_json`.** Das ist die
Variante, die DESIGN Punkt 7 schon als Rückfall nennt. Begründung: gleiche
Arbeit, 3,5 % der Laufzeit, ein Faden, keine Laufzeit im Gateway. Der
Preis ist eigener Code für Zeilenrahmen, `id`-Verwaltung und Dispatch —
gemessen an den 20 000 Zeilen dieses Messaufbaus ist das ein gutes Geschäft.

Die Crate bleibt als **Referenz** nützlich: Ihre Schema-Typen
(`InitializeRequest`, `InitializeResponse`, `AgentCapabilities`, …) sind die
Feldnamen, gegen die die eigenen Typen geprüft werden — ohne sie als
Abhängigkeit ins Gateway zu holen.

## Grenzen der Messung (ehrlich)

- **Nur `initialize`** — der teuerste Teil von ACP ist `session/prompt` mit
  Streaming. Die Crate könnte dort relativ besser werden; gemessen ist es
  nicht. Für den Kern (Zeilenrahmen, JSON-RPC, Dispatch) ist das Ergebnis
  eindeutig.
- **Sandbox statt Pi.** Beide Seiten laufen auf derselben aarch64-Umgebung,
  der Vergleich ist also fair; die absoluten Zahlen auf dem Pi sind langsamer.
- **Die Crate ist nicht falsch gebaut** — sie macht mehr (v1 und v2,
  Proxy-Rolle, Prozess-Transport, Schema-Validierung). Nur: Chimera braucht
  diesen Umfang nicht, und sein Preis ist an dieser Stelle zu hoch.
