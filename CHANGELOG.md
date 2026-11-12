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
- **Websuche, erste Stufe** (DESIGN Regel 5r): `op: web_suche` im Gateway
  (`suche.rs`) und das Werkzeug `web_suche` im Agenten. Quellen in
  `wahl.json` unter `suche.quellen`, in Reihenfolge: `searxng:<adresse>`
  (eigene Instanz, `format=json`; ein 403 nennt `search.formats` als Grund)
  und `ollama` (`https://ollama.com/api/web_search`, `OLLAMA_API_KEY` aus
  der Umgebung des Gateways). Fällt eine Quelle aus, wird die nächste
  versucht; ohne Quelle kommt `keine_quelle` mit Beispiel, nie ein stiller
  Ausfall. Treffer: 5 (bis 10), 400 Zeichen Auszug, 8.000 gesamt, nichts
  auf Platte. Der Agent hat weiter kein Netz — er fragt über den Socket.
  Tests: 8 in `suche` (Quellen lesen, Kürzen, 403-Text, Ausfall der ersten
  Quelle, fehlender Schlüssel) und 6 in `test_agent` (Gateway wird gefragt,
  Antwort wird lesbar, „keine Quelle" wird genannt).
- **Suchquelle `ddg` (DuckDuckGo lite), kostenlos und ohne Schlüssel**
  (`suche.rs`): die Ziele stehen prozent-kodiert im `uddg=`-Parameter des
  Weiterleitungs-Links, Auszüge in `class='result-snippet'`. Bewusst
  **Opt-in** (5r): kein Vertrag, die Seite kann brechen. Liefert sie keine
  Treffer, ist das ein benannter Fehler statt eines leeren Erfolgs.
  2 Tests mit einem echten Seitenausschnitt (Ziele, Entitäten, Kürzung,
  Bot-Seite ohne Treffer) und einer für `%XX`/`+`.
- **`stream` ist umschaltbar** (DESIGN, Regel „Aufrufe, nicht Text“): Das
  Gateway liest `stream` aus `wahl.json` (Vorgabe **aus**) und setzt den Wert
  ausdrücklich — Ollama hat sonst `true`. Ist er an, werden die NDJSON-
  Teilstücke zusammengesetzt (`ollama::strom_sammeln`: Text anhängen,
  Werkzeugaufrufe je `index` zusammenführen, Argumente aus Objekt **oder**
  Text, Fehlerzeile wird nicht als Antwort verkauft), und das Ergebnis geht
  durch dieselbe Auswertung wie eine Antwort ohne Strom. In Telegram schaltet
  `/stream an` bzw. `/stream aus`; `/stream` allein zeigt den Zustand.
  Tests: 2 in `ollama` (Strom mit Aufruf über zwei Zeilen, Fehlerzeile),
  1 in `dienst` (Schalter wirkt, Teilstücke kommen als ein Text an),
  1 in `telegram` (Befehl mit und ohne Wert).
- **Native Werkzeugaufrufe, Stufe 1 und 2** (DESIGN, Regel „Aufrufe, nicht
  Text“; smilez 12.11.): Das Gateway trägt `tools` in der Form von Ollama
  durch (`{"type":"function","function":{…}}`), setzt `stream` immer
  ausdrücklich (Ollama hat sonst default **true**) und gibt Aufrufe als
  `werkzeuge: [{name, argumente, id?}]` zurück. `content: ""` ist dabei kein
  Fehler mehr — „leer“ ist nur, wenn **weder** Text **noch** Aufruf kommt.
  Argumente werden als Objekt **oder** JSON-String angenommen und intern als
  Objekt gehalten (Ollama schickt Objekte, die OpenAI-Form Strings).
  Der Agent schickt seine Schemas mit; kommt ein Aufruf zurück, läuft er über
  `tools.call()` — also durch `chimera-sohelper`, kein zweiter Weg. Das
  Text-Protokoll `TOOL: …` bleibt Rückfall für Modelle, die keine Aufrufe
  liefern. Tests: 3 in `ollama` (Form, leerer Text, Reihenfolge nach `index`),
  12 in `test_agent` (Verlauf mit `role:"tool"`, unbekanntes Werkzeug, ohne
  Ausführer nichts getan).
- **`/model` in Telegram** (`telegram.rs`): `/model` zeigt die Modellliste des
  Servers, markiert die geltende Wahl und benennt Modelle, die gemessen keine
  Werkzeuge können; `/model 3` oder `/model <name>` zieht den Verweis
  `ollama/<modell>` in `wahl.json` nach vorn (ohne Doppelung, der Rest der
  Datei bleibt). Geschrieben über `op: wahl_setzen` — die Tür schreibt nicht
  selbst an der Datei vorbei. 3 Tests (Befehle mit Botnamen, Liste mit
  Markierung und Hinweis, Reihenfolge ohne Verlust).
- **Die Reihenfolge aus `wahl.json` gilt vor der Serverreihenfolge**
  (`daten::bevorzugt`, `ollama::modell_waehlen`): Was der Nutzer vorn hat,
  wird genommen — aber nur, wenn der Server das Modell noch meldet und die
  Messung ihm nicht die Werkzeuge abspricht. Ohne Datei bleibt es bei der
  Reihenfolge des Servers.
- **Das Modell kommt aus der Serverliste** (`rust/crates/tor/src/ollama.rs`,
  `dienst.rs`): `ollama::modell_waehlen` ist der eine Ort für die Regel —
  ein genanntes Modell gilt; sonst das **erste in der Reihenfolge des
  Servers**, das der Katalog mit `tools: true` gemessen hat; sonst
  `kein_modell` mit Klartext-Grund („kein Modell", „keines kann
  Werkzeuge", „nicht gemessen"), und es wird nichts geschickt. `op: modelle`
  nennt dieselbe Wahl als `wahl` (und `wahl_grund`), damit der Dienst sie
  nicht nachbaut — er nimmt sie fürs Kontextfenster (5a). Ist für **kein**
  Modell etwas gemessen, misst das Gateway einmal selbst (12 s) und
  entscheidet neu; sonst bliebe ein Anbieter, den die Netzsuche nicht
  auffrischt (`auto: false`), dauerhaft ohne Antwort. Tests: 4 in
  `ollama`, 3 in `dienst` (u. a. „ohne taugliches Modell wird nichts
  geschickt" — der Testserver bekommt nur die Modellliste) und 5 in
  `tests/test_gateway_provider.py`. **Am chimera-pi belegt (11.11.):**
  `op: modelle` meldet `wahl: qwen3.6:27b` (erster Eintrag der Serverliste mit
  `tools`), und ein `op: chat` **ohne** Modellangabe antwortet mit genau
  diesem Modell — kalt 120,7 s, Text „bereit".
- **Gleichheit gegen die Python-Seite belegt** (`tests/test_sohelper_gleichheit.py`):
  dieselben Befehle und Pfade gehen durch `safety.py` **und** durch einen
  laufenden `chimera-sohelper`; verglichen wird das Urteil und der Text der
  Ablehnung. 45 Fälle, darunter Anführungszeichen, Backslash, leere
  Argumente, Symlink-Flucht und die Zerlegung (Ausgabe von `printf`
  gegen `shlex.split`). **Dabei vier Unterschiede gefunden und behoben:**
  die Rust-Seite zitierte mit `"` statt `'` (wie Pythons `repr`), sagte
  „nicht erlaubt" statt „nicht freigegeben", und bei kaputten
  Anführungszeichen stand eine deutsche Übersetzung statt der Meldung von
  `shlex` („No closing quotation"). Die Texte sind jetzt gleich — das
  Modell soll keinen Unterschied sehen. Gegenprobe
  (`tests/gegenprobe_sohelper_gleichheit.py`): vier Verfälschungen, jede
  wird rot (`sudo` wieder erlaubt, Netzprogramme durch, Backslash schützt
  nicht mehr, anderer Text).
- **Der Ausführer ist eingerichtet** (Schritt 1b, entschieden 10./11.11.):
  Systemnutzer `chimera-sohelper` (kein Home, keine Anmeldung, keine Gruppe
  außer der eigenen), Arbeitsordner `/opt/chimera/sohelper` (700, Eigentum
  des Ausführers — nach dem Setzen geprüft, nicht angenommen),
  Socket-Aktivierung über `/run/chimera/sohelper.sock` (Gruppe `chimera`,
  0660: nur der Agent darf fragen), Dienst mit `IPAddressDeny=any` und
  `InaccessiblePaths=/opt/chimera/config` (das venv ja, die Schlüssel
  nein). Nachweis über einen echten `--ping` und `NRestarts=0`. Neues Modul
  `99-sohelper` mit Rückbau (`99-remove-sohelper`); 59 Tests, 8 Mutationen
  in der Gegenprobe (offener Socket, falsche Gruppe, fehlende Netzsperre,
  sichtbare Schlüssel, offener Arbeitsordner, ausgefallener Nachweis,
  Zusatzgruppen).
- **Socket-Anbindung einmal statt zweimal** (`gemein::socket`): `von_systemd`
  (Socket-Aktivierung, Handle 3), `binden` (mit Prüfung „wird schon
  bedient?" und 0660) und `oeffnen`. Gateway und Ausführer nehmen dieselbe
  Funktion; `chimera-tor` bindet sein Verhalten unverändert.
- **Das Binary des Ausführers liegt im Repo** (`sohelper/chimera-sohelper-aarch64`,
  entschieden 11.11.): derselbe Weg wie beim Gateway — Prüfsumme und Stand
  daneben, aus dem Startbaum eingespielt, nie auf dem Gerät gebaut. Der
  Ausführer nennt seine Version jetzt als `chimera-sohelper <VERSION>`
  (`--version`, wie `chimera-tor`); daran prüft die Ablage, ob Binary und
  Repo zusammenpassen. Die CI baut beide Programme in einem Lauf und legt
  beide als Artefakt ab. Abgelegt wird mit **einem** Werkzeug,
  `tools/binary-ablegen.sh <binary> --art tor|sohelper`;
  `tools/gateway-binary.sh` bleibt als Kurzform für das Gateway, damit
  Skripte, Doku und Tests weiter stimmen.
- **Ausführer `chimera-sohelper` (`rust/crates/sohelper`)** — der eigene
  Prozess aus der Regel „Wer prüft, führt aus": Er nimmt Werkzeugwünsche
  über einen Unix-Socket an (eine JSON-Zeile hin, eine zurück), prüft sie
  und führt sie aus. Die Regeln sind aus `agent/safety.py` portiert, nicht
  neu erfunden: Sperrliste (`sudo`, `su`, `doas`, `pkexec`), Interpreter,
  Shell-Zeichen, gefährliche Muster, Ersetzung und Mehrzeiligkeit,
  Pfadschutz mit Symlink-Auflösung, Ausgabe kürzen. **Kein Netz:** `curl`,
  `wget`, `git` und Verwandte werden immer abgelehnt. Zerlegt wird wie
  `shlex.split(posix=True)`. Die Antworttexte sind dieselben wie in
  `tools.py`. 10 Regeltests, clippy sauber, Rauchtest über den Socket
  (Schreiben, Lesen, Auflisten, gesperrter Befehl, Pfadflucht). Noch nicht
  eingebunden: Nutzer, Ordner, Unit, Gleichheitstest gegen Python.
- **Das Gateway-Binary liegt im Repo:** `gateway/chimera-tor-aarch64`
  (2,0 MB, aarch64-musl, gebaut von der CI für `fa7edfb`) mit
  `chimera-tor-aarch64.sha256` und `chimera-tor-aarch64.stand`
  (`<commit> <hash des rust/-Baums> <version>`). Damit bringt ein Zip von
  GitHub das Binary mit: Wer das Repo als Zip holt, auf dem Pi entpackt und
  daraus installiert, braucht für das Gateway kein Netz.
- **`tools/gateway-binary.sh`:** legt ein gebautes Binary ab und schreibt
  Prüfsumme und Stand dazu; prüft vorher, dass es läuft und die `VERSION`
  der Quelle nennt (`--ohne-probe` für fremde Architekturen, mit Warnung).
- **`rust_baum_hash` und `rust_stand_schreiben` liegen in
  `installer/lib/source.sh`** statt in Schritt 55 — das Ablege-Werkzeug
  braucht dieselben Funktionen; zwei Fassungen würden auseinanderlaufen.
- **`chimera-installer.sh` in der Repo-Wurzel — der Einstieg für den
  Nutzer** (smilez, 10.11.; Vorbild `setup.sh` in rag4ll und `install.sh`
  in llmcf). `sudo sh chimera-installer.sh` aus dem Klon oder dem
  entpackten Zip; die Datei reicht an `installer/chimera-install` weiter,
  mit denselben Optionen und demselben Exitcode. Fehlt der innere
  Installer, bricht sie benannt ab. Der Hinweis „mit sudo neu starten“
  nennt jetzt die Datei, die aufgerufen wurde. Tests:
  `installer/tests/test-einstieg.sh` (16 Prüfungen, Vergleich mit dem
  inneren Installer statt eines nachgebauten Sollwerts) und
  `counter-check-einstieg.sh` (fünf Mutationen, jede rot am erwarteten
  Punkt). Portabilitätstest und Syntaxlauf der CI erfassen die Datei.
- **Blaupause: Regel „Wer prüft, führt aus“ — Werkzeuge laufen in einem
  eigenen Prozess, den der Agent nicht ändern kann.** Vorgabe smilez
  (10.11.): eine unabhängige Kontrollinstanz vor der Werkzeugausführung,
  ausdrücklich nicht als zweites Sprachmodell. Heute prüft und startet
  derselbe Prozess (`agent/tools.py`); künftig liegen Prüfung und Ausführung
  zusammen in einem eigenen Rust-Prozess mit Socket und ohne Netz, nicht im
  Gateway. Er läuft unter einem eigenen Systemnutzer `chimera-sohelper`
  (secops helper), dem der Arbeitsordner gehört. Nur Design und Roadmap
  (Phase 6) — gebaut ist noch nichts; offen ist das Pfadschema.
- **ACP-Transportschicht** (`rust/crates/acp/src/transport.rs`): Der Kern
  kennt nur einen `Strom` aus JSON-Zeilen; `Stdio` hängt ihn an stdin/stdout
  (der Fall, den eine IDE erwartet), weitere Transporte (Unix-Socket,
  HTTP/WebSocket) setzen dasselbe Merkmal um. `bedienen()` läuft bis zum
  Verbindungsende; eine kaputte Zeile beendet die Sitzung **nicht** — der
  Client bekommt `-32700` und die nächste Anfrage wird beantwortet. Meldungen
  eines Zuges gehen vor dessen Antwort raus, sonst sähe der Client die
  Aktualisierung erst nach dem Ende. Fünf Tests mit In-Memory-Strömen
  (drei Anfragen → drei Antworten plus Meldung, kaputte Zeile, leere Eingabe,
  Meldung ohne `id`, eine Ausgabezeile je Nachricht).
- **ACP-Kern** (`rust/crates/acp`, `chimera-acp`): JSON-RPC 2.0 mit
  Zeilenrahmen und der Mindestumfang aus der Regel „ACP“ — `initialize`
  (Protokollversion 1, nur Fähigkeiten, die es gibt), `session/new`,
  `session/prompt` mit `stopReason`, `session/update` als Meldung,
  `session/cancel` als Meldung ohne Antwort. Unbekannte Methoden, kaputte
  Zeilen und fehlende Parameter werden zu Fehlerantworten mit dem Code, den
  JSON-RPC 2.0 dafür vorsieht (`id: null`, wenn die Anfrage selbst unlesbar
  war) — ein Client mit Tippfehler kann weiterreden. Der Zeilenrahmen kommt
  aus `gemein::zeile`, der Kern ist synchron und ohne Laufzeit; was ein Zug
  inhaltlich tut, hängt am Trait `Agent`. 17 Tests, dazu vier Grenzfälle
  (Meldung ohne `id`, `id: null` als echte Anfrage, Bildblock wird
  abgelehnt statt geschluckt, mehrere Textblöcke bleiben getrennt).
- **Blaupause: Regel „Warte-Schleife" — kein Download bricht bei einem
  Netzaussetzer ab.** Jeder Abruf läuft in einer Schleife, die den Ausfall
  meldet, pausiert und weitermacht, sobald das Netz zurück ist (`network_wait`
  für einen Host, `netz_warten_erreichbar` für Werkzeuge, die selbst laden).
  Grenze `CHIMERA_NETWORK_LIMIT` (600 s), danach ein benannter Befund statt
  eines stillen Abbruchs. Geprobt wird über TCP, nicht über ICMP.

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
- **uv für die Python-Abhängigkeiten in Modul 50** (`installer/lib/python.sh`).
  Vorgabe smilez (2.11./5.11.): uv löst Abhängigkeiten als Ganzes auf und ist
  auf dem Pi schneller als pip. Bauform:
  - uv liegt in einem **eigenen Werkzeug-venv** `<CHIMERA_OPT>/tools/uv` und
    wird **nur angelegt, wenn es fehlt**; installiert wird es mit pip (der
    die Prüfsummen der PyPI prüft).
  - `pydep_holen()` nimmt uv `pip install --python <venv>`; vorgeladene
    Wheels gehen als `--find-links` mit — **nur wenn das Verzeichnis
    existiert** (ein fehlendes bricht uv ab, gemessen).
  - **Harte Zeitgrenze** `CHIMERA_UV_FRIST` (Vorgabe 600 s) über `timeout`;
    fehlt `timeout`, läuft der Aufruf ohne Grenze.
  - **Rückfall auf pip** bei jedem uv-Fehlschlag — derselbe Abruf, dieselbe
    Warte-Schleife. Schalter `CHIMERA_UV=aus`.
  - Das Ergebnis zählt weiterhin: `pydep_ensure` misst nach dem Abruf, der
    Exitcode von uv oder pip entscheidet nichts.
  Tests `installer/tests/test-uv.sh` 20 ok (Werkzeug-venv, zweiter Aufruf
  richtet nichts mehr ein, venv nicht anlegbar → pip, uv scheitert → pip,
  uv **und** pip scheitern → Befund, Zeitgrenze greift in 1 s, `--find-links`
  nur bei vorhandenem Verzeichnis). Gegenproben: Zeitgrenze ausgebaut → 2 rot,
  Rückfall ausgebaut → 3 rot. `test-python-env.sh` 53 ok, `test-portability.sh`
  10 ok. **Am Pi gemessen (5.11., je eigener Cache, kalt, dieselben Pakete
  Pillow 13.0.0 + numpy 2.5.4): pip 41 s, uv 10 s.** uv liegt dort als
  0.13.7 (aarch64) unter `/opt/chimera/tools/uv`; der Lauf war grün, LED ok.
  Dabei fiel ein echter Fehler auf: Zuerst stand die Bereitstellung nur im
  Abrufzweig — auf einem Gerät, dessen Abhängigkeiten schon erfüllt sind,
  wurde uv also **nie** angelegt (Lauf grün, kein uv). Jetzt wird es auch im
  fertigen Fall bereitgestellt.

### Geändert
- **`OLLAMA_MODEL` entfällt** (smilez, 11.11.): `provider/gateway.py` liest
  die Umgebung nicht mehr, sondern schickt ohne eigene Wahl ein leeres
  Modell — das Gateway entscheidet. `provider/setup.py` nimmt die Wahl des
  Gateways statt der Zahl im Modellnamen (`_size_of` bleibt nur für
  Anbieter, die keine Wahl melden). `SERVICE_ENV_NAMEN` im Installer ist
  leer: eine Einstellung, die aussieht wie ein Schalter und keiner ist,
  gehört nicht in die Umgebung des Dienstes.
- **Der Agent führt nichts mehr selbst aus** (`src/chimera/agent/sohelper.py`,
  `tools.py`): `run_command`, `read_file`, `write_file` und `list_dir` gehen
  als eine JSON-Zeile an den Socket des Ausführers; geprüft und ausgeführt
  wird dort. **Kein Rückfall:** Ist er nicht erreichbar, wird nichts getan
  und der Grund genannt („Der Ausführer ist nicht erreichbar (…). Es wurde
  nichts ausgeführt."). Die Texte bleiben dieselben wie bisher
  („Abgelehnt: …"), damit das Modell keinen Unterschied sieht. `set_face`
  bleibt im Dienst (Anzeige, kein Programmstart).
  `tests/test_tools_socket.py` prüft, dass `tools.py` **kein `subprocess`
  mehr kennt** (sonst gäbe es einen zweiten Weg) und dass die Anfragen so
  über den Draht gehen, wie der Ausführer sie erwartet;
  `tests/gegenprobe_tools_socket.py` macht die Zusage rot, wenn jemand den
  zweiten Weg zurückholt (Import, Selbstlesen, verschluckter Fehler).
- **`chimera-sohelper` kennt `--version` und `--ping`:** dieselbe Form wie
  beim Gateway (`chimera-sohelper <VERSION>`), damit Ablage und Installer
  am Programm selbst prüfen können statt am Exitcode von systemctl.
- **Modul 55 legt beide Rust-Binaries ab** (`chimera-tor` **und**
  `chimera-sohelper`); die Prüfung (Prüfsumme, Architektur, Laufprobe,
  fremde Datei, Manifest) steht in `installer/lib/binary.sh` und wird von
  Schritt 99-sohelper mitbenutzt. Fehlt eines der beiden, ist das ein
  Befund (rc 1); das andere wird trotzdem abgelegt.
- **Gateway-Binary neu gebaut und abgelegt** (nach 2.3a): `gateway/chimera-tor-aarch64`
  stammt jetzt aus dem CI-Lauf zu `cba71db` (Prüfsumme `e57433ad…`,
  `rust/`-Baum `068fecc3…`, Version `0.1.0-pre`), gelegt von
  `tools/gateway-binary.sh`. Belegt über den Socket statt über den Quelltext:
  die neue Fassung antwortet auf `{"op":"katalog_lesen","id":"ollama"}` mit
  `{"ok":true,…}`, die alte (`fa7edfb`, Gegenprobe) mit `op_unbekannt`. Damit
  bekommt der Dienst das gemessene Kontextfenster statt des Vorgabewerts.
- **Drei Regeln nachgeschärft** (Review 11.11., nur Blaupause): Der
  Cache eines Laufs beantwortet nur die Frage, die gestellt wurde
  (`--bereich netz` hört nicht auf ein globales „ok"), eine Reparatur läuft
  zur Zeit (`state/mojo.lock`, nicht blockierend), `context_window` kommt aus
  der Serverabfrage statt aus einer Konstante, und atomares Schreiben heißt
  jetzt vollständig: eindeutiger Sidecar-Name je Schreiber, `fsync` vor dem
  Umbenennen, `copymode` für bestehende Rechte.
- **`docs/INSTALLER.md`: das HAT-EEPROM gibt es auf unserem Board nicht**
  (gemessen 6.11., `HARDWARE.md`/`DISPLAYS.md`): kein
  `/proc/device-tree/hat/`, nur die ES8389-Fassung trägt eines. Die Revision
  bleibt physisch zu prüfen.
- **`docs/CLI.md`: zwei Dateien, zwei Leser** — die `.env` liest nur das
  Gateway (`root:chimera-tor` 0640), der Dienst liest `config/dienst.env`
  (heute nur `OLLAMA_MODEL`). `OLLAMA_API_BASE` ist damit eindeutig eine
  Gateway-Einstellung.
- **Das Gateway ordnet ausgehende Ziele ein** (DESIGN 5n): `ip_im_lan` gilt
  künftig auch für ausgehende Verbindungen, geprüft wird die aufgelöste
  Adresse und jeder Sprung. Lokal und LAN ohne Rückfrage, Internet nur für
  eingetragene Anbieter; eine neue Adresse wird einmal zurückgefragt. Damit
  gehen Display und Sprachmodell über dasselbe Tor wie alles andere.
- **Gedächtnis: keine Verdichtung per Modell mehr** (DESIGN 8c): Monats- und
  Jahresordner statt Zusammenfassung, Wegweiser-Datei mit Sprungmarken
  (`## JJJJ-Www`), erzeugt im Harness aus Überschriften, Zeitstempeln,
  offenen Punkten und Entscheidungen — ohne Tokens, ohne erfundene Prosa. Im
  Kontext steht die aktuelle Woche, ältere Einträge holt `erinnern`.
- **ACP: das Display ist verleihbar** (DESIGN „ACP“ Punkt 10) — Ergänzung,
  keine Umwidmung: Ein gekoppeltes Gerät spricht dasselbe Display an
  (vorhandene Moods, Status), mit eigener Kennung und ohne Werkzeuge.
- **Der Agent-Dienst hat kein Netz mehr und liest die `.env` nicht**
  (DESIGN 5n, Verschärfung; smilez 10.11./11.11.). Die Unit trägt
  `IPAddressDeny=any` und lädt statt der `.env` eine eigene
  `config/dienst.env`, die der Installer aus einer Erlaubnisliste schreibt
  (`OLLAMA_MODEL` — kein Geheimnis). Grund: systemd liest
  `EnvironmentFile=` als root und reicht die Werte an den Prozess durch;
  eine für den Dienst unlesbare `.env` stünde trotzdem in seiner Umgebung.
  Die `.env` gehört jetzt `root:chimera-tor` — gesetzt in Schritt 99, weil
  der Nutzer erst dort entsteht (in Schritt 98 wäre der `chown` ein stiller
  Fehlschlag). `provider/setup.py` hat keinen Rückfall mehr auf den
  direkten Weg: Ohne Gateway ist Ollama „nicht verfügbar", und das
  Protokoll sagt warum. **Am chimera-pi belegt:** `IPAddressDeny=::/0
  0.0.0.0/0`, Unit laedt nur `dienst.env` und `anzeige.env`, `.env` gehoert
  `root:chimera-tor`, keine Schluesselnamen mehr in der Umgebung des
  Dienstes, Socket antwortet, keine TCP-Sockets, 12 Module ohne Fehler,
  `NRestarts=0`, beide Dienste aktiv.
- **Schritt 55 nimmt das Binary aus dem Startbaum, nicht aus einem
  Prerelease.** Kein Netz, kein Commit, kein `state/quelle-commit` mehr: Er
  prüft die `.sha256`-Datei daneben, die Architektur, startet das Binary und
  vergleicht `--version` mit der `VERSION` der Quelle, dann legt er es ab.
  Ist der `rust/`-Baum im Startbaum neuer als der, aus dem das Binary gebaut
  wurde, steht das im Protokoll — **ohne Befund** (smilez, 10.11.: „ja"),
  denn zwischen zwei Fassungen ist das der Normalfall. Fehlt das Binary im
  Startbaum, ist das ein Befund (rc 1) mit Hinweis, wohin es gehört.
  `CHIMERA_RUST_URL` entfällt (der Schritt holt nichts nach),
  `CHIMERA_RUST_LOKAL` bleibt für selbst gebaute Binaries. Tests neu:
  `test-rust.sh` 77 Prüfungen, `counter-check-rust.sh` 12 Mutationen, beide
  unter sh, dash und BusyBox grün.
- **Blaupause: Das Gateway-Binary bekommt einen festen Namen und kommt aus
  dem Startbaum** (smilez, 10.11.; DESIGN Regel 14). Bisher sucht Schritt 55
  ein Prerelease `rust-<Commit>` — der Name wechselt mit jedem Commit, und
  eine frische Installation aus einem Zip bekäme gar kein Gateway.
  Entschieden: fester Name, Bau für jedes Release und bei Bedarf für
  Tests auf der Hardware, ein Zip bringt sein Binary mit. Nur Design und Roadmap —
  gebaut ist nichts. Das Binary liegt künftig als Datei im Repo
  (ZIP-Shipping: Repo als Zip holen, auf dem Pi entpacken, daraus
  installieren), abgelegt von einem CI-Lauf oder mit einem Commit; offen
  sind Ort und Dateiname.
- **Blaupause: Modellwahl nach dem Vorbild des eigenen Forks von
  openclawgotchi** (smilez, 10.11.; DESIGN 5n): gespeicherte Wahl, eine
  Stelle für die Auflösung, nur Modelle mit `tools`. Der Abgleich nennt,
  was Chimera davon schon hat (Adresse beim Gateway, Platzhalter, Katalog
  mit `tools`) und was fehlt (gespeicherte Wahl, Frage im Installer).
- **Blaupause: Regel 10g bekräftigt** (smilez, 10.11.): erst nachsehen, was
  da ist, was die Änderung berührt und wo sie anknüpft; mit der Blaupause
  vergleichen, bevor gebaut wird. Die Reihenfolge der Sicherheitsarbeit
  (Sperre, Ausführer, Claude ins Gateway mit Schwärzung, übrige Tore) ist
  genehmigt und steht in der ROADMAP.
- **Blaupause: Der Einstieg des Installers wird eine `.sh`** (smilez,
  10.11.): Der Nutzer ruft ihn aus seinem Betriebssystem auf. Heute heißen
  die Einstiege `installer/chimera-install` und
  `uninstaller/chimera-uninstall`, ohne Endung. Nur Design (Regel
  „Installerhelfer“) und Roadmap (Phase 8). Gebaut ist danach der Einstieg
  `chimera-installer.sh` (siehe „Hinzugefügt“); die inneren Dateien heißen
  weiter wie bisher.
- **Blaupause: Bauplan für die Sperre des Agent-Dienstes** (DESIGN 5n,
  „Bauplan, Stufe 1“): jede berührte Stelle mit Ist und Soll, dazu der
  Vorrang von Regel 5l bei der `.env` — drei Stellen im Design und der
  Installer sagen noch, der Agent lese sie.
- **Blaupause: Regel 5n verschärft — Netz ausschließlich über das Gateway,
  ohne Rückfall.** Vorgabe smilez (10.11.): Alles, was Chimera tut und Netz
  braucht, geht über das Gateway, und nur wenn dessen Tore den Aufruf
  durchlassen (feste Regeln, kein Modell). Neu im Design: kein direkter Weg
  aus dem Dienst mehr, auch nicht als Rückfall; die Unit des Dienstes lädt
  die `.env` nicht (Dateirechte genügen nicht, systemd reicht die Werte
  durch); der Ausführer hat nie Netz. Dazu der am Pi gemessene Stand: Die
  Unit trägt keine Netzsperre, ein Prozess unter dem Nutzer `chimera`
  erreicht Internet und LAN, die Namen der Zugänge stehen in der Umgebung
  des Dienstes. `provider/` und `bot/telegram.py` bleiben, gehen aber selbst
  durch das Gateway. Alle Tore liegen am Gateway: zu den heutigen kommen
  die Schwärzung vor der Cloud, eine Positivliste für `web_abruf` und die
  Rückfrage beim Nutzer. Nur Design und Roadmap — nichts davon ist gebaut.
- **ACP-Bibliothek gemessen und verworfen: der Mindestumfang wird selbst
  gebaut.** Die Rust-Crate `agent-client-protocol` (3.6.0 und 5.0.0) gegen
  denselben JSON-RPC-Zeilenrahmen mit `serde_json` — gleiche Arbeit, gleiche
  Antworten: 2,07 MB gegen 516 kB Binärdatei, 5 034 ms gegen 370 ms für
  20 000 Anfragen, 984 kB und 10 Fäden gegen 424 kB und einen Faden, 105 ms
  gegen 26 ms bis zur ersten Antwort. Die Crate brächte `tokio` mit, das
  Gateway läuft ohne Laufzeit; sie bleibt Referenz für die Feldnamen, nicht
  Abhängigkeit. Bericht samt Grenzen der Messung (nur `initialize`, nicht das
  Streaming) in `docs/messungen/2026-11-06-acp-bibliothek.md`.
- **Platzprüfung vor dem Snapshot rechnet den Bedarf, statt einen Richtwert zu
  prüfen** (`neustart.rs`, `platzbedarf_mb`). Bisher galt „100 MB frei" als
  Bedingung — auch für einen Snapshot von 200 MB. Jetzt zählt die Summe der
  zu sichernden Dateien, **doppelt** (der neue Snapshot und das Archiv des
  vorherigen liegen kurzzeitig beide auf der Karte), mit 100 MB als
  Untergrenze für den Fall, dass eine Größe nicht lesbar ist. Die Meldung
  nennt Zahl, Bedarf und Herkunft. Tests: 60-MB-Datei → 120 MB Bedarf,
  kleine Dateien → Untergrenze, unlesbare Datei → Bedarf unbekannt, 110 MB
  frei für 60 MB Dateien → kein Snapshot (Gegenprobe: Faktor 1 → genau diese
  zwei Tests rot).
- **Python-Abhängigkeiten werden bei jedem Lauf aufgefrischt — kein Lock.**
  Vorgabe smilez (5.11.): *immer die neueste Fassung, die mit allem anderen
  kompatibel ist.* Ein Abhängigkeit kann vor dem ersten Installerlauf auf dem
  Gerät liegen und dabei veraltet sein; „läuft, also nichts zu tun" hieße,
  eine geschlossene Sicherheitslücke nie einzusammeln. `--upgrade` ist damit
  Vorgabe in `pydep_holen` (`CHIMERA_PIP_UPGRADE=aus` schaltet es ab), und
  Modul 50 endet nicht mehr vorzeitig mit „bereit", wenn die Umgebung steht.
  Ablauf: `pip freeze` nach `state/python-stand.txt` → auffrischen →
  Nachweis → bei Bruch den gesicherten Stand zurückspielen (erst dann wird
  die Sicherung überschrieben; andersherum rollt der Rückfall auf den
  kaputten Stand — der neue Test hat genau das gefunden). Ohne Netz keine
  Warte-Schleife, solange die Umgebung vollständig ist (Auffrischung, kein
  Herstellen). `uv pip compile` als Lock ist damit **verworfen**: Es friert
  Fassungen ein und liefert Updates erst beim Neukompilieren. Gemessen am Pi:
  die Auffrischprüfung kostet 888 ms („Would make no changes").
  Tests `test-python-env.sh` 63 ok (Stand-Sicherung, „Fassungen
  unverändert", Bruch → Rückfall → Umgebung wieder messbar; Gegenprobe ohne
  die Prüfung nach der Änderung → kein Rückfall, Mutation per `cmp` belegt),
  `test-uv.sh` 28 ok (Vorgabe `--upgrade`, Schalter aus).
- **uv für Modul 50 eingeführt und am Pi gemessen**
  (`docs/messungen/2026-11-05-vorab-laden-und-uv.md`). Je Lauf kalt
  (venv, pip-/uv-Cache weg), sieben Läufe: ohne uv 82–85 s in Modul 50
  (Gesamt 107–126 s), mit uv 53–58 s (Gesamt 79–81 s) — **uv spart rund
  30 s**. uv liegt in einem eigenen Werkzeug-venv (`/opt/chimera/tools/uv`),
  wird nur angelegt, wenn es fehlt, und hat eine harte Zeitgrenze
  (`CHIMERA_UV_FRIST`, 600 s); scheitert es, geht derselbe Abruf über pip.
  Achtung auf die Lehre aus der Messreihe: `uv pip download` gibt es nicht,
  und Holen ohne Installieren kann nur pip.
- **`CHIMERA_UV` geht jetzt an den Helfer** (`HELFER_UMGEBUNG`). Vorher
  erreichte ein gesetzter Schalter den Lauf nicht — beim Messen aufgefallen,
  weil `CHIMERA_UV=aus` trotzdem uv benutzte. Dabei ein zweiter Fehler:
  `pydep_holen` fragte nur nach dem uv-Binary, nicht nach dem Schalter;
  `CHIMERA_UV=aus` schaltete damit nur das Anlegen ab. Test `test-uv.sh`
  erweitert (uv wird bei `=aus` nicht benutzt, pip übernimmt), Gegenprobe rot.
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

- **Der zweite Reparaturlauf wartet, statt auszufallen** (smilez, 11.11.):
  Ist `state/mojo.lock` belegt, wartet `--miracle` bis zu fünf Minuten
  (`CHIMERA_MOJO_FRIST`) und kommt danach dran. Nach dem Warten wird **frisch
  gemessen** — der Oracle-Cache wird nicht befragt, weil die Befunde von
  vorhin überholt sind. Erst wenn die Sperre nach der Frist noch belegt ist,
  endet der Lauf mit 75. Tests: warten bis frei, aufgeben nach Frist,
  Gegenprobe (nicht warten → rot). 266 Tests grün.

### Entfernt
- **Vorab-Laden im Hintergrund wieder entfernt** (`installer/lib/vorab.sh`,
  `installer/chimera-prefetch`, `installer/tests/test-vorab.sh`, Schalter
  `CHIMERA_PREFETCH_RAD`, `--find-links` auf `state/prefetch/wheels` in
  Modul 50): Sieben kalte Läufe am Pi ergaben **0 s Gewinn**, in einem Lauf
  21 s Verlust (der Abruf nahm Modul 50 die Leitung); nur eine
  Erstinstallation hätte etwas abfangen können, und die ist nicht gemessen.
  Was 0 s bringt und gepflegt werden muss, ist toter Ballast — die
  Begründung und die Messreihe stehen in
  `docs/messungen/2026-11-05-vorab-laden-und-uv.md`. **uv bleibt:** Modul 50
  braucht mit uv 53–58 s statt 82–85 s, über vier Läufe stabil.
- **Anzeige:** Herstellertreiber `whisplay.py` samt `spidev`/`gpiod`/
  `python3-dev` aus dem venv; die Anzeigetypen `st7789` und `epaper` der
  alten Tabelle (kommen als Module `gamepi13` und `epd2in13b` wieder).

### Behoben
- **CI rot nach den nativen Werkzeugaufrufen** (`tests/test_gesicht_zustand.py`):
  Die Attrappe der Registry nahm kein `**kw` an, und ihr Antwort-Objekt hatte
  kein `werkzeuge` — beides ist jetzt Teil des Vertrags (ein Anbieter, der
  Werkzeuge trägt, muss beides können). Der Loop liest das Feld zusätzlich
  mit `getattr`, damit ein fremdes Antwort-Objekt ihn nicht mit `TypeError`
  aus dem Lauf wirft. Lokal lief der Test grün, weil er die Attrappe nicht
  mit Werkzeugen aufrief — der CI-Lauf hat es gefunden.
- **Die Gegenprobe zu Modul 55 maß nichts mehr** (`counter-check-rust.sh`):
  Seit das Ablegen und Prüfen des Binaries in `installer/lib/binary.sh` liegt
  (`186a116`, `a8098b4`), zeigten 11 von 13 Mutationen auf Muster, die in
  `steps/55-rust.sh` nicht mehr stehen — sie meldeten „Mutation griff nicht"
  statt zu prüfen. Gemerkt hat es niemand, weil die CI die
  `counter-check-*.sh` nicht fährt. Jetzt: Schritt 55 lädt die Bibliothek über
  `CHIMERA_BINARY_LIB` (Vorgabe unverändert der eigene Pfad), die Gegenprobe
  hat ein Ziel `lib` und verfälscht die Bibliothek selbst. Alle 13 Mutationen
  werden rot, jede am erwarteten Prüfpunkt. Der Rückbau-Prüfpunkt hieß
  außerdem noch `$_pfad` statt `$_ziel`.
- **Die Wahl sah einen leeren Katalog, weil der Anbieter anders heißt**
  (`dienst.rs`, am Gerät gemessen 11.11.): Die Netzsuche legt den Server als
  `ollama-192-168-178-100` an, der Dienst fragt `ollama` über die Adresse aus
  der `.env` — der Katalog lag unter der gefundenen Id, die Wahl unter
  `ollama` fand nichts und meldete `kein_modell`. `katalog_fuer` sucht jetzt
  zuerst unter der Id, dann unter **derselben Adresse**. Test mit beiden
  Namen (`der_katalog_der_netzsuche_gilt_auch_fuer_den_namen_ollama`).
- **Das Kontextfenster kam nie aus einer Messung** (`provider/gateway.py`):
  Der Dienst las den Katalog flach (`.get(modell)`), das Gateway legt ihn
  aber als `{"stand": …, "modelle": {…}}` ab (`daten::katalog_lesen`) —
  der Treffer war immer leer, und es blieb beim angenommenen Wert. Der Test
  hatte die falsche Form **nachgebaut** und war deshalb grün. Jetzt wird
  unter `modelle` gelesen, und der Test benutzt die echte Form.
- **`write_file` schrieb nicht sicher** (`agent/tools.py`): Die Nebendatei
  hatte einen festen Namen (zwei Schreiber teilten sie), es fehlte `fsync` vor
  dem Umbenennen (nach Stromausfall eine leere Datei), und bestehende Rechte
  gingen verloren (0640 wurde 0600). Jetzt: `mkstemp` vergibt den Namen je
  Schreiber, `flush` + `fsync` vor `os.replace`, `copymode` erhält die Rechte,
  und bei einem Fehler wird die Nebendatei weggeräumt. Test mit Gegenprobe
  (ohne `copymode` → rot).
- **Zwei Schreiber teilten sich dieselbe Nebendatei** (`daten.rs`,
  `.datei.neu` fest): Beim gleichzeitigen Zugriff über Gateway-Socket und
  `netzsuche`-Faden konnte das Umbenennen gelingen, während der Inhalt schon
  von der anderen Seite überschrieben war. Der Name enthält jetzt
  Prozesskennung und einen fortlaufenden Zähler (`sidecar_pfad`), das
  Vorab-Löschen entfällt damit. Test mit Gegenprobe (fester Name → rot).
- **`context_window` war geraten** (`provider/gateway.py` trug fest `32 000`):
  Das Gateway misst das Fenster längst (`/api/show` → `kontext` im Katalog),
  der Dienst konnte es aber nicht fragen — der Katalog war nur über die
  Weboberfläche erreichbar. Neu: `op: katalog_lesen` am Socket, und
  `GatewayOllama` holt das Fenster des bedienenden Modells daraus
  (`fenster_angenommen` bleibt `True`, solange es nur der Vorgabewert ist).
  Test mit Gegenprobe (Katalog nicht befragen → rot). **Das ausgelieferte
  Gateway-Binary kennt die Operation noch nicht** — bis zum Neubau antwortet
  es `op_unbekannt`, der Dienst bleibt beim Vorgabewert. Sicher, aber
  ungemessen.
- **Zwei Reparaturen konnten gleichzeitig laufen** (`--mojo --miracle`): Timer,
  `OnFailure=` und Installer hätten denselben Fehlversuch doppelt gezählt oder
  sich gegenseitig überschrieben (`mojo-versuche.json`). Ein reparierender Lauf
  nimmt jetzt eine **nicht blockierende** Sperre auf `state/mojo.lock`
  (`ReparaturSperre`); wer sie nicht bekommt, sagt es und endet mit 75
  (`EX_TEMPFAIL`). Test mit Gegenprobe (ohne Sperre → rot).
- **Der Oracle-Cache beantwortete eine größere Frage als gestellt**
  (`chimera-tor --mojo --miracle --bereich netz`): Lag ein Ergebnis mit
  `exitcode 0` von vorhin da, endete der Lauf sofort mit 0 — ohne das Netz zu
  prüfen. Ist ein Bereich genannt, wird der Cache jetzt nicht befragt
  (`darf_cache_antworten`, DESIGN Regel „Mojo"); der Lauf prüft selbst, auf
  den gefilterten Bereich. Test mit Gegenprobe (Cache immer befragen → rot).
- **Die V1-Warnung hing am HAT-EEPROM, das unser Board nicht hat**: Die
  Meldung „Auf V1 führt die Button-Leitung 5 V — ein Tastendruck kann das
  Board stromlos schalten" erschien nur bei `present`, also auf unserem
  Gerät **nie** — genau dort, wo sie gebraucht wird. Sie hängt jetzt an
  `whisplay_in_betrieb()`: Soundkarte im Gerätebaum (das Overlay legt sie
  an, der eigene Treiber beweist das Board) oder EEPROM. Die Meldung „HAT
  nicht aufgesteckt oder ohne EEPROM" hieß es bei aufgestecktem HAT —
  jetzt „kein HAT-EEPROM (bei der WM8960-Fassung normal)". Am Pi gemessen:
  `sound/compatible` = `pisugar,whisplay-soundcard`, kein
  `/proc/device-tree/hat`. Test: 50 ok (sh, dash, BusyBox), Gegenprobe
  (nur EEPROM fragen) macht genau einen Fall rot.
- **Der Geheimnis-Prüfer hielt eine Anschrift aus dem Gateway-Binary für
  eine private Mailadresse.** Ein statisch gelinktes Programm bringt
  Zeichenketten fremder Bibliotheken mit (eine Anschrift eines
  OpenSSL-Mitwirkenden aus dem Krypto-Anteil); die Textsuche darauf
  blockierte den Push. Eine
  Binärdatei wird jetzt auch **am Inhalt** erkannt (NUL-Byte in den ersten
  2 KB), nicht nur an der Endung, und die übersprungenen Dateien werden
  benannt („1 Binaerdatei(en) uebersprungen") statt verschwiegen. Dieselbe
  Grenze wie die Endungsliste, die es schon gab.
- **`test-einstieg.sh` war in der CI unter BusyBox rot** (`c385136`). Der
  Test ersetzte `id` durch eine Attrappe im Suchpfad. Die BusyBox der CI
  (Ubuntu `busybox-static` 1.36.1) nimmt ihre eingebauten Befehle vor dem
  Suchpfad; `id -u` meldete dort 0, und der Test brach an seiner eigenen
  Schutzprüfung ab. Jetzt schützt eine `systemd-run`-Attrappe vor einem
  echten Lauf (in keiner Shell eingebaut), und die eine Prüfung, die einen
  gewöhnlichen Nutzer braucht, wird dort als übersprungen gemeldet, nicht
  als grün. Nachgestellt mit derselben BusyBox aus dem Ubuntu-Archiv.
- **Der Installerlauf hinterlässt sein Protokoll jetzt vollständig auf der
  Karte** — auch nach dem `exec`-Neustart in Modul 00 (Regel 10e). Ursache am
  Pi gemessen: `HELFER_UMGEBUNG` reichte `CHIMERA_LOG_DIR` an den Helfer
  weiter, aber nicht `CHIMERA_LOG_ZIEL`. In `lib/common.sh` gilt „`LOG_DIR`
  ist gesetzt" als `--log-dir` des Nutzers — dann wird das Ziel gleich der
  Quelle gesetzt, die Protokolle bleiben in `/run` (tmpfs), und `log_sync`
  gleicht absichtlich nichts ab. Belegt an `install-20261105-005936.log`:
  `/run` 10.719 B, `/opt` 1.902 B (bis Modul 00). Jetzt gehen beide Variablen
  durch die Umgebungsdatei; Nachweis nach dem Fix an
  `install-20261105-071018.log`: `cmp` identisch, 10.721 B auf beiden Seiten,
  13 Moduleinträge, „Fertig: 12 Module ohne Fehler", LED ok. Tests
  `test-helfer.sh` 51 ok, zwei neue Prüfungen (Ziel erreicht den Helfer, Ziel
  bleibt vom Quellordner verschieden); Gegenprobe: `CHIMERA_LOG_ZIEL` aus der
  Liste entfernt → rot. Der erste Anlauf der Prüfung war grün *ohne* Wert in
  der Datei (die Testschale hielt die Variablen noch) — deshalb `unset` vor
  dem Lesen.
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
- **Die CI veröffentlicht kein Prerelease mehr von selbst** (smilez,
  11.11.): Der Installer nimmt das Binary aus `gateway/`. Gebaut und
  geprüft wird bei jeder Änderung an `rust/` weiter; veröffentlicht nur
  noch auf Wunsch (`workflow_dispatch` mit `prerelease: true`), wenn eines
  zum Testen gebraucht wird.
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
- **Am chimera-pi eingespielt (11.11.2026, Stand `a8098b4`):** Module 55 und
  99-sohelper grün, `tools/abgleich.sh` meldet „der eingespielte Stand
  entspricht der Quelle". Nachweise am laufenden System: Nutzer
  `chimera-sohelper` in **keiner** Gruppe, `/opt/chimera/sohelper` 700 und
  sein Eigentum, `/run/chimera/sohelper.sock` 0660 `chimera-sohelper:chimera`,
  Unit mit `IPAddressDeny=::/0 0.0.0.0/0`, `InaccessiblePaths=/opt/chimera/config`,
  `ProtectSystem=strict`, `ReadWritePaths=/opt/chimera/sohelper`,
  `NoNewPrivileges=yes`, keine `SupplementaryGroups`. `--ping` antwortet.
  Die vier Werkzeuge als Nutzer `chimera` über den Socket: schreiben, lesen,
  auflisten, `ls -l` laufen; `../../etc/passwd`, `sudo id` und `curl` werden
  mit denselben Texten abgelehnt wie vorher. **Ruhezustand: 492 kB RSS**
  (Gateway zum Vergleich 1592 kB, `MemoryCurrent` ist wie erwartet nicht
  gesetzt — Controller auf dem Pi aus).

- **Netzsperre ohne localhost-Freigabe am chimera-pi (10.11.):** Ein Prozess
  unter dem Nutzer `chimera` mit `IPAddressDeny=any` erreicht das Gateway
  über den Unix-Socket (`status`, Modell-Liste des Ollama-Servers im LAN);
  `127.0.0.1:8080` und das Internet sind zu. `IPAddressAllow=localhost`
  wird nicht gebraucht.
- **Hardware-Checkliste am chimera-pi (6.11.):** Kernel
  `6.18.59+rpt-rpi-v8` mit vorhandenem `/lib/modules/.../build`,
  `snd-soc-wm8960` und `snd_soc_whisplay_soundcard` geladen, ALSA-Karte
  „Whisplay Sound" mit Playback und Capture, Aufnahme (2 s, 16 kHz) mit
  Pegel max 1432 / rms 333 — also echtes Signal, keine Stille — und
  Wiedergabe mit Exitcode 0; unter Last 185 MB von 462 MB verfügbar.
  Offen bleibt die Whisplay-Revision (V2?): Das Board hat kein HAT-EEPROM,
  sie ist nur physisch zu lesen. Alles in `docs/HARDWARE.md`,
  Abschnitt „Ergebnisse am chimera-pi".
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
