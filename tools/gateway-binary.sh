#!/bin/sh
# Ablage des Gateway-Binaries im Repo -- Kurzform von tools/binary-ablegen.sh.
#
# Bleibt bestehen, weil Skripte, Doku und Tests diesen Namen nennen; die
# Arbeit macht binary-ablegen.sh (ein Weg fuer beide Programme, Regel 10g).
#
# Aufruf:
#   tools/gateway-binary.sh <binary> [--commit <kurz>] [--ohne-probe]

set -eu

_HERE="$(cd "$(dirname "$0")" && pwd)"
exec sh "$_HERE/binary-ablegen.sh" "$@" --art tor
