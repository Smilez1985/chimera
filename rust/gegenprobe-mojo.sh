#!/bin/sh
# Gegenprobe Mojo (DESIGN, Regel "Mojo"): jede Mutation muss einen Test rot machen.
# Aufruf: sh gegenprobe-mojo.sh   (Ergebnis: "0 gruen" ist gut)
. "$HOME/.cargo/env"
cd "$(dirname "$0")" || exit 2
gruen=0
mut() { # name, suchen, ersetzen
  f="crates/tor/src/mojo.rs"
  cp "$f" /tmp/gpm-orig.rs
  python3 - "$f" "$2" "$3" <<'EOF'
import sys
f, a, b = sys.argv[1:4]
s = open(f).read()
if s.count(a) < 1:
    sys.exit(3)
open(f, "w").write(s.replace(a, b, 1))
EOF
  if [ $? -ne 0 ]; then
    echo "MUSTER FEHLT: $1"; gruen=$((gruen+1)); cp /tmp/gpm-orig.rs "$f"; return
  fi
  if CARGO_TARGET_DIR=/root/chimera-target cargo test --offline -p chimera-tor mojo:: >/tmp/gpm.log 2>&1; then
    echo "GRUEN (schlecht): $1"; gruen=$((gruen+1))
  else
    echo "rot (gut): $1"
  fi
  cp /tmp/gpm-orig.rs "$f"
}
# 1. Oracle veraendert doch etwas
mut oracle-aendert 'if !fix {
        return Bericht { befunde: erste, versuche: Vec::new(), fix: false };
    }' 'if false {
        return Bericht { befunde: erste, versuche: Vec::new(), fix: false };
    }'
# 2. Nachpruefung ignoriert: Befund gilt immer als behoben
mut nachpruefung-ignoriert 'v.bestehen_geblieben = noch.contains(&(v.bereich.clone(), v.gegenstand.clone()));' 'v.bestehen_geblieben = false;'
# 3. unreparierbar wird nicht markiert
mut unreparierbar-nicht-markiert 'b.unreparierbar = true;' 'b.unreparierbar = false;'
# 4. Rueckgabewert der Reparatur zaehlt statt der Messung
mut rueckgabewert-zaehlt 'v.bestehen_geblieben = noch.contains(&(v.bereich.clone(), v.gegenstand.clone()));' 'v.bestehen_geblieben = v.fehler.is_some();'
# 5. Reparatur laeuft mehrfach
mut mehrfach 'let fehler = sys.ausfuehren(r).err();' 'let _ = sys.ausfuehren(r); let fehler = sys.ausfuehren(r).err();'
# 6. Schluessel ohne Gegenstand: zwei Sockets werden verwechselt
# Zwei Befunde am selben Bereich, aber an verschiedenen Gegenstaenden, werden verwechselt
mut schluessel-ohne-gegenstand 'versuche.iter().any(|v| v.bestehen_geblieben && v.bereich == b.bereich && v.gegenstand == b.gegenstand)' 'versuche.iter().any(|v| v.bestehen_geblieben && v.bereich == b.bereich)'
# 7. Status 203 wird nicht erkannt
mut ursache-203 '("exit-code", Some(203)) =>' '("exit-code", Some(2030)) =>'
# 8. Status 217 wird nicht erkannt
mut ursache-217 '("exit-code", Some(217)) =>' '("exit-code", Some(2170)) =>'
# 9. Signal 9 wird falsch benannt
mut signal-name '9 => "SIGKILL' '10 => "SIGKILL'
# 10. Ausgabe-Muster werden nicht gelesen
mut muster-ignoriert 'if klein.contains(m) {' 'if false {'
# 11. unbekannte Ursache wird verschwiegen (leerer Text)
mut unbestimmt-verschwiegen 'text: "Ursache nicht bestimmbar".into(),' 'text: String::new(),'
# 12. Rohdaten fehlen bei unbekannter Ursache
mut rohdaten-fehlen 'Ursache::unbestimmt(&format!("{beleg_status}; letzte Zeilen: {}"' 'Ursache::unbestimmt(&format!("{beleg_status}{}"'
# 13. Startgrenze nicht erkannt
mut startgrenze 'journal.iter().any(|l| l.contains("repeated too quickly"))' 'false'
# 14. Zwischenfehler (activating) wird als Fehler gemeldet
mut activating-alarm 'Schwere::Info,
                    "dienst",
                    "dienst.startet",' 'Schwere::Error,
                    "dienst",
                    "dienst.startet",'
# 15. Neustart-Warnung entfaellt
mut neustarts-warnung '"active" if z.neustarts > NEUSTARTS_WARNUNG =>' '"active" if false =>'
# 16. Reparatur fuer "laeuft, aber oft neu" (loescht den Beleg)
mut reset-loescht-beleg '                        ursache_fuer(sys, &z, &sys.journal(unit, 30)),
                        None,' '                        ursache_fuer(sys, &z, &sys.journal(unit, 30)),
                        Some(Reparatur::ResetUndStart { unit: unit.to_string() }),'
# 17. Socket-Reparatur fehlt
mut socket-ohne-reparatur 'Some(rep),
            );
            b.roh' 'None,
            );
            b.roh'
# 18. Exitcode ignoriert die Schwere
mut exitcode 'self.schlimmste().rang()' '0'
# 19. Warnung ohne Reparatur wird trotzdem angefasst (Schwelle)
mut schwelle 'if b.schwere < Schwere::Warn || r.stufe() > TIER_MAX {' 'if r.stufe() > TIER_MAX {'
# 20. JSON ohne Ursache
mut json-ohne-ursache 'v["ursache"] = json!({"text": u.text, "beleg": u.beleg, "weg": u.weg, "bestimmt": u.bestimmt, "nur_mensch": u.nur_mensch});' ''
# 21. Text ohne Ursache
mut text-ohne-ursache 't.push_str(&format!("        Ursache: {}\n        Beleg:   {}\n        Weg:     {}\n", u.text, u.beleg, u.weg));' ''
# 22. Speicherschwelle wird nie ausgeloest
mut speicher-schwelle 'Some(mb) if mb < SPEICHER_WARNUNG_MB =>' 'Some(mb) if mb < 0 =>'
# 23. Gescheiterte Fremd-Unit wird ignoriert (die Luecke vom 1.11.)
mut fremde-unit-ignoriert 'for unit in sys.gescheiterte_units() {' 'for unit in Vec::<String>::new() {'
# 24. Doppelte Meldung fuer Units mit eigener Pruefung
mut doppelt-gemeldet 'if bekannt.contains(&unit.as_str()) {' 'if false {'
# 25. Nicht-Chimera-Units werden mitgelesen
mut fremdes-gelesen '.filter(|n| n.starts_with("chimera") &&' '.filter(|n| true &&'
# 26. Unreparierbares wird im Journal nicht als solches markiert
mut journal-ohne-unreparierbar '" [UNREPARIERBAR: die Reparatur hat nichts bewirkt]"' '""'
# 27. Warnungen werden nicht laut gemeldet
mut warnung-still 'if f.schwere < Schwere::Warn {
            continue;
        }
        let (ursache, weg)' 'if f.schwere < Schwere::Error {
            continue;
        }
        let (ursache, weg)'
# 28. Das laute Journal nennt die Ursache nicht
mut laut-ohne-ursache '"Mojo: {}{} -- Ursache: {} -- Weg: {}",' '"Mojo: {}{} -- {} -- {}",'
# 29. Reparatur auch dort, wo ein Neustart nie hilft (203 Programm fehlt)
mut neustart-hilft-ignoriert 'let rep = reparatur_fuer(&u, unit);' 'let rep = Some(Reparatur::ResetUndStart { unit: unit.to_string() });'
# 30. Fremde Unit: Reparatur auch dort
mut neustart-hilft-fremd 'let rep = reparatur_fuer(&u, &unit);' 'let rep = Some(Reparatur::ResetUndStart { unit: unit.clone() });'
# 31. Nachpruefung ohne Warten
mut kein-warten 'sys.warten(NACHPRUEFUNG_WARTEN);' '();'
# 32. Budget wird nie geprueft
mut budget-ignoriert 'if sys.fehlversuche(&key) >= BUDGET {' 'if false {'
# 33. Wirkungsloser Versuch wird nicht gemerkt
mut fehlversuch-nicht-gemerkt 'sys.fehlversuch_merken(&schluessel(&v.bereich, &v.gegenstand));' '();'
# 34. Ein Anlauf gilt als behoben
mut anlauf-gilt-als-behoben '.filter(|b| b.schwere >= Schwere::Info)
        .map(|b| (b.bereich.clone(), b.gegenstand.clone()))' '.filter(|b| b.schwere >= Schwere::Warn)
        .map(|b| (b.bereich.clone(), b.gegenstand.clone()))'
# 35. Das Budget zaehlt auch alte Versuche
mut budget-alte 'jetzt.saturating_sub(**t) < FEHLVERSUCH_FRIST_S' 'true'
# 36. Ausgesetzt wartet trotzdem
mut ausgesetzt-wartet 'if versuche.iter().any(|v| !v.ausgesetzt) {' 'if !versuche.is_empty() {'
# 37. Signal gilt als nicht heilbar
mut signal-ohne-neustart '"Das Kernelprotokoll auf Speichermangel pruefen (dmesg | grep -i kill); bei Signal 11 den Fehler im Programm suchen.",
            ).mit_neustart())' '"Das Kernelprotokoll auf Speichermangel pruefen (dmesg | grep -i kill); bei Signal 11 den Fehler im Programm suchen.",
            ))'
# 38. Permission denied bekommt einen Neustart
mut permission-neustart '"address already in use",' '"address already in use",
    "permission denied",'
# 39. Schreibprobe wird nie als Fehler gewertet
mut karte-immer-gut 'Err(grund) => {
                    let (text, weg) = if grund' 'Err(grund) if false => {
                    let (text, weg) = if grund'
# 40. Schreibgeschuetzt wird nicht erkannt
mut karte-readonly 'if grund.to_lowercase().contains("read-only") ||' 'if grund.to_lowercase().contains("zzz-read-only") ||'
# 41. Karte "voll" warnt nie
mut karte-platz 'Some(mb) if mb < PLATZ_WARNUNG_MB => {' 'Some(mb) if mb < 0 => {'
# 42. Der Mensch-Fall bekommt eine Reparatur angedichtet (Neustart einer Karte)
mut karte-reparatur 'Ursache::mensch(text, &grund, weg),
                        None,' 'Ursache::mensch(text, &grund, weg),
                        Some(Reparatur::ResetUndStart { unit: "x".into() }),'
# 43. Fremder Bereich faellt nicht auf
mut bereich-egal 'if f.bereich != p.bereich() {' 'if false {'
# 44. Mojo meldet seine eigenen Units als gescheitert
mut mojo-meldet-sich-selbst 'if unit.starts_with("chimera-mojo") {' 'if false {'
# 45. Die Karte wird am falschen Ort geprueft (logs statt logs/productive)
mut karte-falscher-ort 'std::env::var("CHIMERA_LOG_KARTE")' 'std::env::var("CHIMERA_LOG_XXX")'
# 46. Fehlendes Paket wird nicht nachgeladen
mut paket-nachladen-aus 'if u.paket_nachladen {' 'if false {'
# 47. Stufe 2 laeuft nicht von allein
mut stufe-2-aus 'r.stufe() > TIER_MAX' 'r.stufe() > 1'
# 48. Fehlendes Paket gilt nicht als Paket-Ursache
mut paket-muster-ohne-paket 'u.mit_paket()' 'u'
# 49. RAM-Fehlmenge falsch (0 statt Zahl)
mut ram-fehlmenge 'let fehlt = SPEICHER_WARNUNG_MB - mb;' 'let fehlt = 0;'
# 50. Karten-Fehlmenge falsch
mut karte-fehlmenge 'let fehlt = PLATZ_WARNUNG_MB - mb;' 'let fehlt = 0;'
# 51. RAM und Karte werden verwechselt (RAM-Meldung nennt SD)
mut ram-nennt-sd '"Der Arbeitsspeicher (RAM) ist knapp, nicht die SD-Karte"' '"Die Speicherkarte (SD) ist knapp"'
# 52. Karte nennt RAM
mut karte-nennt-ram '"Die Speicherkarte (SD) ist fast voll, nicht der Arbeitsspeicher"' '"Der Arbeitsspeicher (RAM) ist fast voll"'
# 53. Programmausgabe: Karte voll wird als RAM benannt
mut muster-voll-als-ram '"Die Speicherkarte (SD) ist voll, nicht der Arbeitsspeicher"' '"Dem Prozess ging der Arbeitsspeicher (RAM) aus, nicht die SD-Karte"'
# 54. Nachladen ohne Eintrag in requirements.txt
mut requirements-ignoriert 'Some(text) if modul_in_requirements(&modul, &text) => u,' 'Some(_) => u,'
# 55. Import-Name wird dem Paket nicht zugeordnet (PIL gegen Pillow)
mut alias-fehlt '("pil", "pillow"), ' ''
# 56. Unlesbare requirements: trotzdem nachladen
mut requirements-unlesbar 'None => Ursache {
            text: format!("Das Python-Paket fuer' 'None => return u, _x => Ursache {
            text: format!("Das Python-Paket fuer'
# 57. Fehlender Protokollpfad wird verschwiegen
mut protokollpfad-still 'if self.pfade.len() < 2 {' 'if false {'
cp /tmp/gpm-orig.rs crates/tor/src/mojo.rs 2>/dev/null
echo "== $gruen gruen =="
