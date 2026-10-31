#!/bin/sh
# Tests fuer die TLS-Voraussetzungen des Gateways (DESIGN Regel 5n, 14).
#
# Das Gateway ist ein vorkompiliertes Binary (rustls und die Zertifikatsliste
# stecken darin). Zur Laufzeit braucht der Pi trotzdem zwei Dinge, die der
# Installer sicherstellen und nachweisen muss:
#
#   1. Das Paket ca-certificates ist ZWINGEND (Modul 20) und sein Nachweis
#      prueft das Ergebnis (das Buendel liegt da und ist nicht leer), nicht
#      nur den Paketstand.
#   2. Eine unplausible Uhr wird im Preflight (Modul 10) benannt: TLS prueft
#      Zertifikate gegen die Zeit, ein Pi ohne RTC startet mit altem Stand.
#
# Geprueft wird die echte Bibliothek und der echte Schritt (Regel 9).
# CHIMERA_TLS_DETECT / CHIMERA_TLS_PAKETE ueberstimmen die Quellen -- damit
# faehrt counter-check-tls.sh denselben Test gegen verfaelschte Fassungen.

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
DETECT="${CHIMERA_TLS_DETECT:-$HERE/lib/detect.sh}"
PAKETE="${CHIMERA_TLS_PAKETE:-$HERE/steps/20-install-packages.sh}"
PASS=0; FAIL=0

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"
	else bad "$1 -- erwartet '$3', bekam '$2'"; fi
}

printf '=== TLS-Voraussetzungen ===\n'

# --- 1. ca-certificates in Modul 20 ---------------------------------------
# Die Liste steht in einer Funktion; sie wird mit dem echten Schritt-Text
# ausgegeben, ohne den Schritt laufen zu lassen.
LISTE="$(sed -n '/^packages_required() {/,/^}/p' "$PAKETE" | sed '1d;$d' | sed '/^cat /d;/^EOF$/d')"
ZEILE="$(printf '%s\n' "$LISTE" | awk -F'\t' '$1 == "ca-certificates"')"
if [ -n "$ZEILE" ]; then ok "ca-certificates steht bei den zwingenden Paketen"
else bad "ca-certificates fehlt bei den zwingenden Paketen"; fi

NACHWEIS="$(printf '%s\n' "$ZEILE" | awk -F'\t' '{ print $2 }')"
case "$NACHWEIS" in
	*ca-certificates.crt*) ok "Nachweis prueft das Buendel, nicht den Paketstand" ;;
	*) bad "Nachweis prueft das Buendel nicht -- '$NACHWEIS'" ;;
esac

# Der Nachweis muss an einem leeren Buendel scheitern und an einem
# gefuellten bestehen. Er wird als Befehl ausgefuehrt, mit umgebogenem Pfad.
W="$(mktemp -d "${TMPDIR:-/tmp}/chimera-tls.XXXXXX" 2>/dev/null)" || W=""
[ -n "$W" ] && [ -d "$W" ] || { echo "kein Testverzeichnis"; exit 2; }
trap 'rm -rf "$W"' EXIT INT TERM
: >"$W/leer.crt"
printf '%s\n' '-----BEGIN CERTIFICATE-----' >"$W/voll.crt"
BEFEHL_LEER="$(printf '%s' "$NACHWEIS" | sed "s|/etc/ssl/certs/ca-certificates.crt|$W/leer.crt|")"
BEFEHL_VOLL="$(printf '%s' "$NACHWEIS" | sed "s|/etc/ssl/certs/ca-certificates.crt|$W/voll.crt|")"
sh -c "$BEFEHL_LEER" >/dev/null 2>&1 && _r=0 || _r=$?
[ "$_r" -ne 0 ] && ok "leeres Buendel: Nachweis scheitert" || bad "leeres Buendel: Nachweis bestand"
sh -c "$BEFEHL_VOLL" >/dev/null 2>&1 && _r=0 || _r=$?
check "gefuelltes Buendel: Nachweis besteht" "$_r" 0
sh -c "$(printf '%s' "$NACHWEIS" | sed "s|/etc/ssl/certs/ca-certificates.crt|$W/fehlt.crt|")" >/dev/null 2>&1 \
	&& _r=0 || _r=$?
[ "$_r" -ne 0 ] && ok "fehlendes Buendel: Nachweis scheitert" || bad "fehlendes Buendel: Nachweis bestand"

# --- 2. Uhr im Preflight ---------------------------------------------------
uhr() { # $1 Zeitpunkt (Sekunden) -> Ausgabe in $W/uhr.aus, rc in $W/uhr.rc
	(
		set +e
		. "$HERE/lib/common.sh"
		. "$DETECT"
		CHIMERA_UHR_JETZT="$1"; export CHIMERA_UHR_JETZT
		uhr_pruefen >"$W/uhr.aus" 2>&1
		echo $? >"$W/uhr.rc"
	)
}

# 2026-10-30 12:00:00 UTC -> plausibel
uhr 1793361600
check "Uhr 2026-10: plausibel (rc 0)" "$(cat "$W/uhr.rc")" 0
# 1970-01-02 -> unplausibel (typischer Pi ohne RTC vor NTP)
uhr 86400
check "Uhr 1970: unplausibel (rc 1)" "$(cat "$W/uhr.rc")" 1
if grep -q 'Uhr steht vor 2026' "$W/uhr.aus"; then ok "unplausible Uhr wird benannt"
else bad "unplausible Uhr wird nicht benannt"; fi
if grep -q 'Zertifikate' "$W/uhr.aus"; then ok "Folge fuer TLS wird genannt"
else bad "Folge fuer TLS wird nicht genannt"; fi
# genau an der Untergrenze: gilt als plausibel
uhr 1767225600
check "Uhr genau an der Untergrenze: plausibel" "$(cat "$W/uhr.rc")" 0
uhr 1767225599
check "Uhr eine Sekunde davor: unplausibel" "$(cat "$W/uhr.rc")" 1
# nicht lesbar
uhr "x"
check "Uhr nicht lesbar: Befund (rc 1)" "$(cat "$W/uhr.rc")" 1
if grep -q 'nicht lesbar' "$W/uhr.aus"; then ok "nicht lesbar wird gesagt, nicht verschwiegen"
else bad "nicht lesbar wird nicht gesagt"; fi

# --- 3. Modul 10 verdrahtet die Pruefung -----------------------------------
if grep -q 'uhr_pruefen' "$HERE/steps/10-check-system.sh"; then ok "Modul 10 ruft die Uhrpruefung auf"
else bad "Modul 10 ruft die Uhrpruefung nicht auf (offenes Ende)"; fi
if grep -q 'UHR_BEFUND' "$HERE/steps/10-check-system.sh" && \
	grep -q 'Befund: Uhr unplausibel' "$HERE/steps/10-check-system.sh"; then ok "Modul 10 wertet den Befund aus"
else bad "Modul 10 wertet den Befund nicht aus"; fi

printf '\nErgebnis: %s ok, %s fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
