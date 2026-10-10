#!/bin/sh
# Chimera installer -- Modul 50: Python-Umgebung.
#
# Chimera ist ein Python-Dauerprozess. Seine Abhaengigkeiten brauchen
# einen eigenen Bereich -- Debian haelt /usr/lib/python3 von apt ab und
# lehnt pip dort seit Trixie ab (PEP 668). Zwei Wege loesen das: ein
# venv oder Systempakete mit --break-system-packages. Wir nehmen das
# venv, denn Systempakete koennten mit apt-Konflikten kollidieren und
# --break-system-packages setzt genau die Tuer aus, die Debian aus
# gutem Grund schliesst.
#
# Exitcode:
#   0  Umgebung bereit, `--pruefen` im venv laeuft durch
#   1  Befund: nichts zu tun, oder Umgebung unvollstaendig
#   2  abgebrochen -- Voraussetzung fehlt

set -eu

_HERE="$(cd "$(dirname "$0")/.." && pwd)"
. "$_HERE/lib/common.sh"
. "$_HERE/lib/network.sh"
. "$_HERE/lib/manifest.sh"
. "$_HERE/lib/module.sh"

CHIMERA_STEP="50-python"; export CHIMERA_STEP

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "python" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

VENV="$(rootpath /opt/chimera/venv)"
REPO="$(cd "$_HERE/.." && pwd)"
REQUIREMENTS="$REPO/requirements.txt"
ENV_EXAMPLE="$REPO/.env.example"
PY="$VENV/bin/python"

log "Chimera Python-Umgebung"
log ""

# --- Umgebungskonfiguration ------------------------------------------------
# Die Vorlage .env.example liegt im Repo (Platzhalter, nie echte Werte,
# Zugangsdaten gehoeren nicht ins Repo). Der Installer legt sie als
# /etc/chimera/.env ab, WENN dort noch keine steht -- eine von Hand
# ausgefuellte Datei wird nie ueberschrieben. Die Vorlage liegt daneben,
# damit ein Ausfuellen nachtraeglich uebersichtlich bleibt.
#
# Fehlende Werte werden benannt: `python -m chimera --pruefen` nennt
# jeden Connector, der wegen eines Platzhalters oder fehlenden Schluessels
# nicht verfuegbar ist.
ENV_DIR="$(rootpath /etc/chimera)"
ENV_FILE="$ENV_DIR/.env"

if [ -f "$ENV_EXAMPLE" ]; then
	if [ -f "$ENV_FILE" ]; then
		info "Umgebungskonfiguration vorhanden: $ENV_FILE (bleibt unangetastet)"
	else
		if is_dry_run; then
			info "[wuerde ablegen] $ENV_FILE (aus .env.example)"
		else
			mkdir -p "$ENV_DIR" || {
				err "Konfigurationsverzeichnis nicht anlegbar: $ENV_DIR"
				log_close 2; exit 2
			}
			cp "$ENV_EXAMPLE" "$ENV_FILE" || {
				err "Umgebungskonfiguration nicht anlegbar: $ENV_FILE"
				log_close 2; exit 2
			}
			chmod 600 "$ENV_FILE"
			manifest_record datei "$ENV_FILE" \
				"$(sha256sum "$ENV_FILE" 2>/dev/null | cut -d' ' -f1)"
			info "Umgebungskonfiguration abgelegt: $ENV_FILE"
			warn "Werte eintragen: OLLAMA_API_BASE, ANTHROPIC_API_KEY oder"
			warn "Abo-Anmeldung. Was fehlt, nennt 'python -m chimera --pruefen'."
		fi
	fi
else
	warn ".env.example fehlt im Repo -- keine Umgebungskonfiguration abgelegt."
fi
log ""

# --- Was brauchen wir? ----------------------------------------------------
# Die Anforderungen stehen in der Repo-Datei, nicht im Schritt: Ein
# Schritt, der Paketnamen dupliziert, waere eine zweite Quelle fuer
# dieselbe Sache (Regel 10g).
[ -f "$REQUIREMENTS" ] || {
	err "requirements.txt fehlt im Repo ($REQUIREMENTS)."
	log_close 2; exit 2
}
# Und die Datei darf nicht leer sein -- eine leere Liste haette noch
# nie ein Modul mit gebrauchten Abhaengigkeiten beschrieben. "Leer"
# heisst hier: ohne eine Zeile, die nicht Kommentar und nicht leer ist.
# Zeilenweise geprueft, nicht zeichenweise -- "# nur ein Kommentar"
# ist ein Kommentar, auch wenn nach dem Leerzeichen Worte stehen.
if ! grep -vE '^[[:space:]]*(#|$)' "$REQUIREMENTS" | grep -q '[^[:space:]]'; then
	err "requirements.txt enthaelt nur Kommentare oder ist leer."
	log_close 2; exit 2
fi

venv_ready() {
	# Ein venv ist fertig, wenn sein Python es selbst sagt, nicht wenn
	# das Verzeichnis existiert: pyvenv.cfg kann da sein, der Interpreter
	# trotzdem kaputt. Der Befehl beweist, dass er laeuft (Regel 10j).
	[ -x "$PY" ] && "$PY" -c 'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)' \
		>/dev/null 2>&1
}

pruef_ok() {
	# Das Modul selbst -- es kennt --pruefen und meldet, was da ist.
	[ -x "$PY" ] && "$PY" -m chimera --pruefen >/dev/null 2>&1
}

if pruef_ok; then
	log "Die Python-Umgebung ist bereit und nachweisbar."
	info "venv: $VENV"
	log_close 0; exit 0
fi

# --- Voraussetzungen ------------------------------------------------------
if ! is_dry_run && [ "$(id -u)" != 0 ]; then
	err "Dieses Modul legt /opt/chimera/venv an und installiert Pakete --"
	err "das geht nur als Verwalter."
	err "  sudo sh $0"
	log_close 2; exit 2
fi

# python3-venv ist die Falle: Debian haelt es getrennt, DietPi auch.
# Ohne es bricht `python3 -m venv` mit einer mehrzeiligen Fehlermeldung
# ab, die an --ensurepip haengt.
#
# Aber: die FAEHIGKEIT zaehlt, nicht der Paketname. Auf einem System,
# wo `python3 -m venv` schon funktioniert, ist kein Paket zu holen --
# genau dieselbe Lehre wie bei `have_cmd` (I4). Erst pruefen, was geht,
# dann fehlendes nachholen.
if python3 -c 'import venv' >/dev/null 2>&1; then
	info "python3 -m venv vorhanden -- kein Paket noetig."
else
	log "Voraussetzungen"
	if ! have_cmd python3; then
		err "python3 fehlt -- Schritt 20 haette es holen muessen."
		log_close 2; exit 2
	fi
	if is_dry_run; then
		info "[wuerde holen] python3-venv python3-pip (falls fehlend)"
	else
		# Nur nachholen, wenn fehlt -- sonst wuerde der zweite Lauf nichts
		# aendern und der erste staende als Abhaengigkeit im Manifest.
		_holt=""
		for _pl_p in python3-venv python3-pip; do
			manifest_package_present "$_pl_p" || _holt="$_holt $_pl_p"
		done
		if [ -n "$_holt" ]; then
			manifest_apt $_holt || {
				err "python3-venv/python3-pip nicht installierbar."
				log_close 2; exit 2
			}
		else
			info "python3-venv und python3-pip vorhanden."
		fi
	fi
fi
log ""

# --- venv anlegen ---------------------------------------------------------
log "Umgebung"
if venv_ready; then
	info "venv vorhanden: $VENV"
else
	if is_dry_run; then
		info "[wuerde anlegen] python3 -m venv $VENV"
		info "[wuerde merken] verzeich /opt/chimera/venv"
	else
		# Das venv wird neu angelegt, wenn es kaputt ist -- es gehoert
		# ganz uns, dafuer steht der Eintrag im Manifest.
		if [ -d "$VENV" ] && [ ! -x "$PY" ]; then
			warn "venv vorhanden, aber unbrauchbar -- wird neu angelegt."
			rm -rf "$VENV"
		fi
		if ! python3 -m venv "$VENV"; then
			err "venv nicht anlegbar unter $VENV."
			err "Laesst python3-venv nachholen? apt install python3-venv"
			log_close 2; exit 2
		fi
		manifest_record verzeich "$VENV" ""
		info "venv angelegt: $VENV"
	fi
fi

# --- Pakete ---------------------------------------------------------------
log "Abhaengigkeiten"
if is_dry_run; then
	info "[wuerde installieren] $(tr -d '\n' <"$REQUIREMENTS" | sed 's/#.*//; s/  */ /g')"
else
	# pip-Pakete ins venv -- hier geht es um die Abhaengigkeiten des
	# Python-Moduls, NICHT um Debian-Pakete. Sie stehen NICHT im Manifest
	# als `paket` (das waere die falsche Art); als `verzeich`-Eintrag
	# besser: das venv selbst ist der vom Installer angelegte Bereich, die
	# Pakete darin gehoeren dazu. Ein Rueckbau entfernt das venv als
	# Ganzes, und damit auch seine Pakete.
	manifest_record verzeich "$VENV" ""

	# --upgrade Pip selbst zuerst: alte pip-Fassungen verstehen neuere
	# Wheel-Tags nicht und brechen mit kryptischem Fehler ab.
	"$PY" -m pip install --upgrade pip >/dev/null 2>&1 || true

	if "$PY" -m pip install -r "$REQUIREMENTS"; then
		info "Abhaengigkeiten installiert."
	else
		err "pip hat die Abhaengigkeiten nicht installiert."
		err "Anforderungen: $REQUIREMENTS"
		log_close 2; exit 2
	fi
fi
log ""

# --- Verdrahtung ----------------------------------------------------------
#
# Das Modul wird NICHT ins venv kopiert: ein `git pull` plus Installerlauf
# muss genuegen (Regel 10). Statt einer Kopie verdrahtet eine .pth-Datei
# im site-packages des venv den Quellpfad des REPOS, aus dem dieser
# Installer laeuft. `python -m chimera` ist dann erreichbar, und das
# Modul folgt dem Repo.
#
# Der Pfad ist der Aufruferkontext, kein Hardcode: Der Installer lebt im
# geklonten Repo, dorthin gehoert auch der Quelltext. _HERE ist bereits
# das Repo -- dirname($0)/.. -- eine Ebene weiter hoch waere es daneben.
_REPO="$REPO"
_srcdir="$_REPO/src"

if is_dry_run; then
	info "[wuerde verdrahten] $_srcdir als chimera.pth"
else
	if [ ! -d "$_srcdir/chimera" ]; then
		err "Das Modulverzeichnis fehlt im Repo: $_srcdir/chimera."
		err "Ohne es ist nichts zu verdrahten -- Abbruch."
		log_close 2; exit 2
	fi
	_sitedir="$("$PY" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')" || {
		err "site-packages-Pfad nicht feststellbar im venv."
		log_close 2; exit 2
	}
	_pth="$_sitedir/chimera.pth"
	printf '%s\n' "$_srcdir" | write_atomic "$_pth" || {
		err "Verdrahtung nicht anlegbar: $_pth"
		log_close 2; exit 2
	}
	manifest_record datei "$_pth" "$(sha256sum "$_pth" 2>/dev/null | cut -d' ' -f1)"
	info "Verdrahtet: $_pth -> $_srcdir"
fi
log ""

# --- Nachweis -------------------------------------------------------------
# Nicht "pip meldet Erfolg", sondern: das Modul selbst laeuft. `--pruefen`
# sagt, was da ist; sein Exitcode ist das Urteil (Regel 10j).
if pruef_ok; then
	log "Ergebnis: Python-Umgebung bereit und nachweisbar."
	info "venv: $VENV"
	info "Nachweis: $PY -m chimera --pruefen"
	log_close 0; exit 0
fi

if is_dry_run; then
	info "[wuerde pruefen] $PY -m chimera --pruefen"
	log_close 0; exit 0
fi

err "Das Modul laeuft im venv nicht durch (--pruefen)."
err "Grund: fehlende Python-Pakete oder ein Fehler im Modul selbst."
"$PY" -m chimera --pruefen 2>&1 | tail -5 >&2 || true
log_close 2; exit 2
