# Research: Mojo — Gesundheitsprüfung und Selbstreparatur

Stand 1.11.2026. Quelle: die Repos `Smilez1985/rag4ll` (`rag4ll/mojo/`) und
`Smilez1985/llm_cross-compiler_framework` (`orchestrator/Core/mojo/`), beide
gelesen am 1.11.2026; Messungen am Zielgerät (Pi Zero 2 W, systemd 257).
**Nichts davon wird kopiert**; dieses Dokument hält fest, was Mojo ist, was
davon für Chimera taugt und was am Gerät gemessen wurde. Entscheidung und
Regeln stehen in `docs/DESIGN.md` (Regel „Mojo“), Vorhaben in `docs/ROADMAP.md`.

*Research: Mojo — health checks and self-repair. English summary at the end.*

---

## 1. Anlass

Vorgabe smilez (1.11.): Die Chimera-Dienste sollen nach dem Boot zuverlässig
starten, bei einem Fehler **erneut versuchen**, jedes Problem **protokollieren**
und, wenn auch der Neuversuch scheitert, **laut einen Fehler melden**. Dafür
nennt smilez Mojo aus den eigenen Projekten.

Befunde am Gerät, die den Anlass belegen:

- `chimera-sitzung.socket` blieb nach einem Installerlauf **inaktiv**
  (`Socket service chimera.service already active, refusing`); der Dienst lief
  22 Stunden ohne Sitzungs-Socket, und niemand erfuhr davon.
- Ein Dienst, der die Startgrenze (5 in 300 s) erreicht, bleibt `failed` und
  meldet sich bei **niemandem**: `OnFailure=` ist an keinem Dienst gesetzt, es
  gibt keinen Weg zum Display oder zu Telegram.
- `chimera-hardware.service` (`oneshot`) hat kein `Restart=`; scheitert er beim
  Boot, startet `chimera.service` trotzdem (nur `Wants=`).

## 2. Was Mojo ist

Ein **Gesundheitsprüfer mit Reparaturstufen**, in der Art von `brew doctor` oder
`flutter doctor`. In beiden Repos gleich aufgebaut:

| Merkmal | Wortlaut / Verhalten |
|---|---|
| Regelmaschine | Feste Prüfungen mit festem Code, **fragt nie ein Modell**; deterministisch, offline, sofort |
| Zwei Modi | *Oracle* schaut nur (Vorgabe, ohne Flag), *Miracle* (`--miracle`) repariert |
| Befund | `Severity` (ok, info, warn, error), Subsystem, stabiler Code, Meldung, Hinweis, optionale Reparatur, Stufe |
| Stufen | 1 sanft und lokal (Dateirechte, Aufräumen, Dienstneustart), 2 Komponente neu, 3 voller Installer oder Wiederherstellung; ohne ausdrücklichen Wunsch läuft nur Stufe 1 |
| Idempotenz | Jede Reparatur ist zweimal ausführbar, ohne dass etwas passiert |
| Exitcode | 0 sauber, 1 nur Warnungen, 2 mindestens ein Fehler |
| Schwärzung | Heimverzeichnis zu `~`, LAN-Adressen zu Platzhaltern, JWT und Geheimnisse zu `<redacted len=N>`; `127.0.0.1` und `0.0.0.0` bleiben sichtbar |
| Ausgabe | lesbar (nach Subsystem gruppiert) und `--json` für Skripte; `detail` nur mit `--verbose` |

### 2.1 Der entscheidende Mechanismus: Nachprüfen

`MojoRunner.fix()` läuft in **drei Phasen**:

1. Alle Prüfungen laufen, Befunde sammeln.
2. Jede Reparatur, deren Stufe nicht über der erlaubten liegt, läuft **einmal**.
   Wirft sie, wird das festgehalten, der Lauf bricht nicht ab.
3. **Dieselben Prüfungen laufen noch einmal.** Taucht ein Befund mit demselben
   `(Subsystem, Code)` wieder auf, hat die Reparatur nichts gebracht
   (`still_present_after`) — er wird als „versucht, hat nicht gegriffen“
   gemeldet, **nicht** in einer Schleife wiederholt.

Das ist genau die geforderte Kette *Versuch, Nachversuch, laut scheitern*. Die
Quelle für „wirkte es?“ ist nicht der Rückgabewert der Reparatur, sondern die
erneute Messung.

### 2.2 Das Cross-Compiler-Framework: strenger

Dort ist die Reparatur ein **Plan, bevor sie etwas anderes ist**
(`repairs/model.py`, `repairs/engine.py`):

- Der Plan besteht aus Schritten mit Art (`chmod`, `acl_narrow`, `switch_ref`,
  `restore_file`, `delete`, `overwrite`, `widen`, `vault`, `policy`, `audit`,
  `oversight`, `system`), Ziel, Zustand vorher und nachher und der Angabe, ob er
  sich rückgängig machen lässt.
- Die **Klasse** des Plans wird aus den Schritten **berechnet**, nie von der
  Reparatur deklariert: *delegable* (nur einengend oder umschaltend, umkehrbar),
  *person* (weitet Zugriff oder ist nicht umkehrbar), *person_deletion*
  (löscht oder überschreibt, nur über die Liste der Person), *person_here*
  (Tresor, Rechte, Protokoll, Aufsicht), *manual* (braucht das System: root,
  Pakete, Dienste).
- Der Plan trägt eine **SHA-256**; eine Antwort „ja, repariere“ bindet sich an
  genau diese Schritte. Ist der Plan inzwischen ein anderer, ändert sich
  **nichts** (`plan_changed`).
- Ablauf in sieben Schritten: **eine** Reparatur gleichzeitig (Sperre), dann
  prüft die zuständige Prüfung erneut (`already_fixed` wenn der Befund weg ist),
  nur harmlose Pläne laufen, **das Protokoll wird zuerst geschrieben, sonst
  ändert sich nichts**, Schritte der Reihe nach mit Vergleich-und-Tausch (der
  erste Fehlschlag bricht ab), Ende protokollieren, **erneut prüfen**:
  `repaired` oder ehrlich `still_present`.
- Ergebnisse: `repaired`, `still_present`, `already_fixed`, `plan_changed`,
  `failed`, `refused`. Eine abgelehnte oder gescheiterte Reparatur wirft nie;
  das Ergebnis nennt den Grund.

### 2.3 Das `systemd_health`-Modul in rag4ll

Entstand aus einer echten Krise (Update unter DietPi): `/run/nologin` blieb
stehen, 17 Ordnungszyklen im Journal, Dienste `inactive` trotz `enabled`,
`systemctl start` meldete „Transaction order is cyclic“. Sechs Prüfungen:

| Prüfung | Befund | Stufe 1 |
|---|---|---|
| `/run/nologin` | Anmeldesperre | Datei entfernen |
| Ordnungszyklen im aktuellen Boot | Dienste gestrichen | nur Hinweis und Doku |
| `systemctl --failed` | Dienst `failed` | `reset-failed`, dann `start`, bei Zyklusfehler `--job-mode=ignore-dependencies` |
| eigene Dienste aktiviert, aber nicht aktiv | stumm tot | Neustart, gleiche Ausweichstufe |
| Hersteller-Autostart | Zustand | Stufe 2 |
| Drop-in-Hygiene | `After=network-online.target` im Drop-in reaktiviert Zyklen | Hinweis |

Gelernt dort und für uns relevant: Die Reparatur gilt als „versucht“, auch wenn
`start` scheitert, **sobald** `reset-failed` den Zustand bereinigt hat; die
Wahrheit liefert die Nachprüfung. Journalinhalt wird **nicht** in den Befund
eingebettet (groß, vielleicht sensibel), nur Zählungen und die ersten drei
Zeichenketten.

## 3. Was für Chimera taugt, was nicht

| Aus Mojo | Übernehmen? | Begründung |
|---|---|---|
| Regelmaschine ohne Modell | **ja** | passt zu Regel 8a und zum 512-MB-Gerät |
| Oracle und Miracle getrennt | **ja** | lesen ist Vorgabe, Ändern braucht ein Flag |
| Befund mit stabilem Code und Stufe | **ja** | Dedup nach Reparatur hängt daran |
| Nachprüfung als Wahrheit | **ja** | der Kern der Anforderung |
| Stufen 1 bis 3 | **nur Stufe 1 automatisch** | höhere nur auf Wunsch |
| Plan mit SHA-256, Klassenberechnung | **später** | gehört zur Freigabe von Reparaturen durch den Nutzer (Web), nicht zur ersten Fassung |
| Schwärzung der Ausgabe | **ja** | Befunde gehen in Protokolle und Telegram |
| Befunddatei fürs JSON | **ja** | die Weboberfläche liest sie |
| Frageaufforderung im Terminal | **nein** | das Gerät hat kein Terminal; die Oberfläche fragt |
| Python und `structlog` | **nein** | Gateway ist Rust (Regel 14), kein neuer Prozess |
| `rag-*`-Dienstnamen, DietPi-Sonderfälle | **nein** | andere Dienste; die Prüfungen heißen bei uns anders |

## 4. Messungen am Gerät (Pi Zero 2 W, systemd 257)

Alle mit Wegwerf-Units (`/etc/systemd/system/chimera-probe*.service`), danach
entfernt. Gerät: 462 MB RAM, Kernel 6.18.

### 4.1 Wiederholung und Aufgeben

Unit mit `Restart=on-failure`, `RestartSec=1`, `StartLimitIntervalSec=300`,
`StartLimitBurst=3`, `ExecStart` scheitert immer:

- 3 Neustarts, danach `Start request repeated too quickly`,
  `ActiveState=failed`, `Result=exit-code`.
- Jeder Start, jedes Scheitern und die Ausgabe des Prozesses stehen im
  Journal. Die Unit erscheint in `systemctl list-units --failed`.
- Nach dem Aufgeben startet systemd nie wieder von selbst; es braucht
  `reset-failed` und einen neuen Start.

### 4.2 Wann feuert `OnFailure=`?

**Gemessen: bei jedem Fehlschlag**, nicht erst nach Erreichen der Startgrenze.
Bei 3 Neustarts kamen 4 Meldungen (3 Zwischenfehler plus 1 beim Aufgeben).
Eine erste Annahme „erst nach der Grenze“ war falsch und ist hier korrigiert.

Folge: Die Meldeunit muss **Zwischenfehler von der Aufgabe trennen**. Sie fragt
beim Aufruf `systemctl show <Dienst> -p ActiveState -p NRestarts`. Steht der
Dienst noch auf `activating` (Neustart ausstehend), ist es ein Zwischenfehler
und wird nur protokolliert. Steht er auf `failed`, ist es das Aufgeben und wird
**laut** gemeldet.

### 4.3 Vorlageneinheit und Umgebung

`OnFailure=chimera-mojo@%N.service` reicht den Namen des gescheiterten Dienstes
weiter; die Meldeunit sieht `MONITOR_SERVICE_RESULT` (`exit-code`),
`MONITOR_EXIT_STATUS` (`1`) und `MONITOR_UNIT` im Environment. Das genügt für
Ursache und Dienstname ohne zusätzliches Parsen.

### 4.3a Ursachen, die systemd selbst nennt (ohne Text zu deuten)

Zehn Wegwerf-Units, je eine andere Fehlerart; gelesen mit `systemctl show`
(`Result`, `ExecMainCode`, `ExecMainStatus`). Danach alles entfernt.

| Fehlerart | `Result` | `ExecMainStatus` | Ursache und Weg |
|---|---|---|---|
| Programm fehlt oder nicht ausführbar | `exit-code` | **203** | Pfad und Rechte prüfen |
| Nutzer fehlt | `exit-code` | **217** | Nutzer anlegen |
| Pfad in `ReadWritePaths=` fehlt | `exit-code` | **226** | Ordner anlegen |
| Arbeitsverzeichnis fehlt | `exit-code` | **200** | Ordner anlegen |
| `EnvironmentFile=` fehlt | `resources` | 0 | Datei anlegen oder `-` davor |
| Programm beendet sich mit 1 | `exit-code` | 1 | **Ursache nur in der Ausgabe des Programms** |
| Start dauert zu lange | `timeout` | 15 | Zeit oder Programm prüfen |
| Prozess per SIGKILL beendet | **`signal`** | **9** (`ExecMainCode=2`) | gekillt, häufig Speichermangel |
| Voraussetzung scheitert | (Job `dependency`) | 0 | die **andere** Unit hat `exit-code`; Meldung: „Dependency failed“ |
| Startgrenze erreicht | `exit-code` | 1 | „Start request repeated too quickly“ |

Zwei erste Messungen waren falsch gebaut und sind hier korrigiert: Ein Signal
im `sh -c` ohne `exec` meldet sich als Status 2, nicht als Signal; und eine
Abhängigkeit auf eine laufende `simple`-Unit scheitert nicht. Mit `exec` und
einer `oneshot`-Voraussetzung ergeben sich die Zeilen oben.

**Rechte (am Gerät gemessen):** Ohne root liest `systemctl show` Zustand und
Ergebnis, aber `journalctl` meldet „No journal files were opened due to
insufficient permissions“, auch für `chimera-tor`. Mojo braucht die Gruppe
`systemd-journal`.

**Grenze:** Fünf der Ursachen liefert systemd als Zahl und je einen bekannten
Weg. Bei Status 1 steckt die Ursache im Text des Programms; dort hilft nur eine
Liste fester Muster, die nicht jede Ursache trifft. Dann gilt „Ursache nicht
bestimmbar“ mit allen Rohdaten, nicht Schweigen.

### 4.4 Speicher (wegen „zuverlässig starten“: reicht der RAM?)

Vor und nach dem CMA-Test (`dtoverlay=cma,cma-size=16777216` in `config.txt`):

| | vorher | nachher |
|---|---|---|
| `CmaTotal` | 65536 kB | 16384 kB |
| `MemAvailable` | etwa 346 MB | etwa 367 MB |

Gewinn etwa 21 MB, nicht die geschätzten 48 MB: Der Kernel nutzt freie CMA-Seiten
bereits für verschiebbare Daten. Dienste starteten nach dem Neustart ohne Fehler,
`NRestarts=0`. Der Speichercontroller (`cgroup_enable=memory`) bleibt aus: kostet
nach Schätzung etwa 9 MB und bringt keinen RAM, nur Schutz.

### 4.5 Sitzungs-Socket

Nach einem Installerlauf war `chimera-sitzung.socket` `inactive (dead)` seit dem
Lauf, im Journal `Socket service chimera.service already active, refusing`.
Reparatur von Hand: Dienst stoppen, Socket starten, Dienst starten. Das ist eine
**Stufe-1-Reparatur** mit klarer Nachprüfung (`ls /run/chimera/sitzung.sock`).

## 5. Folgerungen für den Bau

1. **`chimera-tor --mojo [--miracle] [--json]`** im Gateway: Prüfungen als
   `impl Pruefung` plus eine Zeile in `pruefungen()` (wie bei den Sonden),
   Befund mit Code, Schwere, Stufe, Reparatur.
2. **Nachprüfung als Wahrheit**: `--miracle` führt Stufe 1 aus, prüft erneut, meldet
   `unreparierbar`, wenn derselbe Code zurückkehrt.
3. **Meldeunit** `chimera-mojo@.service` per `OnFailure=` an `chimera`,
   `chimera-tor` und `chimera-hardware`; trennt Zwischenfehler von Aufgabe.
4. **Zeitgeber** `chimera-mojo.timer` (nach dem Boot und stündlich), weil ein
   Dienst, der nie scheitert, aber still falsch läuft (Socket aus), kein
   `OnFailure=` auslöst.
5. **Laut** heißt: Journal mit Stufe `<3>`, Befunddatei
   `state/mojo-letzter.json`, Zeile im Protokoll auf der Karte (überlebt den
   Neustart), LED und Statuszeile auf dem Display, Anzeige im Status-Modul der
   Weboberfläche.
6. **Nicht jetzt:** Pläne mit Prüfsumme und Klassenberechnung (gehören zur
   Freigabe durch den Nutzer), Stufe 2 und 3, Telegram-Meldung (wartet auf die
   Telegram-Tür im Gateway mit `/model` und `/suche`).

## 6. Offene Fragen

- Ob `chimera-hardware.service` ein `Restart=` bekommen soll: ein `oneshot`
  unterstützt `Restart=on-failure` erst ab systemd 244, hier verfügbar; die
  Wirkung am Gerät ist nicht gemessen.
- Wo der Befund auf dem Display steht, wenn **kein** Renderer läuft (der Dienst
  selbst ist ausgefallen): die LED müsste das Gateway oder die Meldeunit setzen,
  nicht der Dienst. Die LED-Schnittstelle lebt heute im Dienst.
- Ob Befunde in `state/` (nur Gateway, Regel 10r) oder `logs/` liegen, damit der
  Agent sie nicht ändert und die Oberfläche sie liest.

---

## English summary

Mojo (from smilez' rag4ll and llm_cross-compiler_framework) is a rule-based
health checker with tiered repairs: *Oracle* only reads, *Miracle* (`--miracle`)
repairs. A finding has a severity, subsystem, stable code and fix tier. The key
mechanism is the **re-check after a repair**: if the same code reappears, the
repair did not hold and the finding is reported as not repairable — exactly the
retry-then-fail-loudly chain Chimera needs. Chimera adopts it in Rust inside the
gateway (`chimera-tor --mojo [--miracle]`), with a failure unit
(`OnFailure=chimera-mojo@%N.service`) and a timer. Measured on the Pi Zero 2 W
(systemd 257): `OnFailure=` fires on **every** failed start, not only when the
start limit is reached, so the unit must tell intermediate failures from giving
up; a stopped session socket after an installer run stays down silently; CMA 64
to 16 MB gained about 21 MB of available memory, not 48 MB.
