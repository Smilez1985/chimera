# LED-Takt: ein Faden für drei Kanäle — gemessen, verworfen

**Datum:** 3.11.2026 · **Gerät:** chimera-pi (Pi Zero 2 W, Kernel damals 6.18.50)
**Stand im Repo:** `fbef797` (LED 60 Hz, drei Fäden)

## Frage

Die drei LED-Kanäle (R, G, B) takten je in einem eigenen `SoftPWM`-Faden.
Bei 60 Hz sind das drei Thread-Wechsel zu beliebigen Zeitpunkten je
Periode — jeder reißt den Renderer aus dem Schlaf. In der ROADMAP stand
deshalb der Punkt „**ein Faden für alle drei Kanäle** mit gemeinsamer
Kantenplanung" (geschätzt ~2,6 % eines Kerns).

## Aufbau der Messung

`SoftPWMGruppe` plante die Kanten aller Kanäle gemeinsam je Periode:
an bei 0 (alle), aus beim jeweiligen Tastgrad; Kanten innerhalb von
0,2 ms teilen sich einen Wecker. Ein Faden statt drei.

Gemessen wurde die **CPU-Zeit des eigenen Prozesses** (`/proc/self/stat`
Feld 14+15) über 20 s, Frequenz 60 Hz, GPIO-Schreibfunktion als
Leerfunktion (`lambda v: None`) — damit misst man den Takt, nicht den Bus:

    python3 tools/pwm-vergleich.py <softpwm.py> einzel|gruppe 50 50 50

## Ergebnis (je 20 s)

| Tastgrade | drei Einzelfäden | eine Gruppe | Unterschied |
|---|---|---|---|
| 50/50/50 (Weiß, Grau) | 1,90 % | **1,55 %** | −18 % |
| 20/50/80 (Farbe) | 1,75 % | **2,10 %** | **+20 %** |

## Warum

Der Gewinn entsteht nur, wenn die Kanäle **dieselben** Kanten haben: dann
sind es zwei Wecker je Periode statt sechs. Bei ungleichen Tastgraden —
also bei jeder **farbigen** LED — hat die Gruppe bis zu vier Kanten je
Periode, und die liegen dichter beieinander als die Schläfchen der
Einzelfäden: mehr kurze `sleep`-Aufrufe, mehr Scheduler-Arbeit als
vorher. Der Normalfall am Gerät ist die farbige Glow-Farbe des Gesichts
(`mood`), nicht Weiß.

## Am Dienst gemessen

Gesamtlast des Dienstes blieb im Rauschen: vorher 8,10 % (20 s), nachher
8,10 / 8,50 / 8,70 / 9,45 % (je 20 s; Streuung dieser Größe am Gerät
±1,4 %). Die Fadenzahl sank von 14 auf 12 — messbar, aber ohne
CPU-Gewinn.

## Entscheidung (3.11.2026)

**Verworfen, nicht übernommen.** Der Umbau kostet im Normalfall mehr, als
er bringt, und macht den Takt komplizierter (Kantenplan, Gruppierung,
Periodenrest). Die drei Einzelfäden bleiben. Wer den Punkt wieder
aufnimmt, muss zuerst zeigen, dass die LED im Betrieb überwiegend
**weiß** leuchtet — sonst lohnt die Kantenplanung nicht.

**Lehre:** Eine Schätzung („spart die drei Weckrufe je Periode") ist
keine Messung. Erst der Vergleich Alt/Neu zeigt, dass die gemeinsame
Kantenplanung bei **ungleichen** Tastgraden teurer ist als getrennte
Fäden — der Vorteil hängt am Gleichklang, nicht an der Fadenzahl.
