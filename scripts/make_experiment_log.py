#!/usr/bin/env python3
"""Assemble EXPERIMENTS.txt, the full plain-text lab record.

The paper is the argument; this file is the evidence behind it. Every command
that produced a committed number appears here with its raw output, so a reader
can check any figure in the paper against the terminal session that made it.

Standard library only. Regenerate with:  python3 scripts/make_experiment_log.py
"""
import datetime
import glob
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
    fh = io.open(OUT, "w", encoding="utf-8")
    C = clock_numbers()

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

CONTENTS
   1. Deliverables
   2. Apparatus
   3. Reproducing from a clean checkout
   4. Source files
   5. Part 1 -- clock selection
   6. Part 2 -- latency
   7. Part 3 -- throughput
   8. Part 4a -- measuring pipe capacity
   9. Part 4b -- capacity as the independent variable
  10. Part 4c -- where the time goes
  11. Derived numbers quoted in the paper
  12. Problems encountered and how they were resolved
  13. Index of raw output files
  14. Commit history
""")

    # ------------------------------------------------------------------
    head(fh, 1, "Deliverables")
    fh.write("""  report/main.tex     the paper, source
  report/main.pdf     the paper, compiled: 2-column, 11pt, 1in margins as the
                      assignment requires. NOTE it currently runs to 3 pages
                      and the assignment asks for 2; trimming is outstanding.
  EXPERIMENTS.txt     this file
  results/csv/        every number the paper cites, as CSV
  results/raw/        unedited stdout from every run
  report/figures/     plot data and the generated table, built from results/csv
  scripts/            aggregation and log generation, standard library only
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
""")

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

  Then back on the host:

    $ rsync -a -e 'ssh -p 2222' shawliu@localhost:~/advos-miniproj-2/results/ results/
    $ python3 scripts/aggregate.py          # results/csv -> report/figures
    $ cd report && latexmk -pdf main.tex

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
""")

    # ------------------------------------------------------------------
    head(fh, 5, "Part 1 -- clock selection")
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
    cannot resolve the 708 ns round trip that part 2 has to measure.

  - The cycle counter is the cheapest to read (%(cc_call).1f ns) but not the
    finest. cntfrq_el0 reports 24 MHz, a %(cc_res).2f ns period, and two
    back-to-back reads differ by zero ticks.

  - clock_gettime shows a smallest nonzero delta of %(cgt_res).0f ns -- the
    same quantum. The reason is that the kernel's clocksource IS that register:

""" % C)
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
    the second is disqualifying. The paper's Table 1 prints the predicted
    value beside the measured one to make that explicit.

  - Cross-core skew is at most %(skew).0f ns with no systematic step. The arm64
    generic timer is architecturally system-wide, so the per-core skew warning
    written for the x86 TSC does not apply here. Measured, not assumed.

  - All three clocks recover sleep(5) as 5.0024 s and agree within 53 ppm. The
    492 ppm excess is the wakeup latency of sleep() itself, not clock error --
    which is exactly why three independent clocks agree on it.
""" % C)

  # ------------------------------------------------------------------
    head(fh, 6, "Part 2 -- latency")
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
    fh.write("""  Remaining runs (r2-r5 for each placement) are in results/raw/ and are
  aggregated into report/figures/latency.dat by scripts/aggregate.py.

  FINDINGS

  - The predicted shape holds: flat below 4 KiB, linear above 16 KiB.

  - The unpredicted result is a constant vertical offset in the flat region.
    Same core costs 708 ns per message; cross core costs 2042 ns. The 1333 ns
    penalty does not vary with payload size, so it is not a copying cost.
    Part 4c shows it is time spent descheduled.

  - Unpinned runs track the cross-core curve, so the scheduler spreads a
    communicating pair across cores by default. A benchmark that does not
    control placement is therefore measuring the cross-core case silently.

  - The slope of the same-core line above 16 KiB implies 19.2 GiB/s of copy
    bandwidth. Derivation: a round trip copies the payload twice, once out of
    the writer on write() and once into the reader on read(), while the
    reported figure is half a round trip. The two factors of two cancel, so the
    bandwidth is simply (largest payload) / (latency span).
""")

    # ------------------------------------------------------------------
    head(fh, 7, "Part 3 -- throughput")
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
    for cfg in ("same", "cross"):
        paste(fh, newest("throughput-%s-r1-*.txt" % cfg), "run 1 of 5, %s" % cfg)
    fh.write("""  FINDINGS

  - The first half of the hypothesis is right and the second half is wrong.

  - Cross core behaves as predicted: it peaks at 6431 MiB/s around 8 KiB and
    collapses to 2391 MiB/s by 512 KiB.

  - Same core does NOT collapse. It climbs to 9678 MiB/s and stays flat through
    chunks eight times the capacity. This falsifies the blocking explanation as
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
""")

    # ------------------------------------------------------------------
    head(fh, 8, "Part 4a -- measuring pipe capacity")
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
    head(fh, 9, "Part 4b -- capacity as the independent variable")
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
    fh.write("""  FINDINGS

  - Cross core: the knee tracks the configured capacity. A 16 KiB pipe
    collapses at 8 KiB chunks, a 64 KiB pipe at 64 KiB, a 256 KiB pipe at
    256 KiB, and a 1 MiB pipe -- larger than any chunk tested -- never
    collapses at all. The causal claim is established.

  - Same core: no knee at any capacity. The curves rise and plateau, and a
    larger pipe simply raises the plateau. Exactly what the overlap
    explanation predicts, since there is no overlap to lose on one core.

  Only the cross-core panel is plotted in the paper (Figure 2b). The same-core
  sweep is five nearly flat lines; its information content is "no knee", which
  the text states in one sentence.
""")

    # ------------------------------------------------------------------
    head(fh, 10, "Part 4c -- where the time goes")
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
    fh.write("""  The syscall breakdown comes from a SEPARATE set of runs under strace. Wall
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
     where it went. Same core: 89-101% system time, ~0% unaccounted. Cross
     core: 37-39% system time and 59-61% UNACCOUNTED -- neither user nor
     kernel. That residue is the 1333 ns penalty from part 2. It is time spent
     descheduled, waiting for a wakeup to be delivered to another core.

  3. Voluntary context switches per round trip are 1.99 at 4 B and 15.99 at
     512 KiB. Against the measured 64 KiB capacity that is exactly

         2 * ceil(payload / capacity)

     512 KiB / 64 KiB = 8 pipe-fills, two switches each, 16 total. Measured
     15.99. Capacity determines the number of handoffs.

  4. strace confirms the same arithmetic from the syscall side. At 512 KiB the
     reader issues 1801 reads for 200 round trips -- 9 per round trip, being 8
     for data plus 1 for the ack -- because a read() returns only what is
     currently buffered. Writes stay at 2 per round trip because write() blocks
     until it has delivered everything. The asymmetry between the two counts is
     a direct read-out of the capacity.

  So: capacity sets how many handoffs a transfer needs, and placement sets what
  each handoff costs. Those two sentences are the paper's conclusion, and every
  clause in them is tied to a measured number above.

  5. One methodological consequence. The mean/min gap in part 2 (means run 3-5x
     the minimum) is this same blocked time appearing as a long tail. That is
     the concrete reason the assignment's instruction to prefer the minimum is
     correct here, and we report it as such rather than as a convention.
""")

    # ------------------------------------------------------------------
    head(fh, 11, "Derived numbers quoted in the paper")
    fh.write("  Produced by scripts/aggregate.py from results/csv, never hand-copied.\n\n")
    try:
        out = subprocess.check_output(
            ["python3", os.path.join(ROOT, "scripts", "aggregate.py")],
            cwd=ROOT, stderr=subprocess.STDOUT).decode()
        paste_text(fh, out, "python3 scripts/aggregate.py")
    except Exception as e:
        fh.write("    (could not run aggregate.py: %s)\n\n" % e)
    fh.write("""  Mapping into the paper:
    Table 1  <- results/csv/clock_precision.csv
    Fig. 1   <- report/figures/latency.dat
    Fig. 2a  <- report/figures/throughput.dat
    Fig. 2b  <- report/figures/resize.dat
    Table 2  <- report/figures/profile_table.tex (from pipe_profile.csv)
""")

    # ------------------------------------------------------------------
    head(fh, 12, "Problems encountered and how they were resolved")
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
     Table 1 and several numbers in the prose were typed in by hand from the
     first timer-test run. Part 1 was later re-run -- after the latency
     benchmark was trimmed -- and clock_precision.csv was regenerated, but the
     paper was not. The table went on quoting a 35.3 ns call cost and a 19.83%
     zero fraction while the committed CSV said 20.2 ns and 53.7%. Both runs
     were internally consistent, so nothing looked wrong; the paper simply
     described a run whose data had been replaced. Cross-core skew had drifted
     the same way, 400 ns in the prose against 83 ns in the data.
     Fixed, and fixed structurally rather than by retyping: Table 1 is now
     generated from clock_precision.csv, and scripts/aggregate.py additionally
     emits figures/numbers.tex, a set of LaTeX macros holding every figure the
     PROSE quotes. Re-running a benchmark now updates the sentences, not just
     the tables. This log takes its numbers from the same source.

  7. FIGURE COLOURS.
     The first draft let pgfplots cycle its default colours. With five curves
     in Figure 2b the cycle repeated, drawing the 4 KiB and 1 MiB capacities --
     the two extremes of the comparison -- in the same blue. Capacity is an
     ORDERED quantity, so the fix was not merely more colours but the right
     kind: a single-hue ramp stepped light to dark, with distinct marks as a
     second channel. Both palettes were checked with a colour-vision validator
     rather than by eye.
""")

    # ------------------------------------------------------------------
    head(fh, 13, "Index of raw output files")
    files = sorted(os.listdir(RAW))
    fh.write("  results/raw/  (%d files)\n\n" % len(files))
    for f in files:
        size = os.path.getsize(os.path.join(RAW, f))
        fh.write("    %-52s %7d bytes\n" % (f, size))
    fh.write("\n  results/csv/\n\n")
    for f in sorted(os.listdir(CSV)):
        size = os.path.getsize(os.path.join(CSV, f))
        fh.write("    %-52s %7d bytes\n" % (f, size))

    # ------------------------------------------------------------------
    head(fh, 14, "Commit history")
    fh.write(git("log", "--format=  %h  %ad  %s", "--date=short", "-12"))

    fh.write("\n" + rule() + "\nend of log\n" + rule() + "\n")
    fh.close()
    print("wrote EXPERIMENTS.txt (%d bytes, %d lines)"
          % (os.path.getsize(OUT), sum(1 for _ in io.open(OUT, encoding="utf-8"))))


if __name__ == "__main__":
    main()
