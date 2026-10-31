#!/bin/sh
# Gegenprobe fuer status.rs (DESIGN Regel 5m): jede Mutation verfaelscht eine
# Messaussage; die Tests muessen dann ROT werden. Danach wird die Quelle
# zurueckgelegt und per cmp geprueft. Dauer einige Minuten: abgekoppelt starten.
set -u
cd "$(dirname "$0")" || exit 2
. "$HOME/.cargo/env"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-/root/chimera-target}"
F=crates/tor/src/status.rs
SICH=$(mktemp) || exit 2
[ -n "$SICH" ] || exit 2
cp "$F" "$SICH" || exit 2
[ -s "$SICH" ] || { echo "Sicherung leer"; exit 2; }
trap 'cp "$SICH" "$F"' EXIT INT TERM

ROT=0; GRUEN=0
mutiere() {  # name, alt, neu
    cp "$SICH" "$F"
    python3 - "$F" "$2" "$3" <<'EOF'
import sys
p, alt, neu = sys.argv[1:4]
s = open(p).read()
if s.count(alt) != 1:
    print("MUSTER NICHT EINDEUTIG:", s.count(alt)); sys.exit(3)
open(p, "w").write(s.replace(alt, neu))
EOF
    [ $? -eq 0 ] || { echo "  FEHLER  $1: Mutation nicht anwendbar"; GRUEN=$((GRUEN+1)); return; }
    if cargo test --offline -p chimera-tor status >/tmp/gp-status.log 2>&1; then
        echo "  GRUEN (schlecht)  $1 -- Test merkt es nicht"; GRUEN=$((GRUEN+1))
    else
        if rg -q 'test result: FAILED|panicked' /tmp/gp-status.log; then
            echo "  rot (gut)  $1"; ROT=$((ROT+1))
        else
            echo "  BAUFEHLER  $1"; rg 'error' /tmp/gp-status.log | head -3; GRUEN=$((GRUEN+1))
        fi
    fi
}

mutiere "CPU: Leerlauf zaehlt als Last" \
  'Some(((ds - dl) / ds * 100.0).clamp(0.0, 100.0))' 'Some((dl / ds * 100.0).clamp(0.0, 100.0))'
mutiere "CPU: Rueckwaertszaehler erlaubt" \
  'if jetzt.summe <= vorher.summe || jetzt.leer < vorher.leer {' 'if false {'
mutiere "CPU: iowait nicht als Leerlauf" \
  'let leer = w[3] + w.get(4).copied().unwrap_or(0);' 'let leer = w[3];'
mutiere "CPU: Kerne ignoriert" \
  '        } else if kopf.len() > 3 && kopf.starts_with("cpu")' '        } else if false && kopf.starts_with("cpu")'
mutiere "Schwelle: Warnung erst ab krit" \
  '    } else if anteil >= warn {' '    } else if anteil >= krit {'
mutiere "Speicher: frei statt belegt" \
  'let belegt = gesamt - frei;' 'let belegt = frei;'
mutiere "Speicher: frei groesser als gesamt zulaessig" \
  'if gesamt == 0 || frei > gesamt {' 'if gesamt == 0 {'
mutiere "Temperatur: Wertebereich nicht geprueft" \
  'if !(-40_000..=150_000).contains(&m) {' 'if false {'
mutiere "Temperatur: kritisch erst ab 200" \
  'const TEMP_KRIT: f64 = 80.0;' 'const TEMP_KRIT: f64 = 200.0;'
mutiere "Takt: Null erlaubt" \
  'if k == 0 || k > 10_000_000 {' 'if k > 10_000_000 {'
mutiere "Last: nicht je Kern" \
  'let anteil = kerne.map(|n| (l[0] / n as f64 * 100.0).clamp(0.0, 100.0));' 'let anteil = kerne.map(|_| (l[0] * 100.0).clamp(0.0, 100.0));'
mutiere "Dienste: gescheitert gilt als ok" \
  '        "unbekannt" => Stufe::Unbekannt,
        _ => Stufe::Kritisch,' '        "unbekannt" => Stufe::Unbekannt,
        _ => Stufe::Ok,'
mutiere "Dienste: unbekannt gilt als ok" \
  '        "unbekannt" => Stufe::Unbekannt,
        _ => Stufe::Kritisch,' '        _ => Stufe::Ok,'
mutiere "Platte: belegt groesser als gesamt zulaessig" \
  'if gesamt == 0 || belegt > gesamt {' 'if gesamt == 0 {'
mutiere "Fehlender Wert wird 0 statt nicht lesbar" \
  '            text: "nicht lesbar".into(),
            wert: None,' '            text: "nicht lesbar".into(),
            wert: Some(0.0),'

cp "$SICH" "$F"
if cmp -s "$SICH" "$F"; then echo "Quelle zurueckgelegt (cmp ok)"; else echo "QUELLE NICHT ZURUECK"; exit 2; fi
echo "rot: $ROT  gruen (schlecht): $GRUEN"
[ "$GRUEN" -eq 0 ] && [ "$ROT" -gt 0 ]
