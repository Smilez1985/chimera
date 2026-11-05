# Messreihe: Vorab-Laden und uv — was bringt was

**Pi Zero 2 W, 05.11.2026, Commit `0965a49`** (letzte zwei Läufe), Gerät sonst
unverändert. „Kalt" heißt je Lauf: `productive/venv` entfernt, pip- und
uv-Zwischenspeicher geleert, Vorab-Marken entfernt. Dann muss der Lauf Pillow
und numpy wirklich holen — genau die Arbeit, um die es geht.

Gemessen wird je Lauf: Gesamtdauer (Start bis „Helfer beendet") und die Dauer
von Modul 50 (`Modul 50-python brauchte Ns`), weil dort die Python-Pakete
entstehen.

| Lauf | Vorab-Laden | uv | Gesamt | Modul 50 |
|---|---|---|---|---|
| A1 | aus | aus | 126 s | 85 s |
| A2 | aus | aus | 107 s | 82 s |
| B  | an  | aus | 107 s | 84 s |
| C  | an  | an  | 79 s | 54 s |
| D  | aus | an  | 79 s | 53 s |
| D2 | aus | an  | 81 s | 55 s |
| E  | an  | an  | 100 s | 58 s |

## Was daraus folgt

1. **uv wirkt und ist der größte Posten.** Ohne uv: Modul 50 = 82–85 s
   (A1, A2, B). Mit uv: 53–58 s (C, D, D2, E). Das sind rund **30 s weniger**,
   über vier Läufe stabil. (Einzelmessung derselben Pakete: pip 41 s, uv 10 s.)
2. **Das Vorab-Laden bringt in dieser Form nichts.** B (an) gegen A2 (aus):
   107 s gegen 107 s, Modul 50 84 s gegen 82 s. Mit uv: D/D2 (aus) 79/81 s
   gegen C/E (an) 79/100 s — kein Gewinn, in einem Lauf sogar schlechter.
   **Grund, am Gerät gemessen:** Modul 50 beginnt nach etwa 20 s
   (Module 00–46), der Wheel-Abruf braucht ebenfalls etwa 20 s für 22 MB.
   Beide wetten auf dieselbe Leitung: Was der Vorab-Lader parallel zieht,
   fehlt Modul 50. Der Gewinn entstünde nur, wenn der Abruf **vor** Modul 50
   fertig wäre — auf diesem Gerät ist das nicht der Fall.
3. **Ein Fehler in meiner ersten Fassung, behoben:** Die Wheels landeten erst
   am Ende des Abrufs in `wheels/` (Zwischenverzeichnis + Umhängen). Damit war
   das Verzeichnis beim Start von Modul 50 noch leer — der Vorab-Lauf konnte
   gar nichts nützen. Jetzt schreibt pip direkt nach `wheels/`; gemessen
   (40 Abtastungen während eines 15-MB-Downloads) legt pip ein Wheel erst
   vollständig ab, nie halb. Der Gewinn blieb trotzdem aus (E gegen D2) —
   der Grund ist die Leitung, nicht die Marke.

## Ehrlich offen

- **Streuung:** A1 gegen A2 sind 19 s Unterschied bei identischen
  Einstellungen. Für eine belastbare Aussage über das Vorab-Laden bräuchte es
  je Variante 3–5 Läufe; die Tendenz (kein Gewinn) ist über vier Läufe gleich,
  die Zahl ist es nicht.
- **Nicht gemessen:** eine echte Erstinstallation (frisches Image). Dort ist
  der Netzanteil größer (1,5–2 min), und nur dort kann das Vorab-Laden
  überhaupt etwas abfangen — falls der Abruf dann nicht ebenfalls hinter dem
  Verbraucher zurückliegt.
- **Nebenbefund:** In allen kalten Läufen meldet der Abschluss `LED: nichts
  (6 s)` statt `LED: ok (3 s)`. Nach dem Neubau des venv findet das
  Abschluss-Signal offenbar keinen Empfänger. Nicht behoben, nicht als Fehler
  bestätigt — nur notiert.

## Messprotokolle

Auf dem Gerät: `/tmp/lauf-A.log`, `/tmp/lauf-D.log`, `/tmp/lauf-D2.log`,
`/tmp/lauf-E.log`; die Läufe selbst unter `/opt/chimera/logs/installer/`.
