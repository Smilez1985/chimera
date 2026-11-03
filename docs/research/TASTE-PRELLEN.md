# Research: Die Seitentaste der Whisplay prellt

Stand 3.11.2026, gemessen am **Pi Zero 2 W** (Kernel 6.18.50) mit der Whisplay
über `/dev/gpiochip0`, laufender Dienst `chimera.service`, Commit `c99b362`.
Folgerungen stehen in `docs/DESIGN.md` (Regel 7a, Abschnitt „Fünf Absichten
auf einer Taste") und in `docs/HERKUNFT.md` §4.2/§4.3.

*Research: button bounce on the Whisplay HAT. English summary at the end.*

---

## 1. Warum überhaupt gemessen wurde

Die Taste wurde bis 3.11.2026 alle **5 ms** abgefragt (`BUTTON_POLL_INTERVAL_SEC`
der Vorlage, PiSugar `runtime/whisplay.py`). Das kostete 200 `ioctl`s je
Sekunde — am Gerät **1,3 % eines Kerns im Leerlauf** für einen Taster, der
meistens nicht gedrückt ist.

Ersetzt durch **Kantenereignisse** des Kernels (GPIO-ABI v2):
`event_buffer_size`, `GPIO_V2_LINE_FLAG_EDGE_RISING|FALLING`, `read()` auf den
Zeilen-FD. Am Gerät belegt, Gesamtlast 10,8 % → **9,5 %** eines Kerns.

Der Nebeneffekt war unerwartet: Die Abfrage im 5-ms-Takt hatte **entprellt**.
Ohne sie kam das rohe Signal durch.

## 2. Der Befund

Protokoll einer Sitzung, in der ein Druck als „dreifach" erkannt wurde
(Flanken mit monotoner Zeit in Sekunden):

```
5239.217 fallend
5239.219 fallend
5239.220 fallend
5239.221 steigend
5239.222 fallend
5239.223 steigend
5239.224 fallend
5239.225 steigend
5239.445 steigend      ← 220 ms später wieder aktiv
5239.446 fallend
5239.743 steigend
5239.744 fallend
5239.745 fallend
5239.746 fallend
5239.747 steigend
5239.749 fallend
5239.749 steigend
5239.750 fallend
5239.751 steigend
5239.752 fallend
5239.753 steigend
5239.754 steigend
5239.880 steigend      ← nach 136 ms Ruhe
```

| Größe | Wert |
|---|---|
| Flankenabstand im Prellen | **0,8–2 ms** |
| Dauer einer Prellserie | **bis 136 ms** |
| Serien je Druck | 2–3 |
| Folge | ein kurzer Druck ergab „dreifach", sieben Fehlerkennungen in 10 s |

Im selben Protokoll standen Paare wie „doppelt" (23:03:15,700) und „lang"
(23:03:16,121) — 0,4 s Abstand, obwohl „lang" 0,7 s Haltedauer verlangt. Das
war der zweite Zeuge: Die Drücke wurden nicht nur falsch gezählt, sie wurden
zerlegt.

## 3. Was nicht half

**Sperrfenster von 30 ms nach der letzten angenommenen Flanke.** Klingt
richtig, ist es nicht: Solange ununterbrochen neue Flanken kommen, liegt jede
weitere mehr als 30 ms nach der vorigen genommenen — das Fenster greift nie.
Nachgewiesen im selben Protokoll: Die Kette 5239.744 … 5239.754 hätte bei
30 ms Sperre trotzdem mehrere „Klicks" ergeben.

## 4. Was hilft: den Pegel lesen, nicht die Flanke

```
Flanke weckt den Faden
  → warte, bis 80 ms keine neue Flanke kommt (Notbremse: 300 ms)
  → lies den ECHTEN Pegel (GET_VALUES/ioctl)
  → melde nur, wenn er sich vom zuletzt gemeldeten unterscheidet
```

Damit erzeugen Prellserien, die zum alten Pegel zurückkehren, **kein**
Ereignis; nur ein Pegel, der nach dem Prellen anders ist, zählt. Die
30-ms-Sperre bleibt in `display/gesten.py` als zweite Stufe stehen.

**Nachher-Messung (23:09, echte Drücke am Gerät):**

```
23:09:12  Geste „kurz"
23:09:14  Geste „lang"
23:09:17  Geste „halten"
23:09:20  Geste „halten_ende"
23:09:23  Geste „doppelt"
23:09:27  Geste „dreifach"
```

Fünf Gesten, fünf Zeilen, keine Fehlerkennung.

## 5. Offene Fragen

- **Reicht 80 ms immer?** Gemessen ist *eine* Taste an *einem* Gerät. Prellen
  wird mit Alter und Kälte länger; die Notbremse (300 ms) verhindert nur das
  Hängen, nicht die Fehlzählung. Wenn wieder Fehlerkennungen auftreten: erst
  das Pegel-Protokoll (`log.debug`) einschalten, dann die Ruhezeit erhöhen —
  nicht auf Verdacht.
- **Zweite Whisplay-Revision** (mit Joystick, HERKUNFT §4.2) hat andere
  Taster; dort ist die Ruhezeit erneut zu messen.
- **Hardware-Entprellung** (RC-Glied) wäre die saubere Lösung, verlangt aber
  einen Lötkolben am Gerät — bei 80 ms Software-Ruhe nicht nötig.

---

## English summary

The Whisplay's side button bounces for up to **136 ms** (edges every 1–2 ms,
in 2–3 bursts per press). The previous 5 ms polling loop had been debouncing
by accident; switching to kernel edge events (GPIO ABI v2, saving 1.3 % of a
core) exposed the raw signal, and a single press was reported as a triple
click. A 30 ms lockout window does not help — bursts keep producing edges
spaced wider than the window. The fix: an edge only wakes the reader, which
then waits for 80 ms of silence (300 ms cap) and reports the **actual level**
read back from the line, only if it differs from the last reported one.
Measured after the change: five gestures, five log lines, no false
detections.
