#!/bin/sh
# Gegenprobe zu den Tests von telegram.rs und sitzung.rs (Regel 9): je eine
# Zusage verfaelschen, `cargo test` muss an der erwarteten Stelle rot werden.
# Aufruf: sh rust/gegenprobe-telegram.sh   (CARGO_TARGET_DIR ausserhalb des Repos)

set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
. "$HOME/.cargo/env" 2>/dev/null || true
: "${CARGO_TARGET_DIR:=${TMPDIR:-/tmp}/chimera-gp-target}"
export CARGO_TARGET_DIR
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }

DATEI="crates/tor/src/telegram.rs"
DATEI2="crates/tor/src/sitzung.rs"
DATEI3="crates/tor/src/telegram_einstellung.rs"
W="$CARGO_TARGET_DIR/gegenprobe-telegram.$$"
mkdir -p "$W" && [ -d "$W" ] || { echo "kein Arbeitsverzeichnis: $W"; exit 2; }
cp "$DATEI" "$W/telegram.orig" && cp "$DATEI2" "$W/sitzung.orig" && cp "$DATEI3" "$W/einst.orig" || { echo "Sicherung fehlt"; exit 2; }
# Die Quellen werden IMMER zurueckgelegt -- und das Ergebnis geprueft (GLOBAL:
# das Ergebnis, nicht der Exitcode).
wieder() {
	cp "$W/telegram.orig" "$DATEI" && cp "$W/sitzung.orig" "$DATEI2" && cp "$W/einst.orig" "$DATEI3" || echo "WARNUNG: Quellen nicht zurueckgelegt, Sicherung in $W"
	cmp -s "$W/telegram.orig" "$DATEI" && cmp -s "$W/sitzung.orig" "$DATEI2" && cmp -s "$W/einst.orig" "$DATEI3" && rm -rf "$W"
}
trap wieder EXIT INT TERM

printf '=== Gegenprobe Telegram-Tuer ===\n'
if cargo test --locked -p chimera-tor >"$W/basis.txt" 2>&1; then ok "unveraendert gruen"
else bad "unveraendert schon rot -- Gegenprobe nicht aussagekraeftig"; tail -5 "$W/basis.txt"; fi

# $1 Name, $2 Datei, $3 sed-Ausdruck, $4 Test, der rot werden muss
mutation() {
	cp "$W/telegram.orig" "$DATEI"; cp "$W/sitzung.orig" "$DATEI2"; cp "$W/einst.orig" "$DATEI3"
	sed "$3" "$2" >"$W/m.rs"
	if cmp -s "$2" "$W/m.rs"; then bad "$1: Mutation griff nicht"; return; fi
	cp "$W/m.rs" "$2"
	if cargo test --locked -p chimera-tor >"$W/$1.txt" 2>&1; then
		bad "$1: Tests blieben gruen"
	elif grep -Eq "$4[a-z_]* \.\.\. FAILED" "$W/$1.txt"; then
		ok "$1: rot bei '$4'"
	else
		bad "$1: rot, aber nicht bei '$4'"; grep FAILED "$W/$1.txt" | head -3
	fi
	cp "$W/telegram.orig" "$DATEI"; cp "$W/sitzung.orig" "$DATEI2"; cp "$W/einst.orig" "$DATEI3"
}

# M1: Fremde werden durchgelassen.
mutation fremde-durch "$DATEI" \
	's|if !erlaubt.contains(&e.user_id) {|if false \&\& !erlaubt.contains(\&e.user_id) {|' \
	"ein_fremder_wird_abgewiesen"

# M3: ohne Liste startet der Bot trotzdem.
mutation offene-tuer "$DATEI" \
	's|    if liste.is_empty() {|    if false \&\& liste.is_empty() {|' \
	"token_ohne_liste"

# M4: die eigene Eingabe wird zurueckgespiegelt.
mutation echo-eigene "$DATEI" \
	's|"eingabe" if e.tuer != TUER|"eingabe" if true|' \
	"die_eigene_eingabe_wird_nicht"

# M5: Zustand wird als Gespraech gesendet.
mutation zustand-gesendet "$DATEI" \
	's|"antwort" \| "fehler" => Some(e.text.clone()),|"antwort" \| "fehler" \| "zustand" => Some(e.text.clone()),|' \
	"zustand_und_umleitung"

# M6: Antworten nur an die Tuer, aus der gefragt wurde.
mutation nur-eigene-antwort "$DATEI" \
	's|"antwort" \| "fehler" => Some(e.text.clone()),|"antwort" \| "fehler" if e.tuer == TUER => Some(e.text.clone()),|' \
	"antworten_und_fehler_gehen_an_telegram"

# M7: das Token erscheint in Meldungen.
mutation token-sichtbar "$DATEI" \
	's|text.replace(&self.token, "<token>")|text.to_string()|' \
	"das_token_erscheint_in_keiner_meldung"

# M8: der Zaehler rueckt bei einer Nachricht ohne Text nicht vor (nur Parser).
mutation bild-ohne-text "$DATEI" \
	's|^    if text.is_empty() {|    if false {|' \
	"alles_ohne_text"

# M9: Lange Texte werden nicht geteilt.
mutation nicht-geteilt "$DATEI" \
	's|if zeichen.len() <= groesse {|if true {|' \
	"langer_text_wird_an_zeilengrenzen"

# M10: der Strom liefert Aelteres noch einmal (Dopplung).
mutation doppelte "$DATEI2" \
	's|if e.nr > \*seit {|if true {|' \
	"hoeren_liefert_nur_neueres"

# M11: eine abgelehnte Frage gilt als Erfolg.
mutation ablehnung-ok "$DATEI2" \
	's|    if a\["ok"\] != true {|    if false {|' \
	"abgelehnte_anmeldung"

# M12: /suche landet in der Sitzung statt in der Netzsuche.
mutation suche-geht-in-sitzung "$DATEI" \
	's#            "suche" | "netzsuche" => return Entscheidung::Suche,#            #' \
	"suche_wird_erkannt_und_geht_nicht_in_die_sitzung"

# M13: eine gescheiterte Suche nennt ihren Grund nicht mehr.
mutation suche-ohne-grund "$DATEI" \
	's#let grund = a\["grund"\].as_str().or_else(|| a\["fehler"\]\["text"\].as_str()).unwrap_or("ohne Grund");#let grund = "ohne Grund";#' \
	"suche_text_nennt_funde_neue_und_den_grund"

# M14: "nichts gefunden" wird als Fund gemeldet.
mutation suche-leer-als-fund "$DATEI" \
	's#    if funde.is_empty() {#    if false {#' \
	"suche_text_nennt_funde_neue_und_den_grund"

# --- Einstellungen der Tuer (14.11.2026) ---

# M15: Der Token wird auch abgelegt, wenn Telegram ihn nicht annimmt.
mutation toter-token-abgelegt "$DATEI3" \
	's#        Err(e) => return Err(format!("Telegram nimmt diesen Token nicht an: {e}")),#        Err(_) => serde_json::json!({}),#' \
	"falscher_token_wird_nicht_abgelegt"

# M16: Die Auskunft verraet den Token.
mutation stand-zeigt-token "$DATEI3" \
	's#"erlaubt": erlaubt,#"erlaubt": erlaubt, "token": token.clone(),#' \
	"stand_verraet_den_token_nicht"

# M17: Die Ablage ist fuer alle lesbar.
mutation ablage-0644 "$DATEI3" \
	's#atomar_schreiben(&ziel, text.as_bytes(), 0o600)#atomar_schreiben(\&ziel, text.as_bytes(), 0o644)#' \
	"ablage_schreibt_0600"

# M18: Ohne Token laesst sich die Positivliste setzen.
mutation liste-ohne-token "$DATEI3" \
	's#    if e.token.is_empty() {#    if false {#' \
	"erlaubt_ohne_token_wird_abgelehnt"

# M19: Eine kaputte Ablage gilt als "nicht eingerichtet".
mutation kaputte-ablage-leer "$DATEI3" \
	's#        Err(e) => return Err(format!("{} nicht lesbar: {e}", pfad.display())),#        Err(_) => return Ok(Einstellung::default()),#' \
	"unlesbare_ablage_ist_auch_ein_fehler"

# M20: Ein Token ohne Doppelpunkt wird angenommen.
mutation form-egal "$DATEI3" \
	's#    if vorne.parse::<u64>().is_err() || hinten.len() < 10 {#    if false {#' \
	"form_verlangt_zahl_doppelpunkt"

printf '\nErgebnis: %s ok, %s fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
