# Baureihenfolge der offenen Punkte

Stand 30.09.2026, nach dem HATFaces-Vergleich. Begründet, nicht geschätzt —
die Abhängigkeiten sind am Code geprüft.

## Ergebnis

```
1. Prioritäts-Verwalter (Kern)        ← zuerst, weil zweimal gebraucht
2. Statuszeile (nutzt 1)
3. Gesichter als Pakete (Phase 3b)
4. Temperaturkopplung (nutzt 1 und 2)
5. LED-Verwalter (nutzt 1)            ← später, Hardware nötig
```

## Warum der Prioritäts-Verwalter zuerst kommt

HATFaces hat dasselbe Muster **zweimal** spezifiziert: einmal für die LED
(`06_LED_Manager.md`), einmal für den Text (`07_Text_Overlay.md`). Beide
Dokumente beschreiben Quellen mit Basis-Priorität, einen Slot je Quelle,
Auflösung über Priorität und Laufzeit, dreistufigen Tiebreaker.

Dort steht ausdrücklich, dass sie sich die Grammatik teilen:

> Text-Overlay teilt sich die Prio-Grammatik (Abstände ≥ 10,
> deterministischer Tiebreaker, Thermal-Level-Konsument). Kein
> Code-Kopplung, nur Stil-Analogie.

**„Nur Stil-Analogie" ist die Stelle, an der ich abweiche.** Zwei Stellen,
die dieselbe Auflösungslogik unabhängig implementieren, sind genau die
Doppelimplementierung, die in ZTB dreimal dieselbe Logik zweimal
unterschiedlich gebaut hat — über Monate unbemerkt. Wenn die Regeln gleich
sind, ist es ein Baustein mit zwei Nutzern, kein Muster zum Abschreiben.

Also: ein `chimera/arbiter.py`, zweimal verwendet. Die Unterschiede (LED
mischt Farben, Text zeichnet Glyphen) liegen im Renderer, nicht in der
Auflösung.

## Warum die Statuszeile vor den Gesichtern kommt

Geprüft: Das Mood-Schema (`mood/schema.py`) hat **kein** Textfeld. Ein
Gesicht beeinflusst heute nicht, was in der Statuszeile steht. Die
Statuszeile ist damit unabhängig baubar.

Umgekehrt gilt das nicht ganz: HATFaces' Plugin-Format hat einen Abschnitt
`[text_overlay]` **pro Charakter** (an/aus, Stil). Wenn Gesichter später
eigene Overlay-Einstellungen mitbringen sollen, muss die Statuszeile einen
Platz dafür haben.

**Folge:** Statuszeile zuerst, aber mit einem vorgesehenen Haken für
gesichtsabhängige Einstellungen. Der Haken bleibt zunächst leer und wird
in Phase 3b gefüllt. Er wird als bekannte Lücke im Changelog geführt, nicht
verschwiegen (Regel 10h).

Der zweite Grund ist praktisch: Die Statuszeile ist kleiner und hat eine
fertige Grundlage (Panel ist 240×280, der Renderer nutzt 240×240). Sie
eignet sich, um den Verwalter an einem einfachen Fall zu erproben, bevor
er die komplexere Gesichter-Schicht trägt.

## Warum die Temperaturkopplung nach der Statuszeile kommt

Sie ist ein **Verbraucher** des Verwalters, kein eigener Baustein: Bei
`warn` wird weniger Fläche neu gezeichnet, bei `critical` bleibt nur die
Statuszeile. Beides setzt voraus, dass es eine Statuszeile gibt und dass
etwas entscheidet, was Vorrang hat.

Dazu kommt: Die Schwellen müssen **auf dem Pi Zero 2 W gemessen** werden
(HATFaces' 62/67/75 °C gelten für den RK3566). Das braucht Hardware.
Solange der Zugang fehlt, wäre der Code gebaut und die Zahlen geraten —
und geratene Schwellen sind schlimmer als keine, weil sie aussehen wie
gemessene.

## Warum der LED-Verwalter zuletzt kommt

Er braucht denselben Verwalter, aber zusätzlich Hardware zum Prüfen. Die
LED ist nachweislich ansteuerbar (Befund vom 30.09.), aber ein
Prioritätsverwalter für Lichtmuster lässt sich ohne Sicht auf die LED nicht
sinnvoll abnehmen.

## Was in die Blaupause muss, bevor gebaut wird

Nach der Projektregel („Wer etwas ändert, das im Design beschrieben ist,
ändert zuerst das Design"):

- [ ] **Regel: Konkurrierende Anzeigequellen werden zentral aufgelöst** —
      ein Verwalter, zwei Nutzer. Begründung: die Doppelimplementierung,
      die HATFaces mit „nur Stil-Analogie" in Kauf nimmt.
- [ ] **Regel: Wer anzeigt, besitzt die Zeit** — Muster sind reine
      Funktionen `f(t, wert) -> wert`, ohne eigene Zeitgeber. Ergänzt
      Regel 7 (ein Prozess, ein Framebuffer) um die Zeitachse.
- [ ] **§ Gesichter** im Design: Was ein Gesicht ist (Bündel aus Moods,
      Vorgaben, Herkunft), warum JSON, warum kein Python darin, welche
      Grenzen für ein erzeugendes Modell gelten.
