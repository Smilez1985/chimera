# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier festgehalten.

Das Format folgt [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung [Semantic Versioning](https://semver.org/lang/de/) — mit
einer bewussten Abweichung: **ein Versionssprung bricht keine laufende
Installation.** Was ein Release an bestehenden Installationen ändert,
erledigt der Installer, nicht der Nutzer (siehe `docs/DESIGN.md`, Abschnitt „Versionierung").


## [0.1.0] — Pre-Alpha, nicht getaggt

**Nicht getaggt.** Pre-Alpha bleibt ungetaggt, bis eine Fassung auf echter
Hardware gelaufen ist. Die Versionsnummer markiert den Stand, nicht ein
Release.

Alles hier Genannte ist committet und geprüft. **Kein `[Unreleased]`-Block:**
Was noch nicht fertig ist, steht in `docs/ROADMAP.md`; was im Repo liegt,
zählt als released (Projektregel, Abweichung von Keep a Changelog).

### Hinzugefügt
- **Vorab-Laden im Hintergrund** (`installer/lib/vorab.sh`,
  `installer/chimera-prefetch`): Vor der Modulschleife startet ein
  abgekoppelter Helfer und holt die Downloads in Modulreihenfolge — zuerst
  die apt-Pakete (`apt-get install --download-only`, damit der Netzanteil aus
  Modul 20 herausfaellt), dann die pip-Wheels (`pip download`, in Schritt 50
  ueber `--find-links` mitbenutzt). Je Objekt eine Marke (`.teil` unterwegs,
  `.done` erst nach dem Erfolg atomar geschrieben, `.fehler` mit Grund); eine
  Marke beschleunigt nur, jeder Verbraucher prueft seine Ware selbst. Kann der
  Vorab-Lader nicht laden (kein Netz, kein pip im Systempython), laedt der
  Schritt wie bisher — es faellt nichts aus. `apt-get` wartet auf beiden
  Seiten ueber `DPkg::Lock::Timeout`, damit sich Vorab-Lader und Modul 20
  nicht gegenseitig abbrechen. Test `installer/tests/test-vorab.sh` 10 ok
  (apt- und pip-Weg werden ohne root/pip als uebersprungen gemeldet, nicht
  als gruen).
- **Blaupause: Regel „Warte-Schleife und Vorab-Laden" — kein Download bricht
  bei einem Netzaussetzer ab, und was der Lauf ohnehin braucht, wird im
  Hintergrund geholt.** Der Installer laedt, was er ohnehin braucht, kuenftig
  abgekoppelt und in Modulreihenfolge vor (`chimera-prefetch`), mit Marken je
  Objekt (`.done` nur nach Prüfsumme) und Rueckfall auf den eigenen Abruf —
  ein toter Prefetch darf einen Schritt nie blockieren. Kein paralleler
  `apt`-Lauf (dpkg-Sperre). Erst messen, dann bauen: Phase P1 (Dauer je Modul
  im Protokoll) ist gebaut, P2–P5 stehen in der Roadmap.
- **Changelog-Wächter** (`tests/test_changelog.py`): prüft Abschnittsnamen,
  dass jeder nur einmal vorkommt, die Reihenfolge nach Keep a Changelog,
  keinen `Unreleased`-Block und keine Punkte ohne Abschnittsüberschrift.
  Gegenprobe im Test selbst (sechs Fälle, dazu der alte Stand als Beleg).
- **Mojo:** Neuer Bereich `netz` — TCP-Probe auf öffentliche Adressen; fehlt das Netz, startet Mojo das WLAN neu (`nmcli`/`wpa_cli`/`wpa_supplicant`/`ifup`). Gezielt abfragbar mit `--mojo --bereich netz`.
- **Installer:** Bei HTTP 404 prüft der Abruf erst die Verbindung, wiederholt, und lässt bei Netzausfall Mojo das WLAN neu starten; nach drei Runden ist es ein benannter Befund statt 91 Sekunden Stillstand.

**Anzeige**
- **Prioritäts-Verwalter** (`chimera.arbiter`): löst auf, wer das
  Ausgabegerät bespielen darf. Quellen mit fester Basis-Priorität, ein
  Platz je Quelle, Auflösung in drei Stufen (Priorität → jüngster
  Zeitstempel → feste Quellenreihenfolge). Kurze Laufzeit plus
  Erneuerungsbedingung statt langer Laufzeit, damit kein Eintrag
  hängenbleibt, den jemand zu löschen vergisst.
- **Statuszeile** (`chimera.display.statusline`) in den unteren 40 Zeilen
  des 240×280-Panels, angeschlossen in `NoisyRenderer.show()`. Sieben
  Quellen von Abschaltmeldung bis Leerlaufbeschriftung.
- Der Verwalter ist **ein Baustein für zwei Nutzer** (Statuszeile jetzt,
  LED später). Die Vorlage nimmt an dieser Stelle bewusst zwei
  Umsetzungen in Kauf; das wäre die Doppelimplementierung, die im Projekt
  schon einmal drei Varianten derselben Logik erzeugt hat.
- Der Quellenkatalog prüft beim Start seine eigenen Abstände. Ein zu eng
  einsortierter Eintrag lässt die Statuszeile **nicht starten**, statt
  später „manchmal" falsch zu sein.
**Ausdruck**
- Mood-Vokabular, Validator und Registry (`chimera.mood`). Schema für das
  Sprachmodell und Prüfung entstehen aus **einer** Tabelle.
- Freie Zeichenformen: elf Grundformen mit relativen Koordinaten, Ebene
  und Bewegung. Benannte Bausteine sind Vorschläge — ein unbekannter Name
  wird übernommen und über eigene Formen dargestellt.
- Mischen und Variieren ohne Sprachmodell; Farben über den Farbton, damit
  Rot und Blau über Violett laufen statt über Grau.
- Übergänge über alle Felder, weich und hart. `fast_track` schaltet
  sofort, damit ein Schreck nicht einblendet.
- 41 Moods aus Noisy als Startbestand, ohne die Audio-Kopplung.
**Anzeige**
- Renderer aus Noisy übernommen und auflösungsrelativ gemacht: Bildgröße
  kommt vom Panel, Ausgabe über ein beliebiges `Panel`, Zustand statt
  Orchestrator.
- Bildausgabe in den Panelspeicher über SPI. Die Umrechnung nach RGB565
  läuft über `numpy` und ist rund 25-mal schneller als bildpunktweise
  (2,5 ms gegen 62,9 ms je Bild).
**Sprachmodelle**
- Anbieter-Registry mit Aufgaben und Gruppen. Der Rückfall geht **über
  Anbietergrenzen**: Ist Ollama weg, hilft ein zweites Ollama-Modell nicht.
- Ollama mit Platzhalter-Erkennung und Netzsuche; Claude getrennt nach Abo
  und API-Schlüssel, jede Antwort trägt ihre Herkunft.
- Client-Kennung für den Abo-Weg wird zur Laufzeit ermittelt (OpenMinis
  PR #407), mit Rückfallwert wenn die CLI fehlt.
- Ersteinrichtung sucht, schlägt vor und übernimmt — jede Zeile änderbar.
**Agent**
- Werkzeugschleife mit fünf Werkzeugen: Befehl ausführen, Datei lesen und
  schreiben, Verzeichnis auflisten, Gesicht setzen.
- Sicherheitsschranke aus openclawgotchi übernommen: keine Shell, keine
  Verkettung, keine Ersetzung, keine verschachtelten Interpreter, `sudo`
  gesperrt. Ergänzt um Netzsperre und Pfadschutz gegen `..` und Symlinks.
- Vorprüfung und JSON-Reparatur: abgebrochene Argumentangaben werden
  gerettet statt verworfen.
- Schleifenerkennung, die **vor** der Ausführung greift und dem Modell
  sagt, dass es feststeckt. Wechselnde Ergebnisse gelten nicht als Kreis.
- Kontextschwellen, gestaffelt nach Fenstergröße und geprüft gegen das
  Modell, das die Anfrage **tatsächlich bedient**.
- Der Agentzustand ist am Gesicht ablesbar: denkt, arbeitet, spricht,
  verwirrt.
- Skills im `SKILL.md`-Format mit **Voraussetzungsprüfung**: Ein Skill,
  dessen Programme fehlen, wird gar nicht erst angeboten — genannt wird er
  trotzdem, mit Grund.
- Gedächtnis mit Rangordnung: dauerhafte Notizen sind für den Agenten nur
  lesbar, Tageslogs schreibt er selbst. Beim Einspeisen wird gesagt, dass
  es Hintergrund ist und nicht Auftrag.
**Installer**
- `chimera-install` mit Modulen, `--only`, `--list`, `--dry-run`, `--check`.
- Modul 10 `preflight`: erkennt Board, Betriebssystem und Bootmethode
  getrennt, liest das Whisplay-EEPROM, meldet die Bauvoraussetzungen.
- Boardprofile für Pi Zero 2 W und Radxa ZERO 3W samt Tabelle bekannter
  Kombinationen. Unbekanntes führt zum Abbruch mit Auskunft, nicht zum
  Rateversuch.
- Protokoll je Lauf, auch bei Erfolg; die jüngsten 20 bleiben erhalten.
- Atomares Schreiben mit geprüftem `mktemp`; leere Eingaben werden
  abgelehnt.
**Blaupause**
- **Regel 10p:** Was beim Laden abstürzt, wird beim nächsten Start nicht
  wieder geladen (Startmarke, Quarantäne, gemeldeter Rückfall,
  `StartLimitBurst=`).
- **Regel 10q:** Speicher wird am Prozess gemessen (`VmRSS`/`VmHWM`/
  `VmSwap`) und vom Prozess selbst begrenzt. Anlass ist ein auf zwei
  Geräten unabhängig ausgewertetes Absturzbild einer Android-App.
- **Anzeige:** Der Installer setzt vor dem Anhalten der Dienste das Gesicht `UPDATE` (bernsteinfarben, fokussierte Augen, Sternchen); das Bild bleibt bis zum Dienststart stehen.
- **Sitzung:** Neue Operation `gesicht` am Sitzungs-Socket — die Anzeige lässt sich ansprechen, ohne die Sitzung zu bedienen.
- **Anzeige:** Fortschrittsbalken während des Installer-Laufs — eine Stufe gleich viel, „Updating…" darüber; der Stand überlebt den Selbstneustart und springt nicht zurück.
- **Anzeige:** LED zeigt den Verlauf — gelb blinkend während des Updates, grün bei Abschluss, ruhig gelb bei Befund, rot SOS bei Fehler.
- **Anzeige:** Jede Backlight-Änderung wird mit Grund protokolliert; der Zeichner schreibt eine Spur (`/run/chimera-setup/zeichner.log`).
- **Installer:** Bei einem Fehler ab rc 2 startet Mojo (`--mojo --miracle`) abgekoppelt als `chimera-mojo-install`.
- **Gateway:** Rust-Grundlage `rust/` mit dem Programm `chimera-tor`; die CI baut es statisch für aarch64 und legt es mit SHA-256 als Artefakt und auf `entwicklung` als Prerelease `rust-<commit>` ab.
- **Installer:** Neues Modul 55 lädt das Gateway-Binary `chimera-tor` zum Commit der Quelle (`rust-<commit>`), prüft SHA-256 und Version und legt es nach `/opt/chimera/bin`; Rückbau 55 entfernt es.
- **Gateway:** `chimera-tor --dienst` bedient einen Unix-Socket (`ping`, `status`); `--ping` fragt ein laufendes Gateway ab.
- **Gateway:** Ollama läuft über das Gateway (`chat`, `modelle`); der Dienst nutzt es, sobald es antwortet, und zeigt „ollama @ Host“. Ohne Gateway bleibt der direkte Weg.
- **Installer:** Neues Modul 99 legt den Nutzer `chimera-tor` und die Units `chimera-tor.socket`/`.service` an (Socket-Aktivierung, `MemoryMax=10M`); Rückbau 99 entfernt sie.
- **Installer:** Modul 00 hält den Commit der Quelle in `state/quelle-commit` fest.
- **Sitzung:** Alle Eingaben und Antworten laufen als nummerierter Ereignisstrom; der Dienst bedient dafür den Socket `/run/chimera/sitzung.sock` (`anmelden`, `frage`, `status`, `ping`). Mit Bezugsnummer `ref` und Umleitung fremder Sitzungs-Kennungen auf die Hauptsitzung.
- **Installer:** Modul 99 legt zusätzlich `chimera-sitzung.socket` an (Besitzer `chimera`, Gruppe `chimera-tor`, Modus 0660); Rückbau 99 entfernt es.
- **Installer:** `ca-certificates` ist zwingend; der Nachweis prüft, dass das Zertifikatsbündel vorhanden und nicht leer ist (Modul 20).
- **Installer:** Der Preflight (Modul 10) meldet eine unplausible Uhr als Befund, weil TLS Zertifikate gegen die Zeit prüft.
- **Sitzung:** Der Verlauf liegt auf der Platte (`sitzungen-ablage/<id>/verlauf.jsonl`) und übersteht Neustarts; Verdichten lässt das Protokoll unberührt.
- **Sitzung:** Wechsel der Hauptsitzung mit Übergabe (`wechseln`): `haupt` zeigt auf die neue Sitzung, die alte ist nur lesbar, die vorletzte wird archiviert, Archive über 3 Tage werden gelöscht. Neue Operationen `wechseln`, `sitzungen`, `lesen` am Sitzungs-Socket.
- **Gateway:** Web-Oberfläche als Plattform aus Modulen (`module/*/manifest.json`, eingebaut oder unter `/opt/chimera/web/module/`), Anmeldung mit Passwort, Chat-Modul am Strom der Hauptsitzung. Ohne `CHIMERA_WEB_PASSWORT_HASH` bleibt sie zu.
- **Gateway:** `chimera-tor --passwort-hash` erzeugt den Passwort-Hash aus der Standardeingabe.
- **Installer:** Modul 99 trägt das Web-Passwort ein: `CHIMERA_WEB_PASSWORT` im Lauf wird über stdin gehasht und nur der Hash landet in der `.env`; ein vorhandener Hash bleibt, das Gateway startet danach neu.
- **Installer:** `CHIMERA_RUST_LOKAL=<Pfad>` legt ein selbst gebautes `chimera-tor` ab (ohne CI, ohne Commit); Versions- und Laufprobe gelten unverändert.
- **Gateway:** Die Web-Oberfläche bedient nur Anfragen aus dem eigenen Netz (Loopback, private, Link-Local, IPv6-ULA); alles andere bekommt 403. `CHIMERA_WEB_LAN_NUR=0` schaltet das ab.
- **Gateway:** Web-Modul „Status“ zeigt CPU-Auslastung in % (gesamt und je Kern), Takt in MHz, Temperatur, Last, Arbeitsspeicher und Platte in MB/GB und %, Laufzeit und den Zustand der Chimera-Dienste, je mit Balken und Warnstufe; ein nicht lesbarer Wert erscheint als „nicht lesbar“, nie als 0.
- **Gateway:** `chimera-tor --module-neu NAME --titel-de …` legt ein Web-Modul aus der Vorlage an (Manifest und JavaScript, nur Variablen auszufüllen) und prüft es mit demselben Code wie das Laden; `--module-pruefen VERZ` prüft ein vorhandenes Modul und nennt seine SHA-256-Prüfsumme; `--module-vorlage` gibt die Variablen aus.
- **Gateway:** Ein Web-Modul darf nur Rechte aus einer festen Liste verlangen; ein unbekanntes Recht verwirft das Modul mit Meldung.
- **Gateway:** Neue Status-Messungen sind Sonden (`impl Sonde` plus eine Zeile in `sonden()`); die Oberfläche zeigt nur die gelieferten Zeilen.
- **Installer:** Modul 99 hält den laufenden Dienst kurz an, wenn es den Sitzungs-Socket erstmals einschaltet (systemd verweigert sonst den Start), und prüft den Zustand der Sockets statt nur das Manifest.
- **Gateway:** Datenschicht für Anbieter, Schlüssel, Katalog und Wahl (`config/anbieter`, `config/geheim`, `state/katalog`, `config/wahl`): atomares Schreiben, kaputte Dateien und Verweise ins Leere werden gemeldet und bleiben liegen, Schlüssel erscheinen in keiner Antwort. Neue Operationen am Gateway-Socket: `anbieter_liste`, `anbieter_setzen`, `anbieter_entfernen`, `schluessel_setzen`, `wahl_lesen`, `wahl_setzen`.
- **Installer:** Modul 99 legt die vier Ablagen an (Modus 700, Besitzer `chimera-tor`) und beschränkt das Schreiben der Gateway-Unit darauf (`ReadWritePaths`); `state/` ist danach 710 `root:chimera-tor`.
- **Gateway:** Netzsuche: Das Gateway sucht im eigenen Subnetz (bis /22) nach Ollama-Servern, trägt jeden Fund als Anbieter ein und füllt dessen Katalog; ein vom Nutzer entfernter Server bleibt entfernt. Aus mit `CHIMERA_NETZSUCHE=0`, Abstand mit `CHIMERA_NETZSUCHE_S` (Vorgabe 300 s).
- **Gateway:** Katalog eines Ollama-Servers mit Größe, Kontext und gemessener Werkzeugfähigkeit (`/api/show`); nicht Messbares erscheint als „unbekannt“. Neue Operationen am Socket: `katalog_aktualisieren`, `netzsuche`.
- **Web-Oberfläche:** Neues Modul „Ollama“: Server hinzufügen, entfernen, ein- und ausschalten, Modelle holen, ein Modell testen. Neue Rechte `anbieter-lesen` und `anbieter-schreiben`; nur eingebaute Module dürfen sie nutzen.
- **Anzeige:** Neuer Ausdruck `SPEAK` für den Zustand „spricht“: Blick geradeaus, kein Zubehör, Mund mit vier Phasen (zu, halb, offen, halb) im Kreis, jede Phase mehrere Bilder lang (`SPEAK_HALTE`, Vorgabe 3). Neuer Mundstil `speak` im Schema.
- **Anzeige:** Nach jeder Antwort meldet die Agentenschleife und die Telegram-Tür `wartet`, auch nach einem Fehler; das Gesicht bleibt nicht auf dem letzten Ausdruck stehen.
- **Tests:** `tests/test_gesicht_zustand.py` prüft die Zuordnung Zustand zu Ausdruck gegen die echte Bibliothek, die Mundphasen im echten Renderer und das `wartet` nach jeder Antwort; `tests/gegenprobe_gesicht.py` verfälscht dazu zwölf Stellen.
- **Tests:** `tests/test_regelnamen.py` verhindert neue nummerierte Regeln in `docs/DESIGN.md`; die bestehenden Nummern stehen als Altbestand-Liste, die nur kürzer werden kann. `tests/gegenprobe_regelnamen.py` prüft das.
- **Tests:** `rust/gegenprobe-daten.sh`, `rust/gegenprobe-anbieter.sh` und `rust/gegenprobe-netzsuche.sh` verfälschen je Stelle die Datenschicht, die Anbieter-Schnittstelle und die Netzsuche; `tests/test_cli_doku.py` prüft, dass jede Gegenprobe in `docs/CLI.md` steht.
- **Dokumentation:** `docs/research/ACP.md` klärt die drei Protokolle mit dem Kürzel ACP und liest den Agent Client Protocol samt Android Studio Rabbit 2; `docs/research/ACP-MCP.md` vergleicht ihn mit MCP; die Regel „ACP“ legt Chimera als Agent hinter einer eigenen Tür fest. Die Regel „MQTT“ legt einen Broker in Rust fest, der gespeicherte Moods auf dem Display auslöst; PaKaChi-SM ist das Vorbild.
- **Dokumentation:** `docs/research/MOJO.md` hält fest, was Mojo (Gesundheitsprüfung mit Reparaturstufen) ist, was für Chimera taugt und was am Gerät gemessen wurde; die Regel „Mojo“ in `docs/DESIGN.md` beschreibt den Bau.
- **Dokumentation:** `docs/CLI.md` listet alle Befehle, Optionen und Umgebungsvariablen nach Kategorie, zweisprachig; `tests/test_cli_doku.py` prüft sie in beide Richtungen gegen die Programme.
- **Anzeige:** Eigenes Treiberpaket `chimera.displays` — Whisplay-LCD, LED,
  Backlight und Taste laufen ohne Herstellercode; ein neues Panel ist ein
  Ordner mit `display.json` und `panel.py`.
- **Anzeige:** Erkennung ohne Treiber (`python3 -m chimera.displays
  erkennen`): Panel-Kennung per SPI, Codec per I2C; Spuren früherer
  Einrichtung wählen nicht mehr.
- **Ton:** Overlays werden zur Laufzeit geladen (`python3 -m chimera.displays
  ton whisplay`); die Bootkonfiguration bleibt neutral, damit dieselbe
  Karte auch in GamePi13 und E-Paper-Geräten startet.
- **Installer:** Python-Abhängigkeiten werden mit Versionsprüfung
  hergestellt — Fehlendes oder Veraltetes wird geholt, Vorhandenes nicht
  angefasst; numpy gehört jetzt dazu.
- **Anzeige:** Die RGB-LED zeigt den Zustand (hört zu, denkt, spricht,
  Warnungen) und sonst gedimmt die Farbe des Gesichts; die Seitentaste
  quittiert per LED.
- **Installer:** Modul 46 misst die Mikrofone der Anzeige und wählt die
  brauchbaren (beide, links, rechts); Spracheingabe nimmt über das Gerät
  `chimera_mikro` auf.
- **Boot:** `chimera-hardware.service` erkennt bei jedem Start die Anzeige,
  lädt den Ton und übergibt beides an den Dienst — nach einem Kartentausch
  startet das Gerät ohne Installerlauf richtig (`chimera-install --hardware`).
- **Protokolle:** Der Dienst schreibt sein Protokoll als Datei und bringt es beim
  Stoppen und in Ruhezeiten (spätestens stündlich) auf die Speicherkarte.
- **Speicher:** Der Installer richtet zram (75 % des Arbeitsspeichers) und
  eine nach Kartengröße gestaffelte Auslagerungsdatei ein (2/4/8/16 GiB);
  der Rückbau stellt den früheren Zustand wieder her.
- **Dienst:** Chimera läuft als systemd-Dienst `chimera.service` unter
  eigenem Systemnutzer `chimera`, startet nach einer Aktualisierung neu
  und begrenzt Neustarts bei wiederholtem Absturz.
- **Dienst:** `python -m chimera --dienst` läuft ohne Terminal bis zum
  Stoppsignal; Telegram startet mit, wenn ein Token eingetragen ist.
- **Rückbau:** `chimera-uninstall` entfernt Dienst und Dienstnutzer; ein
  schon vorhandener Nutzer und die Nutzerdaten bleiben.
- **Rueckbau:** Die Python-Umgebung (venv samt Verdrahtung) laesst sich
  mit Rueckbauen — `chimera-uninstall` fuert den Schritt 50 jetzt mit.
- **Konfiguration:** Die Umgebungsvorlage `.env.example` wird als
  `/etc/chimera/.env` abgelegt (600, nur Platzhalter) — ohne eine von
  Hand ausgefuellte Datei zu ueberschreiben. Was fehlt, nennt
  `--pruefen`.
- **Installer:** Ein Modul kann "eingerichtet, Neustart noetig" (rc 3)
  melden, ohne den Lauf abzubrechen. Der Neustartwunsch wird EINMAL am
  Ende gemeldet, der Gesamt-Exitcode bleibt 3.
- **Installer:** Der Whisplay-Herstellerinstaller wird auf einen Commit
  festgelegt und vor dem Aufruf gegen eine Pruefsumme geprueft. Ein
  geaenderter Fremdstand bricht BENANNT ab, statt als root ausgefuehrt zu
  werden.
- **Installer:** Der Whisplay-HAT wird auch ohne programmiertes EEPROM
  erkannt — ueber den `dtoverlay`-Eintrag, die ALSA-Karte und das gebaute
  Kernelmodul. Welche Quelle gegriffen hat, wird benannt.
- **Installer:** Kernelmodule werden per `modprobe` geprueft, nicht mehr
  nur per Dateiexistenz — ein ABI-inkompatibles Modul meldet keinen
  Erfolg mehr.
**Werkzeug**
- **GitHub Actions** (`.github/workflows/tests.yml`): Python-Tests auf 3.11
  und 3.13, Installer-Tests unter **dash und BusyBox** (beide unterscheiden
  sich von bash, aber nicht gleich), Syntaxprüfung aller Skripte, dazu ein
  Trockenlauf gegen ein erfundenes Wurzelverzeichnis — der prüft, dass der
  Installer im Trockenlauf wirklich nichts anfasst, auch keine Sicherung.
**Installer: Abhängigkeiten, Bestand, Anzeigen**
- **Modul 20 (`20-pakete.sh`) läuft vor allem anderen.** Es prüft und holt,
  was die späteren Module brauchen — und prüft danach, ob das Werkzeug
  wirklich *aufrufbar* ist, nicht nur ob apt Erfolg meldet. Anlass: Der
  erste echte Lauf scheiterte mitten in der Arbeit an fehlendem `make`.
- **Bestandsverzeichnis (`lib/bestand.sh`, `/var/lib/chimera/bestand.tsv`).**
  Jede Änderung am System wird mit Modul, Art und Pfad festgehalten —
  Grundlage für eine spätere Deinstallation. Entscheidend ist die
  Unterscheidung `neu` gegen `vorher_da`: `apt-get install` meldet Erfolg
  auch für bereits installierte Pakete, und was es vor Chimera gab, darf
  eine Deinstallation nicht entfernen.
- **Modul 30 (`30-headers.sh`) holt die Kernel-Headers** — eigenes Modul,
  weil das richtige Paket an Board *und* Kernelfassung hängt. Geprüft wird
  das Bauverzeichnis, nicht der Paketstatus: Ein Paket kann installiert
  sein und trotzdem zur falschen Kernelfassung gehören.
- **Modul 40 (`40-anzeige.sh`) richtet die Anzeige ein**, über eine
  Registry (`lib/anzeigen.sh`) statt über Fallunterscheidungen: `whisplay`,
  `st7789`, `epaper`, `keine`. Eine neue Anzeige ist ein Eintrag. Der
  Herstellertreiber wird aufgerufen, nicht nachgebaut — aber mit
  gesicherter Bootkonfiguration, eigenem Protokoll und Prüfung am
  Ergebnis. Exitcode 3 heißt „Neustart nötig", also weder Erfolg noch
  Fehlschlag. Nimmt den Nutzer außerdem in die Gruppen `audio`, `spi`,
  `gpio` und `i2c` auf — ohne sie meldet `aplay -l` „keine Soundkarten",
  obwohl die Karte läuft.
- **Netzzugriffe überleben Unterbrechungen (`lib/netz.sh`).** Ein Ausfall
  ist eine Pause, kein Ende: Downloads setzen fort (`curl -C -`), zwischen
  den Versuchen wird auf das Netz gewartet, und **jeder** Abbruch wird
  gemeldet. Ein stiller Wiederholungsversuch sieht von außen aus wie ein
  Hänger. Erreichbarkeit wird über TCP geprüft, nicht über ICMP; fehlt das
  Werkzeug dafür, heißt das „nicht prüfbar", nicht „nicht erreichbar".
**Bedienschnittstelle (H4)**
- **Sitzung und Kanal** (`chimera.agent.session`). Der Kern von Regel 5d:
  ein Agent, ein Verlauf, beliebig viele Türen. Eine Sperre serialisiert
  den Zugriff — der Agent ist nicht wiedereintrittsfähig, zwei
  gleichzeitige Läufe würden sich den Verlauf überschreiben. Ein Kanal
  beschreibt nur Ein- und Ausgabe und hält keinen eigenen Zustand
  (Regel 5i).
- **Telegram** (`chimera.bot.telegram`), ohne Fremdbibliothek — die
  Bot-API ist HTTPS mit JSON, das kann die Standardbibliothek. Auf 512 MB
  ist jede vermiedene Abhängigkeit eine gesparte. Positivliste erlaubter
  Absender ist Pflicht (Regel 5j): Ohne Liste startet der Bot nicht.
- **Der Zusammenbau** (`chimera.app`, `python3 -m chimera`). Den gab es
  vorher nicht — der Agent wurde nirgends instanziiert. Setzt nichts
  voraus: ohne Anbieter, ohne Panel, ohne Skills läuft es und sagt, was
  fehlt.
**Anzeige**
- **Der Renderer wird jetzt angeschlossen und gestartet.** Vorher setzte
  das Gesicht Ausdrücke auf einen Zustand, den niemand las — ein offenes
  Ende nach Regel 10h. `start_display()`/`stop_display()` führen ihn als
  Faden; das Panel wird durchgereicht statt weggeworfen (Regel 7b).
- **Die Bildrate gehört zum Panel** (Regel 7a). Ein LCD will 15 Bilder je
  Sekunde, E-Ink eines alle paar Sekunden; bei `fps = 0` zeichnet der
  Renderer nur auf Anstoß. Damit trägt derselbe Renderer beide
  Anzeigearten, ohne Sonderweg — ein neues Panel setzt eine Zahl.
- `tools/check-globals.py` — findet Namen, die eine Funktion als global
  liest, die es aber nicht gibt. Statisch, ohne Ausführung.

- **Mojo macht nach einem Neustart weiter.** `chimera-mojo-fortsetzung.service`
  läuft einmal nach dem Start — nur wenn der Marker `state/mojo-fortsetzen.json`
  steht (`ConditionPathExists`, kein Zeitgeber), geordnet **nach** den Diensten,
  und ruft `chimera-tor --mojo --miracle --fortsetzen`. Im Manifest, im
  Rückbau abgedeckt, Nachweis über `is-enabled` (die Unit ist absichtlich meist
  inaktiv). Test `test-mojo.sh` 81 ok, sieben neue Mutationen in
  `counter-check-mojo.sh`.
- **LED meldet jeden Ausgang des Installer-Laufs.** Bisher gab es ein
  Abschlusszeichen nur, wenn der Lauf die Dienste angehalten hatte — ein Lauf
  ohne Änderung („alles aktuell") zeigte gar nichts. Jetzt: `ok` grün fest,
  `nichts` grün langsam blinkend, `befund` gelb fest, `neustart` blau blinkend,
  `fehler` rot SOS. Liegt der Dienst still auf den Leitungen, meldet der
  Installer über den Sitzungs-Socket (neue Operation `led`), der Renderer setzt
  die Farbe (neue LED-Quelle `installer`, Muster `sos`).
- **Ruhe-Bildrate** (`NoisyRenderer.RUHE_FPS`, Vorgabe 2 Bilder/s; `0` heißt
  „nicht zeichnen"): Der Zustand bestimmt die Bildrate. Volle Rate nur bei
  Blinzeln, Sprechen/Reden, Partikeln, Takt/gehörtem Pegel, Bewegungsphysik
  und nach einem Zustandswechsel (`wecken(sekunden)`); sonst zeichnet die
  Schleife mit der Ruhe-Rate. Am Pi gemessen: 35,5 % → 10,8 % eines Kerns,
  577 → 134 `write()`/s, 383 → 86 KB/s. Test `test_bildrate.py` 25 ok,
  Gegenprobe `gegenprobe_bildrate.py` 8 ok (sieben Mutationen).
- **Taste ohne Abfrage im Takt:** `Leitungen.request(kanten=…)` fordert
  Kantenereignisse an (`event_buffer_size`, `GPIO_V2_LINE_FLAG_EDGE_RISING/
  FALLING`), `ereignisse()` wartet im Kern auf die Flanke. Die Tastenschleife
  fragte vorher alle 5 ms ab (200 `ioctl`s je Sekunde, ~1,3 % eines Kerns);
  ohne Kanten greift die Abfrage als Rückfall. Fremde Ereignisse werden
  aufgehoben, nicht verworfen. Test `test_gpio_kanten.py` 23 ok, Gegenprobe
  8 ok. Am Pi: Gesamtlast 10,8 % → 9,5 %, Protokoll „Taste:
  Kantenereignisse“.
- **LED-Taktfrequenz je Anzeige einstellbar** (`display.json` →
  `led_frequenz_hz`, Vorgabe 100 Hz, Whisplay 60 Hz). Drei Kanäle takten
  damit billiger: am Pi 9,6 % → **8,1 %** eines Kerns im Leerlauf. Am Gerät
  geprüft, dass 60 Hz nicht flimmern.
- **Tastenentprellung über den Pegel:** Die Taste prellt am Gerät bis 136 ms;
  Flankenketten wurden als mehrere Klicks gezählt (ein Druck ergab „dreifach").
  Jetzt weckt die Flanke nur den Faden, der auf 80 ms Ruhe wartet und dann den
  echten Pegel liest — gemeldet wird der Übergang, nicht die Flanke. Am Gerät
  belegt: fünf Gesten, je eine Protokollzeile.
- **Fünf Tastengesten** (`display/gesten.py`): kurz (<0,7 s), lang (0,7–2 s),
  halten (ab 2,0 s, während gehalten), `halten_ende` als Gegenstück (für
  Push-to-Talk), doppelt und dreifach im Klickfenster (0,8 s). Reine
  Zustandsmaschine nach Regel 7d; `GestenTakt` wartet auf die Frist und weckt
  sie. Der Druck quittiert sofort per LED, die erkannte Geste geht ins
  Protokoll. Test `test_gesten.py` 29 ok, Gegenprobe 8 ok.
- **Blinzeln hängt an der Uhr, nicht an der Bildzahl:** Abstand 3,0–8,7 s,
  Dauer 0,20–0,47 s (vorher 45–130 bzw. 3–7 Bilder, was nur bei 15 Bildern/s
  stimmte). Die Ruhe-Schleife schläft genau bis zum Blinzelbeginn, statt mit
  festem Vorlauf zu laufen — ein Vorlauf von 0,6 s kostete je Blinzeln fast
  eine Sekunde voller Rate (14,6 % statt 10,8 %).
- **Installer: die Arbeit läuft abgekoppelt** (`chimera-installhelper`, eine
  transiente `oneshot`-Unit). `chimera-install` startet sie und kehrt zurück;
  ohne root wird der Aufruf abgelehnt, statt in der SSH-Sitzung zu laufen, und
  ein zweiter Aufruf hängt sich an den laufenden Lauf, statt einen zweiten zu
  beginnen.
- **Installer: die Klammer um den Lauf** — Dienste anhalten, Dateien tauschen,
  in der gemessenen Reihenfolge starten (Sockets **vor** Diensten), danach der
  Nachweis, dass alles läuft. Das Gateway wird dabei über seinen Socket
  **geweckt** und nicht direkt gestartet: Ein direkter Start scheitert am Pi,
  weil `LISTEN_FDS` fehlt.
- **Installer: SSH-Schutz** gegen den OOM-Killer — Drop-in
  `ssh.service.d/10-chimera-oom.conf` mit `OOMScoreAdjust=-900`. Anlass:
  Sitzungsprozesse standen auf `oom_score_adj=0` und waren die ersten Opfer,
  wenn die Speichergrenze griff.
- **Anzeige: Komponenten-Pipeline, Blink-Engine, Nachlauf-Effekte und
  Software-Dimming** kamen mit dem Renderer aus Noisy und laufen auf Zuständen
  statt auf einem Orchestrator; Muster sind reine Funktionen der Zeit
  (Regel 7d).
- **Ausdruck: Herkunft, Anlage- und Nutzungszeit** stehen an jedem
  Bibliothekseintrag; Einträge, die nur für einen Anlass gebaut wurden, werden
  nach dem Gebrauch wieder aufgeräumt.
- **Werkzeug:** `tools/contact-sheet.py` legt alle Ausdrücke als
  Kontaktbogen auf ein Blatt — Muster auf einen Blick statt eine Datei je
  Mood.

### Geändert
- **Vorab-Laden: idempotent, abbruchsicher, ohne eigenen apt-Weg.** Vier
  Änderungen, alle aus derselben Regel („installieren, nur was fehlt"):
  - **`apt` ist wieder draußen.** Es hat schon einen Eigentümer
    (`network_apt` in `lib/network.sh`) und teilt sich mit Modul 20 dieselbe
    Sperre — überlappen kann es nicht (gemessen: 25 s für null Pakete).
    Vorgabe smilez: die Pakete werden ohnehin geladen, wann ist egal.
  - **Geladen wird nur, was fehlt** (`vorab_wheel_da`): Der Bestand
    entscheidet, nicht eine Marke von gestern. Ist alles da, kostet der
    Vorab-Lauf einen Blick ins Verzeichnis und keine Netzverbindung.
  - **Fehlt `pip` selbst, wird es geholt** — über `network_apt`
    (`python3-pip`, jetzt Pflichtpaket in Modul 20), nicht gemeldet und nicht
    übersprungen. Danach läuft der Abruf normal weiter.
  - **Kein harter Abbruch:** `pip download` läuft in derselben Warte-Schleife
    wie `network_fetch` und Modul 50 (Netz abwarten, erneut versuchen);
    teilweise geholte Wheels bleiben in `wheels.teil` und werden beim
    nächsten Versuch nicht erneut geholt. Erst nach allen Versuchen entsteht
    eine `.fehler`-Marke mit Grund.
  Tests: `installer/tests/test-vorab.sh` 46 ok (drei Fälle neu bzw. geschärft:
  fehlender pip ist ein Befund mit Grund, vorhandene Wheels werden erkannt,
  vollständiger Bestand meldet „nichts zu holen" mit rc 3). Gegenproben
  gemacht (apt-Zeile zurück in die Liste → rot; Bericht stummgeschaltet →
  zwei rot).
- **P5 gemessen (Pi, 5.11., `4f06a3c`) — der apt-Teil des Vorab-Ladens bringt
  nichts.** Lauf mit gelöschten Marken: `pip-wheels` 16 s für 22 MB
  (Pillow 13.0.0 + numpy 2.5.4), `apt-debs` 25 s für **0 Pakete** (alle schon
  installiert) — die Zeit war Warten auf die apt-Sperre neben Modul 20/30.
  Der apt-Weg kann nicht überlappen; auf einer Erstinstallation verschiebt er
  die Downloadzeit nur von Modul 20 in den Vorab-Lader. Empfehlung und
  Entscheidungspunkt in `DESIGN` und `ROADMAP` festgehalten. Moduldauern
  dieses Laufs (20: 1 s, 50: 6 s) zeigen auf bestücktem Gerät keinen Gewinn;
  das war auch nicht zu erwarten.
- **Der Vorab-Lader läuft in einer eigenen transienten Unit**
  (`systemd-run --unit=chimera-prefetch --collect --service-type=oneshot`),
  nicht mehr als `nohup`-Kind des Installers. Am Pi 5.11. gemessen: Der
  Installer läuft selbst als transiente Unit (`chimera-installhelper.service`,
  `KillMode=control-group`); das Kind hing in dieser Cgroup und wurde beim
  Ende des Laufs erschossen — mitten im Download, ohne `.done` und ohne
  `.fehler` (erster Lauf: Pillow halb geholt, `wheels/` leer). Neu:
  `vorab_starten()` in `installer/lib/vorab.sh` (Rückfall auf `setsid`, wenn
  kein `systemd-run` vorhanden ist), Rückgabe 0/1/2 und eine Meldung je Fall
  im Protokoll — ein nicht startbarer Vorab-Lader ist ein Befund, kein
  stiller Erfolg. Tests: neun Prüfungen mit einer `systemd-run`-Attrappe
  (Unit-Name, `--collect`, `--service-type`, Programm kommt an, Name belegt →
  zweiter Versuch → rc 1, abgeschaltet startet nicht); Gegenprobe gemacht
  (Unit-Name mutiert → zwei rot).
- **Abschalter fürs Vorab-Laden** (`CHIMERA_PREFETCH_RAD=0`): Der in
  `lib/vorab.sh` angekündigte Schalter wurde nirgends gelesen — er war ein
  Wort ohne Wirkung. Er wird jetzt an genau einer Stelle geprüft
  (`vorab_an()`), Installer und `chimera-prefetch` fragen dort, und
  `vorab_alle()` meldet rc 2 statt zu laden. Gebraucht wird er zum Messen
  (vorher/nachher) und als Notaus. Tests: drei neue Prüfungen in
  `installer/tests/test-vorab.sh` (Vorgabe an, `0` ab, abgeschaltet
  entstehen keine Marken) — Gegenprobe gemacht: ohne den Riegel in
  `vorab_alle()` fallen zwei davon, mit ihm keine.
- **DESIGN, Regel „Warte-Schleife und Vorab-Laden": Teil 2 steht nicht mehr
  als „entworfen" da.** Der Stand ist eingetragen, samt der Abweichungen:
  kein Eingriff in `network_fetch` (die Verbraucher finden ihre Ware über
  den apt-Cache bzw. `--find-links`), keine Haltemarken (bei zwei Objekten
  mehr Maschinerie als Nutzen), Whisplay-Klon und `rust-<commit>` bleiben
  draußen (3 s / 1 s rechtfertigen keine eigene Marke). Ebenso die
  offene Messung: auf einem bestückten Gerät ist nichts zu holen, der
  Nutzen gilt bis zum Beleg als **unbelegt**.
- **`lib/vorab.sh`: Der Kopf-Kommentar widersprach der Liste.** Er sagte
  „Was NICHT hierher gehört: apt" — die Liste holt seit `3f79030` genau das.
  Jetzt steht dort, warum apt dazugehört und nur `--download-only` sein darf.
- **Der Snapshot vor einem Neustart ist ein Verzeichnis, kein Archiv**
  (`state/mojo-snapshot/` mit `stand.tsv` und den Kopien unter ihrer Nummer).
  Zurückrollen ist damit ein Kopieren mit Prüfsummenvergleich — kein
  Entpacken, keine Abhängigkeit von einem Packprogramm. `DESIGN` nennt jetzt
  auch die Marker-Felder `grund` und `befunde`: der zweite Lauf kennt den
  Bericht des ersten nicht mehr.
- **Herkunft um die PiSugar-Repos erweitert** (`HERKUNFT `docs/HERKUNFT.md`, Abschnitt „PiSugar Whisplay"`): Lizenzgrenze
  je Teilbaum, der Stand unseres Treiber-Nachbaus gegen den heutigen
  Upstream (nur Joystick, Pull-up und MangoPi sind dazugekommen), und die
  vier Sprachmuster, die nachgebaut werden statt kopiert. Ergebnis in
  `ROADMAP`: Energie-VAD mit nachgeführtem Geräuschpegel, Satzstrom-TTS,
  ALSA-Besitz, `dmix`/`dsnoop`, eigene Lautstärkekurve, Gesten der Taste.
- **Unbekannte Boards brechen den Installer nicht mehr ab** (Regel 10k).
  Unbekannt heißt ungetestet, nicht unvereinbar: Wer Chimera auf einem
  Pi 4 versuchen will, darf das nach einer ehrlichen Warnung und einer
  bewussten Bestätigung. Was weiterhin **nicht** passiert, ist ein
  geratenes Overlay in der Bootkonfiguration — dieser eine Schritt kostet
  bei einem Gerät ohne Bildschirm den Ausbau der SD-Karte. Ohne Profil
  laufen die boardunabhängigen Module, die bootnahen melden sich ab.
  Exitcode 1 heißt jetzt „kein Profil, läuft weiter", 2 „niemand hat
  zugestimmt"; nicht-interaktiv braucht es `CHIMERA_ASSUME_YES=1`.
- Die CPU-Temperatur wird über eine Instanzeigenschaft gelesen, nicht über
  eine Modulkonstante — auf dem Radxa heißt die Zone anders als auf dem Pi
  (Regel 10c).
- **`docs/DESIGN.md`, Abschnitt „Keine Secrets im Repo" verschärft und als Regel 13a gefasst:** Vor jedem Push läuft eine
  Prüfung auf Geheimnisse und Personenbezug, und sie belegt vorher, dass
  sie überhaupt etwas finden kann. Hinzugekommen in der Liste des
  Unerwünschten: private IP-Adressen, MAC-Adressen, Heimnetz-Hostnamen,
  private Mailadressen. Das Prüfwerkzeug selbst bleibt außerhalb des
  Repos — es nennt die Muster und damit die Form der geschützten Werte.
- **Installer:** Ein Zeichner je Lauf, der den Selbstneustart übersteht und vom neuen Prozess übernommen wird.
- **Anzeige:** Nur Schritt 40 gibt das Panel frei — und auch nur, wenn er die Anzeige wirklich prüfen muss. Das Display bleibt dadurch hell.
- **Anzeige:** Der bisherige Ausdruck `TALK` (Ohr, gerader Mund, Blick zur Seite) heißt jetzt `LISTEN` und gehört dem Zustand „hört zu“; das bisherige lächelnde `LISTEN` heißt `IDLE` und ist der Ruhezustand. Die Bibliothek hat 42 Ausdrücke.
- **Gateway:** `anbieter_speichern` nimmt die Adresse von der Ablehnungsliste der Netzsuche, wenn der Nutzer einen entfernten Server wieder hinzufügt.
- **Installer:** `manifest_init` setzt `state/` nur noch beim Anlegen auf 700 und überschreibt spätere Rechte nicht mehr.
- **Anzeige:** `chimera.display.panel` ist nur noch die Fassade; welche
  Anzeige geöffnet wird, sagt `CHIMERA_ANZEIGE` bzw. `state/anzeige`, der
  Dienst erkennt nicht mehr selbst. Läuft er blind, steht der Grund in der
  Statuszeile.
- **Installer:** `lib/display.sh` liest `display.json` des Anzeigemoduls
  statt einer eigenen Tabelle; Schritt 40 richtet nur noch den Ton über
  den Herstellerinstaller ein, das Panel braucht ihn nicht mehr.
- **Installer:** Zeilen an der Bootkonfiguration werden atomar
  geschrieben statt per `>>` angehaengt.
- **Installer:** Geprueftes Anlegen von Zwischendateien in Schritt 20;
  ein unbrauchbares `TMPDIR` bricht BENANNT ab statt still weiterzulaufen.
- **Installer:** Kernelfassung kommt aus `kernel_version()`; die
  Fallback-Falle (`read_file … || uname -r`) ist behoben.
- **Installer:** Die Verdrahtungsdatei `chimera.pth` steht als Art
  `datei` (mit Pruefsumme) im Manifest, nicht mehr als `verzeich`.
- **Tests:** Die Testsuite richtet ihr Arbeitsverzeichnis selbst ein und
  haengt nicht mehr an einem bestimmten `TMPDIR`.
- **Anzeige:** numpy wird erst beim ersten Bild geladen; die Anzeige-Abfragen
  des Installers (Profil, Erkennung, Ton, Mikrofon) starten schneller.
- **Installer:** Der Abgleich beim Start dauert weniger als halb so lange;
  der Dienst startet entsprechend früher.
- **Installer:** Der Nachweis der Python-Umgebung sucht nicht mehr im Netz
  nach Anbietern und öffnet das Panel nicht mehr.
- **Installer:** Modul 55 verlangt kein neues Binary, wenn der `rust/-Baum`
  unverändert ist. `state/rust-stand` hält Commit, Hash des Baums und
  Version fest; bei Gleichheit bleibt das vorhandene Binary liegen
  (`Rust unverändert seit <commit>`) — ohne Netz, ohne Befund, ohne
  CI-Build. Geprüft werden dabei Prüfsumme, Lauf und Version; ein
  geänderter Baum oder eine neue `VERSION` hebt es auf. Anlass: Jeder
  Doku-Commit erzeugte einen Befund und einen unnötigen CI-Build.

- **Der Installer ist der einzige Weg auf ein Gerät** (DESIGN Regel 13):
  Zuordnung „Changelog-Bereich → Modul" in `docs/INSTALLER.md`, Abschnitt „Was welches Modul aus dem Changelog einspielt", neues
  Werkzeug `tools/abgleich.sh` vergleicht Quellbaum, eingespielten Stand
  und `state/quelle-commit`. Anlass: vier Commits lagen nur per `scp` in
  `productive/code` und wurden beim nächsten Boot-Abgleich zurückgerollt.
- **Installer: die Klammer greift nur bei echter Änderung** — unveränderter
  Quellstand und erfüllte Abhängigkeiten lassen die Dienste weiterlaufen;
  nichts wird angefasst, nichts angehalten.
- **Installer: zram wird nur noch angelegt, wenn es fehlt.** Läuft es, bleibt
  der Speicherschritt ganz aus — kein `swapoff -a`, kein Dateischritt, keine
  Änderung der Konfiguration.
- **Installer: der abgekoppelte Helfer hat einen Laufzettel**
  (`/run/chimera-installhelper.status`). Die transiente Unit lässt sich über
  `systemctl` nicht abfragen („Failed to open /run/systemd/transient/…") und
  läuft trotzdem; der Zustand wird deshalb neben der Unit geführt, statt aus
  ihr gelesen.
- **Installer: `write_atomic` übernimmt neben den Rechten auch Besitzer und
  Gruppe** des Originals (`chown --reference`) — eine ersetzte Datei behält
  damit ihre Zugehörigkeit, auch wenn sie als root geschrieben wird.
- **Anbieter: `Connector` kennt jetzt `supports_tools`, `context_window`,
  `supports_streaming`, `cost_class` und `access`** — die Wahl eines Ziels
  entscheidet über Eigenschaften, nicht über einen Namen.
- **Installerschritt 50 installiert Python-Abhaengigkeiten ohne `--upgrade`.**
  `pydep_ensure` uebergibt pip nur die *nicht erfuellten* Anforderungen
  (fehlend oder zu alt). Mit `--upgrade` haette pip auch eine *genuegende*
  Fassung auf die jeweils neueste gehoben — ohne bleibt die erfuellte stehen.
  Getestet mit `test-python-env.sh` (50 ok, auch der Fall „zu altes numpy im
  Angebot"), also keine Verhaltensaenderung an einer Messstelle: pip
  installiert eine unerfuellte Anforderung ohnehin. Ehrlich dazu: Der
  beobachtete Fall `numpy 2.5.4` statt `1.26.4` kam **nicht** von `--upgrade`,
  sondern von der Anforderung ohne Obergrenze (`numpy>=1.26`) — das steht als
  offener Punkt in der Roadmap.
- **`installer/tests/test-python-env.sh` laeuft ohne Netz.** Pillow und numpy
  kommen aus Attrappen-Wheels, die der Test mit `tests/fake-wheel.py` selbst
  baut (`PIP_NO_INDEX=1`, `PIP_FIND_LINKS`); auch `pip install --upgrade pip`
  findet nichts und scheitert folgenlos. Anlass: Der Test holte die echten
  Pakete von PyPI — im Sandbox wurde der Lauf dabei abgeschossen, und das
  Ergebnis hing davon ab, ob und wie schnell der Rechner Internet hat.
  **Belegt:** mit vergiftetem Proxy (`http_proxy=http://127.0.0.1:9`) 50 ok,
  0 fehlgeschlagen, unter dash und BusyBox. Die Attrappen tragen nur Metadaten
  und ein leeres Modul; deshalb prueft der Test Anzeigemodule ueber die
  Registry (`panel_klasse`) statt durch Zeichnen, und `--pruefen` meldet
  „Gesicht: Baustein fehlt (PIL)" als Auskunft, nicht als Fehler.
- **CI: Der Rust-Job laeuft nur noch, wenn sich am Binary etwas aendert.**
  Er liegt jetzt in `.github/workflows/rust.yml` mit Pfadfilter (`rust/**`,
  `VERSION`, die Workflow-Datei selbst) statt in `tests.yml`. Anlass: Jeder
  Doku-Commit startete einen arm64-Runner, baute `cargo test`, `cargo deny`
  und das Release-Binary und legte ein Artefakt ab — fuer ein Ergebnis, das
  im Voraus feststand (Modul 55 haelt ueber `state/rust-stand` ohnehin
  still). Die Auswahl trifft GitHub **vor** dem Start des Runners; ein
  Vorschalt-Job haette ihn schon bezahlt. `VERSION` gehoert in den Filter,
  weil das Binary seine Version traegt. Weil ein Lauf damit immer eine echte
  Aenderung ist, veroeffentlicht er das Prerelease `rust-<commit>` jetzt
  direkt (vorher an `workflow_dispatch` gebunden, sodass nach jedem
  Rust-Commit von Hand nachgestossen werden musste und der Job zweimal
  baute). Von Hand bleibt `gh workflow run rust.yml --ref entwicklung`.
- **Dokumentation: Verweise nennen den Abschnitt beim Namen.** 113
  Paragrafenverweise in sieben Dokumenten, im Quelltext und in den Werkzeugen
  zeigen auf Abschnittsnamen statt auf `§9` („`docs/INSTALLER.md`, Abschnitt
  „Was welches Modul aus dem Changelog einspielt""). Im Repo steht kein `§`
  mehr; `tests/test_regelnamen.py` hält neue Nummern fern.

### Entfernt
- **Anzeige:** Herstellertreiber `whisplay.py` samt `spidev`/`gpiod`/
  `python3-dev` aus dem venv; die Anzeigetypen `st7789` und `epaper` der
  alten Tabelle (kommen als Module `gamepi13` und `epd2in13b` wieder).

### Behoben
- **Das Changelog war zerlegt**: „Hinzugefügt" kam zweimal (nach
  „Entfernt"), und zwei Punkte standen ohne Überschrift direkt nach dem
  Vorspann — beim Lesen unsichtbar, beim Auswerten nicht. Wieder in die
  Reihenfolge gebracht, die Dublette zusammengeführt; nur verschoben,
  kein Text geändert (Mengen der Zeilen vorher/nachher verglichen).
- **Leerlauf-Last des Renderers.** Grund war nicht der Transport, sondern die
  Bildrate: In der Ruhe schwingt das Gesicht, dadurch änderte sich jeder
  Rahmen flächig (44–60 % der Pixel, gemessen über 20 Rahmen). Der Umbau auf
  geänderte Bereiche brachte deshalb nichts (35,5 % statt 28,4 %, mehr
  Schreibaufrufe als vorher). Mit der Ruhe-Bildrate fällt die Last auf 10,8 %.
- **Vier Installertests liefen im CI gar nicht** — sie meldeten Fehler, die
  keiner waren. `test-helfer.sh` definierte seine `systemd-run`-Attrappe als
  Shell-Funktion mit Bindestrich: in dash und BusyBox-ash ein Syntaxfehler,
  die Datei wurde dort nie ausgeführt (0 statt 49 Prüfungen). Die Attrappe
  ist jetzt ein Skript im PATH. `test-launcher-hardware.sh`,
  `test-launcher-rc3.sh` und `test-source.sh` fuhren einen echten Lauf und
  landeten damit in der Abkopplung nach systemd-run — im CI-Runner nicht
  vorhanden, also rc 2 vor dem ersten Modul. Sie setzen nun `CHIMERA_HELFER=1`
  (die Lage des Prozesses, der die Arbeit ausführt) und eine
  `systemctl`-Attrappe; geprüft wird, was sie prüfen wollen. Alle vier sind in
  dash und BusyBox-ash grün, die Gegenproben `counter-check-helfer` und
  `counter-check-source` werden weiterhin rot.
- **Die Hilfe von `python3 -m chimera.displays --help` sah unter Python 3.13
  anders aus.** Ab 3.13 entfernt der Interpreter die Einrückung aus
  `__doc__` (Docstrings werden dedentet); die Befehlsliste verlor ihre vier
  Leerzeichen und war damit für Werkzeuge, die sich daran orientieren, nicht
  mehr zu erkennen. Die Hilfe wird jetzt ausdrücklich eingerückt und ist in
  3.11 und 3.13 Zeichen für Zeichen gleich.
- **Schritt 40 machte aus einem laufenden Dienst einen Befund.** Die
  Anzeige-Erkennung kann nicht messen, solange der Dienst SPI hält, und
  meldete „Leitungen belegt" — Schritt 40 wertete das als „keine Anzeige
  gewählt" (rc 1, gelbe LED) und kam nie zur Ton-Einrichtung. Jetzt gilt der
  in `state/anzeige` festgehaltene Typ, wenn sein eigener Nachweis zutrifft
  (`display_typ_nachgewiesen`); ohne Nachweis bleibt es ein Befund. Am Pi
  belegt: rc 0 im selben Zustand, in dem der alte Code rc 1 lieferte.
- **`NoisyRenderer.run()` stürzte in der zweiten Zeile ab.** Es las
  `TARGET_FPS` und `FRAME_TIME` als Modulglobale; die gab es nie, nur als
  Attribute. Unentdeckt, weil die Tests `render()` und `show()` aufriefen,
  nie `run()`.
- **`run()` hätte auch ohne diesen Fehler kein Bild ausgegeben** — es rief
  `render()`, das ein Bild zurückgibt, ohne es an das Panel zu schicken.
  Zwei Fehler auf demselben Weg, beide hinter demselben nie betretenen
  Zweig.
- **Die Temperaturkopplung war dauerhaft wirkungslos, und zwar lautlos.**
  `read_temperature()` las eine Konstante, die es nicht gab; der
  `NameError` fiel in ein `except Exception` und wurde zu `45,0 °C`. Die
  Müdigkeit des Avatars bei Hitze hat nie funktioniert. Genau die
  Fehlerklasse aus Regel 8a, gefunden mit dem neuen Werkzeug.
- **`app.py` öffnete ein Panel und warf es weg.** Auf echter Hardware wäre
  der SPI-Bus belegt und unbenutzt gewesen, während sich der Renderer ein
  eigenes Platzhalter-Panel baute.
- **Ein Fehler beim Anzeigen des Zustands verschwand in einer
  Debug-Zeile.** `Chimera.face` war ein namenloses `object`, die Methode
  wurde vermutet.
- `Registry.load()` konnte die mitgelieferte Mood-Bibliothek nie lesen —
  zwei unabhängig entstandene Dateiformate. Der Test daneben las die Datei
  selbst und rief `add()` auf, umging also genau die Funktion, um die es
  ging.
- `Channel.trim()` überschritt die Obergrenze, die es zusagt, um die Länge
  seines eigenen Abbruchzeichens.
- **Start:** `chimera.service` hängt jetzt an seinem Sitzungs-Socket (`Requires=`, `After=`). Der Zustand „Dienst läuft ohne Sitzungs-Socket“ kann nicht mehr entstehen; ein Neustart bringt beide in der richtigen Reihenfolge hoch.
- **Installer:** Die Klammer nimmt den Zustand vor dem Anhalten auf und stoppt Dienste vor Sockets — ein Dienst, den ein Socket mitnimmt, verschwindet nicht mehr aus der Liste und wird wieder gestartet.
- **Installer:** Klammer und Protokoll überleben den Selbstneustart aus `source/`; der abgekoppelte Helfer bekommt wieder `--helfer` und schreibt „fertig“.
- **Installer:** `systemd-run` läuft mit `--no-block`; ein Lauf mit Befund gilt nicht mehr als Startfehler, und die Meldung eines gescheiterten Starts enthält den Grund.
- **Installer:** Schritte starten während der Klammer keine Dienste und führen den Dienstnachweis nicht mehr mitten im Lauf.
- **Anzeige:** Die Pause für die Anzeige-Schritte setzt ihren Wiedereinstiegspunkt selbst und zeichnet kein „fertig" mehr — der Balken springt nicht mehr auf 100 % und zurück.
- **Anzeige:** Der Zustand „spricht“ zeigte ein Gesicht mit Ohr, also „hört zu“; der Zustand „arbeitet“ verwies auf einen Ausdruck `FOCUS`, den es nie gab, und blieb darum unsichtbar (jetzt `WORK`).
- **Gateway:** Eine Adresse für einen Ollama-Anbieter muss mit `http://` oder `https://` beginnen; alles andere wird beim Speichern abgewiesen.
- **Gateway:** Die Kopfzeile der Oberfläche (mit „Abmelden“) ist vor der Anmeldung nicht mehr sichtbar.
- **Installer:** Ein Download von einer Adresse mit Port (Spiegel, Test) prüft jetzt diesen Port statt 80 oder 443.
- **Anzeige:** Die Statuszeile unter dem Gesicht wird wieder gezeichnet —
  sie war gebaut, aber nicht an den Renderer angeschlossen.
- **Anzeige:** Die Statuszeile ist sichtbar: Sie zeigt ohne Meldung den
  Namen des Ausdrucks, in lesbarer Schriftgröße, und nennt einen fehlenden
  Sprachanbieter.
- **Anzeige:** Ein Tastendruck lässt die LED deutlich weiß blinken statt
  sie nur kurz aufzuhellen.
- **Anzeige:** Backlight und LED belasten bei festem Pegel die CPU nicht
  mehr (vorher rund 7 % eines Kerns im Leerlauf).
- **Anzeige:** Der Installer holt den Whisplay-Paneltreiber und seine
  Python-Pakete selbst ins venv; der Dienst zeigt das Gesicht, statt ohne
  Anzeige zu laufen.
- **Installer:** Die Anzeige-Erkennung meldet I2C nicht mehr fälschlich als
  inaktiv, wenn nur der Userspace-Zugang `i2c-dev` fehlt.
- **Installer:** Die Netzprüfung vor `apt` erkennt den Paketspiegel wieder als
  erreichbar; vorher wartete der Lauf zehn Minuten und brach ab.
- **Installer:** Auf Debian ohne `python3-venv` erkennt Schritt 50 jetzt, dass
  das venv nicht anlegbar ist, und holt das Paket nach.
- **Installer:** Ein halb angelegtes venv ohne pip (Rest eines abgebrochenen
  Laufs) wird erkannt und neu angelegt.
- **Installer:** Modul 50 rechnete mit der Repo-Wurzel, wo
  `dirname($0)/..` (`installer/`) liegt — eine echte Installation
  waere an `requirements.txt fehlt` gescheitert. Der Testbaum trug die
  Struktur an der falschen Stelle, deshalb blieb es unentdeckt.
- **Tests:** Der Modul-50-Test baute die Quellkopie verschachtelt
  (`src/chimera/chimera`) — der echte Lauf brach mit rc 2 ab. Ebenso
  legte die Gegenprobe ihren Schritt ausserhalb des Baums ab und
  scheiterte am fehlenden `common.sh`, nicht an der Verdrahtung.
- **Tests:** Der Bashism-Detektor schlug bei POSIX-Zeichenklassen
  (`[[:space:]]`) an — Fehlalarm.
- **Installer:** Eine Datei mit Zeilenumbruch im Namen fiel still aus der
  Prüfsumme heraus; jetzt bricht die Prüfung benannt ab.

### Bekannte Einschränkungen
- **`MemoryMax=` wirkt auf dem Pi nicht.** Der RPi-Kernel startet mit
  `cgroup_disable=memory`. Gemessen: 150 MB unter `MemoryMax=20M` liefen
  durch. Regel 10q setzt deshalb auf Selbstbegrenzung, die noch nicht
  gebaut ist (Roadmap Phase 6).
- **Keine Sprachein- oder -ausgabe.** Sprache, Wake-Word und
  Umgebungshören sind entworfen, aber nicht gebaut.
- **Die Abo-Marke wird nicht aufgefrischt.** Läuft sie ab, greift der
  Rückfall auf das nächste Ziel. Koordinator fehlt.
- **Werkzeugaufrufe werden aus dem Text gelesen** (`TOOL: name {...}`),
  nicht über die Werkzeug-Schnittstelle der Anbieter. Funktioniert mit
  jedem Modell, ist aber nicht die saubere Lösung.
- **`Action.OFFLOAD` wird erkannt, aber nicht ausgeführt** — verdichtet
  wird erst an der nächsten Schwelle.
- **Nur ein Panel ist gebaut** (Whisplay). E-Paper und ST7789 sind
  entworfen (`docs/DISPLAYS.md`), nicht umgesetzt.
- **Die Statuszeile überträgt immer das ganze Bild.** Der Schalter
  `nur_zeile` ist vorgesehen, hat aber keine Wirkung — `panel.py` kennt
  keine Teilübertragung. Wer nur die unteren 40 von 280 Zeilen schickt,
  spart am teuersten Posten: SPI kostet 28,1 von 39,3 ms je Bild.
- **Die Statuszeile kennt keine gesichtsabhängigen Einstellungen.** Der
  Platz dafür ist vorgesehen (die Vorlage hat `[text_overlay]` je
  Charakter), bleibt aber leer, solange es keine Gesichter als Pakete
  gibt.
- **Die Statuszeile nutzt die Standardschrift von Pillow.** Sie ist klein
  und nicht auf 240 Pixel Breite abgestimmt; eine eigene Schrift ist
  nicht ausgesucht.
- **Die Temperaturkopplung ist nicht gebaut.** Der Verwalter könnte sie
  tragen (Quelle `hitze` mit Erneuerungsbedingung ist vorhanden), aber
  niemand misst die Temperatur und niemand degradiert die Anzeige.
  Befund B6 bleibt damit offen.
- **Auf der Zielhardware gemessen wurde bisher nur die Bildrate**
  (39,3 ms je Bild, SPI 28,1 davon) sowie Display, Ton, Mikrofon und LED.
  Statuszeile und Verwalter liefen dort noch nicht.
- **Nichts davon lief auf der Zielhardware.** Insbesondere ist die
  Bildrate von 15 auf einem Pi Zero 2 W nicht gemessen, sondern von Noisy
  übernommen.
- Der Renderer läuft als Faden im Hauptprozess (Regel 7a). Dass die
  globale Sperre dabei nicht stört, ist begründet, aber auf dem Zero 2 W
  nicht gemessen.

### Geprüft
- **Ein Faden für die drei LED-Kanäle: gebaut, gemessen, verworfen**
  (3.11., Pi Zero 2 W). Die gemeinsame Kantenplanung spart 18 % der
  LED-Taktlast, wenn alle Kanäle denselben Tastgrad haben (Weiß), kostet
  aber 20 % mehr, sobald sie verschieden sind — also bei jeder Farbe, dem
  Normalfall beim Glow. Aufbau, Zahlen und die Lehre daraus stehen in
  `docs/research/LED-TAKT.md`; nachmessen mit `tools/pwm-vergleich.py`.
  Die drei Einzelfäden bleiben, der ROADMAP-Punkt ist damit zu.
- **Neustart mit Fortsetzung am Gerät belegt** (3.11., 21:40, Pi Zero 2 W,
  Kernel 6.18.50): Installer aus `81c047b` schreibt und aktiviert
  `chimera-mojo-fortsetzung.service` (Manifest-Eintrag `dienst`); Marker
  geschrieben, `systemctl reboot` → die Fortsetzung lief nach dem Start,
  meldete „der Neustart hat gewirkt … Marker entfernt" und entfernte den
  Marker. Ohne Marker meldet systemd „skipped, unmet condition check" mit
  `Result=success` — beim nächsten Boot also kein Befund. Alle fünf Units
  danach aktiv.
302 Tests, alle grün: 64 Agent, 68 Mood, 46 Installer, 41 Anbieter,
35 Skills und Gedächtnis, 21 Übergänge, 16 Renderer, 11 Anzeige. Jeder Regressionstest hat eine Gegenprobe. Die
Anbieterschicht und die Agent-Schleife wurden zusätzlich gegen einen
echten Ollama-Server geprüft.
431 Tests, alle grün: 361 Python, 70 Installer. Neu darunter 27 für die
Gesichtskette (`test_display_wiring.py`) und 24 für Regel 10k. Jeder
Regressionstest hat eine Gegenprobe, und die Gegenproben wurden gegen den
jeweils alten Code **verifiziert** — jeder der sechs Befunde färbt den
Test rot, wenn man ihn wiederherstellt.
Die Prüfung des H4-Stands gegen die Blaupause steht in
`docs/PRUEFUNG-H4.md`.
**Zum ersten Mal auf der Zielhardware gelaufen** (Pi Zero 2 W, DietPi
10.7, Kernel 6.18.50): Preflight mit Exitcode 0, Whisplay-Treiber gebaut,
ALSA-Karte `whisplaysound` registriert (Codec WM8960). Was sich dabei
gezeigt hat — auch die Fehlschläge und ihre Ursachen — steht in
`docs/HARDWARE-BEFUNDE.md`.
- **Bedarf am Pi gemessen** (3.11., Pi Zero 2 W, Kernel 6.18.50): RAM 462 MB
  gesamt / 359 MB verfügbar, Karte 117 GB mit 95 GB frei; `source/` 3 MB,
  `state/` 40 KB, `productive/` 107 MB; `chimera.service` 47 MB RSS,
  `chimera-tor --dienst` 1,6 MB und 0,2 % eines Kerns; Mojo-Prüfung 528 ms bei
  6 MB Spitze. Die 100 MB vor einem Snapshot sind damit eine Untergrenze, kein
  gemessener Bedarf.
- **Ein voller Installerlauf endet grün.** Aus dem Klon auf Commit `e3cff04`
  (Doku, `rust/` unverändert): „12 Modul(e), ohne Fehler", `LED: ok (3 s)`,
  und `tools/abgleich.sh --erwartet e3cff04` bestätigt Quellbaum wie
  eingespielten Stand. Vorher endete jeder Lauf aus einem Zip mit einem
  Befund und gelber LED.
- **Das „Updated"-Gesicht wurde am Panel abgelesen** (2.11.): Gesicht,
  Fortschrittsbalken und „Updating…" stehen sichtbar auf der Anzeige und
  bleiben bis zum Dienststart stehen — nicht nur die Socket-Antwort stimmte.
