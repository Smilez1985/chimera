# Chimera — Roadmap

Was noch fehlt, nach Priorität. Entscheidungen und Begründungen stehen in
`docs/DESIGN.md`, nicht hier.

Stand: 2026-10-11. Pre-Alpha.

---

## Phase 0 — Blaupause ✅ (läuft)

- [x] `docs/DESIGN.md` — Architektur, Regeln, Grenzen
- [x] `docs/ROADMAP.md`
- [x] `CHANGELOG.md` nach Keep a Changelog (ohne `[Unreleased]`, Regel „Changelog ohne Unreleased“)
- [x] `README.md`, `LICENSE`, `VERSION`
- [x] `docs/HARDWARE.md` — Zielplattform und Boardfrage
- [x] Debian-Fassung entschieden: **Trixie** (stable), nicht Forky
- [ ] Hardware-Revision der vorhandenen Whisplay prüfen (**V2?**)
- [ ] `uname -r`, `/lib/modules/$(uname -r)/build`, `modinfo snd-soc-wm8960`
      auf dem Zielgerät notieren (Checkliste in `docs/HARDWARE.md` §4)

---

## Phase Installer — Idempotenz, Abkopplung, Anzeige beim Update

Vorgaben smilez (2.11.): Der Installer fasst **nur an, was fehlt oder wegen
einer neuen Version aktualisiert werden muss**; er läuft nie in der SSH-Sitzung;
zram wird nicht angefasst, wenn es läuft.

- [x] **Abkopplung im Code:** `chimera-install` startet die Arbeit als
      `chimera-installhelper` (transient, `oneshot`) und wartet; ohne root wird
      abgelehnt statt in der Sitzung zu laufen. Ein zweiter Aufruf hängt sich an
      den laufenden Lauf.
- [x] **Klammer um den Lauf:** Dienste anhalten, Dateien tauschen, in der
      gemessenen Reihenfolge starten (Sockets **vor** Diensten), Nachweis, dass
      alles läuft. Das Gateway wird über den Socket **geweckt**, nicht direkt
      gestartet (am Pi gemessen: direkter Start scheitert, es braucht
      `LISTEN_FDS`).
- [x] **Klammer nur bei echter Änderung:** unveränderter Quellstand und erfüllte
      Abhängigkeiten → Dienste laufen weiter, nichts wird angefasst.
- [x] **zram:** Läuft es, bleibt der Speicherschritt ganz aus (kein
      `swapoff -a`, kein Dateischritt, keine Änderung der Konfiguration).
      Angelegt wird nur, wenn es fehlt.
- [x] **SSH-Schutz:** Drop-in `ssh.service.d/10-chimera-oom.conf` mit
      `OOMScoreAdjust=-900` (Sitzungsprozesse hatten `oom_score_adj=0`).
- [x] **Transiente Unit geklärt (2.11.):** Die Unit ist über `systemctl` nicht
      abfragbar („Failed to open /run/systemd/transient/…“), **läuft aber**. Das
      ist eine Eigenheit der transienten Unit, kein Fehler — deshalb der
      Laufzettel in `/run/chimera-installhelper.status`. Die eigentliche Ursache
      der „startete nicht“-Meldungen war eine andere: `systemd-run` ohne
      `--no-block` wartet auf den `oneshot` und meldet dessen Exitcode als
      Startfehler. Belegt: Verbindungsabbruch nach 9 s, Helfer lief durch,
      Zettel `fertig`, Dienste aktiv, Web 200.
- [x] **„Updated“-Gesicht vor dem Anhalten:** Gesicht `UPDATE` (Mood) +
      Operation `gesicht` am Sitzungs-Socket; der Installer setzt es, bevor die
      Dienste gehen (`installer/lib/py/gesicht.py`). Das Panel wird nicht
      geleert, das Bild bleibt bis zum Dienststart stehen.
- [x] **Fortschrittsbalken, LED und Licht:** echte Stufen (fertig/gesamt),
      „Updating…" darüber, ein Zeichner je Lauf; LED gelb blinkend → grün /
      gelb ruhig / rot SOS; jede Backlight-Änderung mit Grund protokolliert.
      Am Pi belegt: Spur `0,00 … 1,00` ohne Rücksprung, genau ein Zeichner.
- [x] **„Updated“-Gesicht am Gerät:** am Panel abgelesen (2.11.): Gesicht mit
      Balken und „Updating…" sichtbar, Anzeige bleibt bis zum Dienststart.
- [ ] **Grüner LED-Abschluss am Gerät:** Bisher leuchtet am Ende gelb, weil
      jeder Lauf aus einem Zip mit dem Befund „kein Commit ⇒ kein Binary" endet
      (rc 1). Ein Lauf aus einem Git-Baum mit Commit muss grün zeigen — einmal
      ablesen, dann ist der Fall belegt.
- [x] **Bedarf messen:** CPU, RAM und freier Datentraeger, die Chimera im
      Betrieb wirklich braucht. *Erledigt 3.11. am Pi (Zahlen im DESIGN,
      Regel „Neustart mit Fortsetzung"): RAM 462 MB, 359 MB verfuegbar;
      Karte 95 GB frei; `source/` 3 MB, `state/` 40 KB, `productive/` 107 MB;
      `chimera.service` 47 MB RSS und **28,4 % eines Kerns im Leerlauf**;
      `chimera-tor --dienst` 1,6 MB / 0,2 %; Mojo-Pruefung 528 ms und 6 MB
      Spitze. Die 100 MB vor einem Snapshot sind damit eine Untergrenze, kein
      Bedarf.*
- [ ] **Platzpruefung vor dem Snapshot:** Statt fester 100 MB die **Groesse der
      zu sichernden Dateien** plus Reserve pruefen (Summe steht vor dem
      Kopieren fest, DESIGN-Regel „Neustart mit Fortsetzung"). Die 100 MB
      bleiben Untergrenze.
- [ ] **Leerlauf-Last des Agenten:** `chimera.service` verbrauchte im Leerlauf
      **28,4 %** eines Kerns; ein Faden hing zu ~22 % in `D` und schrieb auf
      `/dev/spidev0.0` — **572 `write()` je Sekunde**, rund 17 volle Bilder je
      Sekunde ohne Änderung.
      *3.11. gemessen und eingegrenzt:* Der Transport war es nicht. Der Umbau
      auf geänderte Bereiche ließ die Last sogar auf 35,5 % steigen (577
      `write()`/s), weil das schwingende Gesicht **jedes** Bild flächig ändert
      (44–60 % der Pixel je Rahmen). Danach die Bildrate an den Zustand
      gebunden (DESIGN, Regel 7a): Ruhe 2 Bilder/s, volle Rate nur beim
      Blinzeln/Sprechen/Zustandswechsel. **Am Pi belegt:** 10,8 % eines Kerns,
      134 `write()`/s, 86 KB/s — ein Drittel der Last, ein Viertel der
      Schreibaufrufe. Offen bleiben die vier Nebenverbraucher (je ~1,3 %):
      - [x] **Tastenschleife:** fragte alle 5 ms die Leitung ab (200 Weckrufe
        je Sekunde, ~1,3 % eines Kerns). *Erledigt 3.11.: Kantenereignisse
        (`request(kanten=…)`, `ereignisse()`, `EDGE_RISING/FALLING`); am Pi
        belegt („Taste: Kantenereignisse" im Protokoll), Gesamtlast 10,8 % →
        9,5 %. Rückfall auf die Abfrage, wenn der Kernel die Kanten nicht
        annimmt. Tests `test_gpio_kanten.py` 23 ok, Gegenprobe 8 ok.*
      - [ ] **LED-Kanäle:** drei Fäden takten mit 100 Hz, weil der Glanzwert
        zwischen 0 und 100 liegt. Prüfen: niedrigere Frequenz oder ein Faden
        für alle drei.

- [x] **Neustart mit Fortsetzung:** Marker, Snapshot der geänderten Dateien,
      `chimera-mojo-fortsetzung.service` (einmal nach dem Start), Rückfall bei
      wirkungslosem Neustart, Sperre nach zwei Versuchen (DESIGN, Regel
      „Neustart mit Fortsetzung und Rückfall").
      *Erledigt 3.11.: Marker, Snapshot, Rückfall und Sperre in
      `chimera-tor --mojo --fortsetzen` (14 Tests, `cargo test -p chimera-tor`
      256 ok); `chimera-mojo-fortsetzung.service` schreibt der Installer
      (Schritt 27, 82 Tests, Gegenprobe 32). **Am Pi belegt** (3.11., 21:40):
      Installer aus `81c047b` → Unit eingeschaltet und im Manifest; Marker
      geschrieben, `systemctl reboot` → Fortsetzung lief nach dem Start
      (9 ok, 0 warn), meldete „der Neustart hat gewirkt … Marker entfernt",
      Marker danach weg. Ohne Marker: „skipped, unmet condition check",
      `Result=success` — kein Befund bei jedem Boot.*
- [x] **Modul 40: laufender Dienst ist kein Befund.** Meldet „Leitungen
      gehalten", wenn die Ton-Prüfung fehlschlägt und Schritt 40 deshalb in die
      Erkennung läuft, obwohl die Anzeige eingerichtet ist und der Dienst sie
      bedient. Fix: eingerichtete Anzeige + laufender Dienst = gesund.
      *Erledigt 3.11.: Typ aus `state/anzeige` gilt bei belegten Leitungen,
      wenn sein Nachweis zutrifft (Am Pi: rc 0, Gegenprobe rc 1). Der grüne
      LED-Abschluss im VOLLEN Lauf steht noch aus.*
- [ ] **Grüner LED-Abschluss am Gerät.** Modul 40 ist erledigt (voller Lauf
      3.11.: `Modul 40-install-display: ok`). Ursache für das Gelb war zuletzt
      **Modul 55**: Fehlte das Prerelease `rust-<commit>`, endet der Lauf mit
      Befund (rc 1). Zum Commit `db8870a` fehlte es, weil die CI auf
      `entwicklung` **nicht bei jedem Push** läuft (`on.push.branches: [main]`
      in `.github/workflows/tests.yml`); Releases entstehen dort nur per
      `workflow_dispatch`. Nach dem Anstoßen war der Lauf fehlerfrei (rc 0,
      „12 Modul(e), ohne Fehler"). Zu entscheiden (smilez): `entwicklung` in
      den Push-Trigger aufnehmen, oder den Rust-Job an einen Pfadfilter
      (`rust/**`) hängen und das Prerelease nur dann erwarten.
- [x] **CI ist auf `entwicklung` rot — behoben am 3.11. (Sitzung `d4427984`).**
      Fünf rote Testdateien, alle mit Ursache: `test-helfer.sh`
      (`bad function name`: Attrappe war eine Funktion mit Bindestrich — jetzt
      ein Skript im PATH), `test-launcher-hardware.sh`,
      `test-launcher-rc3.sh` und `test-source.sh` (liefen in die Abkopplung nach
      `systemd-run`, das im CI-Runner fehlt: rc 2 vor dem ersten Modul — jetzt
      `CHIMERA_HELFER=1` und `systemctl`-Attrappe), `test_cli_doku.py`
      (Python 3.13 dedentet Docstrings, die Befehlsliste der `displays`-Hilfe
      verlor ihre Einrückung). Nichts davon war durch die Anzeige-Änderung
      verursacht; sie waren nur unsichtbar, solange der Push-Trigger fehlte.
- [ ] **pip: nur Fehlendes, ohne `--upgrade`.** Zurückgestellt: Die Änderung
      machte zwei Tests von `test-python-env.sh` rot; der erprobte Stand bleibt,
      bis die Ursache geklärt ist (das venv hatte `numpy 2.5.4` statt `1.26.4`).
- [ ] **UV für `requirements.txt`** (Vorgabe smilez, 2.11.): eigenes
      Werkzeug-venv, nur anlegen wenn es fehlt, Installation über pip (Prüfsummen
      von PyPI), harte Zeitgrenzen, Rückfall auf pip. Vorbedingung: die Tests von
      `test-python-env.sh` müssen ohne Netz reproduzierbar sein (der
      Nachweis-Fall geht heute ins Netz und hängt in der Sandbox).
- [ ] **`test-python-env.sh` hermetisch machen:** alle Fälle mit
      `PIP_NO_INDEX=1` und lokalen Wheels, damit das Ergebnis nicht davon
      abhängt, ob der Rechner Internet hat.

## Phase ACP — Chimera als Agent für Editoren und IDEs (DESIGN: Regel „ACP“)

Pflicht-Schnittstelle (smilez, 2.11.). **Entschieden: Der ACP-Server wird gebaut,
mit einer Transportschicht, damit eine IDE das Gateway ansprechen kann.**
Recherche: `docs/research/ACP.md` und `docs/research/ACP-MCP.md`. Rust im
Gateway-Workspace (Regel „Rust, wo dauernd läuft“), eigene Tür.

- [x] Recherche: ACP klären (Client, Communication, Context), mit MCP vergleichen,
      Android Studio Rabbit 2 lesen.
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

- [x] Regel „Sprechende Namen“ steht; `tests/test_regelnamen.py` verhindert neue
      Nummern, mit Gegenprobe.
- [x] „Sprechgesicht“ (vorher 4d) und „Mojo“ (vorher 10t) tragen schon Namen.
- [ ] Die Namen für den Altbestand festlegen (eine Tabelle Nummer -> Name, von
      smilez abzunehmen), dann je Themenblock umbenennen: Anbieter und Gateway
      (5*), Anzeige (6*, 7*), Gedächtnis und Sitzung (8*), Installer (10*),
      Rest. Jeder umbenannte Eintrag verlässt die Altbestand-Liste des Tests.
- [ ] Die Verzeichnisse und Querverweise „Regel 5n“ usw. in Quelltext-Kommentaren
      folgen mit der Umbenennung.

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
- [x] **Prioritäts-Verwalter** (`chimera/arbiter.py`) — gemeinsame
      Auflösung für Statuszeile **und** LED (Regel 7c). Ein Baustein, zwei
      Nutzer; die Vorlage nimmt hier bewusst eine Doppelung in Kauf
      („nur Stil-Analogie"), das war für uns die falsche Wahl.
      30 Prüfungen mit Gegenproben.
- [x] **Statuszeile in den 40 zusätzlichen Zeilen — nach der
      Prioritäts-Grammatik** (`chimera/display/statusline.py`),
      angeschlossen in `NoisyRenderer.show()`. 25 + 7 Prüfungen.
      Offen geblieben (siehe unten): gesichtsabhängige Einstellungen,
      Teilübertragung, eigene Schriftart.
- [x] **Eigenes Treiberpaket `chimera.displays`** (11.10.2026): ST7789-Kern,
      GPIO v2/SPI per ctypes, Whisplay-Modul (LCD, LED, Backlight, Taste),
      Registry über Ordner, Erkennung in drei Klassen, Ton zur Laufzeit.
      Gemessen: `show` 29,4 ms je Bild (statt 39,3 mit Herstellertreiber),
      keine Quellbau-Abhängigkeiten mehr. Tests 42 + Gegenprobe 7 Mutationen.
- [ ] **Module `gamepi13/`** (DC25 RST27 BL19, 240×240, MADCTL 0x70,
      Pimoroni-Einschaltfolge, invertiert) und **`epd2in13b/`** (Treiber aus
      dem Gotchi-Fork, BUSY-Prüfung, Mindestabstand 120 s, reduziert+Akzent).
      Messung erst beim Kartentausch bzw. am E-Ink-Pi.
- [x] **Boot-Abgleich:** `chimera-hardware.service` (oneshot, root, vor dem
      Dienst) → `chimera-install --hardware` (40/45/50), Ton laden,
      `/run/chimera/anzeige.env` an den Dienst. Dienst startet mit Panel
      und Ton ohne Zutun.
- [ ] **Dienst-Template `chimera@<typ>.service`** (ein Dienst je
      Anzeigeart, E-Paper braucht einen anderen Renderer) und
      `state/hardware.json` (erkannt, Zeit, Quelle; Soll/Ist-Abgleich für
      UPS). Bis dahin: ein `chimera.service`, Anzeige aus der Umgebung.
- [x] **Boot-Abgleich unter 10 s** (9,6 s, vorher 20,2 s).
- [ ] **Boot-Abgleich weiter kürzen:** Schritt 40 startet Python für
      Erkennung, Profil und Ton getrennt (zusammen 4,5 s).
- [ ] **Anbieterausfall auf der LED?** Entscheiden, ob ein Gerät ohne
      Sprachmodell auch per LED warnt (`anbieter_weg`) oder nur in der
      Statuszeile — bei bewusstem Betrieb ohne Modell wäre Dauerblinken
      störend.
- [ ] **Akku in der Statuszeile** (DESIGN §5), sobald die Akkuquelle
      (PiSugar / UPS HAT C) gebaut ist.
- [x] **Mikrofonwahl durch Messung** (Modul 46): Jede Installation misst
      ihre Mikrofone und wählt die brauchbaren; Aufnahmegerät `chimera_mikro`.
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
- [x] Client-Kennung zur Laufzeit (aus `claude --version`), mit
      Rückfallwert. Weicht von PR #407 ab und wird in Phase 4d ersetzt.
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

## Phase 4d — Gateway in Rust (DESIGN §4c, Regel 14)

Löst `provider/` und `bot/` im Dienst ab. Jede Stufe für sich lauffähig.

- [x] **Rust-Grundlage:** `rust/` als Cargo-Workspace (`gemein`, `chimera-tor`), CI-Job mit
      `cargo test`, `cargo deny`, Build aarch64-musl und SHA-256 am
      Prerelease `rust-<commit>`. Installer-Modul 55 holt und prüft das Binary.
- [x] **Gerüst:** Socket `/run/chimera/tor.sock`, Unit mit Nutzer
      `chimera-tor` und `MemoryMax` (Modul 99).
- [x] **Ollama im Gateway:** `op: chat`/`modelle` mit `anbieter: ollama`,
      Python-Connector `provider/gateway.py` (Name bleibt `ollama`, Anzeige
      „ollama @ Host“); der Dienst nutzt das Gateway, wenn es antwortet,
      sonst den direkten Weg.
- [ ] **Ein Kanal, eine Hauptsitzung** (DESIGN 5s) — Sitzungs-Socket, Ereignisstrom, Telegram-Tür im Gateway, Umleitung auf `haupt` und Sitzungsablage mit Wechsel (`wechseln`, `sitzungen`, `lesen`) laufen. Offen: Auslöser für den Wechsel (Wächter, 8d), Python-Telegram im Dienst entfernen, Klingel (Briefkasten, 5o) als Tür mit `ref`.
- [ ] **Web-Oberfläche als Modul-Plattform** (5m), **vor** den weiteren
      Anbietern, damit alles per Oberfläche einstellbar ist:
      1. [x] Rahmen: Anmeldung (Passwort-Hash), Menü, Router, Modul-Erkennung
         (`module/*/manifest.json`), eingebaute und nachgelegte Module.
      2. Module, in dieser Reihenfolge (DESIGN 5t, 5u):
         [x] Chat (Strom, Senden, ältere Sitzungen lesen);
         [x] Status (Dienste, Speicher, Temperatur);
         [ ] Modul-Registrierung (5v) — Rechteliste und Vorlage (`--module-neu`, `--module-pruefen`) stehen; offen: Freigabe mit Prüfsumme und
         Passwort, Sandbox-iframe mit Brücke, Weitergabe an Modul-Socket;
         [ ] Datenschicht im Gateway — Ablagen, Operationen und Unit-Rechte
         stehen; offen: Katalog füllen (Abfrage + `fehlt_seit`), Neustart
         des Gateways nach Schlüsseländerung, Umzug von Telegram-Token und
         Passwort-Hash aus der `.env` nach `config/geheim/`
         (`migrate_from`), Rechte `anbieter-lesen`/`anbieter-schreiben`;
         [x] Anbieter Ollama (Vorlage für alle), „Anbieter hinzufügen“ und
         Netzsuche mit Selbsteintrag (am Pi gelaufen);
         [ ] Reihenfolge (Wahl über Anbieter hinweg);
         [ ] Einstellungen: Passwort ändern, Werksreset mit Satz am Display,
         Telegram, Sprache;
         [ ] Anbieter Anthropic (Schlüssel, danach Abo);
         [ ] Anzeigespiegel (Waveshare) — braucht zuerst ein fertiges Bild
         im Shared Memory vom Renderer, eigener Entwurf.
      3. [x] Ein Zusatzmodul erscheint ohne Änderung an Rahmen oder Gateway
         (Test mit Gegenprobe).
      4. [x] Installer trägt den Hash ein (`CHIMERA_WEB_PASSWORT`);
         [x] Port nur im LAN begrenzen (Prüfung der Quelladresse im Gateway, 5m).
      5. [ ] Am Pi laufen lassen (Anmeldung, Chat gegen die echte Sitzung).
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

## Phase 4c — Telegram erhalten ✓

Erledigt, siehe `CHANGELOG.md`. Telegram wurde nicht
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
- [ ] **Aufnahme mit Energie-VAD als Rückfall** (ohne Modell, ~0 CPU):
      sox-`silence` mit Start-/Endschwelle, 1,5 s Stille beendet den Satz,
      harte Höchstdauer; Schwelle aus dem **nachgeführten Geräuschpegel**
      (0,35 s alle 30 s, RMS×100, +1, geklemmt 2–60, geglättet 0,7/0,3).
      Muster aus dem Whisplay-Chatbot (GPL-3.0, nachgebaut — HERKUNFT §4.5).
- [ ] **Satzstrom statt fertiger Antwort** (Voraussetzung für RTF > 1):
      LLM-Text beim Eintreffen an Satzzeichen trennen, kurze Sätze zu
      ≤ 60 Zeichen bündeln, jeden Satz sofort an die TTS, bis zu 5
      Synthesen parallel, Wiedergabe **in Reihenfolge**, leerer Ton einmal
      wiederholt, Watchdog „Dauer + 2 s". Text vorher für die TTS reinigen
      (URLs, Markdown, Emoji). Muster: HERKUNFT §4.5.
- [ ] **ALSA-Besitz**: vor der Aufnahme den Wiedergabeprozess beenden und
      ~500 ms warten, bis das Gerät frei ist; danach neu starten.
- [ ] STT: **fp32-Variante zuerst messen**, nicht die int8 (bisher war
      `nemo-fast-conformer-ctc-en-de-es-fr-int8` vorgesehen), Latenz messen
- [ ] TTS: **`low`/fp32 zuerst**, dann `medium`/fp32 zum Vergleich
      (bisher war `thorsten_emotional-medium-int8` vorgesehen)
- [ ] **RTF auf dem Gerät messen, nicht übernehmen.** Grenze: RTF < 1,2 für
      Dialog, sonst blockiert die Ausgabe
- [ ] TTS-Emotion an Mood koppeln (Architekturregel 4b)

### Mienenspiel beim Sprechen (`docs/DESIGN.md` §4.1)

- [x] **Ausdruck für „spricht“** (Regel „Sprechgesicht“): `SPEAK` mit vier Mundphasen,
      `LISTEN` für „hört zu“, `IDLE` für den Ruhezustand, `wartet` nach jeder
      Antwort; Tests und Gegenprobe stehen, am Pi noch nicht angesehen.
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

Die vier Muster aus `docs/DESIGN.md` §8 sind gebaut und verdrahtet.
Offen bleibt:

- [x] Rangordnung im Gedächtnis (nur lesbar gegen agentgeschrieben)
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
- [x] Systemd-Unit mit `StartLimitBurst=` in `[Unit]` (10p, Punkt 4) —
      Schritt 98, Abnahme am Gerät offen
- [ ] Prüfung des Speicher-Controllers, falls `MemoryMax=` je in die Unit
      kommt (10q) — die Unit trägt es bewusst nicht

## Phase 7 — Restliche Peripherie

- [x] RGB-LED an Mood-Glow (`display/led.py`, Verwalter nach Regel 7c,
      Muster als reine Funktionen der Zeit, Regel 7d) — 48 Prüfungen,
      Gegenprobe 7 Mutationen
- [x] Statuszeile angeschlossen (war gebaut, aber nie an den Renderer gegeben)
- [x] Taste verdrahtet: quittiert per LED, protokolliert
- [ ] Das Display zeigt einen Zustand erst nach dem Neustart des Dienstes
      richtig: Am Pi nach der Änderung von `SPEAK` ansehen und mit dem
      Dienstprotokoll abgleichen (Ausdruck, Statuszeile, LED).
- [x] Button: Gesten — *Erkennung erledigt 3.11. (`display/gesten.py`):
      kurz (<0,7 s), lang (0,7–2 s), halten (≥2 s, mit `halten_ende` für
      Push-to-Talk), doppelt, dreifach. Reine Zustandsmaschine (Regel 7d),
      `GestenTakt` weckt zur Frist; Sofortquittung per LED beim Drücken.
      Tests `test_gesten.py` 29 ok, Gegenprobe 8 ok.*
- [ ] **Bedeutung der Gesten** (DESIGN §3.4): kurz = Umgebungshören
      beenden/Gespräch öffnen, lang = Gespräch beginnen, halten =
      Push-to-Talk, doppelt = abbrechen, dreifach = zurück. Hängt am
      Audio-Prozess (Phase 5). Bis dahin: Protokoll und LED-Quittung.
- [ ] **Gestentest am Gerät:** einmal jede der fünf Gesten drücken und mit
      dem Protokoll (`Taste: Geste „…"`) vergleichen — die Erkennung ist
      geprüft, die Tastenmechanik am Gerät noch nicht.
- [ ] **Joystick (5-Wege) der neueren HAT-Revision** als Option prüfen:
      BOARD 32/33/31/29/37, active-low mit internem Pull-up, 20 ms
      Entprellung (HERKUNFT §4.2). Erst am Gerät feststellen, ob unsere
      Revision die Schalter hat — dann Opt-in im Panel, kein Zwang.
- [ ] Software-PWM bei Zwischenwerten: Backlight 50 % kostet ~9 % eines
      Kerns (1 kHz-Takt in Python). Kandidat: Backlight nur an/aus oder
      Takt senken, nach Sichtprüfung auf Flackern; zweiter Kandidat ein
      kleiner Rust-Helfer (HERKUNFT §4.6).
- [ ] Lautsprecher-Routing, Lautstärkeverwaltung — dabei **zwei** Dinge:
      `asound.conf` mit `dmix`/`dsnoop` (48 kHz, S16, period 1024,
      buffer 4096), damit Aufnahme und Ausgabe gleichzeitig gehen; und
      eine **wahrgenommene Lautstärkekurve** 0–100 % → Codec-Wert. Die
      Tabelle des Herstellers ist GPL-2.0 und wird nicht übernommen
      (HERKUNFT §4.4) — eigene Messung oder Formel.
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
- [x] `installer/lib/common.sh` — Ausgabe, Systemabfragen über `CHIMERA_ROOT`
- [x] Atomares Schreiben: Sidecar neben dem Ziel, dann `mv`
- [x] **`mktemp` geprueft** — ungeprueft leert es Zieldateien (I3)
- [x] **Leere Eingabe wird abgelehnt** (Regel 8a: stiller Erfolg). Gefunden
      durch den eigenen Test, nicht durch Nachdenken
- [x] `chimera-install` als Einstieg, Module nach Nummer, `--only`, `--list`
- [x] **Protokolldatei je Lauf, auch bei Erfolg** (Regel 10e)
- [ ] `--dry-run` und `--check` in den Modulen tatsaechlich auswerten
      (werden bisher nur durchgereicht)
- [x] Protokolle aufraeumen (Anzahl oder Alter begrenzen) —
      `common.sh:log_rotate`, die juengsten `CHIMERA_LOG_KEEP` bleiben
- [ ] `VERSION` ins System stempeln, `chimera --version`

### 8a1 — Laeufer (neu, aus Stufe B1)
- [x] **Exitcodes der Module** (neues I7): 0 = fertig, 1 = Befund,
      2 = Abbruch, 3 = Neustart noetig. Der Lauf wird von rc 3 NICHT mehr
      abgebrochen; der Wunsch wird EINMAL am Ende gemeldet, und der
      Gesamt-Exitcode sagt es weiter (3). Vorher endete der Lauf an
      Schritt 40 und kam auf einer frischen Installation nie darueber
      hinaus. Test: `tests/test-launcher-rc3.sh`, mit Gegenprobe gegen
      die alte Fassung
- [x] Zeilen an Fremddateien werden ebenfalls ATOMAR geschrieben
      (Regel I3): nicht mehr `>>`, sondern Inhalt lesen, Zeile anfuegen,
      in einem Zug ersetzen (`manifest_line` ueber `write_atomic`).
      Eine Bootkonfiguration, die mitten im Schreiben den Strom verliert,
      enthaelt sonst eine halbe Zeile
- [x] `write_atomic` uebernimmt ausser den Rechten auch **Besitzer und
      Gruppe** des Originals (`chown --reference`)

### 8a2 — Gepruefte Fehlerzweige (neu, aus Stufe B1)
- [x] `mktemp` wird in Schritt 20 GEPRUEFT (`common.sh:tmp_path`). Vorher
      stand dort `"${TMPDIR:-/tmp}/.name.$$"` — zeigte TMPDIR ins Leere,
      starb der Schritt unter `set -e` mit rc 1 und der Laeufer wertete
      das als Befund und lief weiter
- [x] **KVER-Falle** (`steps/10`, `steps/30`): `$(read_file … || uname -r)`
      greift nie, weil der Exitstatus einer Pipe der des letzten Glieds
      ist. Jetzt `common.sh:kernel_version`, leere Kennung = benannter
      Abbruch statt `/lib/modules//build`
- [x] Tests laufen TMPDIR-unabhaengig (`run-tests.sh` richtet sein eigenes
      Arbeitsverzeichnis ein); der Rundlauftest prueft den Pfad auf die
      Eigenschaft "liegt unter meinem Arbeitsverzeichnis" statt auf eine
      Positivliste /tmp|/var/tmp

### 8a3 — Fremdcode und Kernelmodul (neu, aus Stufe B1)
- [x] **Whisplay-Repo auf einen Commit festgelegt und die aufgerufene
      Datei gegen eine Pruefsumme geprueft** (I4, 5f). `network_git`
      nimmt einen Commit (shallow `fetch` auf die Kennung, gemessen),
      `fremddatei_pruefen` prueft die Datei. Hinterlegt ist
      Commit `c73051e6…` und sha256 `0767aba3…` (install_driver.sh,
      10.10.2026). Eine Abweichung wird BENANNT abgebrochen, nicht
      ausgefuehrt
- [x] **Kernelmodul wird per `modprobe` geprueft**, nicht nur per
      Dateiexistenz (`lib/module.sh:kernel_module_state`). Ein
      ABI-inkompatibles Modul liegt da und laedt trotzdem nicht. Test:
      `tests/test-module-state.sh`, mit Gegenprobe
- [x] **Whisplay ohne EEPROM erkannt** (`lib/display.sh`): Overlay-Eintrag
      in der Bootkonfiguration, ALSA-Karte, gebautes Modul — alles am
      Herstellertreiber belegt (dtoverlay=whisplay-soundcard,
      whisplaysound), kein Geraten. Welcher Treffer gilt, steht in
      `DISPLAY_QUELLE` und wird benannt. Test:
      `tests/test-display-signatur.sh`, mit Gegenprobe

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
      — Module 20/30/40 stehen im Code; was auf echter Hardware gelaufen
      ist, steht in `docs/HARDWARE-BEFUNDE.md`
- [x] WM8960 pruefen: **`modprobe` versuchen**, nicht nur Existenz pruefen
      (ein vorhandenes Modul kann ABI-inkompatibel sein) — die Pruefung
      steht jetzt in `lib/module.sh:kernel_module_state` und ist in
      Schritt 40 verdrahtet; fuer WM8960 wird sie im Codec-Modul
      benutzt, wenn es gebaut wird
- [ ] Overlay, kollidierende **umbenennen** statt loeschen
- [ ] Bootmethode erkennen statt `u-boot-update` vorauszusehen
- [x] Bootdateien vorher sichern
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
- [x] systemd-Unit und Dienstnutzer (Schritt 98) — Abnahme am Gerät offen:
      `systemctl is-active` nach 10 s, `NRestarts=0`
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

- **Web-Oberfläche** — jetzt Phase 4d (Modul-Plattform, 5m).
  Schlank, lokaler Port, kein Framework. Chimera muss ohne sie vollständig
  einsatzfähig bleiben (`docs/DESIGN.md` §11a). Gehört in eine eigene Phase
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
