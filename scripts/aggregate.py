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
import math
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


def half_up(x):
    """Round .5 away from zero.

    Python rounds half to even, which made the headline table disagree with
    itself: 708.5 became 708 and 2041.5 became 2042, so the printed cross-core
    penalty did not equal the printed difference of the two printed values.
    """
    return int(math.floor(x + 0.5))


def write_dat(name, header, keys, columns):
    path = os.path.join(OUT, name)
    with open(path, "w") as fh:
        fh.write(" ".join(header) + "\n")
        for k in keys:
            fh.write(" ".join([str(k)] + ["%.4f" % c[k] for c in columns]) + "\n")
    print("wrote", os.path.relpath(path, ROOT), "(%d rows)" % len(keys))



ORDER = ["clock_gettime", "gettimeofday", "cntvct_el0"]


def emit_clock_table(path):
    """Table 1, generated from clock_precision.csv.

    The zero-delta fraction is reported beside the quantum and beside what the
    quantum predicts, because the raw fraction on its own is misleading: it
    measures how cheap a call is relative to one tick, not how coarse the clock
    is. A cheap call against a fine quantum (cntvct_el0) produces a high
    fraction for a completely different reason than a coarse quantum
    (gettimeofday) does, and only the latter is disqualifying.
    """
    d = {}
    with open(os.path.join(CSV, "clock_precision.csv")) as fh:
        for r in csv.DictReader(fh):
            d[(r["clock"], r["metric"])] = float(r["value"])

    order = ORDER
    with open(path, "w") as fh:
        fh.write("\\begin{tabular}{lrrrr}\n\\toprule\n")
        fh.write("Clock & Call & Quantum & Zero & Predicted \\\\\n")
        fh.write(" & (ns) & (ns) & deltas & $1-c/q$ \\\\\n\\midrule\n")
        for c in order:
            call = d[(c, "mean_call_ns")]
            q = d[(c, "smallest_nonzero_delta_ns")]
            z = d[(c, "zero_delta_fraction")]
            fh.write("\\texttt{%s} & %.1f & %.1f & %.1f\\,\\%% & %.1f\\,\\%% \\\\\n"
                     % (c.replace("_", "\\_"), call, q, 100 * z,
                        100 * (1 - call / q)))
        fh.write("\\bottomrule\n\\end{tabular}\n")
    return d


def emit_clock_dat(path, clk):
    """Figure 1 data.  Call cost and quantum for the three candidate clocks,
    which are the two quantities the choice of clock turns on."""
    short = {"clock_gettime": "cgt", "gettimeofday": "gtod",
             "cntvct_el0": "cntvct"}
    with open(path, "w") as fh:
        fh.write("clock call quantum\n")
        for c in ORDER:
            fh.write("%s %.2f %.2f\n"
                     % (short[c], clk[(c, "mean_call_ns")],
                        clk[(c, "smallest_nonzero_delta_ns")]))
    print("wrote", os.path.relpath(path, ROOT))


def emit_data_table(path, datfile, key_label, unit, fmt="%.0f"):
    """A plain table of the measured series, so a reader can recover any value
    instead of reading it off a log axis."""
    rows = [l.split() for l in open(os.path.join(OUT, datfile)).read().strip().split("\n")]
    header, body = rows[0], rows[1:]
    cols = header[1:]
    nice = {"same": "same core", "cross": "cross core", "unpinned": "unpinned"}
    with open(path, "w") as fh:
        fh.write("\\begin{tabular}{r%s}\n\\toprule\n" % ("r" * len(cols)))
        fh.write("%s & %s \\\\\n" % (key_label,
                 " & ".join(nice.get(c, c) for c in cols)))
        fh.write("(bytes) & \\multicolumn{%d}{c}{%s} \\\\\n\\midrule\n"
                 % (len(cols), unit))
        for r in body:
            fh.write("%s & %s \\\\\n" % (r[0],
                     " & ".join(fmt % float(v) for v in r[1:])))
        fh.write("\\bottomrule\n\\end{tabular}\n")


# The ten sizes the assignment names.  Both sweeps were run over supersets of
# this list; the paper's data table reports exactly these so a reader can check
# the required points without reading them off a log axis.
REQUIRED_SIZES = [4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 524288]


def emit_headline_table(path, lat, thr):
    """Both sweeps at the required sizes, transposed so the ten sizes run
    across the page.  The upright form needs more vertical space than a
    two-page paper has; this one spans the columns in four rows."""
    def label(n):
        for div, suf in ((1 << 20, "M"), (1 << 10, "K")):
            if n >= div:
                return "%d%s" % (n // div, suf)
        return "%d" % n

    def row(name, series, key):
        return "%s & %s \\\\\n" % (name, " & ".join(
            "%d" % half_up(series[key][n]) for n in REQUIRED_SIZES))

    with open(path, "w") as fh:
        fh.write("\\begin{tabular}{l%s}\n\\toprule\n"
                 % ("r" * len(REQUIRED_SIZES)))
        fh.write("Size (B) & %s \\\\\n\\midrule\n"
                 % " & ".join(label(n) for n in REQUIRED_SIZES))
        fh.write("Latency, same core (ns) & %s"
                 % row("", lat, "same").lstrip(" &"))
        fh.write("Latency, cross core (ns) & %s"
                 % row("", lat, "cross").lstrip(" &"))
        fh.write("Throughput, same core (MiB/s) & %s"
                 % row("", thr, "same").lstrip(" &"))
        fh.write("Throughput, cross core (MiB/s) & %s"
                 % row("", thr, "cross").lstrip(" &"))
        fh.write("\\bottomrule\n\\end{tabular}\n")


def emit_numbers(path, lat, thr, clk, sizes):
    """Every figure the prose quotes, as LaTeX macros.

    Table 1 was hand-typed once and then silently disagreed with the committed
    CSV after the benchmark was re-run. Emitting the prose numbers too means a
    re-run updates the sentences, not just the tables.
    """
    big = max(sizes)
    span = lat["same"][big] - lat["same"][4]
    prof = {}
    with open(os.path.join(CSV, "pipe_profile.csv")) as fh:
        for r in csv.DictReader(fh):
            prof[(r["config"], int(r["payload_bytes"]))] = r
    skew = max(abs(v) for (c, m), v in clk.items()
               if m.startswith("cpu") and m.endswith("skew_ns"))
    blk = prof[("cross", 4)]
    blkpct = 100 * float(blk["unaccounted_s"]) / float(blk["wall_s"])

    # The sleep(5) cross-check.  What it establishes is that the three clocks
    # agree with each other; the shared excess over five seconds is sleep()
    # overshooting its deadline, which is a property of the scheduler and not
    # of any clock, so it is reported separately rather than as clock error.
    secs = [clk[(c, "mean_seconds")] for c in ORDER]
    spread_ppm = 1e6 * (max(secs) - min(secs)) / min(secs)
    overshoot_ppm = sum(clk[(c, "error_ppm")] for c in ORDER) / len(ORDER)

    vals = {
        "LatSameSmall":  "%d" % half_up(lat["same"][4]),
        "LatCrossSmall": "%d" % half_up(lat["cross"][4]),
        "LatPenalty":    "%d" % (half_up(lat["cross"][4])
                                 - half_up(lat["same"][4])),
        "LatSameBig":    "%d" % half_up(lat["same"][big]),
        "LatSpan":       "%.0f" % span,
        "CopyBW":        "%.1f" % (big / (span * 1.073741824)),
        "CopySlope":     "%.2f" % (big / span),
        "ThrSamePeak":   "%.0f" % max(thr["same"].values()),
        "ThrCrossPeak":  "%.0f" % max(thr["cross"].values()),
        "ThrCrossBig":   "%.0f" % thr["cross"][524288],
        "GtodZero":      "%.1f" % (100 * clk[("gettimeofday", "zero_delta_fraction")]),
        "CgtCall":       "%.1f" % clk[("clock_gettime", "mean_call_ns")],
        "CcCall":        "%.1f" % clk[("cntvct_el0", "mean_call_ns")],
        "GtodCall":      "%.1f" % clk[("gettimeofday", "mean_call_ns")],
        "CgtQuantum":    "%.0f" % clk[("clock_gettime", "smallest_nonzero_delta_ns")],
        "CcPeriod":      "%.2f" % clk[("cntvct_el0", "smallest_nonzero_delta_ns")],
        "SkewMax":       "%d" % int(math.ceil(skew)),
        "CtxSmall":      "%.2f" % float(prof[("same", 4)]["vol_ctxsw_per_rt"]),
        "CtxBig":        "%.2f" % float(prof[("same", 524288)]["vol_ctxsw_per_rt"]),
        "CrossBlocked":  "%.0f" % blkpct,
        "SleepMean":     "%.4f" % (sum(secs) / len(secs)),
        "SleepSpread":   "%.1f" % spread_ppm,
        "SleepOver":     "%.0f" % overshoot_ppm,
    }
    with open(path, "w") as fh:
        fh.write("%% Generated by scripts/aggregate.py -- do not edit.\n")
        for k, v in sorted(vals.items()):
            fh.write("\\newcommand{\\n%s}{%s}\n" % (k, v))
    return vals


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

    emit_data_table(os.path.join(OUT, "latency_table.tex"), "latency.dat",
                    "Payload", "one-way latency (ns)")
    emit_data_table(os.path.join(OUT, "throughput_table.tex"), "throughput.dat",
                    "Chunk", "throughput (MiB/s)")
    emit_headline_table(os.path.join(OUT, "headline_table.tex"), lat, thr)
    clk = emit_clock_table(os.path.join(OUT, "clock_table.tex"))
    emit_clock_dat(os.path.join(OUT, "clock.dat"), clk)
    print("wrote latency_table.tex, throughput_table.tex, clock_table.tex,"
          " headline_table.tex")

    # Table 3: the time breakdown.  Emitted as a LaTeX fragment so the numbers
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

    emit_numbers(os.path.join(OUT, "numbers.tex"), lat, thr, clk, sizes)
    print("wrote numbers.tex")

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
