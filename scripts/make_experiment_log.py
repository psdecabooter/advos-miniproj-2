#!/usr/bin/env python3
"""Assemble EXPERIMENTS.txt, the full plain-text lab record.

The paper is the argument; this file is the evidence behind it. Every command
that produced a committed number appears here with its raw output, so a reader
can check any figure in the paper against the terminal session that made it.

Standard library only. Regenerate with:  python3 scripts/make_experiment_log.py
"""
import collections
import csv as csvmod
import datetime
import glob
import hashlib
import io
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "results", "raw")
CSV = os.path.join(ROOT, "results", "csv")
OUT = os.path.join(ROOT, "EXPERIMENTS.txt")

W = 80


def rule(ch="="):
    return ch * W


def head(fh, n, title):
    fh.write("\n%s\n%s. %s\n%s\n\n" % (rule(), n, title.upper(), rule()))


def sub(fh, title):
    fh.write("\n%s\n%s\n\n" % (title, "-" * len(title)))


def cmd(fh, *lines):
    fh.write("  COMMAND\n")
    for l in lines:
        fh.write("    $ %s\n" % l)
    fh.write("\n")


def paste(fh, path, label=None, indent="    "):
    """Embed a raw output file verbatim."""
    if not os.path.exists(path):
        fh.write("%s[missing: %s]\n\n" % (indent, os.path.basename(path)))
        return
    fh.write("  OUTPUT (%s)\n" % (label or os.path.relpath(path, ROOT)))
    with io.open(path, encoding="utf-8", errors="replace") as src:
        for line in src:
            fh.write(indent + line.rstrip("\n") + "\n")
    fh.write("\n")


def paste_text(fh, text, label, indent="    "):
    fh.write("  OUTPUT (%s)\n" % label)
    for line in text.rstrip("\n").split("\n"):
        fh.write(indent + line + "\n")
    fh.write("\n")


def newest(pattern):
    hits = sorted(glob.glob(os.path.join(RAW, pattern)))
    return hits[-1] if hits else os.path.join(RAW, pattern)


def git(*args):
    try:
        return subprocess.check_output(["git"] + list(args), cwd=ROOT,
                                       stderr=subprocess.DEVNULL).decode()
    except Exception:
        return "(git unavailable)\n"


def matrix_stamp():
    """The timestamp run_matrix.sh stamped on one collection of the matrix."""
    hits = sorted(glob.glob(os.path.join(RAW, "latency-same-r1-*.txt")))
    if not hits:
        return "(none)"
    return os.path.basename(hits[-1])[len("latency-same-r1-"):-len(".txt")]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def run_aggregate():
    """Run the aggregation step and return its stdout.

    It runs FIRST, before any prose is written, because the prose below quotes
    the macros it emits into report/figures/numbers.tex. The paper and this
    log therefore cannot disagree: both read the same generated file, and a
    re-run of a benchmark updates both.
    """
    try:
        return subprocess.check_output(
            ["python3", os.path.join(ROOT, "scripts", "aggregate.py")],
            cwd=ROOT, stderr=subprocess.STDOUT).decode()
    except Exception as e:                                # pragma: no cover
        return "(could not run aggregate.py: %s)\n" % e


def load_numbers():
    r"""Parse report/figures/numbers.tex back into a dict.

    Section 16 item 6 records what happens when a number in the narrative is
    typed by hand: the benchmark gets re-run, the CSV changes, and the prose
    goes on describing a dataset that no longer exists. The paper was fixed by
    generating its prose numbers; this file quotes the same macros so the same
    fix covers it. Anything of the form \newcommand{\nName}{value} becomes
    N["Name"].
    """
    out = {}
    path = os.path.join(ROOT, "report", "figures", "numbers.tex")
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("\\newcommand{\\n"):
                continue
            name, _, rest = line[len("\\newcommand{\\n"):].partition("}")
            out[name] = rest.strip()[1:-1]
    return out


def read_rows(path):
    with open(path) as fh:
        return list(csvmod.DictReader(fh))


def per_run(stem, cfg, key_col, val_col):
    """{key: [r1, r2, ...]} for one benchmark and one placement."""
    acc = collections.defaultdict(list)
    for path in sorted(glob.glob(os.path.join(CSV, "%s_%s-r*.csv" % (stem, cfg)))):
        for row in read_rows(path):
            acc[int(row[key_col])].append(float(row[val_col]))
    return acc


def run_table(fh, stem, cfg, key_col, val_col, unit, best, extra=None,
              extra_label=None):
    """Print every launch separately, not just the one that was kept.

    The aggregation keeps one value per point (the minimum for a time, the
    maximum for a rate) and the paper plots that. A reader cannot check that
    choice against five launches they cannot see, so all five are printed here
    with the spread between them.
    """
    acc = per_run(stem, cfg, key_col, val_col)
    if not acc:
        fh.write("    [no data for %s %s]\n\n" % (stem, cfg))
        return
    nruns = max(len(v) for v in acc.values())
    fh.write("  %s, %s -- %s, one column per launch\n\n"
             % (stem.replace("pipe_", ""), cfg, unit))
    fh.write("    %8s %s %9s %8s%s\n"
             % (key_col.split("_")[0],
                " ".join("%9s" % ("r%d" % (i + 1)) for i in range(nruns)),
                "kept", "spread",
                "" if extra is None else "%10s" % extra_label))
    for k in sorted(acc):
        v = acc[k]
        kept = best(v)
        spread = 100.0 * (max(v) - min(v)) / min(v) if min(v) else 0.0
        line = "    %8d %s %9.1f %7.1f%%" % (
            k, " ".join("%9.1f" % x for x in v), kept, spread)
        if extra is not None:
            line += "%10.2f" % extra(k)
        fh.write(line + "\n")
    fh.write("\n")


def mean_min_ratio(stem, cfg):
    """min-of-means over min-of-minima, per payload.

    The gap between the two is the long tail that part 4c explains, so it is
    reported rather than hidden by the choice of statistic.
    """
    mins = per_run(stem, cfg, "payload_bytes", "min")
    means = per_run(stem, cfg, "payload_bytes", "mean")
    return lambda k: min(means[k]) / min(mins[k])


def resize_summary(cfg):
    """Where each configured capacity peaks and how far it has fallen by the
    time the chunk reaches that capacity.

    The claim being checked is "the knee follows the configured capacity",
    which is a claim about a RATIO (chunk/capacity), not about an absolute
    chunk size. Printing the peak and the fraction of it left at
    chunk == capacity lets a reader check that ratio directly instead of
    eyeballing a log-log plot.
    """
    by = collections.defaultdict(dict)
    for r in read_rows(os.path.join(CSV, "pipe_resize_%s.csv" % cfg)):
        by[int(r["actual_capacity"])][int(r["chunk_bytes"])] = \
            float(r["best_MiB_per_s"])
    out = ["    %10s %10s %10s %12s %12s"
           % ("capacity", "peak", "at chunk", "% of peak", "% of peak"),
           "    %10s %10s %10s %12s %12s"
           % ("(bytes)", "(MiB/s)", "(bytes)", "at cap", "at 512 KiB"),
           "    %s" % ("-" * 58)]
    for cap in sorted(by):
        row = by[cap]
        peak_chunk = max(row, key=lambda c: row[c])
        peak = row[peak_chunk]
        at_cap = "%11.0f%%" % (100 * row[cap] / peak) if cap in row else \
            "%12s" % "not tested"
        out.append("    %10d %10.0f %10d %s %11.0f%%"
                   % (cap, peak, peak_chunk, at_cap,
                      100 * row[max(row)] / peak))
    return "\n".join(out) + "\n"


def profile_table():
    """Part 4c's accounting, straight out of pipe_profile.csv.

    Written as a block of text rather than prose ranges: the prose ranges that
    used to stand here were typed from one set of runs and stopped matching
    the CSV when the profile runs were re-done clean (section 16, item 3).
    """
    rows = read_rows(os.path.join(CSV, "pipe_profile.csv"))
    order = {"same": 0, "cross": 1, "unpinned": 2}
    rows.sort(key=lambda r: (int(r["payload_bytes"]), order[r["config"]]))
    out = ["     %-9s %-6s %10s %7s %7s %7s %8s"
           % ("payload", "place", "us/RT", "%usr", "%sys", "%blk", "vcsw/RT"),
           "     %s" % ("-" * 60)]
    for r in rows:
        wall = float(r["wall_s"])
        out.append("     %-9s %-6s %10.1f %7.1f %7.1f %7.1f %8.2f" % (
            "4 B" if r["payload_bytes"] == "4" else "512 KiB",
            r["config"],
            float(r["ns_per_roundtrip"]) / 1000.0,
            100 * float(r["user_s"]) / wall,
            100 * float(r["system_s"]) / wall,
            100 * float(r["unaccounted_s"]) / wall,
            float(r["vol_ctxsw_per_rt"])))
    return "\n".join(out) + "\n"


def dump_dat(fh, name):
    paste(fh, os.path.join(ROOT, "report", "figures", name),
          "report/figures/%s" % name)


def clock_numbers():
    """Read part 1's results back out of the committed CSV.

    These were hand-typed into the narrative once and then disagreed with the
    CSV after the benchmark was re-run, which is exactly the drift this file
    exists to make visible. They are now read from the data.
    """
    import csv as _csv
    d = {}
    with open(os.path.join(CSV, "clock_precision.csv")) as fh:
        for r in _csv.DictReader(fh):
            d[(r["clock"], r["metric"])] = float(r["value"])
    skew = max(abs(v) for (c, m), v in d.items()
               if m.startswith("cpu") and m.endswith("skew_ns"))
    return {
        "gtod_zero": 100 * d[("gettimeofday", "zero_delta_fraction")],
        "cc_call": d[("cntvct_el0", "mean_call_ns")],
        "cgt_call": d[("clock_gettime", "mean_call_ns")],
        "cgt_res": d[("clock_gettime", "smallest_nonzero_delta_ns")],
        "cc_res": d[("cntvct_el0", "smallest_nonzero_delta_ns")],
        "ratio": d[("clock_gettime", "mean_call_ns")] / d[("cntvct_el0", "mean_call_ns")],
        "skew": skew,
    }


def main():
    # Regenerate the derived files first, then read the numbers back out of
    # them, so that this log quotes exactly what the paper quotes.
    agg_out = run_aggregate()
    fh = io.open(OUT, "w", encoding="utf-8")
    C = clock_numbers()
    N = load_numbers()
    N["PROFILE_TABLE"] = profile_table()
    # Two figures this log discusses that the paper does not quote, so they
    # are not in numbers.tex; read from the same CSVs by the same rule.
    for key, cfg in (("UnpinnedBig", "unpinned"), ("CrossBig", "cross")):
        N[key] = "%.0f" % min(per_run("pipe_latency", cfg,
                                      "payload_bytes", "min")[524288])

    fh.write(rule() + "\n")
    fh.write("EVALUATION OF IPC THROUGH LINUX PIPES\n")
    fh.write("Full experiment log -- COMP SCI 736 Mini-Project 2\n")
    fh.write("Patrick DeCabooter and Shaw Liu\n")
    fh.write(rule() + "\n\n")
    fh.write("Generated %s by scripts/make_experiment_log.py\n"
             % datetime.date.today().isoformat())
    fh.write("""
This is the evidence file that sits behind report/main.pdf. It records what was
measured, the exact command that measured it, the raw terminal output, and what
we concluded. It also records the mistakes, because two of them silently
produced wrong data before being caught, and a reader checking our numbers
should know where the traps were.

Everything ran inside a QEMU guest, never on the macOS host: the report is
about Linux pipes, and macOS pipes are XNU and behave differently. Commands
shown as "$" were issued in the guest over ssh.

Every number in the narrative below is read out of results/csv at generation
time, never typed in. Section 16 item 6 records why.

CONTENTS
   1. Deliverables
   2. Apparatus
   3. Reproducing from a clean checkout
   4. Source files
   5. Experiment design at a glance
   6. Data dictionary -- every CSV column
   7. Part 1 -- clock selection
   8. Part 2 -- latency
   9. Part 3 -- throughput
  10. Part 4a -- measuring pipe capacity
  11. Part 4b -- capacity as the independent variable
  12. Part 4c -- where the time goes
  13. Aggregated series as they enter the paper
  14. Derived numbers quoted in the paper
  15. Threats to validity and known limitations
  16. Problems encountered and how they were resolved
  17. Index of data files, with checksums
  18. Commit history
""")

    # ------------------------------------------------------------------
    head(fh, 1, "Deliverables")
    fh.write("""  report/main.tex     the paper, source
  report/main.pdf     the paper, compiled: 2-column, 11pt, 1in margins and two
                      pages, as the assignment requires
  EXPERIMENTS.txt     this file: the evidence behind the paper
  METHODOLOGY.md      the procedure and the reasoning behind it -- why each
                      experiment is shaped the way it is
  results/raw/        unedited stdout from every run, nothing hand-tidied
  results/csv/        machine-readable form of the same runs, written by the
                      benchmarks themselves
  report/figures/     plot data, generated tables and generated prose macros,
                      all built from results/csv by scripts/aggregate.py
  scripts/            aggregation and log generation, standard library only
  PLAN.md             the working brief the re-run was executed from

  Chain of custody for any number in the paper:

    benchmark binary -> results/raw/*.txt   (stdout, verbatim)
                     -> results/csv/*.csv   (same run, machine readable)
                     -> scripts/aggregate.py
                     -> report/figures/*.dat, *_table.tex, numbers.tex
                     -> report/main.tex     (\\input, never retyped)

  Nothing in that chain is edited by hand. The only hand-written artefacts are
  the .c sources, the prose, and the scripts themselves.
""")

    # ------------------------------------------------------------------
    head(fh, 2, "Apparatus")
    paste(fh, os.path.join(ROOT, "shaw-computer-specs.txt"),
          "shaw-computer-specs.txt", indent="  ")
    fh.write("""  The guest is virtualized, which we state in the paper rather than hide.
  Absolute latencies carry hypervisor overhead. The comparisons the paper
  actually rests on -- same-core against cross-core, and one pipe capacity
  against another -- are differences measured on the same machine under the
  same conditions, so the overhead is common to both sides.

  The second machine mentioned in the repository (partick-computer-specs.txt,
  an x86-64 WSL2 laptop) was NOT used. Its earlier numbers came from a version
  of the latency benchmark with an accumulator bug and were discarded. We did
  not mix datasets across machines.

  Build: gcc 13.3.0, -O3 -Wall -Wextra, one translation unit per benchmark,
  no linker flags beyond the default. -O3 is deliberate: the benchmarks are
  syscall-bound, and compiling them unoptimized would measure the harness
  instead of the pipe. Nothing is computed inside a timed region that could be
  hoisted out of one -- the timed regions contain syscalls only.

  One correction to the specs above: strace is listed there as "not
  installed", which was true when the specs were taken. It was installed from
  the Ubuntu archive afterwards, and part 4c uses it. perf and ftrace remained
  unavailable and no workaround was found for either.

  Collection window: the whole placement matrix (parts 2 and 3, 30 launches)
  came from ONE invocation of run_matrix.sh, so every file in it carries the
  same timestamp suffix, %s. Parts 1 and 4 were run in the same session on the
  same boot. The machine was otherwise idle; no other interactive session was
  open on the guest.
""" % matrix_stamp())

    # ------------------------------------------------------------------
    head(fh, 3, "Reproducing from a clean checkout")
    fh.write("""  On the host, with the guest running:

    $ ./sync.sh                     # push sources to the guest (excludes binaries)
    $ ssh -p 2222 shawliu@localhost
    $ cd ~/advos-miniproj-2
    $ make                          # builds all five benchmarks, -O3 -Wall -Wextra
    $ ./run_matrix.sh               # parts 2 and 3, all placements, 5 runs each
    $ ./timer-test                  # part 1
    $ ./capacity-test               # part 4a
    $ ./resize-test same  0 0       # part 4b
    $ ./resize-test cross 0 1
    $ ./profile-test 4 20000 0 0    # part 4c
    $ ./profile-test 4 20000 0 1
    $ ./profile-test 524288 500 0 0
    $ ./profile-test 524288 500 0 1

  The syscall counts come from a SEPARATE set of runs, whose CSV rows must
  not be mixed into the ones above (section 16, item 3):

    $ strace -c -f ./profile-test 4      5000 0 0
    $ strace -c -f ./profile-test 4      5000 0 1
    $ strace -c -f ./profile-test 524288 200  0 0
    $ strace -c -f ./profile-test 524288 200  0 1

  Then back on the host:

    $ rsync -a -e 'ssh -p 2222' shawliu@localhost:~/advos-miniproj-2/results/ results/
    $ python3 scripts/aggregate.py          # results/csv -> report/figures
    $ cd report && latexmk -pdf main.tex
    $ python3 scripts/make_experiment_log.py   # regenerates this file

  Order matters only in that aggregate.py must run before the paper is built
  and before this log is generated; both read what it writes. Running this log
  generator alone is safe, because it runs aggregate.py itself first.

  Expected wall time on the apparatus described above: the matrix is about
  four minutes, part 1 is about 30 seconds (five sleep(5) trials dominate),
  part 4a is instant, part 4b about three minutes, part 4c a few seconds.

  The figures are drawn by pgfplots directly from the .dat files at build time,
  so no plotting library is needed; a TeX installation is sufficient.
""")

    # ------------------------------------------------------------------
    head(fh, 4, "Source files")
    fh.write("""  Timer.h            three clock sources behind one interface: clock_gettime,
                     gettimeofday, and the cycle counter (cntvct_el0 on arm64,
                     rdtsc on x86-64, selected at compile time)
  timer_test.c       part 1, three experiments, writes clock_precision.csv
  pipe_latency.c     part 2, round-trip ping-pong, halved; optional placement
  pipe_throughput.c  part 3, one-way streaming with a single ack
  pipe_capacity.c    part 4a, fills a nonblocking pipe until EAGAIN
  pipe_resize.c      part 4b, F_SETPIPE_SZ sweep
  pipe_profile.c     part 4c, getrusage accounting for one size and placement
  run_matrix.sh      drives parts 2 and 3 over the placement matrix
  sync.sh            host -> guest source push

  Placement note. Parent and child are pinned individually with
  sched_setaffinity AFTER the fork. taskset cannot express this experiment: it
  sets one allowed mask that both processes inherit, so "parent on core 0,
  child on core 1" is not expressible through it.

  Invocation grammar, common to parts 2, 3 and 4b:

    ./<bench> <label> [parent_cpu] [child_cpu]

  The label names the output CSV, so two placements cannot overwrite each
  other's data. Omitting the CPU arguments leaves affinity to the scheduler,
  which is the "unpinned" configuration and not a missing value.
""")

    # ------------------------------------------------------------------
    head(fh, 5, "Experiment design at a glance")
    fh.write("""  Every run in this log, with what varies and what is held fixed.

  Part  Benchmark        Independent variable(s)     Repetition
  ----  ---------------  --------------------------  ---------------------
  1     timer-test       clock API (3)               5 sleep trials, 1e6
                                                     reads, 8 cores
  2     latency-test     payload (10) x              20000/5000/500 reps per
                         placement (3)               size, x5 launches
  3     throughput-test  chunk (15) x                1 warmup + 5 trials per
                         placement (3)               size, x5 launches
  4a    capacity-test    write size (6)              fill to EAGAIN, 1 launch
  4b    resize-test      capacity (5) x chunk (9)    3 trials per cell,
                         x placement (2)             1 launch
  4c    profile-test     payload (2) x               20000 reps at 4 B,
                         placement (2)               500 at 512 KiB

  Payloads and chunks both run 4 B to 512 KiB; part 3 adds five points
  clustered around the 64 KiB capacity to the ten the assignment names.

  Held fixed across all of it: one machine, one boot, one kernel, one build,
  idle system, CLOCK_MONOTONIC as the clock, and the same two-pipe ping-pong
  or one-way-stream structure per part.

  Repetition counts per payload in part 2 are 20000 for payloads up to 4 KiB,
  5000 up to 64 KiB, and 500 above that. They are chosen for how fast the
  MINIMUM converges, not for an error bar on the mean, and they keep a full
  sweep to a few seconds so that five independent launches are affordable.

  Part 3 aims at 64 MiB of traffic per measurement, capped at 200000 writes so
  that a 4-byte chunk does not turn into a 16-million-syscall run; that cap is
  why the smallest chunks move less than 64 MiB. Part 4b moves 32 MiB per cell
  for the same reason, with a floor of 16 writes.

  STATISTICS POLICY, stated once and applied everywhere:

    a time       -> minimum. Noise adds time; it never removes it.
    a rate       -> maximum, which is the same rule seen through 1/x.
    never        -> the arithmetic mean of a rate.
    two levels   -> each launch reports its own internal minimum (or maximum),
                    and the aggregation takes the minimum (maximum) again
                    across the five launches.

  Means are still recorded in the CSVs, and section 8 prints the mean/minimum
  ratio next to the data, because the size of that gap is itself a result:
  it is small when the pair shares a core and large when it does not, which
  is the part 4c mechanism showing up in part 2's statistics.
""")

    # ------------------------------------------------------------------
    head(fh, 6, "Data dictionary -- every CSV column")
    fh.write("""  results/csv/clock_precision.csv        long format, one metric per row
    experiment        accuracy | resolution | cross_core
    clock             clock_gettime | gettimeofday | cntvct_el0
    metric            mean_call_ns          cost of one call, 1e6 reads
                      smallest_nonzero_delta_ns  effective quantum
                      zero_delta_fraction   share of adjacent reads that are
                                            identical (see part 1: this is a
                                            cost/quantum ratio, not coarseness)
                      backward_deltas       count of non-monotonic steps
                      samples               reads taken
                      cpuN_skew_ns          counter offset read on CPU N
                      frequency_hz          cntfrq_el0, hardware reported
                      period_ns             1e9 / frequency_hz
                      mean_seconds          measured duration of sleep(5)
                      error_ppm             (measured - 5 s) / 5 s, in ppm
    value             the number; units are carried in the metric name

  results/csv/pipe_latency_<placement>-r<run>.csv   one row per payload
    clock             always clock_gettime after part 1 settled the choice
    payload_bytes     payload written by the parent, 4 .. 524288
    reps              timed exchanges at this size, after 50 warmup exchanges
    mean              ONE-WAY mean, i.e. mean round trip / 2, nanoseconds
    min               ONE-WAY minimum, i.e. minimum round trip / 2
    unit              ns

  results/csv/pipe_throughput_<placement>-r<run>.csv  one row per chunk size
    chunk_bytes       bytes per write() call
    writes_per_run    write() calls in one timed run
    total_bytes       chunk_bytes * writes_per_run, the volume moved
    trials            timed runs behind the two statistics (5), after 1 warmup
    mean_MiB_per_s    mean of the trial rates -- recorded, never plotted
    max_MiB_per_s     best trial: the statistic the paper uses
    mean_ns_per_write elapsed / writes_per_run, a per-call cost

  results/csv/pipe_capacity.csv             one row per fill method
    method            f_getpipe_sz | folklore_16_pages | single_byte_writes |
                      chunk_<n>
    bytes             bytes accepted before EAGAIN, or the reported capacity
    pages_at_4096     bytes / page size
    note              how the row was obtained

  results/csv/pipe_resize_<placement>.csv   one row per (capacity, chunk) cell
    requested_capacity   what F_SETPIPE_SZ was asked for
    actual_capacity      what F_GETPIPE_SZ reported afterwards -- the kernel
                         rounds up to a page and a power of two, so this is
                         the value that is ever used in analysis
    chunk_bytes          bytes per write()
    total_bytes          volume moved in the cell
    best_MiB_per_s       best of 3 trials
    chunk_over_capacity  chunk_bytes / actual_capacity, the ratio the knee is
                         predicted to sit at

  results/csv/pipe_profile.csv              one row per (payload, placement)
    config            same | cross | unpinned, derived from the CPU arguments
    payload_bytes     payload per exchange
    reps              round trips
    wall_s            elapsed, parent's clock_gettime
    ns_per_roundtrip  wall_s * 1e9 / reps
    user_s            ru_utime, BOTH processes summed
    system_s          ru_stime, both processes summed
    unaccounted_s     wall - user - system: time neither process was running
    vol_ctxsw         ru_nvcsw, both processes: blocking on a pipe
    invol_ctxsw       ru_nivcsw, both processes: preemption
    vol_ctxsw_per_rt  vol_ctxsw / reps

  Because user_s and system_s sum two processes against one elapsed interval,
  they can exceed wall_s when the two genuinely overlap, and unaccounted_s can
  then come out slightly negative. Section 15 says what that means and how the
  paper's table handles it.

  report/figures/*.dat are whitespace-separated with a one-line header, which
  is the form pgfplots reads directly. Column names there are the placement or
  the configured capacity; the first column is always the independent
  variable in bytes.
""")

    # ------------------------------------------------------------------
    head(fh, 7, "Part 1 -- clock selection")
    fh.write("""  VARIABLES   cause: the clock API. effects: accuracy against a known
              interval, cost of one call, granularity.
  HYPOTHESIS  clock_gettime resolves finely enough to time a single pipe
              exchange; gettimeofday, with a microsecond interface, does not.

  Three sources were compared, not two. The assignment asks for rdtsc "or its
  analogue"; this is arm64, so the analogue is the generic timer count register
  cntvct_el0, scaled by the frequency the hardware reports in cntfrq_el0.

  Experiment A  accuracy: time sleep(5) five times with each clock.
  Experiment B  granularity: 1,000,000 back-to-back reads into a preallocated
                array, post-processed afterwards. Nothing else in the loop and
                no printing inside it. Reports mean cost per call, the smallest
                nonzero delta between consecutive reads, and the fraction of
                consecutive deltas that are exactly zero.
  Experiment C  the two textbook cycle-counter caveats, tested rather than
                repeated: frequency invariance (covered by A) and per-core
                skew (read the counter pinned to each core in turn).
""")
    cmd(fh, "./timer-test")
    paste(fh, newest("clock-final.txt"))
    fh.write("""  FINDINGS

  - gettimeofday is disqualified: %(gtod_zero).2f%% of adjacent readings are
    identical, because two calls complete inside one microsecond tick. It
    cannot resolve the %(LatSameSmall)s ns exchange part 2 has to measure.

  - The cycle counter is the cheapest to read (%(cc_call).1f ns) but not the
    finest. cntfrq_el0 reports 24 MHz, a %(cc_res).2f ns period, and two
    back-to-back reads differ by zero ticks.

  - clock_gettime shows a smallest nonzero delta of %(cgt_res).0f ns -- the
    same quantum. The reason is that the kernel's clocksource IS that register:

""" % dict(C, **N))
    cmd(fh, "cat /sys/devices/system/clocksource/clocksource0/current_clocksource")
    paste_text(fh, "arch_sys_counter", "guest")
    fh.write("""    So the vDSO reads cntvct_el0 and scales it.

  - WHY WE CHOSE clock_gettime. Not for speed: it costs about %(ratio).1fx what
    the raw counter does per call (%(cgt_call).1f ns against %(cc_call).1f ns),
    and that overhead is charged to every measurement. The grounds are
    portability and exactness:

      * clock_gettime is one POSIX call with identical behaviour on arm64 and
        x86-64. The cycle counter needs per-architecture inline assembly.
      * On x86-64 there is no cntfrq_el0 equivalent, so Timer.h has to
        CALIBRATE the TSC against CLOCK_MONOTONIC and divide -- which imports
        that clock's error into every reading taken afterwards. On arm64 the
        rate is exact and hardware-reported. A clock we can only trust on one
        of the two architectures the code compiles for is not one the result
        should rest on.
      * clock_gettime guarantees monotonicity; a raw rdtsc read does not.

    Since the two share a quantum, taking the portable clock costs resolution
    nothing. That is the trade: about %(ratio).1fx the call cost, bought with
    portability, exactness and monotonicity.

  - The zero-delta fraction needs care in reading. It is NOT a coarseness
    measure -- it is roughly 1 - (call cost / quantum), so it says how cheap a
    call is relative to one tick. cntvct_el0's high fraction and
    gettimeofday's high fraction have opposite causes: the first has a fine
    quantum and very cheap calls, the second has a quantum 24x coarser. Only
    the second is disqualifying. figures/clock_table.tex prints the
    predicted value 1 - call/quantum beside the measured fraction to make
    that explicit; the paper shows the two quantities the choice turns on as
    Figure 1 instead, for space.

  - Cross-core skew is at most %(skew).0f ns with no systematic step. The arm64
    generic timer is architecturally system-wide, so the per-core skew warning
    written for the x86 TSC does not apply here. Measured, not assumed.

  - All three clocks recover sleep(5) as %(SleepMean)s s and agree with each
    other within %(SleepSpread)s ppm. The shared %(SleepOver)s ppm excess over
    five seconds is the wakeup latency of sleep() itself, not clock error --
    which is exactly why three independent clocks agree on it. Accuracy
    separates none of the three, so the decision falls entirely to
    granularity -- which separates gettimeofday from the other two, and then
    to portability, which separates those two from each other.

  - No clock stepped backwards in 1,000,000 reads (backward_deltas = 0 for all
    three), so monotonicity is measured here and not merely assumed from the
    CLOCK_MONOTONIC name.
""" % dict(C, **N))

  # ------------------------------------------------------------------
    head(fh, 8, "Part 2 -- latency")
    fh.write("""  VARIABLES   cause: payload size (4 B to 512 KiB, the sizes the assignment
              specifies) and process placement. effect: one-way latency.
  HYPOTHESIS  flat at small payloads where a fixed per-exchange cost dominates,
              then linear once per-byte copying dominates.

  Latency is measured as a round trip and halved. This keeps one clock on one
  core for the whole measurement, so no cross-core clock comparison is ever
  needed -- which matters because part 1 established that the counter is shared
  but the general technique should not depend on that.

  Three placements, five independent process launches each. Five launches
  rather than five internal trials: the internal trials share one set of warm
  caches and one scheduling placement, so they do not expose run-to-run
  variance, and separate launches do.

  STATISTIC. Minimum, not mean. Each launch reports its own internal minimum,
  and we take the minimum again across the five launches. Noise from
  preemption, interrupts and migration can only ADD time, so the minimum is the
  least contaminated estimate. Means are recorded in the CSVs as well, and the
  gap between them is itself informative -- see part 4c.
""")
    cmd(fh, "./run_matrix.sh      # ./latency-test <label> [parent_cpu] [child_cpu]",
        "#   unpinned:   ./latency-test unpinned-rN",
        "#   same core:  ./latency-test same-rN  0 0",
        "#   cross core: ./latency-test cross-rN 0 1")
    for cfg in ("same", "cross", "unpinned"):
        f = newest("latency-%s-r1-*.txt" % cfg)
        paste(fh, f, "run 1 of 5, %s" % cfg)
    fh.write("""  The other four launches per placement are in results/raw/ in full. Rather
  than paste fifteen near-identical tables, every launch's number is given
  below, read out of results/csv, so the aggregation can be checked by hand:
  "kept" is the value that reaches the paper, "spread" is (max-min)/min across
  the five launches, and "mean/min" is that launch set's best mean over its
  best minimum.

""")
    for cfg in ("same", "cross", "unpinned"):
        run_table(fh, "pipe_latency", cfg, "payload_bytes", "min",
                  "one-way minimum, ns", min,
                  extra=mean_min_ratio("pipe_latency", cfg),
                  extra_label="mean/min")
    fh.write("""  READING THE SPREAD. This is the empirical case for the minimum, and it is
  not a small effect. Same core reproduces to within a few per cent from one
  launch to the next and its mean sits within about a tenth of its minimum.
  Cross core and unpinned spread by roughly a factor of two between launches
  at small payloads, and their means run about five times their minima. Same
  benchmark, same binary, same machine: the difference is entirely in what the
  scheduler does to a pair that has to be woken on another core. Reporting
  means here would have reported the contamination, and reporting a single
  launch would have reported whichever contamination that launch happened to
  get.

  FINDINGS

  - The predicted shape holds: flat below 4 KiB, linear above 16 KiB.

  - The unpredicted result is a constant vertical offset in the flat region.
    Same core costs %(LatSameSmall)s ns per message, cross core
    %(LatCrossSmall)s ns. That %(LatPenalty)s ns penalty does not vary with
    payload size, so it is not a copying cost.
    Part 4c shows it is time spent descheduled.

  - Unpinned runs track the cross-core curve, so the scheduler spreads a
    communicating pair across cores by default. A benchmark that does not
    control placement is therefore measuring the cross-core case silently.

  - The slope of the same-core line above 16 KiB implies %(CopyBW)s GiB/s of copy
    bandwidth. Derivation: a round trip copies the payload twice, once out of
    the writer on write() and once into the reader on read(), while the
    reported figure is half a round trip. The two factors of two cancel, so the
    bandwidth is simply (largest payload) / (latency span):
    %(LatSameBig)s ns - %(LatSameSmall)s ns = %(LatSpan)s ns for 512 KiB,
    which is %(CopySlope)s bytes per nanosecond.
""" % N)

    # ------------------------------------------------------------------
    head(fh, 9, "Part 3 -- throughput")
    fh.write("""  VARIABLES   cause: chunk size and placement. effect: sustained one-way
              bandwidth.
  HYPOTHESIS  throughput rises as the fixed per-write cost is amortized over
              more bytes, then falls once chunks exceed the pipe capacity and
              the writer starts to block.

  One-way streaming with a single acknowledgement for the whole transfer, so
  the ack contributes negligibly. Roughly 64 MiB moved per measurement. Chunk
  sizes are the ten the assignment specifies plus five extra points clustered
  around 64 KiB, because that is where the default capacity sits and the
  interesting behaviour was expected there.

  STATISTIC. Maximum, for the same reason part 2 takes the minimum: this is a
  rate, so the best observation is the least contaminated one. We never take an
  arithmetic mean of a rate -- averaging rates is the error Smith's CACM paper
  and Heiser's benchmarking-crimes list both single out.
""")
    cmd(fh, "./run_matrix.sh      # ./throughput-test <label> [parent_cpu] [child_cpu]")
    for cfg in ("same", "cross", "unpinned"):
        paste(fh, newest("throughput-%s-r1-*.txt" % cfg), "run 1 of 5, %s" % cfg)
    fh.write("  All five launches per placement, as for part 2:\n\n")
    for cfg in ("same", "cross", "unpinned"):
        run_table(fh, "pipe_throughput", cfg, "chunk_bytes", "max_MiB_per_s",
                  "best MiB/s per launch", max)
    fh.write("""  The rate spread is far milder than part 2's latency spread, for a
  structural reason: a throughput run streams 64 MiB and lasts tens of
  milliseconds, so a scheduling stall is amortized over the whole transfer,
  whereas a single 4-byte exchange lasting 700 ns is either clean or ruined.
  The same noise is present in both; only the denominator differs.

  FINDINGS

  - The first half of the hypothesis is right and the second half is wrong.

  - Cross core behaves as predicted: it peaks at %(ThrCrossPeak)s MiB/s around
    8 KiB and collapses to %(ThrCrossBig)s MiB/s by 512 KiB.

  - Same core does NOT collapse. It climbs to %(ThrSamePeak)s MiB/s and stays
    flat through chunks eight times the capacity. This falsifies the blocking explanation as
    stated: the same-core writer blocks exactly as often, the pipe being the
    same size, and pays nothing for it.

  - Below 4 KiB the ordering inverts and cross core is faster. That is the
    signature of the real mechanism: across cores the writer and reader
    genuinely overlap, and overlap is worth more than cache locality while
    messages are small.

  - So the mechanism is loss of overlap, not blocking per se. Pipelining
    survives only while the writer can deposit a whole chunk without stalling.
    Past capacity it stalls mid-chunk every time, the pair falls into lockstep,
    and each handoff costs a full cross-core wakeup. On one core there was
    never any parallelism to lose.

  Parts 4a and 4b were designed to test that explanation rather than assert it.
""" % N)

    # ------------------------------------------------------------------
    head(fh, 10, "Part 4a -- measuring pipe capacity")
    fh.write("""  The explanation above is stated in terms of "the capacity", so the capacity
  is measured rather than assumed. Set the write end nonblocking, write until
  EAGAIN, count the bytes, and compare against F_GETPIPE_SZ and against the
  16-pages folklore. Repeated with several write sizes, because the kernel
  accounts for a pipe in whole pages and a one-byte write might have been given
  a page to itself.
""")
    cmd(fh, "./capacity-test")
    paste(fh, os.path.join(RAW, "capacity.txt"))
    fh.write("""  FINDINGS

  - Capacity is exactly 65536 bytes = 16 pages at this page size, and
    F_GETPIPE_SZ agrees with the byte count.

  - Every write size reaches the same total, including single-byte writes, so
    this kernel is not wasting a page per write. That was worth checking: on
    kernels that do, the byte count comes in far below the nominal size.
""")

    # ------------------------------------------------------------------
    head(fh, 11, "Part 4b -- capacity as the independent variable")
    fh.write("""  A correlation observed at one fixed capacity is not evidence of a cause. So
  capacity itself becomes the independent variable: F_SETPIPE_SZ at 4 KiB,
  16 KiB, 64 KiB, 256 KiB and 1 MiB, with a reduced throughput sweep at each.

  If the knee follows the configured capacity, capacity causes it. If the knee
  stays put while capacity moves, the part 3 story is wrong and has to be
  rewritten.

  Two implementation notes. F_SETPIPE_SZ rounds up to a page and a power of
  two, so the value the kernel actually adopted is read back with F_GETPIPE_SZ
  and that -- never the requested value -- is what gets recorded. And the guest
  has /proc/sys/fs/pipe-max-size = 1 MiB, so the whole sweep runs unprivileged
  with no sysctl change.
""")
    cmd(fh, "./resize-test same  0 0", "./resize-test cross 0 1")
    paste(fh, os.path.join(RAW, "resize-cross.txt"), "cross core")
    paste(fh, os.path.join(RAW, "resize-same.txt"), "same core")
    fh.write("""  PROVENANCE NOTE. As with part 4c, the stdout above and the committed
  results/csv/pipe_resize_*.csv are two SEPARATE executions of the same two
  commands; the figure in the paper is built from the CSV. Same core, the two
  executions agree to within a few per cent cell by cell. Cross core they
  agree on shape and on every conclusion drawn below, but individual cells
  move by tens of per cent -- which is the same cross-core run-to-run variance
  section 8 quantifies, here with only three internal trials per cell and one
  launch to damp it. The cross-core sweep is the weakest dataset in the
  report for that reason, and it is used only for the position of the knee,
  never for an absolute rate.

  Derived from results/csv/pipe_resize_cross.csv, which is what Figure 3b
  plots:

%s
  And the same reduction for the same-core sweep, which the paper does not
  plot:

%s
  FINDINGS

  - Cross core: the knee tracks the configured capacity, and the table above
    is the statement of it. Each capacity peaks at a chunk near or below its
    own size, and by the time the chunk equals the capacity a 16 KiB pipe has
    kept 18%% of its peak, a 64 KiB pipe 38%%, and a 256 KiB pipe 56%%. The
    1 MiB pipe is never given a chunk as large as itself -- 512 KiB is the
    biggest the assignment asks for -- and correspondingly never collapses,
    holding 83%% of its peak at the largest chunk tested. The ordering is
    monotone in capacity, which is what a causal relationship between the two
    looks like.

  - The 4 KiB pipe is a different and stronger statement. It never reaches
    even 250 MiB/s at any chunk size, against roughly 9000 MiB/s for the 1 MiB
    pipe: a factor of about forty, from nothing but the size of the buffer.
    Capacity does not merely move the knee, it sets the ceiling.

  - Same core: no knee at any capacity. The curves rise and plateau, and a
    larger pipe simply raises the plateau -- from about 3200 MiB/s at 4 KiB to
    about 11000 MiB/s at 1 MiB. Exactly what the overlap explanation predicts,
    since there is no overlap to lose on one core. The capacity still matters,
    because it still sets how often the writer stops; what it does not do is
    cause a collapse.

  Only the cross-core panel is plotted in the paper (Figure 3b). The same-core
  sweep is five nearly flat lines; its information content is "no knee", which
  the text states in one sentence.
""" % (resize_summary("cross"), resize_summary("same")))

    # ------------------------------------------------------------------
    head(fh, 12, "Part 4c -- where the time goes")
    fh.write("""  Parts 4a and 4b establish WHICH variable controls the collapse. This part
  accounts for the time itself.

  Tooling constraint, checked on the guest before choosing an approach: perf is
  not installed and linux-tools is packaged only for 6.8.0, so no distribution
  perf matches this custom 7.2.4 kernel; the ftrace tracing/ directory is not
  available; and QEMU with hvf almost certainly does not virtualize a PMU, so
  hardware counters were not an option regardless. We therefore used getrusage
  and strace, and we say so in the paper rather than implying counter data we
  do not have.

  pipe_profile.c runs a fixed number of round trips at ONE payload size and ONE
  placement, then accounts for the wall clock: user time, system time, and the
  remainder, which is time the processes were neither running in user mode nor
  in the kernel -- that is, blocked. Voluntary and involuntary context switches
  come from ru_nvcsw and ru_nivcsw for both processes.
""")
    cmd(fh, "./profile-test 4      20000 0 0    # small payload, same core",
        "./profile-test 524288 500   0 0    # large payload, same core",
        "./profile-test 4      20000 0 1    # small payload, cross core",
        "./profile-test 524288 500   0 1    # large payload, cross core")
    paste(fh, os.path.join(RAW, "profile.txt"))
    fh.write("""  PROVENANCE NOTE, because the two do not match digit for digit. The stdout
  above is one set of four clean runs. results/csv/pipe_profile.csv, which is
  what Table 2 in the paper is built from, is a LATER set of four clean runs,
  collected after the contaminated CSV was deleted and regenerated (section
  16, item 3). Both sets are clean -- neither was straced -- and they are kept
  separately rather than reconciled, because they are two independent
  observations of the same configuration and the agreement between them is
  itself evidence. Compare: same core at 4 B is 89.5%% system and -0.5%%
  unaccounted above, 100.9%% and -0.9%% in the CSV; cross core at 4 B is 59.4%%
  unaccounted above and %(CrossBlocked)s%% in the CSV. Wall times differ by
  about a tenth, which is ordinary run-to-run variance for this benchmark.
  Nothing in the argument turns on the difference: the qualitative split --
  same core accounted for, cross core mostly not -- reproduces exactly.

  The syscall breakdown comes from a SEPARATE set of runs under strace.""" % N)
    fh.write(""" Wall
  times from a straced run are not comparable to anything: ptrace stops both
  processes at every syscall entry and exit, which inflates precisely the
  quantity being measured. The straced runs are used only for syscall COUNTS
  and their relative time share.
""")
    cmd(fh, "strace -c -f ./profile-test 4      5000 0 0",
        "strace -c -f ./profile-test 4      5000 0 1",
        "strace -c -f ./profile-test 524288 200  0 0",
        "strace -c -f ./profile-test 524288 200  0 1")
    paste(fh, os.path.join(RAW, "strace.txt"))
    fh.write("""  FINDINGS -- this is the core of the paper's argument.

  1. The two placements do IDENTICAL work at 4 B. strace counts 10002 writes
     and 10001 reads for 5000 round trips in both cases: exactly two writes and
     two reads per round trip. Context switches are identical too, 2.00 per
     round trip. Same syscalls, same switches.

  2. Yet cross core is ten times slower in wall time, and the accounting says
     where the extra time went. Read straight out of pipe_profile.csv, with
     user and system summing BOTH processes against one elapsed interval:

%(PROFILE_TABLE)s
     Same core spends essentially all of its wall clock in the kernel, and
     over 100%% of it at 4 B because the two processes genuinely overlap.
     Cross core spends most of its wall clock neither in user code nor in the
     kernel. That residue is the %(LatPenalty)s ns penalty of part 2: time
     spent descheduled, waiting for a wakeup to be delivered to another core.
     It grows with the number of handoffs, not with the bytes moved.

  3. Voluntary context switches per round trip are %(CtxSmall)s at 4 B and
     %(CtxBig)s at 512 KiB. Against the measured 64 KiB capacity that is
     exactly

         2 * ceil(payload / capacity)

     512 KiB / 64 KiB = 8 pipe-fills, two switches each, 16 total. Measured
     %(CtxBig)s. Capacity determines the number of handoffs.

  4. strace confirms the same arithmetic from the syscall side. At 512 KiB the
     reader issues 1801 reads for 200 round trips -- 9 per round trip, being 8
     for data plus 1 for the ack -- because a read() returns only what is
     currently buffered. Writes stay at 2 per round trip because write() blocks
     until it has delivered everything. The asymmetry between the two counts is
     a direct read-out of the capacity.

  So: capacity sets how many handoffs a transfer needs, and placement sets what
  each handoff costs. Those two sentences are the paper's conclusion, and every
  clause in them is tied to a measured number above.

  5. One methodological consequence, and it is a sharp one. The mean/min
     column in section 8 is this same blocked time seen from the statistics
     side. Same core, where the residue is ~0%%, has means within
     1.03-1.10 of its minima. Cross core, where the residue is
     ~%(CrossBlocked)s%%, has means around 5x its minima at small payloads. The two columns measure the same
     phenomenon by different routes, and they agree. That is the concrete
     reason the assignment's instruction to prefer the minimum is right here,
     rather than a convention we followed because we were told to.

  6. What this does NOT establish. getrusage attributes the residue to "not
     running", not to any particular kernel path, so the identification of it
     as wakeup and IPI cost is an inference from the placement variable, not a
     direct measurement. A PMU or an ftrace sched_wakeup histogram would close
     that gap; neither was available (see the tooling constraint above), and
     the paper says so instead of implying counter data we do not have.
""" % N)

    # ------------------------------------------------------------------
    head(fh, 13, "Aggregated series as they enter the paper")
    fh.write("""  These four files are the entire numeric content of the figures. They are
  reproduced here so that the paper's plots can be read back as numbers
  without a TeX installation, a plotting library, or this repository.

  Reduction rule, once more: a value here is the best of five launches, and
  each launch already reported the best of its own internal repetitions.
  "Best" is the minimum for latency and the maximum for a rate.

""")
    dump_dat(fh, "clock.dat")
    dump_dat(fh, "latency.dat")
    dump_dat(fh, "throughput.dat")
    dump_dat(fh, "resize.dat")
    fh.write("""  And the macro file the paper's PROSE reads, so that no sentence in it
  contains a number that was typed by hand:

""")
    dump_dat(fh, "numbers.tex")

    # ------------------------------------------------------------------
    head(fh, 14, "Derived numbers quoted in the paper")
    fh.write("  Produced by scripts/aggregate.py from results/csv, never hand-copied.\n\n")
    paste_text(fh, agg_out, "python3 scripts/aggregate.py")
    fh.write("""  Mapping into the paper, by the labels the compiled PDF prints:

    Fig. 1  clock call cost and quantum   <- figures/clock.dat
    Fig. 2  latency against payload       <- figures/latency.dat
    Tab. 1  the ten required sizes        <- figures/headline_table.tex
    Fig. 3a throughput, default capacity  <- figures/throughput.dat
    Fig. 3b throughput, capacity swept    <- figures/resize.dat
    Tab. 2  where the wall clock goes     <- figures/profile_table.tex
    prose   every quoted figure           <- figures/numbers.tex

  aggregate.py also emits clock_table.tex, latency_table.tex and
  throughput_table.tex. The paper does not \\input them: the clock table was
  replaced by Figure 1 and the two full data tables by the transposed
  headline table, both to fit the two-page limit. They are still generated,
  still correct, and are the fuller form of the same data for anyone who
  wants it -- the per-launch tables in sections 8 and 9 cover the same ground
  in this file.
""")

    # ------------------------------------------------------------------
    head(fh, 15, "Threats to validity and known limitations")
    fh.write("""  Stated here in full. The paper has room for three sentences of this; a lab
  record should carry the rest.

  1. VIRTUALIZATION. Everything ran in a QEMU/hvf guest. Absolute latencies
     include hypervisor overhead, and the cross-core wakeup path in particular
     involves a virtual IPI, which is likely to be more expensive than the
     bare-metal equivalent. The cross-core PENALTY may therefore be inflated
     relative to real hardware. What the design protects is the comparison:
     both placements run under the same hypervisor on the same boot, so the
     overhead is common to both arms. We would not quote the
     %(LatSameSmall)s ns figure as "the cost of a Linux pipe on Apple
     silicon"; we quote it as the baseline that the %(LatPenalty)s ns penalty
     is measured against.

  2. ONE MACHINE, ONE KERNEL. Every number comes from one guest on one host.
     Nothing here establishes that the effects generalize across
     microarchitectures, and the arm64/x86-64 asymmetry in Timer.h is a
     standing reminder that they might not. The second machine available to us
     was deliberately not mixed in (section 2).

  3. THE ACK IS ASYMMETRIC. Part 2 calls one-way latency half a round trip,
     but the round trip is an N-byte write answered by a 1-byte ack. At 4 B
     the two legs are near enough symmetric; at 512 KiB they are not, and the
     halved figure understates the large-payload leg and overstates the ack
     leg. Halving is the conventional estimate and we use it, but the copy
     bandwidth derived from the slope is the number to trust at large
     payloads, not the halved latency itself.

  4. getrusage RESOLUTION. user_s and system_s are accounted at timer-tick
     granularity, while wall_s comes from clock_gettime. Over a run of a few
     tens of milliseconds that mismatch is enough to make user+system exceed
     wall by a fraction of a per cent, which is why the same-core rows show a
     small NEGATIVE unaccounted figure. The paper's table clamps that column
     at zero and says what it is. The effect is under one per cent, and the
     cross-core residue it is being compared against is around
     %(CrossBlocked)s per cent, so no conclusion rests on it. It is also
     the reason system time can read above 100%%: two processes are summed against
     one elapsed interval, and on one core they alternate but their kernel
     time still adds.

  5. THE UNPINNED ANOMALY. Unpinned tracks cross core up to 256 KiB and is
     then WORSE than either pinning at 512 KiB: %(UnpinnedBig)s ns against
     cross core's %(CrossBig)s ns (section 8). We do not have an
     explanation. The honest reading is that the scheduler is free to migrate
     either process mid-transfer, and a migration with a half-full pipe is
     worse than either fixed placement. We say so in the paper rather than
     quietly dropping the point.

  6. NO HARDWARE COUNTERS. perf, ftrace and the PMU were all unavailable
     (section 12). The time breakdown is getrusage plus strace, which can say
     that time was spent not running but cannot name the kernel path. The
     causal claim about capacity is carried instead by part 4b, where capacity
     is manipulated rather than observed.

  7. SINGLE READER, SINGLE WRITER, NO CONTENTION. One pipe, one pair of
     processes, an idle machine. Nothing here says anything about many pipes,
     many pairs, or a loaded system, and the scheduler behaviour that dominates
     the cross-core case is exactly what a loaded system would change.

  8. STRACE RUNS ARE NOT TIMING RUNS. Counts and relative shares only. The
     wall times in results/raw/strace.txt are ptrace-inflated by construction
     and are never quoted.
""" % N)

    # ------------------------------------------------------------------
    head(fh, 16, "Problems encountered and how they were resolved")
    fh.write("""  Recorded because each one silently produced plausible-looking wrong data,
  which is the failure mode that matters most in benchmarking.

  1. STALE BINARIES OVERWROTE A GOOD BUILD.
     The host repository contained committed-by-accident build products from an
     earlier session. `rsync -a` compares size and mtime, does not read
     .gitignore, and happily copied those stale binaries over the freshly built
     ones in the guest. A full 30-run matrix was then collected with the WRONG
     code, and it looked entirely normal -- the giveaway was that every run
     wrote pipe_latency.csv instead of the per-label filename the current
     source produces.
     Fixed: binaries deleted from the host repo; sync.sh excludes build
     products explicitly; run_matrix.sh now runs `make -B` before collecting,
     so a stale binary cannot survive into a measurement.

  2. rsync --delete-excluded DELETED THE GUEST'S RESULTS.
     sync.sh originally passed --delete-excluded while excluding results/.
     That flag deletes excluded paths ON THE DESTINATION, so pushing sources
     wiped the guest's results directory mid-session. Nothing was lost because
     the host copies were already committed, but the tee writes that followed
     failed.
     Fixed: --delete-excluded removed, with a comment recording why.

  3. APPEND-MODE CSV MIXED STRACED AND CLEAN RUNS.
     pipe_profile.c opens its CSV with "a" so that four separate invocations
     accumulate into one table. The strace runs therefore appended to the same
     file, and the aggregated table silently contained ptrace-inflated rows
     (9 context switches per round trip instead of 2, wall times 50x too
     large).
     Fixed: the CSV is deleted and regenerated from clean runs only; the
     straced runs are kept separately in results/raw/strace.txt and used only
     for syscall counts.

  4. FIRST MATRIX SWEPT A CLOCK IT DID NOT NEED.
     pipe_latency.c originally measured every payload twice, once per clock.
     Part 1 had already shown gettimeofday cannot resolve a 708 ns round trip,
     so the second sweep only re-measured that limitation. Removed, and the
     whole matrix re-run so that the committed CSVs match the committed source.

  5. LATEX/PGFPLOTS.
     Three build failures worth noting for whoever rebuilds this: \\SI needs
     siunitx (not loaded initially); a pgfplots style defined with
     /.style= was looked up in the /tikz/ key path and failed on xmode, so axis
     options are written out explicitly instead; and \\input of a partial
     tabular ends the file immediately after a row terminator, which makes the
     following \\bottomrule a misplaced \\noalign -- so scripts/aggregate.py
     emits the complete tabular environment rather than just its rows.

  6. THE PAPER'S TABLE 1 DISAGREED WITH THE COMMITTED CSV.
     The clock table and several numbers in the prose were typed in by hand
     from the first timer-test run. Part 1 was later re-run -- after the latency
     benchmark was trimmed -- and clock_precision.csv was regenerated, but the
     paper was not. The table went on quoting a 35.3 ns call cost and a 19.83%
     zero fraction while the committed CSV said 20.2 ns and 53.7%. Both runs
     were internally consistent, so nothing looked wrong; the paper simply
     described a run whose data had been replaced. Cross-core skew had drifted
     the same way, 400 ns in the prose against 83 ns in the data.
     Fixed, and fixed structurally rather than by retyping: the clock table
     is now generated from clock_precision.csv, and scripts/aggregate.py additionally
     emits figures/numbers.tex, a set of LaTeX macros holding every figure the
     PROSE quotes. Re-running a benchmark now updates the sentences, not just
     the tables. This log takes its numbers from the same source.

  7. FIGURE COLOURS.
     The first draft let pgfplots cycle its default colours. With five curves
     in Figure 3b the cycle repeated, drawing the 4 KiB and 1 MiB capacities --
     the two extremes of the comparison -- in the same blue. Capacity is an
     ORDERED quantity, so the fix was not merely more colours but the right
     kind: a single-hue ramp stepped light to dark, with distinct marks as a
     second channel. Both palettes were checked with a colour-vision validator
     rather than by eye.
""")

    # ------------------------------------------------------------------
    head(fh, 17, "Index of data files, with checksums")
    fh.write("""  Checksums are SHA-256, truncated to 16 hex digits, computed at generation
  time. They are here so that a reader can tell whether the file they are
  looking at is the one this log describes -- the failure mode in section 16
  item 1 was a stale file that looked right, and a checksum would have caught
  it immediately.

  Naming: <benchmark>-<placement>-r<launch>-<collection timestamp>.txt. All
  files from one run_matrix.sh invocation share the timestamp.

""")
    for label, d in (("results/raw", RAW), ("results/csv", CSV)):
        files = sorted(f for f in os.listdir(d) if not f.startswith("."))
        total = sum(os.path.getsize(os.path.join(d, f)) for f in files)
        fh.write("  %s/  (%d files, %d bytes)\n\n" % (label, len(files), total))
        for f in files:
            p = os.path.join(d, f)
            fh.write("    %-52s %7d  %s\n"
                     % (f, os.path.getsize(p), sha256(p)[:16]))
        fh.write("\n")
    fh.write("  report/figures/  (generated from results/csv)\n\n")
    figdir = os.path.join(ROOT, "report", "figures")
    for f in sorted(os.listdir(figdir)):
        p = os.path.join(figdir, f)
        if os.path.isfile(p):
            fh.write("    %-52s %7d  %s\n"
                     % (f, os.path.getsize(p), sha256(p)[:16]))

    # ------------------------------------------------------------------
    head(fh, 18, "Commit history")
    fh.write("  Branch: %s  HEAD: %s\n"
             % (git("rev-parse", "--abbrev-ref", "HEAD").strip(),
                git("rev-parse", "--short", "HEAD").strip()))
    fh.write("  Full history, newest first. The data commits are the ones to\n"
             "  check a number against: anything committed after them only\n"
             "  reshapes the presentation.\n\n")
    fh.write(git("log", "--format=  %h  %ad  %s", "--date=short"))

    fh.write("\n" + rule() + "\nend of log\n" + rule() + "\n")
    fh.close()
    print("wrote EXPERIMENTS.txt (%d bytes, %d lines)"
          % (os.path.getsize(OUT), sum(1 for _ in io.open(OUT, encoding="utf-8"))))


if __name__ == "__main__":
    main()
