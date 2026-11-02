#!/bin/sh
# Tests fuer lib/speicher.sh -- zram + Auslagerungsdatei (Schritt 25).
#
# Geprueft wird die echte Bibliothek (Regel 9) in einer erfundenen Wurzel.
# Werkzeuge stehen als SHELL-FUNKTIONEN bereit (wie test-service.sh):
#
#   findmnt/lsblk/df  liefern erfundene Datentraeger- und Platzwerte
#   systemctl         `restart zramswap` macht, was das Paketskript tut:
#                     disksize = MemTotal*PERCENT/100, zram0 in /proc/swaps
#   dietpi-set_swapfile  eine Attrappen-DATEI unter <wurzel>/boot/...,
#                     die wie das Original zuerst `swapoff -a` macht
#                     (/proc/swaps leer), dann die Datei anlegt und
#                     dietpi.txt schreibt
#
# CHIMERA_SPEICHER_LIB ueberstimmt die Bibliothek (counter-check-speicher.sh).

set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
export HERE
LIB="${CHIMERA_SPEICHER_LIB:-$HERE/lib/speicher.sh}"
PASS=0; FAIL=0

: "${CHIMERA_TESTDIR:=${TMPDIR:-/tmp}}"
[ -d "$CHIMERA_TESTDIR" ] || CHIMERA_TESTDIR="$HERE/.testtmp"
mkdir -p "$CHIMERA_TESTDIR" || { echo "kein brauchbares Testverzeichnis"; exit 1; }
W="$(mktemp -d "$CHIMERA_TESTDIR/chimera-speicher.XXXXXX" 2>/dev/null)" || W=""
if [ -z "$W" ] || [ ! -d "$W" ]; then
	printf 'mktemp lieferte kein Testverzeichnis in %s\n' "$CHIMERA_TESTDIR"
	exit 2
fi
trap 'rm -rf "$W"' EXIT INT TERM

ok()  { PASS=$((PASS+1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check() {
	if [ "$2" = "$3" ]; then ok "$1"
	else bad "$1 -- erwartet '$3', bekam '$2'"; fi
}
hat() {
	if grep -qF -- "$3" "$2" 2>/dev/null; then ok "$1"
	else bad "$1 -- '$3' fehlt in $2"; fi
}

printf '=== Speicher (lib/speicher.sh) ===\n'

# --- Spielfeld ------------------------------------------------------------
# $1 Name, $2 Kartengroesse in Byte, $3 frei in KiB.
# Ausgangszustand wie auf dem echten chimera-pi (11.10.2026 gemessen):
# zram 50 %, Datei /var/swap 32 MiB, MemTotal 473784 kB.
feld() {
	F="$W/$1"; R="$F/root"
	mkdir -p "$R/proc" "$R/etc/default" "$R/boot/dietpi/func" \
		"$R/sys/class/block/mmcblk0" "$R/sys/block/zram0" "$R/var" "$R/opt/chimera/state"
	printf 'MemTotal:         473784 kB\n' >"$R/proc/meminfo"
	printf '%s\n' "$(( $2 / 512 ))" >"$R/sys/class/block/mmcblk0/size"
	printf '%s\n' "$3" >"$F/frei"
	printf 'ALGO=lz4\nPERCENT=50\nSIZE=512\nPRIORITY=100\n' >"$R/etc/default/zramswap"
	cp "$R/etc/default/zramswap" "$F/zram-original"
	printf 'AUTO_SETUP_SWAPFILE_SIZE=32\nAUTO_SETUP_SWAPFILE_LOCATION=/var/swap\n' >"$R/boot/dietpi.txt"
	cp "$R/boot/dietpi.txt" "$F/dietpi-original"
	truncate -s 32M "$R/var/swap"
	echo $((473784 * 1024 * 50 / 100)) >"$R/sys/block/zram0/disksize"
	{
		printf 'Filename\tType\tSize\tUsed\tPriority\n'
		printf '/var/swap file 32764 0 -2\n'
		printf '/dev/zram0 partition %s 0 100\n' $((473784 * 50 / 100))
	} >"$R/proc/swaps"
	printf 'enabled\n' >"$F/zram-enabled"
	: >"$F/spur"; : >"$F/pakete"
	printf 'zram-tools\n' >"$F/pakete"
	# Attrappe des DietPi-Werkzeugs: wie das Original swapoff -a zuerst.
	cat >"$R/boot/dietpi/func/dietpi-set_swapfile" <<'EOF'
#!/bin/sh
R="${TEST_R:?}"; F="${TEST_F:?}"
printf 'dietpi-set_swapfile %s %s\n' "$1" "$2" >>"$F/spur"
printf 'Filename\tType\tSize\tUsed\tPriority\n' >"$R/proc/swaps"
rm -f "$R$2"
truncate -s "${1}M" "$R$2"
printf '%s file %s 0 -2\n' "$2" $(( $1 * 1024 - 4 )) >>"$R/proc/swaps"
printf 'AUTO_SETUP_SWAPFILE_SIZE=%s\nAUTO_SETUP_SWAPFILE_LOCATION=%s\n' "$1" "$2" >"$R/boot/dietpi.txt"
EOF
	chmod +x "$R/boot/dietpi/func/dietpi-set_swapfile"
}

# Dasselbe Feld, aber OHNE eingerichtetes zram: keine Konfiguration, kein
# Geraet, kein Eintrag in /proc/swaps. Nur hier darf der Installer zram anlegen
# (Vorgabe smilez 2.11.: vorhandenes zram wird nie angefasst).
feld_ohne_zram() {
	feld "$@"
	rm -f "$R/etc/default/zramswap" "$R/sys/block/zram0/disksize" "$F/zram-original"
	printf 'Filename\tType\tSize\tUsed\tPriority\n' >"$R/proc/swaps"
	printf '/var/swap file 32764 0 -2\n' >>"$R/proc/swaps"
}

# $1 Funktion (speicher_einrichten / speicher_rueckbau), $2 Modus.
lauf() {
	(
		set +e
		CHIMERA_ROOT="$R"; export CHIMERA_ROOT
		TEST_R="$R"; TEST_F="$F"; export TEST_R TEST_F
		CHIMERA_MANIFEST="$R/opt/chimera/state/manifest.tsv"
		CHIMERA_LOG_DIR="$F"; CHIMERA_LOGFILE=""
		CHIMERA_MODE="${2:-run}"; CHIMERA_STEP=25-speicher
		. "$HERE/lib/common.sh"
		. "$HERE/lib/manifest.sh"
		. "$LIB"

		findmnt() { echo /dev/mmcblk0p2; }
		lsblk()   { echo mmcblk0; }
		df() {
			printf 'Filesystem 1024-blocks Used Available Capacity Mounted\n'
			printf '/dev/root 1 1 %s 1%% /\n' "$(cat "$F/frei")"
		}
		manifest_package_present() { grep -qx "$1" "$F/pakete"; }
		manifest_apt() { printf 'apt %s\n' "$*" >>"$F/spur"; printf '%s\n' "$@" >>"$F/pakete"
			for _p in "$@"; do manifest_record paket "$_p" neu; done; }
		systemctl() {
			printf 'systemctl %s\n' "$*" >>"$F/spur"
			case "$1 ${2:-}" in
				"is-enabled zramswap") cat "$F/zram-enabled"
					[ "$(cat "$F/zram-enabled")" = enabled ] ;;
				"enable zramswap") echo enabled >"$F/zram-enabled" ;;
				"cat zramswap.service")
					# echtes systemd: unbekannte Unit -> Fehler. Hier gibt es eine
					# Unit-Datei nur, wenn das Feld eine anlegt.
					[ -f "$R/etc/default/zramswap" ] ;;
				"restart zramswap")
					. "$R/etc/default/zramswap"
					_b=$((473784 * 1024 * PERCENT / 100))
					echo "$_b" >"$R/sys/block/zram0/disksize"
					grep -v '^/dev/zram0 ' "$R/proc/swaps" >"$F/sw" || true
					printf '/dev/zram0 partition %s 0 %s\n' $((_b / 1024)) "$PRIORITY" >>"$F/sw"
					mv "$F/sw" "$R/proc/swaps" ;;
				*) return 0 ;;
			esac
		}
		"$1" >"$F/aus" 2>&1
		echo $? >"$F/rc"
	)
	RC="$(cat "$F/rc")"
}
zaehle() { grep -c -- "$1" "$F/spur" 2>/dev/null || true; }

# --- Staffel (reine Funktion) --------------------------------------------
(
	CHIMERA_ROOT=""; . "$HERE/lib/common.sh"; . "$LIB"
	for p in 8000000000:2048 16000000000:4096 32000000000:8192 \
	         63999999999:8192 64000000000:16384 128177930240:16384; do
		printf '%s %s\n' "${p%%:*}" "$(speicher_staffel_mib "${p%%:*}")"
	done
) >"$W/staffel"
check "Staffel 8 GB -> 2 GiB"    "$(sed -n 1p "$W/staffel" | cut -d' ' -f2)" 2048
check "Staffel 16 GB -> 4 GiB"   "$(sed -n 2p "$W/staffel" | cut -d' ' -f2)" 4096
check "Staffel 32 GB -> 8 GiB"   "$(sed -n 3p "$W/staffel" | cut -d' ' -f2)" 8192
check "Staffel knapp 64 -> 8 GiB" "$(sed -n 4p "$W/staffel" | cut -d' ' -f2)" 8192
check "Staffel 64 GB -> 16 GiB"  "$(sed -n 5p "$W/staffel" | cut -d' ' -f2)" 16384

# --- Fall 1: zram laeuft -> Speicher bleibt komplett unberuehrt -----------
# Vorgabe smilez 2.11.: kein `swapoff -a`, einfach nichts tun, wenn zram laeuft.
feld erst 128177930240 115811320
cp "$R/var/swap" "$F/swap-vorher"
lauf speicher_einrichten
check "zram laeuft: rc 0" "$RC" 0
check "zram laeuft: kein Dateischritt (kein swapoff -a)" \
	"$(grep -c 'dietpi-set_swapfile' "$F/spur")" 0
check "zram laeuft: Auslagerungsdatei unveraendert" \
	"$(cmp -s "$F/swap-vorher" "$R/var/swap" && echo gleich)" gleich
check "zram laeuft: Konfig unberuehrt (PERCENT bleibt 50)" \
	"$(grep -c '^PERCENT=50$' "$R/etc/default/zramswap")" 1
if cmp -s "$F/zram-original" "$R/etc/default/zramswap"; then
	ok "zram laeuft: Konfiguration byte-gleich"
else bad "zram laeuft: Konfiguration veraendert"; fi
check "zram laeuft: zram nicht angehalten oder gestartet" \
	"$(grep -c 'zramswap' "$F/spur")" 0
check "zram laeuft: kein Manifest-Eintrag fuer die Datei" \
	"$(awk -F'\t' '$3=="swapdatei"' "$R/opt/chimera/state/manifest.tsv" 2>/dev/null | grep -c .)" 0
hat "zram laeuft: benannt" "$F/aus" "bleiben unberuehrt"

# --- Fall 1b: kein zram -> wird angelegt (nur hier!) ----------------------
feld_ohne_zram neu 128177930240 115811320
lauf speicher_einrichten
check "Anlegen: rc 0" "$RC" 0
check "Anlegen: Konfig PERCENT=75 geschrieben" \
	"$(grep -c '^PERCENT=75$' "$R/etc/default/zramswap")" 1
check "Anlegen: zram aktiv" "$(grep -c '^/dev/zram0 ' "$R/proc/swaps")" 1
check "Anlegen: zram 75 % von MemTotal" \
	"$(cat "$R/sys/block/zram0/disksize")" $((473784 * 1024 * 75 / 100))
check "Anlegen: zram vor der Datei (Prioritaet)" \
	"$(awk '$1=="/dev/zram0"{z=$5} $1=="/var/swap"{d=$5} END{print (z>d)?"ja":"nein"}' "$R/proc/swaps")" ja
check "Anlegen: kein Original zu sichern (es gab keins)" \
	"$(awk -F'\t' '$3=="sicherung" && $5 ~ /zramswap$/' "$R/opt/chimera/state/manifest.tsv" | grep -c .)" 0

# --- Fall 1c: zweiter Lauf auf angelegtem zram -> nichts mehr -------------
: >"$F/spur"
cp "$R/etc/default/zramswap" "$F/zram-nach-1b"
lauf speicher_einrichten
check "Zweitlauf nach Anlegen: rc 0" "$RC" 0
check "Zweitlauf nach Anlegen: kein zram-Neustart" "$(zaehle 'restart zramswap')" 0
check "Zweitlauf nach Anlegen: keine neuen Starts" "$(zaehle 'start zramswap')" 0
if cmp -s "$F/zram-nach-1b" "$R/etc/default/zramswap"; then
	ok "Zweitlauf nach Anlegen: Konfig unveraendert"
else bad "Zweitlauf nach Anlegen: Konfig veraendert"; fi

# --- Fall 2: zweiter Lauf aendert nichts (Regel 5e) ----------------------
feld zweit 128177930240 115811320
: >"$F/spur"
if [ -f "$R/opt/chimera/state/manifest.tsv" ]; then
	cp "$R/opt/chimera/state/manifest.tsv" "$F/manifest-1"
else
	: >"$F/manifest-1"
fi
lauf speicher_einrichten
check "Zweitlauf: rc 0" "$RC" 0
check "Zweitlauf: Werkzeug nicht aufgerufen" "$(zaehle dietpi-set_swapfile)" 0
check "Zweitlauf: kein zram-Neustart" "$(zaehle 'restart zramswap')" 0
check "Zweitlauf: kein Eintrag fuer die Auslagerungsdatei" \
	"$(awk -F'\t' '$3=="swapdatei"' "$R/opt/chimera/state/manifest.tsv" 2>/dev/null | grep -c .)" 0

# --- Fall 3: Karte gewechselt, zram laeuft -> auch dann nichts -----------
printf '%s\n' $((32000000000 / 512)) >"$R/sys/class/block/mmcblk0/size"
: >"$F/spur"
lauf speicher_einrichten
check "Kartenwechsel: rc 0" "$RC" 0
check "Kartenwechsel bei laufendem zram: kein Dateischritt" \
	"$(grep -c 'dietpi-set_swapfile' "$F/spur")" 0
check "Kartenwechsel bei laufendem zram: kein zram-Neustart" "$(zaehle 'restart zramswap')" 0
check "Kartenwechsel bei laufendem zram: kein Eintrag fuer die Datei" \
	"$(awk -F'\t' '$3=="swapdatei"' "$R/opt/chimera/state/manifest.tsv" 2>/dev/null | grep -c .)" 0
check "Kartenwechsel: keine zram-Sicherung (Konfig nie geschrieben)" \
	"$(awk -F'\t' '$3=="sicherung" && $5 ~ /zramswap$/' "$R/opt/chimera/state/manifest.tsv" | grep -c .)" 0

# --- Fall 4: zu wenig Platz -> nicht kuerzen, Befund ---------------------
feld_ohne_zram eng 128177930240 $(( 10 * 1024 * 1024 ))
lauf speicher_einrichten
check "Platzmangel: rc 1" "$RC" 1
check "Platzmangel: Werkzeug nicht aufgerufen" "$(zaehle dietpi-set_swapfile)" 0
check "Platzmangel: Datei bleibt 32 MiB" "$(stat -c %s "$R/var/swap")" $((32 * 1048576))
if grep -q 'Nicht gekuerzt' "$F/aus"; then ok "Platzmangel: benannt"
else bad "Platzmangel: nicht benannt"; fi

# --- Fall 5: Trockenlauf aendert nichts ----------------------------------
feld trocken 128177930240 115811320
lauf speicher_einrichten dry
check "Trockenlauf: rc 0" "$RC" 0
check "Trockenlauf: Werkzeug nicht aufgerufen" "$(zaehle dietpi-set_swapfile)" 0
if cmp -s "$F/zram-original" "$R/etc/default/zramswap"; then ok "Trockenlauf: zram-Konfig unberuehrt"
else bad "Trockenlauf: zram-Konfig geaendert"; fi

# --- Fall 6: fremder zram-Verwalter -> zram ueberspringen, nicht abbrechen
feld fremd 128177930240 115811320
printf 'rpi-swap\n' >>"$F/pakete"
lauf speicher_einrichten
check "rpi-swap: rc 0 (kein Abbruch)" "$RC" 0
check "rpi-swap: zram-Konfig unberuehrt" "$(cmp -s "$F/zram-original" "$R/etc/default/zramswap" && echo gleich)" gleich
check "rpi-swap: zram nicht neu gestartet" "$(zaehle 'restart zramswap')" 0
check "rpi-swap: zram nicht angehalten" "$(zaehle 'stop zramswap')" 0
if grep -q 'zram wird bereits verwaltet' "$F/aus"; then ok "rpi-swap: benannt"
else bad "rpi-swap: nicht benannt"; fi

# --- Fall 7: zram-tools fehlt UND kein zram -> installiert, als neu vermerkt
feld_ohne_zram ohne 128177930240 115811320
: >"$F/pakete"
lauf speicher_einrichten
check "ohne zram-tools: rc 0" "$RC" 0
check "ohne zram-tools: installiert" "$(zaehle 'apt zram-tools')" 1
check "ohne zram-tools: enable" "$(zaehle 'enable zramswap')" 0
check "ohne zram-tools: als neu vermerkt" \
	"$(awk -F'\t' '$3=="paket" && $4=="zram-tools"{print $5}' "$R/opt/chimera/state/manifest.tsv")" neu

# --- Fall 8: Rueckbau stellt den Ausgangszustand her ---------------------
feld_ohne_zram rueck 128177930240 115811320
lauf speicher_einrichten
: >"$F/spur"
lauf speicher_rueckbau
check "Rueckbau: rc 0" "$RC" 0
check "Rueckbau: Werkzeug mit Ausgangswerten" "$(zaehle 'dietpi-set_swapfile 32 /var/swap')" 1
if cmp -s "$F/dietpi-original" "$R/boot/dietpi.txt"; then ok "Rueckbau: dietpi.txt wie vorher"
else bad "Rueckbau: dietpi.txt weicht ab"; fi
# Ohne vorheriges zram gab es kein Original: Die angelegte Konfiguration bleibt,
# der Rueckbau hat nichts wiederherzustellen, was er nicht selbst angelegt haette.
check "Rueckbau: angelegte Konfiguration bleibt (kein Original vorhanden)" \
	"$(grep -c '^PERCENT=75$' "$R/etc/default/zramswap")" 1
check "Rueckbau: zram bleibt aktiv" "$(grep -c '^/dev/zram0 ' "$R/proc/swaps")" 1

printf '\nErgebnis: %d ok, %d fehlgeschlagen\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
