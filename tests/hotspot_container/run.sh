#!/bin/bash
# Builds the Linux stand-in and runs check.sh in it. Needs Docker; the
# container is privileged because it creates network namespaces and loads
# nftables rules (into its own network namespace, not the host's).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
docker build -q -t ssp-hotspot-check "$HERE" >/dev/null
docker run --rm --privileged -v "$REPO":/repo:ro ssp-hotspot-check bash /repo/tests/hotspot_container/check.sh
