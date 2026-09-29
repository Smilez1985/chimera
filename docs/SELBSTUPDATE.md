# Selbstaktualisierung

Wie Chimera sich selbst aktualisiert, ohne sich dabei zu zerlegen.

Grundlage ist die erprobte Updateroutine aus dem PiHole-Projekt (2 402
Zeilen, läuft auf einem Pi Zero 2 W unter DietPi). Sie wird nicht kopiert,
sondern ihre Mechanik übernommen — sie löst dasselbe Problem unter
denselben Bedingungen.

Stand: 2026-09-29. Entwurf.

---

## 1. Warum nicht `patch_self.py`

openclawgotchi bringt eine Selbstveränderung mit, die den eigenen
Quelltext ändert — ohne Sicherung, ohne Selbstprüfung, ohne Rückweg. Auf
einem Gerät, dessen System auf eMMC liegt, gibt es bei einem misslungenen
Eingriff nichts auszubauen (`docs/HARDWARE.md` §3a).

Das Muster der PiHole-Routine ist das Gegenteil und deshalb die Vorlage:

    sichern → prüfen ob die Sicherung taugt → aktualisieren
      → Dienst prüfen → bei Fehlschlag gestuft zurückspielen

---

## 2. Was übernommen wird

### 2.1 Ohne verifizierte Sicherung kein Eingriff

Die Routine sichert nicht nur, sie **prüft die Sicherung**:

- Existiert die Quelle überhaupt?
- Hat das Kopieren funktioniert?
- Ist die Kopie **nicht leer**?

Erst wenn alle drei stimmen, wird angefasst. Das kommt aus einem realen
Fehlschlag: Gesichert wurde mit `cp` ohne erhöhte Rechte, das scheiterte
still, und der Rollback kopierte anschließend eine Datei, die nie
entstanden war, über ein kaputtes Programm.

Das ist dieselbe Fehlerklasse wie unser geprüftes `mktemp` und die
abgelehnte leere Eingabe (Regel 8a) — nur an einer anderen Stelle.

### 2.2 Die Selbstprüfung muss etwas bestätigen

Nicht „lief ohne Fehler durch", sondern „der Dienst läuft **noch immer**".
Die Routine prüft den Dienst in Sekundenschritten über eine Wartezeit —
ein Dienst, der startet und nach drei Sekunden abstürzt, gilt damit als
gescheitert.

Für Chimera heißt das: Dienst aktiv **und** Anzeige antwortet **und**
mindestens ein Anbieter erreichbar.

### 2.3 Gestufter Rollback

Nicht alles auf einmal zurück, sondern in Stufen — und nach jeder Stufe
prüfen, ob es schon reicht:

    Stufe 1: Programm zurückspielen   → läuft es wieder? fertig.
    Stufe 2: Konfiguration zurück     → läuft es? fertig.
    sonst:   sagen, dass Handarbeit nötig ist — mit den Befehlen dazu

Der letzte Punkt ist der wichtigste: Wenn auch der Rollback scheitert,
wird das **gesagt**, samt der Befehle zum Nachsehen. Kein stilles
Scheitern.

### 2.4 Der Rückweg liegt neben dem Programm, nicht darin

Ein eigener Befehl (`pihole-rollback`), kein Schalter im Hauptprogramm.
Begründung aus der Routine: Das Hauptprogramm gehört dem offiziellen
Installer und wird bei jedem Update überschrieben — ein dort eingebauter
Schalter wäre danach weg.

Für Chimera gilt das genauso: Das Rückspielwerkzeug wird bei jedem Lauf
neu sichergestellt und liegt außerhalb dessen, was aktualisiert wird.

### 2.5 Eine Kette bricht nicht beim ersten Fehler ab

Der Orchestrator läuft weiter, wenn ein Modul scheitert, und der Exitcode
ist die **Anzahl** gescheiterter Module. So merkt eine Zeitsteuerung den
Unterschied trotzdem.

Auch das kommt aus einem realen Fall: Ein defektes Modul stand vorn in der
Kette und hat ein halbes Jahr lang jede weitere Wartung verhindert. Jeder
Lauf endete dort — bevor je ein anderes Update passiert wäre.

### 2.6 Trockenlauf durchgehend

`DRY_RUN=1` zieht sich durch alle Module. Bei einem Werkzeug, das
Programme austauscht und Dienste neu startet, ist das kein Komfort
sondern Selbstschutz. Chimeras Installer hat dieselbe Betriebsart
(`--dry-run`), sie wird hier fortgesetzt.

### 2.7 Die Voraussetzung der Prüfung selbst herstellen

Der Leitsatz aus den Befunden der Routine:

> Eine Prüfung, die ihre eigene Voraussetzung nicht herstellen kann,
> meldet Unsichtbarkeit als Abwesenheit — und zwar positiv, ohne Alarm.
> Das Ergebnis sieht jedes Mal aus wie ein gesunder Lauf.

Konkret: Die Paketliste wurde nie aufgefrischt, also meldete jede Prüfung
„kein Update verfügbar" — in Wahrheit „ich habe seit Wochen nicht
nachgesehen". Belegt mit einer Paketliste, die einen Monat alt war.

Das ist eine Verschärfung unserer Regel 10g („nie raten"): **Wer prüft,
muss vorher dafür sorgen, dass er etwas sehen kann.**

---

## 3. Was für Chimera anders ist

| | PiHole-Routine | Chimera |
|---|---|---|
| Gegenstand | fremde Dienste | die eigene Software |
| Quelle | Paketverwaltung, Installer | Git |
| Prüfung | Dienst läuft | Dienst, Anzeige, Anbieter |
| Auslöser | Zeitsteuerung | Befehl, später Zeitsteuerung |

Der wesentliche Unterschied: **Chimera aktualisiert sich selbst.** Das
Programm, das den Rollback ausführen soll, ist dasselbe, das gerade
ausgetauscht wurde.

### Architekturregel 10i (verschärft) — Der Rückweg darf nicht vom Update abhängen

Das Rückspielwerkzeug muss laufen, wenn

- das Netz weg ist,
- die neue Fassung nicht startet,
- Abhängigkeiten fehlen, die das Update gebracht hat.

Also: eigenes Skript, keine fremden Bibliotheken, außerhalb des
aktualisierten Verzeichnisses, bei jedem Lauf neu sichergestellt.

---

## 4. Ablauf

    1  Trockenlauf anbieten, auf eMMC-Systemen nachfragen
    2  Änderungen holen (git fetch), noch nichts anwenden
    3  Sichern:  Arbeitsverzeichnis, Konfiguration, Mood-Bibliothek
       └─ Sicherung PRÜFEN — ohne sie kein Eingriff
    4  Anwenden (git checkout), Abhängigkeiten nachziehen
    5  Selbstprüfung:
       ├─ Dienst läuft nach 10 s noch
       ├─ Anzeige antwortet (ein Bild ausgeben)
       └─ mindestens ein Anbieter erreichbar
    6  Bei Fehlschlag gestuft zurück:
       ├─ Stufe 1: Programmstand zurück      → läuft es? fertig
       ├─ Stufe 2: Konfiguration dazu        → läuft es? fertig
       └─ sonst: melden, was von Hand zu tun ist
    7  Protokoll — auch bei Erfolg (Regel 10e)

Die Mood-Bibliothek gehört in die Sicherung: Sie ist über Wochen
gewachsen und lässt sich nicht aus Git wiederherstellen.

---

## 5. Offen

- Ob die Selbstprüfung die Anzeige wirklich ansprechen kann, während der
  Dienst neu startet, ist ungeprüft.
- Wie lange ein Rollback auf einem Pi Zero dauert, ist ungemessen.
- Die Sicherung der Mood-Bibliothek kann wachsen; eine Obergrenze fehlt.

---

## Quelle

Updateroutine aus dem PiHole-Projekt, Fassung vom 29.09.2026:
`update_orchestrator.sh`, `modules/lib_common.sh`,
`modules/update_pihole.sh`, `modules/pihole-rollback.tpl` und die
Befundsammlung `BEFUNDE-Updateroutine.md` — letztere ist der wertvollste
Teil, weil dort steht, **warum** jeder Schutz existiert, mit Datum und
Beleg.
