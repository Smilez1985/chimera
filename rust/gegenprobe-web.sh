#!/bin/sh
# Gegenprobe fuer web.rs (DESIGN Regel 5m): jede Mutation verfaelscht eine
# Sicherheitsentscheidung; die Tests muessen dann ROT werden. Danach wird die
# Quelle zurueckgelegt und per cmp geprueft (GLOBAL: Ergebnis pruefen).
# Dauer einige Minuten: abgekoppelt starten.
set -u
cd "$(dirname "$0")" || exit 2
. "$HOME/.cargo/env"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-/root/chimera-target}"
F=crates/tor/src/web.rs
SICH=$(mktemp) || exit 2
[ -s "$SICH" ] || true
cp "$F" "$SICH" || exit 2
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
    [ $? -eq 0 ] || { echo "  FEHLER  $1: Mutation nicht anwendbar"; ROT=-999; return; }
    if cargo test --offline -p chimera-tor web >/tmp/gp-web.log 2>&1; then
        echo "  GRUEN (schlecht)  $1 -- Test merkt es nicht"; GRUEN=$((GRUEN+1))
    else
        if rg -q 'test result: FAILED|panicked' /tmp/gp-web.log; then
            echo "  rot (gut)  $1"; ROT=$((ROT+1))
        else
            echo "  BAUFEHLER  $1"; rg 'error' /tmp/gp-web.log | head -3; GRUEN=$((GRUEN+1))
        fi
    fi
}

mutiere "Anmeldung nicht geprueft" \
  'if !angemeldet {' 'if false {'
mutiere "Passwort immer richtig" \
  'if !pw.is_empty() && hash_pruefen(&z.hash, pw) {' 'if true {'
mutiere "leeres Passwort erlaubt" \
  'if !pw.is_empty() && hash_pruefen' 'if hash_pruefen'
mutiere "Bremse aus" \
  'q.len() < MAX_FEHLVERSUCHE' 'true'
mutiere "Marke nicht verlangt" \
  'if ist_post && a.marke != "1" {' 'if false {'
mutiere "Pfadschutz: '..' erlaubt" \
  '&& !s.contains("..")' ''
mutiere "Endungsliste: alles ausliefern" \
  '_ => return None, // unbekannte Endung: nicht ausliefern' '_ => "application/octet-stream",'
mutiere "Chat ohne Recht" \
  'x.name == name && x.rechte.iter().any(|r| r == recht)' 'x.name == name'
mutiere "Cookie ohne HttpOnly" \
  '"{COOKIE}={t}; HttpOnly; SameSite=Strict' '"{COOKIE}={t}; SameSite=Strict'
mutiere "nachgelegtes Modul ersetzt eingebautes" \
  'Ok(m) if ok.contains_key(&m.name) => {' 'Ok(m) if false => {'
mutiere "Sitzungs-ID ungeprueft" \
  "if sid.is_empty() || !sid.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_' || b == b'.') {" 'if false {'
mutiere "Hash: Form nicht geprueft" \
  't.len() == 4
        && t[0] == KOPF' 't.len() == 4
        && true'

mutiere "LAN: private Adressen nicht erkannt" \
  'IpAddr::V4(a) => a.is_loopback() || a.is_private() || a.is_link_local(),' 'IpAddr::V4(a) => a.is_loopback() || a.is_link_local(),'
mutiere "LAN: alles gilt als LAN" \
  'IpAddr::V4(a) => a.is_loopback() || a.is_private() || a.is_link_local(),' 'IpAddr::V4(_) => true,'
mutiere "LAN-Sperre nicht Vorgabe" \
  '            lan_nur: true,' '            lan_nur: false,'

cp "$SICH" "$F"
if cmp -s "$SICH" "$F"; then echo "Quelle zurueckgelegt (cmp ok)"; else echo "QUELLE NICHT ZURUECK"; exit 2; fi
echo "rot: $ROT  gruen (schlecht): $GRUEN"
[ "$GRUEN" -eq 0 ] && [ "$ROT" -gt 0 ]
