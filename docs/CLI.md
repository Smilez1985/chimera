# Chimera — CLI-Referenz / CLI reference

Alle Befehle auf einen Blick, nach Kategorie. Die Tabellen sind gegen die
echten Programme geprüft (`tests/test_cli_doku.py`): Eine Option, die hier
fehlt oder nicht mehr existiert, lässt den Test rot werden.

All commands at a glance, by category. The tables are checked against the
real programs (`tests/test_cli_doku.py`): an option missing here, or one that
no longer exists, turns that test red.

**Stand / Status:** Optionen mit **(geplant / planned)** gibt es noch nicht;
sie stehen hier, damit die Planung sichtbar ist. Der Test prüft nur Optionen
ohne diese Marke. / Options marked **(geplant / planned)** do not exist yet.
The test ignores them.

| Kategorie / Category | Befehle / Commands |
|---|---|
| [1. Agent](#1-agent--agent) | `chimera` |
| [2. Installation](#2-installation--installation) | `chimera-install`, `chimera-uninstall` |
| [3. Gateway](#3-gateway--gateway) | `chimera-tor` |
| [4. Anzeige & Hardware](#4-anzeige--hardware--display--hardware) | `python3 -m chimera.displays` |
| [5. Betrieb](#5-betrieb--operations) | `log-abgleich.sh` |
| [6. Entwicklung](#6-entwicklung--development) | `tools/*.py`, `installer/run-tests.sh` |
| [7. Umgebungsvariablen](#7-umgebungsvariablen--environment-variables) | `CHIMERA_*` |

Exitcodes: `0` in Ordnung / ok, `1` Befund / finding, `2` Aufruf oder
Konfiguration falsch / bad call or configuration, `3` Neustart nötig
(Installer) / reboot needed (installer).

---

## 1. Agent / Agent

### `chimera`

Der Agent. Ohne Option ein Terminal-Gespräch. / The agent. Without options an
interactive terminal conversation.

| Option | Wirkung / Effect |
|---|---|
| `-f`, `--frage TEXT` | Eine Frage stellen und aufhören. / Ask one question and exit. |
| `--telegram` | Die Telegram-Tür öffnen. / Open the Telegram door. |
| `--pruefen` | Nur zeigen, was vorhanden ist. / Only show what is available. |
| `--offline` | Nicht im Netz nach Anbietern suchen. / Do not search the network for providers. |
| `--dienst` | Als Dienst laufen: ohne Terminal, bis SIGTERM. / Run as a service: no terminal, until SIGTERM. |
| `-v`, `--ausfuehrlich` | Ausführliche Protokollierung. / Verbose logging. |
| `-h`, `--help` | Hilfe. / Help. |

Beispiele / Examples:

    chimera -f "Wie spät ist es?"
    chimera --pruefen

---

## 2. Installation / Installation

### `chimera-install`

Der Installer, ein Modul nach dem anderen, idempotent. / The installer, one
module after another, idempotent.

| Option | Wirkung / Effect |
|---|---|
| `--only PRÄFIX` | Nur das passende Modul (z. B. `10`). / Only the matching module. |
| `--hardware` | Nur Hardware-Module (40 45 50), der Boot-Abgleich. / Only hardware modules (boot reconcile). |
| `--list` | Module auflisten. / List modules. |
| `--dry-run` | Nichts ändern, nur berichten. / Change nothing, only report. |
| `--check` | Nur prüfen, der Exitcode sagt den Zustand. / Check only; the exit code tells the state. |
| `--log-dir DIR` | Ablage des Protokolls. / Where the log goes. |
| `--downgrade=true` | Älteren Stand bewusst nach `source/` übernehmen. / Deliberately accept an older source. |
| `--mit GRUPPE` | Opt-in-Recht für den Dienstnutzer (`i2c`, `video`). / Opt-in group for the service user. |
| `-h`, `--help` | Hilfe. / Help. |

Umgebung bei einem Lauf (Auswahl, alle in Abschnitt 7) / Environment for a run
(selection, all in section 7): `CHIMERA_WEB_PASSWORT`, `CHIMERA_RUST_LOKAL`,
`CHIMERA_ANZEIGE`.

Beispiele / Examples:

    sudo sh installer/chimera-install --dry-run
    sudo env CHIMERA_WEB_PASSWORT='…' sh installer/chimera-install
    sudo sh installer/chimera-install --only 99

### `chimera-uninstall`

Der Rückbau. Die einzige Wahrheitsquelle ist das Manifest
(`/opt/chimera/state/manifest.tsv`); ohne Manifest wird nichts entfernt. Läuft
in umgekehrter Modulfolge, idempotent. / The uninstaller. The only source of
truth is the manifest; without it nothing is removed. Runs modules in reverse
order, idempotent.

| Option | Wirkung / Effect |
|---|---|
| `--only PRÄFIX` | Nur der passende Schritt. / Only the matching step. |
| `--list` | Schritte auflisten. / List steps. |
| `--dry-run` | Nichts ändern, nur berichten. / Change nothing, only report. |
| `--manifest DATEI` | Anderes Manifest verwenden. / Use another manifest. |
| `--remove-packages` | Auch die von Chimera installierten Pakete entfernen (Vorgabe: behalten). / Also remove packages Chimera installed (default: keep). |
| `--log-dir DIR` | Ablage des Protokolls. / Where the log goes. |
| `--daten-loeschen` | Gedächtnis und Moods im Home löschen (Opt-in). / Delete memory and moods (opt-in). |
| `--logs-loeschen` | Protokolle löschen (Opt-in). / Delete logs (opt-in). |
| `-h`, `--help` | Hilfe. / Help. |

**Geplant / Planned** — Ebenen, einzeln wählbar, Vorgabe überall „bleibt“.
Levels, selectable one by one, everything is kept by default:

| Option | Entfernt zusätzlich / Also removes |
|---|---|
| `--abhaengigkeiten-loeschen` **(geplant / planned)** | venv, neu installierte Pakete, Cache. / venv, newly installed packages, cache. |
| `--agent-loeschen` **(geplant / planned)** | Agent-Dateien: Gedächtnis, `ich/`, Sitzungen, Moods (Alias: `--daten-loeschen`). / Agent files: memory, `ich/`, sessions, moods. |
| `--einstellungen-loeschen` **(geplant / planned)** | `.env` (Schlüssel, Anbieter, Hash), `wahl.json`. / `.env` (keys, providers, hash), `wahl.json`. |
| `--alles` **(geplant / planned)** | Alle Ebenen. / All levels. |

Beispiele / Examples:

    sudo sh uninstaller/chimera-uninstall --dry-run
    sudo sh uninstaller/chimera-uninstall --daten-loeschen --logs-loeschen

---

## 3. Gateway / Gateway

### `chimera-tor`

Das Gateway: der einzige Prozess mit Netzzugang (Regel 5n). / The gateway: the
only process with network access.

| Option | Wirkung / Effect |
|---|---|
| `--version` | Version ausgeben. / Print version. |
| `--pruefen` | Selbstprüfung als JSON (für den Installer). / Self-check as JSON. |
| `--dienst` | Dienstbetrieb: den von systemd übergebenen Socket bedienen. / Service mode: serve the socket handed over by systemd. |
| `--dienst --socket PFAD` | Ohne systemd selbst binden. / Bind yourself, without systemd. |
| `--passwort-hash` | Passwort von stdin lesen, Hash für `CHIMERA_WEB_PASSWORT_HASH` ausgeben (mind. 8 Zeichen). / Read a password from stdin, print the hash for `CHIMERA_WEB_PASSWORT_HASH` (min. 8 chars). |
| `--ping [PFAD]` | Gateway fragen (Vorgabe `/run/chimera/tor.sock`), rc 0 = antwortet. / Ask the gateway, rc 0 = answers. |
| `-h`, `--help` | Hilfe. / Help. |

Das Passwort nie als Argument übergeben (Prozessliste). / Never pass the
password as an argument (process list).

    echo 'MeinPasswort' | chimera-tor --passwort-hash

---

## 4. Anzeige & Hardware / Display & hardware

### `python3 -m chimera.displays`

| Befehl / Command | Wirkung / Effect |
|---|---|
| `erkennen [--json]` | Welche Anzeige steckt dran? rc 0 gewählt, 1 nicht. / Which display is attached? |
| `liste` | Bekannte Module mit Kurzdaten. / Known modules. |
| `profil TYP` | `display.json` eines Moduls (JSON); liest der Installer. / A module's `display.json`. |
| `ton TYP [--json]` | Ton des Moduls bereitstellen (root): Overlays, Mixer, ALSA-Karte nachweisen. / Provide the module's audio (root). |
| `kennung DC [RST]` | ST7789-Kennung roh lesen (Messwerkzeug). / Read the ST7789 ID raw. |
| `mikro [--json]` | Mikrofone messen (Testtöne über den Lautsprecher): `beide`, `links`, `rechts`, `keins`. / Measure microphones. |

---

## 5. Betrieb / Operations

### `installer/bin/log-abgleich.sh`

Dienstprotokolle aus dem Arbeitsspeicher auf den Datenträger bringen. Wird von
der Dienst-Unit und einem Timer aufgerufen, nicht von Hand. / Copy service logs
from RAM to disk. Called by the unit and a timer, not by hand.

| Option | Wirkung / Effect |
|---|---|
| *(keine / none)* | Sofort abgleichen. / Sync now. |
| `--ruhig` | Nur abgleichen, wenn seit 120 s nichts geschrieben wurde oder die Karte über eine Stunde alt ist. / Only sync when idle for 120 s or the card copy is over an hour old. |

Braucht `CHIMERA_LOG_RAM` und `CHIMERA_LOG_KARTE`. / Needs both variables.

---

## 6. Entwicklung / Development

| Befehl / Command | Wirkung / Effect |
|---|---|
| `sh installer/run-tests.sh` | Alle hardwarefreien Installertests samt Gegenproben (über 15 Minuten). / All hardware-free installer tests with counter-checks. |
| `sh installer/tests/test-<name>.sh` | Ein Installertest. / One installer test. |
| `sh installer/tests/counter-check-<name>.sh` | Gegenprobe zu einem Test. / Counter-check for a test. |
| `python3 tests/test_<name>.py [--gegenprobe]` | Ein Python-Test, optional mit Gegenprobe. / One Python test. |
| `sh rust/gegenprobe-web.sh` | Gegenprobe der Web-Oberfläche. / Web UI counter-check. |
| `sh rust/gegenprobe-telegram.sh` | Gegenprobe der Telegram-Tür. / Telegram counter-check. |
| `cd rust && cargo test --locked` | Rust-Tests. / Rust tests. |
| `python3 tools/check-globals.py` | Namen finden, die gelesen, aber nie definiert werden. / Find names read as globals but never defined. |
| `python3 tools/contact-sheet.py [ZIEL.png]` | Moods nebeneinander zeichnen. / Draw moods side by side. |
| `python3 tools/import-noisy-moods.py PFAD [ZIEL.json]` | Noisys 41 Moods als Startbestand übernehmen. / Import Noisy's 41 moods. |

Langläufer immer abgekoppelt starten (nicht im Turn warten). / Always start
long runs detached.

---

## 7. Umgebungsvariablen / Environment variables

Werte für den Dienst stehen in `/opt/chimera/config/.env` (Vorlage
`.env.example`). Schlüssel nie in Ausgaben oder ins Repo. / Service values live
in `/opt/chimera/config/.env`. Never print keys or commit them.

### Beim Installieren / During install

| Variable | Wirkung / Effect |
|---|---|
| `CHIMERA_WEB_PASSWORT` | Web-Passwort im Klartext, nur für diesen Lauf; der Installer trägt den Hash ein. / Plain web password for this run only; the installer stores the hash. |
| `CHIMERA_RUST_LOKAL` | Pfad zu einem selbst gebauten `chimera-tor` statt des CI-Prerelease. / Path to a self-built `chimera-tor` instead of the CI prerelease. |
| `CHIMERA_ANZEIGE` | Anzeigetyp festlegen, wenn die Erkennung nichts wählt. / Force a display type. |
| `CHIMERA_MIKRO_NEU` | `1`: Mikrofonmessung wiederholen. / Repeat the microphone measurement. |

### Im Betrieb (`.env`) / In operation (`.env`)

| Variable | Wirkung / Effect |
|---|---|
| `OLLAMA_API_BASE` | Adresse des Ollama-Servers. / Ollama server address. |
| `OLLAMA_MODEL` | Standardmodell (optional), z. B. `llama3.2:3b`. / Default model (optional). |
| `ANTHROPIC_API_KEY` | Anthropic-Schlüssel. / Anthropic key. |
| `ANTHROPIC_OAUTH_TOKEN` | Anthropic-Abo-Anmeldung. / Anthropic subscription login. |
| `CHIMERA_TELEGRAM_TOKEN` | Bot-Token vom BotFather; leer = Telegram aus. / Bot token; empty = off. |
| `CHIMERA_TELEGRAM_ALLOWED` | Erlaubte Nutzer-IDs, kommagetrennt (Pflicht mit Token). / Allowed user IDs (required with a token). |
| `CHIMERA_WEB_PASSWORT_HASH` | Passwort-Hash der Web-Oberfläche; leer = Oberfläche aus. / Web UI password hash; empty = UI off. |
| `CHIMERA_WEB_PORT` | Port der Oberfläche (Vorgabe 8080). / UI port (default 8080). |
| `CHIMERA_WEB_BIND` | Adresse der Oberfläche (Vorgabe `0.0.0.0`). / UI bind address (default `0.0.0.0`). |
| `CHIMERA_WEB_MODULE` | Verzeichnis nachgelegter Web-Module (Vorgabe `/opt/chimera/web/module`). / Directory of add-on web modules. |
| `CHIMERA_SITZUNG_SOCKET` | Pfad des Sitzungs-Sockets (Vorgabe `/run/chimera/sitzung.sock`). / Session socket path. |
| `CHIMERA_HOME` | Datenverzeichnis des Agenten. / Agent data directory. |

### Für Tests / For tests

`CHIMERA_ROOT`, `CHIMERA_MANIFEST`, `CHIMERA_TESTDIR`: verschieben Wurzel,
Manifest und Testverzeichnis. / Relocate root, manifest and test directory.
