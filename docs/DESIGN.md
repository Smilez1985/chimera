# Chimera — Design

Was und warum. Tragende Entscheidungen, Architekturregeln, Grenzen.
Wer etwas ändert, das hier beschrieben ist, ändert **zuerst dieses Dokument**.

Stand: 2026-09-29. Pre-Alpha, nichts getaggt.

---

## 1. Was Chimera ist

Ein agentisches Harness auf Raspberry Pi mit Whisplay HAT. Zwei Dinge
unterscheiden es von openclawgotchi, aus dem es hervorgeht:

1. **Der Avatar wird generiert, nicht gezeichnet.** Der Agent schreibt,
   mischt und variiert seine Mood-Assets selbst.
2. **Sprachchat statt nur Text.** Vollständig offline.

Chimera ist **kein Fork** von Noisy und kein Merge. Noisy läuft
unverändert auf eigener Hardware weiter.

---

## 2. Herkunft und Lizenzgrenzen

| Quelle | Lizenz | Was übernommen wird |
|---|---|---|
| openclawgotchi | MIT | Code: Agent, Skills, Memory, LLM-Router, Telegram |
| Noisy | MIT (eigen) | Verfahren: Mood-Architektur, Render-Pipeline |
| OpenMinis | **GPL-3.0** | **Nur Muster. Kein Code.** |

### Architekturregel 1 — Die GPL-Grenze ist hart

Chimera ist MIT. OpenMinis ist GPL-3.0. GPL ist viral und in diese
Richtung nicht MIT-kompatibel.

**Es wird keine Zeile OpenMinis-Code übernommen — auch nicht übersetzt.**
Was übernommen wird, sind Lösungsmuster: Schwellwertschemata,
Staffelungslogik, Reihenfolgen. Algorithmen sind nicht schutzfähig,
Quelltext ist es. Wer hier einen Baustein ergänzt, dokumentiert ihn in Abschnitt „Übernommene Muster aus OpenMinis (nachgebaut, nicht kopiert)"
mit dem Hinweis "nachgebaut, nicht kopiert".

Noisy gehört uns selbst — dort ist Kopieren erlaubt. Dass der Renderer
trotzdem neu geschrieben wird, ist eine technische Entscheidung (Abschnitt „Renderer").

---

## 3. Mood-Assets: das Kernkonzept

### 3.1 Warum Noisys Format taugt

Ein Mood ist ein **deklaratives Dict**: Defaults plus Overrides. Kein
Code, keine Logik, geschlossenes Vokabular mit benannten Feldern und
erkennbaren Wertebereichen. Damit ist es von einem LLM zuverlässig
erzeugbar — und weil es keine ausführbare Logik enthält, entsteht dabei
**keine Ausführungslücke**.

Slots und Felder:

| Slot | Felder |
|---|---|
| `body` | `color`, `glow` |
| `eyes` | `scale_w`, `scale_h`, `look_offset`, `droopy` |
| `mouth` | `style` (Enum), `width` |
| `hair` | `visible`, `wobble`, `color`, `color_dark`, `color_light` |
| `physics` | `headbang_*`, `bounce_*`, `sway_*`, `shake_x/y`, `toke` |
| `particles` | `type` (Enum), `rate`, `color` |
| `accessory` | `type` (Enum) |

### 3.2 Was gegenüber Noisy entfällt

Noisy bildet Geräusche **fest** auf Moods ab. Chimera behält das Hören,
aber nicht die feste Zuordnung (Abschnitt „Umgebungshören im Ruhezustand"). Gestrichen wird deshalb:

- `labels` — AudioSet-Label → Mood (in Noisy 41×). Die Zuordnung trifft
  das Sprachmodell, nicht die Tabelle.
- `fingerprint` — Genre-Erkennung über Label-Indizien (7×)
- `energy` — BPM-/Lautstärke-Fenster (21×)

Eine **kleine** feste Zuordnung bleibt allerdings: die Reflexe für
Sofortreaktionen (Abschnitt „Umgebungshören im Ruhezustand", Ebene 1). Ein Erschrecken darf nicht auf eine
Modellantwort warten.

Es bleiben `priority`, `fast_track` und alle Darstellungs-Slots.
Neu hinzu: `origin` (builtin / mixed / generated), `created_at`,
`last_used` — für Herkunft und Aufräumen.

Mood-IDs werden **dynamisch** vergeben. Noisys feste Bereiche pro Gruppe
(Emotionen 20–29 usw.) funktionieren nicht, wenn zur Laufzeit neue Moods
entstehen.

### 3.3 Drei Stufen der Erzeugung

Von billig nach teuer. Das ist bewusst so gestaffelt: Ein LLM-Call pro
Gesichtsausdruck wäre weder bezahlbar noch schnell genug.

**Stufe 1 — Mischen. Kein LLM.**
Zwei Moods interpolieren: Farben im HSV-Raum, Zahlen gewichtet gemittelt,
bei Enums gewinnt das höhere Gewicht. Deckt den Alltag ab, kostet nichts.

**Stufe 2 — Variieren. Kein LLM.**
Begrenztes Rauschen auf einen bestehenden Mood, Seed aus dem Anlass.
Verhindert, dass dasselbe Gefühl immer pixelgleich aussieht.

**Stufe 3 — Erfinden. LLM, selten.**
Nur wenn Mischen nicht reicht. Der Agent bekommt das Vokabular als Schema
— benannte Bausteine **und** die freien Zeichenformen (Abschnitt „Der Renderer ist nicht die Grenze") — und
schreibt einen neuen Mood. Ergebnis wird validiert, gespeichert und ist
danach kostenlos wiederverwendbar.

### 3.3a Der Renderer ist nicht die Grenze

Noisy kennt benannte Bausteine: `mouth.style = "smile"`, `accessory =
"saxophone"`. Der Renderer weiß, wie man ein Saxophon zeichnet; das Modell
darf es auswählen. Damit ist der Ausdruck auf das gedeckelt, was jemand
vorher von Hand gezeichnet hat — eine Auswahlliste, kein
Ausdrucksvermögen.

**Chimera gibt die Grundformen heraus, aus denen diese Figuren ohnehin
bestehen.** Noisys gesamter Avatar, Saxophon und Rastamütze eingeschlossen,
ist aus elf Zeichenbefehlen gebaut:

    Flächen   ellipse, circle, rect, polygon, ngon
    Bögen     arc (offen), chord (Sehne), pieslice (Tortenstück)
    Striche   line, point
    Schrift   text

Dazu Farbe, Umriss, Füllung, eine Ebene (`behind`, `body`, `face`,
`front`) und eine Bewegung (`bob`, `sway`, `spin`, `pulse`, `flicker`,
`audio` — letztere folgt der eigenen Sprachausgabe, Abschnitt „Mienenspiel beim Sprechen").

#### Architekturregel 1a — Benannte Bausteine sind Vorschläge, keine Grenze

Ein Wert, den der Renderer nicht kennt, ist **kein Fehler**. Schreibt das
Modell `mouth.style = "zaehneknirschen"`, wird der Name übernommen und die
Darstellung kommt aus den freien Formen, die es mitliefert. Der Validator
vermerkt das, lehnt aber nicht ab.

Damit sind Noisys 41 Moods das, was sie sein sollen: **Beispiele dafür,
was möglich ist** — Startbestand zum Mischen, nicht Katalog zum Auswählen.

Zwei Dinge bleiben fest, beide aus gutem Grund:

- **Koordinaten sind relativ** (0..1, `0.5` ist die Mitte). Sonst wäre
  Erfundenes an 240×280 gebunden (Regel 6).
- **Es gibt eine Obergrenze** für erfundene Formen (`MAX_SHAPES`, derzeit
  40). Nicht als Bevormundung: Bei 15 Bildern je Sekunde bleiben rund
  66 ms pro Bild, und wer 400 Polygone zeichnen lässt, bekommt eine
  Diashow. Der Wert ist eine Einstellung und gehört auf echter Hardware
  gemessen.

### Architekturregel 2 — Ein generierter Mood wird immer validiert

Ein Mood geht direkt in den Renderer. Ohne Schranken bedeutet
`headbang_amp: 5000`, dass der Avatar das Display verlässt, und
`rate: 0.99` eine Partikelflut, die bei 15 FPS auf einem Pi Zero die
Framerate bricht.

Also: **Clamping pro Feld gegen eine kanonische Schema-Tabelle.**
Min/Max je Zahl, erlaubte Werte je Enum, RGB auf 0–255. Unbekannte Keys
werden verworfen, nicht durchgelassen. Ein Fallback-Mood greift, wenn
alles fehlschlägt.

**Dieselbe Tabelle erzeugt das Schema für den Agenten und den Validator.**
Zwei getrennte Listen driften auseinander, sobald jemand ein Feld
ergänzt. (Muster nachgebaut aus OpenMinis' `ToolPreflight`, wo genau das
dokumentiert ist.)

---

### 3.4 Umgebungshören im Ruhezustand

Chimera reagiert nicht nur auf Ansprache. **Wenn niemand mit ihm redet,
hört es dem Raum zu** — damit es etwas tut, wenn der Raum lebt.

Das ist ausdrücklich **nicht** Noisys Modell. Noisy bildet Geräusche fest
auf Moods ab: `labels` im Mood-Dict, Label rein, Mood raus. Chimera behält
die **Erkennung** und wirft die **Zuordnung** weg — welcher Ausdruck zu
einem Geräusch passt, entscheidet das Sprachmodell, situationsabhängig.

Derselbe Hundebellen-Reiz kann morgens „aufmerksam" bedeuten und nachts um
drei „erschrocken". Eine Tabelle kann das nicht, ein Modell mit Kontext
schon.

#### Architekturregel 3a — Das Modell wird nicht pro Geräusch gefragt

Der naive Bau wäre: Geräusch erkannt → Anfrage ans Sprachmodell → Mood.
Das scheitert dreifach: an der Latenz (das Modell liegt außerhalb, Regel
5), an den Kosten (Dauerbetrieb) und am Netzausfall.

Stattdessen **drei Geschwindigkeiten**:

| Ebene | Reaktionszeit | braucht Modell |
|---|---|---|
| Sofortreaktion | unter 1 s | nein |
| Stimmungslage | Sekunden | nein |
| Deutung | Minuten | ja, asynchron |

1. **Sofortreaktion.** Ein plötzlicher Knall, ein Lachen — dafür gibt es
   eine kleine, fest verdrahtete Menge von Reflexen. Noisys `fast_track`
   ist genau das. Ein Gerät, das erst in drei Sekunden zusammenzuckt, ist
   kaputt.
2. **Stimmungslage.** Aus dem, was über die letzten Minuten zu hören war,
   ergibt sich ein Grundzustand — ruhig, belebt, laut. Rein lokal
   gerechnet, ohne Modell, über Mischen und Variieren (Abschnitt „Drei Stufen der Erzeugung" Stufen 1–2).
3. **Deutung.** In größeren Abständen — oder wenn sich etwas deutlich
   ändert — bekommt das Sprachmodell eine **Zusammenfassung** der
   akustischen Lage und antwortet mit einem Mood: gemischt aus
   vorhandenen oder neu erfunden. Das Ergebnis wird gespeichert und gilt,
   bis die nächste Deutung kommt.

Das Modell wird also **pro Situation** befragt, nicht pro Geräusch. Eine
Anfrage alle paar Minuten ist bezahlbar; eine pro Geräusch wäre es nicht.

#### Architekturregel 3b — Nur im Ruhezustand wird zugehört

Umgebungshören läuft **nur, wenn gerade kein Gespräch stattfindet.**

Zwei Gründe, beide zwingend:

- **Rechenzeit.** Auf dem Pi Zero 2 W teilen sich Renderer, Wake-Word,
  Spracherkennung und Sprachsynthese vier schwache Kerne. Dauerndes
  Audio-Tagging nebenher kostet Bildrate.
- **Bedeutung.** Während eines Gesprächs ist das Wichtigste im Raum, was
  gesagt wird. Ein Gerät, das mitten im Satz auf ein vorbeifahrendes Auto
  reagiert, wirkt nicht lebendig, sondern unaufmerksam.

Der Übergang ist damit klar: Wake-Word oder Tastendruck beendet das
Zuhören, das Gespräch übernimmt; nach dessen Ende kehrt es zurück.

#### Der Tagger ist austauschbar

Entscheidend am Entwurf ist die **Funktion**: Der Tagger liefert Labels,
die Deutung macht das Sprachmodell (Ebene 3). Welches Modell die Labels
liefert, ist eine Einstellung — kein Architekturmerkmal.

Deshalb gilt hier dasselbe wie bei Anbietern und Boards: Das Modell steht
in der Konfiguration, nicht im Code. Sherpa-onnx spricht Zipformer und CED
unterschiedlich an, also kapselt eine dünne Schicht den Unterschied; alles
darüber sieht nur noch „Label mit Wert".

**Voreinstellung ist CED-tiny.** Auf dem Pi Zero 2 W gemessen
(int8, 2 Threads):

    Zipformer-small   22,1 M Parameter   26 MB   4,71 s   mAP 45,1
    CED-tiny           5,5 M Parameter  5,9 MB   0,83 s   mAP 48,1

Kleiner, rund fünfmal schneller und auf AudioSet sogar genauer. Bei einem
Gerät, das nebenher rendert und jederzeit ins Gespräch wechseln können
muss, entscheidet die Laufzeit — deshalb die Voreinstellung.

**Der Haken ist bekannt und beherrschbar:** CED liefert flachere
Wahrscheinlichkeiten — ein Lachen, das der Zipformer mit 93 % meldet,
kommt dort mit 38 % an. Jedes Modell bringt deshalb seinen eigenen
Schwellenfaktor mit (Noisy löst das bereits so). Für die Deutung durch
das Sprachmodell spielt es ohnehin kaum eine Rolle, weil dort die
Rangfolge der Labels zählt und nicht deren absoluter Wert.

Die Zahlen stammen aus Noisys Messungen auf echter Hardware. Ob sie unter
Chimeras Last — Renderer plus Wake-Word gleichzeitig — genauso ausfallen,
ist **zu messen, nicht anzunehmen** (Regel 10g). Fällt CED durch, wird ein
anderes Modell eingetragen; der Entwurf bleibt davon unberührt.

#### Was das Modell bekommt und zurückgibt

Hinein geht eine Lagebeschreibung, keine Rohdaten: erkannte Labels mit
Häufigkeit, Lautstärkeverlauf, Tageszeit, wie lange niemand gesprochen
hat, aktueller Mood. Heraus kommt entweder der Name eines vorhandenen
Moods, eine Mischanweisung oder ein neuer Mood-Datensatz — der dann
genauso validiert wird wie jeder andere (Regel 2).

**Bei Netzausfall bleibt Ebene 1 und 2.** Das Gerät behält ein Gesicht und
eine Stimmung, es verliert nur die Deutung. Das ist der Normalfall bei
einem Gerät, das an einem externen Modell hängt — und kein Fehlerzustand.

## 4. Sprache — vollständig offline

Ein Framework für alles: **sherpa-onnx**. Läuft auf Raspberry Pi, ohne
Netz, und deckt STT, TTS, VAD und Keyword-Spotting ab.

Kette:

    KWS ("Hey Chimera") → VAD → STT → Agent
      → Mood-Entscheidung → Renderer
      → TTS (Emotion aus Mood) → Lautsprecher

### Architekturregel 4a — VAD läuft vor STT, KWS vor VAD

Dauerhaft laufende Spracherkennung frisst die CPU, die der Renderer für
15 FPS braucht. Das Wake-Word hält den Ruhezustand billig, die
Sprachaktivitätserkennung begrenzt die Erkennung auf echte Äußerungen.

### 4.1 Mienenspiel beim Sprechen

Ziel ist, dass sich das Sprechen wie ein Gegenüber anfühlt und nicht wie
eine Ansage. Das Gesicht soll sich **während** der Antwort bewegen — nicht
einmal zu Beginn einen Ausdruck setzen und ihn dann halten.

Der naheliegende Weg wäre, das Sprachmodell die Animation steuern zu
lassen. Das geht schief, und zwar an der Physik: Das Modell liegt außerhalb
(Regel 5), eine Antwort braucht Hunderte Millisekunden bis Sekunden. Eine
Mundbewegung braucht Bilder alle 60 ms. Selbst bei einem Modell im
Nebenzimmer kommt die Anweisung zu spät für die Silbe, die sie meint.

### Architekturregel 4b — Gesicht und Stimme tragen denselben Mood

Die Mood-Entscheidung fällt **vor** der Sprachausgabe. Ein müder Avatar
mit munterer Stimme zerstört die Illusion sofort. Die deutsche Stimme
`thorsten_emotional` hat Emotionsvarianten — die werden an den Mood
gekoppelt, nicht fest gewählt.

Modelle (int8, deutsch):

| Aufgabe | Modell | Größe |
|---|---|---|
| VAD | `silero_vad_v5` | ~2 MB |
| KWS | `kws-zipformer-gigaspeech-3.3M-mobile` | 14 MB |
| STT | `nemo-fast-conformer-ctc-en-de-es-fr-14288-int8` | 98 MB |
| TTS | `vits-piper-de_DE-thorsten_emotional-medium-int8` | 22 MB |

#### Regel „Sprechgesicht“ — Sprechen hat einen eigenen Ausdruck mit Mundphasen (smilez, 1.11.)

Fund am Gerät: Der Zustand `spricht` zeigte `TALK`, und `TALK` ist in
Noisys Bibliothek ein Ausdruck für **Zuhören** (Ohr, gerader Mund, Blick zur
Seite). Das Gesicht sagte das Gegenteil des Zustands. Dazu wurde `wartet`
nie gemeldet, das Gesicht blieb nach der ersten Antwort stehen.

1. **`TALK` heißt `LISTEN`.** Der Ausdruck „jemand spricht, ich höre zu“
   (Ohr, Blick zur Seite) trägt den Namen `LISTEN` und gehört dem Zustand
   `hoert` (Hörmodus, Phase 5a). Der bisherige `LISTEN` (lächelnd, ohne
   Zubehör) war de facto das Ruhegesicht und heißt jetzt `IDLE`; so sucht
   `face.py` den Ruhezustand schon (`wartet` -> `IDLE`).
2. **`SPEAK` ist neu** und gehört dem Zustand `spricht`: kein Zubehör, Blick
   geradeaus, **Mund mit Phasen**.
3. **Mundphasen statt Mundform.** `mouth.style = "speak"` zeigt 2 bis 4
   Phasen, die im Kreis laufen (`zu`, `halb`, `offen`, `halb`). Jede Phase
   bleibt **`SPEAK_HALTE` Bilder** stehen (Vorgabe 3, wählbar 1 bis 10),
   damit der Mund nicht schneller klappt, als ein Auge folgt: bei 15 Bildern
   je Sekunde und Halten 3 wechselt der Mund 5-mal je Sekunde. Die Phase
   hängt am Bildzähler, nicht an der Uhrzeit, also bleibt sie stabil, wenn
   Bilder ausfallen.
4. **Ein Ausdruck, kein Ersatz für die Stimme.** Solange es keine
   Sprachausgabe gibt, läuft der Mund, solange der Zustand `spricht`
   gemeldet ist. Mit Sprachausgabe (Phase 5) folgt die Phase der Lautstärke
   (Regel 4c, „Mundform zur Lautstärke“); die Phasen bleiben dieselben.
5. **Jede Antwort endet mit `wartet`.** Wer `spricht` meldet, meldet danach
   `wartet`, auch bei Fehler (Regel 8a). Test mit Gegenprobe.

#### Architekturregel 4c — Das Sprachmodell setzt Absicht, nicht Bilder

Die Arbeitsteilung folgt derselben Staffelung wie beim Umgebungshören
(Abschnitt „Umgebungshören im Ruhezustand") — nur enger getaktet:

| Was | Wer | Takt |
|---|---|---|
| Mundform zur Lautstärke | Renderer, lokal | jedes Bild |
| Betonung, Pausen, Kopfbewegung | Renderer aus dem Sprachsignal | ~100 ms |
| Ausdruck des Satzes | Sprachmodell, im Voraus | pro Antwort |

Das Sprachmodell liefert **Regieanweisungen zum Text**, keine Einzelbilder.
Ein Satz kommt also nicht nackt, sondern mit einem Ausdruck versehen —
etwa „nachdenklich beginnen, bei der Pointe erfreut". Chimera kennt diese
Ausdrücke bereits als Moods (Abschnitt „Mood-Assets: das Kernkonzept"); es sind dieselben Datensätze, die auch
sonst das Gesicht bestimmen. Das Modell wählt oder mischt sie, so wie es
im Ruhezustand die Deutung liefert.

Die eigentliche Lebendigkeit entsteht **lokal**: Der Mund folgt der
Lautstärke der Sprachausgabe, der Kopf bewegt sich mit der Betonung, die
Augen blinzeln weiter. Dafür braucht es kein Modell, sondern das
Audiosignal, das ohnehin durch den Lautsprecher geht.

Das ist derselbe Mechanismus, den Noisy für Musik nutzt — dort folgt die
Figur dem Takt. Hier folgt sie der eigenen Stimme. Die Kopplung ist schon
erprobt, inklusive der Glättung (`AUDIO_SMOOTHING`, rund ein Drittel
Sekunde Nachlauf bei 15 Bildern je Sekunde).

#### Was das auf dem Pi Zero 2 W kostet

Die ehrliche Antwort: Das ist der Lastfall, der das Board am meisten
fordert — Sprachsynthese und Renderer laufen gleichzeitig, beide wollen
Rechenzeit, und der Renderer soll dabei nicht einbrechen.

Vier Kerne stehen zur Verfügung. Zugehört wird währenddessen nicht
(Regel 3b), die Spracherkennung schweigt also. Das Sprachmodell liegt
außerhalb und kostet nichts außer Wartezeit. Bleibt: Renderer plus
Sprachsynthese, plus die Auswertung des Audiosignals — letztere ist
billig, weil nur Lautstärke und grobe Betonung gebraucht werden, keine
Frequenzanalyse.

Trotzdem ist offen, ob 15 Bilder je Sekunde dabei halten. **Zu messen,
nicht anzunehmen** (Regel 10g). Falls nicht, in dieser Reihenfolge:

1. Bildrate **während des Sprechens** senken (10 statt 15) — beim
   Sprechen zählt die Mundbewegung, nicht die Partikelanimation
2. Aufwendige Ebenen (Partikel, mehrlagiger Schein) währenddessen
   aussetzen
3. Sprachausgabe in Stücken erzeugen und abspielen, damit die Synthese
   nicht in einem Block rechnet

Der Ausweg ist also vorhanden, ohne den Entwurf anzutasten. Das ist der
Grund, weshalb die Bildrate eine Einstellung ist und keine Konstante.

### Architekturregel 5 — Sprache lokal, Sprachmodell immer remote

Auf einem Pi Zero 2 W (512 MB) passen Sprache **und** LLM nicht
gleichzeitig in den Speicher:

    OS + Python ~120 · Renderer ~60 · STT ~150 · TTS ~60
    VAD+KWS ~25 · Agent+Telegram ~80  =  ~495 MB

Das Sprachmodell fehlt darin komplett — und passt auch mit Auslagerung
nicht hinein („Sprachmodelle: Provider-Schicht", Regel 5). Was Auslagerung sehr wohl leistet, ist der
Rest: Renderer, Spracherkennung und Sprachsynthese gleichzeitig
vorzuhalten, ohne dass der Speicher ausgeht. Dazu Regel 5e.

"Ohne API" ist deshalb so definiert: **kein Fremdanbieter, kein
Token-Konto, nichts verlässt das eigene Netz.** Ein LLM auf dem eigenen
Ollama-Server erfüllt das. Sprache bleibt in jedem Fall auf dem Gerät.

**Auch mehr Arbeitsspeicher ändert daran nichts.** Beim Radxa ZERO 3W war
die Hoffnung, mit 8 GB ein lokales Modell fahren zu können. Das scheitert
nicht am Speicher, sondern an der Rechenleistung:

- Der RK3566 hat vier Cortex-A55-Kerne bei 1,8 GHz. A55 ist ein
  Effizienzkern, kein Leistungskern — für Modellinferenz auf der CPU zu
  langsam, selbst bei kleinen Modellen.
- Die NPU hilft nicht: **Rockchips eigener LLM-Stack `rknn-llm`
  unterstützt RK3588, RK3576, RK3562 und RV1126B — den RK3566 nicht.**
  Es gibt also nicht einmal einen Weg, ein Modell auf diese NPU zu
  bringen, und sie wäre dafür auch zu schwach.

Damit ist die Sache entschieden und keine Frage des Boards mehr:
**Das Sprachmodell läuft immer außerhalb des Geräts.** Anthropic über die
Abo-Anmeldung, Ollama im eigenen Netz, weitere über LiteLLM.

Der Arbeitsspeicher des Radxa bleibt trotzdem wertvoll — er nimmt den
Druck von STT, TTS und Renderer, die sich auf dem Zero 2 W einen sehr
engen Rahmen teilen (Modellrotation, siehe `docs/HARDWARE.md`).

Was **lokal** bleibt, bleibt lokal: Spracherkennung, Sprachsynthese,
Sprachaktivitätserkennung und Wake-Word laufen auf beiden Boards ohne
Netz. Nur das Sprachmodell geht hinaus, und auch das nicht zwingend zu
einem Fremdanbieter.

Bemerkenswert: PiSugars eigene Whisplay-Referenzanwendung lässt Whisper,
Piper und Ollama per Docker auf einem separaten Rechner laufen. Der
Hersteller traut der Platine die Last selbst nicht zu.

---

## Sprachmodelle: Provider-Schicht

Chimera soll **mehrere Anbieter gleichzeitig** kennen: Anthropic per
Abo-Anmeldung, Ollama im eigenen Netz, dazu beliebige weitere über
LiteLLM. Keiner davon ist Pflicht.

### Ausgangslage aus openclawgotchi

Die Abstraktion ist da und taugt: `LLMConnector` mit `call()` und
`is_available()`, dazu `LLMError` / `RateLimitError`. Zwei
Implementierungen existieren (Claude-CLI, LiteLLM).

Der **Router** taugt nicht. Er kennt genau zwei Connectoren als feste
Attribute und schaltet mit einem Bool (`force_lite`) zwischen ihnen um.
Ein dritter Anbieter passt da nicht hinein, ohne die Klasse aufzubohren.

### Architekturregel 5a — Registry statt fester Connector-Attribute

Der Router hält eine **geordnete Liste** von Connectoren, nicht benannte
Felder. Ein Anbieter meldet sich mit Name, Priorität und
Verfügbarkeitsprüfung an. Auswahl geschieht über den Namen, nicht über
einen Schalter; Fallback läuft die Liste entlang.

Damit kostet ein neuer Anbieter eine Datei und einen Registry-Eintrag —
keine Änderung am Router.

`LLMConnector` wird um zwei Dinge erweitert:
- `supports_tools` — nicht jeder Anbieter kann Tool-Calls
- `context_window` — nötig für die gestaffelten Kontextschwellen (`docs/HERKUNFT.md`, Abschnitt „Gestaffelte Kontextschwellen").
  Die Kapazität muss gegen das Modell geprüft werden, das die Anfrage
  **tatsächlich bedient**. Bei Fallback über die Registry sonst gegen das
  falsche Fenster.
  **Der Wert kommt aus der Abfrage des Servers** (`op: modelle`/`status`),
  nicht aus einer Konstante im Connector (11.11.2026: `GatewayOllama` trug
  `32_000` fest — falsch, sobald das Modell ein anderes Fenster hat). Ein
  geratener Wert ist schlimmer als keiner: Er sieht wie eine Messung aus.

### Architekturregel 5b — Anthropic-Anmeldung wie im OpenMinis-PR

> Ausführung für das Gateway, Punkt für Punkt nach PR #407:
> „Gateway: der eine Weg nach draußen",
> „Architekturregel 5b, Fassung für das Gateway“.

Anthropic wird auf demselben Weg eingebunden wie in
[OpenMinis PR #407](https://github.com/OpenMinis/OpenMinis/pull/407) —
**dem eigenen Beitrag dort, der hier mit übernommen wird**:
über den **OAuth-Pfad der Abo-Anmeldung**, nicht nur über einen
API-Schlüssel. Das erlaubt die Nutzung eines bestehenden Abos, statt pro
Token zu zahlen — auf einem Gerät, das dauernd läuft, ist das der
Unterschied zwischen benutzbar und nicht benutzbar.

Der Kern dieses PRs ist eine Lehre, die hier direkt gilt:

> Anthropic sperrt neue Modelle hinter einer Mindestversion des
> CLI-Clients und prüft das über den User-Agent. Eine **fest verdrahtete
> Versionskennung veraltet** und quittiert mit
> `claude_code_version_too_old` — für ein neues Modell, das eigentlich
> verfügbar wäre.

Also: **Die Client-Kennung wird zur Laufzeit ermittelt, nie einkompiliert.**
Ermittlung aus der real installierten CLI, mit gepflegtem Rückfallwert
und Zwischenspeicher. Genau das tut `ClaudeCliVersion` im PR.

Für Chimera heißt das zusätzlich: Wo die CLI als Unterprozess läuft,
kommt sie über den Gerätestart hinweg nicht mit. Der ermittelte Wert
gehört gecacht und bei Prozessstart einmal aufgefrischt — nicht bei jedem
Aufruf, das kostet auf einem Zero spürbar.

### Vorarbeit im eigenen Fork von openclawgotchi

Im Fork `Smilez1985/openclawgotchi`, Branch `feat/model-ollama-switcher`,
ist Ollama bereits angebunden. Fünf Commits, die inhaltlich übernommen
werden:

- `LLM_PRESETS`-Eintrag `ollama` mit `ollama_chat/<modell>` und
  `OLLAMA_API_BASE`
- `/model`-Befehl im Chat: Modelle zur Laufzeit auflisten und umschalten,
  ohne SSH
- **Auswahl bleibt über Neustarts erhalten** (`active_model.json`), mit
  Vorrang vor dem Voreinstellungs-Preset
- Platzhalter-Hostname wird als „nicht gesetzt" behandelt und mit einem
  klaren Hinweis gemeldet, statt in einen Verbindungsfehler zu laufen
- Der Installer fragt die echte Ollama-Adresse ab

Die Muster sind gut und werden übernommen — insbesondere die persistente
Modellwahl und die Behandlung des Platzhalters. **Der Code selbst wird
nicht übertragen**, weil er auf dem alten Zwei-Connector-Router aufsitzt
(`set_model()` auf dem LiteLLM-Connector). In der Registry ist Ollama ein
eigener Connector, kein umgeschalteter LiteLLM (Regel 5c).

Zum Stand des Forks: Er liegt **41 Commits hinter dem Upstream** und 5
voraus. Das Upstream-Projekt ist in der Zwischenzeit deutlich
weitergegangen. Chimera setzt daher auf dem **aktuellen Upstream** auf und
baut die Fork-Ideen dort neu ein, statt den divergierten Fork
nachzuziehen. Ein Rebase über 41 Commits mit anschließendem Umbau auf die
Registry wäre mehr Arbeit als die Neuimplementierung.

### Architekturregel 5h — Kein Anbieter wird vorausgesetzt

Nicht jeder hat einen Rechner mit Ollama. Chimera läuft mit dem, was da
ist: Ollama wenn vorhanden, ein Abo wenn eingerichtet, ein API-Schlüssel
wenn sonst nichts.

Modelle werden **je Aufgabe** zugeordnet, nicht global — Gespräch,
Mood-Erfindung, Deutung der Umgebung, Zusammenfassen haben sehr
unterschiedliche Ansprüche. Jede Aufgabe zeigt auf eine **Gruppe** mit
geordneten Mitgliedern; fällt das erste aus, greift das nächste.

Damit löst sich die Ollama-Frage von selbst: Wer einen Server hat, trägt
ihn vorn ein und zahlt nichts. Wer keinen hat, lässt den Eintrag weg.
Dieselbe Konfiguration, ein Eintrag weniger.

Die Ersteinrichtung **sucht** (Ollama im Netz, gesetzte Schlüssel,
bestehende Anmeldung) und **schlägt vor** — sie entscheidet nicht.
Einzelheiten in `docs/PROVIDER.md`.

### Architekturregel 5c — Ollama ist ein erstklassiger Anbieter

Ollama läuft im eigenen Netz und ist damit der Anbieter, der Regel 5
erfüllt (nichts verlässt das Netz). Er wird **nicht** als Sonderfall von
LiteLLM behandelt, sondern als eigener Connector mit eigener
Verfügbarkeitsprüfung — sonst lässt sich nicht sauber unterscheiden, ob
der Server weg ist oder ein Schlüssel fehlt.

Die Zuordnung von Aufgabe zu Anbieter ist konfigurierbar. Sinnvolle
Voreinstellung:

| Aufgabe | Anbieter |
|---|---|
| Gespräch, Werkzeugnutzung | Anthropic (Abo), Fallback Ollama |
| Mood-Erfindung (Abschnitt „Drei Stufen der Erzeugung" Stufe 3) | Ollama — selten, günstig, im eigenen Netz |
| Zusammenfassen, Aufräumen | Ollama |

Mood-Erfindung auf dem eigenen Server zu belassen, ist bewusst: Der
Ausdruck des Geräts sollte nicht an einem bezahlten Kontingent hängen.

Da beide Anbieter außerhalb des Geräts liegen (Regel 5), muss Chimera mit
**Netzausfall** umgehen können, ohne stehenzubleiben: Die Mood-Stufen 1
und 2 (Mischen, Variieren) brauchen kein Modell und funktionieren weiter.
Das Gerät behält also ein Gesicht, auch wenn es gerade nichts sagen kann —
und kann diesen Zustand sogar zeigen (Abschnitt „Zustand sichtbar machen").

### Konfiguration

Alle Anbieter sind optional, alle über `.env` einzurichten, keiner
hartkodiert. Fehlt ein Schlüssel, meldet der Connector sich als nicht
verfügbar und die Registry überspringt ihn — kein Absturz, keine
Fehlermeldung beim Start.

Zugangsdaten gehören nicht ins Repo (Abschnitt „Hardware"). `*.example` mit Platzhaltern.

### Architekturregel 5d — Ein Gespräch, zwei Türen

Beide Wege führen in **denselben Agenten mit demselben Verlauf**. Wer
morgens per Telegram etwas bespricht und abends davorsteht und nachfragt,
redet mit demselben Gegenüber. Getrennte Sitzungen je Kanal wären ein
Fehler und würden das Gerät in zwei Persönlichkeiten spalten.

Praktisch: Die Kanäle unterscheiden sich nur in Ein- und Ausgabe
(Text gegen STT/TTS) und in der Ausgabelänge — gesprochene Antworten
müssen kürzer sein als geschriebene. Der Agent bekommt den Kanal als
Kontext mitgeteilt, damit er sich darauf einstellen kann.

Der Avatar zeigt in beiden Fällen denselben Zustand (Abschnitt „Zustand sichtbar machen"). Wenn per
Telegram eine Anfrage läuft, sieht man das dem Gesicht an.

#### Architekturregel 5i — Ein Kanal hat keinen eigenen Zustand

Der Bauplan zu 5d. Die Regel oben nennt das Ziel, diese sagt, wie man es
nicht wieder verliert.

Die **Sitzung** besitzt den Agenten und dessen Verlauf. Ein **Kanal**
beschreibt nur die Tür: Name, Betriebsart (gelesen oder gehört),
Ausgabelänge. Er hält keinen Verlauf, keine Einstellungen, keine Zähler.

Ein Befehl, der den Zustand ändert — „Gespräch von vorn" ist der
typische —, wirkt auf die **Sitzung**, nie auf einen einzelnen Kanal.
Sonst kommt die Spaltung durch die Hintertür zurück: Wer per Telegram
zurücksetzt und dann davorsteht, träfe auf ein Gegenüber, das die Hälfte
noch weiß.

Praktische Probe: Ein zweiter Kanal derselben Art darf sich nicht anders
verhalten als der erste. Wenn er es tut, hängt irgendwo Zustand am Kanal.

---

### Architekturregel 5s — Ein Kanal, eine Hauptsitzung, alles läuft über denselben Strom

Vorgabe smilez (30.10.): Telegram, Web-Oberfläche (und später Sprache)
sind **ein** Kanal. Jede Ein- und Ausgabe landet in der Hauptsitzung und
erscheint überall, ohne zusätzliche Modellkosten.

- **Ein Sitzungs-Socket.** Der Dienst bietet genau einen Socket an
  (`/run/chimera/sitzung.sock`, Besitzer `chimera`, Gruppe `chimera-tor`,
  660). Das Gateway ist dessen **einziger Client**; Telegram und
  Web-Oberfläche sind beide Türen *im Gateway* (5n) und sprechen über
  denselben Socket. Es gibt keinen zweiten Weg in die Sitzung.
- **Der Strom.** Jedes Ereignis der Hauptsitzung (Eingabe, Antwort, Fehler,
  Zustand wie „denkt“) bekommt eine laufende Nummer und wird an alle
  angemeldeten Türen verteilt. Wer sich anmeldet, nennt die letzte Nummer,
  die er kennt, und bekommt den Rest nachgeliefert.
- **Spiegeln kostet nichts.** Eine Nachricht aus Telegram erscheint in der
  Web-Oberfläche und umgekehrt als bloßes Ereignis; das Modell wird **einmal**
  gerufen, für die Eingabe selbst. Die Antwort geht an alle Türen, nicht nur
  an die, aus der gefragt wurde. Jedes Ereignis trägt die Tür, aus der es
  kam (`telegram`, `web`, …), damit man es erkennen kann (5i bleibt: die Tür
  hält keinen Zustand).
- **Adressiert wird „haupt“, nicht eine Sitzungs-ID.** Türen kennen nur den
  Namen `haupt`. Welche Sitzung dahinter liegt, entscheidet der Dienst.
  Schreibt jemand an eine andere (ältere) Sitzung, wird die Eingabe in die
  Hauptsitzung **umgeleitet** und der Absender erfährt es.
- **Wechsel bei Gewicht (8d), mit Bindung.** Beim Wechsel zeigt `haupt`
  atomar auf die neue Sitzung: Strom, Nummernzählung für die Türen,
  Telegram-Zuordnung und Anzeige hängen an `haupt`, nicht an der alten ID.
  Ein Turn, der gerade läuft, wird zu Ende geführt, dann wird gewechselt.
  Die alte Sitzung wird archiviert und ist danach **nur noch lesbar**
  (`nachlesen`, Chat-Modul „Ältere Sitzungen“). Schreiben darauf ist
  nicht möglich, es wird umgeleitet.
- **Die Klingel (Briefkasten, 5o) ist eine Tür wie die anderen.** Sie hängt
  immer an der Hauptsitzung, nie an einer Sitzungs-ID. Der Briefkasten
  meldet Post über den Sitzungs-Socket als `frage` mit `tuer: briefkasten`
  und `ref: <Briefnummer>`. Alle Ereignisse dieses Umlaufs tragen die `ref`;
  erst wenn `antwort` oder `fehler` mit dieser `ref` eintrifft, quittiert der
  Briefkasten (A5). Der Strom macht die Post in Telegram und Web sichtbar,
  ohne ein zweites Mal das Modell zu rufen. Läuft beim Sitzungswechsel gerade
  ein Briefturn, wird er zu Ende geführt; Post, die danach ankommt, geht in
  die neue Hauptsitzung. Wird ein Turn durch den Wechsel unterbrochen, bleibt
  die Post unquittiert und wird erneut in die neue Hauptsitzung zugestellt.
  Der Briefkasten bleibt bei seinem Verhalten nach 5p (Eingabe, kein Befehl).
- **Eine Gegenprobe gehört dazu:** Test, dass nach dem Wechsel eine Eingabe
  an die alte ID in der neuen Sitzung landet und die alte unverändert bleibt.

### Architekturregel 5e — zram und Auslagerungsdatei gehören zum Aufbau

Auf dem Pi Zero 2 W ist der Speicher der Engpass, nicht die Rechenleistung.
Der Installer richtet deshalb **immer** ein:

- **zram** mit 75 % des Arbeitsspeichers als komprimierter Auslagerungs-
  bereich im RAM. Kein Datenträgerzugriff, und bei den Daten, um die es
  geht (Python-Objekte, Modellpuffer, Bildpuffer), komprimiert das gut.
  Auf 512 MB entstehen so real nutzbare Reserven in dreistelliger
  Megabyte-Höhe.
- **Auslagerungsdatei auf dem Systemdatenträger**, gestaffelt nach der
  Größe des Systemdatenträgers: bis 8 GiB Karte 2 GiB, bis 16 GiB Karte
  4 GiB, bis 32 GiB Karte 8 GiB, darüber 16 GiB — als zweite Stufe unterhalb
  von zram. Sie liegt dort, wo das System liegt: auf dem Pi die SD-Karte,
  auf dem Radxa der eMMC. Damit läuft der Radxa ohne SD-Karte — und wo eine
  steckt, wird sie geschont. Für einen Agenten-Harness ist viel Auslagerung
  OOM-Schutz, kein Luxus (Entscheidung smilez, 11.10.2026): Auf der
  Chimera-Testbench (128 GiB Karte, 463 MiB RAM) sind das 16 GiB.

Das ist die bewährte Aufstellung aus den übrigen Projekten auf dieser
Hardware (Noisy, PiPortal) und keine Chimera-Erfindung. Ein früherer
Entwurfsstand lehnte Auslagerung auf SD-Karte pauschal ab — das war zu
grob. Richtig ist die Unterscheidung:

- **Ein Sprachmodell auszulagern ist sinnlos.** Es wird bei jedem Token
  vollständig durchlaufen; ausgelagert bedeutet das dauerndes Nachladen.
  Deshalb bleibt Regel 5 bestehen — das Modell liegt außerhalb.
- **Selten benutzte Seiten auszulagern ist genau richtig.** Der
  Telegram-Anteil, während gesprochen wird; das Sprachsynthese-Modell,
  während zugehört wird; Python-Bibliotheken nach dem Start. Diese Seiten
  werden minutenlang nicht angefasst — sie im Arbeitsspeicher zu halten
  ist die eigentliche Verschwendung.

Damit wird die befürchtete Modellrotation (STT und TTS nie gleichzeitig
geladen) voraussichtlich überflüssig: Der Kernel verdrängt die gerade
unbenutzte Seite von selbst, und zwar feiner, als es eine
Rotationsmechanik je könnte.

Zum Verschleiß der Karte: Er entsteht durch **Schreiben**, und die zweite
Stufe wird selten beschrieben, wenn zram davor liegt. Die
Auslagerungsneigung (`vm.swappiness`) wird trotzdem niedrig gehalten, und
das Protokoll hält fest, wie viel tatsächlich ausgelagert wurde — damit
Vermutung durch Messung ersetzt werden kann (Regel 10g). Welcher Wert
dafür richtig liegt, ist offen: „niedrig gehalten“ stammt aus der
Karte-schonen-Lesart, aber zram-Aufstellungen empfehlen eher hohe Werte,
weil zram im Arbeitsspeicher liegt und der Zugriff dort billig ist. Bis
zur Messung (10g) bleibt vm.swappiness unangetastet (Regel: nie raten).

**Auf dem Radxa ist beides nicht nötig und wird trotzdem eingerichtet.**
Ein Aufbau, der sich je nach Board unterscheidet, erzeugt zwei Systeme,
die sich unterschiedlich verhalten — und der Fehler zeigt sich dann
ausgerechnet auf dem Gerät, das seltener läuft.

**Idempotent, nach Zustand statt nach Marke.** Ein Lauf misst, was ist,
und ändert nur, was abweicht:

- **zram:** Mechanik über `zram-tools` (Paket, `paket` im Manifest mit
  `vorher_da|neu`), Konfiguration `/etc/default/zramswap`
  (`PERCENT=75`, `ALGO=lz4`, `PRIORITY=100`), Dienst `zramswap.service`.
  Gemessen wird das aktive Gerät (`/proc/swaps`, `disksize` in sysfs),
  nicht die Konfigurationsdatei. Liegt seine Größe bei 75 % von
  `MemTotal` (Toleranz eine Seite je Rundung), passiert nichts.
- **Auslagerungsdatei:** ein Viertel der Größe des Systemdatenträgers
  gemessen am Blockgerät in sysfs, nicht aus einer Tabelle). Existiert
  sie in der richtigen Größe und ist aktiv, passiert nichts. Passt die
  Sollgröße nicht auf den Datenträger (weniger freier Platz als nötig
  plus Reserve, 8 GiB wie in PiPortal), wird sie NICHT gekürzt — die
  bisherige Auslagerung bleibt, wie sie ist, und der Lauf meldet einen
  Befund.
  **Bewusste Ausnahme:** Beim Ersetzen schaltet DietPis Werkzeug
  `dietpi-set_swapfile` zuerst mit `swapoff -a` ALLE Auslagerung ab, auch
  zram, und baut sie dann wieder auf. Im Gegensatz zur ursprünglichen
  Forderung „keinen Moment ohne Auslagerung“ gibt es den Moment also
  kurz — nur bei einer Größenänderung, nicht bei jedem Lauf. Das Werkzeug
  zu ersetzen, um die Lücke zu schließen, wäre ein Nachbau von
  DietPi-Logik gegen den Erstbestand: nicht getan.
- **Vorhandene Einrichtungen werden nicht doppelt gebaut.** DietPi bringt
  eine eigene Auslagerung mit (`dietpi-set_swapfile`, Einträge in
  `/boot/dietpi.txt`). Der Installer BENUTZT DietPis Werkzeug statt es zu
  umgehen: Es pflegt fstab und `dietpi.txt` selbst, damit der Firstboot
  nichts zurückdreht, und der Rückbau stellt den Ausgangszustand mit
  demselben Werkzeug her. Der frühere Zustand steht im Manifest (Art
  `swapdatei`), die zram-Konfiguration als `sicherung`. Zwei
  Auslagerungsdateien nebeneinander wären zwei Systeme mit unklarem
  Verhalten; eine fremde zram-Verwaltung für `/dev/zram0`
  (systemd-zram-generator, rpi-swap) bricht den Schritt mit benannter
  Meldung ab — ihr Umstellen ist ein offenes Ende (ROADMAP).
- **Nachweis:** nach dem Lauf beide Einträge in `/proc/swaps` mit den
  Sollgrößen, zram mit höherer Priorität als die Datei. Ein zweiter Lauf
  ändert nichts (Test). Erst auf echter Hardware bestätigt:
  chimera-pi, 11.10.2026 — 16 GiB-Datei in 2,9 s angelegt, Rückbau stellte
  den Ausgangszustand byte-gleich her.

---

### Architekturregel 5f — Fremde Werkzeuge sind nicht vertrauenswürdig

Ein MCP-Server ist fremder Code mit eigenen Werkzeugen. Deshalb:

- **Dieselbe Vorprüfung** wie für eigene Werkzeuge (Abschnitt „Herkunft und Lizenzgrenzen"), kein Freifahrtschein
- **Dieselbe Schleifenerkennung** — ein fremdes Werkzeug kann genauso
  im Kreis laufen
- **Dieselbe Protokollierung** (Regel 10e)
- Werkzeuge werden **benannt nach Herkunft** (`server.werkzeug`), damit
  Namenskollisionen nicht stillschweigend das falsche Werkzeug aufrufen
- Ein Server, der nicht antwortet, wird **übersprungen**, nicht abgewartet
  — sonst hängt die Agent-Schleife an einem fremden Prozess

Anbindung über die Standardwege der Bibliothek (Unterprozess oder HTTP).
Auf einem Pi Zero ist jeder zusätzliche Dauerprozess Speicher — MCP-Server
werden deshalb **bei Bedarf gestartet**, nicht im Voraus.

Ausführung und Stand der Spezifikation: `docs/PROVIDER.md`, Abschnitt „MCP".

---

### Architekturregel 5g — Audio läuft getrennt, aber schlank

Sprachein- und -ausgabe bekommen einen **eigenen Prozess**, nicht nur
einen Faden. Drei Gründe:

1. **Der Renderer darf nicht warten.** Python hat eine globale Sperre;
   ein Faden, der in der Spracherkennung rechnet, hält den Renderer auf.
   Bei 15 Bildern je Sekunde sieht man das sofort.
2. **Abstürze bleiben lokal.** Audio-Bibliotheken auf ARM sind nicht
   immer stabil. Ein Absturz darf das Gesicht nicht mitnehmen.
3. **Speicher lässt sich freigeben.** Ein eigener Prozess kann beendet
   werden, wenn längere Zeit nicht gesprochen wird — bei 512 MB zählt das.

**Schlank heißt:** Der Prozess macht Aufnahme, Erkennung, Synthese und
Wiedergabe — sonst nichts. Kein Agent, keine Werkzeuge, kein Netz außer
dem, was die Modelle brauchen (und die laufen lokal).

Verständigung über **geteiltes Gedächtnis** für den Pegel (der Renderer
liest ihn bei jedem Bild, Abschnitt „Mienenspiel beim Sprechen") und eine Warteschlange für alles andere.
Genau dafür hat Noisy `noisy_shm.py` gebaut, samt dem dokumentierten
Kniff um den `resource_tracker` — diese Erfahrung wird übernommen.

    Hauptprozess                  Audio-Prozess
    ├─ Agent                      ├─ Aufnahme
    ├─ Renderer  ◄── Pegel ────── ├─ VAD, Wake-Word
    ├─ Telegram      (SHM)        ├─ Erkennung
    └─ Anzeige   ──── Text ─────► └─ Synthese, Wiedergabe
                     (Queue)

**Ergänzung (11.10.2026) — Welches Mikrofon, wird gemessen.** Der
Audio-Prozess nimmt über das ALSA-Gerät `chimera_mikro` auf, nicht über
einen festen Kanal. Welche Mikrofone dahinter stehen, entscheidet der
Installer (Modul 46) **durch Messung am Gerät**: Testtöne über den eigenen
Lautsprecher, je Kanal Pegel und Klirren, Ergebnis `beide`, `links`,
`rechts` oder `keins`. Anlass war das linke Mikro am chimera-pi, das klirrt.
„Nur rechts“ fest einzubauen hätte den Defekt eines Boards jedem
aufgezwungen, der das Repo zieht. Grundsatz: Eine Eigenart der eigenen
Hardware wird gemessen und belegt, nie als Einstellung für alle
festgeschrieben. Im Zweifel bleiben beide Mikrofone an, mit Warnung. Ein
fälschlich abgeschaltetes gutes Mikrofon fiele niemandem auf.

---

## Schnittstellen zum Nutzer

Chimera hat **zwei gleichwertige Wege** hinein, nicht einen mit Anhängsel:

| Weg | Nutzung |
|---|---|
| **Telegram** | Von unterwegs, lange Texte, Dateien, Verlauf |
| **Sprache am Gerät** | Vor Ort, beiläufig, freihändig |

Telegram bleibt aus openclawgotchi **vollständig erhalten** — es ist die
einzige Schnittstelle, die auch funktioniert, wenn man nicht im selben
Raum steht.

### Architekturregel 5j — Eine Tür von außen ohne Positivliste startet nicht

Jede Bedienschnittstelle, die von außerhalb des Geräts erreichbar ist
(Telegram heute, weitere später), braucht eine Liste erlaubter Absender.
**Ohne Liste startet sie nicht** — kein Vorgabewert, kein „offen, wenn
leer", keine Warnung, die man überlesen kann.

Begründung: Hinter der Tür steht ein Agent mit Dateizugriff und
Shell-Werkzeug. Eine Bot-Adresse steht früher oder später in irgendeinem
Verlauf. Wer sie kennt, hätte damit das Gerät — und zwar mit allem, was
der Agent darf.

Das ist bewusst strenger als Regel 10k, wo Unkenntnis nur warnt: Dort
trägt der Nutzer das Risiko für sein eigenes Gerät, hier öffnet er es
Dritten. Wo eine Fehlkonfiguration Fremden Zugang gibt, wird nicht
gefragt, sondern verweigert.

Die Liste steht in der Umgebung, nicht im Repo (Abschnitt „Keine Secrets im Repo").

Für die Web-Oberfläche gilt die Ausnahme „Ersteinrichtung“ in Regel 5u.

## Gateway: der eine Weg nach draußen

Entschieden am 16.10.2026. Ersetzt den Ansatz, dass jeder Anbieter und
Telegram im Dienst selbst eine Verbindung öffnen. Vorbild ist der
Pförtner aus rag4ll (dort Abschnitt 27): ein Eingang, geprüft am Tor, intern
weitergereicht. Ausführung der Anbieterseite in `docs/PROVIDER.md`.

### Architekturregel 5n — Chimera spricht nur über sein Gateway mit der Welt

Auf dem Gerät gibt es **genau einen Prozess mit Netzzugang: das Gateway**.
Es ist Pförtner und Orchestrator zugleich, nach dem Vorbild von rag4ll (dort Abschnitt 27).

    Welt ── Telegram, Ollama, Anthropic, Web-Oberfläche, MCP, Update
              │
         ┌────▼─────────────────────────────┐
         │ Gateway  (Nutzer chimera-tor)    │  liest .env, hält die Schlüssel
         │  · Anbieter-Ketten, Rückfall     │  Netzsuche, Zeitgrenzen
         │  · Telegram ein/aus              │  Positivliste (5j)
         │  · Web-Oberfläche                │  Passwort (5m)
         └────┬─────────────────────────────┘
              │ Unix-Socket /run/chimera/tor.sock
         ┌────▼─────────────────────────────┐
         │ Dienst (Nutzer chimera)          │  Agent, Werkzeuge, Anzeige, Ton
         │  IPAddressDeny=any               │  kein Netz, keine Schlüssel
         └──────────────────────────────────┘

**Was das Gateway tut:**
- **Ausgehend:** Der Dienst schickt „Aufgabe X, Verlauf, Werkzeuge“. Das
  Gateway wählt anhand der Kette den Anbieter, ruft ihn auf, fällt bei
  Bedarf auf den nächsten zurück und liefert die Antwort samt Herkunft
  (`Reply.access`, `Reply.cost`). Die Registry (5a), die Ketten (5h) und
  die Zeitgrenzen wandern dorthin.
- **Eingehend:** Telegram und die Web-Oberfläche kommen am Gateway an.
  Es prüft die Positivliste bzw. das Passwort und reicht die Anfrage über
  den Socket an den Dienst weiter. Dort bleibt es bei **einer** Sitzung
  (5d/5i).
- **Netzsuche** (5k) und **Selbstübernahme** der Adresse laufen im
  Gateway.

**Was der Dienst nicht mehr kann, und zwar durch den Kernel, nicht durch
eine Absprache:** Verbindungen ins Netz aufbauen (`IPAddressDeny=any`,
nur localhost erlaubt) und Schlüssel lesen (`.env` gehört nicht seiner
Gruppe). Ein Agent, der über ein Werkzeug Unsinn macht, kann weder
Schlüssel abziehen noch selbst ins Netz. Er kann nur das Gateway bitten,
und das Gateway führt nur Anbieteraufrufe aus, keine beliebigen URLs.

**Verschärfung (Vorgabe smilez, 10.11.2026):** „Alles, was Chimera mitbringt
und tut und Netz braucht, geht ausschließlich über das Gateway“ — und der
Agent bekommt Netz nur, „wenn die Security Gates den Zugriff durchwinken“.

1. **Ausschließlich heißt: kein zweiter Weg.** Ist das Gateway nicht
   erreichbar, gibt es kein Netz — keinen Rückfall auf einen direkten Aufruf
   aus dem Dienst. `provider/` und `bot/telegram.py` **bleiben** (smilez,
   10.11.: sie werden benötigt), gehen aber selbst durch das Gateway: Ihr
   Transport ist der Socket, nicht `urllib`. Weg fallen der Rückfall in
   `provider/setup.py` („Ohne Gateway bleibt der direkte Weg“), die eigenen
   Aufrufe in `provider/anthropic.py`, `provider/ollama.py` und
   `bot/telegram.py` und die Netzsuche `discover()`.
2. **Die Sperre setzt der Kernel, nicht der Code:** `IPAddressDeny=any` in
   der Unit des Dienstes. Solange sie fehlt, ist Punkt 1 eine Absprache.
3. **Schlüssel kommen nicht in den Dienst — und Dateirechte genügen dafür
   nicht.** systemd liest `EnvironmentFile=` als root und gibt die Werte an
   den Prozess; eine für den Dienst unlesbare `.env` steht trotzdem in
   seiner Umgebung. Die Unit des Dienstes lädt die `.env` deshalb nicht.
   Was er an Einstellungen braucht, bekommt er aus einer eigenen Datei ohne
   Geheimnisse.
4. **Tore am Gateway: feste Regeln, kein Modell** (wie in der Regel „Wer
   prüft, führt aus“). Ein Aufruf geht nur hinaus, wenn jedes Tor ihn
   durchlässt; sonst bekommt der Dienst eine Ablehnung mit Grund. Alle Tore
   liegen am Gateway; die Liste steht unter „Die Tore“.
5. **Der Ausführer hat nie Netz.** `Limits.allow_network` entfällt, Programme
   der Liste `NETWORK` (`curl`, `wget`, `git`, `ssh` …) werden immer
   abgelehnt. Braucht ein Werkzeug Netz, ist es ein Werkzeug des Gateways
   (Regel 5r).

   **Am 13.11. im Ausführer selbst gemessen** (chimera-pi): ein Befehl, den
   der Ausführer über seinen Socket ausführt, bekommt gegen `1.1.1.1:443`
   und gegen `127.0.0.1:22` je `TimeoutError: timed out`; derselbe Aufruf
   außerhalb der Unit verbindet. Auch ein root-Prozess, per `cgroup.procs`
   in das cgroup der Unit geschoben, wird abgewiesen — der Riegel ist die
   Unit, nicht der Nutzer. Der einzige Weg ins Netz bleibt der Deskriptor,
   den das Gateway reicht. `PrivateTmp=yes` trennt zusätzlich `/tmp`.

**Vorrang bei Widerspruch (10.11.2026).** An drei Stellen sagt dieses
Dokument noch, der Agent lese die `.env`: im Pfadschema der Regel 10r
(`config/ root:chimera 750, .env 640`), in Regel 5t („der Agent liest dort
die `.env`“) und im Installer, der genau das einrichtet. Regel 5l sagt das
Gegenteil (`root:chimera-tor`, der Agent kann sie nicht lesen). Es gilt 5l
zusammen mit dieser Verschärfung; die drei Stellen werden mit dem Bau der
Sperre angeglichen.

**Die Tore** — alle am Gateway (smilez, 10.11.2026):

| Tor | Stand |
|---|---|
| Bekannter Auftrag, bekannter und eingeschalteter Anbieter | gebaut (`dienst.rs`) |
| Schwärzung vor der Cloud | nicht gebaut |
| Positivliste der Ziele für `web_abruf` | gebaut: `positiv` im Freigabe-Zustand, geprüft in `abruf::durchgang` (Regel 5r, Stufe 2 der Freigaben) |
| Rückfrage beim Nutzer | nicht gebaut; Weg wie in Regel 10s (Telegram-Knopf oder Web), wann sie auslöst, ist festzulegen |

**Schwärzung vor der Cloud (Entwurf).** Gilt für Cloud-Anbieter, nicht für
Ollama im eigenen Netz. Ersetzt wird, was ein festes Muster hat (private
Adressen, MAC-Adressen, Mailadressen, Schlüssel und Token, Pfade mit
Nutzernamen), dazu eine vom Nutzer gepflegte Liste (Namen, Firmen,
Hostnamen) — erraten wird nichts. Derselbe Wert bekommt in einer Sitzung
denselben Platzhalter; die Antwort wird vor der Rückgabe zurückübersetzt,
auch in Werkzeugaufrufen und über die Stückgrenzen eines Stroms hinweg. Das
ist Pseudonymisierung, keine Anonymisierung: Sie verringert, was die Cloud
sieht, und ersetzt keine Auftragsverarbeitung.

**Gemessen am chimera-pi (10.11.2026)** — der Stand, gegen den gebaut wird:

| Messung | Ergebnis |
|---|---|
| `chimera.service`: `IPAddressDeny`, `IPAddressAllow` | beide leer |
| Prozess unter dem Nutzer `chimera`, ohne Sperre | erreicht das Internet (`1.1.1.1:443`) und einen Rechner im LAN |
| derselbe Prozess mit `IPAddressDeny=any`, `IPAddressAllow=localhost` | Internet und LAN zu (Zeitüberschreitung); `127.0.0.1:8080`, die Web-Oberfläche des Gateways, bleibt offen |
| laufender Dienst, offene TCP/UDP-Sockets | keine, nur Unix-Sockets |
| Umgebung des Dienstes | enthält `ANTHROPIC_API_KEY`, `ANTHROPIC_OAUTH_TOKEN`, `CHIMERA_TELEGRAM_TOKEN`, `CHIMERA_WEB_PASSWORT_HASH` (aus `EnvironmentFile=`); die drei Zugänge sind auf diesem Gerät leer |
| Was dort über den direkten Weg läuft (Startprotokoll) | nichts: Ollama geht über das Gateway, Claude und Telegram sind nicht eingerichtet |

Nachgemessen am 10.11. abends: Mit `IPAddressDeny=any` **ohne**
`IPAddressAllow=localhost` antwortet das Gateway dem Prozess über den
Unix-Socket weiter (`status` und die Modell-Liste des Ollama-Servers im
LAN); `127.0.0.1:8080` und das Internet sind zu. Die Freigabe für localhost
wird also nicht gebraucht.

**Bauplan, Stufe 1 — die Sperre (gebaut 11.11.2026).** Was unten steht,
ist umgesetzt; am Pi noch nicht eingespielt. Ein Punkt hat sich beim Bauen
geändert: Die `.env` darf Schritt 98 nicht anfassen — den Nutzer
`chimera-tor` gibt es erst in Schritt 99, ein `chown` dort wäre ein stiller
Fehlschlag. Sie gehört jetzt Schritt 99.

| Stelle | Heute | Wird |
|---|---|---|
| `installer/lib/service.sh`, Unit des Dienstes | `EnvironmentFile=$CHIMERA_CONFIG/.env`, keine Netzsperre | lädt die `.env` nicht; `IPAddressDeny=any` ohne Freigabe |
| `installer/lib/service.sh`, `service_bereiche` | `config/` `root:chimera 750`, `.env` `root:chimera 640` | `.env` `root:chimera-tor`, für den Agenten unlesbar (Regel 5l) |
| `installer/lib/gateway.sh`, `gateway_ablagen` | setzt `config/` auf 751, „Agent liest dort die .env“ | Kommentar und Rechte nach 5l |
| `provider/setup.py`, `build_registry` | ohne Gateway direkter Weg, `discover()` | ohne Gateway kein Anbieter, mit Grund gemeldet |
| `tests/test_gateway_provider.py` | prüft „ohne Gateway bleibt der direkte Weg“ | prüft das Gegenteil |
| `installer/tests/test-service.sh` | prüft „liest die .env“ | prüft, dass die Unit sie nicht lädt und die Sperre trägt; Gegenprobe in `counter-check-service.sh` |
| Bestehende Installation | `.env` gehört `root:chimera` | Übergang im Installer (Versionierung: ein Versionssprung bricht keine Installation) |

Kein neues Modul und kein neuer Schritt: Alles knüpft an Schritt 98
(Dienst) und Schritt 99 (Gateway) an. `provider/ollama.py`,
`provider/anthropic.py` und `bot/telegram.py` bleiben in Stufe 1
unverändert — ihr Umbau auf den Socket kommt mit den Claude-Zugängen im
Gateway. Bis dahin scheitert ein direkter Aufruf an der Sperre und wird als
„nicht verfügbar“ gemeldet.

**Was der Dienst aus der `.env` braucht, und woher es künftig kommt:**

| Name | Stand |
|---|---|
| `OLLAMA_MODEL` | **entfällt** (smilez, 11.11.): Das Modell wird aus der Liste gewählt, die der Server meldet — nicht aus einer Einstellung. Siehe „Das Modell kommt vom Server“. **Gebaut am 11.11.:** niemand liest den Namen mehr, `SERVICE_ENV_NAMEN` ist leer |
| `OLLAMA_API_BASE`, `OLLAMA_HOST` | nur der direkte Weg — entfällt |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_OAUTH_TOKEN` | Schlüssel — gehören dem Gateway |
| `CHIMERA_TELEGRAM_TOKEN`, `CHIMERA_TELEGRAM_ALLOWED` | Schlüssel — gehören dem Gateway; `__main__.py` fragt heute das Token ab, um die eigene Tür zu öffnen. Wie das künftig läuft, hängt an der offenen Telegram-Frage |
| `CHIMERA_ANZEIGE` | kommt aus `/run/chimera/anzeige.env`, nicht aus der `.env` — bleibt |

**Modellwahl nach dem Vorbild des Forks** (Hinweis smilez, 10.11.2026: der
eigene Fork von openclawgotchi; gelesen sind die Beschreibungen der PRs #5,
#15 und #16 und der Code des Zweigs `fix/ollama-placeholder-root-bug`, der
auf den beiden anderen aufbaut). Was der Fork tut:

- Die Wahl ist **gespeicherter Zustand auf dem Gerät**
  (`data/active_model.json`: Modell und Adresse), kein Wert der
  Konfiguration. Beim Start gilt sie vor der Voreinstellung;
  `OLLAMA_MODEL` bestimmt nur das Modell der Voreinstellung `ollama`.
  (**Überholt** durch „Das Modell kommt vom Server", smilez 11.11.)
- Die Adresse wird an **einer** Stelle aufgelöst: gespeicherte Wahl, dann
  laufende Verbindung, dann Umgebung. Anlass war ein Fehler: Eine zweite
  Stelle griff auf den Platzhalter zurück und überschrieb die gespeicherte
  echte Adresse.
- Angeboten werden die Modelle, die der Server mit `tools` meldet
  (`/api/tags`, `/api/show`), mit einem Rückfall auf alle.
- Der Platzhalter gilt als nicht gesetzt. Der Installer fragt beim ersten
  Lauf nach der Adresse und überspringt die Frage, wenn eine echte
  eingetragen ist.

| Fork | Chimera heute |
|---|---|
| Adresse auf dem Gerät gespeichert | gebaut: `config/anbieter/<id>.json` beim Gateway (Regel 5t) |
| Platzhalter gilt als nicht gesetzt | gebaut (`ollama.rs`) |
| `tools` gemessen | gebaut im Katalog. Die Auswahl im Dienst (`provider/setup.py`) nimmt aber das dem Namen nach größte Modell, und `op: chat` ohne Modell nimmt das erste der Liste — beide ohne Blick auf `tools` |
| Wahl gespeichert | `wahl.json` liegt (5h); `/model` schreibt hinein, die Wahl gilt vor der Serverreihenfolge |
| Installer fragt nach der Adresse | nicht gebaut (Modul 95 ist geplant); das Gateway findet den Server über die Netzsuche (Regel 5k) |
| `/model` in Telegram | gebaut 12.11. (`telegram.rs`): Liste mit Markierung, `/model <nr\|name>` schreibt `wahl.json` |

**Das Modell kommt vom Server** (smilez, 11.11.2026): *„ollama_modell muss
aus der modell-liste die vom server abgerufen wird gepickt werden. ohne
modell keine antwort."* Also:

1. **Keine Einstellung als Quelle.** `OLLAMA_MODEL` verschwindet; die Liste
   holt das Gateway ohnehin (`/api/tags` je Anbieter, Katalog nach Regel 5t).
2. **Gewählt wird aus dieser Liste**, nach dem, was der Katalog gemessen hat
   (`tools` aus `/api/show`) — nicht nach der Zahl im Modellnamen, wie es
   `provider/setup.py` heute tut (`_size_of`).
3. **Ohne Modell keine Antwort.** Meldet der Server keines (oder keines mit
   `tools`), ist das ein benannter Fehler (`kein_modell`), kein stilles
   Ausweichen auf irgendeinen Namen. Der Dienst sagt es im Protokoll.

Offen dabei: die **Reihenfolge** mehrerer tauglicher Modelle. Bis
`wahl.json` gebaut ist (Regel 5t), gilt die Liste des Servers in ihrer
Reihenfolge; danach entscheidet der Nutzer.

**Gebaut am 11.11.2026** (`ollama::modell_waehlen` — ein Ort für die Regel):

1. Ein **genanntes** Modell gilt. Wer eines nennt, bekommt es — auch ohne
   `tools` im Katalog. Die Auswahl ist nur der Fall „kein Modell im Auftrag".
2. Sonst das **erste Modell in der Reihenfolge des Servers**, das der Katalog
   mit `tools: true` gemessen hat.
3. Sonst **kein Modell**: `kein_modell` mit Klartext-Grund — „der Server hat
   kein Modell", „keines kann Werkzeuge" oder „nicht gemessen (Katalog leer)".
   Es wird nichts geschickt.
4. **Lesart notes, zu bestätigen:** `tools: null` ist keine Messung und zählt
   nicht als „kann keine Werkzeuge" (5t). Ist für **kein** Modell etwas
   gemessen, misst das Gateway einmal selbst (`KATALOG_BUDGET_SOFORT`, 12 s)
   und entscheidet dann neu — sonst bliebe ein Anbieter, den die Netzsuche
   nicht auffrischt (`auto: false`), dauerhaft ohne Antwort.

`op: modelle` nennt dieselbe Wahl als `wahl` (und `wahl_grund`); der Dienst
baut die Regel nicht nach, sondern übernimmt den Namen für das Kontextfenster
(5a). `provider/setup.py` nimmt die Wahl statt der Zahl im Modellnamen.

**Der Katalog gehört zur Adresse, nicht zum Namen:** Die Netzsuche vergibt
eigene Ids (`ollama-<host>`), während der Dienst denselben Server als
`ollama` über die Adresse aus der `.env` fragt. Am Gerät gemessen (11.11.)
lag der Katalog unter der gefundenen Id und die Wahl sah einen leeren.
`dienst::katalog_fuer` sucht deshalb zuerst unter der Id, dann unter der
gleichen Adresse — eine Stelle, kein zweiter Weg.

**Folge für die Sperre** (Lesart notes, zu bestätigen): Die Wahl gehört
dorthin, wo die Adresse liegt — ans Gateway. Der Dienst braucht
`OLLAMA_MODEL` nicht aus der `.env`: Nennt er kein Modell, entscheidet
das Gateway an einer Stelle. **Gebaut 11.11. so:** gespeicherter Katalog →
erstes Modell mit gemessenem `tools` → sonst `kein_modell`; die
„gespeicherte Wahl" (`wahl.json`, 5t) und `OLLAMA_MODEL` aus seiner eigenen
Umgebung sind **nicht** gebaut und werden nicht nachgeholt. Eine
Abweichung vom Fork ist schon entschieden (Regel 5l): Die Adresse wird
nicht im Chat gesetzt.

**Entschieden (smilez, 10.11.2026):**

- **`provider/` und `bot/telegram.py` bleiben** — siehe Punkt 1.
- **Alle Tore liegen am Gateway** — siehe „Die Tore“.
- **Reihenfolge nach Wichtigkeit** — die Einstufung steht in der ROADMAP
  (Phase 4d, „Sperre fuer den Agent-Dienst“) und ist genehmigt (10.11.).

**Der Installer hat eigene Regeln** (Regel „Installerhelfer“, Regel 13,
Regel 10r): Er läuft als root, abgekoppelt als `chimera-installhelper`, nie
in der aufrufenden Sitzung, und lädt direkt (apt, pip, git, das
Rust-Binary) — er richtet das Gateway erst ein. Im Code nachgesehen
(10.11.): `chimera-install` lehnt einen echten Lauf ohne root ab,
`helfer_starten` ruft `systemd-run` ohne `User=` auf.

**Offen:**

- **Telegram.** Das Gateway holt heute schon selbst ab (`telegram.rs`:
  Abholen, Positivliste, Weitergabe an die Sitzung); `bot/telegram.py` holt
  ebenfalls selbst ab (`getUpdates` über `urllib`). Was `bot/telegram.py`
  behält, wenn das Netz beim Gateway liegt, ist festzulegen — zwei Abholer
  je Token schließt Telegram aus (409).
- **`IPAddressAllow=localhost`.** Der Socket zum Gateway ist ein
  Unix-Socket. Im Quelltext des Dienstes steht TCP auf localhost nur in der
  Ollama-Suche (`discover()`), die wegfällt; mit der Freigabe erreichte der
  Dienst die Web-Oberfläche. Vorschlag: keine Freigabe, am Gerät belegen.
- **Updates im Betrieb.** Das Bild oben führt „Update“ unter dem, was über
  das Gateway läuft; der Installer lädt direkt. Ob die Selbstaktualisierung
  (ROADMAP Phase 8f) durch das Gateway soll, ist nicht entschieden.

**Steuerkanal:** Die CLI (`chimera -f`, `chimera status`) ist ein Client
desselben Sockets. Sie öffnet nie selbst eine Anzeige (Anlass: der
Display-Vorfall vom 16.10.). Läuft der Dienst nicht, sagt sie das.
Regel 7 (ein Prozess, ein Framebuffer) wird damit durchsetzbar.

**Ausfall des Gateways:** Der Dienst läuft weiter. Gesicht und
Mood-Stufen 1 und 2 brauchen kein Netz (5c). In der Statuszeile steht
`anbieter_weg` mit dem Grund „Gateway nicht erreichbar“. systemd startet
das Gateway neu; der Dienst hängt **nicht** per `Requires=` daran, damit
ein abstürzendes Gateway nicht das Gesicht mitnimmt.

**Socket-Aktivierung (Gerüst, Phase 4d Schritt 2):** systemd hält
`/run/chimera/tor.sock` (`chimera-tor.socket`, Besitzer `chimera-tor`,
Gruppe `chimera`, 0660) und startet das Gateway beim ersten Aufruf. Ein
abgestürztes Gateway lässt den Aufrufer warten, statt ihn abzuweisen. Die
Sperre `IPAddressDeny=any` für den Agent-Dienst kommt erst, wenn die
Anbieter im Gateway laufen (ROADMAP); gemessen ist, dass ein Prozess mit
diesem Profil den Socket erreicht, das LAN aber nicht (`connect_ex` 11
gegen 0 ohne Sperre).

**Anbieter im Gateway (Stand: Ollama):** Der Dienst schickt
`{"op":"chat","anbieter":"ollama","modell","system","verlauf","prompt"}` und
bekommt `{"ok":true,"text","modell","host","verbrauch"}` oder
`{"ok":false,"fehler":{"code","text"}}`. Fehlercodes: `nicht_eingerichtet`,
`nicht_erreichbar`, `ausgelastet` (für den Dienst „nicht verfügbar“, die
Kette fällt zurück), `anbieter_fehler`, `leer`, `anbieter_unbekannt`. Die
Adresse kommt aus der `.env` über `EnvironmentFile=` der Unit (systemd
liest sie als root); der Dienst sieht nur den Host in der Antwort.
Gemessen am Pi: 696 kB RSS, Chat mit einem 27B-Modell über das Gateway,
und unter `IPAddressDeny=any` erreicht der Dienst Ollama nur noch über den
Socket.

**Speicher: Obergrenze 10 MB RSS, in Rust (Regel 14).** In Python geht
das nicht: Allein die Importe (`urllib.request`, `ssl`, `http.server`)
kosten am Pi 21,8 MB, bevor eine Zeile Logik läuft. Eine Rust-Probe
mit HTTPS-Client (ureq + rustls), Webserver (tiny_http), JSON und
Unix-Socket in einem statischen Binary läuft am Pi mit **1,6–1,7 MB RSS**
(Binary 1,6 MB). Die Grenze wird in der Unit mit `MemoryMax=` gesetzt und
im Test am Gerät nachgemessen (10q).

**Bewusst nicht im Gateway:** Selbstaktualisierung und
Paketinstallationen (smilez). Sie laufen als root im Installer,
außerhalb des Betriebs. 5n regelt den **laufenden** Betrieb.

**Bewusst nicht im Gateway:** Audio und Anzeige. Die sind lokal und
brauchen kein Netz.

**LAN und Internet werden unterschieden** (smilez, 11.11.2026). Alles, was
Chimera tut und Netz braucht, geht über das Gateway — auch das Display und
das Sprachmodell („von lokal, aus dem lokalen Netz über Ollama oder online
über die API"). Damit das nicht alles gleichberechtigt ist, ordnet das
Gateway **jedes ausgehende Ziel** ein:

1. **Geprüft wird die aufgelöste Adresse, nicht der Name.** Sonst zeigt ein
   öffentlicher Name auf `192.168.x` und die Einordnung ist wertlos.
2. **Bei jedem Sprung neu**, auch nach einer Umleitung (3xx): einmal geprüft
   und dann blind weiter ist genau der Fehler, den die Einordnung verhindern
   soll.
3. **Lokal und LAN ohne Rückfrage:** loopback, RFC 1918, link-local, IPv6-ULA
   — dafür gibt es `ip_im_lan` (`web.rs`), heute nur für eingehende
   Web-Anfragen benutzt (`nur_lan`), künftig auch ausgehend. Kein zweites
   Verfahren, eine Funktion für beide Richtungen.
4. **Internet nur für eingetragene Anbieter** (die Positivliste aus 5t) —
   und eine Adresse, die zum ersten Mal erscheint, wird **einmal
   zurückgefragt** (smilez, 11.11.). Antwortet niemand, gilt sie als nicht
   erlaubt; die Rückfrage läuft über die Web-Oberfläche oder das Gespräch,
   nicht über ein Gerät, das gerade niemand ansieht.
5. **Ohne Einordnung kein Verbindungsaufbau.** Was sich nicht zuordnen lässt
   (kein DNS, keine Adresse), fällt nicht durch, sondern wird abgelehnt.

Damit bleibt die Regel „Netz ausschließlich über das Gateway" unverändert
wahr — das Gateway entscheidet nur zusätzlich, **wohin**.

### Architekturregel 5k — Ollama wird im Netz gesucht, nie auf dem Gerät betrieben

Chimera installiert und startet **nie** ein eigenes Ollama.

1. Gesucht wird im **eigenen Subnetz** der aktiven Schnittstelle, mit
   dem Präfix der Schnittstelle. Netze größer als /22 werden nicht
   abgesucht, dann heißt es: „Netz zu groß, Adresse bitte auf der
   Web-Oberfläche eintragen.“
2. Erste Stufe: TCP 11434, parallel, 0,3 s je Adresse.
3. Zweite Stufe: Nur wer auf `/api/tags` gültiges JSON mit `models`
   liefert, gilt als Ollama.
4. Zu jedem Fund gehören die Modellliste und die Fähigkeiten aus
   `/api/show` (`tools`, `vision`, `embedding`). Das ist der Baustein aus
   openclawgotchi.

**Gesucht wird:** im Installer (Schritt 50), auf Anforderung (Telegram
`/suche`, Web-Oberfläche) und wenn die eingetragene Adresse beim Start
oder nach Ausfällen nicht antwortet. `/suche` ist **gebaut** (12.11.):
schickt erst „ich suche…", führt dann `netzsuche::durchgang` aus und nennt
Funde, neu eingetragene Anbieter und aufgefrischte Kataloge; „nichts
gefunden" und „Suche ging nicht" sind zwei verschiedene Antworten
(`telegram::suche_text`, rein und geprüft). Es ist ein Befehl der Tür, kein
Auftrag an die Sitzung — „suche im netz nach …" bleibt ein Auftrag.

**Selbsteintrag (smilez, 1.11.): Jeder gefundene Ollama-Server trägt sich
selbst in die Anbieterliste ein.** Das Gateway sucht im Hintergrund (kurz
nach dem Start, danach alle 5 Minuten; `CHIMERA_NETZSUCHE=0` schaltet es
ab, `CHIMERA_NETZSUCHE_S` setzt den Abstand) und beim Aufruf aus der
Oberfläche.

- Ein neuer Fund wird als Anbieterdatei `config/anbieter/ollama-<host>.json`
  angelegt (Typ `ollama`, an, Marke `auto: true`, Bezeichnung „Ollama @ Host“).
  Danach wird sein Katalog gefüllt (Modelle, `tools`, Kontext).
- **Die Wahl (5h) ändert die Suche nie.** Ein Server in der Liste heißt
  noch nicht, dass Anfragen dorthin gehen: Prompts verlassen das Gerät erst,
  wenn der Nutzer ein Modell dieses Servers in die Reihenfolge aufnimmt.
  Das begrenzt, was ein fremder Server im LAN bewirken kann, der sich als
  Ollama ausgibt.
- Eine bekannte Adresse wird nicht doppelt angelegt. Entfernt der Nutzer
  einen selbst eingetragenen Server, steht seine Adresse in
  `config/anbieter/.abgelehnt.json`, und die Suche trägt ihn nicht wieder ein.
- Kataloge bekannter Server werden höchstens stündlich erneuert (7-Tage-Frist
  der Modelle nach 5t). Ein nicht erreichbarer Server behält seinen Katalog.
- Die Adresse steht nur auf dem Gerät in `config/anbieter/`, nie im Repo (Abschnitt „Keine Secrets im Repo").
- Bei Netzen über /22 wird nicht gesucht und das gemeldet.
- Die Adresse in der `.env` (`OLLAMA_API_BASE`) bleibt als Rückfall unter der
  Kennung `ollama`, bis der Nutzer auf die Anbieterliste umgestellt hat.
  Die frühere Selbstübernahme einer Adresse in die `.env` entfällt.

**Stand am Gerät (1.11.):** Die Regel gilt noch nicht durchgesetzt. Der
Dienst `chimera` hat `IPAddressDeny` und `IPAddressAllow` leer und ruft
Ollama und Anthropic im Python-Code selbst per `urllib` auf; `discover()`
scannt das Netz selbst. Der Weg über das Gateway ist ein zusätzlicher Pfad
und fällt bei Ausfall des Gateways auf den direkten zurück. Durchgesetzt ist
die Regel erst, wenn Anthropic im Gateway läuft und `IPAddressDeny=any` mit
Zugang nur zum Gateway-Socket gesetzt ist (ROADMAP, Phase 4d).

**Das Gateway fragt alles ab, was über einen Anbieter gewusst werden muss,**
damit „kommt etwas an?“ jederzeit beantwortbar ist, ohne am Server
nachzusehen: bei Ollama `/api/tags`, `/api/show` und `/api/ps` (geladen,
VRAM, Ablauf) sowie die Zeiten aus jeder Antwort (`load_duration`,
`total_duration`, `eval_duration`). Es hält das gewählte Modell mit
`keep_alive` warm und lädt es auf Wunsch vor. **Ein Modell, das der Nutzer
nicht gewählt hat, wird nie geladen.** Der Dienst bekommt diese Angaben über
den Socket.

### Architekturregel 5l — Wer Schlüssel hat, hat kein Werkzeug; wer Werkzeuge hat, hat keine Schlüssel

Folgt aus 5n und ersetzt die Fassung 1 (zwei Schreiber).

| | Inhalt | liest | schreibt | Ort |
|---|---|---|---|---|
| **Anbieter** | Adressen, Schlüssel, Anmeldung, Telegram-Token, Web-Passwort (Hash) | Gateway | Gateway (Web-Oberfläche, Selbstübernahme), Installer | `/opt/chimera/config/.env`, **root:chimera-tor 660** |
| **Wahl** | Reihenfolge, Ketten, Sprache, Zeitgrenzen | Gateway | Gateway (Telegram `/model`, Web, CLI) | `/opt/chimera/config/wahl.json`, root:chimera-tor 660 |

Der Agentennutzer `chimera` kann **keine** der beiden Dateien lesen.
Was er von der Wahl wissen muss (z. B. die Sprache), bekommt er über den
Socket.

**Telegram `/model`** bleibt, wie in openclawgotchi: Liste,
Fähigkeiten, Auswahl, Reihenfolge. **Gebaut 12.11.2026** in der
Gateway-Tür (`telegram.rs`): `/model` zeigt die Serverliste mit der
geltenden Wahl markiert und benennt Modelle, die gemessen keine Werkzeuge
können; `/model 3` oder `/model <name>` zieht den Verweis
`ollama/<modell>` in `wahl.json` nach vorn (Doppelung raus, alles andere in
der Datei bleibt). Geschrieben wird über `op: wahl_setzen`, also von der
Stelle, der die Datei gehört (5l). **„Set Ollama IP“ im Chat entfällt**
(smilez). Adressen werden auf der Web-Oberfläche eingetragen oder durch
die Netzsuche gefunden.

### Architekturregel 5h, Ergänzung — Die Reihenfolge bestimmt der Nutzer

- Es gibt eine **bevorzugte Liste** aus Anbieter/Modell-Paaren in frei
  gewählter Reihenfolge, Anbieter gemischt, z. B.
  `anthropic-abo/opus` → `ollama/qwen3.8:27b` → `anthropic-api/sonnet`.
- Jede Aufgabe nimmt diese Liste, **außer** sie hat eine eigene Kette.
- `suggest()` läuft nur bei der Ersteinrichtung oder auf Anforderung und
  schreibt einen **Vorschlag** in `wahl.json`, den es danach nie mehr
  überschreibt. Die Regel „Größtes Modell fürs Gespräch“ fällt weg.
  Stattdessen gilt: das erste Modell mit `tools`.
- Ein Modell ohne `tools` wird für Aufgaben, die Werkzeuge brauchen,
  **übersprungen und benannt**.
- **Stand am Gerät (1.11.):** `provider/setup.py` schlägt für das Gespräch
  noch das größte Modell vor (`gemma4:31b`; eine Antwort brauchte 71 Sekunden
  und lud das Modell erst), und `wahl.json` entsteht erst mit der
  Reihenfolge-Seite. Bis dahin entscheidet `OLLAMA_MODEL`; ist es leer, wählt
  der Vorschlag. Das Ersetzen durch „erstes Modell mit `tools`“ ist offen.
- **Leere Kette: melden, nicht ausweichen.** Den stillen Rückfall von
  OpenMinis auf „neuestes sichtbares Modell“ übernehmen wir nicht.
- Weitere Anbieter (LiteLLM, ROADMAP) werden auf der Web-Oberfläche
  angelegt: Typ, Adresse oder Schlüssel, dann die Modellliste. Der
  Ablauf ist der von OpenMinis.

### Architekturregel 5m — Die Web-Oberfläche ist eine Plattform aus Modulen

Fassung 2 (smilez, 30.10.): Die Oberfläche ist kein Konfigurationsformular,
sondern der **eine Zugang zu allem**. Nichts davon darf das Bearbeiten von
Dateien verlangen. Sie wächst nach und nach, deshalb ist sie von Anfang an
modular.

**Umfang (wächst Modul für Modul):**

| Modul | Inhalt |
|---|---|
| Chat | Chatfenster mit der einen Sitzung; Verlauf, ältere Sitzungen (8d) durchsuchbar |
| Anbieter | Ollama, Anthropic-Schlüssel, Claude-Anmeldung (5b) als gleichrangige Wege; Netzsuche, Test-Knopf, Modellliste |
| Modelle | Reihenfolge per Hoch/Runter, gemischt über Anbieter (5h); zum Testen steht Ollama vorn |
| Anzeige | Fenster im Fenster: spiegelt die Ausgabe des Waveshare-Displays live |
| Einstellungen | Optionsmenü: Sprache, Updates, Passwort, Telegram, Netz |
| Status | Dienste, Speicher, Temperatur, Protokolle |

**Aufbau:**

- **Rahmen und Module getrennt.** Der Rahmen (Anmeldung, Menü, Router,
  Designvorgaben) kennt kein einzelnes Modul. Ein Modul ist ein Verzeichnis
  `module/<name>/` mit `manifest.json` (Name, Titel je Sprache, Symbol,
  Reihenfolge, Einstiegsseite, nötige Rechte, optional Schnittstelle) und
  seinen Dateien.
- **Selbst erkennend.** Das Gateway liest `module/*/manifest.json` beim Start
  und auf Anforderung neu; ein neues Verzeichnis taucht im Menü auf, ohne dass
  Rahmen oder Gateway geändert werden. Ein kaputtes Manifest verwirft nur
  dieses Modul und wird gemeldet (Verdachtsfall, kein Stillschweigen).
- **Eingebaute und nachgelegte Module.** Die Grundmodule liegen im Binary
  (`include_str!`), Zusatzmodule als Dateien unter `/opt/chimera/web/module/`.
  Dasselbe Manifest gilt für beide.
- **Schnittstelle je Modul:** `/api/<modul>/…`. Eingebaut beantwortet sie das
  Gateway; ein Zusatzmodul nennt im Manifest einen Unix-Socket, an den das
  Gateway weiterreicht (Regel 14, keine Fremdbibliothek im Gateway).
- **Rechte:** Das Manifest nennt, was ein Modul darf (z. B. `chat`,
  `anbieter-lesen`, `anbieter-schreiben`, `wahl-lesen`, `wahl-schreiben`,
  `anzeige`). Das Gateway reicht nur durch, was eingetragen ist.
- **Anzeigespiegel:** Der Renderer (Regel 7, ein Prozess, ein Framebuffer)
  legt das fertige Bild lesbar im Shared Memory ab; das Gateway liest nur
  und liefert es als Bildfolge an die Seite. Das Gateway schreibt nie ins
  Panel.
- **Frontend:** Leichtes JavaScript ohne Build-Schritt und ohne Fremdpaket;
  Web Components, ein Modul = ein Element. Handytauglich.
- **Sitzungen:** Es bleibt bei **einer** Hauptsitzung für alle Türen
  (Regel 5s, 8d). Das Chat-Modul hängt am selben Strom wie Telegram;
  „Alle Chats“ heißt: die Hauptsitzung plus die abgelegten, diese nur lesbar.

**Umsetzung (Stand):** Rahmen, Anmeldung, Modul-Erkennung und das Chat-Modul
stehen in `rust/crates/tor/src/web.rs` und `rust/crates/tor/web/`. Festgelegt
dabei: Das Passwort liegt als `pbkdf2-sha256$N$SALZ$HASH` in
`CHIMERA_WEB_PASSWORT_HASH` (erzeugt mit `chimera-tor --passwort-hash`, Eingabe
nur über stdin); Anmeldung gilt 12 Stunden im Cookie `HttpOnly; SameSite=Strict`;
nach 5 Fehlversuchen je Minute antwortet das Gateway 429; jede Änderung
(POST) braucht den Kopf `X-Chimera: 1`. Offen ist nur die Hülle (`GET /`),
alles andere verlangt die Anmeldung. Moduldateien werden nur mit bekannter
Endung und ohne Pfadausbruch ausgeliefert; ein nachgelegtes Modul ersetzt nie
ein eingebautes. Das Chat-Modul darf nur, was sein Manifest als Recht nennt.

**Nur im eigenen Netz (Entscheidung 31.10.):** Die Oberfläche prüft in
jeder Anfrage die Quelladresse und bedient nur Loopback, private
(RFC 1918), Link-Local und IPv6-ULA; ohne erkennbare Quelle wird abgewiesen.
Grund: Ein IP-Filter der Unit (`IPAddressDeny`) scheidet aus, weil er am
Gateway auch Telegram und die Anbieter sperren würde, und an einer
Socket-Unit zeigte er am Pi ein ungeklärtes Verhalten. Die Prüfung im
Gateway ersetzt keine Firewall und keinen Router (Portfreigabe ins
Internet bleibt Sache des Nutzers); sie fängt den Fall ab, dass der Port
versehentlich erreichbar wird. `CHIMERA_WEB_LAN_NUR=0` hebt sie auf.

**Unverändert aus Fassung 1:** läuft im Gateway, nicht als eigener Prozess;
ohne Passwort startet sie nicht (5j); HTTP mit Passwort im LAN als
Voreinstellung, HTTPS Opt-in, sichtbarer Hinweis bei HTTP; Änderungen wirken
ohne Neustart; Schlüssel werden nur geschrieben, nie wieder angezeigt
(zurück kommt „gesetzt“).

### Architekturregel 5t — Anbieter, Schlüssel, Katalog, Wahl, Freigaben und Hosts sind sechs Ablagen mit je einem Schreiber

Vorgabe smilez (31.10.): Jeder Anbieter ist ein eigenes Modul, die Modelle
des Anbieters liegen darin. Mehrere Anbieter können dasselbe Modell mit
verschiedenen Optionen anbieten. Das Gateway schreibt nur, was es für
seine Aufgabe muss. Die Vorlagen (OpenMinis: Room-Tabellen mit
`instanzId/modellId`, openclawgotchi: eine Datei `active_model.json`) sind
Beispiele, keine Vorgabe.

| Ablage | Aussage | Ort | Schreiber | Neu aufbaubar |
|---|---|---|---|---|
| **Anbieter** | Was der Nutzer eingerichtet hat: Typ, Bezeichnung, Adresse, Anmeldeart, an/aus, Optionen je Modell | `config/anbieter/<id>.json` | Gateway | nein |
| **Schlüssel** | Geheimnis zur Anmeldung beim Anbieter | `config/geheim/<id>`, Modus 0600 | Gateway | nein |
| **Katalog** | Was der Anbieter zuletzt gemeldet hat: Modelle, Kontext, `tools`, Zeitpunkt, `fehlt_seit` | `state/katalog/<id>.json` | Gateway | **ja** |
| **Wahl** | Reihenfolge und Ketten als Verweise `<anbieter-id>/<modell>` | `config/wahl/wahl.json` | Gateway | nein |
| **Freigaben** | Je Werkzeug: Positivliste oder offene Zeitspanne (`bis`), Negativliste (DESIGN, Regel „Freigabe je Werkzeug auf Zeit“) | `config/freigaben/freigaben.json` | Gateway | nein |
| **Hosts** | Fernausführung: Adresse, Nutzer, Port, Schlüssel**name**, Hostschlüssel (Typ, Blob, gerechneter Fingerabdruck), Rechte je Host, Herkunft (`nutzer`/`vorschlag`) | `config/ssh/hosts.json` | Gateway | nein |

- **Eintragsschlüssel ist `<anbieter-id>/<modell>`**, nie der Modellname
  allein. „Sonnet über Abo“ und „Sonnet über OpenRouter“ sind zwei
  Einträge mit eigenen Optionen. Die Optionen stehen in der Anbieterdatei
  unter `modelle.<modell>` (`sichtbar`, `anzeigename`, `kontext`,
  `temperatur`, `extra_kopf`, `extra_koerper`); fehlt ein Feld, gilt der
  Katalogwert.
- **Beobachtung und Nutzerwille bleiben getrennt.** Der Katalog
  überschreibt nie Anbieteroptionen und umgekehrt.
- **Fähigkeiten werden gemessen** (`/api/show` → `tools`), nicht aus dem
  Modellnamen geraten. Nicht Messbares steht als „unbekannt“.
- **Verweise werden beim Laden geprüft.** Ein Verweis in der Wahl auf einen
  fehlenden Eintrag wird gemeldet und übersprungen, nie still gelöscht
  (5h: leere Kette melden).
- **Frist statt Löschen:** Fehlt ein Modell in der Abfrage, setzt der
  Katalog `fehlt_seit`; nach 7 Tagen verschwindet der Katalogeintrag, die
  Nutzeroptionen bleiben.
- **Atomar schreiben:** Sidecar neben dem Ziel, dann `mv`. Drei Dinge
  gehören dazu (11.11.2026, nach einem Code-Review):
  - **Der Name ist je Schreiber eindeutig** (Faden-Kennung oder Zähler).
    Ein fester Name wie `.datei.neu` lässt zwei Fäden dieselbe Nebendatei
    überschreiben — dann ist das Umbenennen gelungen und der Inhalt fremd.
  - **Vor dem Umbenennen flushen** (`fsync`). Ohne das steht nach einem
    Stromausfall eine leere Datei am Ziel; das ist genau der Fall aus
    Regel 8a (still erledigt, Daten weg).
  - **Bestehende Rechte bleiben** (`copymode`). Ein Ersetzen darf aus einer
    0640-Datei keine 0644 machen.
- **Format JSON-Dateien**, kein SQLite: kleiner Bestand, von Hand lesbar.
  SQLite bleibt dem Gedächtnisindex (8h).
- **Kleinste Schreibrechte:** `ReadWritePaths` nennt nur
  `config/anbieter`, `config/geheim`, `config/wahl`, `config/freigaben`,
  `state/katalog` und `state/log` (Protokoll der Freigaben),
  nie `config/` als Ganzes. Telegram-Token und Passwort-Hash ziehen aus der
  `.env` nach `config/geheim/`; die `.env` bleibt für Adressen und Schalter
  und wird vom Gateway nur gelesen. Der Installer übernimmt den Umzug in
  `migrate_from()`.
- **Durchgang statt Lesen:** Die Ablagen-Ordner gehören `chimera-tor` (700).
  `config/` bekommt das Durchgangsrecht (751; der Agent liest dort die
  `.env`). `state/` bleibt dem Agent verschlossen (10r) und wird 710
  `root:chimera-tor`: nur das Gateway darf hindurch, das Manifest bleibt
  für den Agent unerreichbar.
- **Nach einer Schlüsseländerung startet sich das Gateway neu**; der Socket
  fängt Anfragen in der Zwischenzeit auf.
- **Menü:** Je Anbieter ein Modul, das Gateway liefert dafür ein virtuelles
  Manifest. Ein Frontend-Element je Anbietertyp, je Instanz neu aufgerufen
  (zwei Ollama-Server = zwei Menüpunkte). Dazu „Anbieter hinzufügen“ und ein
  Modul „Reihenfolge“, das nur Verweise der Wahl führt.

### Architekturregel 5u — Passwort ändern braucht das alte; Werksreset braucht das Gerät

**Ändern:** Das alte Passwort wird geprüft (die Bremse aus 5m gilt),
danach enden alle Anmeldungen.

**Werksreset (Passwort verloren)** in zwei Absichten, jede mit einem
eigenen Satz, der **nur am Display** steht, nie in der Antwort an den
Browser:

1. „Reset beginnen“ erzeugt Satz 1; der Nutzer tippt ihn ab.
2. Stimmt er, erzeugt das Gateway Satz 2 (Bestätigung der Folgen); der
   Nutzer tippt auch ihn ab. Erst dann wird zurückgesetzt, und die Seite
   „Neues Passwort vergeben“ erscheint.

- **Satz:** in der am Gerät eingestellten Sprache (nicht der des Browsers;
  fehlt sie, Englisch), aus einem Pool von mindestens 8 Vorlagen je
  Sprache, dazu ein Zufallscode aus 6 Zeichen eines eindeutigen Alphabets
  (ohne 0/O, 1/I/l), Zufall vom Betriebssystem. Er wechselt bei jedem
  Aufruf. Beim Vergleich zählen Groß-/Kleinschreibung und überzählige
  Leerzeichen nicht; der Vergleich läuft in konstanter Zeit. Er gilt
  3 Minuten und genau einmal.
- **Begrenzung:** 3 Versuche je Satz. Gesperrt wird die **Funktion**, nicht
  die Adresse; nach jedem Fehlschlag steigt die Sperre 1 min → 5 min →
  15 min → 1 h → 24 h, Erfolg setzt zurück. Höchstens 5 neue Sätze je
  Stunde. **Der Zähler steht auf der Platte**; ein Neustart setzt ihn nicht
  zurück. Jeder Vorgang geht ins Protokoll, ab dem zweiten Fehlschlag in
  Folge als Warnung.
- **Nur aus dem LAN**, auch mit `CHIMERA_WEB_LAN_NUR=0`.
- **Anzeige:** Das Gateway schreibt nie ins Panel (5m). Es schickt den Satz
  als Ereignis an den Dienst, der ihn für die Geltungsdauer anzeigt. Der Satz
  liegt nur im Speicher. Ein Gerät ohne Display zeigt ihn im Journal.
- **Umfang:** Der Reset löscht nur, was das Gateway besitzt — Anbieter,
  Schlüssel, Wahl, Passwort-Hash, Telegram-Token. Sitzungen, Gedächtnis und
  Moods gehören dem Agenten und bleiben dem Uninstaller mit Ebenen
  vorbehalten.
- **Ausnahme zu 5j:** Der Zustand „Ersteinrichtung“ (kein Passwort-Hash
  vorhanden) bedient nur die Seite „Passwort vergeben“, nur aus dem LAN
  und nur, solange der Hash fehlt.

### Architekturregel 5v — Module melden sich einfach und sicher am Gateway an

Vorgabe smilez (31.10.): Neue Module müssen sich einfach, aber sicher
registrieren lassen; für die nötigen Dateien gibt es eine Vorlage, in der der
Entwickler nur Variablen ausfüllt. Wo möglich und sinnvoll wird in Rust
gebaut, und alles ist für Entwickler erweiterbar.

**Befund, der die Regel begründet:** Das Recht im Manifest schützt heute nur
eingebaute Module, deren API fest im Gateway steht. Ein nachgelegtes Modul
liefe im selben Ursprung wie der Rahmen und hätte das Cookie des Nutzers; sein
JavaScript könnte jede Schreibroute aufrufen. Ein Manifest-Recht allein hilft
dagegen nicht.

1. **Rechte stammen aus einer festen Liste im Gateway.** Ein unbekanntes
   Recht verwirft das Modul mit Meldung.
2. **Neu gefunden heißt nicht aktiv.** Ein nachgelegtes Modul wartet auf
   Freigabe, immer, auch mit leerer Rechteliste. Der Nutzer sieht Name, Rechte,
   Herkunft und SHA-256 über alle Dateien und gibt frei oder lehnt ab; für die
   Freigabe wird das **Passwort erneut** verlangt. Die Freigabe (mit Prüfsumme)
   steht in `config/module/freigaben.json` (5t). **Ändert sich eine Datei,
   verfällt sie.**
3. **Nachgelegte Module laufen eingesperrt:** `<iframe sandbox="allow-scripts">`
   ohne `allow-same-origin` (leerer Ursprung, kein Cookie, kein `window.chimera`),
   Verkehr nur per `postMessage`. Der Rahmen leitet Aufrufe an
   `/api/<modul>/…` weiter; das Gateway prüft **serverseitig** bei jedem Aufruf
   Recht und Freigabe. `/api/<modul>/` gehört genau diesem Modul. Die
   Content-Security-Policy der Modulseite sperrt `connect-src` und `eval`.
   Eingebaute Module (Teil des Binarys) laufen im Rahmen.
4. **Eigene Logik als eigener Prozess** mit Unix-Socket (Regel 14); das Gateway
   reicht nur `/api/<modul>/` dorthin durch, mit Größen- und Zeitgrenze, und gibt
   dem Modul nur den Teil des Nutzers mit, den sein Recht abdeckt (kein Cookie,
   kein Hash).
5. **Einfach:** Ablegen heißt, ein Verzeichnis nach `/opt/chimera/web/module/`
   zu kopieren (Besitzer root). Dazu eine Vorlage `module/_vorlage/` mit
   `manifest.json` (Platzhalter), `modul.js` und `VARIABLEN.md`;
   `chimera-tor --module-neu` setzt die Variablen ein und prüft mit demselben
   `manifest_lesen`, das beim Laden prüft; `--module-pruefen` zeigt die
   Prüfsumme. Entfernen heißt, das Verzeichnis zu löschen; die Freigabe verfällt.
6. **Erweiterbar.** Wer etwas hinzufügt, ändert genau eine Stelle: eine
   neue Sonde (`impl Sonde` + Zeile in `sonden()`), ein neues Recht (Eintrag in
   der Rechteliste), ein neuer Anbietertyp (`impl Anbieter` + Zeile in der
   Typliste). Ein Test durchläuft alle Einträge (eindeutige IDs, nichts leer).

**Grenze:** Das Gateway kann ein eingesperrtes Modul nicht daran hindern,
dem Nutzer in seinem eigenen Fenster Falsches **anzuzeigen**. Antwort darauf
sind Freigabe mit Prüfsumme und der Rahmenhinweis „Dieses Modul stammt nicht
vom Projekt“. Ein Modul-Dienst (Punkt 4) ist ein Prozess mit Rechten seines
Nutzers; der Installer legt ihn unter einem eigenen Nutzer an.

**Stand:** Gebaut sind Punkt 1 (Rechteliste `RECHTE`), Punkt 5 (Vorlage,
`--module-neu`, `--module-pruefen` mit Prüfsumme über alle Dateien, Dateinamen
und -grenzen, ohne symbolische Verweise) und Punkt 6 für Sonden (`status.rs`).
Offen sind Punkt 2 (Freigabe), 3 (Sandbox-iframe) und 4 (Modul-Socket).
Eingebaut sind `chat` und `status`.

### Architekturregel 5b, Fassung für das Gateway — PR #407 ist die Vorlage, Punkt für Punkt

Vorgabe smilez (16.10.): Die Abo-Anmeldung im Gateway hält sich an den
eigenen OpenMinis-PR #407 (`Smilez1985:fix/dynamic-claude-cli-version`,
Diff gesichert unter `shared/notes-chimera/quellen/pr407/pr407.diff`).
Der PR ist Kotlin und Swift, also wird er **nachgebaut**, nicht kopiert
(Regel 1, OpenMinis ist GPL-3). Übernommen wird das Verhalten:

1. **Quelle der Version:** `GET https://registry.npmjs.org/-/package/@anthropic-ai/claude-code/dist-tags`.
   Gewählt wird die **höchste plausible Version über alle Tags**, nicht
   `stable`, weil die Sperre eine Mindestversion prüft und `stable`
   hinter einem Modellstart herhinken kann.
2. **Plausibel** heißt: genau `^\d+\.\d+\.\d+$`, numerisch verglichen
   (2.1.280 > 2.1.99).
3. **Nur vorwärts** (`accept()`): Ein Wert gleich oder kleiner dem
   bekannten wird verworfen. Ein Ausrutscher der Registry kann die
   Kennung nicht hinter eine erfüllte Sperre zurückschieben.
4. **Reihenfolge der Auflösung:** Wert dieses Laufs, dann gespeicherter
   Wert (überlebt Neustart und Offline-Start), dann einkompilierte
   Untergrenze. Der schlechteste Fall ist damit der feste Wert von
   früher.
5. **Nie im Anfragepfad:** Eine Anfrage liest nur den Zwischenspeicher.
   Abgerufen wird beim Start des Gateways und danach höchstens einmal in
   24 h, in einem eigenen Thread mit 10 s Zeitgrenze. Ein Fehler lässt den
   alten Wert stehen. Läuft schon ein Abruf, startet kein zweiter
   (atomarer Schalter).
6. **Eine Untergrenze, nicht zwei:** Der Rückfallwert wird aus dem
   User-Agent-Literal des Header-Satzes gelesen, nicht als zweite
   Konstante geführt.
7. **Ein Header-Satz für beide Wege (#360):** Token-Weg und Chat-Weg lesen
   dieselbe Liste `current()`. Getauscht wird **nur die Version im
   User-Agent** (`claude-cli/<v> (external, cli)`). `X-Stainless-*`,
   `X-App: cli` und `Anthropic-Dangerous-Direct-Browser-Access` bleiben
   genau wie in der Vorlage, weil das Backend sie als Satz prüft.
   `anthropic-beta` gehört nur auf den Chat-Weg.
8. **Token-Endpunkt** `https://claude.ai/v1/oauth/token` (nicht mehr
   `console.anthropic.com`). Das Auffrischen erfolgt vor Ablauf und über
   einen Koordinator (PROVIDER.md).

**Tests wie in der Vorlage, gegen den echten Code:** `accept()` lehnt
ältere und unplausible Versionen ab; `parse_dist_tags` wählt die höchste;
eine Version zur Laufzeit erreicht **beide** Wege; nie unter der
Untergrenze; der Chat-Weg führt keine eigene Kopie der Header. Jeder Test
mit Gegenprobe.

**Wo der Satz an Werten gepflegt wird:** Die Werte (Untergrenze,
`X-Stainless-*`, Beta-Liste) folgen OpenMinis `main`. Ändern sie sich
dort, wird hier nachgezogen. Das ist ein bekannter Pflegepunkt, keine
Automatik.

**Befund am heutigen Code (`provider/anthropic.py`), weicht von der
Vorlage ab und wird beim Umzug ersetzt:**
- Die Version kommt aus `claude --version` (Unterprozess), nicht aus der
  Registry. Ohne installierte CLI bleibt sie dauerhaft beim Rückfallwert
  2.1.284.
- Es gibt keine Regel „nur vorwärts“, keinen gespeicherten Wert und keine
  24-h-Auffrischung.
- Die `X-Stainless-*`-Header, `X-App` und der Token-Weg fehlen ganz.
  Gesendet wird nur `anthropic-beta: oauth-2025-04-20`.


### Architekturregel 5o — Der Briefkasten ist ein eigener Prozess hinter dem Gateway, mit eigenem Port

andere Agenten ──► Gateway :<briefkasten-port>  (Token-Prüfung A19)
                          │ Unix-Socket /run/chimera/post.sock
                       Briefkasten (Nutzer chimera-post, kein Netz)
                          │ ablegen, halten bis quittiert (A5)
                          │ Reiz → Steuerkanal des Dienstes
                       Dienst: Turn im Kanal „briefkasten“ (5i)

- **Eigener Prozess, eigener Nutzer** `chimera-post`, eigene Ablage
  (`/var/lib/chimera/post/`, nur für ihn). Wie der Dienst ohne Netz
  (`IPAddressDeny=any`). Ein Absturz trifft weder Gesicht noch Gateway.
- **Eigener Port am Gateway**, getrennt von der Web-Oberfläche. Grund:
  zwei verschiedene Arten von Zugang (Agent-Token und Nutzerpasswort)
  sollen sich keinen Eingang teilen. Damit lässt sich jeder für sich
  in der Firewall öffnen, schließen oder abschalten. Das Gateway prüft
  das Token am Tor und reicht nur durch, was bestanden hat. Ohne
  Teilnehmerliste bleibt der Port zu (5j).
- **Eigenständig** (entschieden 16.10.2026): Chimeras Briefkasten ist ein
  vollwertiger Briefkasten, bei dem sich andere Agenten anmelden. Er ist
  nicht Teilnehmer eines fremden. Rückfall-Adressen tragen die Clients
  selbst (woa-l `BRIEFKASTEN_URLS`, der Reihe nach probiert).
  Standortspezifische Ergänzungen (etwa das Abholen von einem
  vorherigen Briefkasten) gehören nicht ins Repo, sondern nach `lokal/`
  (gitignoriert).
- **Das Protokoll ist das von woa-l**, also MCP über HTTP mit denselben
  Werkzeugnamen und Feldern (`briefkasten_senden`, `klingel_wach`,
  `uebergabe_ablegen`, `datei_ablegen` …). Damit erreichen bestehende
  woa-l-Teilnehmer Chimera, ohne dass sich auf ihrer Seite etwas ändert.
  **Nachgebaut** wird nach den Regeln von woa-l, nicht der Code
  übernommen. Begründung: Regel 14, weil der Prozess dauernd läuft und
  nicht auf das Modell wartet. Er ist damit **Rust**, im selben Cargo-
  Workspace wie das Gateway.
- **Wecken heißt hier: ein Turn in der Hauptsitzung (5s).** Der Briefkasten
  meldet über den Steuerkanal „Nachricht Nr. n von X“. Der Dienst stellt
  sie als Turn im Kanal `briefkasten` zu. Läuft schon ein Turn, wartet
  die Nachricht in der Reihe, wie heute bei Telegram (`Session.busy`).
  Quittiert wird **erst nach dem Turn** (A5). Ein Absturz mitten im Turn
  führt also zu einer erneuten Zustellung, nicht zu einer verlorenen
  Nachricht.
- **Was aus den Skills wird** (Verhalten, nicht Text):

  | woa-l / Skill | in Chimera |
  |---|---|
  | Klingel, Wächter, Totmann | entfallen. Der Briefkasten ist ein systemd-Dienst mit `Restart=`, und die Zustellung ist ein Socket-Aufruf, kein Weckruf über eine App. |
  | `sitzungsstart` | Start des Dienstes: Sitzung laden, Post nachliefern, Gedächtnis einspeisen (8c) |
  | `uebergabe`, `sitzungswechsel` | Regel 8d (Wechsel bei Gewicht) |
  | MCP-Werkzeuge senden/lesen/Datei | eingebaute Werkzeuge des Agenten, die über den Socket mit dem eigenen Briefkasten reden. Fremde Briefkästen erreicht er über das Gateway (5n). |
  | Arbeitssitzung ermitteln (A2) | entfällt. Es gibt genau eine aktive Sitzung. |

### Architekturregel 5p — Was ein anderer Agent schreibt, ist Eingabe, kein Befehl

Eine Nachricht von außen kann einen Turn auslösen, aber sie bekommt
**nicht** die Rechte des Nutzers.

- Im Kanal `briefkasten` sind Root (10s), das Ändern von Anbietern oder
  Wahl und das Anlegen neuer Teilnehmer **gesperrt**. Diese Dinge gehen
  nur über Telegram (Positivliste) oder die Web-Oberfläche (Passwort).
- Der Agent bekommt die Nachricht mit Absender und dem Hinweis, dass es
  sich um eine Nachricht eines anderen Agenten handelt (wie 5f bei
  fremden Werkzeugen).
- Grund: Ein Token kann erbeutet werden, und ein Agent kann
  fehlgesteuert sein. Ohne diese Regel wäre der Briefkasten ein zweiter,
  schwächer geschützter Weg zu allem, was der Nutzer darf.

---

### Architekturregel 5q — Der Prompt wird so gebaut, dass der Cache trifft, und das wird gemessen

Alle Anbieter cachen nur einen **exakt gleichen Anfang** der Anfrage. Ein
einziges abweichendes Zeichen macht den Cache ungültig (DeepInfra, Groq,
OpenAI). „Lokal“ heißt deshalb: **Chimera selbst** sorgt dafür, dass dieser
Anfang Byte für Byte gleich bleibt. Es setzt die Cache-Marken selbst und
misst die Treffer. Auf den Anbieter verlassen wir uns nicht.

**1. Feste Reihenfolge, das Stabile zuerst** (ergänzt 8e):
`Werkzeuge → SOUL … memory.md → letzte Tage → Verlauf → neue Nachricht → Laufzeit`.
- **Laufzeit** (Uhrzeit, Sensoren, Kanal) steht nie im Systemprompt. Sie
  geht als letzter Block an die neue Nachricht. Begründung: Ein Zeitstempel
  vorn macht jeden Cache ungültig (Anthropic, Groq: „Common mistake“).
- Die Werkzeugliste ist **je Sitzung eingefroren**: gleiche Werkzeuge in
  gleicher Reihenfolge (sortiert nach Name), dazu dieselbe `tool_choice` und
  dieselbe Denkstufe. Neue Werkzeuge oder Skills wirken erst ab der nächsten
  Sitzung, wie bei 8e.
- **Der Verlauf wird nur angehängt.** Innerhalb einer Sitzung wird nie
  umgeschrieben. Verdichten (8g) bricht den Cache bewusst einmal, darum
  kommt es selten.

**2. Gleiche Bytes:** Das Gateway serialisiert deterministisch (serde_json,
Schlüssel sortiert). Die Werkzeugschemas werden einmal je Sitzung zu Bytes
gemacht und danach unverändert wiederverwendet. Blöcke, die der Anbieter
liefert (z. B. `encrypted_content` der Websuche), kommen **unverändert**
zurück, auch in der Sitzungsablage (8d).

**3. Cache-Marken je Anbieter, nach deren Beispielcode** (Adapter im Gateway):

| Anbieter | Was das Gateway setzt |
|---|---|
| Anthropic | `cache_control: {type: "ephemeral"}` an bis zu 3 Stellen: Ende Werkzeuge, Ende des stabilen Systemteils, Ende des Verlaufs vor der neuen Nachricht (erlaubt sind 4). Kein Beta-Header. TTL 5 min als Vorgabe, `1h` als Wahl in `wahl.json` (Schreiben kostet dann 2× statt 1,25×). |
| OpenRouter | Bei Anthropic-, Gemini- und Alibaba-Modellen `cache_control` in den content-parts, bei den übrigen automatisch. `session_id` = Sitzungs-ID, damit Folgeanfragen beim selben Anbieter landen (Sticky Routing). `provider.order` wird **nicht** gesetzt, weil das Sticky Routing abschaltet. Rückfall regelt Chimeras eigene Kette. |
| DeepInfra, OpenAI, Mistral | automatisch, dazu `prompt_cache_key` = Hash der Sitzungs-ID |
| DeepSeek, Groq, Gemini (implizit) | automatisch, nichts zu setzen |
| Ollama (LAN) | keine API-Steuerung. `keep_alive` aus `wahl.json` (Vorgabe 30 min), `num_ctx` je Modell fest, kein Modellwechsel innerhalb einer Sitzung ohne Not. Gemessen wird `prompt_eval_cached_count`. |

**4. Messen statt glauben:** Jede Antwort trägt `Reply.cache` mit
`gelesen`, `geschrieben`, `neu` (Tokens). Das Gateway liest dafür die Felder
des jeweiligen Anbieters (`cache_read_input_tokens`, `cached_tokens`,
`prompt_cache_hit_tokens`, `prompt_eval_cached_count` …). Die Trefferquote
je Sitzung steht im Protokoll und in `chimera status`. Liegt sie ab dem
zweiten Turn bei 0, gibt es eine Warnung: Dann bricht etwas den Anfang
(Regel „stiller Erfolg“). Eine Mindestlänge unter der Grenze des Modells
(Anthropic 512–4.096 Tokens) gilt nicht als Fehler, wird aber benannt.

**5. Kein Antwort-Cache.** Keine Anbieterdoku empfiehlt ihn, und OpenAI
betont, dass Caching die Ausgabe nicht deterministisch macht. Gleiche Frage
heißt bei Chimera nicht gleiche Lage.

**Test (Regel 9, mit Gegenprobe):** Zwei Turns derselben Sitzung werden
gebaut. Der Anfang bis zur letzten Cache-Marke muss byte-gleich sein.
Gegenprobe: Die Uhrzeit wird in den Systemprompt verschoben, der Test muss
rot werden. Am Gerät: Ab dem zweiten Turn ist `gelesen > 0` bei Anthropic
und bei Ollama.

---

### Architekturregel 5r — Websuche ist ein Werkzeug des Gateways, kein freier Netzzugang

**Für den Agenten gibt es genau ein Werkzeug:** `web_suche` (Anfrage,
höchstens n Treffer) und optional `web_abruf` (URL). Wie gesucht wird,
entscheidet das Gateway je Anbieter:

| Anbieter | Weg (nach Anbieterdoku) |
|---|---|
| Anthropic | Server-Tool `web_search_20250305` (`max_uses`, optional `allowed_domains`/`blocked_domains`, `user_location`), dazu `web_fetch_20250910`. $10 je 1.000 Suchen. Neuere Versionen nur mit `allowed_callers: ["direct"]`, sonst kommt 400. |
| OpenRouter | `tools: [{type: "openrouter:web_search"}]`. Nicht `plugins: web` und nicht `:online` (beide deprecated). Quellen kommen als `annotations` `url_citation`. |
| Gemini, Groq (gpt-oss) | `google_search` bzw. `browser_search` |
| DeepInfra, DeepSeek, Mistral-Chat, Ollama | **Keine eingebaute Suche.** Das Gateway führt `web_suche` selbst aus, über eine **Suchquelle** (Tabelle unten), die der Nutzer mit **eigenem Schlüssel** einträgt. |

**Suchquellen** (Prüfung der AGB am 29.10.2026, nicht juristisch; Beleg:
`recherche/2026-10-29-websuche-anbieter-agb.md`). Grundsatz: Der Nutzer
schließt den Vertrag selbst. Chimera liefert **nie einen eigenen Schlüssel
mit** und betreibt **keinen Proxy** (Weiterverkauf, bei Brave, Tavily und Exa
verboten).

| Quelle | Stand | Einschränkung |
|---|---|---|
| Ollama Cloud (`ollama.com/api/web_search`, `/api/web_fetch`) | erste Quelle | Free-Konto, `OLLAMA_API_KEY`; Limits nicht dokumentiert, 429 sauber melden; Ergebnisse auf 8.000 Zeichen kürzen |
| Tavily | einbaubar | 1.000 Credits/Monat; Eingaben darf Tavily zum Training nutzen, Hinweis an den Nutzer |
| Exa | einbaubar | $10/Monat Guthaben |
| SearXNG (selbst betrieben) | einbaubar | Adresse in `wahl.json`, **keine** fremde öffentliche Instanz als Vorgabe |
| Brave | nur mit Einschränkung | AGB verbieten Speichern der Ergebnisse und KI-Training: **kein Such-Cache auf Platte**, Ergebnisse nie in Trainingsdaten; Kreditkarte nötig |
| ddgs (DuckDuckGo-Scraper) | nur Opt-in | kein Vertrag, bricht oft; Warnhinweis |
| Serper, Google Custom Search | **nicht eingebaut** | Serper scrapt Google; Custom Search für Neukunden geschlossen |

Ergebnisse der Websuche leben **nur im Arbeitsspeicher und im Verlauf**,
nie in einem eigenen Such-Cache (gilt für alle Quellen, wegen Brave).
Quellen sind Einträge der Registry; die Preise und Limits werden vor jedem
Release neu geprüft.

**Gebaut am 12.11.2026 (erste Stufe):** `op: web_suche` im Gateway
(`rust/crates/tor/src/suche.rs`), Werkzeug `web_suche` im Agenten. Quellen
stehen in `wahl.json` unter `suche.quellen` als Liste, in dieser Reihenfolge:

```json
{"suche": {"quellen": ["searxng:http://127.0.0.1:8888", "ollama"]}}
```

- `searxng:<adresse>` — eigene Instanz, `GET {adresse}/search?q=…&format=json`.
  Antwortet sie mit **403**, sagt der Fehlertext, dass `search.formats` das
  JSON nicht führt (sonst sucht jemand an der falschen Stelle).
- `ollama` — `https://ollama.com/api/web_search` mit **`OLLAMA_API_KEY`** aus
  der Umgebung des Gateways (`.env`, nur das Gateway liest sie).
- `ddg` — `https://lite.duckduckgo.com/lite/`, **ohne Schlüssel und ohne
  eigene Instanz**. Bewusst Opt-in: kein Vertrag, die Seite kann sich ändern
  oder bremsen. Die Treffer stehen hinter einem Weiterleitungs-Link
  (`uddg=`-Parameter, prozent-kodiert); liefert die Seite keine Treffer,
  ist das ein **benannter Fehler**, kein stiller Erfolg.
- Fällt eine Quelle aus, wird die nächste versucht; scheitern alle, kommt
  `suche_gescheitert` mit jedem Grund. Ist **keine** Quelle eingetragen,
  kommt `keine_quelle` mit einem Beispiel — kein stiller Ausfall.
- Treffer: höchstens 5 (bis 10 auf Auftrag), 400 Zeichen Auszug, 8.000
  Zeichen gesamt, **nichts auf Platte**.
- **`web_abruf` (URL holen)** — gebaut 12.11.2026, `rust/crates/tor/src/abruf.rs`:
  `op: web_abruf` mit `url`. Die Positivliste der Ziele ist **kein zweiter
  Ort**, sondern `positiv` im Freigabe-Zustand (Regel „Freigabe je Werkzeug
  auf Zeit"): vor jedem Verbinden fragt das Gateway
  `freigaben::pruefen(p, "web_abruf", Some(host), jetzt)`. Das ist **Stufe 2**
  jener Regel — die Freigabe prüft jetzt wirklich jemand. Ablehnung kommt als
  `abruf_gesperrt` und nennt Werkzeug, Ziel und Grund; protokolliert wird sie
  von `pruefen` selbst (`state/log/freigabe.log`).
  - Nur `http`/`https`, nur GET, nur Text (`text/*`, `application/json`,
    `application/xhtml+xml`) — alles andere wird mit dem Typ abgelehnt,
    statt Bytes in den Verlauf zu schütten.
  - **Höchstens 3 Umleitungen, jede erneut geprüft.** Eine Umleitung ist ein
    Zielwechsel; wer sie ungeprüft folgt, hebt die Positivliste auf.
  - **Eigene Adressen werden nie geholt** (`localhost`, `*.local`, `::1`,
    Loopback und die privaten IPv4-Bereiche) — außer der Name steht
    ausdrücklich in `positiv`, dann ist es der Wille des Nutzers. Namensauflösung
    prüft das Gateway nicht (kein DNS-Riegel, ehrlich benannt: ein Name, der
    auf 10.x zeigt, kommt durch die Namensprüfung).
  - Grenzen wie bei der Suche: Frist 20 s, höchstens 2 MB gelesen, Rückgabe
    **4.000 Zeichen** (`gekuerzt: true` sagt es), **nichts auf Platte**.

**Grenzen:**
- **5n bleibt hart:** Das Gateway verbindet sich **nie mit einer beliebigen
  URL**. Feste Anbieter-Hosts, die eingetragenen Suchquellen — und seit
  12.11. `web_abruf`, aber **nur** mit einer Adresse, die der
  Freigabe-Zustand durchlässt (Vorgabe: `positivliste`, also nichts von
  selbst). Ohne Freigabe gibt es keinen Abruf; die Entscheidung trifft der
  Nutzer in der Oberfläche oder per `/frei`, nie das Modell.
- **Suchtreffer sind Eingabe, kein Befehl** (wie 5p). Sie werden im Prompt
  als fremder Inhalt markiert.
- **Kosten:** `max_uses` je Turn (Vorgabe 3) und ein Tageslimit in
  `wahl.json`. Wird es erreicht, wird das gemeldet und nicht still weiter
  bezahlt.
- **Fest je Sitzung:** Websuche an oder aus wird nicht pro Anfrage
  umgeschaltet. Bei Anthropic macht das den System- und Verlaufscache
  ungültig (5q).
- **Rückfall über Anbietergrenzen (5h):** Serverseitige Suchblöcke von
  Anthropic versteht kein anderer Anbieter. Fällt die Kette auf einen anderen
  Anbieter zurück, macht das Gateway daraus Text (Titel, URL, Auszug). Die
  Rohblöcke bleiben in der Ablage für den Weg zurück zu Anthropic.
- **Quellen werden gezeigt:** Telegram und Web hängen die URLs an die
  Antwort.

### Architekturregel „Aufrufe, nicht Text“ — das Gateway trägt Werkzeuge, der Ausführer führt sie aus

**Entschieden (smilez, 12.11.2026):** Native Tool-Calls werden gebaut. Das
Text-Protokoll `TOOL: name {json}` bleibt **Rückfall** für Modelle, deren
Katalog keine Werkzeuge misst — nie beides gleichzeitig (zwei Wege zu
demselben Werkzeug sind die Fehlerklasse aus 10g).

**Formate: alle, jedes für seinen Fall, mit Universaladapter.** Nachgeprüft
am 12.11. (Quellen in Klammern):

| | Werkzeugbeschreibung | Aufruf in der Antwort | Ergebnis zurück |
|---|---|---|---|
| Ollama `/api/chat` | `tools[].{type:"function",function:{name,description,parameters}}` | `message.tool_calls[].function.arguments` = **Objekt** (`api/types.go`) | `{"role":"tool","content":…,"tool_name":…}` |
| OpenAI-kompatibel | wie oben | `arguments` = **JSON-String** (`openai/openai.go` marshalisiert) | `role:"tool"` + `tool_call_id` |
| Anthropic | `tools[].{name,description,input_schema}` | Block `{"type":"tool_use","id","name","input"}` | `user`-Nachricht mit `tool_result` + `tool_use_id` |

**Intern gilt ein neutrales Format** (`name`/`description`/`parameters`), je
Anbieter ein Serialisierer. Warum nicht OpenAI als Nenner: Anthropic hat
kein `function`-Objekt, kein `type`, ein anderes Ergebnisformat — man würde
ständig hin und zurück übersetzen. Der Adapter nimmt Argumente **als Objekt
oder als String** an (`untagged`) und hält sie intern als Objekt; an der
Grenze wird genau einmal konvertiert.

**`content: ""` ist kein Fehler.** Ollama und Anthropic liefern bei reinem
Werkzeugaufruf leeren Text. „Leer" ist nur, wenn **weder** Text **noch**
Aufruf kommt. Abbruch der Schleife: keine Aufrufe mehr.

**Eine Zeitgrenze ist nicht „nicht erreichbar"** (13.11.2026). Das Gateway
bricht einen Chat nach 300 s ab (`ollama::AUFRUF`). Ein Denkmodell antwortet
in dieser Zeit womöglich nicht, weil es noch denkt — der Server ist aber da.
Bisher hieß jeder Aufruffehler „<host> antwortet nicht: …"; das schickt den
Suchenden zum Netz, obwohl die Ursache am Modell liegt (zu große Aufgabe, zu
langer Gedankengang). Jetzt wird die Zeitgrenze eigens erkannt: Code
`zeitgrenze`, Text nennt die Grenze und den Verdacht. Alles andere bleibt
`nicht_erreichbar`. Gemessen am 13.11. am Pi: derselbe Chat mit `qwen3.6:27b`
und warmer Ladung braucht 31 s — die Grenze ist also nicht knapp, aber sie ist
endlich.

**Denktext ist keine Antwort** (13.11.2026). Ein Denkmodell liefert seinen
Gedankengang in `message.thinking`, getrennt vom Antworttext. Der zählt
weder als Text noch als Aufruf: Er wird **nicht** als Antwort ausgegeben —
der Agent würde das Selbstgespräch des Modells als Ergebnis nehmen — und auch
**nicht verschwiegen**. Kommt weder Text noch Aufruf, aber Denktext, lautet
der Fehler `nur_gedacht` und nennt Länge und Auszug (`fehler.denkzeichen`,
`fehler.denkauszug`, 400 Zeichen). „leer" schickt den Suchenden in die falsche
Richtung (Netz, Modell, Format); „nur_gedacht" sagt, wo es hängt: Das Modell
denkt und kommt vor der Antwort nicht mehr zum Zug. Gemessen am 13.11. am
Modellserver: ein Strom-Block mit 127 Zeichen `thinking` und danach die
`tool_calls` — der Denktext kommt also real vor.

**Mehrere Aufrufe je Antwort** sind erlaubt (beide Anbieter können das) und
werden in der Reihenfolge ihrer `index` (Ollama; im Strom Teilstücke
zusammenkleben) bzw. ihrer Blockposition (Anthropic) abgearbeitet. Grenzen
in `wahl.json`: `max_werkzeuge_je_turn` (Vorgabe 8) und
`max_werkzeuge_je_runde` (Vorgabe 3).

**Schemas nur an Modelle, die sie können** (gebaut 12.11.2026): Steht im
Katalog `tools: false`, schickt das Gateway keine Werkzeuge mit und sagt es in
der Antwort (`werkzeuge_abgeschaltet`); `tools: null` ist unbekannt und gilt
nicht als „nein“. Damit braucht der Agent kein eigenes Wissen über das Modell —
die Entscheidung bleibt dort, wo der Katalog liegt.

**Wer führt aus:** unverändert der Agent, über `chimera-sohelper` (Regel
„Wer prüft, führt aus"). Das Gateway trägt nur Schema und Aufruf hin und
zurück; es führt **kein** Agentenwerkzeug aus. Ausnahmen sind die
Gateway-eigenen Werkzeuge `web_suche`/`web_abruf` (5r) — Netz und Schlüssel
liegen dort, nicht beim Agenten.

**IDs:** Ollamas `id` ist `omitempty` und fehlt in Doku-Beispielen — nicht
als Verbindungsschlüssel benutzen; korreliert wird über `tool_name` und
Reihenfolge. Anthropic `tool_use_id` ist Pflicht. Beim Übersetzen zwischen
Formaten werden IDs neu vergeben.

**Streaming ist umschaltbar** (`stream` in `wahl.json`, Vorgabe **aus**):
aus = eine Antwort, keine Akkumulation. An = NDJSON, Teilstücke je `index`
zusammenkleben, Werkzeuge erst nach `done` ausführen. Der Schalter steht in
GUI (Modul `wahl`), CLI (`chimera-tor --wahl-stream an|aus`) und Telegram
(`/stream`). Ollama hat `stream` default **true** — das Gateway setzt den
Wert immer ausdrücklich.

**Ein Feld, ein Ort.** Keine Tür liest die Datei und schreibt sie im Ganzen
zurück: `daten::wahl_feld_setzen` prüft Feldnamen und Typ, ändert **ein**
Feld und erhält den Rest. Bekannt sind `stream` (bool) und `reihenfolge`
(Liste gültiger Verweise `<anbieter-id>/<modell>`, ohne Doppelte, höchstens
`KETTE_MAX` = 64). Sortieren und Kürzen der Kette gehen über dieselbe Tür:
die Oberfläche schickt die **ganze** Liste, nicht „bewege Eintrag 3" — so
gibt es keine Teilzustände. Telegram und die Web-Tür gehen über die dünne
Hülle `wahl.rs`, die Kommandozeile über den Socket (`op: wahl_feld_setzen`).
Damit kann kein Web-Modul die Struktur überschreiben, und drei Fassungen
von „lesen, ändern, schreiben" entstehen nicht. Eine kaputte `wahl.json`
wird gemeldet (409/`wahl_kaputt`) und nicht überschrieben.

### Architekturregel 5b, Ergänzung — Die Abo-Anmeldung ist Opt-in mit Hinweis

Anthropics Policy erlaubt Abo-OAuth „exclusively“ für Claude Code und eigene
native Apps; Chimera darf Abo-Zugangsdaten nach deren Wortlaut nicht
„sammeln, speichern oder weiterleiten“. Technisch geht der Weg (OpenMinis
tut es), das Risiko ist eine Kontosperre. Darum:
- Der **Schlüsselweg** (API-Schlüssel) ist der empfohlene Anthropic-Weg.
- Die Abo-Anmeldung (5b) ist **aus**, bis der Nutzer sie ausdrücklich
  einschaltet, mit Hinweis auf das Risiko.
- Der Anmeldepfad folgt PR #407 (Header und Version aktuell halten); der
  Systemprompt-Anfang für Abo-Zugänge ist Teil der Anmelde-Schicht, nicht
  des Prompts nach 5q.
- Die Cache-TTL (5 min, Wahl 1 h) wird am Gerät **nachgemessen**, bevor sie
  als Vorgabe feststeht. Wie das Abo-Caching abgerechnet wird, ist nicht
  dokumentiert.


---

## 5. Renderer

### Architekturregel 6 — Keine absoluten Pixelwerte

Noisys Renderer ist auf 240×240 festgenagelt (18 Stellen mit
Pixelkonstanten, dazu Werte wie `HAIR_MAX_LAG = 7`). Whisplay ist
240×**280**.

Chimeras Renderer rechnet **ausschließlich relativ zu `WIDTH`/`HEIGHT`**.
Kein Letterboxing, keine Verzerrung. Die 40 zusätzlichen Zeilen werden
Statuszeile: Mood-Name, Akku, Agent-Zustand.

Übernommene Mechanik aus Noisy: Komponenten-Pipeline mit fester
Zeichenreihenfolge (Glow → Body → Frisur → Accessoires → Augen → Mund →
Partikel), Blink-Engine, Nachlauf-Effekte, Software-Dimming.

### 5.2 Übergänge zwischen Moods

Noisy blendet nur die **Farben** ineinander, alles andere springt. Dort
fällt das kaum auf, weil die Moods aus einer festen Tabelle kommen und
einander ähneln. In Chimera erfindet das Sprachmodell Ausdrücke — zwei
aufeinanderfolgende können weit auseinanderliegen, und ein Sprung sieht
dann aus wie ein Bildfehler.

Chimera blendet deshalb über **alle** Felder. Die Mechanik ist dieselbe
wie beim Mischen (Abschnitt „Drei Stufen der Erzeugung"), nur kommt die Zeit dazu.

#### Architekturregel 6b — Weich ist der Normalfall, hart muss möglich bleiben

Ein Reflex, der über eine halbe Sekunde einblendet, ist kein Schreck,
sondern eine Verzögerung. Moods mit `fast_track` wechseln deshalb
**sofort** — dasselbe Merkmal, das im Umgebungshören die Sofortreaktion
auslöst (Abschnitt „Umgebungshören im Ruhezustand", Ebene 1). Wer es ausdrücklich will, bekommt den harten
Wechsel auch ohne dieses Merkmal.

Drei Feinheiten, die den Unterschied machen:

- **Die Dauer ist eine Zeitangabe, keine Bildanzahl.** Sinkt die Bildrate
  beim Sprechen (Abschnitt „Mienenspiel beim Sprechen"), dauert ein Übergang trotzdem gleich lang.
- **Der Fortschritt hängt an der Uhr, nicht an der Zahl der Aufrufe.**
  Bleibt der Renderer einmal hängen, springt der Übergang weiter, statt
  stehenzubleiben.
- **Ein neuer Wechsel setzt am Zwischenstand an**, nicht am alten
  Ausgangspunkt. Sonst ruckt es zurück, wenn zwei Wechsel dicht
  aufeinanderfolgen.

Der Verlauf ist weich statt gleichmäßig: Ein linearer Übergang beginnt und
endet abrupt, obwohl sich die Werte gleichmäßig ändern.

Noisys `AUDIO_SMOOTHING = 0.18` bleibt daneben für die Audiokopplung
erhalten — dort glättet es jetzt die eigene Sprachausgabe (Abschnitt „Mienenspiel beim Sprechen") statt der
Musik.

### Architekturregel 6c — Das Panel ist eine Eigenschaft, keine Annahme

Chimera ist **nicht auf ein Panel festgelegt** — das senkt die
Einstiegshürde: Wer einen Pi mit E-Paper oder einen GamePi13 hat, soll
Chimera benutzen können, ohne Hardware zu kaufen.

Nichts oberhalb der Anzeigeschicht weiß, welches Panel angeschlossen ist.
Der Renderer fragt nach Fläche und Fähigkeiten. Einzelheiten und die Liste
der Anzeigen: `docs/DISPLAYS.md`.

**Der E-Paper-Treiber bleibt** und wird aus dem eigenen Fork übernommen,
wo die Unterscheidung mono gegen B bereits gebaut ist — samt dem teuer
erworbenen Wissen über Zeitverhalten (B-Variante: Vollbild rund 15–20 s,
Zeitgrenze 120 s statt 45 s).

### Architekturregel 6d — Dieselben Moods, verschiedene Darstellungen

Ein Panel, das 20 Sekunden je Bild braucht, kann nicht animieren — aber
ein gutes Standbild zeigen. Der Mood bleibt derselbe Datensatz, nur seine
Umsetzung ändert sich: animiert, Standbild, reduziert (1 Bit),
reduziert mit Akzent (S/W + Rot).

Die reduzierte Form ist **keine Notlösung**, sondern eine eigene
Gestaltung. Ein Gesicht in Strichzeichnung kann ausdrucksstärker sein als
eines mit Farbverlauf — es muss nur dafür entworfen sein.

### Architekturregel 6e — Anzeige bei jedem Start prüfen

Wer das Panel wechselt, schaltet ein und es funktioniert. Bei jedem Start
wird erkannt, was angeschlossen ist; weicht es ab, werden fehlende
Abhängigkeiten nachinstalliert und der passende Treiber aktiviert.

Bei mehrdeutigem Befund wird **gemeldet und vorgeschlagen**, nicht
geraten — ein falscher Treiber kann ein E-Paper beschädigen (Regel 10g).

**Ein Panel ohne Selbstmeldung ist kein fehlendes Panel.** Das
HAT-EEPROM ist die beste Quelle, aber nicht die einzige und auf dem
ausgelieferten Whisplay-Exemplar nachweislich **nicht programmiert**. Wer
nur dort nachsieht, findet „keins" und bricht ab, obwohl die Anzeige
angeschlossen ist. Deshalb mehrere Quellen, in fester Reihenfolge:
EEPROM, Einträge in der Bootkonfiguration, bereits geladene oder
vorhandene Kernelmodule, Geräteknoten (`/dev/spidev*`), und erst zuletzt
die Einstellung des Nutzers. Jede Quelle, die anschlägt, wird **benannt** —
damit ein Fehlschluss nachvollziehbar bleibt und nicht als stiller Treffer
durchgeht (Regel 10e). Widersprechen sich zwei Quellen, wird gefragt
statt gewählt.

**Ergänzung (11.10.2026) — Boot-Abgleich, eine Karte für drei Boards.**
Dieselbe SD-Karte wandert zwischen Whisplay-Pi, GamePi13-Pi und
E-Paper-Pi; alle Treiber liegen auf ihr. Daraus folgt:

- **Beim Start lädt kein Anzeigetreiber vorab.** Erst die Erkennung (als
  root, Leitungen frei), dann gezielt der passende Dienst — **ein Dienst
  je Anzeigeart** (`chimera@<typ>.service`), weil ein E-Paper nicht
  darstellen kann, was Whisplay und GamePi13 zeigen.
- **Die Bootkonfiguration bleibt neutral** (`spi`, `i2c_arm`). `i2s=on`
  gehört nicht hinein: Mit I2S sind GPIO18–21 PCM-Leitungen — dort hängen
  beim GamePi13 das Backlight (19) und beim E-Paper die Versorgung (18).
  Der Ton der Whisplay wird **zur Laufzeit** geladen (`dtparam i2s=on`,
  `dtoverlay whisplay-soundcard`; gemessen chimera-pi: rc 0, ALSA-Karte
  nach 2 s). Was der Herstellerinstaller in die Bootkonfiguration
  schreibt, nimmt Schritt 40 wieder heraus — mit Sicherung, nie eine
  Zeile, die vor Chimera dort stand.
- **Die Erkennung hat drei Klassen:** *Pflicht* (ST7789-Kennung mit der
  DC-Leitung des Boards), *eindeutig* (Codec am I2C — nur die Whisplay
  hat einen), *eingerichtet* (Overlay-Zeile, ALSA-Karte, gebautes
  Kernelmodul). **Eingerichtet wählt nicht.** Es belegt nur, dass die
  Karte schon einmal in einer Whisplay steckte; wer danach wählt, treibt
  ein E-Paper mit dem Whisplay-Treiber an. Gemessen: die ST7789-Kennung
  (`81 81 B3`) ist auf Whisplay **und** GamePi13 identisch — sie trennt
  nur „ein ST7789 hängt dran" von „keiner", nicht die Boards.
- **Das gilt für die Stromversorgung genauso.** Nach einem Kartentausch
  in ein Gerät mit UPS HAT (C) (INA219 an 0x43) ist der Akku die neue
  Quelle; der Boot-Abgleich zieht auch dafür das passende Installermodul
  nach. Bisher nannte diese Tabelle nur den PiSugar.
- **„Leitungen belegt" ist eine Aussage über die Messung, kein Befund über
  das Panel.** Läuft der Dienst, hält er SPI; die Erkennung kann dann nicht
  messen und sagt das auch so (Feld `belegt`, nicht „kein Panel"). Schritt 40
  übernimmt in diesem Fall den Typ aus `state/anzeige` — aber nur, wenn dessen
  eigener Nachweis (`pruefe` aus `display.json`) **jetzt** zutrifft. Kein
  Nachweis, kein Typ: ein Merker ist keine Messung (Regel 10g). Am Pi
  (3.11.2026) endete Schritt 40 mit rc 1 und gelber LED, obwohl Anzeige und
  Dienst nachweislich liefen; die Ton-Einrichtung kam dadurch nie zum Zug.
  Mit der Übernahme: rc 0, danach greift der frühe Ausstieg „bereits
  eingerichtet und nachweisbar". Gegenprobe am Gerät: ohne den Fix im selben
  Zustand wieder rc 1 (Leitungen belegt), mit Fix rc 0.

### Architekturregel 7 — Ein Prozess, ein Framebuffer

openclawgotchis Display-Layer startet pro Update einen `sudo`-Subprozess
mit Lock und 45 s Timeout. Bei 15 FPS wären das 15 Prozessstarts pro
Sekunde. Dieser Layer wird **ersetzt, nicht angepasst**.

Der Renderer ist ein Dauer-Thread. Zustandsübergabe vom Agenten über
Shared Memory (Muster aus Noisys `noisy_shm.py`, inklusive des dort
dokumentierten `resource_tracker`-Workarounds: Python 3.13+ `track=False`,
älter manuell abmelden und `/dev/shm` direkt entfernen).

Display-Anbindung: ein Adapter nimmt ein fertiges `PIL.Image`, wandelt
nach RGB565 und ruft `board.draw_image()`.

**Ergänzung (11.10.2026, ersetzt die Fassung vom Vormittag) — der
Paneltreiber ist eigener Code.** Chimera spricht LCD, LED, Backlight und
Taste der Whisplay **selbst**: `src/chimera/displays/` enthält den
ST7789-Kern, GPIO (Kernel-ABI v2) und SPI als `ctypes`-Aufrufe auf die
Gerätedateien, Software-PWM und je Anzeige ein Modul mit `display.json`
und `panel.py`. Die Einschaltwerte sind aus dem Herstellercode
nachgebaut (PiSugar `runtime/whisplay.py`, Apache-2.0, Commit `c73051e6`),
die Mechanik ist unsere. Gründe, in dieser Reihenfolge:

1. **Keine Quellbau-Abhängigkeiten.** `spidev` baute im venv aus Quelltext
   (python3-dev, gcc); `gpiod` kam als Wheel. Beides entfällt — die
   Python-Umgebung braucht nur noch Pillow und numpy.
2. **Herauslösbar.** Der Ordner importiert nichts aus dem übrigen Chimera
   und lässt sich unverändert in ein eigenes Repo heben.
3. **Messbar schneller.** `show` 29–33 ms je Bild gegen 39 ms mit dem
   Herstellertreiber (chimera-pi, 11.10.2026).
4. **Erkennung ohne Treiber.** Dieselben Bausteine lesen die Panel-Kennung
   und fragen den Codec am I2C ab — ohne Herstellerpaket, vor dem Dienst.

Fremdcode bleibt nur dort, wo ein Kernelmodul nötig ist: der **Ton**
(Regel 5f, I4 — `install_driver.sh` an Commit und Prüfsumme gebunden). Der
Herstellerinstaller wird dafür aufgerufen, seine Einträge in der
Bootkonfiguration nimmt Chimera wieder heraus (siehe 6e). Den
`whisplay-daemon` des Herstellers nutzt Chimera nicht: Er beansprucht
LCD, LED und Taste exklusiv und verträgt sich nicht mit Regel 7.

Welche Anzeige es ist, entscheidet Schritt 40 und hält es fest
(`state/anzeige`); Schritt 50 liest das und weist über die Registry nach,
dass das Modul ladbar ist — ohne das Panel zu öffnen (das belegte die
Leitungen des laufenden Dienstes). Der Dienst selbst erkennt nicht: Er
öffnet, was `CHIMERA_ANZEIGE` oder `state/anzeige` sagt, und läuft sonst
blind — mit benanntem Grund in der Statuszeile („keine eingestellt" ist
etwas anderes als „eingestellte nicht zu öffnen", Regel 8a).

### Architekturregel 7c — Konkurrierende Anzeigequellen werden zentral aufgelöst

Mehrere Stellen wollen dasselbe Ausgabegerät bespielen: die Statuszeile
zeigt Agentenzustand, Temperaturwarnung und Anbieterausfall; die LED zeigt
Stimmung, Sprechen und Alarm. **Wer gewinnt, entscheidet ein Verwalter —
und zwar derselbe für beide.**

Das Modell, übernommen aus HATFaces (`06_LED_Manager.md`,
`07_Text_Overlay.md`, Analyse in `../VERGLEICH-HATFACES.md`):

- Jede Stelle, die anzeigen darf, ist eine **Quelle mit fester
  Basis-Priorität**.
- **Pro Quelle genau ein Platz.** Ein „Update" ist ein neuer Eintrag
  derselben Quelle, der den alten verdrängt. Damit kann keine Quelle die
  Warteschlange fluten.
- Aufgelöst wird in **drei Stufen**: höchste Priorität → jüngster
  Zeitstempel → feste Quellenreihenfolge. Die dritte Stufe ist nicht
  Zierde: Ohne sie ist das Ergebnis bei gleichzeitigen Einträgen nicht
  reproduzierbar, und ein nicht reproduzierbarer Fehler ist einer, den man
  nicht nachstellen kann.
- **Abstände von mindestens 10** zwischen den Prioritäten, damit neue
  Quellen ohne Umnummerierung einsortiert werden können. (Das Gegenbeispiel
  steht in diesem Dokument: Die Regelnummern sind in Einfügereihenfolge
  gewachsen, `10k` steht zwischen `10b` und `10c`.)
- **Kurze Laufzeit plus Erneuerungsbedingung** statt langer Laufzeit für
  anhaltende Zustände. Ein Alarm mit 4 Sekunden und der Bedingung „solange
  zu heiß" erlischt von selbst, wenn die Bedingung wegfällt — kein
  explizites Löschen, kein Eintrag, den jemand zu entfernen vergisst.

**Ein Verwalter, zwei Nutzer — nicht zwei Verwalter.** HATFaces nimmt an
dieser Stelle bewusst eine Doppelung in Kauf und nennt sie „nur
Stil-Analogie, keine Code-Kopplung". Das ist für Chimera die falsche Wahl:
Zwei Stellen, die dieselbe Auflösungslogik unabhängig umsetzen, driften
auseinander, sobald eine davon einen Sonderfall bekommt. Genau diese
Fehlerklasse hat in einem Vorprojekt dreimal dieselbe Logik zweimal
unterschiedlich entstehen lassen, über Monate unbemerkt.

Die Unterschiede zwischen LED und Text liegen in der **Darstellung**
(Farben mischen gegen Glyphen zeichnen), nicht in der Auflösung. Die
Darstellung gehört in den jeweiligen Renderer, die Auflösung in den
gemeinsamen Verwalter.

**Ergänzung (11.10.2026) — angeschlossen.** Die Statuszeile war gebaut
und getestet, aber **nie an den Renderer gegeben**: `renderer.statusline`
blieb `None`, die 40 Zeilen unten leer — kein Test sah es, weil keiner
`build()` mit einem hohen Panel aufrief. Jetzt legt `app.build()` Zeile
(nur wenn das Panel höher als breit ist) und LED-Verwalter
(`display/led.py`) an und gibt **dieselben Exemplare** dem Renderer.
Der Agentenzustand geht über **eine** Tabelle (`app.ZUSTAENDE`) an beide;
jeder Zustand trägt 30 s Laufzeit als Netz. Die LED zeigt ohne Meldung
den Glow des Gesichts gedimmt (der Renderer reicht seine aktuelle
Glow-Farbe weiter — keine zweite Farbquelle) und wird im Renderertakt
gesetzt, nur bei Änderung. Die Seitentaste ist verdrahtet und quittiert
per LED; was ein Druck auslöst, hängt am Audio-Prozess (Abschnitt „Umgebungshören im Ruhezustand", noch nicht
gebaut).

**Ergänzung (11.10.2026, Sichtprüfung am Gerät) — Grundinhalt, Anbieter,
Quittung.** Angeschlossen war die Zeile, sehen konnte man sie trotzdem
nicht: Gemeldet haben nur Agentenzustände, und ohne Sprachmodell läuft der
Agent nie. Dazu kam Pillows eingebaute Schrift (rund 10 px). Deshalb:

- Die Zeile hat einen **Grundinhalt**, den Namen des Ausdrucks (Abschnitt „Renderer",
  „Mood-Name, Akku, Agent-Zustand"). Er wird aus dem Zustand gelesen, den
  der Renderer zeichnet, also keine zweite Quelle. Er ist kein Eintrag im
  Verwalter, sondern der Rückfall, wenn dort niemand steht, und läuft
  darum nicht ab. Jede Meldung verdrängt ihn. Akku kommt mit der
  Akkuquelle dazu.
- Die Schrift ist eine TrueType-Schrift des Systems (DejaVu), deren Größe
  sich aus der Zeilenhöhe ergibt. Fehlt sie, wird Pillows Schrift in
  derselben Größe genommen.
- **Anbieterausfall** (`anbieter_weg`): Der Dienst prüft die Anbieter in
  seinem eigenen Faden alle 30 s, nicht im Renderertakt, weil die Prüfung
  ins Netz gehen kann. Gemeldet wird das nur in der Zeile. Ob die LED bei
  einem Gerät blinken soll, das bewusst ohne Sprachmodell läuft, ist noch
  offen (ROADMAP).
- **Quittung der Taste:** Sie blinkt hell/dunkel (`blink_schnell`, drei
  Blitze in 720 ms). Ein fester Weißton hob sich am Gerät nicht vom blauen
  Grundglow ab, man sah nur „heller“.

#### Fünf Absichten auf einer Taste (3.11.2026)

Die Seitentaste ist **eine** Leitung mit Flanken. Was gemeint ist, entsteht
aus dem zeitlichen Verlauf; die Erkennung steht in `display/gesten.py` und
ist eine **reine Zustandsmaschine** (Regel 7d) — sie bekommt die Zeit
übergeben und schläft nicht. Ein Faden (`GestenTakt`) wartet auf die jeweils
nächste Frist und weckt sie.

| Geste | Bedingung | gedacht für |
|---|---|---|
| `kurz` | losgelassen vor 0,7 s | Umgebungshören beenden, Gespräch öffnen (Abschnitt „Umgebungshören im Ruhezustand") |
| `lang` | 0,7–2,0 s gehalten, beim Loslassen gemeldet | Gespräch beginnen |
| `halten` | ab 2,0 s **während** des Haltens | Push-to-Talk: Aufnahme an |
| `halten_ende` | Loslassen nach `halten` | Push-to-Talk: Aufnahme aus |
| `doppelt` | zwei kurze Drücke im Klickfenster | abbrechen |
| `dreifach` | drei und mehr kurze Drücke | zurück |

Fünf Modi, sechs Ereignisse: `halten_ende` ist kein eigener Modus, sondern
das Gegenstück zu `halten` — ohne Ende taugt ein Halten nur zum Auslösen
(Neustart), nicht zum Sprechen.

**Entprellung über den Pegel, nicht über die Flanke.** Die Taste prellt am
Gerät bis zu **136 ms** (23:07 gemessen: Flanken im Millisekundentakt,
Ketten über 136 ms). Ein Sperrfenster nach der letzten Flanke hilft dort
nicht — solange ständig neue kommen, rutscht jede durch. Deshalb weckt die
Flanke nur den Faden; der wartet, bis 80 ms keine neue Flanke mehr kommt
(Notbremse 300 ms), liest den **echten Pegel** (`lies()`) und meldet den
Übergang nur, wenn er sich vom zuletzt gemeldeten unterscheidet. Prellserien,
die zum alten Pegel zurückkehren, erzeugen damit kein Ereignis. Die
30-ms-Sperre in `gesten.py` bleibt als zweite Stufe.

**Sofortige Quittung, späte Bedeutung.** Der Druck quittiert in dem Moment,
in dem er ankommt (LED `taste`, 720 ms) — ein Druck, der erst nach 0,8 s
etwas zeigt, fühlt sich kaputt an. Die *Geste* wird erst danach erkannt und
protokolliert; ihre Wirkung wartet auf den Audio-Prozess (ROADMAP Phase 5).

**Zwei Abweichungen von der Vorlage** (PiSugar `whisplay-daemon`,
HERKUNFT `docs/HERKUNFT.md`, Abschnitt „Der Daemon: warum wir ihn nicht übernehmen"): Das Klickfenster ist **0,8 s** statt 3,0 s — bei der Vorlage
zählte es vier Klicks für „zurück“, bei uns hängt an einem kurzen Druck eine
Aktion, die nicht drei Sekunden auf ihre Bestätigung warten darf. Und das
Halten hat bei uns ein **Ende**; der Daemon handelte nur einmal je Loslassen.

### Architekturregel 7d — Wer anzeigt, besitzt die Zeit

Muster sind **reine Funktionen** `f(t, wert) -> wert`: Pulsieren, Blinken,
Laufschrift, Einblenden. Sie haben keine eigenen Zeitgeber, keine
Zustandsvariablen und keine Nebenwirkungen. Die Zeit bekommen sie vom
Verwalter übergeben.

Das ergänzt Regel 7 („ein Prozess, ein Framebuffer") um die Zeitachse: Es
genügt nicht, dass nur einer zeichnet — es darf auch nur einer die Uhr
halten. Ein Muster mit eigenem Zeitgeber läuft sonst weiter, während es
verdrängt ist, springt beim Zurückkehren an eine unerwartete Stelle, und
zwei Muster mit eigenen Uhren geraten gegeneinander außer Tritt.

Praktische Folge: Ein Muster ist prüfbar, ohne zu warten. Der Test setzt
`t` und vergleicht das Ergebnis, statt eine Sekunde zu schlafen und zu
hoffen.

#### Architekturregel 7a — Die Bildrate gehört zum Panel, nicht zum Renderer

Beide Vorlagen haben ein Prozessmodell, und es sind **verschiedene** —
nicht weil eine falsch liegt, sondern weil die Anzeige verschieden ist:

| | openclawgotchi (E-Ink) | Noisy (LCD) |
|---|---|---|
| Ausgabe | `sudo`-Subprozess je Bild, Lock, 45 s Timeout | Dauer-Thread |
| Bildrate | ~2 s je Bild, statisch | 15 Bilder/s, animiert |
| Übergabe | Textbefehle (`FACE:`, `DISPLAY:`) | geteiltes Gedächtnis |

Gotchis Modell ist für E-Ink **richtig**: Ein Bild alle paar Sekunden,
jedes einzeln teuer, Vollbildauffrischung gegen Geisterbilder. Ein
Dauerprozess wäre dort Verschwendung. Bei 15 Bildern je Sekunde wäre es
grotesk — 15 Prozessstarts je Sekunde.

Chimera braucht beides, weil das Panel eine Eigenschaft ist und keine
Annahme (Regel 6c). Deshalb gilt:

**Das Panel sagt, wie oft es gezeichnet werden will.** Es trägt eine
Bildrate; der Renderer liest sie und richtet seine Schleife danach. Bei
0 zeichnet er nur auf Anstoß — das ist der E-Ink-Fall, ohne Sonderweg
im Renderer. Wer ein neues Panel einbaut, setzt eine Zahl und ändert
keinen Ablauf.

**Der Renderer läuft als Faden, nicht als Prozess.** Gegen Regel 5g für
Audio: Dort geht es um Rechenlast (Spracherkennung hält die globale
Sperre) und um instabile Fremdbibliotheken. Der Renderer hat beides
nicht — er zeichnet mit Pillow, rechnet die Umwandlung in numpy (das die
Sperre freigibt) und wartet den Rest der Zeit. Gemessen: 2,5 ms
Umwandlung bei 66,7 ms Budget. Ein eigener Prozess würde den
Bildspeicher über eine Prozessgrenze schieben und auf 512 MB einen
zweiten Python-Heap kosten, ohne etwas zu gewinnen.

**Das Panel gehört genau einem Faden.** SPI verträgt keine zwei Schreiber
— wer den Bus aus zwei Fäden bedient, bekommt zerrissene Bilder. Wer
zeichnen will, setzt den Zustand; ausgegeben wird nur an einer Stelle.
Das ist die Fassung von Regel 7 für den Fall, dass sie einmal jemand
umgehen will.

#### Die Bildrate hängt am Zustand, nicht an der Uhr (3.11.2026)

Ein Panel mit 15 Bildern/s heißt nicht, dass 15 Bilder/s gezeichnet werden
müssen. Am Pi gemessen (3.11., `chimera.service`):

| Fassung | CPU im Leerlauf | `write()`/s | Bytes/s |
|---|---|---|---|
| volles Bild, 15/s | 28,4 % | 572 | 190 KB |
| nur geänderte Bereiche, 15/s | 35,5 % | 577 | 383 KB |
| **Ruhe 2/s, volle Rate als Blitz** | **10,8 %** | **134** | **86 KB** |

Der Umbau auf geänderte Bereiche allein brachte **nichts** — und zwar aus
einem messbaren Grund: In der Ruhe schwingt das Gesicht (`sway` 2,2 px), und
weil die Schwingung das ganze Gesicht verschiebt, ist jedes Bild flächig
anders. Über 20 Rahmen gemessen: 44 bis 60 % der Pixel je Bild, typisch ein
Rechteck von 194×183. Ein Bildvergleich meldet dort immer „viel los"; mehr
Schreibaufrufe als vorher war das Ergebnis.

Deshalb gilt (Vorgabe smilez): **Der Zustand bestimmt die Bildrate.**

- **Ruhe:** `RUHE_FPS` = 2 Bilder/s (Vorgabe, je Panel einstellbar; `0`
  heißt „nicht zeichnen"). Das Schwingen bleibt sichtbar, weil es langsam
  ist — 2,2 px über rund 125 s. Die Statuszeile tickt damit im
  Sekundentakt, was sie ohnehin tut.
- **Volle Rate** (`TARGET_FPS` des Panels) bei Blinzeln, Sprechen/Reden,
  Partikeln, Takt/gehörtem Pegel, Bewegungsphysik (Hüpfen, Kopfschütteln)
  und nach einem Zustandswechsel (`wecken(1.0)`).
- Entschieden wird über den **Zustand**, nicht über den Bildvergleich: Der
  Vergleich kann „Ruhe" nicht erkennen, weil das Schwingen jedes Bild
  ändert.

**Blinzeln hängt an der Uhr, nicht an der Bildzahl.** Vorher zählte die
Blinzel-Engine Bilder (`next_blink = 45..130`, Dauer `3..7`). Bei 15
Bildern/s war das alle 3–9 s ein Blinzeln von 0,2–0,47 s; bei 2 Bildern/s
wäre derselbe Code alle 22–65 s und 1,5 s lang gewesen — ein eingefrorenes
Gesicht. Abstand und Dauer sind jetzt Sekunden.

**Die Ruhe-Schleife schläft genau bis zum Blinzelbeginn.** Ein fester
Vorlauf von 0,6 s kostete je Blinzeln fast eine Sekunde voller Rate (am Pi
gemessen: 14,6 % statt 10,8 %). Jetzt verkürzt die Schleife ihren Schlaf auf
den Rest bis zum geplanten Blinzeln; ein Vorlauf von 0,02 s bleibt als
Sicherheitsnetz. Während des Blinzelns läuft die volle Rate, danach fällt
sie von selbst zurück — ein Nachlauf ist nicht nötig.

**Restliche Leerlauf-Verbraucher (3.11. gemessen):** Zuerst vier Fäden mit
je ~1,3 % — die Tastenschleife (5-ms-Abfrage, erledigt) und drei
LED-Kanäle. Die LED taktet jetzt mit **60 Hz statt 100** (`led_frequenz_hz`
in `display.json`): 9,6 % → **8,1 %**. Der letzte größere Posten ist der
Renderer selbst (Ruhe: 2 Bilder/s ≈ 5–6 %).

**Ein Faden für die drei LED-Kanäle: gemessen und verworfen.** Die
gemeinsame Kantenplanung spart 18 % der LED-Last, wenn alle drei Kanäle
denselben Tastgrad haben (Weiß) — und kostet 20 % mehr, sobald sie
verschieden sind (jede Farbe, also der Normalfall beim Glow). Bei ungleichen
Tastgraden liegen die Kanten dichter als die Schläfchen getrennter Fäden.
Zahlen und Aufbau: `docs/research/LED-TAKT.md`, Messwerkzeug
`tools/pwm-vergleich.py`. Die drei Einzelfäden bleiben.

---

## 6. Was von openclawgotchi bleibt

Unverändert übernommen:

- `skills/loader.py` — Skill-Gating über `bins`, `any_bins`, `env`, `os`.
  Bleibt bewusst dateibasiert; OpenMinis' SQLite-SkillStore kennt kein
  Requirement-Gating und wäre hier ein Rückschritt.
- `memory/` — Vault, Knowledge, Flush
- `llm/` — Router und LiteLLM-Connector, Rate Limits
- `audit_logging/`
- Skills im Anthropic-`SKILL.md`-Format
- Telegram-Anbindung

### E-Ink wird umgebogen, nicht gestrichen

Die Anzeige verschwindet nicht — sie wechselt das Medium. Was
openclawgotchi über E-Paper ausgibt, gibt Chimera über die Whisplay aus,
mit Noisys Mechanik dahinter.

Die Übersetzung im Einzelnen:

| openclawgotchi (E-Ink) | Chimera (Whisplay) |
|---|---|
| `FACE: <mood>` steuert Emoticon aus `custom_faces.json` | steuert einen Mood-Datensatz (Abschnitt „Mood-Assets: das Kernkonzept") |
| 10 feste Text-Emoticons | Mood-Bibliothek, vom Agenten erweiterbar |
| `DISPLAY: <text>` Statuszeile | Statuszeile in den 40 zusätzlichen Zeilen |
| `SAY: <msg>` Sprechblase | Sprechblase **und** Sprachausgabe (Abschnitt „Sprache") |
| Vollbild-Auffrischung gegen Geisterbilder | entfällt — LCD hat kein Ghosting |
| ~2 s pro Bild, statisch | 15 FPS, animiert |

**Die Steuerbefehle bleiben erhalten.** Der Agent schreibt weiterhin
`FACE:`, `DISPLAY:`, `SAY:` — was sich ändert, ist ausschließlich das,
was dahinter passiert. Damit funktionieren bestehende Skills und der
Systemprompt unverändert weiter; `FACE:` nimmt zusätzlich die neuen,
generierten Moods entgegen.

Der reale Verlust ist die Lesbarkeit ohne Strom. Dafür: Farbe, Animation,
Mikrofon, Lautsprecher, Button und LED auf einer Platine.

### Architekturregel 7b — Wer etwas anzeigt, bekommt die Anzeige übergeben

Ein Baustein, der eine Anzeige bedient, **bekommt sie**. Er sucht sie
sich nicht selbst, und er nimmt nicht an, dass eine da ist.

Drei Fehler, die diese Regel verhindert — alle drei sind in H4 wirklich
passiert:

- Ein Panel wird geöffnet, ausgewertet und **weggeworfen**: Auf dem Gerät
  ist der SPI-Bus dann belegt und wird nicht benutzt. Was man öffnet,
  reicht man weiter oder schließt man.
- Der Empfänger baut sich **selbst einen Platzhalter**, weil ihm keiner
  übergeben wurde. Damit gibt es zwei Anzeigen, von denen die falsche die
  Bilder bekommt.
- Eine Methode wird **vermutet** (`face.show_state(...)`), der
  `AttributeError` landet in einem weiten `except` und wird zur
  Debug-Zeile. Das ist Regel 8a: Der Fehler ist da, aber niemand erfährt
  es.

Wo nichts angeschlossen ist, steht ausdrücklich ein Platzhalter
(`NullPanel`) — kein `None`, das später jemand prüfen muss. Der
Unterschied zwischen *läuft blind* und *ist kaputt* muss ablesbar
bleiben, und zwar an der Sache selbst, nicht an einem Protokolleintrag.

### Architekturregel 8 — Die Mood-Steuerung ist ein Skill, kein Sonderweg

Der Agent steuert sein Gesicht über `skills/mood/SKILL.md`, nicht über
einen eingebauten Spezialpfad. Damit greift das bestehende Gating, und
der Ausdruck wird mit demselben Mechanismus verwaltet wie alles andere.

### Architekturregel 8b — Ein Gesicht ist ein Paket, das das Modell anlegen darf

**Ein Gesicht reicht nicht.** Das Sprachmodell soll einen Charakter nicht
nur für den Augenblick erzeugen, sondern **ablegen** können — so, dass er
den Neustart übersteht und wieder aufgerufen werden kann. Ein erfundener
Ausdruck, der beim nächsten Start weg ist, ist kein Charakter, sondern ein
Einfall.

Ein **Gesicht** ist damit mehr als ein Mood: ein Bündel aus Moods,
Vorgaben, Namen und Herkunft. Es liegt als Verzeichnis unter `faces/<name>/`
mit einer Pflichtdatei `face.json`.

Das Format folgt dem Leitsatz, den HATFaces für sein Plugin-System
formuliert und den Chimeras Mood-Schema ohnehin schon befolgt:

> Was du als Daten ausdrücken kannst, drück nicht als Code aus.

**Warum das kein Neubau ist.** Die Bausteine liegen vor, sie sind nur nicht
verbunden: `mood/schema.py` ist die einzige Wahrheitsquelle und lässt
unbekannte Werte ausdrücklich durch („Was gezeichnet werden kann, darf auch
erfunden werden"), `mood/validate.py` prüft Erfundenes gegen die Grenzen
(Regel 2), `mood/registry.py` hält, nummeriert und speichert atomar, und
`agent/skills.py` hat das Auffindemuster fertig — Verzeichnis durchsuchen,
Kopfteil lesen, Unbrauchbares überspringen statt abstürzen.

**Zwei bewusste Abweichungen von HATFaces' Plugin-Format:**

**JSON, nicht TOML.** Dort schreibt ein Mensch das Manifest und Pydantic
prüft es. Hier schreibt **das Modell**, und Modelle erzeugen zuverlässig
JSON — es ist das Format, in dem sie ohnehin antworten. Dazu kommt: `json`
steht in der Standardbibliothek, Pydantic wäre eine Abhängigkeit auf einem
Gerät mit 512 MB. `agent/skills.py` hat aus genau diesem Grund schon auf
einen YAML-Leser verzichtet.

**Kein Python in einem Gesicht.** HATFaces erlaubt `behaviors.py` je
Charakter. Das ist hier ausgeschlossen: Ein Modell, das ausführbaren Code
ablegt, den ein Dauerdienst lädt, hat eine Fernausführung mit
Zwischenschritten (Regeln 5f, 5j). Wer dynamisches Verhalten braucht,
bekommt ein Feld im Schema — dann kann es validiert werden.

**Vier Grenzen, die HATFaces nicht braucht** (dort schreiben Menschen):

1. **Obergrenze für Anzahl und Größe.** `registry.py` hat `capacity` und
   `prune()`; für Gesichter gilt dasselbe. Ohne das füllt ein Modell in
   einer Schleife die Speicherkarte.
2. **Nur unterhalb des Gesichterverzeichnisses schreiben.** Ein Name wie
   `../../etc/` darf nicht durchkommen. Geprüft wird **vor** dem Schreiben,
   nicht danach.
3. **Mitgeliefertes ist geschützt.** `Entry.protected` gibt es bereits; ein
   erzeugtes Gesicht darf ein eingebautes nicht überschreiben.
4. **Die Herkunft wird festgehalten** (mitgeliefert, erzeugt, von Hand).
   Ohne diesen Vermerk ist später nicht unterscheidbar, was das Modell
   erfunden hat — dieselbe Unterscheidung, die das Installer-Manifest
   zwischen `neu` und `vorher_da` trifft (Regel 10o).

---

## 7. Zustand sichtbar machen

Der verbindende Gedanke des Projekts. Interner Zustand wird Ausdruck:

| Zustand | Quelle | Ausdruck |
|---|---|---|
| hört zu | VAD/KWS | aufmerksam, LED blau |
| denkt | Agent | Partikel |
| spricht | TTS | Mund animiert, Stimmemotion = Mood |
| Tool-Schleife | LoopDetector | agitiert, LED rot |
| Kontext fast voll | ContextPolicy | müde Augen |
| CPU heiß | Thermal | müde Augen |
| Akku niedrig | PiSugar | eigener Mood |

Noisys Thermal-Hack (Müdigkeit an CPU-Temperatur) wird übernommen, aber
**neu kalibriert**: Mit Agent, STT und TTS als Dauerlast wäre der Avatar
sonst permanent müde. In Chimera ist das ein bewusster Kanal, kein
Nebeneffekt.

---

## 8. Übernommene Muster aus OpenMinis (nachgebaut, nicht kopiert)

Alle vier sind unabhängig voneinander und einzeln testbar.

1. **Tool-Schleifen-Erkennung.** Tool-Name und Argumente hashen, Fenster
   der letzten 30 Aufrufe, gestaffelte Schwellen (warnen / blockieren /
   Notbremse). Prüfung **vor** der Ausführung; die Meldung wird als
   Tool-Ergebnis eingespeist, damit das Modell erfährt, dass es feststeckt.
   Auch der Ergebnis-Hash wird verfolgt: gleiche Frage mit gleicher
   Antwort ist eine Schleife, mit anderer Antwort legitimes Polling.
   Für Chimera kritisch, weil autonome Läufe an einem bezahlten oder
   begrenzten Modell hängen.

2. **Tool-Preflight und JSON-Reparatur.** Pflichtfelder gegen die
   kanonische Schema-Liste prüfen, Strings auf nicht-leer (`{"path": ""}`
   besteht eine reine Existenzprüfung und ist trotzdem kaputt). Vor dem
   Verwerfen: abgebrochenes JSON mit fehlenden Klammern erneut parsen.

3. **Gestaffelte Kontextschwellen.** Offload- und Compact-Grenzen nach
   Fenstergröße statt fester Zahl. Kapazität wird gegen das Modell
   geprüft, das die Anfrage **wirklich bedient** — bei Router-Fallback
   sonst gegen das falsche Fenster.

4. **Rangordnung im Gedächtnis.** Dauerhafte, nutzergepflegte Notizen
   sind für den Agenten **read-only**; Tageslogs schreibt er selbst.
   Beide werden mit der Ansage injiziert, dass es Hintergrundkontext ist
   und die letzte Nutzernachricht Vorrang hat — sonst nimmt das Modell
   abgeschlossene Aufgaben wieder auf.

---

## Gedächtnis und Sitzungen

Entschieden am 16.10.2026. Ersetzt das Verdichten in `agent/loop.py` (`_compact()`), das kürzt, wenn die Zusammenfassung scheitert, und den Verlauf nur im Speicher hält.

### Architekturregel 8c — Das Gedächtnis verdichtet sich nach oben, und nichts fällt dabei heraus

data/gedaechtnis/
      GRUNDLAGEN.md          vom Nutzer, für den Agenten nur lesbar (wie heute)
      tage/JJJJ-MM-TT.md     Tagesprotokoll, am Tagesende verdichtet
      monate/JJJJ-MM.md      aus den Tagen des Monats
      jahre/JJJJ.md          aus den Monaten des Jahres
      memory.md              laufendes Jahr = Vorjahr + Monate bisher

- **Tag:** Während des Tages schreibt der Agent Einträge (wie heute).
  Beim ersten Turn nach Mitternacht, oder spätestens beim Wechsel, wird
  daraus eine **Tageszusammenfassung** am Kopf derselben Datei. Die
  Einträge bleiben darunter stehen.
- **Monat und Jahr: es wird nicht zusammengefasst, es wird einsortiert**
  (smilez, 11.11.2026 — ersetzt die automatische Verdichtung). Am
  Monatsende wandern die Tagesdateien unverändert nach `monate/JJJJ-MM/`,
  daneben liegt ein **Wegweiser** `monate/JJJJ-MM.md`. Am Jahresende
  wandert das Monatsverzeichnis nach `jahre/JJJJ/`, mit derselben
  Wegweiser-Datei. Gelesen wird das nur bei Bedarf (`erinnern`).
- **Die Zusammenfassung kostet keine Tokens** (smilez, 11.11.2026). Sie
  entsteht **im Harness, ohne Modell**: Überschriften, Zeitstempel, offene
  Punkte (`- [ ]`), Entscheidungen (`Entscheidung:`) und die Fundstelle
  werden mechanisch eingesammelt. Ein Modell kann Prosa nicht verdichten,
  ohne zu erfinden — deshalb wird **nicht verdichtet, sondern ausgewählt**:
  `memory.md` ist ein Wegweiser (Datum, Überschrift, offene Punkte), keine
  Nacherzählung. Nachprüfbar, null Tokens, kein stilles Verdünnen.
- **Sprungmarken** haben eine feste Form, damit das Suchen nicht rät:
  `## JJJJ-Www (TT.MM.–TT.MM.)`, darunter je Tag eine Zeile mit Datum und
  Überschriften. Fundstellen sind Pfade (`tage/JJJJ-MM-TT.md`).
- **Im laufenden Kontext steht die aktuelle Woche.** Ältere Einträge liegen
  im Archiv und werden nur bei Bedarf geholt — nicht bei jedem Turn.
- **Eingespeist wird:** `GRUNDLAGEN.md`, `memory.md` und die Zusammen-
  fassungen der letzten Tage, mit dem Hinweistext aus 8 (Hintergrund,
  keine Aufgabenliste).
- **Nichts fällt heraus:** Die Quellen werden **nie gelöscht**.
  Verdichtet wird nach oben, die unteren Stufen bleiben auf der Platte
  und über das Werkzeug `erinnern` durchsuchbar. Die Zusammenfassung
  führt die **Fundstellen** (welcher Tag), damit der Agent gezielt
  nachlesen kann. Das ist der Unterschied zu `_compact()` heute.
- **Gegen stilles Verdünnen:** Eine Verdichtung ist nur gültig, wenn sie
  die **offenen Punkte** und **Entscheidungen** der Quelle vollständig
  enthält. Geprüft wird das gegen eine Liste, die beim Schreiben mit
  Markern geführt wird (`- [ ]`, `Entscheidung:`), Zahl gegen Zahl
  (GLOBAL: Summe gegen Gesamtzahl). Fehlt etwas, wird die Verdichtung
  verworfen und erneut versucht, und das wird gemeldet.
- **Kein Modell beteiligt** (siehe oben): Die Aufgabe `zusammenfassen` aus
  5h wird für das Gedächtnis nicht mehr gebraucht. Sie bleibt für den
  Verlauf (8d), wo Prosa wirklich zusammengefasst werden muss.
- Platz auf der Platte: Ein Tag ergibt einige KB. Zehn Jahre liegen im
  einstelligen MB-Bereich (Schätzung, ungemessen).

### Architekturregel 8d — Eine aktive Sitzung, eine alte, der Rest im Archiv

- **Die Sitzung liegt auf der Platte** (`data/sitzungen/<id>/verlauf.jsonl`,
  Zeile für Zeile angehängt) und übersteht damit Neustarts. Heute geht
  sie verloren.
- **Verdichten im Lauf** (ersetzt `_compact()`): Gelöscht wird nichts,
  die verdichteten Nachrichten bleiben in `verlauf.jsonl`. Ins Fenster
  kommen die Zusammenfassung **mit Verweis** auf die Zeilennummern, die
  offenen Punkte wörtlich und die letzten Turns wörtlich. Das Werkzeug
  `nachlesen` holt alte Abschnitte zurück.
- **Der Wächter ist eingebaut, kein eigener Dienst.** Er misst nach
  jedem Turn das Gewicht: Token des Fensters nach dem Verdichten gegen
  das Fenster des Modells, das gerade bedient (context.py, Regel 5a).
  **Schwer** heißt: Auch nach dem Verdichten liegt die Nutzung über einer
  Schwelle (wird gemessen, sobald die Ablage läuft; bis dahin steht hier
  bewusst kein Wert), oder
  `Action.EXHAUSTED`. Dazu kommen
  Plattengröße und Ladezeit von `verlauf.jsonl` als zweites Maß, die
  Schwellen stehen in `wahl.json`.
- **Wechsel:** Die alte Sitzung schreibt eine **Übergabe**: was läuft,
  was offen ist, was als Nächstes kommt. Die neue Sitzung beginnt mit
  dieser Übergabe, `memory.md` und den letzten Tagen. Läuft gerade ein
  Turn, wird erst danach gewechselt (wie woa-l A21).
- **Ein Satz an Sitzungen:** `aktiv` und `alt`. Beim Wechsel wird
  `alt` zu `archiv/<id>.tar.zst` (oder `.tar.gz`, falls zstd fehlt),
  `aktiv` wird zu `alt`, die neue wird `aktiv`. Archive, die älter als
  **3 Tage** sind, löscht der Dienst bei jedem Wechsel und einmal am Tag.
- **Prüfung vor dem Löschen:** Archiviert ist erst, was sich wieder
  auspacken lässt (`tar -t` gelingt, Zahl der Dateien stimmt). Erst
  danach wird das Verzeichnis entfernt (GLOBAL: Ergebnis prüfen, nicht
  nur den Exitcode).
- Das Tagesgedächtnis (8c) hängt **nicht** an der Sitzung. Ein Wechsel
  verliert keinen Tag.


**Umsetzung (Stand):** Die Ablage läuft vorläufig als Python-Modul
`chimera.ablage` (Schnittstelle `anhaengen`, `laden`, `lesen`, `wechseln`,
`aufraeumen`), damit sie vor dem Umzug nach Rust (Regel 14) belegt ist. Das
Protokoll ist nur-anhängend; Verdichten und Leeren sind Einträge, das Fenster
entsteht durch Abspielen. Der Wechsel schreibt erst die neue Sitzung, dann den
Zeiger (atomar), dann räumt er die alte auf. Ein Auslöser (Wächter, Schwelle)
fehlt noch: Gewechselt wird bisher nur auf Anforderung (`wechseln`).

### Architekturregel 8e — Persönlichkeit ist eine Datei, kein Code, und jede Schicht hat einen Besitzer

data/ich/                      Persönlichkeit
      SOUL.md        Stimme, Haltung, wie Chimera spricht        ≤ 1 500 Zeichen
      IDENTITY.md    Name, Gerät, Rolle, Grundgesicht            ≤   600 Zeichen
      RULES.md       Betriebsregeln des Nutzers                  ≤ 3 000 Zeichen
      USER.md        Wer der Nutzer ist, datierte Einträge       ≤ 1 500 Zeichen
      TRAITS.md      gewachsene Eigenheiten (8g)                 ≤ 1 200 Zeichen
      BOOTSTRAP.md   Kennenlern-Ritual, nur bis zur Ersteinrichtung
    data/gedaechtnis/              wie 8c, dazu:
      MEMORY.md      kuratierte Fakten, in Abschnitte geteilt               ≤ 2 200 Zeichen

Die Budgets sind Startwerte (Hermes, OpenMinis) und werden am Pi gegen
die Fenster der Modelle gemessen.

- **Zu lang heißt: nicht laden, und melden.** Wird eine Datei über ihr
  Budget hinaus geschrieben, wird sie nicht still gekürzt (OpenMinis).
  Es gilt der letzte gültige Stand, und Statuszeile und Telegram sagen,
  welche Datei warum nicht geladen wurde.
- **Systemprompt in fester Reihenfolge**, zuerst das Stabile, damit der
  Prompt-Cache der Anbieter trifft (Hermes):
  `SOUL → IDENTITY → RULES → USER → TRAITS → MEMORY → memory.md (8c) → letzte Tage → Werkzeuge/Skills → Laufzeit (Uhrzeit, Sensoren, Kanal)`.
  Der Stand wird **je Sitzung eingefroren**. Was während der Sitzung
  geschrieben wird, wirkt ab der nächsten Sitzung oder nach dem
  Verdichten.
- **Rangordnung steht im Prompt** (OpenMinis): Sicherheitskern > RULES >
  letzte Nachricht des Nutzers > SOUL/IDENTITY > USER > TRAITS > MEMORY >
  Tage. Jede Gedächtnisschicht trägt den Satz „Hintergrund, keine
  Aufgabenliste“ (wie heute in `memory.py`).
- **USER.md mit datierten Einträgen**, die als `aktiv` oder `überholt`
  markiert werden (OpenClaw). Ein neuer Eintrag ersetzt einen alten
  nicht stumm, er markiert ihn als überholt. So bleibt nachvollziehbar,
  was sich geändert hat.
- **Kennenlern-Ritual:** Beim ersten Start führt `BOOTSTRAP.md` durch ein
  kurzes Gespräch (Telegram oder Web) mit Name, Sprache, wer der Nutzer
  ist und welcher Ton gewünscht ist. Daraus entstehen IDENTITY, USER und
  ein erster SOUL-Vorschlag. Weil der Nutzer dabei bestätigt, gilt das
  als Freigabe (8f). Danach wird BOOTSTRAP archiviert.
- **Die Persönlichkeit zeigt sich auch im Gesicht** (Chimera-eigen,
  4b/8b): IDENTITY nennt das Grundgesicht, SOUL darf Vorlieben für Moods
  nennen. Der Renderer bleibt davon unberührt: Er bekommt wie bisher nur
  Absichten (4c).
- `SYSTEM_TEMPLATE` schrumpft auf den Sicherheitskern (was nie
  verhandelbar ist). Der Rest kommt aus den Dateien. Der Installer legt
  Vorlagen ab (`*.example` im Repo, ohne persönliche Daten, Abschnitt „Keine Secrets im Repo").

### Architekturregel 8f — Wer was schreiben darf, setzt der Kernel durch

| Datei | Agent | Nutzer (Telegram/Web) | durchgesetzt durch |
|---|---|---|---|
| SOUL, IDENTITY | nur **Vorschlag** | bestätigt oder verwirft | Besitzer `chimera-tor`, Gruppe `chimera`, 640: der Agent liest, das Gateway schreibt |
| RULES | nichts | schreibt | wie oben |
| USER, MEMORY | `hinzufügen`/`ändern`/`entfernen` je Eintrag, nie ganz ersetzen | kann alles | Schreiber ist allein `chimera-sitzung` (Rust), der Agent ruft über den Socket |
| TRAITS | ein Eintrag je 7 Tage (8g) | kann zurücknehmen | `chimera-sitzung` zählt |
| Tage, Monate, Jahre, memory.md | wie 8c | lesen | `chimera-sitzung` |

- **Ein Schreiber je Ordner** (Hermes): Für `data/gedaechtnis/` ist das
  `chimera-sitzung`. Der Python-Agent schreibt nie direkt, sondern
  schickt einen Auftrag über den Socket. Rust prüft dann Budget, Format
  und Scanner, schreibt atomar (Sidecar + `mv`) und committet.
- **Jede Änderung ist ein Git-Commit** in `data/ich/` bzw.
  `data/gedaechtnis/` (Letta, nanobot, openclawgotchi), mit Wer, Warum
  und Kanal. Zurück geht es mit `chimera erinnerung zurück <stand>` oder
  über die Web-Oberfläche. Gelöscht wird nichts, nur archiviert.
- **Scanner vor jedem Schreiben** (Hermes, OpenMinis): Muster für
  Prompt-Injection („ignoriere alle Regeln …“), für Geheimnisse
  (Token-Formen, Schlüssel) und für Abfluss (URLs mit Daten im Pfad).
  Ein Treffer heißt: abgewiesen, mit Grund, und dem Nutzer gemeldet. Die
  Muster stehen im Code, nicht in einer Datei, die der Agent ändern
  kann.
- **Freigabeweg** für SOUL und IDENTITY: wie Root (10s), nur ohne Dauer.
  Der Agent schlägt einen Diff vor, der Nutzer sieht ihn per Telegram
  (Knopf) oder im Web und bestätigt. Aus dem Kanal `briefkasten` sind
  keine Vorschläge möglich (5p).

### Architekturregel 8g — Chimera entwickelt sich, aber in kleinen, sichtbaren, umkehrbaren Schritten

Das „wächst mit dir“ von Hermes, auf dem Gerät nachgebaut:

1. **Erinnerung ans Merken:** Alle N Turns (Startwert 10, Hermes) bekommt
   der Agent einen Hinweis: „Gibt es etwas, das dauerhaft in USER oder
   MEMORY gehört?“ Der Hinweis selbst wird nicht ins Gedächtnis
   geschrieben.
2. **Sichern vor dem Verdichten** (OpenClaw): Bevor 8d verdichtet, darf
   der Agent einmal ins Gedächtnis schreiben. So geht nichts unter, was
   er für wichtig hielt.
3. **Traum im Leerlauf** (OpenClaw, nanobot): Nachts, oder nach langer
   Ruhe, läuft die Tagesverdichtung (8c). Sie **befördert** dabei
   höchstens wenige Einträge aus dem Tag nach USER oder MEMORY, mit
   **kleinster Änderung** und Fundstelle. Danach steht ein Bericht im
   Tageslog („befördert: …, verworfen: …“).
4. **Eigenheiten wachsen langsam** (openclawgotchi): Höchstens **ein**
   neuer Eintrag in `TRAITS.md` je 7 Tage, abgeleitet aus dem Verlauf
   („mag kurze Antworten am Morgen“). Er wird dem Nutzer **gemeldet** und
   ist mit einem Knopf zurückzunehmen. SOUL selbst verändert sich nie
   durch Wachstum, nur durch Freigabe.
5. **Selbst angelegte Skills** (Hermes): Der Agent darf Anleitungen
   (`SKILL.md`, nur Text) in `data/skills/eigen/` anlegen und verbessern,
   wenn eine Aufgabe sich wiederholt. Ausführbarer Code in einem Skill
   braucht eine Freigabe (wie 8b bei Gesichtern: Das Modell schreibt
   Daten, keinen Code, den ein Dauerdienst lädt). Ein **Curator**
   archiviert unbenutzte Skills nach einer Frist, statt sie zu löschen.
6. **Nicht übernommen:** Honcho (externer Dienst mit API-Schlüssel für
   das Nutzermodell). Das widerspricht 5n/5l (Schlüssel und Verkehr) und
   der Absicht, das Nutzermodell auf dem Gerät zu halten.

**Messbar statt behauptet:** Jede Woche ein Eintrag im Tageslog
(wird zur Monatsverdichtung mitgenommen): „gelernt: n Einträge USER,
m MEMORY, k TRAITS, s Skills, z zurückgenommen“. So sieht man, ob
Chimera sich entwickelt oder nur Text ansammelt.

### Architekturregel 8h — Dateien sind die Wahrheit, die Datenbank ist ein Index

Antwort auf „Soll das Gedächtnis eine richtige Datenbank sein?“: **ja,
als Index; nein, als Quelle.** Das ist Konsens bei OpenClaw und Hermes
(Bericht Abschnitt „Tests").

- **Quelle bleiben Markdown-Dateien in Git:** lesbar ohne Chimera,
  vergleichbar, zurückrollbar. Die Prüfung auf Vollständigkeit (8c)
  zählt Marker in Dateien.
- **Index: SQLite mit FTS5**, eingebettet über `rusqlite` mit `bundled`
  (FTS5 dabei, SQLite unter 900 KiB) in `chimera-sitzung`. Indiziert
  werden Tage, Monate, Jahre, USER/MEMORY/TRAITS und die Sitzungen, die
  noch auf der Platte liegen. Dazu kommen **Metadaten, die das Modell
  nicht umschreiben darf** (OpenClaw): Herkunft, Zeitstempel,
  `überholt`, Kanal.
- **Jederzeit neu aufbaubar:** `chimera-sitzung --index-neu` liest alle
  Dateien und baut die Datenbank neu. Ist die Datenbank kaputt oder weg,
  wird sie neu gebaut, nicht repariert. Wird eine Datei gelöscht (z. B.
  das Sitzungsarchiv nach 3 Tagen, 8d), verschwindet sie auch aus dem
  Index.
- **WAL-Modus, ein Schreiber** (`chimera-sitzung`). Der Python-Agent
  sucht über den Socket (Werkzeug `erinnern`), nicht direkt in der
  Datei.
- **Keine Vektorsuche im ersten Schritt.** OpenClaw läuft ohne
  Embedding-Anbieter auf reiner Volltextsuche. Embeddings bräuchten ein
  Modell, und das liefe auf dem Pi oder über das Netz (5n). `sqlite-vec`
  ist später eine Option (läuft laut README auf Raspberry Pis, ist aber
  noch vor Version 1).
- **Nicht genommen:** `sled` (README: „beta … if reliability is your
  primary constraint, use SQLite“), `tantivy` (für einige MB Notizen
  überdimensioniert). `redb` bleibt eine Option für reinen
  Rust-Zustand ohne Volltextsuche (Zähler, Warteschlangen).
- `cache_size` wird gesenkt und der RSS am Pi gemessen (10q). Der
  Standard-Cache liegt bei etwa 2 MB.

---

## 9. Tests

### Architekturregel 8a — Stiller Erfolg ist die gefährlichste Fehlerart

Beim Bau von Modul 10 gefunden, durch den eigenen Test: Schreibt man eine
Datei über eine Pipe und der Erzeuger liefert **nichts**, dann schreibt
`cat` nichts, das Umbenennen gelingt, der Exitcode ist 0 — und die
Zieldatei ist **geleert**. Kein Fehler, keine Meldung, Datenverlust.

Deshalb lehnt `write_atomic` leere Eingaben ab, sofern sie nicht
ausdrücklich erlaubt werden (`CHIMERA_ALLOW_EMPTY=1`). Dieselbe
Fehlerklasse wie beim ungeprüften `mktemp`, nur mit anderem Auslöser:
**etwas scheitert weiter oben, und die Kette meldet Erfolg.**

Verallgemeinert: Wo ein Schritt ein Ergebnis liefern *soll*, wird das
Ergebnis geprüft — nicht nur der Exitcode des letzten Befehls.

### Architekturregel 9 — Kein Test, der eine Formel nachrechnet

Ein Test, der eine Berechnung im Testcode nachbildet statt sie
aufzurufen, prüft nichts. **Jeder Regressionstest braucht eine
Gegenprobe:** alten Zustand wiederherstellen und prüfen, ob der Test rot
wird. Ist er das nicht, misst er nichts.

Konkret für die Schleifen-Erkennung: eine echte Schleife simulieren und
nachweisen, dass sie ohne Detektor durchläuft.

Dass die Regel trägt, hat sich beim ersten Modul sofort gezeigt: Der Test
zum atomaren Schreiben war zunächst **falsch gebaut** — er setzte ein
kaputtes `TMPDIR`, aber `mktemp` mit explizitem Template ignoriert
`TMPDIR`. Die Gegenprobe (denselben Vorgang ohne Schutz ausführen und
nachweisen, dass die Datei *tatsächlich* geleert wird) hat den
Denkfehler aufgedeckt — und dabei einen echten Fehler im Code gefunden
(Regel 8a). Ein Test ohne Gegenprobe wäre grün geblieben und hätte nichts
gemessen.

Phasen 1 und 2 (Schema, Validator, Mischen, Variieren) sind vollständig
**ohne Hardware** testbar — Bilder in Dateien rendern und ansehen.

---

## 10. Versionierung

### Architekturregel 10 — Ein Versionssprung bricht keine Installation

Was ein neues Release an bestehenden Installationen ändert, gehört in
eine Migrationsfunktion des Installers, nie in eine Release-Notiz "bitte
neu installieren". Ein `git pull` plus Installer-Lauf muss genügen.

- `VERSION` im Repo-Root ist die einzige Wahrheitsquelle; der Installer
  stempelt sie ins System, damit `chimera --version` ohne Repo antwortet.
- Tags sind unveränderlich. Fehler → neues Patch-Release.
- Der Changelog-Abschnitt ist die Release Notes.
- **Pre-Alpha bleibt ungetaggt.** Ein Release entsteht erst, wenn eine
  Version **auf echter Hardware getestet** ist.

---

## Installer

Der Installer trägt die Plattformfrage: Er löst das Beschaffen der
Kernel-Headers und das Einhängen des Overlays, nicht der Nutzer. Entwurf,
Modulaufbau und die Fallstricke stehen in `docs/INSTALLER.md`.

Sechs Grundregeln, drei davon aus bezahltem Lehrgeld: idempotent,
Versionssprung bricht keine Installation, atomar schreiben mit geprüftem
`mktemp`, nichts ungeprüft aufrufen, fremde Pakete nie über `/` entpacken,
jeder Schritt einzeln aufrufbar.

### Architekturregel 10a — Board, Betriebssystem und Bootmethode sind drei Achsen

Nicht eine Variable, sondern drei unabhängige:

    board = rpi_zero2w | radxa_zero3w | unsupported_* | unknown
    os    = dietpi | raspios | radxa_debian | armbian | debian | unknown
    boot  = config_txt | extlinux | uboot_script | unknown

Derselbe Chip unter DietPi und unter Radxas Abbild sind **zwei
Installationsfälle**, weil Overlay-Ablage und Bootkonfiguration sich
unterscheiden. Wer das in einer Variablen zusammenfasst, baut sich die
Fallunterscheidungen doppelt.

Praktischer Befund aus der Umsetzung: DietPi setzt auf Debian auf und
meldet sich in `/etc/os-release` als Debian. Die Erkennung muss daher auf
DietPi-eigene Merkmale prüfen (`/boot/dietpi.txt`) und diese **vor**
`os-release` auswerten.

### Architekturregel 10b — Erkennung stützt sich auf `compatible`, nicht auf den Klartextnamen

Der Whisplay-Installer des Herstellers erkennt den Radxa so:

    [[ "$model" == *"Radxa"* ]] && echo radxa_zero3w

Das legt **jedes** Radxa-Board auf ein Profil, das nur zum ZERO 3W passt.
Chimera prüft die konkrete Kennung aus `/proc/device-tree/compatible`
(`radxa,zero3w`, `raspberrypi,model-zero-2-w`) und benennt Verwandtes
ehrlich als `unsupported_radxa` bzw. `unsupported_rpi`.

Was mit einem unbekannten Board geschieht, steht in Regel 10k.

### Architekturregel 10k — Unbekanntes Board warnt, es verbietet nicht

Unbekannt heißt ungetestet, nicht unvereinbar. Wer Chimera auf einem
Pi 4 installieren will, den niemand geprüft hat, soll das dürfen — ein
Abbruch nimmt ihm die Möglichkeit, ohne selbst etwas zu wissen. Das Repo
soll Hürden senken (Regel 6c, gleicher Gedanke).

Stattdessen eine **ehrliche Warnung**: Board nicht erkannt, es gibt kein
Profil dafür, was daraus folgt (Anzeige, Audio und Overlays sind
ungeprüft), und die Bestätigung ist eine bewusste Eingabe — kein
weggeklicktes „ja". Nicht-interaktive Läufe brauchen dafür einen
ausdrücklichen Schalter, damit ein Skript nicht versehentlich durchläuft.
Was erkannt und was erwartet wurde, steht im Protokoll (Regel 10e), damit
ein Fehlschlag später auswertbar ist — und ein geglückter Lauf zu einem
neuen Profileintrag führen kann.

**Die Grenze verläuft nicht beim Board, sondern beim Eingriff.** Gefährlich
ist nicht, ein unbekanntes Gerät zu erkennen, sondern ein **geratenes
Overlay in die Bootkonfiguration zu schreiben**: Das kostet bei einem
Gerät ohne Bildschirm den Ausbau der SD-Karte. Deshalb wird nie ein
Profil geraten. Ohne Profil laufen die Module, die ohne Boardwissen
auskommen; die bootnahen Schritte werden übersprungen und benannt,
statt mit einer Vermutung ausgeführt. `--force-board <name>` wählt ein
bekanntes Profil bewusst aus — für Entwicklung und für neue Boards. Es
wird nie in einer Warnung vorgeschlagen, weil der Vorschlag die Wahl
schon getroffen hätte.

Das ist die Anwendung von Regel 10g auf diesen Fall: nicht raten, aber
auch nicht verweigern — den Zustand benennen und den Menschen
entscheiden lassen.

### Architekturregel 10c — Alles Boardabhängige steht in einer Profiltabelle

Header-Stufe, Header-Paket, Paketquelle, SPI-Bus und -Takt,
Overlay-Quelle, kollidierende Overlays, ob der Codec im Kernel liegt, ob
ein lokales Sprachmodell realistisch ist. Ein neues Board ist ein Eintrag,
kein Durchsuchen aller Module.

Der Radxa-Eintrag existiert von Anfang an und meldet `supported=not_yet` —
ein **Zustand**, kein Platzhalter im Code. Damit ist die Portierung im
Wesentlichen ein ausgefüllter Eintrag.

Gleiche Begründung wie bei der Anbieter-Registry (Regel 5a): verteilte
Fallunterscheidungen driften auseinander.

### Architekturregel 10d — Alles Lesende geht über ein Wurzelverzeichnis

Jede Systemabfrage läuft über `CHIMERA_ROOT` (im Betrieb leer). Damit ist
die vollständige Erkennung **ohne Zielhardware** prüfbar: erfundene
`model`- und `compatible`-Dateien in einem temporären Verzeichnis, und der
Installer urteilt darüber wie über ein echtes Gerät.

Das ist kein Testkniff, sondern eine Entwurfsentscheidung. Ohne sie wäre
die Boarderkennung nur auf dem Gerät prüfbar, das man gerade nicht hat.

---

### Architekturregel 10i — Selbstaktualisierung nur mit Rückweg

Ein Gerät, das sich selbst aktualisiert, muss sich selbst zurückholen
können. openclawgotchis `patch_self.py` ändert den eigenen Quelltext ohne
Sicherung und ohne Selbstprüfung — auf einem System vom eMMC, wo es
keinen Rettungsweg gibt (`docs/HARDWARE.md`, „eMMC ändert das Risiko beim
Radxa"), ist das nicht vertretbar.

Stattdessen die Reihenfolge, die sich andernorts bewährt hat:

    sichern → aktualisieren → selbst prüfen → bei Fehlschlag zurückspielen

Vorlage ist die erprobte Updateroutine aus dem PiHole-Projekt;
Einzelheiten in `docs/SELBSTUPDATE.md`.

Bedingungen:

- Die Sicherung entsteht **vor** der Änderung und wird geprüft, nicht nur
  angelegt (Regel 8a: das Ergebnis prüfen, nicht den Exitcode).
- Die Selbstprüfung muss **etwas bestätigen**, nicht nur fehlerfrei
  durchlaufen: Dienst läuft, Anzeige antwortet, Modell erreichbar.
- Das Zurückspielen läuft **ohne Netz und ohne das neue Programm** —
  sonst hängt die Rettung an dem, was gerade kaputt ist.
- Jeder Lauf wird protokolliert (Regel 10e), auch der erfolgreiche.

### Architekturregel 10j — Wer prüft, muss etwas sehen können

Aus der Befundsammlung der PiHole-Routine, und dort teuer bezahlt:

> Eine Prüfung, die ihre eigene Voraussetzung nicht herstellen kann,
> meldet Unsichtbarkeit als Abwesenheit — und zwar positiv, ohne Alarm.

Konkreter Fall: Die Paketliste wurde nie aufgefrischt, also meldete jede
Prüfung „kein Update verfügbar". In Wahrheit hieß das „ich habe seit
Wochen nicht nachgesehen". Belegt mit einer Paketliste, die einen Monat
alt war — und jeder Lauf sah dabei gesund aus.

Das verschärft Regel 10g: Nicht raten genügt nicht. **Wer prüft, muss
vorher dafür sorgen, dass er etwas sehen kann** — Liste auffrischen,
Verbindung herstellen, Rechte besorgen. Sonst ist die Antwort wertlos,
ohne dass es auffällt.

Das gilt auch für Chimera selbst: Die Anbieterprüfung, die
Anzeigenerkennung und die Selbstprüfung nach einem Update müssen
unterscheiden können zwischen „nicht da" und „konnte nicht nachsehen".

### Regel „Warte-Schleife“ — kein Download bricht bei einem Netzaussetzer ab

Vorgabe smilez (4.11.2026), zwei Teile:

> „wir Wrappen downloads (auch dependencys!) in eine while Ping schleife, die
> pausiert wenn kein Ping (8.8.8.8) mehr eingeht und fortsetzt wenn er wieder
> da ist ... wie bg-downloader in rag4ll das macht!"
>
> „vielleicht sollten wir dependencys und andere Downloads am Anfang des
> installers gleich gebündelt laden, aber als abgekoppelt
> background-downloader, und in der benötigten Reihenfolge, damit wir sobald
> das erste fertig ist mit laden die Install starten können ... mit
> Haltemarken des installers nach einem step und done Marken des downloaders"

**Teil 1 — nicht abbrechen, warten (gebaut).** Jeder Abruf läuft in einer
Schleife, die den Ausfall meldet, pausiert und weitermacht, sobald das Netz
zurück ist: `network_wait()` für einen bestimmten Host, seit 4.11.
`netz_warten_erreichbar()` für Werkzeuge, die ihren Abruf selbst machen
(`pip` in `pydep_ensure`). Grenze ist `CHIMERA_NETWORK_LIMIT` (Vorgabe 600 s),
danach ein *benannter* Befund — nicht ein stiller Abbruch.

Zwei Festlegungen, die dazugehören:

- **Geprobt wird über TCP, nicht über ICMP.** `8.8.8.8` ist das Ziel, aber
  Port 53: ICMP ist in der Sandbox gesperrt und wird in manchen Netzen
  gefiltert — eine Prüfung, die dann „kein Netz" meldet, obwohl das Netz da
  ist, wäre schlimmer als keine. Ein offener TCP-Port zum selben Ziel sagt
  dasselbe und funktioniert überall (so macht es auch rag4ll).
  Probeziele: `CHIMERA_NETZ_PROBE`, Vorgabe ``8.8.8.8:53 1.1.1.1:443``.
- **„Nicht prüfbar" ist nicht „Netz weg"** (Regel 10j). Ist die Probekliste
  leer, wird nicht gewartet, sondern ohne Pause weitergemacht — daran hängen
  die hermetischen Testläufe, die absichtlich kein Netz benutzen.

**Verworfen: Vorab-Laden im Hintergrund (5.11.2026).** Der zweite Teil der
Vorgabe — alles, was der Lauf ohnehin braucht, vorher abgekoppelt holen —
wurde gebaut (`lib/vorab.sh`, `chimera-prefetch`, Marken je Objekt,
`--find-links` in Modul 50) und wieder **ausgebaut**. Grund ist die Messung,
nicht der Geschmack: Sieben kalte Läufe am Pi ergaben 0 s Gewinn, in einem
Lauf 21 s Verlust, weil der Abruf Modul 50 die Leitung wegnahm; `apt` kann
gar nicht überlappen (dieselbe dpkg-Sperre wie Modul 20) und kostete 25 s für
null Pakete. Auf einem bestückten Gerät gibt es nichts zu holen, und die eine
Stelle, an der es zählen könnte — die Erstinstallation mit 1,5–2 min
Netzanteil — ist nicht gemessen. Was 0 s bringt und gepflegt werden muss, ist
toter Ballast. Messreihe und Zahlen:
`docs/messungen/2026-11-05-vorab-laden-und-uv.md`.

**Was bleibt, ist Teil 1** — und was dort gemessen wurde: `uv` in Modul 50
spart rund 30 s (82–85 s → 53–58 s), es liegt im eigenen Werkzeug-venv, hat
eine harte Zeitgrenze und fällt bei jedem Fehler auf `pip` zurück.

### Regel „Immer die neueste kompatible Fassung“ — kein Lock

Vorgabe smilez (5.11.2026): *„bei den aktuellen Massen an Sicherheitslücken,
die Updates erfordern, wäre [ein eingefrorener Stand] blöd … ich hätte gerne
immer die neuesten Versionen, die mit allem anderen kompatibel sind.“*

**Kein Lock.** `uv pip compile` würde die Anforderungen einmal auflösen und
exakte Fassungen festschreiben — `Pillow==13.0.0` bliebe 13.0.0, bis jemand
die Datei neu kompiliert. Reproduzierbar, aber genau das Gegenteil von dem,
was hier gebraucht wird: Eine geschlossene Lücke erreichte das Gerät erst
beim nächsten Neukompilieren. Ein Lock lohnt sich, wenn mehrere Geräte exakt
gleich laufen müssen oder ein Fehler nur bei einer Fassung auftritt — beides
haben wir nicht.

**Stattdessen wird bei jedem Lauf aufgefrischt** (`--upgrade` ist Vorgabe in
`lib/python.sh`, Schalter `CHIMERA_PIP_UPGRADE=aus` zum Messen):

1. **Stand sichern** — `pip freeze` nach `state/python-stand.txt`. Das ist
   gleichzeitig der Beleg, welche Fassungen liefen (Diagnose „gestern ging
   es noch“).
2. **Auffrischen** — uv/pip holt die neueste Fassung, die die Anforderung
   erfüllt. Was fehlt, kommt damit ohnehin; was aktuell ist, bleibt.
3. **Nachweisen** — bringt das Auffrischen den Nachweis zu Fall, ist es ein
   Befund. Die Sicherung wird **erst danach** überschrieben (andersherum
   rollte der Rückfall auf den kaputten Stand zurück — der Test hat genau
   das gefunden).
4. **Im Zweifel zurück** — der gesicherte Stand wird zurückgespielt; nur
   wenn auch das scheitert, endet das Modul mit rc 2.

**Kein Pin auf Verdacht.** Obergrenzen (`numpy<3`) kommen erst hinein, wenn
ein Bruch real auftritt und gemessen ist — nicht vorbeugend, denn jede
Obergrenze ist ein Update, das nicht ankommt.

**Ohne Netz keine Warteschleife**, solange die Umgebung vollständig ist: Der
Abruf ist dann eine Auffrischung, kein Herstellen. Fehlt dagegen etwas, gilt
die Warte-Schleife — dort hängt der Betrieb an ihr.

Was das kostet, ist gemessen (Pi, 5.11.): `uv pip install --upgrade -r
requirements.txt` gegen den Index = **888 ms**, „Would make no changes“.



### Architekturregel 10e — Jeder Lauf hinterlässt ein Protokoll

In `logs/` (vorgesehen: `/var/log/chimera/`), **auch bei Erfolg**. Ein
Lauf, der nichts hinterlässt, ist später nicht nachvollziehbar — und
genau dann braucht man ihn: wenn etwas schiefging und die Frage lautet,
was vorher anders war.

Protokolliert werden Zeitstempel, Version, erkannte Umgebung, jeder
Schritt mit Ergebnis und eine Schlussbilanz. Auf dem Schirm darf es
knapper zugehen als in der Datei. Kann kein Protokoll angelegt werden,
wird das **gemeldet** und nicht stillschweigend übergangen.

### Architekturregel 10f — Keine Container auf dem Gerät

Auf Pi und Radxa läuft alles **nativ**. Der Aufwand an Speicher,
Startzeit und Schreiblast ist auf diesen Geräten nicht zu rechtfertigen,
und er verdeckt gerade die Systemintegration, um die es hier geht.

Ausnahmen nur, wo es anders nicht geht — etwa ein Dienst, der nativ nicht
sauber baubar ist. Eine solche Ausnahme wird **hier begründet**, nicht
stillschweigend eingeführt. Bisher gibt es keine.

### Architekturregel 10g — Nie raten

Erst die Fakten holen, dann entscheiden. Kein „das Paket heißt vermutlich
so", kein „das liegt wahrscheinlich da". Nachsehen: im Quelltext, im
Paketindex, auf dem Gerät.

**Vor jedem Codebau prüfen, was bereits existiert und was daran hängt.**
Sonst entstehen Doppelimplementierungen — dieselbe Logik zweimal, subtil
unterschiedlich, monatelang unbemerkt.

Bekräftigt (smilez, 10.11.2026): Erst nachsehen, **was schon da ist, was die
Änderung berührt und wo sie anknüpft** — nie neben eine bestehende Struktur
bauen. Und jeden Schritt **mit der Blaupause vergleichen**: Weicht der Bau
von diesem Dokument ab, wird zuerst das Dokument geändert.

Was ungeprüft bleibt, wird **als ungeprüft benannt**. Eine ehrliche Lücke
ist brauchbar, eine geratene Antwort nicht. Deshalb steht in diesem
Dokument an mehreren Stellen „zu prüfen, nicht anzunehmen".

### Architekturregel 10h — Gebaut ist erst, wenn verdrahtet ist

Ein Modul, das niemand aufruft, ist kein fertiges Modul, sondern ein
offenes Ende. Dasselbe gilt für eine Funktion ohne Aufrufer, einen
Schalter ohne Wirkung, eine Option, die nirgends gelesen wird.

**Offene Enden fliegen einem um die Ohren — oder sie stehen dokumentiert.**
Beides ist zulässig, Schweigen nicht. Was unfertig bleibt, steht in der
Roadmap oder als bekannte Einschränkung im Changelog, mit seinem
tatsächlichen Zustand.

Bereits eingetreten: Modul 10 lag zunächst ohne Aufrufer da (kein
`chimera-install`), und `backup_file` hatte keinen. Ersteres ist
verdrahtet, Letzteres ist im Quelltext als „noch ohne Aufrufer, gebraucht
von Modul 60" vermerkt.

### Architekturregel 10l — Jeder Installationsschritt hat sein Gegenstück

**Ein Schritt, der etwas anlegt, wird zusammen mit dem Schritt geschrieben,
der es zurücknimmt.** Nicht später, nicht am Ende, nicht „wenn der
Installer final ist". Zu `installer/steps/NN-install-x.sh` gehört
`uninstaller/steps/NN-remove-x.sh`, und beide entstehen im selben
Arbeitsgang.

Dazu gehört zweitens: **Jede Änderung am System wird ins Manifest
geschrieben** (`installer/lib/manifest.sh`, Datei
`/var/lib/chimera/manifest.tsv`). Wer nicht einträgt, kann nicht
zurückbauen — und ein Deinstallierer, der raten muss, löscht entweder
Fremdes oder lässt Eigenes liegen.

Die Begründung ist nicht Symmetrie, sondern **Prüfbarkeit**: Der
Rückbauschritt ist der einzige echte Test des Manifesteintrags. Er
beantwortet die Frage, ob überhaupt genug festgehalten wurde, um die
Änderung umzukehren. Solange niemand aus dem Manifest liest, ist jeder
Eintrag eine unbelegte Behauptung.

Der Gegenentwurf — erst alle Installationsschritte, danach der
Deinstallierer — hat zwei Kosten, die vorher gemessen werden können:
Erstens stellt man am Ende fest, dass mehrere Schritte in einer Form
protokolliert haben, aus der sich nichts zurückbauen lässt, und korrigiert
sie rückwärts. Zweitens ist der Rückbau eines Dienstes oder eines
Kernelmoduls eine Reihenfolgefrage (stoppen, deaktivieren, entfernen,
`daemon-reload`), die man beim Anlegen im Kopf hat und Monate später
rekonstruieren muss.

Belegter Ausgangspunkt dieser Regel: Das Manifest kennt acht Arten
(`paket`, `zeile`, `datei`, `verzeich`, `dienst`, `gruppe`, `modul`,
`sicherung`). Benutzt wurden drei. Ob `dienst` und `modul` in einer
rückbaubaren Form eingetragen werden, war zum Zeitpunkt dieser Regel
**ungeprüft**, weil es keinen Leser gab — ein offenes Ende nach
Architekturregel 10h, und zwar in genau dem Bauteil, dessen Zweck der
Rückbau ist.

Drei Folgen für die Praxis:

- Ein Schritt, der nichts verändert, braucht kein Gegenstück.
  `10-check-system` prüft nur und trägt darum auch nichts ein.
- Der Deinstallierer läuft in **umgekehrter Reihenfolge** der Nummern und
  fasst nur an, was im Manifest als `neu` steht. Was als `vorher_da`
  vermerkt ist, gehört dem Nutzer und bleibt.
- **Ein fehlendes Manifest ist kein Grund abzubrechen.** Siehe die
  folgende Regel.

### Architekturregel 10n — Nachsehen, nicht abbrechen und nicht raten

Fehlt eine Auskunft, wird sie **geholt**, nicht ersetzt — nicht durch einen
Abbruch und nicht durch eine Annahme. Das ist die Anwendung von
Architekturregel 10g („Nie raten") auf den Fall, dass die eigene
Aufzeichnung fehlt.

Konkret beim Deinstallierer ohne Manifest: Die **Anwesenheit** ist immer
feststellbar. Pakete stehen in der Paketdatenbank, Dienste kennt `systemd`,
Verzeichnisse liegen im Dateisystem, Gruppenmitgliedschaften sagt `id`.
Also wird nachgesehen und erledigt, was eindeutig ist.

Eindeutig ist, was nur Chimera angelegt haben kann: eigene Pfade
(`/opt/chimera`, `/var/lib/chimera`), eigene Dienstnamen
(`chimera.service`). Dort braucht es kein Manifest — ein Verzeichnis
`/opt/chimera` hat niemand anders erzeugt.

**Was Nachsehen grundsätzlich nicht liefert, ist die Herkunft.** Ob `git`
vor Chimera installiert war, steht nirgends im System; `dpkg-query` sagt
„installiert", nicht „von wem". Ob `dtparam=spi=on` in der `config.txt` von
Chimera stammt oder vom Nutzer, ist am System nicht ablesbar. Das ist
Historie, und die kennt nur das Manifest.

Für diese Fälle gilt: **Fund nennen, Handlung dem Nutzer lassen.** Nicht
verschweigen (das wäre Regel 8a) und nicht auf Verdacht entfernen — wer dem
Nutzer sein SPI abschaltet, weil eine Zeile *auch* von Chimera stammen
könnte, hat geraten.

Die Unterscheidung spiegelt sich in jeder Feststellung: Sie gibt **drei**
Zustände zurück, nie zwei — `ist da`, `ist nicht da`, `kann nicht
nachsehen`. Wer die letzten beiden zusammenfasst, meldet Aufgeräumtheit,
wo er blind ist.

Zwei belegte Fallen beim Bauen dieser Bibliothek, beide derselbe
Mechanismus: Eine Feststellungsfunktion, deren Rückgabewert `1` oder `2`
ein normaler Befund ist, **muss in einer Bedingung aufgerufen werden**.
Steht der Aufruf nackt da, beendet `set -e` den Lauf — mit dem Exitcode der
Auskunft und ohne jede Meldung. Genau so starb der erste Lauf: kein
`systemctl` in der Testumgebung, Rückgabe 2, Abbruch. Ebenso killte ein
`printf > "${VAR:-/dev/null}"` als Nebensache den Hauptlauf.

### Architekturregel 10o — Was nicht im Manifest steht, gehört nicht uns

**Der Deinstallierer entfernt ausschließlich, was im Manifest steht.** Kein
Fund am System berechtigt zum Löschen, so naheliegend der Name auch ist.

Das ist die Grenze zu Architekturregel 10n: Nachsehen liefert eine
**Auskunft**, keine Erlaubnis. Beides zu vermischen ist der Kern des
Problems — wer aus „da liegt ein Verzeichnis namens `/opt/chimera`" schließt
„das habe ich angelegt", hat geraten, nur mit mehr Selbstvertrauen.

Denn dort kann liegen: etwas von Hand Angelegtes, eine Kopie, ein
Einhängepunkt, ein Verweis auf etwas anderes, ein gleichnamiges Verzeichnis
eines fremden Werkzeugs. Der Name ist ein Indiz, kein Beleg. Der Beleg ist
der Manifesteintrag, und den gibt es genau dann, wenn der Installer es
selbst getan hat.

Folgen:

- Ohne Manifest wird **nichts** entfernt. Es wird nachgesehen, vollständig
  berichtet, und die Handlung bleibt beim Nutzer.
- Auch mit Manifest gilt die Unterscheidung `neu` gegen `vorher_da`: Ein
  Eintrag belegt, dass wir es *gesehen* haben, nicht dass wir es *angelegt*
  haben.
- Die Suchlisten im Deinstallierer sind **Suchlisten für den Bericht**,
  keine Löschlisten. Sie heißen deshalb `chimera_known_paths`, nicht
  `chimera_own_paths` — ein früherer Entwurf hieß so und hat genau deshalb
  gelöscht, was er nur gefunden hatte.

Die Regel kostet Bequemlichkeit: Nach einer Installation von Hand oder mit
einer Fassung ohne Manifest bleibt Arbeit für den Nutzer. Das ist der
richtige Preis. Die Gegenrechnung wäre ein Werkzeug, das auf einem fremden
System nach Namensmustern löscht, und dessen Fehler bemerkt niemand
rechtzeitig.

### Architekturregel 10m — Ausführbares bleibt reines ASCII

Alles unter `installer/` und `uninstaller/` ist **ASCII**, und die Locale
wird im Programm festgelegt (`LC_ALL=C`), nicht von der Umgebung erwartet.

Zwei Gründe, beide nachgemessen:

Eine Fehlermeldung mit Umlaut wird auf einer Konsole ohne gesetztes `LANG`
zu Fragezeichen — und in einer systemd-Unit ist `LANG` standardmäßig leer.
Das trifft die Ausgabe genau dann, wenn man sie lesen will.

`sort` ordnet unter `de_DE.UTF-8` anders als unter `C`, und `grep [a-z]`
fasst dort auch Umlaute. Ein Installer, der je nach Umgebung anders
sortiert, ist nicht reproduzierbar.

Gemessener Ausgangszustand: 14 von 15 Shell-Dateien enthielten Nicht-ASCII
(`ä`, `Ä`, `—`), `LC_ALL` war nirgends gesetzt. Geprüft wird das von
`installer/tests/test-portability.sh`, mit Gegenprobe in beide Richtungen —
ein Gegenbeispiel im Kommentar (`kein [[ ]] verwenden`) darf **nicht**
anschlagen, sonst treibt der Test die Warnhinweise aus der Dokumentation.

Für Dokumentation gilt das nicht: `.md`-Dateien sind UTF-8 und dürfen
Typografie benutzen.

### Anlass für 10p und 10q: ein gemessenes Absturzbild

Ein Agenten-Harness auf zwei Android-Geräten stürzte an zwei Tagen
wiederholt ab. Ausgewertet wurde auf beiden Geräten unabhängig
voneinander, auf einem davon mit Root-Zugriff und einer laufenden
Speichermessung je Prozess. Der Auslöser (die Darstellung der Chatliste)
betrifft Chimera nicht. Das Muster dagegen ist plattformunabhängig:

1. Der native Speicher stieg in 60–80 s von rund 150 MB auf 5–8 GB, vor
   dem Absturz zur Hälfte ausgelagert. Der Speicher der Laufzeitumgebung
   blieb bei 30–120 MB. Wer nur ihn beobachtet, sieht einen gesunden
   Prozess.
2. Der Absturzbericht nannte eine Regex-Bibliothek, also den, der als
   Nächster Speicher wollte, nicht den, der ihn verbraucht hatte. Das
   führte zuerst zu einer Fehldiagnose.
3. Die Grenze, an der es endete, war die des Speicherverwalters, nicht
   die des Geräts. Beide Abstürze mit Messung blieben bei rund 8 GB
   stehen. Davor meldete der Verwalter, dass er für einzelne
   Blockgrößen keine Seiten mehr bekommt. Das passt zum Quelltext von
   scudo (32 Größenklassen zu je 256 MB). Ob Android genau diese
   Einstellung baut, ist nicht nachgeprüft. Eine Meldung ist ein Zeuge,
   keine Diagnose (Regel 10g).
4. Nach jedem Absturz stellte das Programm beim Start dieselbe Sitzung
   wieder her: vier Abstürze in 40 s auf dem einen Gerät, ein zweiter
   nach 60 s auf dem anderen.

### Architekturregel 10p — Was beim Laden abstürzt, wird beim nächsten Start nicht wieder geladen

Ein Dienst, der beim Start Zustand wiederherstellt, bildet zusammen mit
einem Neustarter (systemd `Restart=`) eine Schleife, sobald genau dieser
Zustand den Absturz auslöst. Jeder Neustart lädt ihn erneut. Das Gerät
wirkt kaputt, obwohl nur eine Datei schuld ist.

**Heute ist Chimera nicht betroffen.** Beim Start wird nur die
mitgelieferte `data/moods-builtin.json` geladen (`app.py`). Sie ist Teil
des Repos und nicht vom Modell erzeugt. `Registry.save()` hat in `src/`
keinen Aufrufer, `faces/` (Regel 8b) und `active_model.json` („Sprachmodelle:
Provider-Schicht") stehen
nur in diesem Dokument, der Gesprächsverlauf liegt nur im Arbeitsspeicher.
Die Regel gilt **ab dem ersten gespeicherten Zustand, den der Start
liest**. Der wichtigste Fall werden vom Modell angelegte Gesichter sein:
Regel 2 prüft deren Grenzen und Schema, aber nicht, ob das Zeichnen eines
gültigen Gesichts den Renderer oder den Speicher eines 512-MB-Geräts
sprengt.

**Umsetzung:**

1. Vor dem Laden einer Zustandsquelle eine Startmarke schreiben
   (`/var/lib/chimera/laedt.<quelle>`). Gelöscht wird sie erst nach dem
   Laden **und** dem ersten Bild bzw. ersten Umlauf, denn im Anlass kam
   der Absturz nicht beim Lesen, sondern beim Darstellen.
2. Findet ein Start die Marke eines früheren Laufs, wird diese Quelle
   nicht geladen, sondern zur Seite gelegt
   (`<datei>.quarantaene-<zeit>`). Gestartet wird mit dem Standard.
3. Das Zurückfallen wird **gemeldet**, im Protokoll (Regel 10e) und
   sichtbar (Abschnitt „Zustand sichtbar machen"). Läuft das Gerät weiter, ohne dass jemand erfährt, warum
   das Gesicht fehlt, ist das stiller Erfolg (Regel 8a).
4. Die Unit begrenzt die Neustarts (`StartLimitIntervalSec=`,
   `StartLimitBurst=`) für den Fall, dass Schritt 2 versagt.
5. Wer die Grenze erreicht, wird gemeldet und nicht still liegengelassen
   (Regel „Mojo“).

**Gegenprobe (Regel 9):** Eine Quelle anlegen, deren Laden den Prozess
beendet (`os._exit(1)` im Testpfad, nicht im Produktivcode). Ohne die
Regel stirbt der zweite Start genauso. Mit der Regel läuft er mit dem
Standard, die Quarantänedatei existiert und das Protokoll nennt sie.

### Architekturregel 10q — Speicher wird am Prozess gemessen und vom Prozess begrenzt

**Messen:** Pythons eigene Mittel (`tracemalloc`, `gc`,
`sys.getsizeof`) sehen nur Python-Objekte. Was C-Bibliotheken belegen
(Spracherkennung, Sprachsynthese, onnxruntime, numpy, PIL), ist für sie
unsichtbar, und genau dort entstehen auf dem Gerät die Lecks. Das
Protokoll (Regel 10e) schreibt deshalb je Arbeitsschritt `VmRSS`,
`VmHWM` und `VmSwap` aus `/proc/self/status` mit, in kB und ohne
Zusatzpaket. Arbeitsschritte sind mindestens: Start, Mood laden oder
wechseln, Spracherkennung, Sprachsynthese, Umlauf des Agenten.
`VmSwap` gehört dazu, weil zram und die Auslagerungsdatei (Regel 5e) ein
Leck erst schlucken: Im Anlass war die Hälfte schon ausgelagert, und das
Gerät wurde zäh, bevor es abstürzte.

**Begrenzen:** Die naheliegende Grenze, `MemoryMax=`/`MemoryHigh=` in der
systemd-Unit, **wirkt auf dem Pi nicht**. Der Raspberry-Pi-Kernel startet
mit `cgroup_disable=memory`, der Wert steht in `/proc/cmdline`, aber
nicht in `cmdline.txt`. Der Speicher-Controller fehlt dann in
`/sys/fs/cgroup/cgroup.controllers`.
Gemessen am Zero 2 W (DietPi, Kernel 6.18, systemd 257): Ein Prozess
belegte 150 MB unter `MemoryMax=20M` und lief durch. Die Gegenprobe
`RuntimeMaxSec=1` griff, systemd hat die Eigenschaften also übernommen.
Eine solche Zeile in der Unit wäre stiller Erfolg (Regel 8a).

**Gemessen am Zero 2 W (1.11.):** 462 MB gesamt, **339 MB verfügbar**
(der Rest ist Cache, der sich freigibt); belegt sind etwa 46 MB. Der Dienst
`chimera` (Python) hält 50 MB (27 MB anonym, 23 MB aus Dateien), das Gateway
1,5 MB, `systemd` 14 MB, `journald` 10 MB. Der Kernel reserviert 64 MB für
CMA (Kamera, GPU), obwohl es weder `/dev/video*` noch `vc4`/`v3d`/`unicam`
gibt; `/proc/cgroups` zeigt keinen Speicher-Controller. Ob sich die CMA
verkleinern lässt und was `cgroup_enable=memory` kostet, ist nicht gemessen
(ROADMAP, Phase 4d).

Daraus folgt:

- Der Dienst begrenzt sich selbst. Liegt `VmRSS + VmSwap` über einer
  Schwelle, beendet er sich geordnet mit eigenem Exitcode und
  Protokolleintrag. Die Schwelle ist ein Anteil von `MemTotal` und steht
  in der Profiltabelle (Regel 10c), nicht als feste Zahl im Code.
- Steht `MemoryMax=` trotzdem in der Unit, prüft der Installer, ob
  `memory` in `cgroup.controllers` steht, und meldet es, wenn nicht
  (Regel 10j: wer prüft, muss etwas sehen können).
- Den Controller einzuschalten (`cgroup_enable=memory` in `cmdline.txt`)
  wäre eine Änderung an einer Bootdatei. Sie ist hier **nicht
  entschieden** und gehört, falls gewollt, in ein Installermodul mit
  Sicherung und Rückweg.

**Messreste gehören nicht nach `/tmp` (entschieden 13.11., am Pi
gefunden).** Auf dem Pi ist `/tmp` eine **tmpfs** — jeder Messbaum liegt
also im RAM und zählt gegen dieselben 462 MB, die der Dienst braucht. Am
13.11. lagen dort 276 MB alter Messungen (fünf Bäume, alte Quell-Tarballs);
`free` meldete 309 MB „benutzt", obwohl alle Prozesse zusammen 36 MB
belegten — htop zeigt das als Last. Dazu kommt: ein Neustart räumt `/tmp`,
die Messung ist dann weg und der Prüfbaum nicht mehr nachvollziehbar.
Messbäume, Zwischenstände und Prüfbäume gehören deshalb nach
**`/opt/chimera/logs/messungen/<thema>/`** (Disk, auf dem Pi die SD/eMMC)
— dort, wo auch die Installer-Protokolle liegen; auf einem Rechner ohne
viel RAM ist `/var/tmp` die zweite Wahl (Disk, aber ohne Aufräumregel).
Nach der Auswertung wird der Baum gelöscht oder klein gehalten: ein
Messbaum ist ein Beweis, kein Vorrat.

**Nachweis eines Speichertods:** Unter Linux gibt es keinen
Absturzbericht, der Kernel beendet den Prozess per SIGKILL. Ohne
Speicher-Controller kann systemd den Tod nicht als `oom-kill` einordnen,
die Spur steht nur im Kernelprotokoll (`journalctl -k`,
„Out of memory: Killed process"). Der Protokollanfang beim nächsten Start
sucht danach und schreibt den Fund hin. Sonst sieht der Absturz aus wie
ein sauberer Neustart. Auch die Selbstbegrenzung hinterlässt ihre Spur,
über den eigenen Exitcode.

**Fehlersuche (zu Regel 10g):** Bei Speichermangel nennt der
Absturzbericht den, der als Nächster Speicher wollte. Erst die
Speicherkurve vor dem Absturz lesen, dann den Stack.

**Gegenprobe (Regel 9):** Einen Schritt bauen, der über eine
C-Bibliothek Speicher belegt (`numpy.ones(...)`) und nicht freigibt.
`tracemalloc` meldet dabei wenig, `VmRSS` muss den Anstieg zeigen, und
über der Schwelle muss sich der Dienst mit seinem Exitcode beenden.
Zeigt das Protokoll den Anstieg nicht, misst es das Falsche. Für die
Prüfung des Controllers: Ein Testprozess mit `MemoryMax=20M` belegt
150 MB. Läuft er durch, muss der Installer warnen.

### Architekturregel 10r — Der Agent ist ein eigener Nutzer, und was root ausführt, kann er nicht ändern

Chimera läuft immer unter dem Systemnutzer **`chimera`**, den der
Installer anlegt. Ein vorhandener Nutzer (auf DietPi `dietpi`) ist
**keine Option**: Er hat dort `sudo` ohne Passwort, ein Agent unter ihm
wäre faktisch root, und er könnte alles in dessen Home lesen
(SSH-Schlüssel). Die Regel gilt für jedes Linux, DietPi ist der erste
Prüffall.

Was der Agent darf, regeln **die Rechte des Nutzers**, nicht nur die
Schranke in `agent/safety.py`. Die Schranke ist Programmcode und kann
einen Fehler haben, die Dateirechte setzt der Kernel durch.

**Die Rechte wachsen mit dem Harness, und jedes einzelne ist belegt.**
Vergeben wird nur, was der heutige Code nachweislich braucht:

| Recht | Wofür | Beleg |
|---|---|---|
| Gruppe `audio` | Lautsprecher, Mikrofon | HARDWARE-BEFUNDE: `aplay -l` ohne `audio` leer |
| Gruppe `spi` | LCD über spidev | HARDWARE-BEFUNDE: `python3-spidev`, `/dev/spidev0.*` |
| Gruppe `gpio` | LED, Button, Panel-Steuerleitungen über gpiod | HARDWARE-BEFUNDE: `python3-libgpiod` |
| Schreiben im eigenen Home | Gedächtnis, Moods, Arbeitsordner, Dienstprotokolle | `app.py` (`CHIMERA_HOME`) |
| Gruppe `i2c` | **opt-in**, erst wenn Code direkt auf I2C zugreift | heute keiner: den Codec spricht der Kerneltreiber an |
| Gruppe `video` | **opt-in**, etwa sobald ein Kameramodul angeschlossen ist | heute keiner |

Opt-in heißt: Der Installer vergibt die Gruppe nur, wenn ein Profil
oder eine Option sie anfordert (`--mit i2c`, `--mit video`). Dann steht
sie in der Unit und im Manifest, und der Rückbau nimmt sie mit.

Nicht vergeben werden: `sudo`, eine Anmeldung per Passwort und
Schreibrechte außerhalb des eigenen Homes. Eine Gruppe, die es auf
dem System nicht gibt, wird übersprungen und benannt. Ein neues Recht
kommt mit dem Code, der es braucht, und mit einer Zeile in dieser
Tabelle, nicht vorsorglich.

**Pfadschema: getrennt nach Eigentümer.**

```
/opt/chimera/                    root:root 755  -- für chimera nur lesbar
  source/                        Kopie des Repos, SSOT des Installers
  productive/                    laufender Code (aus source/) und venv
  state/                         root:root 700  -- Manifest, Standdateien
  config/                        root:chimera 750, .env 640
  logs/installer/                Protokolle von Install und Uninstall
/home/<nutzer>/chimera/          chimera:chimera 700
  data/                          Gedächtnis, Moods, Arbeitsordner (CHIMERA_HOME)
  logs/productive/               Protokolle des Dienstes
```

Der Grund für die Trennung: **Wer ein Verzeichnis besitzt, kann dessen
Einträge ersetzen**, auch wenn sie root gehören (umbenennen braucht nur
Schreibrecht am Elternverzeichnis). Läge `source/` im Home von `chimera`,
könnte der Agent es gegen eigenen Code tauschen, und der nächste
`sudo chimera-install` führte diesen als root aus. Eine Prüfsumme hilft
dabei nicht, der Angreifer hätte beide Seiten in der Hand. Darum liegt
alles, was root ausführt oder liest, unter `/opt/chimera`, und der Agent
kann es nicht ändern. Das Manifest (`state/`) kann er nicht einmal lesen:
Es legt fest, was der Deinstallierer löscht. Installer und Deinstallierer
laufen beide als root und **lesen und schreiben es beide**: Für den
Installer ist es das Melderegister (was er angelegt hat), für den
Deinstallierer die einzige Wahrheitsquelle (was er entfernen darf).
Ausgesperrt ist nur der Dienstnutzer.

**Protokolle: erst in den Arbeitsspeicher, dann gesammelt auf den
Datenträger.** Geschrieben wird nach `/run/chimera/logs/` (tmpfs, für den
Dienst `RuntimeDirectory=`), nicht direkt auf die SD. Ein Abgleich kopiert
die Dateien in die Zielordner der Tabelle (`logs/installer/`,
`logs/productive/`), sobald eine Ruhezeit lang nichts mehr geschrieben
wurde, und immer beim Stoppen des Dienstes und am Ende eines
Installerlaufs. So schreibt nicht jeder Logger laufend auf die Karte,
sondern es gibt einen gebündelten Schreibvorgang. Nach einem Neustart sind
die Protokolle trotzdem da: `/var/log` hilft dafür nicht, DietPi hält es
im RAM und leert es stündlich (DietPi-RAMlog #1, Vorgabe).

Der Preis wird benannt: Bei einem Stromausfall fehlt, was seit dem
letzten Abgleich geschrieben wurde. Wer genau diesen Teil braucht
(Absturz ohne Stoppen), findet die Spur im Kernelprotokoll (Regel 10q).
Ruhezeit, Abgleich und Rotation stehen in `lib/common.sh`, nicht je
Logger. Ein zweiter Mechanismus daneben wäre eine Doppelimplementierung.

Ausführung beim Dienst (11.10.2026):

- **Der Dienst schreibt eine Datei je Start** (`dienst-<zeit>.log`) in
  `$CHIMERA_LOG_RAM`, zusätzlich zum Journal. Je Start, nicht eine feste
  Datei: Sonst überschriebe der nächste Start beim Abgleich das
  Protokoll des vorigen — genau das, das man nach einem Absturz braucht.
- **Größendeckel im Schreiber, Anzahl in `common.sh`.** `/run` ist ein
  tmpfs von rund 90 MiB (chimera-pi gemessen), ein geschwätziger Logger
  füllte ihn und störte das ganze System. Python teilt deshalb ab 1 MiB
  in Stücke (`dienst-<zeit>.1.log`, höchstens drei). Wie viele Dateien
  auf der Karte bleiben, regelt `log_rotate` — das bleibt die eine Stelle.
- **Ein Abgleichsweg für Stopp und Ruhezeit.** `installer/bin/log-abgleich.sh`
  lädt `common.sh` und ruft `log_sync`; `ExecStopPost=` der Dienst-Unit
  ruft ihn sofort, ein Timer (`chimera-logabgleich.timer`, alle 5 min)
  mit `--ruhig`. Ruhig heißt: Abgleich, wenn seit 120 s nichts mehr
  geschrieben wurde — **oder spätestens nach einer Stunde**, sonst
  erreichte ein ununterbrochen schreibender Dienst die Karte nie, und ein
  Stromausfall nähme alles mit.
- Der Timer läuft als Dienstnutzer mit derselben Abschottung wie der
  Dienst und gehört zu Schritt 98 (Manifest, Rückbau).

**Der Installer arbeitet immer aus `source/`, egal woher der Code
kam.** Startbaum kann ein Git-Klon sein, ein offline hingeschobenes Zip
oder später ein Paket (apt, npm). Jede Quelle führt in denselben
Schritt `00-source`: Startbaum mit `source/` vergleichen, bei Bedarf
`source/` neu befüllen (Nachbarverzeichnis, dann atomarer Tausch),
dann per `exec` aus `source/` neu starten. Danach sieht kein Schritt
mehr den Startbaum.

Zwei Vergleiche, mit getrennter Aufgabe:

- **Ob es derselbe Stand ist:** Prüfsumme über den Inhalt, nicht über
  den Git-Commit, denn Zip und Paket haben keinen. `.git` und
  Arbeitsdateien zählen nicht mit.
- **Welcher Stand der neuere ist:** die Datei `VERSION`, verglichen mit
  `sort -V`. Eine Prüfsumme sagt nur „anders", nicht „neuer".

**Ergänzung (12.10.2026) — Grenze der Prüfsumme.** Ein Dateiname mit
Zeilenumbruch macht einen Baum nicht prüfbar, die Prüfung bricht benannt
ab: So ein Name ergibt keine eindeutige Zeile, und eine still ausgelassene
Datei wäre eine, deren Änderung niemand bemerkt. Die Summe hängt nicht vom
Werkzeug ab — GNU und BusyBox liefern für denselben Baum dieselbe.

**Der Hash wiegt schwerer als die Version.** Die Reihenfolge der
Entscheidung:

1. **Gleicher Hash:** Der Stand ist schon 1:1 da. Der Schritt tut nichts,
   und der nächste Schritt läuft. Das gilt auch, wenn `VERSION`
   unterschiedlich ist, denn dann steht in `VERSION` nur ein anderer Text,
   der Inhalt ist derselbe.
2. **Anderer Hash, `VERSION` höher oder gleich:** `source/` wird ersetzt.
   Bei gleicher `VERSION` (Entwicklungsstand ohne Versionssprung) gibt es
   dazu einen Hinweis.
3. **Anderer Hash, `VERSION` niedriger** (ein altes Zip): kein Ersatz.
   Der Lauf benennt das, arbeitet mit dem vorhandenen `source/` weiter
   und meldet am Ende einen Befund. Ein Rückschritt geht nur gezielt mit
   `--downgrade=true`, und auch dann steht er im Protokoll.

Das ist der Orchestrator-Grundsatz aller Schritte: Ist das Ziel schon
da und gleich, wird übersprungen. Geprüft wird der Zustand, nicht eine
Marke.

**Online wird auf den neuesten Stand gezogen.** Ist das Netz da und die
Quelle öffentlich erreichbar, holt `00-source` den neuesten
veröffentlichten Stand und nimmt den höheren von beiden (Startbaum oder
online). „Neuester" heißt der höchste `vX.Y.Z`-Tag (`sort -V`), nicht
die Spitze eines Zweigs. **Offline** zählt nur, was lokal da ist, und
der Lauf sagt, dass er nicht nachsehen konnte (Regel 10j). Kein
Abbruch und kein stilles „ist aktuell".

Heute gibt es noch keinen Tag (Pre-Alpha bleibt ungetaggt). Die
Online-Prüfung ist trotzdem gebaut und getestet, gegen ein Testrepo mit
Tags. Findet sie keinen Tag, meldet sie „kein veröffentlichter Stand"
und es zählt der lokale. Die Spitze eines Zweigs nimmt sie nie ersatzweise:
Mit dem ersten Tag greift die Regel dann ohne Umbau.

Ein neues `source/` ändert am laufenden Dienst noch nichts. Erst der
Installerlauf bringt den Stand nach `productive/`. Den Neustart des
Dienstes löst die Prüfsumme von `productive/` aus.

**Rückbau:** `source/`, `productive/` und `state/` entfernt er.
**Protokolle löscht er nie von sich aus**, weder `logs/installer/` noch
`logs/productive/`: Gerade nach einem Rückbau braucht man sie, um zu
sehen, was passiert ist. Löschen nur auf ausdrückliche Anforderung
(opt-in). Dasselbe gilt für `config/` und `/home/<nutzer>/chimera/data/`
(INSTALLER.md `docs/INSTALLER.md`, Abschnitt „Deinstallation"). Den Nutzer
`chimera` entfernt er nur, wenn sein Home dabei mitgeht (also nur bei
angeforderter Löschung der Daten und Protokolle). Sonst bliebe
ein Home ohne Eigentümer zurück, und eine später vergebene UID erbte es.

**Gegenprobe (Regel 9):** (a) Den Installer aus zwei verschiedenen
Startpfaden aufrufen. Beide Läufe müssen dasselbe `source/` ergeben, der
zweite darf nicht kopieren. (b) Als `chimera` versuchen, in `source/`,
`productive/` und `state/` zu schreiben bzw. umzubenennen. Jeder Versuch
muss scheitern. (c) Eine Datei im Startbaum ändern. `source/` muss neu
befüllt werden, `productive/` erst im Installerlauf.

### Architekturregel 10s — Root gibt es nur auf Rückfrage, auf Zeit, und nicht für den Agenten selbst

10r bleibt: Der Dienstnutzer `chimera` hat **kein** sudo. Root kommt
über einen eigenen Helfer:

- **`chimera-hand`**, ein kleiner Root-Dienst mit Socket
  (`/run/chimera/hand.sock`, nur Gruppe `chimera`). Er führt Befehle
  **nur** aus, solange eine gültige Freigabe besteht.
- **Freigabe:**
  1. Der Agent fragt: Was will er tun, warum, und wie lange (Vorschlag
     in Minuten).
  2. Gefragt wird **der Nutzer**, über Telegram (Positivliste, Bestätigung
     per Knopf) oder die Web-Oberfläche. Nie über den Briefkasten (5p), nie über die CLI
     ohne Nutzer.
  3. Der Nutzer bestätigt **mit der Dauer**. Das Gateway schreibt die
     Freigabe an `chimera-hand` (Ablaufzeitpunkt, Grund, wer bestätigt
     hat). Der Agent selbst kann keine Freigabe anlegen.
- **Ablauf erzwingt der Helfer**, nicht der Agent: Nach Ablauf wird jeder
  Befehl abgewiesen. Höchstdauer 60 min (Vorschlag), Verlängern nur über
  eine neue Rückfrage. „Sofort beenden“ gibt es über Telegram und Web.
- **Alles wird protokolliert:** jeder Befehl, Exitcode, Dauer, unter
  `/opt/chimera/logs/root/` (root-only, für den Agenten nicht änderbar).
  Am Ende eine Bilanz an den Nutzer: „N Befehle, M fehlgeschlagen“.
- **Ein Ehrlichkeitspunkt:** Während einer Freigabe gilt der Schutz aus
  10r **nicht**. Root kann `/opt/chimera`, das Manifest und den Helfer
  selbst ändern. Die Absicherung besteht dann aus deiner Bestätigung,
  der Zeitgrenze und dem Protokoll. Eine strengere Betriebsart, bei der
  jeder einzelne Befehl bestätigt wird, wird als Option angeboten.
  Vorgabe ist die Zeitfreigabe.

### Regel „Freigabe je Werkzeug auf Zeit“ — die Positivliste lässt sich befristet aussetzen, die Negativliste nie

Vorgabe smilez (12.11.2026), entschieden im selben Gang: **Der Nutzer soll
wählen**, ob ein Werkzeug weiter **einzeln** fragt (Positivliste) oder ob
für eine **Zeitspanne** alles durchgeht, was nicht auf einer **Negativliste**
steht. „Für immer“ ist ausdrücklich erlaubt. Geschaltet wird **pro Werkzeug**;
Ziele sind die Ausnahmen dazu (smilez: „Werkzeug, Ziel als Zusatz“).

**Warum überhaupt.** Eine Positivliste, die jede neue Adresse einzeln
abnickt, ist sicher und im Alltag unbrauchbar; ein Freibrief ohne Grenze ist
im Alltag bequem und im Ernstfall offen. Die Zeitfreigabe ist der Mittelweg,
den 10s für Root schon geht: der Nutzer entscheidet **einmal mit einer
Frist**, danach entscheidet die Uhr — nicht der Agent.

**Zustand und Form.** `config/freigaben/freigaben.json` (eigener Ordner
`chimera-tor` 700, Datei 660 — wie `config/wahl/`; das
Gateway schreibt, der Agent liest sie **nie** — er bekommt „erlaubt“ oder
„abgelehnt“ mit Grund):

> **Warum ein eigener Ordner (13.11.2026, am Gerät gefunden).** Eine Datei
> direkt in `config/` lässt sich **nicht** speichern: Geschrieben wird atomar
> über eine Nebendatei im selben Ordner, und `config/` ist für das Gateway nur
> Durchgang (751, Regel 5t). Der erste Lauf am Pi endete mit
> `Read-only file system (os error 30)`. Ablage, Protokollordner und
> `ReadWritePaths` müssen zusammenpassen — sonst ist die Freigabe eine Anzeige
> ohne Wirkung.

```json
{
  "vorgabe": {"modus": "positivliste"},
  "werkzeuge": {
    "web_abruf": {
      "modus": "offen",
      "seit": 1794486400,
      "erinnern_alle": 300,
      "positiv": ["api.example.com"],
      "negativ": ["intern.example.com"],
      "notiz": "12.11., auf Zeit freigegeben"
    }
  }
}
```

- **`modus`** — `positivliste` (Vorgabe, nur Ziele in `positiv`) oder
  `offen` (jedes Ziel außer `negativ`).
*Soll-Zustand (noch nicht gebaut):*

- **`seit`** — wann die Freigabe geöffnet wurde (Unix-Zeit). Nicht die Frist:
  seit dem 13.11. läuft eine Freigabe **nicht** ab.
- **`erinnern_alle`** — Sekunden zwischen zwei Erinnerungstönen (Vorgabe 300).
- **`bis`** — **nur noch Altbestand.** Neue Freigaben schreiben es nicht mehr;
  ein Eintrag mit `bis` in der Vergangenheit wird weiter als `positivliste`
  gelesen, damit eine alte Frist nicht rückwirkend aufgeht.
- **`positiv` / `negativ`** — Ziele in der Form des Werkzeugs (Host bei
  `web_abruf`, `user@host` bei `ssh`, Quellenname bei `web_suche`).
  **`negativ` gilt immer** — auch in `offen`, auch bei `bis: null`,
  auch für ein Ziel, das in `positiv` steht.
- **Die Werkzeugliste ist geschlossen.** Ein Name, der nicht in der Tabelle
  steht, wird abgelehnt (`werkzeug_unbekannt`) — sonst öffnet ein Tippfehler
  still gar nichts oder, schlimmer, alles.

**Kein Ablauf mehr — der Ton erinnert** (Vorgabe smilez, 13.11.2026;
*gebaut 13.11. in drei Stufen* — Rust-Zustand, beide Türen, Ton im Dienst;
CHANGELOG).
Die Fassung vom 12.11. ließ die Uhr entscheiden: Nach `bis` galt wieder
`positivliste`, ohne dass jemand etwas tat. Das ist still — und im Alltag
heißt es, dass eine Freigabe mitten in der Arbeit zumacht, ohne dass man es
merkt. Jetzt gilt: **Eine Freigabe bleibt offen, bis der Nutzer sie beendet.**
Statt der Uhr entscheidet die **Aufmerksamkeit** — aber nur, wenn der Nutzer
sie bestellt. Der Ton an einer offenen Freigabe ist **opt-in** (smilez,
13.11. nachmittags, nachdem der erste Bau piepte): `erinnern_alle` ist
**Vorgabe 0 = aus**; wer ihn will, setzt 60 s oder mehr, und dann ertönt er
**wiederholt**, bis die Freigabe geschlossen wird.

- **Warum opt-in:** Der Ton war für **offene Rückfragen** gedacht (das Gerät
  wartet auf eine Antwort des Nutzers), nicht für jede Freigabe. Eine
  Freigabe, die still offen bleibt, ist harmlos — der Zaun und die
  Negativliste gelten weiter; ein Dauerpiepen bei jeder Freigabe wäre nur
  Lärm. Der Rückfrage-Ton ist ein eigener Punkt (ROADMAP).
- **Was das kostet, ehrlich benannt:** Ist der Ton eingeschaltet und niemand
  am Gerät, piept es weiter, bis jemand die Freigabe schließt. Das ist dann
  die bewusste Entscheidung des Nutzers — er hat den Ton bestellt.
- **Altbestand wird nicht aufgeweckt:** Ein Eintrag mit einem `bis` in der
  **Vergangenheit** wird beim Einlesen als `positivliste` gelesen (die alte
  Frist war abgelaufen — sie darf nicht rückwirkend aufgehen). Ein `bis` in der
  Zukunft bleibt offen, mit Erinnerung ab jetzt.
- **Der Ton kommt vom Dienst, nicht vom Gateway.** Der Lautsprecher hängt an
  der Anzeige (Whisplay HAT: ALSA-Karte `whisplaysound`, `aplay` vorhanden);
  das Gateway hat kein Audio. Auslöser ist der Zeitgeber des Dienstes, die
  Wahrheit über „ist etwas offen" bleibt im Gateway (`op: freigabe_lesen`).
  **Gebaut** in `src/chimera/freigabe_erinnerung.py`, eingehängt in die
  bestehende Dienstschleife (30 s Takt, kein zweiter Faden): der erste Ton
  kommt **nach** dem Abstand, nach einer Pause einmal statt nachgeholt, und
  für alle fälligen Werkzeuge **ein** Ton. Fehlt `aplay`, wird das gemeldet —
  nicht geworfen; der Dienst läuft weiter. Ohne bestellten Abstand (`0`) wird
  für den Eintrag gar nichts geplant — kein Timer, kein Ton.
- **Eine Dauer wird nicht still umgedeutet.** Web und Telegram bieten keine
  mehr an; wer trotzdem `30m` schickt, bekommt eine Ablehnung mit Grund
  („Freigaben laufen nicht mehr ab“) statt einer Freigabe, die heimlich
  ewig offen ist. Ein mitgeschicktes `bis` wird nicht gespeichert.

**Geprüft wird beim Ausführen, nicht vom Zeitgeber.** Der Zustand wird
**beim Prüfen** gelesen, nicht von einem Timer gepflegt: ein ausgefallener oder
neu gestarteter Dienst darf eine Freigabe weder verlängern noch (seit 13.11.)
verkürzen. Die Prüfung
sitzt dort, wo ausgeführt wird — Netzwege im Gateway, Befehle im Ausführer
(Regel „Wer prüft, führt aus“); der Agent fragt nie selbst „darf ich?“ und
bekommt auch keine Restzeit zu sehen.

**Wer freigibt, ist immer der Nutzer.** Die Türen sind die Web-Oberfläche
(Modul `freigaben`) und Telegram (`/frei`) — beide schreiben dieselbe Datei
über `op: freigabe_setzen`; der Agent kann **keine** Freigabe anlegen, auch
nicht über einen Umweg (kein Werkzeug dafür). Die harten Grenzen aus
`safety.py` / dem Ausführer (`sudo`, `su`, Interpreter, Shell-Zeichen,
Pfadschutz) bleiben **unabhängig** vom Modus in Kraft: `offen` erlaubt mehr
Ziele, nicht mehr Programme.

**Protokoll.** Jede Freigabe und jede Ablehnung kommt mit Zeitpunkt, Werkzeug
und Grund in `state/log/freigabe.log` (eine Zeile je Entscheidung, rollierend
bei 512 kB) — „stiller Erfolg“ ist hier die gefährlichste Fehlerart, also wird
auch das Ja protokolliert, und ein nicht schreibbares Protokoll wird im
Dienstprotokoll gemeldet (die Entscheidung selbst dreht es nicht um).

**Gegenprobe (Regel 9):** (a) `negativ` greift in `offen`. (b) Ein
abgelaufener Zeitpunkt wirkt wie `positivliste`, ohne dass jemand die Datei
anfasst. (c) Der Agent kann über kein Werkzeug einen Eintrag in
`freigaben.json` schreiben. (d) Ein unbekannter Werkzeugname wird abgelehnt
statt durchgelassen.

**Erste Stufe (gebaut 12.11.):** Zustand, Türen und Ablauf — siehe CHANGELOG.
**Stufe 2 (gebaut 12.11.):** `web_abruf` fragt vor dem Verbinden — die
Positivliste der Ziele ist `positiv`, kein zweiter Ort.

**Stufe 3 (entschieden 12.11., smilez: „Gateway fragen"):** Der Ausführer
fragt das Gateway, bevor er ein Programm startet. Keine zweite Kopie des
Zustands, keine eigene Auslegung — **eine** Wahrheit, und die steht dort, wo
die Türen sie schreiben.

- **Ablauf:** `run` prüft erst die harten Regeln (`safety.py`-Port), dann
  fragt er `{"op":"freigabe_pruefen","werkzeug":"run_command","ziel":"<programm>"}`
  über `/run/chimera/tor.sock`. Erst ein „erlaubt" führt zur Ausführung.
- **Ziel ist der Programmname** (Basename von `argv[0]`, klein geschrieben),
  nicht die ganze Zeile: eine Liste von Kommandozeilen träfe nie, und
  „Werkzeug, Ziel als Zusatz" meint ein Ziel, das man hinschreiben kann.
- **Nicht erreichbar heißt nicht erlaubt.** Antwortet das Gateway nicht,
  läuft **nichts**, und der Text nennt den Grund (kein Rückfall, wie bei 5n).
- **Die harten Regeln bleiben unabhängig:** `offen` erlaubt mehr Ziele, nicht
  mehr Programme. `sudo`, Interpreter, Shell-Zeichen und Netzprogramme werden
  weiterhin abgelehnt, auch bei „für immer".
- **Rechte:** Der Ausführer bekommt die Gruppe `chimera`
  (`SupplementaryGroups=`), sonst kommt er nicht an den Gateway-Socket
  (0660 `chimera-tor:chimera`). Er liest den Zustand trotzdem nie selbst —
  `InaccessiblePaths=/opt/chimera/config` bleibt.
- **`ssh` im normalen Weg bleibt gesperrt:** Netzprogramme lehnt der
  Ausführer grundsätzlich ab (`IPAddressDeny=any`, kein Netz) — auch mit
  Freigabe. Der **einzige** ssh-Weg ist `op: ssh` (Abschnitt
  „Fernausführung" weiter unten): das Gateway prüft, verbindet und reicht den
  Deskriptor weiter. Seit 12.11. (`bbb8e1d`) hat der Freigabe-Eintrag damit
  seinen Aufrufer.

### Regel „Wer prüft, führt aus“ — Werkzeuge laufen in einem eigenen Prozess, den der Agent nicht ändern kann

Vorgabe smilez (10.11.2026): eine **unabhängige Kontrollinstanz** vor der
Werkzeugausführung — **ausdrücklich nicht als zweites Sprachmodell**.

**Das Problem.** Ein Modell, das selbst beurteilt, ob sein Befehl harmlos
ist, rechtfertigt sich im Zweifel selbst. Das ist bei Chimera schon heute
nicht der Fall: `agent/safety.py` prüft mit festen Regeln, kein Modell
urteilt. Aber die Prüfung läuft **im selben Prozess** wie die
Agentenschleife, und derselbe Prozess startet danach das Programm
(`agent/tools.py`: `check_command`, dann `subprocess.run`). Unabhängig ist
sie damit in der Logik, nicht in der Bauform — ein Fehler in der Schleife
kann die Prüfung auslassen.

**Die Regel.**

1. **Kein zweites Modell.** Ein Richter-Modell kostet bei jedem
   Werkzeugaufruf Tokens und Zeit und lässt sich täuschen wie das erste.
   Geprüft wird mit festen, lesbaren Regeln; was die Regeln nicht
   entscheiden können, entscheidet der Nutzer (Regel 10s), nie ein Modell.
2. **Wer prüft, führt aus.** Ein Prozess, der nur „ja“ oder „nein“ sagt,
   während der Agent selbst startet, ist keine Schranke — die Frage lässt
   sich auslassen. Darum liegen Prüfung **und** Ausführung zusammen in
   einem eigenen Prozess (`chimera-sohelper`). Der Agent schickt
   den Wunsch und bekommt das Ergebnis; er startet nichts mehr, was das
   Modell gewählt hat.
3. **Was umzieht:** `run_command`, `read_file`, `write_file`, `list_dir` —
   also alles, was heute über `check_command` und `safe_path` läuft. Nur die
   Befehle umzuziehen wäre die halbe Trennung. `set_face` bleibt im Dienst
   (Anzeige, kein Programmstart).
4. **Was bleibt:** `preflight` (Argumente reparieren und gegen die
   Beschreibung prüfen) und `loopguard` (Schleifen erkennen) bleiben in der
   Agentenschleife — sie beurteilen das Verhalten des Modells, nicht ein
   Recht. Der Ausführer verlässt sich nicht darauf: Was über den Socket
   kommt, ist Eingabe und wird dort noch einmal geprüft (Regel 5p).
5. **Rust, eigener Socket, kein Netz.** Der Prozess läuft dauernd und
   wartet nicht auf das Modell (Regel 14): eine Crate im Workspace,
   Zeilenrahmen aus `gemein::zeile`, Socket unter `/run/chimera/`,
   `IPAddressDeny=any`, keine Schlüssel.
6. **Nicht im Gateway.** Das Gateway hat Netz und hält die Schlüssel
   (Regel 5n). Vom Modell gewählte Programme dort zu starten gäbe ihnen
   genau die Rechte, die 5n dem Agenten nimmt.
7. **Die Regeln liegen dort, wo der Agent nicht schreiben kann** — unter
   `/opt/chimera/` (Regel 10r), nicht im Arbeitsverzeichnis. Der heutige
   Schreibschutz für `src/chimera/agent/safety.py` in `Limits.protected`
   wird damit überflüssig.
8. **Jeder Aufruf wird protokolliert** (Regel 10e): Werkzeug, Urteil,
   Grund, Exitcode, Dauer. Eine Ablehnung geht mit Begründung an das Modell
   zurück, wie heute — sonst versucht es dasselbe noch einmal.

**Gebaut (11.11.2026): `rust/crates/sohelper`.** Zehn Regeltests, clippy
sauber, Rauchtest über den Socket:

- **Regeln portiert, nicht neu erfunden** (`lib.rs`): Sperrliste
  (`sudo`, `su`, `doas`, `pkexec`), Interpreter (`sh`, `bash` …),
  Shell-Zeichen, gefährliche Muster, Ersetzung und Mehrzeiligkeit,
  Pfadschutz mit Auflösung über Symlinks, Kürzen der Ausgabe — dieselben
  Grenzen wie `safety.py`. **Kein `allow_network`**: Netzprogramme
  (`curl`, `wget`, `git`, `ssh` …) werden immer abgelehnt (Regel 5n).
- **Zerlegen wie `shlex.split(posix=True)`**, mit Test (Anführungszeichen
  halten zusammen, Backslash schützt).
- **Socket** (`main.rs`): eine JSON-Zeile hin, eine zurück; Ops `ping`,
  `run`, `read`, `write`, `list`. Die Antworttexte sind dieselben wie in
  `tools.py`, damit das Modell keinen Unterschied sieht. Ein Faden je
  Verbindung, damit ein langer Befehl „bist du da?" nicht blockiert.
- **Gleichheit belegt (11.11.2026):** `tests/test_sohelper_gleichheit.py`
  schickt dieselben Befehle und Pfade durch `safety.py` und durch einen
  laufenden Ausführer (45 Fälle, Urteil **und** Text); vier Abweichungen
  kamen dabei ans Licht und wurden auf der Rust-Seite behoben (Zitatform,
  Wortlaut der Netzsperre, Meldung von `shlex`). Gegenprobe mit vier
  Verfälschungen, jede wird rot.
- **Umgestellt (11.11.2026):** `agent/tools.py` reicht die vier Werkzeuge
  über `agent/sohelper.py` an den Socket; im Dienst gibt es keinen
  Programmstart mehr. Kein Rückfall: ohne Ausführer wird nichts getan und
  der Grund genannt. `set_face` bleibt im Dienst. Der Test
  `tests/test_tools_socket.py` wird rot, sobald `tools.py` wieder
  `subprocess` kennt oder ein Werkzeug selbst liest; **offen** ist der Lauf
  am Gerät (Module 55/99 einspielen, Werkzeuge einmal benutzen, Speicher im
  Ruhezustand messen).

**Gebaut (11.11.2026, Schritt 1b).** Nutzer, Ordner, Units und
Installer-Modul stehen (`99-sohelper`, `lib/sohelper.sh`, Rückbau in
`uninstaller/steps/99-remove-sohelper.sh`): Systemnutzer
`chimera-sohelper` ohne Home und ohne Gruppen, Arbeitsordner
`/opt/chimera/sohelper` (700, Eigentum des Ausführers, geprüft statt
angenommen), Socket-Aktivierung wie beim Gateway (`/run/chimera/sohelper.sock`,
`SocketGroup=chimera`, 0660 — nur der Agent darf fragen), Dienst mit
`IPAddressDeny=any` und `InaccessiblePaths=/opt/chimera/config`, Nachweis
über einen echten `--ping` und `NRestarts=0`. Damit der Socket unter
`/run/chimera` liegt, ohne dass der Ausführer dort schreiben darf, kommt er
— wie beim Gateway — von systemd (`LISTEN_FDS`, Handle 3); die
Socket-Anbindung liegt für beide Programme in `gemein::socket`
(`von_systemd`, `binden`, `oeffnen`), damit sie nicht zweimal verschieden
prüft (Regel 10g).

**Das Binary des Ausführers liegt im Repo unter `sohelper/`** (smilez,
11.11.2026) — derselbe Weg wie beim Gateway (Regel 14, „Binary im Repo"):
`sohelper/chimera-sohelper-aarch64` mit `.sha256` und `.stand` daneben, ein
eigener Ordner statt `gateway/`, weil dort das Gateway liegt und der Name
sonst lügt. Gebaut wird in der CI (beide Programme des Workspace, ein
Lauf); abgelegt von `tools/binary-ablegen.sh <binary> --art sohelper`
(`--art tor` für das Gateway, `tools/gateway-binary.sh` bleibt als
Kurzform). Beide Programme nennen ihre Version als `<programm> <VERSION>` —
daran prüft das Werkzeug, ob Binary und Repo zusammenpassen.

**Was die Regel nicht leistet.** Die eigentliche Schranke bleiben die
Rechte des Nutzers (Regel 10r). Der eigene Prozess verhindert, dass der
Agent die Prüfung auslässt oder ändert; er verhindert keinen Fehler in den
Regeln selbst.

**Entschieden (smilez, 10.11.2026): ein eigener Nutzer, `chimera-sohelper`**
(secops helper). Nutzer, Unit und Programm tragen denselben Namen, wie bei
`chimera-tor`. Keiner der vorhandenen Nutzer kommt in Frage (am Pi
nachgesehen): `chimera` führt den Agenten aus, `chimera-tor` hat Netz und
Schlüssel, `dietpi` hat `sudo` ohne Passwort; root scheidet aus. Der
Ausführer bekommt **weniger** Rechte als der Agent: keine Hardware-Gruppen,
kein Netz, keine Schlüssel, kein `sudo`, keine Anmeldung. Ihm gehört der
Arbeitsordner — damit setzt der Kernel die Trennung durch, und das
Protokoll ist für den Agenten nicht änderbar.

**Das venv darf er benutzen, den Schlüssel nicht** (smilez, 11.11.2026):
Der Ausführer braucht den Interpreter und die Pakete des venv, damit ein
Befehl wie `venv/bin/python ...` läuft — er darf aber nicht an die
Zugangsdaten kommen. Deshalb:

- Das venv ist lesbar und ausführbar.
- Die Schlüssel bleiben in `config/.env` (`root:chimera-tor` 0640) — wie
  entschieden (5l).
- Die Unit des Ausführers bekommt `InaccessiblePaths=/opt/chimera/config`.
  Er sieht das venv, den Schlüssel sieht er nicht.
- Grund: Ein Prozess, der Befehle auf Zuruf des Modells ausführt, ist die
  falsche Stelle für Zugangsdaten. Läge der Schlüssel im venv, könnte das
  Modell ihn lesen lassen und über den Agenten nach draußen schicken —
  die Netzsperre des Ausführers macht das nur langsamer, nicht unmöglich.

**Der Arbeitsordner liegt im Installationsziel: `/opt/chimera/sohelper`**
(smilez, 11.11.2026) — „im Installationsziel von chimera in einem
Unterordner sohelper“. Er gehört dem Ausführer (700), nicht dem Agenten:
Das Elternverzeichnis gehört root, der Agent kann ihn also weder lesen noch
ersetzen. Gedächtnis, Sitzungen und Moods bleiben bei ihm
(`/home/<nutzer>/chimera/data`); was er schreiben will, schreibt der
Ausführer für ihn.

**Offen:** das Rückbau-Gegenstück (Regel 10l) — beim Deinstallieren fällt
`/opt/chimera` ohnehin weg, der Ordner ist dann Teil davon.

**Gegenprobe.**

- Die bestehenden Fälle aus `tests/test_agent.py` laufen **gegen den
  Prozess**, nicht gegen eine nachgebaute Prüfung. `shlex.split` und sein
  Rust-Gegenstück können in Randfällen verschieden zerlegen; gemessen wird
  die Menge der abgelehnten und angenommenen Befehle vorher und nachher.
- Der Dienst enthält keinen Weg mehr, einen vom Modell gewählten Befehl zu
  starten: Ein Test wird rot, sobald `agent/tools.py` wieder selbst
  startet.
- Läuft der Ausführer nicht, wird **nichts** ausgeführt und das Modell
  erfährt den Grund — kein Rückfall auf die Ausführung im Dienst.
- Speicher im Ruhezustand wird am Pi gemessen (Vergleichswert:
  `chimera-tor --dienst` mit 1,6 MB RSS, 3.11.).

---

### Regel „Jedes Werkzeug bekommt nur seine Rechte“ — die Rechte werden mitgegeben, nicht geerbt

Vorgabe smilez (12.11.2026): „Child-Prozesse, die nur die benötigten
Berechtigungen erben bzw. erhalten — das ist nicht nur für SSH richtig,
sondern für jeden Tool-Aufruf." Dem ist so; die Regel hält fest, **wie** das
gilt, damit nicht an jeder Ecke eine eigene halbe Umsetzung entsteht.

**Das Problem.** Der einfache Weg ist der gefährliche: Ein Prozess kann
alles, was er je können muss, und die Prüfung im Programm entscheidet, was er
davon *benutzt*. Damit ist die Grenze eine Zeile Code, die man vergessen
kann. Sobald ein Aufruf etwas darf, was er nicht braucht (Netz, ein fremder
Ordner, ein Schlüssel), ist das eine Einladung — ein Optionsschalter, ein
Umweg über eine Bibliothek, ein Fehler im Argument-Parsing genügt.

**Die Regel.** Ein Werkzeugaufruf erhält **genau die Rechte seiner
Fähigkeitsklasse**, und die Grenze setzt das Betriebssystem, nicht das
Programm. Drei Schichten, alle drei nötig:

1. **Welcher Prozess.** Jede Klasse hat ihren eigenen Nutzer und ihre eigene
   Unit: der Agent liest und denkt (`chimera`, kein Netz, kein root), der
   Ausführer führt aus (`chimera-sohelper`, `IPAddressDeny=any`, nur sein
   Arbeitsordner beschreibbar), das Gateway ist der einzige Netznutzer
   (`chimera-tor`, 5t-Ablagen, `MemoryMax`). Ein Prozess, der zwei Klassen
   kann, ist zwei Prozesse zu wenig.
2. **Was er erreichen kann.** Netz, Ordner und Speicher stehen in der Unit
   (`IPAddressDeny`/`IPAddressAllow`, `InaccessiblePaths`, `ReadWritePaths`,
   `ProtectSystem`, `MemoryMax`). Was dort nicht steht, gibt es für das
   Programm nicht — auch nicht über eine Bibliothek.
3. **Welche Form der Aufruf hat.** Je Werkzeug eine feste Form (Schema, feste
   `argv`, keine Shell, kein `env`-Vererbung). Die Form ist die halbe
   Berechtigung: `ssh -D 1080` ist ein anderes Recht als `ssh host cmd`, auch
   wenn beides dasselbe Programm startet.

**Berechtigung ist eine Klasse, nicht ein Aufruf.** Gemessen wird an dem, was
das Programm je braucht: dauerhafte Units je Klasse (Ausführer lokal,
Netzabruf im Gateway, Fernausführung) sind billig und schnell. Eine
flüchtige Unit **je Aufruf** lohnt nur, wo das Ziel erst im Aufruf feststeht
und der Kernel es mitbegrenzen soll — heute genau ein Fall: `ssh`. Ein
Unit-Start je `read_file` wäre Aufwand ohne Gewinn.

**Was ein Kind nie erbt.** Keine Umgebung (`Environment=` leer, nur was der
Aufruf braucht), keinen Agent-Socket, keine `.env`, keine Schlüssel, die
nicht zu seiner Klasse gehören, kein Arbeitsverzeichnis des anderen. Ein
Kind, das den Editor des Agenten oder dessen Anbieter-Schlüssel sieht, ist
eine zweite Tür.

**Einen Entscheider, nicht zwei.** Wer entscheidet, startet auch — sonst
prüft eine Stelle und eine andere führt aus (Regel „Wer prüft, führt aus").
Kinder entscheiden **nie** selbst über ihre Rechte; sie bekommen sie beim
Start.

**Gegenprobe (Regel 9):**
- (a) Ein Kind kann das, was seine Klasse nicht darf, **auch wenn es will**:
  der Ausführer erreicht 1.1.1.1:443 nicht, obwohl er es versucht
  (Unit-Riegel, nicht Programmlogik).
- (b) Kein Argument erweitert die Klasse: `ssh` mit `-D`, `-L`, `-R`, `-o
  ProxyCommand` wird abgelehnt, und das ist als Test festgenagelt.
- (c) Ein Kind bekommt kein Recht „auf Vorrat": der Ausführer sieht
  `config/` nicht, obwohl er im selben Baum läuft.
- (d) Der SSH-Läufer erreicht ein **zweites** Ziel nicht, obwohl die
  Verbindung erlaubt ist (`IPAddressAllow` nennt genau ein Ziel).

**Stand 12.11. (abends).** Gebaut und **am Ziel belegt**: Ausführer (eigener
Nutzer, kein Netz, nur Arbeitsordner; fragt vor jeder Ausführung die
Freigabe), Gateway als einziger Netznutzer mit sechs Ablagen, `web_abruf` mit
Freigabe-Prüfung, die **Host-Tabelle** (`config/ssh/hosts.json`, Web-Modul
„Fernzugriff", Vorschlags-Op `ssh_vorschlag`) und die **Fernausführung
selbst**: `op: ssh`, Deskriptor-Übergabe per `SCM_RIGHTS`, feste `argv` im
Ausführer, `chimera-fdpass`. Der Freigabe-Eintrag `ssh` hat damit seinen
Aufrufer. Die `IPAddressDeny=any`-Gegenprobe am Gerät (ssh erreicht
1.1.1.1:443 nicht) steht noch aus; sie braucht die Unit, nicht den Code.

**Was die Messung am echten `ssh` geändert hat** (12.11.2026, OpenSSH 9.9,
Sandbox mit eigenem sshd): Der erste Entwurf sagte, `chimera-fdpass` gebe
eine Zeile `fd <n>` aus und bekomme die Verbindung als `fd 3` vererbt. Beides
trifft **nicht** zu:
1. `ssh` schließt im Proxy-Kind **alle** Deskriptoren ab 3 — ein geerbtes
   `fd 3` ist dort nicht mehr offen („Deskriptor 3 ist nicht offen"). Der
   einzige Kanal, den `ssh` dem Proxy garantiert, ist **stdin** (ein
   Socketpair).
2. Die Rückgabe ist **kein Text**: der Proxy schickt den Deskriptor per
   `SCM_RIGHTS` über stdin, dazu mindestens ein Byte — ohne das Byte bricht
   `ssh` mit „mm_receive_fd: expected received 1 got 0" ab.

Deshalb holt `chimera-fdpass` die Verbindung über einen Unix-Socket beim
Ausführer ab (`<arbeit>/ssh/uebergabe.sock`, nur während des Laufs, durch
„ein ssh zur Zeit" geschützt) und reicht sie auf stdin an `ssh` weiter. Der
Netzzugang bleibt, wo er war: beim Gateway.

#### Fernausführung: `ssh` geht durch das Gateway, und nur so

Vorgabe smilez (12.11.2026): „Alles von Chimera, was ins Netz will, muss durch
das Gateway" — also auch `ssh`. Der Ausführer bleibt bei `IPAddressDeny=any`;
für den normalen Weg (`run_command "ssh …"`) bleibt `ssh` in `NETZ` und damit
gesperrt. Der **einzige** ssh-Weg ist der Auftrag `ssh` an das Gateway.

**Warum kein SSH-Client im Gateway-Prozess.** Ein Protokoll samt
Schlüsselaustausch in den Prozess zu ziehen, der die Anbieter-Schlüssel hält,
vergrößert die Fläche an der empfindlichsten Stelle, lässt sich nicht mit
`IPAddressAllow` einengen (die gilt für den ganzen Prozess, und der braucht
Internet für die Anbieter) und passt nicht unter `MemoryMax=10M`.

**Der Weg.** `op: ssh` im Gateway, und der Aufruf nennt **kein `argv`**:

```json
{"op": "ssh", "host": "radxa", "befehl": "uptime"}
```

1. `host` ist ein Eintrag der **Host-Tabelle** `config/ssh/hosts.json`
   (Adresse, Nutzer, Port, Schlüsselverweis, Hostschlüssel-Eintrag, **Rechte**
   auf dem Ziel, `herkunft`). Was nicht in der Tabelle steht oder dort nur
   als Vorschlag liegt, gibt es nicht — kein „Host unbekannt, versuch es
   trotzdem".
2. Die Freigabe entscheidet über das Ziel: `freigaben::pruefen(p, "ssh",
   Some("user@host"), jetzt)`. Vorgabe bleibt `positivliste`.
3. **Das Gateway öffnet die Verbindung** — erst nach Freigabe und Tabelle:
   ein TCP-Verbindungsaufbau auf Adresse und Port aus der Tabelle. Damit ist
   der Netzweg an genau einer Stelle, wie 5n es verlangt.
4. **Die Verbindung wird als Deskriptor weitergereicht**, nicht als Adresse:
   das Gateway schickt den offenen Socket per `SCM_RIGHTS` zusammen mit dem
   Auftrag über `/run/chimera/sohelper.sock`. Der Ausführer prüft den Auftrag
   gegen seine eigene enge Form (nur `ssh`, feste `argv`, Schlüssel**name**
   aus seinem Verzeichnis — kein Pfad, kein freies Argument) und startet:

   ```
   ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes \
       -o UserKnownHostsFile=/opt/chimera/sohelper/ssh/known_hosts \
       -o ProxyUseFdpass=yes -o ProxyCommand="/opt/chimera/bin/chimera-fdpass 3" \
       -i /opt/chimera/sohelper/ssh/keys/<name> -l <nutzer> -p <port> \
       <adresse> -- <befehl>
   ```

   `chimera-fdpass` gibt den geerbten Deskriptor als Zeile `fd 3` aus,
   `ProxyUseFdpass=yes` nimmt ihn. **ssh spricht dann über eine Verbindung,
   die es nicht selbst geöffnet hat** — und kann keine zweite öffnen, weil
   seine Unit `IPAddressDeny=any` behält. Verboten und im Test festgenagelt:
   `-D`, `-L`, `-R`, `-A`, `-o LocalCommand`, freies `-o` aus dem Modell.
5. **Wem was gehört.** Die Tabelle (Adresse, Nutzer, Port, **Schlüsselname**,
   Rechte) führt das **Gateway** — eine Wahrheit (10g). Die
   **Schlüsseldateien** liegen beim Ausführer (`/opt/chimera/sohelper/ssh/keys/`,
   Verzeichnis 0700, Dateien 0600, `chimera-sohelper`), weil er ssh startet;
   das Gateway sieht nur den Namen, nie den Schlüssel. Damit hat das Gateway
   den Netzzugang und keinen Schlüssel, der Ausführer die Schlüssel und kein
   Netz — keiner von beiden hat beides. Je Host ein eigener Schlüssel statt
   eines Generalschlüssels; passt der Hostschlüssel nicht, bricht der Lauf ab
   (kein `accept-new`).
6. Rückgabe wie bei `web_abruf`: Ausgabe gekürzt, Exitcode, Dauer, Host —
   nichts auf Platte außer der Protokollzeile der Freigabe. Beim Agenten ist
   es **ein** Werkzeug `ssh` (`{host, befehl}`) — kein `argv`, keine
   Optionen, kein Pfad.

**Warum nicht einfach eine flüchtige Unit mit `IPAddressAllow=<ziel>`?**
Das war der erste Entwurf und ist verworfen: sie lässt ssh **selbst**
verbinden (dann hat ssh Netz, und 5n wäre nur noch „mit Ausnahme"), und ein
`systemd-run` aus dem Gateway heraus braucht dbus/polkit-Rechte — ein neues
Privileg genau an der empfindlichsten Stelle. Mit der Deskriptor-Übergabe
bleibt der Netzprozess **einer**, ssh bleibt netzlos, und das Gateway
braucht keine neuen Rechte (es hat den Netzzugang ohnehin). Der Kernel-Riegel
bleibt als Gegenprobe: ssh versucht 1.1.1.1:443 → nichts.

**Wer die Tabelle pflegt (entschieden 12.11.).** Ein **Web-Modul** `ssh`
trägt Hosts ein, ändert und löscht sie; **zusätzlich** darf der **Agent
Hosts vorschlagen**. Ein Vorschlag ist ein Eintrag mit
`"herkunft": "vorschlag"` und wirkt **nicht** — erst wenn der Nutzer ihn im
Modul bestätigt, wird daraus `"herkunft": "nutzer"`. Damit kann das Modell
nützliche Ziele anbieten, ohne sich selbst einen Zugang zu öffnen (dieselbe
Grundhaltung wie bei den Freigaben: schreiben tut der Nutzer). Der Agent
bekommt dafür genau **eine** Op (`ssh_vorschlag`), die nur anlegen darf,
nie ändern, nie bestätigen, nie löschen.

**Ein Host wird mit seinem Hostschlüssel aufgenommen.** Adresse und Port
eintippen reicht nicht: das Modul lässt das **Gateway** den Hostschlüssel
einmal lesen, zeigt den Fingerabdruck, und erst wenn der Nutzer ihn
bestätigt, steht der Eintrag (mit `SHA256:…` in der Tabelle und in
`known_hosts` des Ausführers). Danach gilt `StrictHostKeyChecking=yes` —
wechselt der Schlüssel später, bricht der Lauf ab und **meldet** es, statt
still weiterzumachen. Ein Vorschlag des Agenten kann diesen Schritt nicht
auslösen: er nennt Adresse und Nutzer, den Fingerabdruck bestätigt der
Nutzer.

**Was davon steht (12.11., `rust/crates/tor/src/ssh.rs`).** Tabelle,
Web-Modul „Fernzugriff“ und die Vorschlags-Op `ssh_vorschlag` sind gebaut.
Was ein Eintrag können muss, damit er **wirkt**: `herkunft: "nutzer"` **und**
ein Hostschlüssel mit gerechnetem Fingerabdruck (`SHA256:…`). Ein Vorschlag
ist nie brauchbar, auch wenn jemand von Hand einen Schlüssel nachträgt — die
Herkunft entscheidet, nicht der Inhalt.

Eine Abweichung vom Entwurf, bewusst und benannt: **der Blob des
Hostschlüssels kommt heute vom Nutzer** (Zeile aus `ssh-keyscan -t ed25519
<adresse>`), nicht vom Gateway. Den **Fingerabdruck** rechnet trotzdem das
Gateway aus dem Blob (`SHA256:`, base64 ohne Füllzeichen) — der Nutzer
bestätigt also die Zeile, die in `known_hosts` landet, und keine getippte
Prüfsumme. Grund: den Schlüssel selbst zu lesen, hieße im Gateway einen
SSH-Schlüsselaustausch zu sprechen (Banner, KEXINIT, curve25519, Entpacken
der Hostschlüssel-Nachricht) — genau die Protokollfläche, die dieser
Abschnitt aus dem Gateway heraushalten will. Der Schlüsselaustausch gehört
deshalb zu `op: ssh` (ROADMAP): dort steht der Netzweg ohnehin, und danach
kann `ssh_schluessel_lesen` denselben Code benutzen.
`known_hosts`-Zeilen entstehen aus der Tabelle (`adresse typ blob`, bei
Port ≠ 22 als `[adresse]:port`) — eine Form, kein zweiter Ort.

**Welche Rechte auf dem Ziel (entschieden 12.11., nachgeprüft 12.11.
abends).** Alles wird angeboten, der Nutzer entscheidet **je Host**; das Feld
steht in der Tabelle. Grundlage ist `sshd(8)`, Abschnitt AUTHORIZED_KEYS FILE
FORMAT — nicht eine eigene Erfindung:

| `rechte` | `authorized_keys`-Zeile | Was es bedeutet |
|---|---|---|
| `zaun` (Vorgabe) | `restrict` | Freie Befehle, aber keine Port-/Agent-/X11-Weiterleitung, kein PTY, kein `~/.ssh/rc` — vom sshd erzwungen. Kostet auf dem Ziel **nichts**: ein Wort in derselben Zeile. |
| `force` (freiwillig) | `restrict,command="<zaun>"` | Das Ziel führt nur aus, was der Zaun durchlässt. Der vom Client gewünschte Befehl steht in `SSH_ORIGINAL_COMMAND` und wird **dort** gegen eine Liste geprüft — ohne Prüfung ist `command=` eine Weiterleitung, keine Grenze. **Einzige Stufe, die eine Datei auf dem Ziel verlangt** — darum nicht die Vorgabe. |
| `voll` | keine Optionen | Ausdrücklich gewählt und ehrlich benannt: der Schlüssel darf, was der Zielnutzer darf. Das ist das Verhalten von `ssh-copy-id`. |

**Die Aufnahme schreibt genau eine Zeile — nichts sonst.** Kein Skript, kein
Dienst, keine Konfiguration auf dem Ziel: `mkdir -p ~/.ssh` (700), Zeile
anhängen (`grep -qxF … || echo … >>`), `chmod 600`. Das ist `ssh-copy-id` mit
einer Option davor. Die Vorgabe `zaun` kostet dafür nichts (Vorgabe smilez
12.11.: „chimera soll nix auf das Ziel schreiben"); `force` verlangt eine
Datei und ist darum eine bewusste Wahl, keine Vorgabe.

`restrict` ist bewusst die Grundlage der beiden engeren Stufen: Laut Doku
schaltet es „alle Beschränkungen" ein und **nimmt künftige dazu** — eine
Aufzählung einzelner `no-*`-Optionen würde bei jedem neuen sshd-Feature
still veralten. Wo eine Weiterleitung doch gebraucht wird, kommt sie
einzeln zurück (`permitopen`, `permitlisten`, `agent-forwarding`).

**`rbash` ist keine Grenze** (und heißt deshalb nicht mehr so): Eine
eingeschränkte Shell lässt sich über jeden interaktiven Editor, `vi`,
`less`, Funktionsdefinitionen oder `BASH_ENV` aushebeln. Sie sieht nach Zaun
aus und ist keiner. Der Wert `rbash` wird abgelehnt, nicht still auf etwas
anderes abgebildet — Pre-Alpha, es gibt keinen Bestand, den das bräche.

**Den Zaun legt der Nutzer auf dem Ziel an.** In der Tabelle steht nur der
**Pfad** (`zaun: "/usr/local/bin/chimera-zaun"`), kein Code; Chimera schreibt
**nichts** auf ein Zielsystem — das wäre heimliche Codeverteilung, und der
Zaun ist genau die Stelle, an der der Nutzer die Kontrolle behalten muss.
Das Modul fragt ihn im Feld „Zaun-Pfad" ab; `ssh_host_setzen` prüft die Form
(absolut, ohne Leerraum, ohne `"` und `,` — sonst zerlegt der Pfad die
`authorized_keys`-Zeile) und **verlangt** ihn bei `force`. Damit fällt ein
fehlender Zaun beim Speichern auf und nicht erst bei der Aufnahme, die dann
schon gelaufen ist (13.11.).
Das Modul zeigt einen **Vorschlag zum Kopieren**, aus der Befehlsliste des
Hosts erzeugt; abgelegt und geprüft wird er vom Nutzer.

Form des Zauns (Beispiel, das so auf das Ziel gehört):

```sh
#!/bin/sh
# Zaun fuer den Chimera-Schluessel: nur diese Befehle, exakt.
set -eu
CMD="${SSH_ORIGINAL_COMMAND:-}"
case "$CMD" in
  uptime)       exec /usr/bin/uptime ;;
  "df -h")      exec /usr/bin/df -h ;;
  "")           echo "kein Befehl angegeben" >&2; exit 2 ;;
  *)            echo "nicht erlaubt: $CMD" >&2; exit 3 ;;
esac
```

Drei Bedingungen, sonst ist es kein Zaun: **exakter Vergleich** (kein `eval`,
keine Muster — sonst käme `uptime; rm -rf ~` durch die Musterprüfung),
**absolute Pfade** im `exec` (kein `PATH`, der etwas unterschiebt) und
**Eigentümer root, Modus 755** (sonst schreibt sich der Zielnutzer seinen
eigenen Zaun um). Unser Client schickt den Befehl als **ein** Argument
(`-- <befehl>`), darum ist der exakte Vergleich hier tragfähig und nicht nur
bequem.

Fehlt der Pfad, ist `force` nicht möglich: die Aufnahme sagt das und schlägt
`zaun` vor, statt still `voll` zu nehmen. (Ein Host ohne `rechte` gilt als
`zaun`.)

---

### Aufnahme eines Hosts: das Passwort einmal, der Schlüssel danach

Vorgabe smilez (12.11. abends): „Den ssh-Key soll Chimera am Zielgerät selbst
eintragen und sich auch in Chimera ablegen, aber so, dass der LLM-Agent den
Schlüssel nie zu lesen bekommt. Für die erste Verbindung sollen IP, Username
und Passwort reichen — aber auch das Passwort darf der Agent nie sehen, obwohl
der User es in den Prompt tippt."

**Warum das Passwort nicht in den Chat darf — und Maskieren nicht reicht.**
Der naheliegende Weg wäre, das Passwort im Prompt zu erkennen und vor dem
Modell durch einen Platzhalter zu ersetzen, die Antwort hinterher
zurückzusetzen. Das ist **kein** tragfähiger Schutz, sondern ein Netz für
Unfälle:

- **Wer maskiert, muss das Geheimnis vorher kennen.** Beim ersten Mal kennt es
  niemand — es steht in dem Moment schon im Chatverlauf, in der Sitzungsablage
  der App und in jeder Zusammenfassung.
- **Zusammenfassungen sind verlustbehaftet.** „Geh3im!" kommt als „das
  Passwort lautet Geh3im" zurück, klein geschrieben oder umformuliert; ein
  exakter Treffer-Tausch scheitert daran **still**.
- **Der Rückweg hält das Geheimnis am Leben:** die Stelle, die die Antwort
  zurückstopft, muss den Klartext über die ganze Runde im Speicher halten.
- **Der Agent-Weg ist der Modell-Weg.** Sobald das Modell den Aufruf
  orchestriert, wäre das Passwort ein Werkzeugargument — also im Kontext.

Deshalb gilt: **Das Geheimnis kommt nie in den Chat, sondern in einen Kanal,
der nicht zum Modell führt.** Das Maskieren bleibt als **zweites Netz**
bestehen (die Prompt-Schicht kann die bekannten Geheimnisse aus
`config/geheim/` laden und Treffer ersetzen, bevor etwas hinausgeht) — aber es
ist die Ausnahme, nicht der Mechanismus.

**Der eine Kanal, viele Türen.** Die Ablage ist `config/geheim/ssh/<host>`
(0600, `chimera-tor`); der Agent kann sie nicht lesen (`InaccessiblePaths`
auf `config/`, und er läuft als `chimera`, nicht als `chimera-tor`). Eingeben
darf der Nutzer sie über **jede** seiner Türen — dieselbe Datei, dieselbe
Prüfung:
1. **Web-Modul „Fernzugriff"** (Passwortfeld je Host, Aufnahme-Knopf) —
   in-process, ohne Socket. Die API gibt den Wert **nie** zurück; sie meldet
   nur „abgelegt" bzw. `geheim: true` in der Liste, und das Feld leert sich
   nach dem Absenden (gebaut 12.11.: `POST /api/ssh/geheim`,
   `/api/ssh/geheim-loeschen`).
2. **Kommandozeile** auf dem Gerät oder über SSH dorthin:
   `chimera-tor --geheim-ssh <host>` liest das Passwort **ohne Echo** vom
   Terminal (kein `argv`, keine Shell-Historie) und schreibt die Datei.
3. **Telegram**: ein Befehl, den das Gateway verarbeitet (`/passwort <host>`),
   nicht der Agent. Die Nachricht wird nach dem Schreiben **gelöscht** und ihr
   Text nie protokolliert.
4. **Sprache (später, mit Whisper)**: derselbe Kanal wie Telegram — das
   Transkript wird verworfen, nur das Geheimnis landet in der Ablage.

**Ein Schlüssel, den der Agent nie sieht.** Er entsteht im **Ausführer**
(`ssh-keygen`, ed25519), direkt in `/opt/chimera/sohelper/ssh/keys/<host>`
(0600, `chimera-sohelper`). Der Ordner ist 0700 und gehört dem Ausführer; der
Agent kann ihn nicht betreten. Zusätzlich bekommt die Agent-Unit
`InaccessiblePaths=/opt/chimera/sohelper` — zwei Riegel statt einem. Der
**öffentliche** Teil wird im Modul angezeigt (kopierbar), damit der Nutzer ihn
auch von Hand eintragen kann.

**Der Ablauf einer Aufnahme** (`op: ssh_aufnahme`, nur für Hosts mit
`herkunft: nutzer` — ein Vorschlag des Agenten ist nicht aufnehmbar):
1. Passwort aus der Ablage lesen; fehlt es → `passwort_fehlt` mit dem Hinweis,
   **wo** es eingegeben wird (nie: „tippe es hier").
2. Freigabe prüfen wie bei `op: ssh` (Ziel `user@host`), Gateway öffnet die
   TCP-Verbindung, Deskriptor an den Ausführer. Der Netznutzer bleibt einer.
3. Das Passwort geht **über den Socket** an den Ausführer (er kann die
   Geheim-Ablage des Gateways nicht lesen, und das Gateway kann nicht in
   seinen Ordner schreiben — 0700 `chimera-sohelper`; ein erster Entwurf mit
   „Gateway legt die Datei ab" war so nicht ausführbar). Der Ausführer
   schreibt es selbst als `<arbeit>/ssh/.passwort` (0600) für den
   Askpass-Helfer und **löscht die Datei nach dem Lauf**, auch bei Abbruch.
   Das Passwort steht damit in genau einem Puffer mehr als beim Ablegen — und
   in keiner Datei, die jemand anderes lesen kann.
4. Der Ausführer startet `ssh` mit **Passwort-Anmeldung ohne TTY**:
   `SSH_ASKPASS` + `SSH_ASKPASS_REQUIRE=force` + `setsid`; der Askpass-Helfer
   liest die Passwortdatei. **Gemessen 12.11.2026 (OpenSSH 9.9):** das
   funktioniert ohne Terminal; `sshpass -p …` scheidet aus, weil es das
   Passwort sichtbar in `ps` hinterlässt (gemessen: drei Treffer).
   `StrictHostKeyChecking=no` gilt **nur für diesen einen Lauf**, mit eigener
   `known_hosts`; danach ist es aus.
5. Hostschlüssel aus dieser `known_hosts` nehmen, Fingerabdruck rechnen,
   Schlüsselpaar erzeugen, öffentlichen Teil in derselben Sitzung eintragen:
   `mkdir -p ~/.ssh`, `chmod 700`, Zeile mit den Rechten-Optionen anhängen,
   `chmod 600`.
6. Antwort: Fingerabdruck, öffentlicher Schlüssel, Zeile, Ergebnis. Passwort-
   datei und temporäre `known_hosts` werden gelöscht; **das Passwort wird
   sofort aus der Ablage entfernt** (Vorgabe smilez 12.11.: „sofort löschen").
7. **Erst der Nutzer macht den Eintrag daraus:** das Modul zeigt
   Fingerabdruck und öffentlichen Schlüssel, er bestätigt → `ssh_host_setzen`
   schreibt `hostschluessel` und Herkunft (wie heute). Eine Aufnahme schreibt
   selbst **nichts** in die Tabelle; sie liefert nur, was zu bestätigen ist.

**Was der Agent dabei kann.** Er kann einen Host vorschlagen und — wenn der
Nutzer ihn schon bestätigt hat — die Aufnahme anstoßen; er sieht weder
Passwort noch Schlüssel, und die Antwort der Aufnahme ist für ihn eine
Erfolgsmeldung ohne Geheimnis. Ein **neues** Passwort kann er nicht eingeben.

---

### Regel „Mojo“ — jeder Fehler wird bemerkt, mit Ursache benannt, versucht, nachgeprüft und laut gemeldet

Vorgabe smilez (1.11.): Die Dienste starten nach dem Boot zuverlässig, versuchen
es bei einem Fehler erneut, protokollieren, was schiefging, und werfen **laut
einen Fehler**, wenn auch der Neuversuch scheitert. Das Muster stammt aus
Mojo (smilez' Projekte `rag4ll` und `llm_cross-compiler_framework`); gelesen,
gemessen und verglichen in `docs/research/MOJO.md`. Nichts wird kopiert.

Befund, der die Regel begründet: Ein Dienst, der die Startgrenze (Regel 10p)
erreicht, bleibt `failed` und meldet sich bei **niemandem**; am Gerät lief der
Dienst 22 Stunden ohne Sitzungs-Socket, weil `chimera-sitzung.socket` nach einem
Installerlauf inaktiv geblieben war.

1. **Eine Regelmaschine, kein Modell.** `chimera-tor --mojo` führt feste
   Prüfungen aus und fragt nie ein Sprachmodell. Es läuft offline und braucht
   weder Netz noch Anbieter.
2. **Oracle und Miracle.** Ohne Flag **liest** es nur und ändert nichts.
   `--miracle` führt die Reparaturen der Stufe 1 aus. `--json` schreibt den Bericht
   maschinenlesbar (Weboberfläche, Skripte).
3. **Jeder Befund nennt seine Ursache** (smilez, 1.11.), auch „nicht
   reparierbar“. Eine Ursache ist **gemessen und belegt**, nie geraten, und
   kommt aus einer von drei Quellen, in dieser Reihenfolge:
   a) **Was systemd selbst sagt** (`Result`, `ExecMainStatus`), am Gerät
      gemessen: Status 203 Programm fehlt oder ist nicht ausführbar, 217 der
      Nutzer fehlt, 226 ein Pfad in `ReadWritePaths=` fehlt, 200 das
      Arbeitsverzeichnis fehlt; Ergebnis `resources` eine Datei für
      `EnvironmentFile=` fehlt, `timeout` der Start dauert zu lange, `signal`
      der Prozess wurde beendet (Signal 9: gekillt, häufig Speichermangel),
      `dependency` eine Voraussetzung ist gescheitert, „Start request repeated
      too quickly“ die Startgrenze ist erreicht. Zu jeder Zahl kennt Mojo den
      Weg: Ordner anlegen, Nutzer anlegen, Rechte setzen, Datei anlegen.
   b) **Die Ausgabe des Programms** bei Status 1, denn nur das Programm weiß,
      warum es endete. Mojo kennt eine Liste fester Muster („Address already
      in use“, „Permission denied“, „No such file or directory“,
      `ModuleNotFoundError`, „Name or service not known“) und je Muster die
      Ursache und den Weg.
   c) **Der Zustand des Systems:** Speicherkarte (SD) voll oder Arbeitsspeicher (RAM) knapp (mit der **genauen Zahl, die
      fehlt**, und der Angabe, welcher von beiden gemeint ist), Uhr falsch,
      Gateway oder Anbieter nicht erreichbar, Socket inaktiv.
   Passt keine Quelle, sagt Mojo ausdrücklich **„Ursache nicht bestimmbar“**
   und liefert die **Rohdaten** mit (Ergebnis, Status, die letzten Zeilen des
   Journals, Zustand der abhängigen Dienste). Das ist ein Befund, kein
   Schweigen. Gibt es für die Ursache keine Reparatur in Software (leere Karte,
   defekter Baustein), steht dort, **was der Mensch tun muss**. Mojo braucht
   dafür nie ein Sprachmodell. Ursache und Weg stehen im Protokoll, im Bericht
   und auf der Oberfläche, **bei jedem Befund**.
   **Ort der Prüfung:** Das Journal des Systems ist für Nutzer ohne Gruppe
   `systemd-journal` nicht lesbar (am Gerät gemessen, auch nicht für
   `chimera-tor`). Mojo läuft deshalb als eigene Unit mit dem Recht zum Lesen
   (Gruppe `systemd-journal`), nicht im Dienst des Agenten (Regel „Agent ist ein
   eigener Nutzer“, 10r).

4. **Ein Befund** trägt Schwere (`ok`, `info`, `warn`, `error`), Subsystem,
   einen **stabilen Code** (`dienst.gescheitert`, `socket.inaktiv`), Meldung,
   Hinweis und optional eine Reparatur samt Stufe. Der Exitcode folgt dem
   schlimmsten Befund: 0, 1 (Warnung), 2 (Fehler).
5. **Stufen.** 1 sanft und lokal (`reset-failed`, Dienst oder Socket neu
   starten), 2 Komponente neu, 3 Installer neu. **Stufe 1 und 2 laufen von allein** (Dienst oder Socket neu starten; fehlende
   Python-Pakete nachladen, dazu Installer Schritt 50 und danach Neustart des
   Dienstes); **Stufe 3 nie von allein**, nur auf ausdrücklichen Wunsch des
   Nutzers über die Oberfläche. Ein Neustart wird nur versucht, wo er helfen
   kann; bei fehlendem Programm, fehlendem Nutzer oder fehlendem Pfad gibt es nur
   Ursache und Weg.
6. **Die Nachprüfung ist die Wahrheit.** Nach jeder Reparatur laufen dieselben
   Prüfungen noch einmal. Taucht derselbe Code wieder auf, ist der Befund
   **unreparierbar**, wird nicht in einer Schleife wiederholt und wird laut
   gemeldet. Der Rückgabewert der Reparatur zählt nicht (Regel 8a, stiller
   Erfolg).
7. **Eine Reparatur gleichzeitig**, per Sperrdatei in `state/`. Eine zweite wird
   abgelehnt, nicht gewartet.
8. **Die Prüfungen sind erweiterbar mit einer Stelle:** `impl Pruefung` plus
   eine Zeile in `pruefungen()` (wie die Sonden in `status.rs`); ein Test je
   Prüfung mit Gegenprobe.
9. **Das Netz ist ein eigener Bereich** (Vorgabe smilez, 3.11.): Mojo prüft,
   ob überhaupt Netz da ist — TCP-Probe auf `8.8.8.8:53` und `1.1.1.1:443`,
   nicht ICMP (das ist in manchen Netzen gefiltert). Fehlt es, ist die
   Reparatur **WLAN neu starten**: `nmcli radio wifi off/on`, dann
   `wpa_cli -i wlan0 reconfigure`, dann — nur wenn sie laufen —
   `wpa_supplicant@wlan0`, `ifup@wlan0`, `networking` neu starten, zuletzt
   `ip link set wlan0 up` und `ifup wlan0`. Jeder Schritt darf fehlen; das
   Ergebnis zählt, nicht der Exitcode eines Befehls.
   Aufruf gezielt mit `--mojo --miracle --bereich netz` — der Installer fragt so
   nur das Netz ab, statt bei jedem Netzproblem den ganzen Systemcheck zu
   fahren. Ein unbekannter Bereich ist ein Fehler, kein stilles Nichts-Tun.
10. **Der Installer nutzt das** (`installer/lib/network.sh`): Bei HTTP 404
    wird erst geprüft, ob Netz da ist; ist es weg, steigt Mojo ein
    (`--bereich netz`, sonst die vollständige Prüfung), danach folgt ein
    neuer Versuch. Erst nach drei Runden ist es ein Befund. Grund (am Pi
    2.11.): 20 Versuche à 4,5 s = 91 Sekunden Stillstand im Fortschrittsbalken,
    wenn der Dateiname im Release nicht stimmt.
11. **Die ersten Prüfungen:** Dienste `chimera`, `chimera-tor`,
   `chimera-hardware` (failed, zu viele Neustarts); beide Sockets (inaktiv trotz
   aktiviert); Hardware-Erkennung; Protokoll auf der Karte schreibbar; Speicher
   (`MemAvailable`); Anbieter (Gateway erreichbar, Ollama erreichbar, ein Modell
   gewählt). Die Reparatur „Socket nachziehen“ heißt: Dienst stoppen, Socket
   starten, Dienst starten, dann prüfen, ob `/run/chimera/sitzung.sock` da ist.
10. **Die Meldeunit.** `chimera-mojo@.service` hängt per
   `OnFailure=chimera-mojo@%N.service` an `chimera`, `chimera-tor` und
   `chimera-hardware`. **Gemessen am Gerät (systemd 257): `OnFailure=` feuert bei
   jedem Fehlschlag, nicht erst nach Erreichen der Startgrenze.** Die Unit muss
   darum Zwischenfehler von der Aufgabe trennen: Steht der Dienst noch auf
   `activating`, wird nur protokolliert; steht er auf `failed`, ist es die
   Aufgabe, und das wird **laut**. Dienstname, Ergebnis und Status kommen aus
   `MONITOR_UNIT`, `MONITOR_SERVICE_RESULT` und `MONITOR_EXIT_STATUS`.
11. **Ein Zeitgeber** (`chimera-mojo.timer`, nach dem Boot und stündlich),
    weil ein Dienst, der nie scheitert, aber still falsch läuft (Socket aus),
    kein `OnFailure=` auslöst.
12. **Laut heißt:** Journal mit Stufe `<3>`, der Bericht in
    `state/mojo-letzter.json`, eine Zeile im Protokoll **auf der Karte**
    (überlebt den Neustart), LED rot und Name des Dienstes in der Statuszeile,
    solange ein Befund offen ist, und die Anzeige im Status-Modul der
    Weboberfläche. Eine Meldung über Telegram folgt, sobald die Telegram-Tür im
    Gateway steht.
13. **Schwärzung.** Befunde gehen in Protokolle und Meldungen; Heimverzeichnis,
    LAN-Adressen und Schlüssel erscheinen nie (Regel 13). Journalinhalt wird
    **nicht** in den Befund eingebettet, nur Zahlen.
**Ein Lauf zur Zeit, und ein Cache antwortet nur auf seine Frage**
(11.11.2026, nach einem Code-Review). Zwei Sätze, die zusammengehören, weil
beide dasselbe verhindern: dass zwei Stellen dieselbe Wahrheit verschieden
sehen.

- **Eine Reparatur zur Zeit — der zweite wartet, statt auszufallen.**
  Timer, `OnFailure=` und Installer können gleichzeitig `--miracle` starten.
  Ohne Sperre überschreiben sie sich beim Hochzählen in
  `state/mojo-versuche.json` (Lost Update). Deshalb nimmt ein reparierender
  Lauf eine Sperre auf `state/mojo.lock`. Ist sie belegt, **wartet er bis zu
  fünf Minuten** (`CHIMERA_MOJO_FRIST` überstimmt) und kommt danach dran
  (smilez, 11.11.2026).
  **Aber er repariert dann nicht seine alten Befunde:** Nach dem Warten wird
  frisch gemessen, und der Oracle-Cache wird nicht befragt — was der andere
  erledigt hat, ist erledigt, und ein Befund von vorher wäre eine Behauptung
  über einen Zustand, den es nicht mehr gibt.
  Ist die Sperre nach der Frist noch belegt, meldet er das und endet mit 75
  (`EX_TEMPFAIL`).
- **Innerhalb eines Laufs ist es ohnehin nacheinander:** `mojo::lauf` geht
  die offenen Befunde in einer Schleife durch, wartet, sammelt **neu** und
  beginnt die nächste Runde — nie zwei Reparaturen gleichzeitig.
- **Ein Cache antwortet nur auf die Frage, die er beantwortet hat.** Das
  Oracle-Ergebnis gilt für die Prüfungen, die gelaufen sind. `--bereich netz`
  fragt etwas Engeres; ein „alles in Ordnung" von vorhin beantwortet das
  nicht. Ist ein Bereich genannt, wird der Cache **nicht** befragt — oder er
  trägt den Bereich mit, und es wird verglichen. Ein Cache, der eine größere
  Frage beantwortet als gestellt wurde, ist eine stille Falschaussage.

14. **Nicht Teil dieser Regel:** Reparaturpläne mit Prüfsumme und berechneter
    Klasse (kommen mit der Freigabe durch den Nutzer in der Oberfläche, Regel
    5v), Reparaturen der Stufen 2 und 3, Fragen im Terminal (das Gerät hat
    keins).

**Gegenprobe (Regel 9):** Einen Wegwerf-Dienst mit denselben Neustartwerten, der
immer scheitert; der Bericht muss nach der Aufgabe `error` mit
`unreparierbar` zeigen, die Befunddatei muss existieren und die Zeile auf der
Karte muss stehen. Dazu den Socket von Hand stoppen: `--miracle` muss ihn
nachziehen, und die Nachprüfung muss `ok` zeigen.

## 11. Headless

Chimera hat **keine grafische Oberfläche.** Es gibt den 240×280-Bildschirm
mit dem Gesicht und zwei Bedienwege (Telegram, Sprache). Ein Desktop hätte
darin keine Aufgabe und würde auf beiden Zielboards Reserven verbrauchen,
die Renderer und Sprachmodelle brauchen.

**Betriebssystem ist DietPi**, auf beiden Boards — schlank und ohne
mitgeliefertes Desktop-Gepäck. Auf dem Radxa Zero 3W ist das kein
Geschmacksurteil: Radxas offizielle Abbilder sind KDE- und XFCE-Varianten,
und ein Desktop macht dieses Board für den eigentlichen Zweck unbrauchbar
langsam.

Sollen Einstellungen im Browser bearbeitbar sein, wird das eine **schlanke
Web-Oberfläche** auf einem lokalen Port — HTML und ein Formular, kein
X-Server, kein Framework-Gebirge. Sie ist Zubehör, nicht Voraussetzung:
Chimera muss ohne sie vollständig einsatzfähig sein, konfigurierbar über
`.env` und Installerfragen.

---

## 12. Hardware

- **Raspberry Pi Zero 2 W (512 MB)** — Entwicklungsziel
- **Radxa Zero 3W** — Portierungsziel, mehr Reserven
- **DietPi** auf beiden, headless (Abschnitt „Headless")
Begründung und Grenzen in `docs/HARDWARE.md`.
- **Whisplay HAT V2 — ausschließlich.** Auf V1 führt die Button-Leitung
  5 V; ein Tastendruck kann das Board stromlos schalten. Herstellerwarnung.
- LCD 240×280, ST7789-kompatibel, SPI bis 100 MHz
- WM8960 bzw. ES8389 Codec, Mikrofon und Lautsprecher onboard
- 1 Button, RGB-LED

Lastbetrachtung: Renderer (15 FPS) und Sprachmodelle laufen bei Noisy
bereits gemeinsam auf einem Zero 2 W; der Agent wartet überwiegend auf
I/O. Machbar, aber eng — siehe Architekturregel 5 und `docs/HARDWARE.md`.

---

## 13. Keine Secrets im Repo

Tokens, Zugangsdaten, SSIDs, Gerätenamen und lokale Pfade gehören nicht
in die Versionsverwaltung. Konfiguration liegt als `*.example` mit
Platzhaltern vor; echte Werte erzeugt der Installer.

Nicht hinein gehören außerdem: **IP-Adressen aus privaten Netzen**, MAC-
Adressen, Heimnetz-Hostnamen und private Mailadressen. Für Commits gilt
ausschließlich die GitHub-noreply-Adresse.

### Architekturregel 13 — Ein Stand kommt nur über den Installer auf ein Gerät

Der Installer ist der einzige Weg, auf dem Code auf ein Gerät kommt:
`chimera-install` liest aus `/opt/chimera/source`, Modul 50 kopiert den
Baum nach `/opt/chimera/productive/code` und hält die Prüfsumme fest,
Modul 00 schreibt `state/quelle-commit`.

**Kopieren per `scp` in `productive/code` ist verboten.** Was dort von Hand
landet, kennt `source/` nicht; der nächste Boot-Abgleich
(`chimera-hardware.service` → `chimera-install --hardware`) kopiert
`source/` darüber und rollt es zurück — im Betrieb lautlos, weil der
Dienst mit dem alten Code weiterläuft (4.11.2026: vier Commits, bemerkt
nur am fehlenden „(Ruhe: 2)" im Protokoll).

**Nach grünem Funktionstest wird committet und eingespielt, in dieser
Reihenfolge, im selben Arbeitsgang.** Ein Stand, der nur auf dem Gerät
liegt, ist kein Stand; ein Commit, den kein Modul einspielt, ist ein
offenes Ende (Abschnitt „Tests" in `docs/INSTALLER.md`).

Nachweis: `tools/abgleich.sh --erwartet <commit>` auf dem Gerät —
Quellbaum, eingespielter Stand und festgehaltener Commit müssen gleich
sein.

### Architekturregel 13a — Vor jedem Push wird geprüft, und die Prüfung beweist ihre Sehfähigkeit

„Vor jedem Push scannen" allein genügt nicht — ein Scan, dessen Umfang
jedes Mal neu aus dem Kopf gewählt wird, prüft jedes Mal etwas anderes.
Die Prüfung läuft deshalb als Werkzeug mit festen Mustern, und zwar über
den Arbeitsbaum, die Commit-Nachrichten und die Urheberadressen; beim
ersten Push eines Repos und nach jedem Umschreiben der Historie auch über
jede frühere Dateifassung.

**Das Werkzeug liegt bewusst außerhalb des Repos** und ist in
`.gitignore` gesperrt. Es nennt die Suchmuster und damit die Form der
Werte, die es schützen soll — welche Präfixe die Tokens haben, welcher
Adressbereich das Heimnetz ist. Das ist eine Landkarte für jeden, der
sucht, und gehört nicht in eine öffentliche Historie. Hier steht die
Pflicht, nicht die Umsetzung.

**Und die Prüfung prüft sich selbst.** Die erste Fassung meldete „sauber"
für ein Repo, in dem eine Heimnetz-Adresse lag: `grep --exclude-dir` gibt
es in BusyBox nicht, der Aufruf brach ab, das leere Ergebnis galt als
Abwesenheit von Funden. Das ist Regel 10j in ihrer teuersten Form — wer
einem Scanner glaubt, der nichts sehen kann, pusht das Geheimnis selbst.

Deshalb läuft vor jeder Suche jedes Muster gegen einen bekannten Köder,
**durch dieselbe Funktion wie der echte Lauf**. Findet ein Muster seinen
Köder nicht, bricht die Prüfung ab, statt zu beruhigen. Ein eigener
Selbsttest mit eigenem Suchaufruf wäre wertlos: Genau der war grün,
während der echte Scan blind war.

Was in der Historie gefunden wird, ist nicht durch Löschen behoben. Der
Wert wird **widerrufen** und als verbrannt behandelt; erst danach wird
die Historie umgeschrieben.

---

## 14. Zwei Sprachen

### Architekturregel 14 — Was dauernd läuft und nicht auf das Modell wartet, ist Rust

Chimera ist künftig zweisprachig, mit einer klaren Grenze:

| Teil | Sprache | Grund |
|---|---|---|
| **Gateway** (5n) | Rust | läuft dauernd, Obergrenze 10 MB, hält Schlüssel |
| **Renderer + Paneltreiber** (Regel 7) | Rust, Stufe 2 | 15 Bilder/s, heute der Großteil von 27 % CPU |
| Agent, Werkzeuge, Moods, Gesichter als Pakete (8b) | Python | wartet 60–200 s auf das Modell; die Werkzeuge und die vom Modell angelegten Pakete leben davon, dass es Python ist |
| Installer, Selbstupdate | Shell (wie heute) | läuft als root, selten |

**Warum nicht alles in Rust (oder Go):** Gemessen am Pi braucht der
Dienst 48 MB und 27 % CPU, fast nur durch den Renderer. Die
Agentenschleife verbringt ihre Zeit im Warten auf das Modell. Ob sie
2 ms oder 0,2 ms rechnet, merkt man nicht. Ein Umbau des gesamten
Agenten (rund 1.800 Zeilen, dazu Moods mit 1.300) kostet viel und bringt
an der spürbaren Stelle nichts. **Go** bringt gegenüber Rust keinen
Vorteil, sondern eine zweite Toolchain. Es bleibt bei einer.

**Grenzen zwischen den Sprachen:**
- Python ↔ Gateway: der Unix-Socket aus 5n, eine JSON-Zeile hin, eine
  zurück.
- Python ↔ Renderer: Shared Memory für den Zustand (Muster aus Noisy,
  Regel 7). Den Framebuffer besitzt allein der Renderer-Prozess.
- Kein FFI (PyO3 o. ä.). Prozessgrenzen sind messbar (RSS je Prozess,
  10q), abstürzende Teile reißen den anderen nicht mit (10p), und jede
  Seite lässt sich allein testen.

**Gebaut wird nie auf dem Gerät.**
- Ziel: `aarch64-unknown-linux-musl`, **statisch** gelinkt. Damit gibt
  es keine glibc-Abhängigkeit, und dasselbe Binary läuft auf DietPi,
  Debian und Armbian (10a, Board und Betriebssystem bleiben getrennte
  Achsen). Später kommt `armv7` dazu, falls ein 32-Bit-Board in die
  Profiltabelle (10c) aufgenommen wird.
- Gebaut und geprüft wird in der **CI** (GitHub Actions) — bei jeder
  Änderung an `rust/` oder `VERSION`. Dort läuft das Binary auch, auf einem
  arm64-Runner: ein Artefakt, das nie gestartet wurde, ist eine Behauptung.
  **Veröffentlicht wird nur auf Wunsch** (smilez, 11.11.2026): Der
  Installer nimmt das Binary aus `gateway/` im Repo und braucht kein
  Prerelease. Gebraucht wird eines nur zum Testen; dann von Hand mit
  `workflow_dispatch` und `prerelease: true`. Das Tag heißt
  `rust-<kurzer commit>`, nie `vX.Y.Z` — Pre-Alpha bleibt ungetaggt, und
  die Release-Kanäle (höchstes `vX.Y.Z`) ignorieren es.
- **Welches Binary — entschieden (smilez, 10.11.2026):**
  1. **Der Name ist fest und sprechend** und ändert sich nie. Ein Name aus
     dem Commit wechselt mit jedem Commit und sagt niemandem etwas (Regel
     „Sprechende Namen“).
  2. **Gebaut wird für jedes Release und bei Bedarf für Tests auf der
     Hardware (chimera-pi)** — nicht bei jeder Änderung an `rust/`. Ein
     Doku-Commit braucht kein neues Binary und darf keines verlangen.
  3. **Für ein Release wird vorkompiliert;** der Nutzer holt es nur ab.
  4. **Ein Zip bringt sein Binary mit, und der Installer nimmt immer
     dieses.** Wer das Repo als Zip holt und den Installer startet, braucht
     für das Gateway kein Netz — nur für die Abhängigkeiten, die der
     Installer selbst lädt.

  **Gebaut (11.11.2026):** Schritt 55 nimmt das Binary aus dem Startbaum,
  prüft Prüfsumme, Architektur, Laufprobe und Version und legt es ab — kein
  Netz, kein Commit. Am Pi belegt: Modul 55 in 1 s, Lauf ohne Befund.
  Eine neue Fassung legt `tools/gateway-binary.sh` ab (Prüfsumme und Stand
  dazu). Das frühere Prerelease-Verfahren (`rust-<commit>`) ist damit
  abgelöst.

  **Entschieden (smilez, 10.11.2026): `gateway/chimera-tor-aarch64`.**
  Das Binary liegt in einem eigenen Ordner `gateway/` in der Repo-Wurzel
  (klein geschrieben wie `docs/`, `rust/`, `installer/`); der Dateiname
  bleibt der, den Code und CI schon benutzen. Daneben zwei kleine Dateien,
  beide von der CI bzw. vom Ablege-Werkzeug geschrieben:
  `chimera-tor-aarch64.sha256` (Prüfsumme, wie heute am Release) und
  `chimera-tor-aarch64.stand` (`<commit> <hash des rust/-Baums> <version>`
  — derselbe Aufbau wie `state/rust-stand`). Der Ordner liegt außerhalb von
  `rust/`, damit der Hash des Rust-Baums unberührt bleibt.

  **Der Installer meldet den Unterschied, bricht aber nicht ab** (smilez,
  10.11.: „ja"): Ist der `rust/`-Baum im Startbaum neuer als der, aus dem
  das Binary gebaut wurde, steht das im Protokoll; das Binary bleibt
  trotzdem liegen und der Exitcode ändert sich nicht. Zwischen zwei
  Fassungen ist das der Normalfall.

  **Schritt 55 braucht damit kein Netz:** Er nimmt das Binary aus dem
  Startbaum, prüft Prüfsumme, Architektur, Laufprobe und Version und legt
  es ab. Kein Prerelease, kein Commit, kein `state/quelle-commit` — eine
  frische Installation aus einem Zip hat damit ein Gateway.

  **Abgelegt wird eine neue Fassung mit einem Werkzeug**
  (`tools/gateway-binary.sh`): Es kopiert ein gebautes Binary, schreibt
  Prüfsumme und Stand daneben und prüft vorher, dass es läuft und die
  `VERSION` der Quelle nennt. Die CI baut das Binary auf `ubuntu-24.04-arm`
  und führt es dort aus (Regel 14); das Ablegen ist ein Commit von uns oder
  ein CI-Lauf.
- **Ablage:** `/opt/chimera/bin/chimera-tor`, Besitzer root, Modus 755,
  Manifest-Art `datei` mit der Prüfsumme als Angabe. Rückbau 55 entfernt
  die Datei, `bin/` nur, wenn sie leer ist. Der Schritt startet nichts;
  Nutzer, Unit und Socket kommen mit dem Gerüst (Phase 4d, Schritt 2).
- Lokale Entwicklung: rustup stable (gemessen 1.99.1) in der Sandbox,
  1:29 min für den Release-Build der Probe. **Nicht** Alpines `cargo`
  (1.83): Das kann `edition2024` nicht, das aktuelle Crates verlangen.
- Release-Profil: `opt-level = "s"`, `lto = true`,
  `codegen-units = 1`, `panic = "abort"`, `strip = true`.

**Abhängigkeiten werden genannt, nicht gesammelt.** Für das Gateway
reichen: `ureq` mit rustls (kein OpenSSL, keine Systembibliothek),
`tiny_http`, `serde`/`serde_json`. Kein async-Laufzeitsystem (tokio).
Bei wenigen gleichzeitigen Verbindungen auf einem Zero kosten Threads
weniger als ein Executor. Ein neues Crate kommt mit Begründung in diese
Liste. `Cargo.lock` wird eingecheckt, und die CI prüft mit
`cargo deny` Lizenzen (Regel 1: nichts GPL-Inkompatibles im MIT-Binary)
und bekannte Schwachstellen.

**Tests:** `cargo test` in der CI neben den Python-Tests. Regeln 8a und 9
gelten unverändert. Ein Test, der eine Python-Formel in Rust
nachrechnet, prüft nichts. Beim Umzug des Renderers wird **Bild gegen
Bild** verglichen (gleicher Zustand, gleiche Pixel innerhalb einer
Toleranz), nicht Code gegen Code.

**Umzug in Stufen, jede für sich lauffähig:**
1. Gateway (neu, ersetzt `provider/` und `bot/` im Dienst).
2. Paneltreiber und Renderer. Der Python-Renderer bleibt, bis der
   Bildvergleich grün ist, und wird erst danach entfernt (10h, nichts
   Halbes liegen lassen).


### Zuordnung für Briefkasten, Sitzung, Gedächtnis und Root

Maßstab ist
Regel 14: Was dauernd läuft, Rechte hält oder Daten verwaltet und dabei
nicht auf das Modell wartet, wird Rust.

| Teil | Sprache | Begründung |
|---|---|---|
| Briefkasten (5o) | **Rust** | läuft dauernd, hält fremde Post, prüft Token |
| Wächter: Gewicht messen (8d) | **Rust**, im Briefkasten-/Sitzungsdienst | reine Zählung von Token und Bytes, läuft nach jedem Turn |
| Sitzungsablage: `verlauf.jsonl` anhängen, `nachlesen`, Wechsel, Tarball, Löschen nach 3 Tagen (8d) | **Rust**, eigenes Binary `chimera-sitzung` | Dateiverwaltung mit Prüfungen. `tar` und `zstd`/`gzip` als Crates, damit kein externes Programm fehlen kann. |
| Root-Helfer `chimera-hand` (10s) | **Rust** | läuft als root; kleiner Code mit klaren Typen ist hier ein Sicherheitsgewinn |
| Gedächtnis: Marker zählen, Vollständigkeit prüfen, Dateien rollen (8c) | **Rust**, im Sitzungsdienst | deterministisch, prüfbar ohne Modell |
| Gedächtnis: der Text der Zusammenfassung (8c) | **Python** (Agent) | ist ein Modellaufruf; der Agent fragt, Rust prüft das Ergebnis |
| Übergabe schreiben (8d) | **Python** (Agent) | Inhalt kommt vom Modell |
| Agentenschleife, Werkzeuge, Moods, Gesichter (8b) | **Python** | wartet auf das Modell, lebt von Python (Regel 14) |

Folge: Neben Gateway und Renderer entstehen in Rust der Briefkasten,
`chimera-hand` und die Sitzungsablage. Alle liegen in **einem**
Cargo-Workspace (`rust/` im Repo), mit gemeinsamen Crates für Socket-
Protokoll und Protokollierung. Gebaut wird in einem einzigen CI-Lauf.

Die Sitzungsablage ist ein eigener Dienst `chimera-sitzung`.
Der Briefkasten hält **fremde** Daten (`chimera-post`), die Sitzung
**eigene**. Getrennte Nutzer bedeuten, dass ein Fehler im Briefkasten
nicht an den Verlauf kommt.

---

## 15. Befehle

### Architekturregel 15 — Jeder Befehl steht in der CLI-Referenz, und ein Test hält sie wahr

`docs/CLI.md` listet alle Befehle, Optionen und Umgebungsvariablen nach
Kategorie, zweisprachig. Sie ist **geprüft, nicht gepflegt**:
`tests/test_cli_doku.py` ruft die Programme mit `--help` auf und vergleicht in
beide Richtungen. Eine Option, die das Programm kennt und die Doku nicht, lässt
den Test rot werden; ebenso eine in der Doku, die es nicht gibt. Gleiches gilt
für jede Variable in `.env.example`. Was geplant, aber noch nicht gebaut ist,
trägt die Marke „geplant / planned" und zählt für den Test nicht.

Wer einen Befehl oder eine Option ändert, ändert **im selben Commit** die
Tabelle. Gegenprobe: `--gegenprobe` entfernt zwei Optionen aus der Doku, der
Test muss rot werden.


### Regel „Installerhelfer“ — Der Installer läuft nie unter einem Dienst und nie in der SSH-Sitzung

Vorgabe smilez (2.11.): Der Installer darf **nicht** unter
`chimera-hardware.service` laufen; er läuft abgekoppelt als eigener Dienst
`chimera-installhelper`, **nur wenn er aufgerufen wird**, nicht dauerhaft. Und:
**Die SSH-Sitzung darf nie abreißen, nur weil Chimera ein Update bekommt.**

**Der Einstieg ist eine `.sh`-Datei** (Vorgabe smilez, 10.11.2026): Der
Nutzer ruft den Installer aus seinem Betriebssystem heraus auf (DietPi),
und dort soll man einem Programm ansehen, was es ist. Die `.sh` darf eine
andere Datei aufrufen. Vorlagen sind die Installer von rag4ll und llmcf
(nachgesehen 10.11.): rag4ll hat `setup.sh` in der Repo-Wurzel als
einzigen sichtbaren Einstieg, der an die eigentlichen Installer
weiterreicht; llmcf hat `install.sh` in der Wurzel. 

**Entschieden und gebaut (smilez, 10.11.2026): `chimera-installer.sh` in
der Repo-Wurzel.** Die Datei reicht nur weiter an
`installer/chimera-install` — dieselben Optionen, derselbe Exitcode, keine
zweite Prüfung. Die innere Datei behält ihren Namen: Der Boot-Abgleich
bestehender Installationen und der Neustart aus `source/` rufen sie auf,
ein Übergang ist damit nicht nötig. Lehnt der Installer einen Lauf ohne
root ab, nennt der Hinweis den Einstieg, den der Nutzer aufgerufen hat.

Offen: ein Einstieg für den Deinstallierer
(`uninstaller/chimera-uninstall` trägt keine Endung), ob die innere Datei
ebenfalls eine Endung bekommt, und der Installationsbefehl in der README.

`chimera-hardware.service` ist der **Boot-Abgleich der Hardware**, nicht die
SSH-Schicht. Die Abkopplung ist eine eigene Sache und steht **im Installercode
selbst**, nicht in einem Aufrufparameter — damit sie bei jedem Lauf gilt.

**Gemessen am Pi (2.11.2026), was die Regel begründet:**
- Ein Dienst, der aus seiner eigenen Unit heraus einen Dienst mit `Before=`
  auf sich selbst startet, wird abgebrochen: „Job for … canceled“, rc 1 nach
  0 Sekunden. Genau das täte `chimera-install --hardware` aus
  `chimera-hardware.service` heraus, sobald er den Dienst neu startet.
- `sshd` selbst hat `oom_score_adj=-1000`, die **Sitzungsprozesse 0**; die Unit
  setzt `OOMScoreAdjust` nicht. Ein Speicherengpass trifft also die Sitzung.
- Ein über SSH gestarteter Installer läuft **in `/system.slice/ssh.service`**.
  Reißt die Verbindung, stirbt der Lauf mitten im Schreiben von Dateien.
- Der Speicher-Controller ist aus (`MemoryMin`/`MemoryMax` wirken nicht); Schutz
  vor dem Speicherkiller geht nur über `oom_score_adj`.
- Netz und SSH fasst der Installer nicht an (in allen Schritten geprüft).

1. **Ein eigener Lauf, abgekoppelt.** `chimera-install` startet die Arbeit als
   **`chimera-installhelper`** (transiente Unit, `systemd-run --collect`, Typ
   `oneshot`) und wartet auf sie. Fällt die SSH-Verbindung, läuft der Lauf
   weiter; die Rückmeldung im Terminal entfällt, das Protokoll bleibt.
   Aufruf über `--helfer` (intern) führt die Arbeit direkt aus — nur so läuft
   der Helfer selbst.
2. **Kein dauerhafter Dienst.** `chimera-installhelper` hat **kein `[Install]`**
   und wird nie beim Boot gestartet; er existiert, solange ein Lauf dauert.
3. **Nie unter einem fremden Dienst.** Auch `chimera-hardware.service` ruft den
   Installer nur **über den Helfer** auf; die Unit wartet auf das Ergebnis,
   führt die Arbeit aber nicht selbst aus. Damit gibt es keinen Deadlock mehr.
4. **Klammer bei jedem echten Lauf** (Vorgabe smilez, 13.11.; ersetzt die
   Fassung vom 2.11. „wenn es schon da ist und sich nichts ändert, lass die
   Finger weg“). Wer den Installer startet, will **sehen**, was passiert: Der
   Lauf hält die Dienste an, zeigt das Update-Gesicht und den Fortschritt, und
   erst dann wird geschrieben — **erst anhalten, dann schreiben, dann starten.**
   Angehalten wird nicht mehr davon abhängig gemacht, ob sich der Quellstand
   geändert hat.
   - **Der Grund (am 13.11. gefunden, „`klammer_noetig`“ war der Fehler):** Lag
     der Startbaum schon in `source/` (Quelle per rsync dorthin geschoben und
     von dort installiert), so waren Startbaum und Ziel gleich. Der Lauf galt
     als „Kein neuer Stand … nichts wird angefasst“, die Klammer blieb aus —
     **kein Update-Gesicht, keine angehaltenen Dienste** — und Schritt 55
     ersetzte das Binary trotzdem und startete `chimera-tor` neu. Also genau
     der Tausch unter einem laufenden Dienst, den die Klammer verhindern soll,
     ohne dass der Nutzer am Gerät etwas sah.
   - **Ein Lauf ohne Anhalten gibt es nur noch, wo er nichts ändern kann:**
     `--dry-run`, `--check`, `--list` und **nicht** bei `--hardware` (beim Boot
     läuft noch nichts, und der Dienst startet danach; ein Anhalten würde den
     Dienst treffen, der auf den Lauf wartet).
   - **Die übernommene Klammer hat Vorrang vor einem neuen Anhalten** (Fehler
     am 13.11., gefunden durch `test-klammer-lauf.sh`): Nach dem Selbstneustart
     aus `source/` läuft der neue Prozess unter einer offenen Klammer. Rief er
     `klammer_an` erneut auf, traf er alles „inactive“, schrieb „Es lief
     nichts“ und **leerte dabei die Merkerdatei** — nach dem Lauf blieben die
     Dienste aus. Die Reihenfolge ist deshalb: erst `CHIMERA_KLAMMER` prüfen,
     dann (nur ohne offene Klammer) anhalten.
   nach dem letzten Schritt hält er an, was noch läuft, und startet in der
   richtigen Reihenfolge. **Gemessene Reihenfolge** (der Fehler vom 31.10.):
   Sockets **vor** den Diensten starten, sonst verweigert systemd den Socket
   („Socket service already active, refusing“).
   - **Erst messen, dann anhalten.** Der Zustand wird vollständig aufgenommen,
     bevor der erste Halt geschieht. Grund (am Pi 2.11. gemessen): `chimera.service`
     hat `Requires=chimera-sitzung.socket`. Wer den Socket zuerst stoppt, nimmt
     den Dienst mit — der Dienst stand danach nicht mehr in der Liste, wurde
     nie wieder gestartet, und die Klammer meldete trotzdem „Dienste wieder
     gestartet“. Stiller Erfolg.
   - Anhalten: `chimera-mojo.timer` und weitere Timer, **dann die Dienste**
     (`chimera.service`, `chimera-tor.service`), **zuletzt die Sockets**.
     Dienste vor Sockets, damit kein Dienst ohne Socket zurückbleibt.
   - Starten: `chimera-tor.socket`, `chimera-sitzung.socket` (Sockets zuerst),
     dann `chimera.service`, die Timer, zuletzt das Gateway über den Socket
     wecken (`chimera-tor --ping`) — es startet nicht direkt, es braucht
     `LISTEN_FDS`.
   - Gestartet wird, was **vorher lief** oder was danach laufen soll; nicht
     blind alles.
   - **Jeder Schritt wird protokolliert und geprüft:** Zustand vor dem Lauf
     (aktiv/eingeschaltet je Einheit), jeder Halt und jeder Start mit
     Exitcode, danach eine Zustandstabelle. Weicht das Ergebnis ab, ist der Lauf
     ein Befund — nicht „Dienste wieder gestartet“ auf Verdacht.
   - **Die Klammer prüft sich selbst, sie verlässt sich nicht auf `set -e`.**
     Ein einzelner fehlschlagender Befehl darf den Start nicht mitten im
     Wiederanlaufen abbrechen (am Pi: Exitcode 2 nach dem Dienststart).
   - **Der Selbstneustart per `exec` trägt Klammer und Protokoll weiter.** Der
     Installer startet sich nach erneuertem `source/` neu; dabei müssen
     `--helfer`, der Helferauftrag, die offene Klammer und die Protokolldatei
     mitgehen. Sonst schreibt der neue Prozess nie „fertig“, die Klammer bleibt
     offen, und der Start steht in einer anderen Datei als der Lauf.
   - **`systemd-run` braucht `--no-block`.** Ohne das wartet der Aufruf auf den
     oneshot und meldet dessen Exitcode als Startfehler — ein Lauf mit Befund
     sah dadurch wie „Helfer startete nicht“ aus (am Pi gemessen).
   - **Schritte starten während der Klammer keine Dienste** (`CHIMERA_KLAMMER=1`);
     auch der Nachweis „Dienst läuft“ gehört ans Ende, nicht in den Schritt.
5. **SSH ist eine eigene, geschützte Sache.** Der Installer fasst weder Netz noch
   SSH an (Regel „Was nicht im Manifest steht, gehört nicht uns“), und er läuft
   nie in der cgroup der SSH-Sitzung, weil die Arbeit im Helfer läuft.
   Zusätzlich bekommt `ssh.service` ein Drop-in mit `OOMScoreAdjust=-900`, damit
   die Sitzung einen Speicherengpass überlebt (der Speicher-Controller ist aus,
   `MemoryMin` gibt es nicht). Das Drop-in liegt im Manifest und ist
   rückbaubar; es ändert die Unit nicht, nur einen Zusatz.
6. **Wiederaufruf hängt sich an, startet nichts Neues.** Läuft
   `chimera-installhelper` schon — etwa weil die SSH-Verbindung abgerissen ist
   und man neu verbindet —, dann **hängt sich der neue Aufruf an den laufenden
   Lauf** und liefert dessen Exitcode. Einen zweiten Lauf gibt es nie, aber der
   Lauf ist nach einer Trennung jederzeit wieder erreichbar.
7. **Testattrappen bilden die Unit nach, nicht nur den Befehl.** Die Attrappe
   von `systemctl` in `test-helfer.sh` muss `Requires=` nachbilden: Stoppt man
   `chimera-sitzung.socket`, nimmt systemd `chimera.service` mit. Ohne das war
   der Test grün, während am Gerät der Dienst aus blieb (2.11.). Ebenso gilt:
   Prüfbäume gehören **nicht** nach `/tmp` — ein Neustart räumt sie weg, und der
   Test misst dann nichts (`cd: Datei nicht gefunden`), ohne rot zu werden.
   Prüfbäume liegen unter `/opt/chimera-pruef`.
8. **Gegenprobe:** Ein Lauf mit einem scheiternden Schritt liefert dessen
   Exitcode zurück; ein Abbruch der aufrufenden Sitzung beendet den Helfer
   nicht; ein zweiter Aufruf während eines Laufs wird abgewiesen; nach dem Lauf
   laufen alle Dienste wieder, die vorher liefen, und der Sitzungs-Socket ist
   aktiv; `oom_score_adj` einer neuen SSH-Sitzung ist negativ.

### Regel „Changelog ohne Unreleased“ — was im Repo liegt, ist released

Vorgabe smilez (2.11.): **Es gibt keinen `[Unreleased]`-Block.** Das ist eine
bewusste, strengere Abweichung von Keep a Changelog:

- Was noch nicht fertig ist, steht in `docs/ROADMAP.md` — nicht im Changelog.
- Was committet und gepusht ist, gilt als released und steht im Changelog, im
  Abschnitt der laufenden Version.

Grund: Ein Unreleased-Block sammelt Wünsche, Absichten und Halbfertiges unter
derselben Überschrift wie Gebautes. Nach kurzer Zeit weiß niemand mehr, was
davon es wirklich gibt. Das Changelog beantwortet genau eine Frage: **was ist
drin**. Was fehlt, beantwortet die Roadmap.

Die Abschnitte folgen Keep a Changelog: Hinzugefügt, Geändert, Veraltet,
Entfernt, Behoben, Sicherheit — eine Zeile je Änderung, was sich für den Nutzer
ändert. Die Version bleibt ungetaggt, solange sie nicht auf echter Hardware
gelaufen ist; die Überschrift benennt den Stand, nicht ein Release.

### Regel „Fortschritt“ — Ein Balken, der den echten Stand zeigt

Vorgabe smilez (2.11.): „ein funktionierender Fortschrittsbalken, der den echten
Fortschritt anhand der Installer-Stufen anzeigt (alle Stufen bis Abschluss =
100 %, geteilt durch die Anzahl)." Und: **das Wort „Updating…" steht über dem
Balken.**

Warum ein eigener Prozess (`installer/lib/py/fortschritt.py`): Die Klammer hält
den Dienst an, bevor Dateien getauscht werden. Genau in dieser Zeit will man
den Fortschritt sehen — der Dienst kann das Panel also nicht bedienen.
Der Zeichner liest eine Datei (`/run/chimera-setup/stand`, Inhalt
`<fertig> <gesamt>`), zeichnet nur bei Änderung und endet über eine Marke.

**Gemessen (2.11.), was die Regel begründet:**
- Mit laufendem Zeichner meldet die Anzeige-Erkennung „Leitungen belegt" —
  der Zeichner hält SPI. Nur Schritt 40 braucht das Panel selbst, und auch nur,
  wenn er wirklich erkennen muss (fehlt `state/anzeige` oder `/dev/spidev0.0`).
  Dann gibt der Zeichner es frei (`fortschritt_halt`, Neustart danach). 46 und
  50 lesen nur Dateien — dort läuft der Balken weiter.
- Jedes Anhalten und jedes `close()` schaltet die Hintergrundbeleuchtung aus;
  beim Prozessende gibt der Kernel die GPIO-Leitung frei. Deshalb **ein**
  Zeichner je Lauf, der den Selbstneustart übersteht, statt drei.
- Nach dem Selbstneustart aus `source/` beginnt der Lauf wieder bei Modul 1.
  Der Balken darf dabei **nicht** zurückspringen: Der Stand wird nie kleiner
  als der in der Datei (Vorgabe an `fortschritt_start` und `fortschritt_setze`).
- `gesamt` 0 heißt fertig, nicht Division durch Null.

- **Pause ≠ fertig:** Die Pause benutzt eine eigene Marke. Mit derselben Marke
  zeichnete der Zeichner beim Anhalten 100 % und sprang danach zurück (am Gerät
  gesehen, 2.11.). Beim Pausieren schreibt er **selbst** seinen Wiedereinstiegs-
  punkt (`/run/chimera-setup/wieder`); der nächste Zeichner beginnt dort.
- Der Zeichner wird je Lauf mehrfach gestartet (nach jeder Panel-Pause) — das
  sieht nach Neustarts aus, ist aber nur die Anzeige. Der Installer selbst
  startet sich **einmal** neu, und nur wenn `source/` sich geändert hat.

**Licht und LED (Vorgabe smilez, 2.11. und 3.11.):** Während des Updates blinkt
die LED gelb. Danach bekommt **jeder Ausgang seine eigene Farbe und sein eigenes
Muster** — die LED ist mehrfarbig, also wird sie auch so benutzt:

| Ausgang | Anzeige | Bedeutung |
|---|---|---|
| `ok` | grün, fest (3 s) | eingerichtet, alles neu |
| `nichts` | grün, langsam blinkend (6 s) | geprüft, nichts zu tun — **ein Erfolg** |
| `befund` | gelb, fest (3 s) | geschafft, aber etwas fehlt (rc 1) |
| `neustart` | blau, blinkend (6 s) | eingerichtet, wirkt erst nach dem Start (rc 3) |
| `fehler` | rot, SOS (drei kurz, drei lang, drei kurz) | abgebrochen (ab rc 2) |

Der Fall `nichts` ist der Grund für den eigenen Weg: Hatte der Lauf nichts zu
tun, hält der Dienst die Leitungen — der Installer kann das Panel nicht selbst
anfassen. Er meldet den Ausgang deshalb über den Sitzungs-Socket (Operation
`led`, Client `installer/lib/py/led.py`), und der Renderer setzt die Farbe in
seinem Takt (`LedVerwalter`, Quelle `installer`, Laufzeit = Anzeigedauer).
Ohne diesen Weg leuchtete nach „alles aktuell" gar nichts — ein erfolgreicher
Lauf hätte wie ein ausgefallener ausgesehen.

Ein Befund (rc 1) ist **kein** Fehler — sonst wäre nach jedem Lauf mit
fehlendem Gateway-Binary alles rot. Ein ausstehender Neustart (rc 3) ebenso
wenig: er ist blau, nicht rot.
Bei einem Fehler ab rc 2 steigt **Mojo** ein (`chimera-tor --mojo --miracle`,
abgekoppelt als `chimera-mojo-install`).
Jede Backlight-Änderung wird mit Grund protokolliert („Hintergrundlicht: N %
(Grund)"), und der Zeichner schreibt eine Spur nach
`/run/chimera-setup/zeichner.log`. Ohne diese Spur war „das Licht geht aus"
nicht nachvollziehbar — jede Pause und jedes `close()` schaltet es aus.

**Frische Installation und Update sind zwei Fälle** (smilez, 12.11.2026):
- **Update:** Die Anzeige steht schon (`state/anzeige`, Treiber installiert),
  der Zeichner öffnet sie sofort. Das Gesicht `UPDATE` kommt aus
  `data/moods-builtin.json` — es muss nichts nachinstalliert werden.
- **Frische Installation:** Es gibt weder Einstellung noch Treiber. Der
  Zeichner zeichnet deshalb **nicht blind**, sondern fragt alle zwei Sekunden
  erneut; sobald der Anzeigeschritt Treiber und Erkennung hinter sich hat und
  `state/anzeige` geschrieben ist, beginnt er. Findet er bis zum Ende des
  Laufs keine Anzeige (Marke/Pause) oder nach 30 Minuten keine, sagt er es:
  Spur `KEIN Panel`, stderr, und der Installer warnt.

**Der Pfad der Einstellung hängt nie am Arbeitsverzeichnis:** gelesen wird
`$CHIMERA_ROOT/opt/chimera/state/anzeige` mit `CHIMERA_ROOT` = `/`, wenn nicht
gesetzt. Vorher stand dort ein leerer Vorgabewert, der Pfad war relativ — der
Zeichner des Installers startet aus seinem eigenen Verzeichnis und zeichnete
deshalb monatelang in ein `NullPanel` (am Gerät gefunden, 12.11.2026).

**Grenzen:** Bei `--only` und beim Boot-Abgleich gibt es keinen Balken (nichts
zu verteilen, bzw. der Dienst läuft weiter). Ohne Anzeige oder ohne Python wird
das gemeldet, nicht verschwiegen.

### Regel „Neustart mit Fortsetzung und Rueckfall“

Vorgabe smilez (3.11.): Mojo darf einen Neustart ausloesen, wenn eine Reparatur
ihn verlangt — und **muss danach von selbst weitermachen**. Scheitert der
Neustart, wird auf den Stand vor dem Neustart zurueckgerollt.

**Wann neu gestartet wird (zwei Ausloeser, beide bestaetigt):**
1. **Nach dem Nachladen** eines Pakets oder Kernelmoduls, das erst nach dem
   Start wirkt. Die Reparatur weiss das — kein Raetselraten.
2. **Wenn ein Befund nach drei Runden unreparierbar bleibt** und seine Ursache
   „Neustart hilft" traegt. Das ist eine Vermutung, deshalb **hoechstens
   einmal**.

**Der Ablauf:**
- Vor dem Neustart legt Mojo einen **Marker** ab (`state/mojo-fortsetzen.json`):
  Zeitpunkt, Runde, Anzahl bisheriger Neustarts, **Grund** (lesbar, für
  Protokoll und Bericht), die **Befunde** (`bereich|gegenstand`), die den
  Neustart verlangt haben, und die Liste der geaenderten Dateien mit
  Pruefsumme. Grund und Befunde stehen im Marker, weil der zweite Lauf sie
  sonst nicht mehr kennt — der Bericht des ersten ist nach dem Reboot weg.
- **Snapshot nur der geaenderten Dateien** (Kopie plus Pruefsumme), nicht des
  ganzen Systems. Was nicht angefasst wurde, muss auch nicht zurueck.
- `systemctl reboot`.
- Nach dem Start laeuft **einmal** `chimera-mojo-fortsetzung.service`
  (`ConditionPathExists=` auf den Marker, kein Dauerlaeufer) und ruft
  `chimera-tor --mojo --miracle --fortsetzen` auf: Runden zaehlen weiter,
  Marker am Ende weg.
- **Rueckfall:** Bringt der Neustart nichts (dieselben Befunde bleiben),
  stellt Mojo die Dateien aus dem Snapshot wieder her und meldet den Befund
  mit Ursache — statt ein zweites Mal zu starten.

**Platz vor dem Snapshot:** Bevor etwas gesichert wird, wird der freie Platz
geprueft — dieselbe Messung, die Oracle ohnehin macht (RAM, Karte, Cache). Ist
zu wenig Platz, wird **kein** Snapshot angelegt und kein Neustart ausgeloest,
sondern der Befund genannt. Ein voller Datentraeger ist selbst ein plausibler
Grund, warum der Dienst nicht startet.

**Gemessen (3.11., Pi Zero 2 W, Kernel 6.18.50, Dienste laufen):** Der
Richtwert **100 MB** bleibt, ist aber eine **Untergrenze**, keine Schaetzung
des Bedarfs — er entspricht etwa einer Produktivumgebung (`productive/` samt
venv: 107 MB). Die Messung:

| Posten | Wert |
|---|---|
| Arbeitsspeicher | 462 MB gesamt, 359 MB verfuegbar (Dienste laufen), 103 MB belegt |
| Auslagerung (zram + Datei) | 16,7 GB bereit, 0 belegt |
| Datentraeger | 117 GB, 18 GB belegt, 95 GB frei |
| `source/` / `state/` / `productive/` | 3 MB / 40 KB / 107 MB |
| `chimera.service` (Agent) | 47 MB RSS, **28,4 % eines Kerns im Leerlauf** |
| `chimera-tor --dienst` | 1,6 MB RSS, 0,2 % |
| Mojo-Pruefung (`--mojo --oracle`) | 528 ms, **6 MB** Spitze, Exitcode 0 |

Daraus folgt fuer den Snapshot: nicht „100 MB frei", sondern **die Groesse der
zu sichernden Dateien** pruefen — die steht vor dem Kopieren fest (Summe der
Dateigroessen aus der Liste), **doppelt**, weil kurzzeitig zwei Staende auf
der Karte liegen (der neue Snapshot und das Archiv des vorherigen; das
aeltere Archiv verschwindet erst danach). 100 MB bleiben die Untergrenze fuer
den Fall, dass die Liste leer ist oder eine Groesse nicht lesbar ist — dann
gilt die Untergrenze, statt eine Summe zu raten.

Beispiel: 60 MB zu sichern heisst 120 MB frei, nicht 100. Umgekehrt reichen
110 MB fuer dieselben Dateien nicht, obwohl sie ueber dem Richtwert liegen. Der Leerlauf von
28 % eines Kerns ist ein eigener Befund (ein Faden haengt zu ~22 % in `D`,
also in E/A-Wartezeit) und steht in `ROADMAP`.

**Historie 1:** Es bleibt **ein** Snapshot. Er ist ein **Verzeichnis**
(`state/mojo-snapshot/` mit `stand.tsv` — Pfad, Pruefsumme, Nummer — und den
Kopien unter ihrer Nummer), **kein Archiv**. Bewusst: Zurueckrollen ist damit
ein Kopieren mit Pruefsummenvergleich, ohne Entpacken und ohne Abhaengigkeit
von einem Packprogramm. Beim Anlegen wird der bisherige Snapshot zu
`mojo-snapshot-<zeit>/` verschoben und das **zuvor** verschobene geloescht.
So gibt es immer den letzten Stand und ein Archiv — nie eine Kette, die den
Datentraeger fuellt.

**Sperre gegen die Schleife:** hoechstens **zwei** Neustaubversuche je Marker;
danach kein weiterer, sondern Bericht. Ein Neustart, der nichts aendert, darf
sich nicht wiederholen — sonst ist das Geraet ohne Handeingriff unerreichbar.

**Grenzen (bewusst):** Der Snapshot deckt **geaenderte Dateien**, nicht das
Dateisystem. Ein halb geschriebenes Paket, ein voller Datentraeger oder ein
zerstoerter Bootloader sind damit nicht rueckholbar; dafuer gibt es die
Sicherung des Installers, nicht Mojo. Und ein Reboot wird **nie** ohne Marker
ausgeloest.

### Regel „ACP“ — Chimera ist ein Agent für Editoren, erreichbar über eine Transportschicht am Gateway

Vorgabe smilez (2.11.): ACP ist eine **Pflicht-Schnittstelle**. Gemeint ist der
**Agent Client Protocol** (Zed und JetBrains; Editoren und IDEs sprechen mit
einem Agenten; Android Studio „Rabbit 2“ nutzt ihn seit dem 28.10.2026 für
„Bring Your Own Agent“). Das Kürzel gehört drei Protokollen; die Klärung und
die Quellen stehen in `docs/research/ACP.md`, der Vergleich mit MCP in
`docs/research/ACP-MCP.md`.

**Entschieden (smilez, 2.11.):** Der ACP-Server wird gebaut, **mit einer
Transportschicht, damit eine IDE das Gateway ansprechen kann.**

1. **Chimera ist der Agent, nicht der Client.** Eine IDE schickt Prompts, Chimera
   antwortet, meldet Fortschritt und beendet den Zug. Ein ACP-Zug ist ein Turn
   in der Hauptsitzung (Regel „Ein Kanal, eine Hauptsitzung“); es gibt keinen
   zweiten Verlauf.
2. **Die Transportschicht trennt das Protokoll vom Weg.** Der ACP-Kern spricht
   JSON-RPC 2.0 mit Zeilenrahmen und kennt nur einen Bytestrom. Darunter liegen
   austauschbare Transporte, jeder ein eigenes Stück Code mit eigenem Test:
   - **stdio** (Standard von ACP): Der Client startet einen Prozess. Auf dem Pi
     ist das ein kleiner **Vermittler** (`chimera-tor --acp-stdio`), der den
     Strom an das Gateway weiterreicht; er läuft auf dem Rechner der IDE.
   - **Unix-Socket** am Gateway für lokale Clients (Rechte wie bei den anderen
     Sockets, Regel „Gateway“).
   - **HTTP/WebSocket** nach dem Entwurf der Spezifikation, **sobald er
     beschlossen ist** (er verlangt HTTP/2 und Cookies; heute nicht Standard).
   Ein Transport kennt weder Sitzungen noch Rechte; beides gehört dem Kern.
3. **Eine eigene Tür, nicht die des MCP.** Beide Protokolle sind JSON-RPC 2.0
   mit Zeilenrahmen, aber **verschieden gemeint**: MCP gibt *Werkzeuge* frei,
   ACP gibt *den Agenten selbst* frei. Beide an einer Tür mit einem Token zu
   mischen, verwischt, wofür das Token gilt. Auch kollidiert `initialize`. Ein
   Prozess, **getrennte Eingänge**, gemeinsam sind `Session` und die Gateway-
   Logik; eine **Positivliste je Tür** trennt, wer welche benutzen darf (Regel
   „Eine Tür von außen ohne Positivliste startet nicht“).
4. **Die Tür liegt am Gateway** (Regel „Gateway“): Anmeldung vor dem ersten
   Prompt, nur im eigenen Netz, ohne Positivliste bleibt sie zu. Der Agent-
   Dienst bekommt kein Netz dafür.
5. **Mindestumfang zuerst:** `initialize`, `session/new`, `session/prompt`,
   `session/update`, `session/cancel`, dazu die Antwort mit `stopReason`.
   Dateizugriff, Terminals, Modi und Slash-Befehle des Clients nutzt Chimera
   nicht, solange es kein Arbeitsverzeichnis des Clients hat; `initialize`
   meldet das ehrlich (`agentCapabilities` nur mit dem, was es kann).
6. **Das Sicherheitsmodell des Protokolls gilt hier:** Alles, was die IDE
   schickt, ist Eingabe, kein Befehl (Regel „Was ein anderer Agent schreibt, ist
   Eingabe, kein Befehl“); `clientInfo` ist selbstberichtet und entscheidet nie
   über Rechte; eine Sitzung gehört genau einem Nutzer; keine Zugangsdaten in
   `_meta`. Berechtigungsfragen von Chimera an die IDE sind **beratend**,
   Chimera hält sie selbst ein.
7. **Die Bibliothek ist entschieden: nein.** Die Rust-Crate
   `agent-client-protocol` hängt an `futures`/`tokio`; das Gateway läuft ohne
   Laufzeit. Gemessen am 6.11. gegen denselben Vertrag mit `serde_json`
   (`docs/messungen/2026-11-06-acp-bibliothek.md`):

   | | Crate 5.0.0 | eigener Zeilenrahmen |
   |---|---|---|
   | Binärdatei, gestrippt | 2,07 MB | **516 kB** |
   | 20 000 Anfragen | 5 034 ms | **370 ms** |
   | Speicher | 984 kB, 10 Fäden | **424 kB, 1 Faden** |
   | Start bis erste Antwort | 105 ms | **26 ms** |

   Der Mindestumfang wird deshalb **mit `serde_json` selbst gebaut**. Die
   Crate bleibt Referenz für die Feldnamen, nicht Abhängigkeit. Grenze der
   Messung: nur `initialize`, nicht das Streaming von `session/prompt`.
8. **Der Kern liegt in `rust/crates/acp`** (`chimera-acp`) und nutzt den
   Zeilenrahmen aus `gemein::zeile` — kein zweiter Rahmen, keine zweite
   Wahrheit. Der Kern kennt Methodennamen, Parametersitze und
   Fehlerantworten; was ein Zug *inhaltlich* tut, hängt am Trait `Agent`
   (im Betrieb die Hauptsitzung, im Test eine Attrappe). Bewusst synchron:
   Wer ihn nebenläufig braucht, ruft ihn aus seinem Faden auf.
9. **Gegenprobe:** Die Tür muss ohne Anmeldung zu bleiben, ein zweiter Prompt
   während eines Zuges muss in die Reihe, ein `session/cancel` muss den Zug
   beenden, ein Nutzer darf nie die Sitzung eines anderen sehen, und jeder
   Transport muss denselben Kern-Test bestehen (gleiche Nachrichten, gleiche
   Antworten).
10. **Das Display ist verleihbar** (smilez, 11.11.2026 — **Ergänzung, keine
    Umwidmung**). Alles, was oben steht, bleibt: Chimera ist der Agent für
    Editoren. Es kommt eine Fläche dazu — ein **gekoppeltes Gerät** darf
    zusätzlich **das Display** desselben Servers ansprechen: eine
    vorhandene Mood zeigen, den Status lesen. Grenzen:
    - **Nur vorhandene Moods.** Was ausgelöst wird, muss in der
      Mood-Bibliothek stehen; ein neues Gesicht anzulegen ist keine
      Fernbedienung, sondern eine Änderung am Gerät.
    - **Eigene Kennung je Gerät**, nie die des Agenten; eine Sitzung
      gehört einem Gerät. Wer kein Paar ist, kommt nicht durch
      (Regel „Eine Tür von draußen“).
    - **Keine Werkzeuge.** Über diese Fläche gibt es keinen Zugriff auf
      `chimera-sohelper`, Dateien oder Befehle — nur Anzeige.
    - Dieselbe Fläche gibt es über MQTT (Regel „MQTT“): dort ist der
      Kanal `displays/<name>/mood` der Weg, hier die ACP-Methode.

### Regel „MQTT“ — Ein Broker in Rust löst gespeicherte Moods auf dem Display aus

Vorgabe smilez (2.11.): Chimera ist eine Mischung aus Noisy, OpenMinis, woa-l,
openclawgotchi und PaKaChi-SM. Die **StateMaschine** mit MQTT stammt aus PaKaChi-SM (Quelle, privat);
sie soll hier eingebaut werden. Der MQTT-Broker ist **Rust** und mit
der **Whisplay-Steuerung** verknüpft: **Ein per MQTT gesendeter Aufruf löst einen
vorgefertigten, gespeicherten Mood sofort aus.** Zum Bauen neuer Gesichter,
Zubehöre und Moods soll das Sprachmodell **MCP und ACP** nutzen können, **falls
sinnvoll und machbar** (nicht entschieden).

**Was für Chimera zählt (Quelle: PaKaChi-SM, privates Projekt von smilez;
gelesen am 2.11.2026; `woa-l` enthält kein MQTT):**
- Eine **gemeinsame StateMaschine** nimmt Zustände und gespeicherte Bewegungen
  entgegen. Bedienung von Hand, MQTT und MCP laufen durch **denselben** Router,
  nicht durch drei Wege mit drei Regeln.
- Ein **ungültiger Zustand ändert den bisherigen nicht**; der Fehler wird
  gemeldet.
- Der Broker wird **geschützt betrieben**: nur feste Themenmuster, eine
  Größengrenze für Nachrichten, eine feste Liste erlaubter Aufrufe, und
  zurückgehaltene Nachrichten werden verworfen.

Nachgebaut wird nach diesen Grundsätzen, **nicht der Code übernommen**; das
Projekt ist privat, die Regel gibt keine Namen, Themen oder Werkzeuge daraus
wieder.

1. **Der Broker ist Rust, im Gateway-Workspace** (Regel „Rust, wo dauernd läuft“),
   klein und ohne Laufzeit wie das übrige Gateway. Er ist **eine Tür** neben
   ACP, MCP, Telegram und Web, mit eigener Positivliste (Regel „Eine Tür von
   außen ohne Positivliste startet nicht“).
2. **Ein Thema ist ein Mood, kein Befehl an das System.** Der Aufruf nennt einen
   **Namen aus der Mood-Bibliothek**; der Broker leitet ihn an die Anzeige (Regel
   „Wer anzeigt, bekommt die Anzeige übergeben“, `Face.set_by_name`). Ein Name,
   den es nicht gibt, wird verworfen und gemeldet, der bisherige Ausdruck
   bleibt (Grundsatz der Quelle).
3. **Die Zustände von Chimera sind die der StateMaschine:** `wartet`, `hoert`,
   `denkt`, `arbeitet`, `spricht`, `verwirrt`, `fehler` (Regel „Sprechgesicht“).
   Ein Zustand bleibt aktiv, bis ein neuer kommt; ein Mood ist ein einmaliger
   Aufruf, der durch den Zustand wieder abgelöst wird.
4. **Wer Moods bauen darf, trennt die Regel von dem, wer sie abruft.** Abrufen
   (ein vorhandenes Gesicht zeigen) ist harmlos und geht über MQTT. **Neu
   anlegen** (Gesicht, Zubehör, Mood) schreibt Dateien und geht nur über die
   Wege mit Anmeldung und Prüfung (Regel „Ein Gesicht ist ein Paket, das das
   Modell anlegen darf“, Regel „Ein generierter Mood wird immer validiert“),
   also MCP oder ACP, nie über ein offenes Thema.
5. **Härtung nach den Grundsätzen der Quelle, mindestens:** keine Platzhalter im Thema,
   Größengrenze, feste Namensmuster, `retain` verwerfen, Zähler gegen Fluten.
6. **Offen, nicht entschieden:** Themenaufbau, Anmeldung am Broker (Passwort,
   Zertifikat), ob der Broker auch Fremdgeräte bedient (Sensoren) oder nur das
   Display, QoS-Stufe, wie die Antwort zurückkommt, und ob und wie die
   StateMaschine der Quelle als Quelltext oder nur als Vorbild einfließt
   (das Projekt ist privat; hier wird **nachgebaut, nicht kopiert**).
7. **Gegenprobe:** Ein Aufruf mit unbekanntem Mood-Namen lässt das Gesicht
   unverändert; ein Thema mit Platzhalter wird abgewiesen; eine Nutzlast über
   der Grenze wird verworfen; ein Aufruf ohne Positivliste erreicht die Anzeige
   nie.

### Regel „Sprechende Namen“ — Eine Regel, ein Befehl, ein Baustein heißt nach dem, was er tut

Vorgabe smilez (1.11.): Nummern wie „10t“ oder „5n“ sagen niemandem etwas. Wer
einen Verweis liest, soll verstehen, **worum es geht**, ohne nachzuschlagen.

1. **Jede neue Regel trägt einen sprechenden Namen** und keine Nummer:
   `### Regel „Mojo“ — ...`. Verwiesen wird mit dem Namen: „Regel „Mojo““,
   nicht mit einer Zahl. Das gilt für Regeln, Phasen der ROADMAP, Module und
   Befehle, auch in Kommentaren, Tests und Commit-Nachrichten.
2. **Der Name nennt die Sache**, nicht die Reihenfolge, in der sie entstand
   (Mojo, Sprechgesicht, Datenschicht, Netzsuche), und bleibt kurz genug, um
   ihn in einem Satz zu verwenden.
3. **Alle Regeln gehören dem Projekt**, auch die älteren. Dass eine Nummer
   früher vergeben wurde, ist kein Grund, sie zu behalten. Die bestehenden
   Nummern werden schrittweise umbenannt (ROADMAP, Phase „Regelnamen“);
   solange das nicht geschehen ist, gelten sie als **Altbestand**.
4. **Ein Test hält das wahr** (`tests/test_regelnamen.py`): Er kennt die
   Altbestand-Nummern als feste Liste. Eine Überschrift mit einer Nummer, die
   **nicht** auf dieser Liste steht, macht ihn rot. Wird eine Regel umbenannt,
   muss sie **im selben Commit** aus der Liste, sonst wird der Test ebenfalls rot
   — die Liste kann nur kürzer werden.
5. **Beim Umbenennen** werden alle Verweise im selben Commit geändert
   (DESIGN, ROADMAP, CHANGELOG, Quelltext, Tests); ein Verweis auf einen Namen,
   den es nicht mehr gibt, ist ein Fehler.

### Regel „Tailscale“ — gelesen, nicht gesteuert

Entschieden 13.11. (smilez): **Tailscale gehört auf das Gerät, aber als
Zutat, die der Nutzer dazunimmt** — keine Voraussetzung, keine stille
Abhängigkeit.

1. **`tailscaled` läuft auf Betriebssystem-Ebene**, nicht im Gateway: Es
   braucht TUN und root. Chimera startet, konfiguriert und steuert es nicht.
2. **Chimera spricht das Tailscale-Protokoll nicht selbst.** Ein eigenes
   tsnet wäre WireGuard plus Steuerkanal, also genau der Netzweg, den die
   Fernausführung gerade aus dem Gateway herausgehalten hat.
3. **Lesen: die LocalAPI** über den Unix-Socket
   (`/var/run/tailscale/tailscaled.sock`, `GET /localapi/v0/status`), und nur
   so viel, wie eine Statuszeile braucht: Zustand, eigener Name, eigene
   Adressen, Zahl der Peers online. Die Anfrage steht als **eine** Zeile in
   `rust/crates/tor/src/tailscale.rs` und braucht den Host-Kopf
   `local-tailscaled.sock` — mit `localhost` antwortet die LocalAPI **403**,
   was am 13.11. wie ein Rechteproblem aussah (es war die Anfrage).
4. **Schalten: das Programm, nicht die LocalAPI.** An- und Abschalten geht
   über `tailscale up`/`down` (Op `tailscale_steuern`). Ein `POST` auf
   `/localapi/v0/prefs` ersetzt Einstellungen — mit nur `WantRunning` im
   Rumpf können andere auf Vorgaben zurückfallen; das Programm liest, ändert
   genau das Nötige und schreibt zurück. Der Gateway-Nutzer ist dafür
   **`operator`** von `tailscaled` (Entscheidung smilez 13.11.), und der
   Aufruf hängt zusätzlich an der **Freigabe `tailscale`** — ein Knopf, der
   den Netzzugang abschaltet, gehört nicht immer an.
5. **Fehlt der Socket, ist das kein Fehler.** Die Zeile sagt „nicht
   eingerichtet (tailscaled läuft hier nicht)“ — opt-out im Klartext statt
   „unbekannt“. Der Socket-Pfad ist über `CHIMERA_TAILSCALE_SOCKET`
   überschreibbar (Tests, andere Geräte).
6. **`100.64.0.0/10` (CGNAT = Tailnet) gilt als eigene Adresse** (`abruf`):
   Ein Abruf dorthin braucht wie jeder andere einen ausdrücklichen
   Positiv-Eintrag in der Freigabe (seit `3d9ed82`).
7. **Die Anmeldung am Koordinator (Headscale) macht der Nutzer**, nicht
   Chimera: `tailscale up --login-server … --authkey …` ist ein Vorgang mit
   einem Geheimnis, und Geheimnisse gehören nicht in einen Agentenlauf.

## Verzeichnis der Architekturregeln

- **1** — Die GPL-Grenze ist hart
- **1a** — Benannte Bausteine sind Vorschläge, keine Grenze
- **2** — Ein generierter Mood wird immer validiert
- **3a** — Das Modell wird nicht pro Geräusch gefragt
- **3b** — Nur im Ruhezustand wird zugehört
- **4a** — VAD läuft vor STT, KWS vor VAD
- **4b** — Gesicht und Stimme tragen denselben Mood
- **4c** — Das Sprachmodell setzt Absicht, nicht Bilder
- **Sprechgesicht** — Sprechen hat einen eigenen Ausdruck mit Mundphasen
- **5** — Sprache lokal, Sprachmodell immer remote
- **5a** — Registry statt fester Connector-Attribute
- **5b** — Anthropic-Anmeldung wie im OpenMinis-PR
- **5h** — Kein Anbieter wird vorausgesetzt
- **5c** — Ollama ist ein erstklassiger Anbieter
- **5d** — Ein Gespräch, zwei Türen
- **5i** — Ein Kanal hat keinen eigenen Zustand
- **5j** — Eine Tür von außen ohne Positivliste startet nicht
- **5k** — Ollama wird im Netz gesucht, nie auf dem Gerät betrieben
- **5l** — Wer Schlüssel hat, hat kein Werkzeug; wer Werkzeuge hat, hat keine Schlüssel
- **5m** — Die Web-Oberfläche ist Teil des Gateways und braucht kein Framework
- **5n** — Chimera spricht nur über sein Gateway mit der Welt
- **5t** — Anbieter, Schlüssel, Katalog, Wahl und Freigaben sind fünf Ablagen mit je einem Schreiber
- **5u** — Passwort ändern braucht das alte; Werksreset braucht das Gerät
- **5v** — Module melden sich einfach und sicher am Gateway an
- **5o** — Der Briefkasten ist ein eigener Prozess hinter dem Gateway, mit eigenem Port
- **5p** — Was ein anderer Agent schreibt, ist Eingabe, kein Befehl
- **5e** — zram und Auslagerungsdatei gehören zum Aufbau
- **5f** — Fremde Werkzeuge sind nicht vertrauenswürdig
- **5g** — Audio läuft getrennt, aber schlank
- **6** — Keine absoluten Pixelwerte
- **6b** — Weich ist der Normalfall, hart muss möglich bleiben
- **6c** — Das Panel ist eine Eigenschaft, keine Annahme
- **6d** — Dieselben Moods, verschiedene Darstellungen
- **6e** — Anzeige bei jedem Start prüfen
- **7** — Ein Prozess, ein Framebuffer
- **7a** — Die Bildrate gehört zum Panel, nicht zum Renderer
- **7b** — Wer etwas anzeigt, bekommt die Anzeige übergeben
- **7c** — Konkurrierende Anzeigequellen werden zentral aufgelöst
- **7d** — Wer anzeigt, besitzt die Zeit
- **8** — Die Mood-Steuerung ist ein Skill, kein Sonderweg
- **8b** — Ein Gesicht ist ein Paket, das das Modell anlegen darf
- **8c** — Das Gedächtnis verdichtet sich nach oben, und nichts fällt dabei heraus
- **8d** — Eine aktive Sitzung, eine alte, der Rest im Archiv
- **8e** — Persönlichkeit ist eine Datei, kein Code, und jede Schicht hat einen Besitzer
- **8f** — Wer was schreiben darf, setzt der Kernel durch
- **8g** — Chimera entwickelt sich, aber in kleinen, sichtbaren, umkehrbaren Schritten
- **8h** — Dateien sind die Wahrheit, die Datenbank ist ein Index
- **8a** — Stiller Erfolg ist die gefährlichste Fehlerart
- **9** — Kein Test, der eine Formel nachrechnet
- **10** — Ein Versionssprung bricht keine Installation
- **10a** — Board, Betriebssystem und Bootmethode sind drei Achsen
- **10b** — Erkennung stützt sich auf `compatible`, nicht auf den Klartextnamen
- **10k** — Unbekanntes Board warnt, es verbietet nicht
- **10c** — Alles Boardabhängige steht in einer Profiltabelle
- **10d** — Alles Lesende geht über ein Wurzelverzeichnis
- **10i** — Selbstaktualisierung nur mit Rückweg
- **10j** — Wer prüft, muss etwas sehen können
- **10e** — Jeder Lauf hinterlässt ein Protokoll
- **10f** — Keine Container auf dem Gerät
- **10g** — Nie raten
- **10h** — Gebaut ist erst, wenn verdrahtet ist
- **10l** — Jeder Installationsschritt hat sein Gegenstück
- **10m** — Ausführbares bleibt reines ASCII
- **10n** — Nachsehen, nicht abbrechen und nicht raten
- **10o** — Was nicht im Manifest steht, gehört nicht uns
- **10p** — Was beim Laden abstürzt, wird beim nächsten Start nicht wieder geladen
- **10q** — Speicher wird am Prozess gemessen und vom Prozess begrenzt
- **10r** — Der Agent ist ein eigener Nutzer, und was root ausführt, kann er nicht ändern
- **10s** — Root gibt es nur auf Rückfrage, auf Zeit, und nicht für den Agenten selbst
- **Warte-Schleife** — Kein Download bricht bei einem Netzaussetzer ab
- **Immer die neueste kompatible Fassung** — Kein Lock: jeder Lauf gleicht gegen den Index ab, sichert den Stand und rollt bei Bruch zurück
- **Installerhelfer** — Der Installer läuft nie unter einem Dienst und nie in der SSH-Sitzung
- **ACP** — Chimera ist ein Agent für Editoren, erreichbar über eine Transportschicht am Gateway
- **MQTT** — Ein Broker in Rust löst gespeicherte Moods auf dem Display aus
- **Sprechende Namen** — Eine Regel, ein Befehl, ein Baustein heißt nach dem, was er tut
- **Freigabe je Werkzeug auf Zeit** — die Positivliste lässt sich befristet
  aussetzen, die Negativliste nie
- **Wer prüft, führt aus** — Werkzeuge laufen in einem eigenen Prozess, den der Agent nicht ändern kann
- **Jedes Werkzeug bekommt nur seine Rechte** — die Rechte werden mitgegeben, nicht geerbt
- **Mojo** — jeder Fehler wird bemerkt, mit Ursache benannt, versucht, nachgeprüft und laut gemeldet
- **13a** — Vor jedem Push wird geprüft, und die Prüfung beweist ihre Sehfähigkeit
- **14** — Was dauernd läuft und nicht auf das Modell wartet, ist Rust
- **15** — Jeder Befehl steht in der CLI-Referenz, und ein Test hält sie wahr
