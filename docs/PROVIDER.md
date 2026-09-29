# Sprachmodell-Anbindung

Wie Anthropic, Ollama und weitere Anbieter in Chimera zusammenkommen —
als Hybrid aus OpenMinis' Anbieterschicht und openclawgotchis
Werkzeugschleife.

Stand: 2026-09-29. Entwurf.

---

## 1. Warum ein Hybrid

Die beiden Quellen sind an verschiedenen Enden stark:

| | openclawgotchi | OpenMinis |
|---|---|---|
| Anbieter | zwei, fest verdrahtet | zehn, als Schicht gebaut |
| Anthropic | CLI als Unterprozess | **Abo-Anmeldung über OAuth** |
| Werkzeuge | reich, mit echter Absicherung | reich, mit Vorprüfung |
| Schleifenschutz | keiner | vorhanden |
| Zielumgebung | Linux, Python | iOS/Android, Swift/Kotlin |

Chimera nimmt **Gotchis Werkzeugschleife** (sie ist für Linux gebaut und
hat eine ernstzunehmende Sicherheitsschicht) und **OpenMinis'
Anbieterschicht** (sie trägt mehr als zwei Anbieter und kann
Abo-Anmeldung).

Weil OpenMinis GPL-3 ist, wird dessen Teil **nachgebaut, nicht
übernommen** (`docs/HERKUNFT.md` §0).

---

## 2. Aufbau

    Agent-Schleife  (aus openclawgotchi, angepasst)
      │  ├─ Werkzeuge + Sicherheitsschicht   ← Gotchi, unverändert
      │  ├─ Vorprüfung + JSON-Reparatur      ← OpenMinis-Muster
      │  ├─ Schleifenerkennung               ← OpenMinis-Muster
      │  └─ Kontextschwellen                 ← OpenMinis-Muster
      ▼
    Aufgaben → Gruppen           ← OpenMinis-Muster, Regel 5h
      gespraech      → [ abo/sonnet-5, ollama/qwen ]
      mood_erfindung → [ ollama/qwen, abo/haiku ]
      umgebung       → [ ollama/qwen ]
      │
      ▼
    Anbieter-Registry            ← OpenMinis-Muster, Regel 5a
      ├─ AnthropicOAuth    Abo-Anmeldung, Kennung zur Laufzeit (5b)
      ├─ AnthropicKey      API-Schlüssel
      ├─ Ollama            eigenes Netz, wenn vorhanden (5c)
      ├─ LiteLLM           alles Weitere
      └─ MCP-Werkzeuge     fremde Werkzeugquellen (§4)

---

## 3. Die Anbieterschicht

### Architekturregel 5h — Kein Anbieter wird vorausgesetzt

Nicht jeder hat einen Rechner mit Ollama im Haus. Ein Entwurf, der das
stillschweigend annimmt, schließt die Hälfte der Interessenten aus — und
widerspricht dem Zweck des Projekts, Hürden zu senken (Regel 6c).

Deshalb gilt: **Chimera läuft mit dem, was da ist.** Ollama, wenn
vorhanden. Ein Abo, wenn eines eingerichtet ist. Ein API-Schlüssel, wenn
sonst nichts. Ist gar nichts eingerichtet, sagt das Gerät das — und
bleibt ansonsten benutzbar (Gesicht, Mood-Stufen 1 und 2, Taste).

### Aufgaben statt fester Zuordnung

Ein Gerät wie Chimera braucht Modelle für sehr unterschiedliche Dinge.
Ein einziges Modell für alles ist entweder zu teuer oder zu schwach:

| Aufgabe | Ansprüche |
|---|---|
| **Gespräch** | Werkzeuge, guter Ausdruck, Kontext — das teure Modell |
| **Mood-Erfindung** | Struktur einhalten, kein Weltwissen — klein genügt |
| **Deutung der Umgebung** | knapp, häufig, unkritisch — klein genügt |
| **Zusammenfassen** | läuft im Hintergrund — klein genügt |
| **Titel, Aufräumen** | trivial — das billigste, was greifbar ist |

Der Nutzer ordnet **je Aufgabe** zu, nicht global:

    gespraech        = anthropic-abo / sonnet-5
    mood_erfindung   = ollama / qwen-3.8:27B_K_M
    umgebung         = ollama / qwen-3.8:27B_K_M
    zusammenfassen   = anthropic-abo / haiku
    titel            = (wie zusammenfassen)

Das ist das Muster, das OpenMinis mit seinen Modellgruppen vormacht:
Modelle werden nicht einmal global gewählt, sondern **für die Arbeit, die
sie tun sollen** — dort für Sprache, Bilderzeugung und Bildauswertung,
hier für Gespräch, Ausdruck und Hintergrundarbeit.

### Gruppen mit Rückfall

Eine Aufgabe zeigt nicht auf ein Modell, sondern auf eine **Gruppe** mit
geordneten Mitgliedern. Fällt das erste aus, greift das nächste:

    mood_erfindung → [ ollama/qwen-3.8, anthropic-abo/haiku ]

Damit löst sich das Ollama-Problem von selbst: Wer einen Server hat, trägt
ihn vorn ein und zahlt nichts. Wer keinen hat, lässt den Eintrag weg und
es läuft über das Abo — dieselbe Konfiguration, ein Eintrag weniger.

Zwei Strategien genügen:

- **Rückfall** (Voreinstellung): der Reihe nach, bis eines antwortet
- **Verteilen**: abwechselnd, wenn mehrere gleichwertig sind

### Automatische Einrichtung, überschreibbar

Beim ersten Lauf sucht der Installer, was erreichbar ist:

1. **Ollama im eigenen Netz** — bekannte Adressen und Port 11434 abfragen;
   antwortet etwas, werden die vorhandenen Modelle aufgelistet
2. **Zugangsdaten in der Umgebung** — gesetzte Schlüssel erkennen
3. **Bestehende Abo-Anmeldung**

Daraus entsteht ein **Vorschlag**, kein Zwang: Gefundene Anbieter werden
den Aufgaben nach Kosten zugeordnet — kostenlos für Hintergrundarbeit,
bezahlt fürs Gespräch. Der Nutzer sieht die Zuordnung und kann jede Zeile
ändern.

**Nichts wird stillschweigend eingerichtet** (Regel 10g). Was gefunden
wurde, steht im Protokoll; was vermutet wurde, wird als Vermutung benannt.

### Gemeinsame Schnittstelle

Gotchis `LLMConnector` (51 Zeilen) ist die Grundlage — sie hat bereits
`call()`, `is_available()` und getrennte Fehlerarten. Ergänzt wird:

| Feld | wofür |
|---|---|
| `name`, `priority` | Auswahl und Rückfallreihenfolge |
| `supports_tools` | nicht jeder Anbieter kann Werkzeugaufrufe |
| `context_window` | **Kontextschwellen gegen das bedienende Modell** |
| `supports_streaming` | für die Sprachausgabe: früher anfangen zu sprechen |
| `cost_class` | `free` / `metered` / `subscription` — steuert die Voreinstellung |

`cost_class` ist der Grund, weshalb die automatische Zuordnung ohne
Nachfragen sinnvolle Vorschläge macht: Was nichts kostet, bekommt die
häufigen Aufgaben.

### Anthropic mit Abo-Anmeldung

**Der eigene Beitrag an OpenMinis wird hier mit übernommen** — PR #407,
„resolve the claude-cli fingerprint at runtime". Er ist nicht Beiwerk,
sondern die Voraussetzung dafür, dass die Abo-Anmeldung auf Dauer
funktioniert.

Der Kern: Anthropic sperrt neue Modelle hinter einer **Mindestversion des
CLI-Clients** und prüft das über die Client-Kennung. Ist diese Kennung
fest einkompiliert, veraltet sie — und ein Modell, das eigentlich
verfügbar wäre, wird mit `claude_code_version_too_old` abgelehnt. In
OpenMinis stand dort eine feste Zeichenkette; genau das hat Opus 5.5
blockiert.

Der Fix ermittelt die Kennung **zur Laufzeit** aus der installierten CLI,
mit gepflegtem Rückfallwert und Zwischenspeicher. Für Chimera gilt das
unverändert (Regel 5b) — auf einem Gerät, das monatelang durchläuft, ist
eine veraltende Kennung keine theoretische Sorge, sondern eine Frage der
Zeit.

Ergänzung gegenüber dem PR: Auf einem Pi Zero kostet das Ermitteln
spürbar, also **einmal beim Prozessstart** und danach aus dem
Zwischenspeicher — nicht bei jedem Aufruf.

Das übrige Muster aus OpenMinis, nachgebaut:

1. **Anmeldung** einmalig, Zugangs- und Auffrischungsmarke werden abgelegt
2. **Auffrischen** vor Ablauf, nicht erst bei Ablehnung
3. **Ein Koordinator** dafür — laufen mehrere Anfragen gleichzeitig, darf
   nur eine auffrischen, sonst entwerten sie sich gegenseitig
4. **Client-Kennung zur Laufzeit** ermitteln (Regel 5b)

Punkt 4 ist die Lehre aus dem eigenen PR an OpenMinis: Eine fest
einkompilierte Versionskennung veraltet, und Anthropic sperrt neue Modelle
hinter einer Mindestversion. Auf einem Gerät, das monatelang durchläuft,
ist das keine theoretische Sorge.

Ergänzung für Chimera: Der ermittelte Wert wird **zwischengespeichert und
einmal beim Prozessstart aufgefrischt**, nicht bei jedem Aufruf — auf
einem Pi Zero kostet das spürbar.

### Ollama — wenn vorhanden

Eigener Connector, kein Sonderfall von LiteLLM (Regel 5c). Sonst lässt
sich nicht unterscheiden, ob der Server weg ist oder ein Schlüssel fehlt.

**Aber keine Voraussetzung** (Regel 5h). Fehlt er, meldet sich der
Connector als nicht verfügbar, die Gruppe fällt auf ihr nächstes Mitglied
zurück, und nichts weiter passiert.

Aus dem eigenen Fork übernommen (Ideen, nicht Code):

- Modelle zur Laufzeit auflisten und umschalten, ohne SSH
- Auswahl überlebt Neustarts, mit Vorrang vor der Voreinstellung
- **Platzhalter-Adresse wird als „nicht gesetzt" erkannt** und gemeldet,
  statt in einen Verbindungsfehler zu laufen

### Ausfall

Alle Anbieter liegen außerhalb des Geräts (Regel 5). Fällt das Netz aus:

- Mood-Stufen 1 und 2 laufen weiter — das Gerät behält ein Gesicht
- Der Zustand wird **angezeigt**, nicht verschwiegen
- Werkzeuge, die nichts vom Modell brauchen, bleiben benutzbar

---

## 4. MCP

Chimera soll fremde Werkzeugquellen einbinden können. Aktueller Stand
(geprüft 29.09.2026): Spezifikation **2026-07-28**, Python-Bibliothek
**2.2.0** (ab Python 3.10 — Trixie hat 3.13, passt).

### Architekturregel 5f — Fremde Werkzeuge sind nicht vertrauenswürdig

Ein MCP-Server ist fremder Code mit eigenen Werkzeugen. Deshalb:

- **Dieselbe Vorprüfung** wie für eigene Werkzeuge (§2), kein Freifahrtschein
- **Dieselbe Schleifenerkennung** — ein fremdes Werkzeug kann genauso
  im Kreis laufen
- **Dieselbe Protokollierung** (Regel 10e)
- Werkzeuge werden **benannt nach Herkunft** (`server.werkzeug`), damit
  Namenskollisionen nicht stillschweigend das falsche Werkzeug aufrufen
- Ein Server, der nicht antwortet, wird **übersprungen**, nicht abgewartet
  — sonst hängt die Agent-Schleife an einem fremden Prozess

Anbindung über die Standardwege der Bibliothek (Unterprozess oder HTTP).
Auf einem Pi Zero ist jeder zusätzliche Dauerprozess Speicher — MCP-Server
werden deshalb **bei Bedarf gestartet**, nicht im Voraus.

---

## 5. Audio als eigener Prozess

### Architekturregel 5g — Audio läuft getrennt, aber schlank

Sprachein- und -ausgabe bekommen einen **eigenen Prozess**, nicht nur
einen Faden. Drei Gründe:

1. **Der Renderer darf nicht warten.** Python hat eine globale Sperre;
   ein Faden, der in der Spracherkennung rechnet, hält den Renderer auf.
   Bei 15 Bildern je Sekunde sieht man das sofort.
2. **Abstürze bleiben lokal.** Audio-Bibliotheken auf ARM sind nicht
   immer stabil. Ein Absturz darf das Gesicht nicht mitnehmen.
3. **Speicher lässt sich freigeben.** Ein eigener Prozess kann beendet
   werden, wenn längere Zeit nicht gesprochen wird — bei 512 MB zählt das.

**Schlank heißt:** Der Prozess macht Aufnahme, Erkennung, Synthese und
Wiedergabe — sonst nichts. Kein Agent, keine Werkzeuge, kein Netz außer
dem, was die Modelle brauchen (und die laufen lokal).

Verständigung über **geteiltes Gedächtnis** für den Pegel (der Renderer
liest ihn bei jedem Bild, §4.1) und eine Warteschlange für alles andere.
Genau dafür hat Noisy `noisy_shm.py` gebaut, samt dem dokumentierten
Kniff um den `resource_tracker` — diese Erfahrung wird übernommen.

    Hauptprozess                  Audio-Prozess
    ├─ Agent                      ├─ Aufnahme
    ├─ Renderer  ◄── Pegel ────── ├─ VAD, Wake-Word
    ├─ Telegram      (SHM)        ├─ Erkennung
    └─ Anzeige   ──── Text ─────► └─ Synthese, Wiedergabe
                     (Queue)

---

## 6. Reihenfolge

Fügt sich in den Hybrid-Plan ein:

| Stufe | was |
|---|---|
| H1 | Registry, Ollama, Anthropic mit Schlüssel |
| H1a | Anthropic mit Abo-Anmeldung, Kennung zur Laufzeit |
| H2 | Vorprüfung, Schleifenerkennung, Kontextschwellen |
| H4a | MCP-Anbindung mit derselben Absicherung |
| H6 | Audio-Prozess |

H1a nach H1, weil ein Anbieter mit Schlüssel schneller läuft und die
Registry zuerst stehen muss. H4a nach Telegram, weil MCP ohne
Bedienschnittstelle schwer zu prüfen ist.

---

## 7. Offen

- Ob Anthropics Abo-Anmeldung auf einem Gerät ohne Browser praktikabel
  ist, muss geprüft werden — möglicherweise braucht die Erstanmeldung
  einen zweiten Rechner.
- Die Bibliothek verlangt Python 3.10; Trixie liefert 3.13. Geprüft ist
  die Verfügbarkeit, nicht das Zusammenspiel.
- Wie viel Speicher ein MCP-Server im Betrieb braucht, ist ungemessen.
