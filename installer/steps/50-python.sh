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
. "$_HERE/lib/source.sh"
. "$_HERE/lib/display.sh"
. "$_HERE/lib/python.sh"

CHIMERA_STEP="50-python"; export CHIMERA_STEP
# Profil-Puffer von lib/display.sh (je Lauf) am Ende wegraeumen.
trap 'display_cache_leeren' EXIT

[ -n "${CHIMERA_LOGFILE:-}" ] || log_open "python" || \
	warn "Kein Protokoll moeglich -- Lauf wird nicht festgehalten."

VENV="$(rootpath "$CHIMERA_VENV")"
# REPO ist der Baum, aus dem dieser Schritt laeuft -- nach Schritt 00 ist
# das source/. Der Dienst laeuft aber nicht aus source/, sondern aus
# productive/code (DESIGN Regel 10r): Ein neues source/ aendert am
# laufenden Dienst nichts, erst dieser Schritt bringt den Stand hinueber.
REPO="$(cd "$_HERE/.." && pwd)"
CODE="$(rootpath "$CHIMERA_CODE")"
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
# Ablage: /opt/chimera/config (root). Die Gruppe chimera und die Rechte
# 750/640 setzt Schritt 98, sobald es den Nutzer gibt; bis dahin 700/600.
ENV_DIR="$(rootpath "$CHIMERA_CONFIG")"
ENV_FILE="$ENV_DIR/.env"

if [ -f "$ENV_EXAMPLE" ]; then
	if [ -f "$ENV_FILE" ]; then
		info "Umgebungskonfiguration vorhanden: $ENV_FILE (bleibt unangetastet)"
	else
		if is_dry_run; then
			info "[wuerde ablegen] $ENV_FILE (aus .env.example)"
		else
			( umask 077; mkdir -p "$ENV_DIR" ) || {
				err "Konfigurationsverzeichnis nicht anlegbar: $ENV_DIR"
				log_close 2; exit 2
			}
			cp "$ENV_EXAMPLE" "$ENV_FILE" || {
				err "Umgebungskonfiguration nicht anlegbar: $ENV_FILE"
				log_close 2; exit 2
			}
			chmod 600 "$ENV_FILE"
			cp "$ENV_EXAMPLE" "$ENV_DIR/.env.example" 2>/dev/null || true
			# config/ NICHT als verzeich: Den Rueckbau von 50 soll sie
			# ueberleben (nur opt-in loeschen, Regel 10r).
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
	#
	# Und es muss pip haben. `python3 -m venv` ohne ensurepip legt Ordner,
	# pyvenv.cfg und Interpreter an und scheitert ERST danach -- am
	# chimera-pi (11.10.2026) blieb so ein venv ohne pip liegen, der
	# naechste Lauf hielt es fuer fertig, und pip install brach ab.
	[ -x "$PY" ] && "$PY" -c 'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)' \
		>/dev/null 2>&1 && "$PY" -m pip --version >/dev/null 2>&1
}

# --- Anzeige: welche Abhaengigkeiten gehoeren dazu? ------------------------
#
# Schritt 40 hat festgehalten, welche Anzeige es ist (state/anzeige). Ihre
# Abhaengigkeiten stehen in display.json des Anzeigemoduls
# (src/chimera/displays/<typ>/, Feld deps.pip / deps.apt) -- derselben
# Datei, die der Python-Treiber liest. Seit 11.10.2026 ist der Paneltreiber
# eigener Code im Repo (DESIGN 5f-Ergaenzung): kein Herstellerbaum mehr im
# venv, keine zweite .pth, kein spidev/gpiod-Quellbau. Was bleibt, sind
# Pillow und numpy -- und die stehen fuer alle Anzeigen in requirements.txt.
ANZEIGE="$(cat "$(rootpath "$CHIMERA_STATE")/anzeige" 2>/dev/null || true)"
ANZEIGE_PIP=""; ANZEIGE_APT=""
if [ -n "$ANZEIGE" ]; then
	if display_profil_lesbar "$ANZEIGE"; then
		ANZEIGE_PIP="$(display_get "$ANZEIGE" pip)"
		ANZEIGE_APT="$(display_get "$ANZEIGE" apt)"
	else
		warn "Anzeige '$ANZEIGE' (state/anzeige) hat kein Modul unter src/chimera/displays/."
		warn "Bekannt: $(display_list)"
	fi
fi

# Ist das Anzeigemodul im venv ladbar? Ueber die Registry, OHNE das Panel
# zu oeffnen: Oeffnen belegte GPIO-Leitungen, die der laufende Dienst haelt.
# Ohne festgehaltene Anzeige ist nichts nachzuweisen.
treiber_ok() {
	[ -n "$ANZEIGE" ] || return 0
	[ -x "$PY" ] || return 1
	"$PY" -c 'import sys; from chimera.displays import registry; registry.panel_klasse(sys.argv[1])' \
		"$ANZEIGE" >/dev/null 2>&1
}

# site-packages des venv -- EINE Stelle fuer beide .pth-Dateien. Liefert
# nie einen leeren Pfad (sonst landete die .pth unter "/").
venv_sitedir() {
	_vs="$("$PY" -c 'import sysconfig; print(sysconfig.get_path("purelib"))' 2>/dev/null)"
	# Laeuft in $(...): ein exit hier beendet nur die Subshell. Deshalb
	# rc 1 liefern; der Aufrufer bricht ab (`|| { ...; exit 2; }`).
	if [ -z "$_vs" ] || [ ! -d "$_vs" ]; then
		err "site-packages-Pfad nicht feststellbar im venv."
		return 1
	fi
	printf '%s\n' "$_vs"
}

# Der Nachweis des Moduls: ohne Netz, ohne Hardware. Beides macht --pruefen
# nie rot -- kein Anbieter und ein Panel, das nicht aufgeht, sind Auskunft,
# kein Fehler. Gekostet hat es trotzdem: Beim Boot suchte --pruefen Ollama
# im Netz, bevor es stand, und oeffnete das Panel, das gleich der Dienst
# braucht (laeuft er schon, scheiterte das Oeffnen an belegten Leitungen).
# Gemessen chimera-pi, Dienst gestoppt: 3,9 s mit beidem, 1,6 s ohne.
# Ob das Anzeigemodul ladbar ist, prueft treiber_ok -- ohne es zu oeffnen.
nachweis_modul() {
	CHIMERA_ANZEIGE=keine "$PY" -m chimera --pruefen --offline
}

pruef_ok() {
	# Das Modul selbst -- es kennt --pruefen und meldet, was da ist.
	# Dazu die Abhaengigkeiten MIT Version (pydep_fehlend): --pruefen laeuft
	# auch mit altem numpy durch. Und das Anzeigemodul: Ein Dienst, der
	# mit NullPanel startet, besteht --pruefen, zeigt aber nichts.
	[ -x "$PY" ] && nachweis_modul >/dev/null 2>&1 \
		&& pydep_fehlend "$PY" $(pydep_liste "$REQUIREMENTS") $ANZEIGE_PIP >/dev/null 2>&1 \
		&& treiber_ok
}

# --- Code nach productive/ ------------------------------------------------
# Wie Schritt 00: gleicher Inhalt -> nichts zu tun. Kein Versionsvergleich
# hier -- ueber die Version hat Schritt 00 schon entschieden; was in
# source/ steht, ist der gewollte Stand.
log "Code"
# rc 1 = nicht eindeutig pruefbar; ohne `||` beendete set -e den Schritt
# hier still mit rc 1 statt mit der Meldung darunter.
_soll="$(source_hash "$REPO")" || _soll=""
[ -n "$_soll" ] || { err "Pruefsumme von $REPO leer -- Abbruch."; log_close 2; exit 2; }
_ist="$(source_hash "$CODE" 2>/dev/null || true)"
if [ "$_soll" = "$_ist" ]; then
	info "productive/code ist bereits dieser Stand."
elif is_dry_run; then
	info "[wuerde kopieren] $REPO -> $CHIMERA_CODE"
else
	if ! is_dry_run && [ "$(id -u)" != 0 ]; then
		err "productive/ gehoert root -- nur als Verwalter."; log_close 2; exit 2
	fi
	source_reparieren "$CODE"
	source_kopieren "$REPO" "$CODE" "$_soll" || {
		err "productive/code nicht erneuert."; log_close 2; exit 2; }
	manifest_has verzeich "$CODE" || manifest_record verzeich "$CODE" ""
	info "productive/code = $(source_version "$CODE")"
fi
log ""

if pruef_ok; then
	log "Die Python-Umgebung ist bereit und nachweisbar."
	info "venv: $VENV"
	log_close 0; exit 0
fi

# --- Voraussetzungen ------------------------------------------------------
if ! is_dry_run && [ "$(id -u)" != 0 ]; then
	err "Dieses Modul legt $CHIMERA_VENV an und installiert Pakete --"
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
#
# Gepruefte Faehigkeit ist `ensurepip`, nicht `import venv`: Auf Debian
# trixie liegt das Modul venv in libpython3.13-stdlib, ensurepip aber erst
# in python3.13-venv. `import venv` gelingt dann, `python3 -m venv` scheitert
# -- am chimera-pi (DietPi 10.7.2) am 11.10.2026 genau so gelaufen: der
# Schritt meldete "vorhanden", und der Lauf brach beim Anlegen ab.
if python3 -c 'import venv, ensurepip' >/dev/null 2>&1; then
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
		info "[wuerde merken] verzeich $CHIMERA_VENV"
	else
		# Das venv wird neu angelegt, wenn es kaputt ist -- es gehoert
		# ganz uns, dafuer steht der Eintrag im Manifest.
		# Unbrauchbar heisst: venv_ready sagte nein, obwohl ein Ordner da
		# ist (kein Interpreter, oder kein pip). Nicht nur am fehlenden
		# Interpreter festmachen -- das halbe venv hat einen.
		if [ -d "$VENV" ]; then
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
	info "[wuerde sicherstellen] $(pydep_liste "$REQUIREMENTS" | tr '\n' ' ')"
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

	# shellcheck disable=SC2046
	pydep_ensure "$PY" $(pydep_liste "$REQUIREMENTS") || {
		err "Abhaengigkeiten nicht hergestellt (Anforderungen: $REQUIREMENTS)."
		log_close 2; exit 2
	}
fi
log ""

# --- Anzeigetreiber -------------------------------------------------------
if [ -n "$ANZEIGE" ] && { [ -n "$ANZEIGE_PIP" ] || [ -n "$ANZEIGE_APT" ]; }; then
	log "Abhaengigkeiten der Anzeige ($ANZEIGE)"
	if is_dry_run; then
		[ -n "$ANZEIGE_APT" ] && info "[wuerde sicherstellen] Systempakete: $ANZEIGE_APT"
		[ -n "$ANZEIGE_PIP" ] && info "[wuerde sicherstellen] $ANZEIGE_PIP"
	else
		# Systempakete nur, wenn sie fehlen (wie PiPortal ensure_pkg);
		# manifest_apt haelt vorher_da/neu fest.
		if [ -n "$ANZEIGE_APT" ]; then
			_aa_fehlt=""
			for _aa_p in $ANZEIGE_APT; do
				manifest_package_present "$_aa_p" || _aa_fehlt="$_aa_fehlt $_aa_p"
			done
			if [ -n "$_aa_fehlt" ]; then
				manifest_apt $_aa_fehlt || {
					err "Systempakete fuer die Anzeige nicht installierbar:$_aa_fehlt"
					log_close 2; exit 2
				}
			else
				info "Systempakete vorhanden: $ANZEIGE_APT"
			fi
		fi
		# shellcheck disable=SC2086
		pydep_ensure "$PY" $ANZEIGE_PIP || { log_close 2; exit 2; }
	fi
	log ""
elif [ -n "$ANZEIGE" ]; then
	info "Anzeige $ANZEIGE braucht keine weiteren Abhaengigkeiten."
else
	info "Keine Anzeige festgehalten (Schritt 40)."
fi

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
_srcdir="$CODE/src"

if is_dry_run; then
	info "[wuerde verdrahten] $_srcdir als chimera.pth"
else
	if [ ! -d "$_srcdir/chimera" ]; then
		err "Das Modulverzeichnis fehlt im Repo: $_srcdir/chimera."
		err "Ohne es ist nichts zu verdrahten -- Abbruch."
		log_close 2; exit 2
	fi
	_sd="$(venv_sitedir)" || { log_close 2; exit 2; }
	_pth="$_sd/chimera.pth"
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
	info "Nachweis: CHIMERA_ANZEIGE=keine $PY -m chimera --pruefen --offline"
	log_close 0; exit 0
fi

if is_dry_run; then
	info "[wuerde pruefen] CHIMERA_ANZEIGE=keine $PY -m chimera --pruefen --offline"
	log_close 0; exit 0
fi

err "Das Modul laeuft im venv nicht durch (--pruefen)."
err "Grund: fehlende Python-Pakete oder ein Fehler im Modul selbst."
nachweis_modul 2>&1 | tail -5 >&2 || true
log_close 2; exit 2
