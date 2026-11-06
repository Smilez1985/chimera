#!/bin/sh
# Messung A (Crate agent-client-protocol 5.0.0) gegen B (nur serde_json).
# Gemessen wird, was die Entscheidung braucht: Groesse des Binarys, Speicher,
# Laufzeit -- und die Startzeit bis zur ersten Antwort.
set -eu

A=/tmp/acp_a
B=/tmp/acp_b
W="${W:-/tmp/acp-mess}"
N="${N:-20000}"

# 20.000 initialize-Anfragen, jede mit eigener id.
awk -v n="$N" 'BEGIN { for (i = 1; i <= n; i++)
  printf "{\"jsonrpc\":\"2.0\",\"id\":%d,\"method\":\"initialize\",\"params\":{\"protocolVersion\":1}}\n", i }' > "$W/anfragen.ndjson"

jetzt() { date +%s%N; }

echo "=== Groesse (gestrippt) ==="
for p in "$A" "$B"; do
	printf '%-24s %s Bytes\n' "$(basename "$p")" "$(wc -c <"$p")"
done

echo
echo "=== Laufzeit: $N Anfragen durch den Zeilenrahmen ==="
for p in "$A" "$B"; do
	t0="$(jetzt)"
	"$p" <"$W/anfragen.ndjson" >"$W/antworten.txt"
	t1="$(jetzt)"
	ms=$(( (t1 - t0) / 1000000 ))
	anz="$(wc -l <"$W/antworten.txt")"
	printf '%-24s %6s ms  (%s Antworten)\n' "$(basename "$p")" "$ms" "$anz"
done

echo
echo "=== Speicher (Ruhezustand, wartet auf Eingabe) ==="
for p in "$A" "$B"; do
	mkfifo /tmp/mess-fifo.$$ 2>/dev/null || true
	( exec 3>/tmp/mess-fifo.$$; sleep 3 ) &
	"$p" </tmp/mess-fifo.$$ >/dev/null &
	pid=$!
	sleep 1.5
	rss="$(awk '/VmRSS/ { print $2 }' /proc/"$pid"/status 2>/dev/null || echo "?")"
	threads="$(awk '/Threads/ { print $2 }' /proc/"$pid"/status 2>/dev/null || echo "?")"
	printf '%-24s %6s kB RSS, %s Faden/Faeden\n' "$(basename "$p")" "$rss" "$threads"
	kill "$pid" 2>/dev/null || true
	wait "$pid" 2>/dev/null || true
	rm -f /tmp/mess-fifo.$$
done

echo
echo "=== Startzeit bis zur ersten Antwort ==="
for p in "$A" "$B"; do
	_summe=0
	_laeufe=5
	_i=0
	while [ "$_i" -lt "$_laeufe" ]; do
		t0="$(jetzt)"
		printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":1}}' | "$p" >/dev/null
		t1="$(jetzt)"
		_summe=$(( _summe + (t1 - t0) / 1000000 ))
		_i=$(( _i + 1 ))
	done
	printf '%-24s %6s ms Mittel aus %s Laeufen\n' "$(basename "$p")" "$(( _summe / _laeufe ))" "$_laeufe"
done
