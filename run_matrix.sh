#!/bin/bash
# Collect the full affinity x repetition matrix for parts 2 and 3.
#
# Three affinity configurations, five independent process launches each.  The
# five trials inside a single process share one set of warm caches and one
# scheduling placement, so they do not show run-to-run variance; separate
# launches do.
set -u
cd "$(dirname "$0")"

# Always rebuild.  A stale binary silently produces data that looks fine and
# is not what the source says it is, which is the worst possible failure mode
# for a benchmark.
make -B || exit 1

mkdir -p results/raw results/csv
rm -f pipe_latency_*.csv pipe_throughput_*.csv
TS=$(date +%Y%m%d-%H%M%S)

run_cfg() {          # name, then any cpu args
  local name=$1; shift
  for run in 1 2 3 4 5; do
    local label="${name}-r${run}"
    ./latency-test    "$label" "$@" > "results/raw/latency-${label}-${TS}.txt"
    ./throughput-test "$label" "$@" > "results/raw/throughput-${label}-${TS}.txt"
    printf '  %s\n' "$label"
  done
}

echo "unpinned:"; run_cfg unpinned
echo "same core (parent 0, child 0):"; run_cfg same 0 0
echo "cross core (parent 0, child 1):"; run_cfg cross 0 1

mv -f pipe_latency_*.csv pipe_throughput_*.csv results/csv/ 2>/dev/null
echo "CSV files: $(ls results/csv | wc -l)"
