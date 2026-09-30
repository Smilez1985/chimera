# Chimera — Roadmap

Was noch fehlt, nach Priorität. Entscheidungen und Begründungen stehen in
`docs/DESIGN.md`, nicht hier.

Stand: 2026-09-29. Pre-Alpha.

---

## Phase 0 — Blaupause ✅ (läuft)

- [x] `docs/DESIGN.md` — Architektur, Regeln, Grenzen
- [x] `docs/ROADMAP.md`
- [x] `CHANGELOG.md` mit `[Unreleased]`
- [x] `README.md`, `LICENSE`, `VERSION`
- [x] `docs/HARDWARE.md` — Zielplattform und Boardfrage
- [x] Debian-Fassung entschieden: **Trixie** (stable), nicht Forky
- [ ] Hardware-Revision der vorhandenen Whisplay prüfen (**V2?**)
- [ ] `uname -r`, `/lib/modules/$(uname -r)/build`, `modinfo snd-soc-wm8960`
      auf dem Zielgerät notieren (Checkliste in `docs/HARDWARE.md` §4)

---

## Phase 1 — Mood-Schema und Validator

**Ohne Hardware testbar.** Kern der neuen Idee, deshalb zuerst.

- [x] Kanonische Feldtabelle (`src/chimera/mood/schema.py`)
- [x] Schema für den Agenten *aus derselben Tabelle* (`describe_for_llm`)
- [x] Validator: zurechtstutzen statt ablehnen, unbekannte Felder verwerfen
- [x] Rückfall-Mood
- [x] Registry mit dynamischer Nummernvergabe, Ablage als JSON
- [x] Herkunft, Anlage- und Nutzungszeit; Aufräumen nach Gebrauch
- [x] **Freie Zeichenformen** (`draw.py`) — 11 Grundformen, Regel 1a
- [x] Noisys 41 Moods als Startbestand (`tools/import-noisy-moods.py`)
- [x] 68 Tests mit Gegenproben

## Phase 2 — Mischen und Variieren

**Ohne Hardware testbar.**

- [x] `mix(a, b, gewicht)` — Farbton statt Kanäle, Listen werden vereinigt
- [x] `vary(mood, seed)` — gleicher Anlass, gleiches Ergebnis
- [x] Kontaktbogen (`tools/contact-sheet.py`)
- [ ] `MAX_SHAPES` auf echter Hardware messen

## Phase 3 — Display und Renderer

Hardware ist vorhanden, also nicht blockiert.

- [x] Display-Adapter: `PIL.Image` → RGB565 → `board.draw_image()`
      (`chimera.display.panel`, wie bei Noisy direkt in den Panelspeicher)
- [x] Renderer aus Noisy übernommen und auflösungsrelativ gemacht
- [x] Komponenten-Pipeline (kam mit)
- [x] Blink-Engine, Nachlauf-Effekte, Software-Dimming (kamen mit)
- [x] Mood-Übergänge über alle Felder, weich und hart (Regel 6b)
- [x] Bildrate auf Zielhardware gemessen: 39,3 ms je Bild
      (zeichnen 3,4 · umrechnen 7,9 · **SPI senden 28,1**) = 25,4 Bilder/s
      Obergrenze. 15 Bilder/s brauchen 59 % des Budgets.
      **Befund: Die Übertragung kostet 70 % — mehr als Zeichnen und
      Umrechnen zusammen.** War nicht erwartet und verschiebt den Engpass.
- [ ] **Statuszeile in den 40 zusätzlichen Zeilen — nach der
      Prioritäts-Grammatik**, nicht als Sonderfall

      Vorbild: HATFaces `docs/konzept/07_Text_Overlay.md` (Analyse in
      `../VERGLEICH-HATFACES.md`). Übernommen wird das Modell, nicht der
      Code — dort gibt es keinen.

      - [ ] Quellen-Katalog mit fester Basis-Priorität, **Abstände ≥ 10**
            (damit neue Quellen ohne Umnummerierung einsortiert werden —
            genau das Problem, das die Regelnummern heute haben: `5h`
            steht zwischen `5b` und `5c`)
      - [ ] **Pro Quelle genau ein Slot.** Ein „Update" ist ein neuer
            Eintrag derselben Quelle, der den alten verdrängt
      - [ ] Auflösung: Priorität → jüngster Zeitstempel → feste
            Quellenreihenfolge. **Die dritte Stufe ist nicht optional**,
            sonst ist das Ergebnis bei gleichzeitigen Einträgen nicht
            reproduzierbar
      - [ ] **Auto-Renew statt langer Laufzeit** für anhaltende Zustände:
            kurze TTL plus Bedingung, die sie zurücksetzt. Erlischt von
            selbst, wenn die Bedingung wegfällt — kein explizites Löschen,
            kein Leck
      - [ ] Chimeras Quellen (nicht HATFaces' — dort gibt es ein Gateway
            und Plugins, hier nicht): Abschaltmeldung, Temperaturwarnung,
            Anbieter nicht erreichbar, Agentenzustand
            (denkt/hört/antwortet), Akkustand, Leerlaufbeschriftung
      - [ ] Muster sind **reine Funktionen** `f(t, farbe) -> farbe`, ohne
            eigene Zeitgeber. Die Zeit gehört dem Verwalter, nicht dem
            Muster
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
      Auswahl in `docs/HERKUNFT.md` §1.2, **Sicherheitsschicht des
      `execute_bash` unverändert mitnehmen**
- [ ] Alten Display-Layer entfernen (Architekturregel 7)
- [ ] Renderer als Dauer-Thread, Zustandsübergabe über Shared Memory
- [ ] `skills/mood/SKILL.md` (Architekturregel 8)
- [ ] Agent-Zustände auf Moods abbilden (denkt, spricht, hört zu)

### Werkzeugschleife → erledigt

`FACE:` ist als Werkzeug `set_face` umgesetzt und mit der Mood-Bibliothek
verdrahtet. Offen bleiben `DISPLAY:` (Statuszeile) und `SAY:` (braucht
Sprachausgabe).

### E-Ink-Ausgabe auf Whisplay umbiegen

Die Steuerbefehle bleiben, nur das Ziel wechselt (`docs/DESIGN.md` §6).

- [ ] `FACE:` auf Mood-Datensätze statt Emoticons legen; generierte Moods
      zulassen
- [ ] `DISPLAY:` auf die Statuszeile legen
- [ ] `SAY:` auf Sprechblase **und** Sprachausgabe legen
- [ ] Ghosting-Behandlung und Vollbild-Auffrischung ersatzlos entfernen
- [ ] Die 10 alten Emoticon-Moods als Startbestand abbilden, damit
      bestehende Skills unverändert laufen

## Phase 4b — Provider-Schicht

Kann parallel zu Phase 4 laufen; berührt den Renderer nicht.

- [x] **Registry** mit Aufgaben und Gruppen (Regel 5a, 5h)
- [x] Rückfall **über Anbietergrenzen** — jedes Glied nennt Anbieter+Modell
- [x] `Connector` um `supports_tools`, `context_window`,
      `supports_streaming`, `cost_class`, `access` erweitert
- [x] **Ollama-Connector** mit Platzhalter-Erkennung und Netzsuche
- [x] **Claude getrennt nach Abo und Schlüssel**, Herkunft in der Antwort
- [x] Client-Kennung zur Laufzeit (PR #407), mit Rückfallwert
- [x] Ersteinrichtung: suchen, vorschlagen, übernehmen — änderbar
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
      `docs/DESIGN.md` §4a): `/model`-Befehl zum Umschalten im Chat,
      **persistente Modellwahl** über Neustarts, Platzhalter-Adresse als
      „nicht gesetzt" behandeln statt Verbindungsfehler, Installer fragt
      die Ollama-Adresse ab
- [ ] Fehlender Schlüssel ⇒ Connector meldet sich als nicht verfügbar,
      kein Startabbruch
- [ ] `.env.example` mit Platzhaltern für alle Anbieter

## Phase 4c — Telegram erhalten ✓

Erledigt, siehe `CHANGELOG.md` unter `[Unreleased]`. Telegram wurde nicht
übernommen, sondern ohne Fremdbibliothek neu gebaut (nur `urllib`) — auf
512 MB ist jede vermiedene Abhängigkeit eine gesparte. Gemeinsamer Verlauf,
Kanal als Kontext und die Zustandsmeldung ans Gesicht sind verdrahtet und
geprüft.

Offen bleibt hier nur, was Sprache voraussetzt: Der Sprachkanal existiert
als Betriebsart (`mode="voice"` mit kürzerer Ausgabe), hat aber noch keine
Ein- und Ausgabe — die kommt mit Phase 5.

## Phase 5a — Umgebungshören im Ruhezustand

Setzt Phase 5 voraus (Audioaufnahme läuft bereits). Details in
`docs/DESIGN.md` §3.4.

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

- [ ] sherpa-onnx auf der Zielhardware, Modelle laden
- [ ] VAD (`silero_vad_v5`)
- [ ] STT: **fp32-Variante zuerst messen**, nicht die int8 (bisher war
      `nemo-fast-conformer-ctc-en-de-es-fr-int8` vorgesehen), Latenz messen
- [ ] TTS: **`low`/fp32 zuerst**, dann `medium`/fp32 zum Vergleich
      (bisher war `thorsten_emotional-medium-int8` vorgesehen)
- [ ] **RTF auf dem Gerät messen, nicht übernehmen.** Grenze: RTF < 1,2 für
      Dialog, sonst blockiert die Ausgabe
- [ ] TTS-Emotion an Mood koppeln (Architekturregel 4b)

### Mienenspiel beim Sprechen (`docs/DESIGN.md` §4.1)
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

Die vier Muster aus `docs/DESIGN.md` §8 sind gebaut und verdrahtet.
Offen bleibt:

- [x] Rangordnung im Gedächtnis (nur lesbar gegen agentgeschrieben)
- [ ] Auslagern bei `Action.OFFLOAD`: erkannt wird es, getan noch nicht
- [ ] Schleifenzustand auf die RGB-LED (braucht Hardware)

## Phase 7 — Restliche Peripherie

- [ ] RGB-LED an Mood-Glow
- [ ] Button: Gesten (kurz / lang / mehrfach)
- [ ] Lautsprecher-Routing, Lautstärkeverwaltung
- [ ] PiSugar-Akkustand als Mood-Eingang
- [ ] Thermal-Hack neu kalibrieren (Agent-Grundlast einrechnen)

## Phase 8 — Installer

Entwurf steht in `docs/INSTALLER.md`. Der Installer traegt die
Plattformfrage, deshalb eigene Phase und nicht am Ende angehaengt.

### 8a — Geruest
- [x] `installer/lib/common.sh` — Ausgabe, Systemabfragen über `CHIMERA_ROOT`
- [x] Atomares Schreiben: Sidecar neben dem Ziel, dann `mv`
- [x] **`mktemp` geprueft** — ungeprueft leert es Zieldateien (I3)
- [x] **Leere Eingabe wird abgelehnt** (Regel 8a: stiller Erfolg). Gefunden
      durch den eigenen Test, nicht durch Nachdenken
- [x] `chimera-install` als Einstieg, Module nach Nummer, `--only`, `--list`
- [x] **Protokolldatei je Lauf, auch bei Erfolg** (Regel 10e)
- [ ] `--dry-run` und `--check` in den Modulen tatsaechlich auswerten
      (werden bisher nur durchgereicht)
- [ ] Protokolle aufraeumen (Anzahl oder Alter begrenzen)
- [ ] `VERSION` ins System stempeln, `chimera --version`

### 8b — Modul 10 `preflight` + Boardprofile  ✅ erster Wurf steht
Liefert sofort Nutzen: klaert die offenen Fragen zum Zielgeraet.
**Von Anfang an mit beiden Boards im Blick** (`docs/INSTALLER.md` §2a) —
sonst bedeutet Portieren spaeter ein Durchsuchen aller Module.
- [x] Board und Betriebssystem **getrennt** erkennen (zwei Achsen: derselbe
      Chip unter DietPi und unter Radxa-Debian sind zwei Faelle)
- [x] Bootmethode erkennen: `config.txt` / extlinux / u-boot-Skript
- [x] Erkennung auf **konkrete `compatible`-Kennung** stuetzen, nicht auf
      `model == *"Radxa"*` — das trifft jedes Radxa-Board
- [x] **Profiltabelle** fuer alles Boardabhaengige (Header-Stufe, SPI-Bus
      und -Takt, Overlay-Quelle und -Ziel, kollidierende Overlays,
      Bootmethode, ALSA-Vorlage) — ein neues Board = ein Eintrag
- [x] Radxa-Eintrag von Anfang an vorhanden, meldet „noch nicht
      unterstuetzt" als bewussten Zustand
- [x] Unbekanntes Board ⇒ **Abbruch mit Auskunft**, kein Rateversuch.
      `--force-board` nur fuer Entwicklung, nie im Fehlertext vorgeschlagen
- [x] Whisplay-EEPROM auslesen (`/proc/device-tree/hat/`)
- [ ] **Offen, braucht Hardware:** laesst sich daraus V1 gegen V2
      unterscheiden? Bis dahin bleibt die Warnung stehen
- [x] `uname -r`, Header-Verzeichnis, `snd-soc-wm8960`, `/boot/config-*`,
      Speicher erfassen und berichten
- [ ] Warnen, wenn ungeteilte Kernelupdates aktiv sind
- [ ] Protokolldatei statt nur Ausgabe auf dem Schirm
- [x] Test ohne Hardware: erfundene `model`- und `os-release`-Inhalte in
      einem temporaeren Wurzelverzeichnis (31 Tests, mit Gegenproben)

### 8c — Module 20–70 fuer Pi Zero 2 W
Der einfache Fall: Header kommen aus dem Distributionspaket.
- [ ] Systempakete, Header (Stufe 1), Whisplay-Treiber bauen
- [ ] WM8960 pruefen: **`modprobe` versuchen**, nicht nur Existenz pruefen
      (ein vorhandenes Modul kann ABI-inkompatibel sein)
- [ ] Overlay, kollidierende **umbenennen** statt loeschen
- [ ] Bootmethode erkennen statt `u-boot-update` vorauszusetzen
- [ ] Bootdateien vorher sichern
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
- [ ] systemd-Unit
- [ ] `migrate_from()` fuer Uebergaenge (I2)
- [ ] Deinstallation, die den Ausgangszustand wiederherstellt

### 8e — Radxa Zero 3W: Portierung
**Zuletzt, gegen ein bereits laufendes Chimera auf dem Pi.** Sonst
debuggt man den Modulbau gegen eine Baustelle und weiss bei jedem Fehler
nicht, ob es der Treiber oder der eigene Code war.
Wenn 8b richtig gebaut ist, ist die Portierung im Wesentlichen **ein
ausgefuellter Profileintrag plus Header-Stufe 2/3**.
Analyse in `docs/INSTALLER.md` §2a und §3.

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

- **Web-Oberfläche für Einstellungen** — gewünscht, aber nachrangig.
  Schlank, lokaler Port, kein Framework. Chimera muss ohne sie vollständig
  einsatzfähig bleiben (`docs/DESIGN.md` §11a). Gehört in eine eigene Phase
  nach dem ersten Release.
- **Mood-Aufräumen:** Wenn der Agent dauerhaft speichern darf, wächst die
  Bibliothek unbegrenzt. LRU über `last_used`? Obergrenze?
- **Bleibt Telegram** die Hauptschnittstelle, wenn Mikrofon, Lautsprecher
  und Button da sind?
- **Wake-Word oder Button** als Gesprächsauslöser (siehe Phase 5).
