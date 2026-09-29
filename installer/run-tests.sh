#!/bin/sh
# Alle hardwarefreien Installertests.
set -eu
cd "$(dirname "$0")"
for t in tests/test-*.sh; do
	printf '=== %s ===\n' "$t"
	sh "$t"
done
