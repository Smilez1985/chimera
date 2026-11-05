# Chimera — Roadmap

Was noch fehlt, nach Priorität. Entscheidungen und Begründungen stehen in
`docs/DESIGN.md`, nicht hier. **Erledigtes steht ausschließlich im
`CHANGELOG.md`** — hier steht nur, was aussteht; ein Haken gibt es deshalb
nicht mehr.

Stand: 2026-11-04. Pre-Alpha.

---

## Phase 0 — Blaupause ✅ (läuft)

- [ ] Hardware-Revision der vorhandenen Whisplay prüfen (**V2?**)
- [ ] `uname -r`, `/lib/modules/$(uname -r)/build`, `modinfo snd-soc-wm8960`
      auf dem Zielgerät notieren (Checkliste in `docs/HARDWARE.md`, Abschnitt „Vor dem ersten Start prüfen")

---

## Phase Installer — Idempotenz, Abkopplung, Anzeige beim Update

Vorgaben smilez (2.11.): Der Installer fasst **nur an, was fehlt oder wegen
einer neuen Version aktualisiert werden muss**; er läuft nie in der SSH-Sitzung;
zram wird nicht angefasst, wenn es läuft.

- [ ] **Platzpruefung vor dem Snapshot:** Statt fester 100 MB die **Groesse der
      zu sichernden Dateien** plus Reserve pruefen (Summe steht vor dem
      Kopieren fest, DESIGN-Regel „Neustart mit Fortsetzung"). Die 100 MB
      bleiben Untergrenze.
- [ ] **Obergrenze für `numpy` (und Pillow) entscheiden.** `requirements.txt`
      verlangt `numpy>=1.26` — ohne Obergrenze holt pip die jeweils neueste
      Fassung. Im Testvenv stand deshalb einmal `numpy 2.5.4` statt `1.26.4`.
      Das ist eine Frage der *Anforderung*, nicht des pip-Aufrufs: `pydep_ensure`
      installiert seit 4.11. ohne `--upgrade` (nur die nicht erfüllten
      Anforderungen), und für eine fehlende Anforderung holt pip so oder so die
      neueste. Zu entscheiden: Obergrenze (`numpy>=1.26,<3`) setzen oder die
      Abweichung bewusst zulassen — gemessen ist bisher nur 1.26.x am Pi.
- [ ] **UV für `requirements.txt` — gebaut in Modul 50, Messung am Gerät
      fehlt noch.** Eigenes Werkzeug-venv `tools/uv` (nur anlegen, wenn es
      fehlt), uv über pip installiert (Prüfsummen von PyPI), `uv pip install
      --python <venv>` mit `--find-links`, nur wenn es vorgeladene Wheels
      gibt; harte Zeitgrenze `CHIMERA_UV_FRIST` (600 s, `timeout`), Schalter
      `CHIMERA_UV=aus`, Rückfall auf pip in derselben Warte-Schleife. Tests:
      `installer/tests/test-uv.sh` 20 ok (Anlegen nur wenn es fehlt, venv
      nicht anlegbar → pip, uv scheitert → pip, auch pip scheitert → Befund,
      Zeitgrenze greift, `--find-links` nur bei vorhandenem Verzeichnis);
      Gegenproben rot (Zeitgrenze ausgebaut → 2 rot, Rückfall ausgebaut →
      3 rot). **Am Pi gemessen (5.11., kalt, je eigener Cache, dieselben
      Pakete Pillow 13.0.0 + numpy 2.5.4): pip 41 s, uv 10 s — der Gewinn
      ist belegt.** uv liegt dort als 0.13.7 (aarch64) im Werkzeug-venv.
      **Offen: `uv pip compile` als Lock** (noch nicht eingebaut) und die
      Frage, ob Modul 50 auch die Obergrenzen-Frage über den Lock löst.
      **Gemessen (5.11., uv 0.13.7, aarch64):** `uv pip download` gibt es
      nicht („unrecognized subcommand"), und `uv pip install --dry-run` löst
      zwar auf, lädt die Wheels aber **nicht** (eigener Cache danach 1,3 MB,
      keine `.whl`). Für das Vorab-Laden bleibt es deshalb bei `pip download`
      — nur pip kann holen, ohne zu installieren. `uv pip compile` (Lock) ist
      noch nicht eingebaut.

- [ ] **Vorab-Laden im Hintergrund** (DESIGN, Abschnitt „Warte-Schleife und
      Vorab-Laden"): **gebaut und am Gerät belegt** (`installer/lib/vorab.sh`,
      `installer/chimera-prefetch` als eigene transiente Unit; Marken
      `.done`/`.fehler`, halbe Downloads landen in `wheels.teil` und werden
      verworfen; `--find-links` in Modul 50; Abschalter
      `CHIMERA_PREFETCH_RAD=0`; alte Fehlmarken werden zu Beginn eines Laufs
      ins Protokoll geholt, damit Mojo sie findet; geladen wird nur, was
      fehlt; fehlendes `pip` wird über `network_apt` geholt). `test-vorab.sh`
      46 ok.
      Gemessen am Pi (5.11., `4f06a3c`): pip-Wheels 16 s für 22 MB (wirkt,
      überlappt), apt-debs 25 s für **null** Pakete — apt ist deshalb wieder
      aus der Liste, es hat in Modul 20 seinen einzigen Weg.
      **Offen:** der Nutzen auf einer **Erstinstallation** (dort liegt der
      Netzanteil bei 1,5–2 min). Bis dahin gilt der Gewinn als plausibel,
      nicht als gemessen.
- [ ] **Weitere Vorab-Objekte** (Whisplay-Klon 13 MB/3 s, `rust-<commit>`
      ~2 MB/1 s): **zurückgestellt**, der Aufwand einer Marke ist größer als
      der Betrag. Wird nur wieder aufgegriffen, wenn die Erstinstallation es
      verlangt.

## Phase ACP — Chimera als Agent für Editoren und IDEs (DESIGN: Regel „ACP“)

Pflicht-Schnittstelle (smilez, 2.11.). **Entschieden: Der ACP-Server wird gebaut,
mit einer Transportschicht, damit eine IDE das Gateway ansprechen kann.**
Recherche: `docs/research/ACP.md` und `docs/research/ACP-MCP.md`. Rust im
Gateway-Workspace (Regel „Rust, wo dauernd läuft“), eigene Tür.

- [ ] **Bibliothek messen:** Crate `agent-client-protocol` 3.6.0 gegen den
      Mindestumfang mit `serde_json` (Größe des Binarys, Speicher, Laufzeit);
      danach entscheiden.
- [ ] **ACP-Kern** (`initialize`, `session/new`, `session/prompt`,
      `session/update`, `session/cancel`) gegen die Hauptsitzung, unabhängig vom
      Transport; Test gegen die Prüfwerkzeuge der Spezifikation (Seite „Testing“).
- [ ] **Transportschicht:** ein Bytestrom-Trait mit Zeilenrahmen; Transporte
      **stdio** (Vermittler `chimera-tor --acp-stdio` auf dem Rechner der IDE),
      **Unix-Socket** am Gateway, später **HTTP/WebSocket** nach dem Entwurf.
      Jeder Transport besteht denselben Kern-Test.
- [ ] **Tür am Gateway** mit Positivliste, Anmeldung und nur im LAN; Test, dass sie
      ohne Positivliste zu bleibt.
- [ ] **In einer echten IDE belegen** (Zed, JetBrains oder Android Studio) und
      klären, wie ein eigener Agent dort ohne Registry eingetragen wird (in den
      gelesenen Quellen nicht beschrieben).
- [ ] Später: Registry-Eintrag, Sitzungsliste und Modi, ein ACP-Client für
      Chimera (Chimera spricht mit anderen Agenten), Gesichter und Moods über ACP
      bauen (siehe Phase MQTT).

## Phase MQTT — Broker in Rust, verknüpft mit der Anzeige (DESIGN: Regel „MQTT“)

Vorgabe smilez (2.11.): Der MQTT-Broker ist **Rust** und mit der
**Whisplay-Steuerung** verknüpft: ein per MQTT gesendeter Aufruf löst einen
**vorgefertigten, gespeicherten Mood** sofort aus. Die StateMaschine aus
Quelle ist PaKaChi-SM (privat); sie dient als Vorbild, hier wird nachgebaut, nicht kopiert.

- [ ] **Quelle zu Ende lesen** (PaKaChi-SM, privat): StateMaschine, Nachrichten,
      Architektur; daraus ein Entwurf im DESIGN (Themen, Nachrichten,
      Zustände), der keine Namen aus dem privaten Projekt übernimmt.
- [ ] **Entscheidungen von smilez:** Themenaufbau, Anmeldung am Broker, ob auch
      Fremdgeräte (Sensoren) bedient werden, QoS, Antwortweg.
- [ ] **Speicher messen:** Ein Broker im Gateway (`MemoryMax=10M`, Pi mit 462 MB)
      gegen einen eigenen Prozess; erst die Zahl, dann die Form.
- [ ] **Broker in Rust** (MQTT 3.1.1, kleiner Umfang: verbinden, abonnieren,
      veröffentlichen), eigene Tür mit Positivliste; Härtung nach den Grundsätzen der Quelle
      (kein Platzhalter im Thema, Größengrenze, feste Namensmuster, `retain`
      verwerfen).
- [ ] **Verknüpfung mit der Anzeige:** Thema trägt einen Mood-Namen, der Broker
      ruft die Anzeige über das Gateway (`Face.set_by_name`); unbekannter Name
      lässt das Gesicht unverändert. Zustände der StateMaschine sind die von
      Chimera (`wartet`, `hoert`, `denkt`, `arbeitet`, `spricht`).
- [ ] **Moods bauen über MCP und ACP** (falls sinnvoll und machbar): Werkzeuge zum
      Anlegen von Gesichtern, Zubehör und Moods, mit Anmeldung und Prüfung
      (Regeln „Gesicht ist ein Paket“ und „Mood wird validiert“); abrufen über
      MQTT, **anlegen nie über ein offenes Thema**.
- [ ] **Am Pi belegen:** Mood per MQTT senden, Gesicht ändert sich; ungültiger
      Name ändert nichts; ohne Positivliste kommt nichts an.

## Phase Regelnamen — Nummern werden zu sprechenden Namen (DESIGN: Regel „Sprechende Namen“)

Alle 74 nummerierten Architekturregeln und die rund 460 Verweise darauf in
DESIGN, ROADMAP, CHANGELOG, Quelltext und Tests bekommen Namen, die sagen, worum
es geht („5n“ wird „Gateway“, „10r“ wird „Agent-Nutzer“ usw.).
Jede Umbenennung ist ein Satz Ersetzungen mit Prüfung, dass kein Verweis auf
einen alten Namen übrig bleibt.

- [ ] Die Namen für den Altbestand festlegen (eine Tabelle Nummer -> Name, von
      smilez abzunehmen), dann je Themenblock umbenennen: Anbieter und Gateway
      (5*), Anzeige (6*, 7*), Gedächtnis und Sitzung (8*), Installer (10*),
      Rest. Jeder umbenannte Eintrag verlässt die Altbestand-Liste des Tests.
- [ ] Die Verzeichnisse und Querverweise „Regel 5n“ usw. in Quelltext-Kommentaren
      folgen mit der Umbenennung.

## Phase 2 — Mischen und Variieren

**Ohne Hardware testbar.**

- [ ] `MAX_SHAPES` auf echter Hardware messen

## Phase 3 — Display und Renderer

Hardware ist vorhanden, also nicht blockiert.

- [ ] **Module `gamepi13/`** (DC25 RST27 BL19, 240×240, MADCTL 0x70,
      Pimoroni-Einschaltfolge, invertiert) und **`epd2in13b/`** (Treiber aus
      dem Gotchi-Fork, BUSY-Prüfung, Mindestabstand 120 s, reduziert+Akzent).
      Messung erst beim Kartentausch bzw. am E-Ink-Pi.
- [ ] **Dienst-Template `chimera@<typ>.service`** (ein Dienst je
      Anzeigeart, E-Paper braucht einen anderen Renderer) und
      `state/hardware.json` (erkannt, Zeit, Quelle; Soll/Ist-Abgleich für
      UPS). Bis dahin: ein `chimera.service`, Anzeige aus der Umgebung.
- [ ] **Boot-Abgleich weiter kürzen:** Schritt 40 startet Python für
      Erkennung, Profil und Ton getrennt (zusammen 4,5 s).
- [ ] **Anbieterausfall auf der LED?** Entscheiden, ob ein Gerät ohne
      Sprachmodell auch per LED warnt (`anbieter_weg`) oder nur in der
      Statuszeile — bei bewusstem Betrieb ohne Modell wäre Dauerblinken
      störend.
- [ ] **Akku in der Statuszeile** (DESIGN `docs/DESIGN.md`, Abschnitt „Renderer"), sobald die Akkuquelle
      (PiSugar / UPS HAT C) gebaut ist.
- [ ] **Audio-Prozess nutzt `chimera_mikro`** (DESIGN 5g), sobald er gebaut
      ist; bis dahin nimmt noch niemand darüber auf.
- [ ] **Teilübertragung des unteren Rands.** `panel.py` schreibt immer
      das ganze Bild. Wer nur die unteren 40 von 280 Zeilen überträgt,
      spart rund 14 % der teuersten Größe — SPI kostet 28,1 von 39,3 ms.
      Der Schalter `nur_zeile` ist vorgesehen, aber ohne Wirkung; das ist
      als bekannte Einschränkung vermerkt (Regel 10h).
- [ ] **Platz für gesichtsabhängige Einstellungen.** HATFaces' Format hat
      `[text_overlay]` je Charakter (an/aus, Stil). Solange es keine
      Gesichter gibt, ist der Haken leer — er wird in Phase 3b gefüllt.
> Das Modell dahinter steht in `DESIGN.md` als Architekturregel 7c/7d,
> die Herleitung in `../VERGLEICH-HATFACES.md`. Übernommen wurde das
> Modell, nicht der Code — dort gibt es keinen.
- [ ] **Anzeige an die Temperatur koppeln**, begründet mit der SPI-Messung

      HATFaces' Begründung trifft Chimeras eigene Zahl: *jede
      Pixeländerung ist eine SPI-Übertragung*. Wir haben gemessen, dass
      SPI 70 % kostet, aber keine Folge gezogen.

      - [ ] Drei Stufen (`ok`, `warn`, `critical`), Schwellen **für den
            Pi Zero 2 W selbst messen** — HATFaces' 62/67/75 °C gelten
            für den RK3566
      - [ ] Bei `warn` weniger Fläche neu zeichnen, bei `critical` nur
            noch die Statuszeile
      - [ ] Stille Degradation: Der Agent erfährt es nicht. **Das ist eine
            Entscheidung, keine Selbstverständlichkeit** — sie steht hier,
            damit sie nicht stillschweigend anders ausfällt
      - [ ] Schließt Befund B6 ab (`docs/PRUEFUNG-H4.md`): Die
            Temperaturkopplung hat nie funktioniert, die Schwellen sind
            also nie erprobt worden

## Phase 3b — Gesichter als Pakete, die das Modell selbst anlegen darf

**Ein Gesicht reicht nicht.** Das Sprachmodell soll ein eigenes Gesicht
erfinden und **ablegen** können — nicht nur einen Ausdruck für den
Augenblick erzeugen, sondern einen Charakter, der den Neustart übersteht
und wieder aufgerufen werden kann.

Vorbild: HATFaces `docs/konzept/04_Character_Plugin_Format.md`. Dessen
Leitsatz trifft genau das, was Chimeras Mood-Schema schon tut:

> Was du als Daten ausdrücken kannst, drück nicht als Code aus.

**Warum das kein Neubau ist.** Die Teile liegen bereits vor, sie sind nur
nicht verbunden:

| vorhanden | wofür |
|---|---|
| `mood/schema.py` | Vokabular als einzige Wahrheitsquelle; `EnumField` lässt unbekannte Werte ausdrücklich durch (»Was gezeichnet werden kann, darf auch erfunden werden«) |
| `mood/validate.py` | prüft Erfundenes gegen die Grenzen (Regel 2) |
| `mood/registry.py` | hält Moods, vergibt Nummern, `add(origin=…)`, `prune()`, `save()`/`load()` atomar |
| `agent/skills.py` | **das Discovery-Muster ist schon gebaut**: Verzeichnis-Scan, Kopfteil mit Metadaten, `Requires`-Prüfung, Unbrauchbares wird übersprungen statt zu stürzen |
| `mood/draw.py` | freie Formen für Werte, die kein fertiges Bauteil haben |

Was fehlt, ist die Schicht darüber: ein **Gesicht** ist mehr als ein Mood.
Es ist ein Bündel aus Moods, Vorgaben, Namen und Herkunft.

- [ ] **Format festlegen — und zwar JSON, nicht TOML**

      HATFaces nimmt TOML mit Pydantic-Validierung. Für Chimera ist das
      die falsche Wahl, aus zwei Gründen, und beide sind nachprüfbar:
      Erstens schreibt hier **das Modell** die Datei, und Modelle erzeugen
      zuverlässig JSON — das ist das Format, in dem sie ohnehin antworten.
      Zweitens ist `json` in der Standardbibliothek; Pydantic wäre eine
      Abhängigkeit auf 512 MB, und `skills.py` hat aus genau diesem Grund
      schon auf einen YAML-Leser verzichtet.
      Validiert wird mit `mood/validate.py`, das es bereits gibt.

- [ ] **Verzeichnisaufbau**, nach dem Muster von `skills.py`

      ```
      faces/
        <name>/
          face.json          Pflicht: Name, Herkunft, Moods, Vorgaben
          README.md          optional, vom Modell geschrieben
          assets/            optional, vorgezeichnete Teile
      ```

      Suchpfade in Vorrangfolge, wie bei den Skills:
      `$CHIMERA_FACES` → `./faces/` → `~/.config/chimera/faces/` →
      `/usr/local/share/chimera/faces/`. **Verdrängung wird protokolliert**
      — sonst rätselt man, warum die Systemfassung die eigene überschreibt.

- [ ] **Der Agent bekommt Werkzeuge dafür** (heute kann er Ausdrücke
      setzen, aber nichts ablegen)

      - [ ] `gesicht_anlegen(name, beschreibung)` — validiert, schreibt
            atomar, lädt nach
      - [ ] `gesicht_wechseln(name)`
      - [ ] `gesicht_liste()` / `gesicht_beschreiben(name)`
      - [ ] `mood_in_gesicht_legen(gesicht, name, felder)`

- [ ] **Grenzen, die das Modell nicht überschreiten darf**

      Das ist der Teil, den HATFaces nicht braucht (dort schreibt ein
      Mensch die Manifeste) und Chimera sehr wohl:

      - [ ] **Obergrenze für Anzahl und Größe.** `registry.py` hat
            `capacity` und `prune()` — das muss für Gesichter genauso
            gelten, sonst füllt ein Modell in einer Schleife die SD-Karte
      - [ ] **Nur unterhalb des Gesichterverzeichnisses schreiben.** Ein
            Name wie `../../etc/` darf nicht durchkommen; Pfadprüfung vor
            dem Schreiben, nicht danach
      - [ ] **Kein Python in einem Gesicht.** HATFaces erlaubt
            `behaviors.py` je Charakter. Hier ist das ausgeschlossen:
            Ein Modell, das ausführbaren Code ablegt, den ein Dauerdienst
            lädt, ist eine Fernausführung mit Extraschritten
            (Regeln 5f, 5j)
      - [ ] **Eingebautes ist geschützt.** `Entry.protected` gibt es
            schon; ein generiertes Gesicht darf ein mitgeliefertes nicht
            überschreiben
      - [ ] **Herkunft wird festgehalten** (`origin`: mitgeliefert,
            generiert, von Hand). Ohne das ist später nicht
            unterscheidbar, was das Modell erfunden hat

- [ ] **Was NICHT übernommen wird** — mit Grund, damit es nicht später
      „vergessen" heißt:

      - Fünf Suchpfade wie bei HATFaces → vier genügen, der fünfte war für
        Distributionspakete gedacht, die es hier nicht gibt
      - `[compatibility]`-Abschnitt mit SemVer-Bereichen → Chimera hat ein
        Panel und eine Auflösung; ein Gesicht, das 320×240 verlangt, ist
        ein Problem, das es hier nicht gibt
      - Live-Nachladen ohne Neustart → nett, aber der Renderer hält den
        Bildspeicher (Regel 7). Nachladen heißt hier: nächster Bildlauf
        liest neu, kein Austausch im laufenden Zeichnen

> **Der Weg zum fertigen Gerät steht in `docs/HYBRID-PLAN.md`** (Stufen
> H1–H8). Was von openclawgotchi und OpenMinis übernommen wird und was
> nicht, steht in `docs/HERKUNFT.md`. Die Phasen hier bleiben als
> Feingliederung.

## Phase 4 — Agent-Kopplung

- [ ] openclawgotchi-Basis übernehmen (Skills, Memory, LLM, Telegram) —
      Auswahl in `docs/HERKUNFT.md`, Abschnitt „Übernehmen", **Sicherheitsschicht des
      `execute_bash` unverändert mitnehmen**
- [ ] Alten Display-Layer entfernen (Architekturregel 7)
- [ ] Renderer als Dauer-Thread, Zustandsübergabe über Shared Memory
- [ ] `skills/mood/SKILL.md` (Architekturregel 8)
- [ ] Agent-Zustände auf Moods abbilden (denkt, spricht, hört zu)

### E-Ink-Ausgabe auf Whisplay umbiegen

Die Steuerbefehle bleiben, nur das Ziel wechselt (`docs/DESIGN.md`, Abschnitt „Was von openclawgotchi bleibt").

- [ ] `FACE:` auf Mood-Datensätze statt Emoticons legen; generierte Moods
      zulassen
- [ ] `DISPLAY:` auf die Statuszeile legen
- [ ] `SAY:` auf Sprechblase **und** Sprachausgabe legen
- [ ] Ghosting-Behandlung und Vollbild-Auffrischung ersatzlos entfernen
- [ ] Die 10 alten Emoticon-Moods als Startbestand abbilden, damit
      bestehende Skills unverändert laufen

## Phase 4b — Provider-Schicht

Kann parallel zu Phase 4 laufen; berührt den Renderer nicht.

- [ ] Auffrischen der Abo-Marke vor Ablauf, mit Koordinator
- [ ] Werkzeugschleife aus openclawgotchi anschließen
- [ ] **Anthropic-Connector mit Abo-Anmeldung** nach dem Muster von
      OpenMinis PR #407 (Architekturregel 5b)
- [ ] Client-Kennung **zur Laufzeit ermitteln**, nie einkompilieren;
      Rückfallwert und Cache, Auffrischung bei Prozessstart
- [ ] Test: veraltete Kennung muss erkannt werden (mit Gegenprobe)
- [ ] **Ollama als eigenständiger Connector** (Architekturregel 5c), nicht
      als LiteLLM-Sonderfall
- [ ] LiteLLM-Connector aus openclawgotchi übernehmen (weitere Anbieter)
- [ ] Aufgabenzuordnung konfigurierbar: Gespräch → Anthropic,
      Mood-Erfindung und Zusammenfassen → Ollama
- [ ] Aus dem eigenen Fork übernehmen (Ideen, nicht Code —
      `docs/DESIGN.md`, „Sprachmodelle: Provider-Schicht"): `/model`-Befehl zum Umschalten im Chat,
      **persistente Modellwahl** über Neustarts, Platzhalter-Adresse als
      „nicht gesetzt" behandeln statt Verbindungsfehler, Installer fragt
      die Ollama-Adresse ab
- [ ] Fehlender Schlüssel ⇒ Connector meldet sich als nicht verfügbar,
      kein Startabbruch
- [ ] `.env.example` mit Platzhaltern für alle Anbieter

## Phase 4d — Gateway in Rust (DESIGN „Gateway: der eine Weg nach draußen", Regel 14)

Löst `provider/` und `bot/` im Dienst ab. Jede Stufe für sich lauffähig.

- [ ] **Ein Kanal, eine Hauptsitzung** (DESIGN 5s) — Sitzungs-Socket, Ereignisstrom, Telegram-Tür im Gateway, Umleitung auf `haupt` und Sitzungsablage mit Wechsel (`wechseln`, `sitzungen`, `lesen`) laufen. Offen: Auslöser für den Wechsel (Wächter, 8d), Python-Telegram im Dienst entfernen, Klingel (Briefkasten, 5o) als Tür mit `ref`.
- [ ] **Web-Oberfläche als Modul-Plattform** (5m), **vor** den weiteren
      Anbietern, damit alles per Oberfläche einstellbar ist.
      Fertig und im Changelog: Rahmen (Anmeldung mit Passwort-Hash, Menü,
      Router, Modul-Erkennung mit eingebauten und nachgelegten Modulen), die
      Module Chat, Status und Ollama, die Rechteliste mit `--module-neu` und
      `--module-pruefen`, das Web-Passwort aus dem Installer und die
      LAN-Begrenzung der Oberfläche. Offen:
      - **Modul-Registrierung (5v):** Freigabe mit Prüfsumme und Passwort,
        Sandbox-iframe mit Brücke, Weitergabe an den Modul-Socket.
      - **Datenschicht im Gateway:** Katalog füllen (Abfrage + `fehlt_seit`),
        Neustart des Gateways nach Schlüsseländerung, Umzug von
        Telegram-Token und Passwort-Hash aus der `.env` nach
        `config/geheim/` (`migrate_from`), Rechte
        `anbieter-lesen`/`anbieter-schreiben`.
      - **Reihenfolge** (Wahl über Anbieter hinweg).
      - **Einstellungen:** Passwort ändern, Werksreset mit Satz am Display,
        Telegram, Sprache.
      - **Anbieter Anthropic** (Schlüssel, danach Abo).
      - **Anzeigespiegel (Waveshare)** — braucht zuerst ein fertiges Bild im
        Shared Memory vom Renderer, eigener Entwurf.
      - **Ein Zusatzmodul** erscheint ohne Änderung an Rahmen oder Gateway —
        belegt ist es (Test mit Gegenprobe); offen bleibt der Lauf am Pi
        (Anmeldung, Chat gegen die echte Sitzung).
- [ ] **Status-Sonden ergänzen:** CPU-Zeit und Speicher je Dienst (`cpu.stat` je Cgroup, RSS aus `/proc/<pid>`), Netz (Durchsatz), Verlauf der Werte.
- [ ] **Weitere Anbieter im Gateway:** Anthropic-Schlüssel, Anthropic-Abo
      nach PR #407 (Regel 5b, Fassung für das Gateway: Registry-Version,
      nur vorwärts, ein Header-Satz für Token- und Chat-Weg). Zeitgrenzen
      (5 s Verbindung / 300 s Aufruf) gelten schon für Ollama. Dazu 5q: Cache-Marken je Adapter, `Reply.cache`,
      Byte-Test mit Gegenprobe; Anthropic-TTL am Gerät nachmessen.
- [ ] **Sperre fuer den Agent-Dienst:** `.env` für ihn unlesbar (Regel 5l,
      `root:chimera-tor 640`) und `IPAddressDeny=any`, mit Test „Dienst
      kommt nicht ins LAN, Gateway-Socket bleibt erreichbar“. Erst wenn
      auch die Claude-Zugänge im Gateway laufen, sonst verliert der
      Python-Dienst seine Anbieter. (Am Pi gemessen: mit dem Profil
      erreicht der Dienst Ollama über den Socket, das LAN nicht.)
- [ ] **Ollama im Gateway ganz abfragen** (5n, 5k): `/api/ps` (geladen,
      VRAM, Ablauf), die Zeiten aus der Antwort (`load_duration`,
      `total_duration`, `eval_duration`), `keep_alive` und Vorladen des
      gewählten Modells; Anzeige „geladen / kalt“ und letzte Antwortzeit je
      Modell im Ollama-Modul. Der Dienst fragt dafür das Gateway, nicht den
      Server.
- [ ] **Modellwahl durch den Nutzer** (5h): bis zur Reihenfolge-Seite
      gilt `OLLAMA_MODEL`; das Vorschlagen des größten Modells
      (`provider/setup.py`, `_target_for`) wird durch „erstes Modell mit
      `tools`“ ersetzt. Ein Modell, das nicht ausgewählt ist, wird nie
      geladen.
- [ ] **Der Dienst verliert sein Netz** (5n): Er ruft heute Ollama und
      Anthropic noch selbst über `urllib` auf (`IPAddressDeny` ist leer);
      der Weg über das Gateway ist nur ein zusätzlicher Pfad, `discover()`
      scannt selbst. Reihenfolge: Anthropic ins Gateway, dann Sperre mit
      Test, dann `provider/` und `bot/telegram.py` entfernen.
- [ ] **Installer: Sitzungs-Socket nach einem Lauf:** `chimera-sitzung.socket`
      blieb nach einem Lauf von Schritt 99 inaktiv („Socket service already
      active, refusing“), der Dienst lief ohne Sitzungs-Socket weiter. Der
      Nachweis von Schritt 99 muss den Zustand beider Sockets prüfen, nicht
      nur den des Gateway-Sockets.
- [ ] **Websuche** (5r): zuerst Anthropic serverseitig, dann OpenRouter,
      dann Suchquellen mit Nutzer-Schlüssel (Ollama Cloud, Tavily, Exa,
      SearXNG; Brave ohne Platten-Cache; ddgs nur Opt-in).
- [ ] **Netzsuche** (5k): Selbsteintrag steht; offen: Telegram `/suche`,
      Knopf „Jetzt suchen“ im Ollama-Modul, Installer Schritt 50.
- [ ] **Speicher am Pi** (10q): `MemoryMax=` wirkt nicht
      (`cgroup_disable=memory`); der Installer meldet das, und das Gateway
      begrenzt sich selbst (`VmRSS` prüfen, bei Überschreiten sauber
      beenden). Installermodul `26-boot` mit Sicherung und `--dry-run`:
      CMA 64 auf 16 MB gemessen: +21 MB verfügbar (Modul `26-boot`, Phase Mojo);
      `cgroup_enable=memory` bleibt aus (kostet etwa 9 MB, bringt keinen RAM).
      Journal im RAM begrenzen.
- [ ] **Gedächtnis-Verdichtung in Blöcken** (8c): lange Verläufe an
      Nachrichtengrenzen teilen, je Block zusammenfassen, zusammenführen; feste
      Briefstruktur (Ziel, Kontext, Stand, nächste Schritte, offene Fragen);
      auch für die Übergabe beim Wechsel der Hauptsitzung (5s).
- [ ] **DeepSeek** als Anbietermodul über die API (OpenAI-kompatibel). Eine
      Browser-Brücke zur Weboberfläche ist nicht beschlossen: Sie bräuchte
      einen Browser auf einem anderen Rechner im LAN (der Pi hat 462 MB RAM)
      und liegt in einem Bereich der Nutzungsbedingungen, der nicht
      eindeutig ist.
- [ ] **`wahl.json`** mit bevorzugter Liste (5h). Telegram im Gateway mit
      `/model` und `/suche`.
- [ ] **CLI** als Socket-Client, ohne eigene Anzeige.
- [ ] HTTPS als Opt-in: Reverse-Proxy dokumentieren, selbstsigniertes
      Zertifikat für alle ohne Proxy.
- [ ] Rückbau-Gegenstücke (10l) und `migrate_from()` (`.env` von
      root:chimera auf root:chimera-tor).
- [ ] Danach `provider/` und `bot/telegram.py` aus dem Dienst entfernen.
- [ ] Später, eigener Entwurf: Renderer und Paneltreiber in Rust (Regel 14,
      Stufe 2).

## Phase Mojo — Dienste starten zuverlässig und melden Fehler laut (DESIGN: Regel „Mojo“)

Recherche: `docs/research/MOJO.md`. Rust im Gateway (Regel 14), Installer
daneben. Jede Stufe für sich lauffähig, am Pi mit einer echten Störung belegt.

- [ ] **`chimera-tor --mojo [--miracle] [--json]`:** Befund, Schwere, Stufe,
      `impl Pruefung` plus Zeile in `pruefungen()`, Nachprüfung nach jeder
      Reparatur, `unreparierbar` bei wiederkehrendem Code, Sperre gegen zwei
      gleichzeitige Reparaturen, Schwärzung der Ausgabe, Befunddatei
      `state/mojo-letzter.json`.
- [ ] **Erste Prüfungen:** Dienste, beide Sockets (Reparatur „Socket
      nachziehen“), Hardware-Erkennung, Protokoll auf der Karte, Speicher,
      Anbieter (Gateway, Ollama erreichbar, Modell gewählt).
- [ ] **Meldeunit und Zeitgeber:** `chimera-mojo@.service` per `OnFailure=`
      an `chimera`, `chimera-tor`, `chimera-hardware` (trennt Zwischenfehler
      von der Aufgabe), `chimera-mojo.timer` (Boot, stündlich).
- [ ] **Laut:** Journal `<3>`, Zeile auf der Karte, LED und Statuszeile (die
      LED-Schnittstelle liegt heute im Dienst; fällt der Dienst aus, muss die
      Meldeunit sie setzen), Anzeige im Status-Modul.
- [ ] **Installer:** neues Modul `27-mojo` (Units, Drop-ins, Timer), mit
      `--dry-run`, Sicherung, Manifest und Rückbau; dazu Modul `26-boot` mit dem
      CMA-Overlay (`dtoverlay=cma,cma-size=…`, Schalter `CHIMERA_CMA_MB`,
      Sicherung von `config.txt`, Neustart mit Messung davor und danach; am Pi
      gemessen +21 MB verfügbar).
- [ ] **`chimera-hardware.service`:** Verhalten bei Fehlschlag klären
      (`Restart=` bei `oneshot` messen), damit ein gescheiterter Boot-Schritt
      den Dienst nicht stumm ohne Hardware starten lässt.
- [ ] **Fehlende Python-Pakete nachladen** (Stufe 2): gebaut mit Tests und
      Gegenprobe; am Pi noch nicht mit einem echten fehlenden Paket belegt
      (Installer läuft dazu über `systemd-run`, weil die Mojo-Unit nur nach
      `state/` schreibt).
- [ ] Später: Reparaturpläne mit Prüfsumme und Klasse (mit Regel 5v),
      Reparaturen der Stufen 2 und 3 auf Wunsch über die Oberfläche, Meldung
      über Telegram.

## Phase 4e — Briefkasten, Sitzung, Gedächtnis, Root (DESIGN 5o, 5p, 8c, 8d, 10s)

Rust-Teile im selben Cargo-Workspace wie das Gateway (Regel 14).

- [ ] **Briefkasten** `chimera-post` (Rust): woa-l-Protokoll (MCP über
      HTTP), eigener Port am Gateway, Token als sha256, Quittung erst nach
      dem Turn. Kanal `briefkasten` im Dienst, gesperrt für Root und
      Konfiguration (5p).
- [ ] **Sitzungsablage in Rust** (`chimera-sitzung`): Die Ablage läuft
      bereits als Python-Modul `chimera.ablage` (`verlauf.jsonl`, Wechsel
      aktiv/alt, Archiv, Löschen nach 3 Tagen nach geprüftem Auspacken,
      Verdichtung ohne Verlust im Protokoll). Umzug nach Rust (Regel 14)
      hinter derselben Schnittstelle; Werkzeug `nachlesen` für den Agenten.
- [ ] Wächter im Sitzungsdienst. **Schwelle „schwer“ messen** und ins
      Design eintragen.
- [ ] Verdichten neu: Zusammenfassung mit Verweis, offene Punkte
      wörtlich. `_compact()` in `agent/loop.py` entfällt.
- [ ] **Gedächtnis** Tag → Monat → Jahr → `memory.md`, Quellen bleiben,
      Vollständigkeitsprüfung (Rust) gegen Marker.
- [ ] **`chimera-hand`** (Rust, root): Freigabe nur durch den Nutzer per
      Telegram-Knopf oder Web, mit Dauer, Protokoll, Bilanz.
- [ ] Rückbau-Gegenstücke (10l) für Nutzer `chimera-post`, Units, Sockets.

## Phase 4f — Persönlichkeit und Selbstentwicklung (DESIGN 8e–8h)

- [ ] `data/ich/` mit SOUL, IDENTITY, RULES, USER, TRAITS, BOOTSTRAP als
      `*.example`-Vorlagen. `SYSTEM_TEMPLATE` schrumpft auf den
      Sicherheitskern.
- [ ] `migrate_from()`: `GRUNDLAGEN.md` → `RULES.md`.
- [ ] Budgets je Datei, Überlänge = nicht laden und melden. Budgets am Pi
      messen.
- [ ] Rechte nach 8f, Git-Commit je Änderung, Scanner vor dem Schreiben.
- [ ] Freigabe für SOUL/IDENTITY per Telegram-Knopf und Web.
- [ ] Merk-Hinweis alle 10 Turns, Sichern vor dem Verdichten, Traum im
      Leerlauf, TRAITS höchstens 1 je 7 Tage, Wochenbilanz.
- [ ] Eigene Skills (Text frei, Code mit Freigabe), Curator archiviert.
- [ ] Index `rusqlite` bundled FTS5 in `chimera-sitzung`, `--index-neu`,
      RSS am Pi messen.

## Phase 5a — Umgebungshören im Ruhezustand

Setzt Phase 5 voraus (Audioaufnahme läuft bereits). Details in
`docs/DESIGN.md`, Abschnitt „Umgebungshören im Ruhezustand".

- [ ] Tagger-Schicht, die Zipformer und CED gleich aussehen lässt —
      sherpa-onnx spricht beide unterschiedlich an. Das Modell ist eine
      Einstellung, kein Architekturmerkmal
- [ ] Voreinstellung CED-tiny (5,9 MB, 0,83 s gegen 4,71 s auf dem
      Pi Zero 2 W, laut Noisys Messung)
- [ ] Schwellenfaktor je Modell: CED liefert flachere Wahrscheinlichkeiten
- [ ] Ebene 1: kleine Reflextabelle für Sofortreaktionen (Knall, Lachen),
      ohne Modell, unter 1 s
- [ ] Ebene 2: Stimmungslage aus den letzten Minuten, lokal über Mischen
      und Variieren
- [ ] Ebene 3: Lagebeschreibung an das Sprachmodell, Antwort ist ein
      Mood-Name, eine Mischanweisung oder ein neuer Mood
- [ ] **Nur im Ruhezustand** hören; Wake-Word oder Taste beendet es
      (Regel 3b)
- [ ] Anfragen begrenzen (Mindestabstand, Auslösung bei deutlicher
      Änderung) — das Modell wird pro Situation befragt, nicht pro Geräusch
- [ ] Netzausfall: Ebene 1 und 2 laufen weiter, Zustand wird angezeigt
- [ ] **Auf Hardware messen:** Bildrate des Renderers mit laufendem
      Tagging; falls zu teuer, Taktrate senken

## Phase 5 — Sprache

Einzeln nachrüstbar, in dieser Reihenfolge.

> **Achtung, die Modellwahl unten muss überprüft werden.** HATFaces hat auf
> einem Cortex-A55 (RK3566) 8 Varianten über 18,6 min vermessen und kommt
> zum umgekehrten Ergebnis dessen, was hier stand:
>
> **fp32 schlägt int8 um Faktor 1,7.** Grund: Der Kern hat kein I8MM, das
> int8-Matrixprodukt fällt auf skalare Pfade zurück, während fp32 NEON
> voll nutzt. Ausgeschlossen wurden dort außerdem alle fp16
> (Laufzeit-Unverträglichkeit) und alle `high`-Varianten (thermisch nicht
> tragbar).
>
> **Was sich überträgt und was nicht:** Der Pi Zero 2 W hat Cortex-**A53**,
> ebenfalls ohne I8MM — das *Argument* gilt also. Die *Zahlen* nicht: Der
> A53 ist schwächer, RTF 0,63 wird er nicht erreichen. Es genügt aber, die
> zwei plausiblen Varianten zu prüfen statt acht.
>
> Auswahlregel: **fp32 vor int8, `low` vor `medium`, fp16 gar nicht.**
> Quelle: `../VERGLEICH-HATFACES.md`, HATFaces
> `docs/konzept/03_Stand_2026-04-17.md`.

- [ ] **Sprachkanal anschließen:** Die Betriebsart `mode="voice"` (kürzere
      Ausgabe) existiert im Telegram-Kanal, hat aber noch keine Ein- und
      Ausgabe — sie hängt an dieser Phase.
- [ ] sherpa-onnx auf der Zielhardware, Modelle laden
- [ ] VAD (`silero_vad_v5`)
- [ ] **Aufnahme mit Energie-VAD als Rückfall** (ohne Modell, ~0 CPU):
      sox-`silence` mit Start-/Endschwelle, 1,5 s Stille beendet den Satz,
      harte Höchstdauer; Schwelle aus dem **nachgeführten Geräuschpegel**
      (0,35 s alle 30 s, RMS×100, +1, geklemmt 2–60, geglättet 0,7/0,3).
      Muster aus dem Whisplay-Chatbot (GPL-3.0, nachgebaut — HERKUNFT `docs/HERKUNFT.md`, Abschnitt „Sprachverarbeitung").
- [ ] **Satzstrom statt fertiger Antwort** (Voraussetzung für RTF > 1):
      LLM-Text beim Eintreffen an Satzzeichen trennen, kurze Sätze zu
      ≤ 60 Zeichen bündeln, jeden Satz sofort an die TTS, bis zu 5
      Synthesen parallel, Wiedergabe **in Reihenfolge**, leerer Ton einmal
      wiederholt, Watchdog „Dauer + 2 s". Text vorher für die TTS reinigen
      (URLs, Markdown, Emoji). Muster: HERKUNFT `docs/HERKUNFT.md`, Abschnitt „Sprachverarbeitung".
- [ ] **ALSA-Besitz**: vor der Aufnahme den Wiedergabeprozess beenden und
      ~500 ms warten, bis das Gerät frei ist; danach neu starten.
- [ ] STT: **fp32-Variante zuerst messen**, nicht die int8 (bisher war
      `nemo-fast-conformer-ctc-en-de-es-fr-int8` vorgesehen), Latenz messen
- [ ] TTS: **`low`/fp32 zuerst**, dann `medium`/fp32 zum Vergleich
      (bisher war `thorsten_emotional-medium-int8` vorgesehen)
- [ ] **RTF auf dem Gerät messen, nicht übernehmen.** Grenze: RTF < 1,2 für
      Dialog, sonst blockiert die Ausgabe
- [ ] TTS-Emotion an Mood koppeln (Architekturregel 4b)

### Mienenspiel beim Sprechen (`docs/DESIGN.md`, Abschnitt „Mienenspiel beim Sprechen")

- [ ] Mundphase folgt der Lautstärke der Sprachausgabe (Regel 4c), sobald es
      sie gibt.
- [ ] Mundform folgt der Lautstärke der Sprachausgabe, jedes Bild
- [ ] Kopfbewegung und Pausen aus dem Sprachsignal, ~100 ms
- [ ] Sprachmodell liefert **Regieanweisung zum Satz** (Mood-Name oder
      Mischung), keine Einzelbilder — Latenz macht alles andere unmöglich
- [ ] **Messen:** hält der Renderer 15 Bilder/s, während gesprochen wird?
- [ ] Falls nicht: Bildrate beim Sprechen senken, aufwendige Ebenen
      aussetzen, Sprachausgabe stückweise erzeugen
- [ ] Wake-Word prüfen — die KWS-Modelle sind nicht auf deutschem Material
      trainiert. Wenn "Hey Chimera" unzuverlässig ist: eigenes Keyword
      trainieren oder Button als Auslöser
- [ ] Speicherverbrauch gegen Architekturregel 5 nachmessen
- [ ] Falls nötig: Modellrotation (STT und TTS nie gleichzeitig geladen)

## Phase 6 — Agent-Härtung

Die vier Muster aus `docs/DESIGN.md`, Abschnitt „Übernommene Muster aus OpenMinis (nachgebaut, nicht kopiert)" sind gebaut und verdrahtet.
Offen bleibt:

- [ ] Auslagern bei `Action.OFFLOAD`: erkannt wird es, getan noch nicht
- [ ] Schleifenzustand auf die RGB-LED (braucht Hardware)
- [ ] **Regel 10q, Messen:** `VmRSS`/`VmHWM`/`VmSwap` je Arbeitsschritt ins
      Protokoll, mit Gegenprobe über `numpy.ones(...)`
- [ ] **Regel 10q, Begrenzen:** Selbstbegrenzung mit eigenem Exitcode,
      Schwelle als Anteil von `MemTotal` in der Profiltabelle
- [ ] **Regel 10q, Nachweis:** beim Start im Kernelprotokoll nach einem
      Speichertod des Vorlaufs suchen
- [ ] **Regel 10p:** Startmarke und Quarantäne, spätestens mit dem ersten
      gespeicherten Zustand, den der Start liest (Gesichter 8b,
      `active_model.json`)
- [ ] **Zu entscheiden:** Speicher-Controller am Pi einschalten
      (`cgroup_enable=memory`, Bootdatei) oder bei der Selbstbegrenzung
      bleiben. Der RPi-Kernel startet mit `cgroup_disable=memory`, und
      `MemoryMax=` wirkt dort nicht (gemessen)
- [ ] Prüfung des Speicher-Controllers, falls `MemoryMax=` je in die Unit
      kommt (10q) — die Unit trägt es bewusst nicht

## Phase 7 — Restliche Peripherie

- [ ] Das Display zeigt einen Zustand erst nach dem Neustart des Dienstes
      richtig: Am Pi nach der Änderung von `SPEAK` ansehen und mit dem
      Dienstprotokoll abgleichen (Ausdruck, Statuszeile, LED).
- [ ] **Bedeutung der Gesten** (DESIGN `docs/DESIGN.md`, Abschnitt „Umgebungshören im Ruhezustand"): kurz = Umgebungshören
      beenden/Gespräch öffnen, lang = Gespräch beginnen, halten =
      Push-to-Talk, doppelt = abbrechen, dreifach = zurück. Hängt am
      Audio-Prozess (Phase 5). Bis dahin: Protokoll und LED-Quittung.
- [ ] **Push-to-Talk über `halten`/`halten_ende`** — *zurückgestellt 3.11.,
      solange es kein Audio-Modul gibt.* Die Geste ist fertig und am Gerät
      belegt (Klammer `halten` → `halten_ende`), es fehlt der Verbraucher:
      Aufnahme starten (Mikrofon, VAD) und stoppen (Transkription). Sobald
      der Audio-Prozess steht, ist es ein Aufrufpaar — die Erkennung muss
      dafür nicht angefasst werden.
- [ ] **Joystick (5-Wege) der neueren HAT-Revision** als Option prüfen:
      BOARD 32/33/31/29/37, active-low mit internem Pull-up, 20 ms
      Entprellung (HERKUNFT `docs/HERKUNFT.md`, Abschnitt „Der Treiber: Stand unseres Nachbaus"). Erst am Gerät feststellen, ob unsere
      Revision die Schalter hat — dann Opt-in im Panel, kein Zwang.
- [ ] Software-PWM bei Zwischenwerten: Backlight 50 % kostet ~9 % eines
      Kerns (1 kHz-Takt in Python). Kandidat: Backlight nur an/aus oder
      Takt senken, nach Sichtprüfung auf Flackern; zweiter Kandidat ein
      kleiner Rust-Helfer (HERKUNFT `docs/HERKUNFT.md`, Abschnitt „Was das für Rust heißt").
- [ ] Lautsprecher-Routing, Lautstärkeverwaltung — dabei **zwei** Dinge:
      `asound.conf` mit `dmix`/`dsnoop` (48 kHz, S16, period 1024,
      buffer 4096), damit Aufnahme und Ausgabe gleichzeitig gehen; und
      eine **wahrgenommene Lautstärkekurve** 0–100 % → Codec-Wert. Die
      Tabelle des Herstellers ist GPL-2.0 und wird nicht übernommen
      (HERKUNFT `docs/HERKUNFT.md`, Abschnitt „Ton: was uns fehlt und was wir nicht anfassen") — eigene Messung oder Formel.
- [ ] PiSugar-Akkustand als Mood-Eingang
- [ ] **UPS HAT (C)** (Waveshare, INA219 an I2C 0x43) als zweite
      Akkuquelle: `src/chimera/power/`, Erkennung im Boot-Abgleich,
      Installer-Modul 45. Vorlage: Gotchi-Fork `src/hardware/battery.py`.
- [ ] HAT-EEPROM der Whisplay (nur ES8389-Fassung) als Opt-in-Quelle
- [ ] Testton nach dem Laufzeit-Laden des Tons (automatische Abnahme:
      Lautsprecher → Mikro R, Spitze bei 1 kHz)
- [ ] Thermal-Hack neu kalibrieren (Agent-Grundlast einrechnen)

## Phase 8 — Installer

Entwurf steht in `docs/INSTALLER.md`. Der Installer traegt die
Plattformfrage, deshalb eigene Phase und nicht am Ende angehaengt.

### 8a — Geruest
- [ ] `--dry-run` und `--check` in den Modulen tatsaechlich auswerten
      (werden bisher nur durchgereicht)
- [ ] `VERSION` ins System stempeln, `chimera --version`

### 8b — Modul 10 `preflight` + Boardprofile  ✅ erster Wurf steht
Liefert sofort Nutzen: klaert die offenen Fragen zum Zielgeraet.
**Von Anfang an mit beiden Boards im Blick** (`docs/INSTALLER.md`, Abschnitt „Boarderkennung") —
sonst bedeutet Portieren spaeter ein Durchsuchen aller Module.
- [ ] **Offen, braucht Hardware:** laesst sich daraus V1 gegen V2
      unterscheiden? Bis dahin bleibt die Warnung stehen
- [ ] Warnen, wenn ungeteilte Kernelupdates aktiv sind
- [ ] Protokolldatei statt nur Ausgabe auf dem Schirm

### 8c — Module 20–70 fuer Pi Zero 2 W
Der einfache Fall: Header kommen aus dem Distributionspaket.
- [ ] Systempakete, Header (Stufe 1), Whisplay-Treiber bauen
      — Module 20/30/40 stehen im Code; was auf echter Hardware gelaufen
      ist, steht in `docs/HARDWARE-BEFUNDE.md`
- [ ] Overlay, kollidierende **umbenennen** statt loeschen
- [ ] Bootmethode erkennen statt `u-boot-update` vorauszusehen
- [ ] ALSA-Konfiguration

### 8d — Module 80–99
- [ ] Headless prüfen: kein Desktop-Paket wird nachgezogen
- [ ] **zram einrichten, 75 % des Arbeitsspeichers** (Regel 5e)
- [ ] **Auslagerungsdatei, ein Viertel des Systemdatenträgers** — auf dem
      Pi die SD, auf dem Radxa der eMMC (laeuft damit ohne SD)
- [ ] `vm.swappiness` niedrig halten; Auslagerungsmenge protokollieren
- [ ] Auf beiden Boards gleich einrichten — auch wo es nicht nötig wäre
- [ ] Python-Umgebung, Modelle laden und Pruefsummen verifizieren
- [ ] `.env` aus Vorlage, Ollama-Adresse erfragen
- [ ] `migrate_from()` fuer Uebergaenge (I2)
- [ ] Deinstallation, die den Ausgangszustand wiederherstellt

### 8e — Radxa Zero 3W: Portierung
**Zuletzt, gegen ein bereits laufendes Chimera auf dem Pi.** Sonst
debuggt man den Modulbau gegen eine Baustelle und weiss bei jedem Fehler
nicht, ob es der Treiber oder der eigene Code war.
Wenn 8b richtig gebaut ist, ist die Portierung im Wesentlichen **ein
ausgefuellter Profileintrag plus Header-Stufe 2/3**.
Analyse in `docs/INSTALLER.md`, Abschnitte „Boarderkennung" und „Modul 30 — Kernel-Headers".

- [ ] Radxa-Profileintrag ausfuellen (SPI3 CS0, Overlay-Ziel `/boot/dtbo`,
      kollidierende Overlays, Bootmethode je Distribution)
- [ ] Radxa-Debian **und** DietPi als getrennte OS-Faelle behandeln
- [ ] Tabelle bekannter Kombinationen (Board, Kernelversion, Quelle,
      Pruefsumme) statt einer fest verdrahteten Version
- [ ] Headers-Paket laden, Pruefsumme verifizieren
- [ ] **`dpkg-deb -x` in ein privates Verzeichnis** — niemals nach `/`
      entpacken (I5: merged-`/usr` wuerde zerstoert, dynamisch gelinkte
      Programme brechen)
- [ ] Versionskennung in `kernel.release` und `utsrelease.h` anpassen
- [ ] ARM64-Generatoreingaben ergaenzen, `cpucaps.h` und `sysreg-defs.h`
      erzeugen
- [ ] `fixdep` und `modpost` selbst bauen
- [ ] `/boot/config-<kver>` als `.config`, dann `olddefconfig` und
      `syncconfig` — sonst baut das Modul und laedt trotzdem nicht
- [ ] `modules_prepare` **nicht** aufrufen (laeuft bei Vendor-Kerneln endlos)
- [ ] `build`-Symlink setzen
- [ ] WM8960 aus Quelle bauen, falls im DietPi-Kernel nicht vorhanden
- [ ] Unbekannte Kernelversion ⇒ Abbruch mit Auskunft, kein Rateversuch

## Phase 8f — Selbstaktualisierung

Entwurf in `docs/SELBSTUPDATE.md`, Vorlage ist die PiHole-Routine.

- [ ] Sicherung mit Prüfung (Existenz, Kopie gelungen, nicht leer)
- [ ] Selbstprüfung: Dienst, Anzeige, Anbieter
- [ ] Gestufter Rollback mit Prüfung nach jeder Stufe
- [ ] Rückspielwerkzeug außerhalb des Updates, ohne Abhängigkeiten
- [ ] Mood-Bibliothek in die Sicherung
- [ ] Trockenlauf durchgehend; auf eMMC nachfragen
- [ ] Gegenprobe: Update absichtlich kaputt machen, Rollback muss greifen

## Phase 9 — Erstes Release

- [ ] CI: Tests der hardwarefreien Teile
- [ ] Secret-Scan vor jedem Push
- [ ] **Erst nach Hardware-Test:** `v0.1.0` taggen

---

## Offen / zu entscheiden

- **Web-Oberfläche** — jetzt Phase 4d (Modul-Plattform, 5m).
  Schlank, lokaler Port, kein Framework. Chimera muss ohne sie vollständig
  einsatzfähig bleiben (`docs/DESIGN.md`, „Headless"). Gehört in eine eigene Phase
  nach dem ersten Release.
- **Mood-Aufräumen:** Wenn der Agent dauerhaft speichern darf, wächst die
  Bibliothek unbegrenzt. LRU über `last_used`? Obergrenze?
- **Bleibt Telegram** die Hauptschnittstelle, wenn Mikrofon, Lautsprecher
  und Button da sind?
- **Wake-Word oder Button** als Gesprächsauslöser (siehe Phase 5).

---

## Phase 7 — Installer-Reste und Entwicklungswerkzeuge

- [ ] **Fremde zram-Verwaltung übernehmen.** Schritt 25 bricht heute mit
  benannter Meldung ab, wenn `systemd-zram-generator`, `rpi-swap` oder
  `dphys-swapfile` `/dev/zram0` verwaltet. Ziel: sichern und umstellen
  wie bei DietPi (Regel 5e).
- [ ] **Auslagerungsdatei ohne DietPi.** Schritt 25 meldet heute einen
  Befund, wenn `dietpi-set_swapfile` fehlt (Radxa mit anderem System).
- [ ] **`vm.swappiness` festlegen** — nach Messung (Regel 10g).
- [ ] **MCP-Server für Chimera.** Ein MCP-Server neuester Generation, der
  zuerst der Entwicklung den Zugriff auf die Testbench erleichtert und
  später dem Agenten den tooluse auf der eigenen Hardware. Zuerst ein
  Entwurf im DESIGN, dann Bau.
