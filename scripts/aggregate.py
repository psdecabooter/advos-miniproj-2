#!/usr/bin/env python3
"""Reduce the raw benchmark CSVs to the small tables the report plots.

Standard library only, on purpose: the figures are built by pgfplots from the
committed .dat files, so a clean checkout needs nothing but a TeX install to
reproduce every figure in the paper.

Aggregation policy.  Each configuration was launched five times, and each
launch already reports the minimum over its internal repetitions.  Across
launches we again take the minimum, never the mean.  The minimum is the run
least contaminated by scheduling noise, descheduling and interrupt arrival,
all of which can only add time.  For throughput, which is a rate, the same
argument selects the maximum, and the arithmetic mean is avoided entirely
because averaging rates is not meaningful.
"""
import csv
import glob
import os
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "results", "csv")
OUT = os.path.join(ROOT, "report", "figures")
CONFIGS = ("unpinned", "same", "cross")


def config_of(path, stem):
    """results/csv/pipe_latency_same-r3.csv -> 'same'"""
    base = os.path.basename(path)[len(stem) + 1:-4]
    return base.rsplit("-r", 1)[0]


def collect(stem, key_col, val_col, reduce_fn):
    acc = collections.defaultdict(lambda: collections.defaultdict(list))
    for path in glob.glob(os.path.join(CSV, "%s_*.csv" % stem)):
        cfg = config_of(path, stem)
        if cfg not in CONFIGS:
            continue
        with open(path) as fh:
            for row in csv.DictReader(fh):
                acc[cfg][int(row[key_col])].append(float(row[val_col]))
    return {c: {k: reduce_fn(v) for k, v in d.items()} for c, d in acc.items()}


def write_dat(name, header, keys, columns):
    path = os.path.join(OUT, name)
    with open(path, "w") as fh:
        fh.write(" ".join(header) + "\n")
        for k in keys:
            fh.write(" ".join([str(k)] + ["%.4f" % c[k] for c in columns]) + "\n")
    print("wrote", os.path.relpath(path, ROOT), "(%d rows)" % len(keys))


def main():
    os.makedirs(OUT, exist_ok=True)

    # Figure 1: round-trip/2 latency, minimum across runs.
    lat = collect("pipe_latency", "payload_bytes", "min", min)
    sizes = sorted(lat["same"])
    write_dat("latency.dat", ["payload"] + list(CONFIGS), sizes,
              [lat[c] for c in CONFIGS])

    # Figure 2a: streaming throughput, maximum across runs.
    thr = collect("pipe_throughput", "chunk_bytes", "max_MiB_per_s", max)
    chunks = sorted(thr["same"])
    write_dat("throughput.dat", ["chunk"] + list(CONFIGS), chunks,
              [thr[c] for c in CONFIGS])

    # Figure 2b: the resize sweep, cross-core only.  Same-core has no knee to
    # move, which is itself the point, so plotting it would only add flat
    # lines.  One column per configured capacity.
    caps, by_cap = [], collections.defaultdict(dict)
    with open(os.path.join(CSV, "pipe_resize_cross.csv")) as fh:
        for row in csv.DictReader(fh):
            cap = int(row["actual_capacity"])
            by_cap[cap][int(row["chunk_bytes"])] = float(row["best_MiB_per_s"])
            if cap not in caps:
                caps.append(cap)
    caps.sort()
    rchunks = sorted(by_cap[caps[0]])
    write_dat("resize.dat", ["chunk"] + ["cap%d" % c for c in caps], rchunks,
              [by_cap[c] for c in caps])

    # Table 1: the time breakdown.  Emitted as a LaTeX fragment so the numbers
    # in the paper cannot drift from the numbers that were measured.
    rows = []
    with open(os.path.join(CSV, "pipe_profile.csv")) as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
    # same-core first: it is the baseline the cross-core row is read against
    order = {"same": 0, "cross": 1, "unpinned": 2}
    rows.sort(key=lambda r: (int(r["payload_bytes"]), order[r["config"]]))
    path = os.path.join(OUT, "profile_table.tex")
    # The whole tabular, not just the rows: \input of a partial tabular ends
    # the file right after a row terminator, and the \bottomrule that follows
    # is then rejected as a misplaced \noalign.
    with open(path, "w") as fh:
        fh.write("\\begin{tabular}{llrrrrr}\n\\toprule\n")
        fh.write("Payload & Place & $\\mu$s/RT & \\%usr & \\%sys & \\%blk"
                 " & cs/RT \\\\\n\\midrule\n")
        for r in rows:
            wall = float(r["wall_s"])
            fh.write("%s & %s & %.1f & %.0f & %.0f & %.0f & %.2f \\\\\n" % (
                "4\\,B" if r["payload_bytes"] == "4" else "512\\,KiB",
                r["config"],
                float(r["ns_per_roundtrip"]) / 1000.0,
                100 * float(r["user_s"]) / wall,
                100 * float(r["system_s"]) / wall,
                max(0.0, 100 * float(r["unaccounted_s"]) / wall),
                float(r["vol_ctxsw_per_rt"])))
        fh.write("\\bottomrule\n\\end{tabular}\n")
    print("wrote", os.path.relpath(path, ROOT))

    # A few derived numbers the prose quotes, so they are never hand-copied.
    print("\nderived:")
    print("  same-core 4B latency      %.0f ns" % lat["same"][4])
    print("  cross-core 4B latency     %.0f ns" % lat["cross"][4])
    print("  cross-core penalty        %.0f ns" % (lat["cross"][4] - lat["same"][4]))
    # Copy bandwidth from the slope of the latency line.  Two factors of two
    # are in play and they cancel: a round trip copies the payload twice, once
    # out of the writer on write() and once into the reader on read(), while
    # the reported figure is half a round trip.  So bytes-per-round-trip over
    # time-per-round-trip is (2*big) / (2*span) = big/span.
    big = max(sizes)
    span = lat["same"][big] - lat["same"][4]
    print("  same-core copy bandwidth  %.2f GiB/s (slope 4 B -> %d B)" %
          (big / (span * 1.073741824), big))
    print("  same-core peak throughput %.0f MiB/s" % max(thr["same"].values()))
    print("  cross-core peak           %.0f MiB/s" % max(thr["cross"].values()))
    print("  cross-core at 512 KiB     %.0f MiB/s" % thr["cross"][524288])


if __name__ == "__main__":
    main()
