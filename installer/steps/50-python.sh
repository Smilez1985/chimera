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

# Der Nachweis (lib/py/nachweis.py), in EINEM Python-Start:
#   - die Abhaengigkeiten MIT Version (dieselbe Messung wie pydep_fehlend):
#     --pruefen laeuft auch mit altem numpy durch;
#   - das Anzeigemodul ueber die Registry, OHNE das Panel zu oeffnen
#     (Oeffnen belegte die Leitungen, die der laufende Dienst haelt) -- ein
#     Dienst, der mit NullPanel startet, besteht --pruefen, zeigt aber nichts;
#   - das Modul selbst: --pruefen --offline mit CHIMERA_ANZEIGE=keine. Kein
#     Anbieter und ein Panel, das nicht aufgeht, machen --pruefen nie rot;
#     die Suche im Netz und das Oeffnen kosteten beim Boot aber Zeit.
# Gemessen chimera-pi, Dienst gestoppt: drei Starts 2,6 s warm / 4,7 s kalt,
# einer 1,7 s / 3,8 s.
NACHWEIS_PY="$_HERE/lib/py/nachweis.py"
nachweis() {
	# shellcheck disable=SC2046,SC2086
	"$PY" "$NACHWEIS_PY" ${ANZEIGE:+--anzeige "$ANZEIGE"} -- \
		$(pydep_liste "$REQUIREMENTS") $ANZEIGE_PIP
}

pruef_ok() {
	[ -x "$PY" ] && [ -f "$NACHWEIS_PY" ] && nachweis >/dev/null 2>&1
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

# --- Fassungen auffrischen (Vorgabe smilez, 5.11.2026) --------------------
#
# "Immer die neueste Fassung, die mit allem anderen kompatibel ist." Ein
# Abhaengigkeit kann auf dem Geraet liegen, bevor der Installer je lief, und
# dabei veraltet sein -- eine vorhandene Fassung ist kein Beweis fuer eine
# aktuelle. Deshalb wird bei JEDEM Lauf gegen den Index abgeglichen
# (`--upgrade` ist Vorgabe in lib/python.sh), nicht nur wenn etwas fehlt.
#
# Reihenfolge, und warum sie so ist: Stand sichern -> auffrischen ->
# nachweisen -> im Zweifel zurueck. Der Nachweis entscheidet, nicht der
# Exitcode von pip. Ohne Sicherung wird nicht zurueckgerollt (dann gibt es
# nichts, wohin), aber auch nicht schweigend weitergemacht.
#
# Eine Stelle fuer beide Wege -- gesunde Umgebung und Herstellen. Zwei
# Kopien dieser Reihenfolge waeren zwei Verhalten (Regel 10g).
#
# Rueckgabe 0 = Umgebung in Ordnung, 2 = Rueckfall gescheitert.
# $1 optional --ohne-nachweis, dann $@ = Anforderungen
#
# --ohne-nachweis braucht der Weg, auf dem die Umgebung erst entsteht: Dort
# ist die .pth-Datei noch nicht verdrahtet, `pruef_ok` waere also immer
# falsch und ein "Rueckfall" wuerde eine gesunde Installation zerlegen. Den
# Nachweis fuehrt dieses Modul am Ende selbst.
auffrischen() {
	_ak_nachweis=1
	[ "${1:-}" = --ohne-nachweis ] && { _ak_nachweis=0; shift; }
	# Dieselbe Anforderung kommt zweimal, wenn requirements.txt und das
	# Anzeigenprofil sie beide nennen (Pillow, numpy -- am Pi im Protokoll
	# gesehen: "hole Pillow>=10.0.0 numpy>=1.26 Pillow>=10.0 numpy>=1.26").
	# pip stoert das nicht, dem Protokoll sieht man es aber an.
	_ak_liste=""
	for _ak_a in "$@"; do
		case " $_ak_liste " in
			*" $_ak_a "*) continue ;;
		esac
		_ak_liste="$_ak_liste $_ak_a"
	done
	# shellcheck disable=SC2086
	set -- $_ak_liste
	_ak_stand="$(rootpath "$CHIMERA_STATE")/python-stand.txt"
	_ak_neu="$_ak_stand.neu"
	_ak_gesichert=0
	if pydep_stand_sichern "$PY" "$_ak_stand"; then
		_ak_gesichert=1
	else
		warn "Kein vorheriger Stand sicherbar (leere Umgebung?) -- ohne Rueckfall."
	fi
	pydep_ensure "$PY" "$@" || \
		warn "Auffrischen meldete einen Fehler -- entscheidend ist der Nachweis."
	if ! pydep_stand_sichern "$PY" "$_ak_neu"; then
		warn "Neuer Stand nicht feststellbar -- Sicherung bleibt erhalten."
		return 0
	fi
	if [ "$_ak_gesichert" = 1 ] && cmp -s "$_ak_stand" "$_ak_neu"; then
		info "Fassungen unveraendert (Stand: $_ak_stand)"
		rm -f "$_ak_neu"
		return 0
	fi
	info "Fassungen erneuert:"
	diff "$_ak_stand" "$_ak_neu" 2>/dev/null | sed -n 's/^> /    + /p; s/^< /    - /p'
	info "Neue Fassungen wirken mit dem naechsten Start des Dienstes."
	# Nachweis nur bei echter Aenderung: einer ohne Anlass kostet einen
	# Python-Start (am Pi gemessen: 1,7 s warm).
	#
	# WICHTIG: Der gesicherte Stand wird erst UEBERSCHRIEBEN, wenn der neue
	# nachgewiesen ist. Andersherum rollte der Rueckfall auf den kaputten
	# Stand zurueck -- der Test tests/test-python-env.sh hat genau das
	# gefunden (Umgebung blieb unbrauchbar, obwohl der Rueckfall lief).
	if [ "$_ak_nachweis" != 1 ] || pruef_ok; then
		mv "$_ak_neu" "$_ak_stand"
		return 0
	fi
	rm -f "$_ak_neu"
	warn "Nach dem Auffrischen ist die Umgebung nicht mehr nachweisbar."
	if [ "$_ak_gesichert" != 1 ]; then
		err "Es gibt keine Sicherung, auf die zurueckgegangen werden koennte."
		return 2
	fi
	if ! pydep_stand_zurueck "$PY" "$_ak_stand"; then
		err "Rueckfall gescheitert -- siehe $_ak_stand."
		return 2
	fi
	if pruef_ok; then
		warn "Alter Stand zurueckgespielt: $_ak_stand"
		return 0
	fi
	err "Rueckfall installiert, Umgebung bleibt aber unbrauchbar."
	return 2
}

if pruef_ok; then
	# Auch auf einem fertigen Geraet das Werkzeug bereitstellen: Der naechste
	# Abruf (neue Anforderung, neuere Fassung) soll uv benutzen. Ohne diesen
	# Aufruf entstuende uv nie -- am Pi gemessen (5.11.): Lauf gruen, kein uv.
	uv_bereitstellen || true

	# --- Fassungen aktuell halten -----------------------------------------
	#
	# Bisher endete Modul 50 hier: "laeuft, also nichts zu tun". Damit blieb
	# eine Fassung, die beim letzten Neubau geholt wurde, fuer immer stehen --
	# auch wenn inzwischen eine Sicherheitsluecke geschlossen wurde.
	log ""
	log "Fassungen"
	if is_dry_run; then
		info "[wuerde auffrischen] $(pydep_liste "$REQUIREMENTS" | tr '\n' ' ')"
	else
		# shellcheck disable=SC2046
		auffrischen $(pydep_liste "$REQUIREMENTS") $ANZEIGE_PIP || {
			err "Fassungen liessen sich nicht in einen brauchbaren Stand bringen."
			log_close 2; exit 2
		}
	fi
	log ""
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

	# uv bereitstellen (eigenes Werkzeug-venv, nur wenn es fehlt). Bewusst
	# HIER und nicht erst im Abruf: Sonst entstuende es nie auf einem Geraet,
	# dessen Abhaengigkeiten schon erfuellt sind -- und genau dort soll der
	# naechste Abruf uv benutzen (gemessen am Pi 5.11.: Lauf gruen, kein uv).
	# Scheitert es, laeuft alles ueber pip; das ist kein Befund.
	uv_bereitstellen || true

	# shellcheck disable=SC2046
	auffrischen --ohne-nachweis $(pydep_liste "$REQUIREMENTS") || {
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
	info "Nachweis: $PY $NACHWEIS_PY (Abhaengigkeiten, Anzeigemodul, --pruefen --offline)"
	log_close 0; exit 0
fi

if is_dry_run; then
	info "[wuerde pruefen] $PY $NACHWEIS_PY"
	log_close 0; exit 0
fi

err "Nachweis im venv gescheitert:"
nachweis 2>&1 | grep -v '^ok ' | tail -8 >&2 || true
log_close 2; exit 2
