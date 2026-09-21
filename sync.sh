#!/bin/bash
# Push sources to the guest.  Build products are excluded deliberately: an
# earlier run overwrote the guest's fresh binaries with stale host copies and
# silently collected a full matrix with the wrong code.
set -eu
REPO="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete-excluded \
  --exclude '.git' --exclude 'results' --exclude 'report' \
  --exclude 'timer-test' --exclude 'latency-test' --exclude 'throughput-test' \
  --exclude 'capacity-test' --exclude 'resize-test' --exclude '*.csv' \
  -e 'ssh -p 2222' "$REPO/" shawliu@localhost:~/advos-miniproj-2/
