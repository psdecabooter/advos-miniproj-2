# Methodology

**Evaluation of IPC through Linux Pipes** — COMP SCI 736 Mini-Project 2
Patrick DeCabooter and Shaw Liu

This document explains *how the experiments were built and why they are shaped
the way they are*. It is the companion to two other files:

| File | Answers |
|---|---|
| `report/main.pdf` | What did you find? |
| `EXPERIMENTS.txt` | What did you run, and what came out? (commands, raw output, every number) |
| `METHODOLOGY.md` (this file) | Why is the experiment built this way, and what else did you consider? |

Nothing here restates data. Numbers appear only where a decision turned on
one, and every such number is in `EXPERIMENTS.txt` with its raw output.

---

## 1. The question, and how we read the assignment

The assignment asks for four things: pick a clock and justify it, measure pipe
latency across payload sizes, measure pipe throughput across chunk sizes, and
explain the mechanism behind the numbers. The required payload/chunk sizes are
ten values from 4 B to 512 KiB.

Two readings of "measure pipe latency" are possible, and they produce different
projects:

1. **Payload size is the independent variable.** Sweep it, plot the curve, note
   that big payloads cost more. This satisfies the assignment literally.
2. **Payload size is *one* independent variable.** Something else may matter
   more, and a sweep that holds it uncontrolled will average over it silently.

We went with (2) after an early observation: repeated runs of the same
benchmark disagreed with each other by more than the effect the payload sweep
was showing. That is the signature of an uncontrolled variable. The obvious
candidate on an 8-vCPU machine is **where the two processes run**, so placement
became a controlled factor everywhere, and the project's actual result —
placement matters more than payload — came out of that decision rather than
out of the sweep the assignment named.

The second choice was to treat part 4 ("explain the mechanism") as *work*
rather than as a discussion paragraph. Parts 4a–4c exist because the part 3
explanation we first wrote down was, on inspection, untested. Section 5.5
below traces that.

---

## 2. Where it runs, and why that was not negotiable

Everything runs inside a QEMU guest (Ubuntu 24.04 arm64, custom Linux 7.2.4,
8 vCPUs), never on the macOS host.

**Why:** the report is about *Linux* pipes. macOS pipes are XNU, with a
different buffer implementation and different blocking behaviour. Numbers taken
on the host would be about a different kernel than the one the paper discusses,
and no amount of caveating fixes that.

**The cost of that decision**, stated in the paper rather than hidden: the guest
is virtualized, so absolute latencies include hypervisor overhead, and the
cross-core wake-up path in particular crosses a virtual IPI. **The design
response** is to make every claim a *comparison measured under identical
conditions* — same core vs cross core, one capacity vs another — so the
overhead is common to both arms and cancels in the difference. We never quote
an absolute latency as a property of Linux pipes in general.

**One machine, one dataset.** A second machine (x86-64, WSL2) was available.
Its earlier numbers came from a version of the latency benchmark with an
accumulator bug and were discarded outright; we did not mix results from two
machines into one figure or one table. Cross-machine comparison would have been
a legitimate *additional* experiment, but silently pooling two machines into
one curve is a benchmarking error, not a shortcut.

---

## 3. Procedure, in the order it happened

1. **Specs first.** Before any benchmark, record the guest's page size,
   `pipe-max-size`, clock source, compiler, and which profiling tools exist
   (`shaw-computer-specs.txt`). Two of those facts changed the design
   immediately: `pipe-max-size` = 1 MiB meant the whole capacity sweep could run
   unprivileged, and the absence of any usable `perf` build ruled out hardware
   counters before we wrote code that assumed them.
2. **Part 1, clock selection.** Three clocks, three experiments, a decision, and
   a written justification. Nothing downstream is timed until this is settled.
3. **Part 2 and 3 harnesses**, sharing one placement mechanism and one
   statistics policy.
4. **The full matrix in one invocation** (`run_matrix.sh`): 3 placements × 5
   launches × 2 benchmarks = 30 launches, all from one command, all stamped with
   one timestamp. One invocation rather than thirty hand-typed commands, because
   a matrix assembled by hand over an afternoon is a matrix collected under
   drifting conditions.
5. **Part 4a**, measure the capacity the part 3 explanation depends on.
6. **Part 4b**, turn that capacity into the independent variable.
7. **Part 4c**, account for the wall clock with `getrusage` and `strace`.
8. **Aggregate** (`scripts/aggregate.py`): CSVs → plot data, tables, and prose
   macros.
9. **Write**, with every number in the paper `\input` from step 8.
10. **Regenerate the log** (`scripts/make_experiment_log.py`), which re-runs
    step 8 first so the log cannot quote a number the paper does not.

Steps 8–10 are re-runnable at any time and are the reason a late re-run of a
benchmark updates the paper's sentences, not just its tables (§6.3).

---

## 4. Design decisions in the measurement code

### 4.1 Three clocks, not two

The assignment names `clock_gettime`, `gettimeofday`, and "`rdtsc` or its
analogue". The machine is arm64, so the analogue is the generic timer's virtual
count register `cntvct_el0`, scaled by the frequency the hardware reports in
`cntfrq_el0`. Including it was not box-ticking: the two architectures differ in
a way that decides the experiment.

| | arm64 `cntvct_el0` | x86-64 `rdtsc` |
|---|---|---|
| Rate | Fixed, reported by `cntfrq_el0` | Unknown; must be calibrated |
| Calibration error | None | Inherits `CLOCK_MONOTONIC`'s error |
| Per-core skew | Architecturally system-wide | The classic caveat |
| Resolution | Coarse (24 MHz) | Fine (near core clock) |

`Timer.h` implements both behind one interface, selected at compile time, which
is what makes that table a property of the code rather than a claim about it.

### 4.2 Choosing `clock_gettime` *against* the cheaper clock

The cycle counter is about half the cost per call. We chose `clock_gettime`
anyway, and the reasoning is the part of part 1 we care most about:

- Both clocks turn out to share the **same quantum** (~41 ns), because the
  kernel's clocksource *is* that register (`arch_sys_counter`) and the vDSO
  simply scales it. So the portable clock costs no resolution at all.
- On x86-64 the cycle counter would have to be **calibrated**, importing
  `CLOCK_MONOTONIC`'s error into every subsequent reading. A clock we can only
  trust on one of the two architectures the code compiles for is not a clock a
  result should rest on.
- `clock_gettime` guarantees monotonicity; a raw counter read does not.

So the trade is explicit: ~1.9× the call cost, bought with portability,
exactness, and monotonicity. Stating the trade *as* a trade is the point;
"we used `clock_gettime` because it is standard" would have been an assertion.

### 4.3 The resolution experiment, and the statistic that misleads

One million back-to-back reads into a **preallocated array**, post-processed
after the loop. Nothing is printed, computed, or allocated inside a timed
region — otherwise the experiment measures `printf`.

The experiment reports three things, and one of them is a trap we decided to
document rather than quietly drop: the **fraction of adjacent reads that are
identical** is *not* a coarseness measure. It is roughly `1 − (call cost /
quantum)`, i.e. it says how cheap a call is relative to one tick. `cntvct_el0`
and `gettimeofday` both score high, for opposite reasons — a fine quantum with
very cheap calls, versus a quantum 24× coarser — and only the second is
disqualifying. The generated clock table prints the measured fraction beside
the value the quantum predicts, so the two cases cannot be confused.

The two textbook cycle-counter caveats (frequency invariance, cross-core skew)
were **tested rather than repeated**: the `sleep(5)` experiment covers the
first, and reading the counter pinned to each core in turn covers the second.
Both came back clean on this hardware, which is a result, not an omission.

### 4.4 Latency as a halved round trip

Parent writes N bytes, child reads and returns a 1-byte ack, parent reads it.
One clock, one core, start to stop.

**Why a round trip:** a one-way measurement needs a clock reading taken in the
writer and another taken in the reader, and comparing them is a cross-core clock
comparison. Part 1 happens to show that the counter here *is* system-wide, so we
could have gotten away with it — but a technique that only works because of a
property of this particular timer is not a technique. The round trip keeps one
clock on one core.

**The cost, stated in the paper and in §7 below:** the two legs are asymmetric
(N bytes out, 1 byte back), so halving is an approximation that gets worse as N
grows. At 4 B it is fine. At 512 KiB the honest number to quote from that curve
is the *slope* (copy bandwidth), not the halved value.

**50 warm-up exchanges per size** before timing, so the first-touch page faults
and cold cache lines of a new payload buffer are not charged to the measurement.

### 4.5 Placement: `sched_setaffinity` after the fork, not `taskset`

`taskset` sets one allowed CPU mask that both processes inherit. It cannot
express "parent on core 0, child on core 1" — the exact contrast this project
is built on. So each process pins **itself** after the `fork`, and calls
`sched_yield()` immediately afterwards so that the migration happens *then*
rather than in the middle of the first measurement.

Three configurations, and the third is deliberate:

| Configuration | Role |
|---|---|
| `same` (0, 0) | One core, no parallelism available |
| `cross` (0, 1) | Two cores, wake-ups cross a core boundary |
| `unpinned` | **Control**: what a benchmark that ignores placement actually measures |

The unpinned arm exists to answer "does this matter in practice?" and it does:
unpinned tracks the cross-core curve, so a benchmark that does not control
placement is silently measuring the cross-core case.

### 4.6 Throughput is a different experiment, not latency with a bigger payload

In the latency benchmark the pipe is nearly always empty: the writer stops after
every message and waits. The round trip, not the pipe, sets the rate. So
throughput gets its own harness: the parent streams a fixed volume (~64 MiB) in
N-byte chunks with **no per-chunk acknowledgement**, and the child drains as
fast as it can.

One design detail matters for correctness: there is a **single 1-byte ack at the
very end**. Without it the parent would stop the clock when its last `write()`
returned into the kernel buffer — measuring how fast bytes can be *handed to the
kernel*, not how fast they can be *delivered*. With it, the clock stops when the
last byte has actually been consumed, and the single ack is negligible against
64 MiB.

**Chunk sizes:** the ten the assignment names, plus five extra clustered around
64 KiB (8 K, 32 K, 48 K, 80 K, 128 K). That is where the default capacity sits
and therefore where a knee, if any, was expected. Sampling densely where you
predict the interesting behaviour is how a sweep tests a prediction rather than
merely illustrating it.

**Syscall-count cap:** the target volume is capped at 200,000 writes, so a
4-byte chunk does not become a 16-million-syscall run. The consequence — the
smallest chunks move less than 64 MiB — is recorded in the data dictionary
rather than left for a reader to infer.

### 4.7 Statistics: minimum for a time, maximum for a rate, never a mean rate

Stated once and applied everywhere:

- **A time → the minimum.** Preemption, interrupt arrival, and migration can
  only *add* time. The minimum is the observation least contaminated by them.
- **A rate → the maximum.** Same rule seen through `1/x`.
- **Never the arithmetic mean of a rate.** Averaging rates is a documented
  benchmarking error (Smith's CACM note; Heiser's benchmarking-crimes list).
- **Two levels of reduction.** Each launch reports its own internal best, and
  the aggregation takes the best again across launches.

**Five independent launches, not five internal trials.** Internal trials share
one set of warm caches, one address-space layout, and one scheduling placement,
so they measure repeatability *within* a run and say nothing about run-to-run
variance. Separate launches expose it. The data then justified the choice
loudly: same-core minima reproduce within a few per cent between launches, while
cross-core minima spread by roughly a factor of two — and the means run about
five times the minima. Reporting means would have reported the contamination;
reporting one launch would have reported whichever contamination that launch
happened to draw.

The means are still written to the CSVs. The mean/minimum **gap** turned out to
be a result in its own right (§5.5), so discarding it would have thrown away
evidence.

### 4.8 Repetition counts chosen for the statistic being used

20,000 repetitions per payload up to 4 KiB, 5,000 to 64 KiB, 500 above. These
are tuned for how quickly the *minimum* converges, not for a tight error bar on
a mean we do not report — and they keep a full sweep to a few seconds, which is
what makes five independent launches affordable in the first place.

---

## 5. Design decisions in the argument

### 5.1 Hypothesis before data, including the ones that failed

Every part states its variables and a hypothesis before its data. Two of the
four hypotheses were wrong, and both are reported as wrong:

| Part | Hypothesis | Outcome |
|---|---|---|
| 1 | `clock_gettime` resolves a single exchange, `gettimeofday` does not | Confirmed |
| 2 | Flat, then linear in payload | Confirmed in shape; **missed** the constant offset between placements entirely |
| 3 | Rises, then falls once chunks exceed capacity | **Half wrong**: cross core falls, same core does not |
| 4 | The cross-core penalty is a scheduling cost | Confirmed |

The part 3 failure is the most useful thing in the project, and the write-up
treats it that way: the wrong prediction is what forced parts 4a and 4b to
exist.

### 5.2 Measuring the capacity instead of assuming it (4a)

The part 3 explanation is phrased in terms of "the capacity". Folklore says 16
pages. Folklore is a claim about a kernel, and we were about to build an
argument on it, so it gets measured: set the write end non-blocking, write until
`EAGAIN`, count the bytes, compare against `F_GETPIPE_SZ` and against
16 × page size.

Repeating the fill at six different **write sizes** was not padding. The kernel
accounts for a pipe in whole pages, and on some kernels a one-byte write is
given a page to itself, so the byte count comes in far under the nominal size.
Checking meant we could state "capacity is 64 KiB *for writes of any size on
this kernel*" instead of "capacity is 64 KiB".

### 5.3 Turning a correlation into a cause (4b)

Part 3 shows a collapse near the default capacity. That is a correlation
observed at *one* value of capacity, which is not evidence that capacity causes
it — the knee could belong to some other 64 KiB-ish threshold (a cache level,
a scheduler quantum, an allocator boundary).

So capacity becomes the **independent variable**: `F_SETPIPE_SZ` at 4 KiB,
16 KiB, 64 KiB, 256 KiB, 1 MiB, with a reduced sweep at each, and a falsifiable
prediction written down first — *if the knee follows the configured capacity,
capacity causes it; if the knee stays put while capacity moves, the part 3 story
is wrong and gets rewritten.* The knee followed.

Two implementation decisions matter here:

- `F_SETPIPE_SZ` rounds up to a page and a power of two. The value the kernel
  **actually adopted** is read back with `F_GETPIPE_SZ`, and that — never the
  requested value — is what gets recorded and plotted. A table of *requested*
  capacities would have been a table of things that did not happen.
- The sweep tops out at 1 MiB because that is the guest's
  `/proc/sys/fs/pipe-max-size`, so everything runs unprivileged. Raising the
  sysctl would have made the experiment depend on a machine modification a
  reader cannot see in the source.

### 5.4 Accounting for the time with the tools that exist (4c)

Tooling was checked on the guest *before* choosing an approach: no `perf` build
matches the custom 7.2.4 kernel, `/sys/kernel/debug/tracing` is unavailable, and
QEMU/hvf almost certainly does not virtualize a PMU. Hardware counters were
never an option.

What is available is `getrusage`, which is enough for the specific question.
Run a fixed number of round trips at one payload and one placement, then split
the wall clock three ways:

```
wall = user + system + (everything else)
```

That third term — time when *neither* process was running in user mode or in
the kernel — is the quantity of interest, because "descheduled, waiting for a
wake-up" is exactly what it means. `ru_nvcsw` and `ru_nivcsw` separate blocking
from preemption.

**`strace` runs are kept strictly separate.** `ptrace` stops both processes at
every syscall entry and exit, which inflates precisely the quantity being
measured, so a straced run's wall time is meaningless. Those runs are used for
syscall **counts and relative shares only**, and they live in a different file.
(This separation was learned the hard way — see §6.2.)

### 5.5 The argument the parts add up to

The design was chosen so that three independent lines of evidence have to agree
before the conclusion stands:

1. **Syscall counts** (`strace`): both placements issue identical calls — two
   writes and two reads per round trip at 4 B — and identical context switches.
   So the cross-core cost is not extra work.
2. **Time accounting** (`getrusage`): same core is ~100% accounted for as kernel
   time with a negligible residue; cross core has most of its wall clock in the
   residue. So the cost is time spent *not running*.
3. **Context switches vs capacity**: voluntary switches per round trip match
   `2 × ceil(payload / capacity)` against the *measured* capacity — 1.99 at 4 B,
   15.99 at 512 KiB — and `read()` counts show the same arithmetic from the
   syscall side (9 reads per round trip at 512 KiB: 8 for data, 1 for the ack).

And a fourth, which is why the means were kept: **the mean/minimum gap in part 2
is the same phenomenon seen through the statistics.** Same core, where the
residue is ~0%, has means within 1.03–1.10 of its minima; cross core, where the
residue is ~61%, has means around 5× its minima. Two entirely different
instruments, the same answer.

Hence the two-sentence conclusion: *capacity sets how many handoffs a transfer
needs; placement sets what each handoff costs.* Every clause is tied to a
measured number, and the last clause is the one part 4b established causally
rather than by correlation.

---

## 6. Process decisions, and the failures that caused them

Four of these are mistakes. They are documented because each one silently
produced *plausible-looking wrong data* — the failure mode that matters in
benchmarking, because nothing crashes and nothing looks odd.

### 6.1 Stale binaries, and why the build is now forced

`rsync -a` compares size and mtime and does not read `.gitignore`. Build
products committed by accident in an earlier session were copied over freshly
built binaries in the guest, and a **full 30-run matrix was collected with the
wrong code**. It looked entirely normal; the only giveaway was that the runs
wrote an old CSV filename.

**Process changes:** binaries removed from the repo, `sync.sh` excludes build
products explicitly, and `run_matrix.sh` runs `make -B` before collecting, so a
stale binary cannot survive into a measurement. The principle: *make the
mistake structurally impossible rather than remembering not to make it.*

A companion failure: `sync.sh` originally passed `rsync --delete-excluded` while
excluding `results/`, which deletes excluded paths **on the destination** and
wiped the guest's results mid-session. The flag is gone, with a comment saying
why, because the next person to "clean up" that command needs to know.

### 6.2 Contaminated CSV rows, and why straced runs are quarantined

`pipe_profile.c` opens its CSV in append mode so four separate invocations
accumulate into one table. The `strace` runs appended to the same file, so the
aggregated table silently contained ptrace-inflated rows — 9 context switches
per round trip instead of 2, wall times ~50× too large. The rows were not
obviously wrong in isolation.

**Process change:** the CSV is deleted and regenerated from clean runs only, and
the straced output is kept in a separate raw file used only for counts.
Append mode is convenient and it is a sharp edge; the log says so.

### 6.3 Hand-typed numbers, and the generation pipeline

Table 1 and several prose figures were typed by hand from the first `timer-test`
run. Part 1 was later re-run and the CSV regenerated — but the paper was not.
The paper went on quoting a 35.3 ns call cost and a 19.83% zero fraction while
the committed data said 20.2 ns and 53.7%. Both runs were internally consistent,
so **nothing looked wrong**; the paper simply described a dataset that no longer
existed.

**Process change, and the one with the widest reach:** the fix was structural,
not retyping.

- Tables are generated from the CSVs by `scripts/aggregate.py`.
- `figures/numbers.tex` holds a LaTeX macro for **every figure the prose
  quotes**, so re-running a benchmark updates the *sentences*, not just the
  tables.
- `EXPERIMENTS.txt` reads the same macro file, so the log cannot drift from the
  paper either.
- The log generator runs the aggregator itself, first, so the two cannot be
  generated from different states.

The rule this enforces: **a number exists in exactly one place, and everything
else points at it.**

### 6.4 Two datasets that legitimately differ

The `strace`/profile and the capacity-resize stdout in `results/raw/` come from
*different executions* than the committed CSVs for those two parts (the runs
were repeated; only one form of each was captured at each point). Rather than
delete one or quietly reconcile them, both are kept and the log says which feeds
the paper. The agreement between two independent executions is itself evidence,
and for the cross-core resize sweep the *disagreement* (tens of per cent, cell
by cell) is an honest warning about how noisy that particular dataset is — which
is why it is used for the position of the knee and never for an absolute rate.

### 6.5 Figure design

Two palettes, chosen for what the variable *is*:

- Figures 1–2 are **categorical** — the identity of a series is which placement
  it used — so they take distinguishable hues.
- Figure 3b is **ordinal** — capacity is an ordered magnitude — so it takes a
  single-hue ramp stepped light to dark. The first draft let pgfplots cycle its
  default colours; with five curves the cycle repeated and drew the 4 KiB and
  1 MiB capacities, *the two extremes of the comparison*, in the same blue.

Marks differ per series in both cases, so identity never rests on colour alone,
and both palettes were checked with a colour-vision validator rather than by
eye.

Plots are drawn by pgfplots directly from committed `.dat` files, so a clean
checkout needs only a TeX installation — no plotting library, no Python at build
time. `scripts/` is standard-library-only for the same reason.

### 6.6 Fitting two pages

The assignment asks for two pages, and the full data tables did not fit. What
was cut and what was kept was decided by information density:

- The clock comparison became a bar chart of the two quantities the decision
  actually turns on (call cost and quantum) instead of a five-column table.
- The two full data tables became one transposed table at the ten required
  sizes, spanning both columns.
- The same-core resize panel was dropped from the figure, because its content is
  "no knee", which is one sentence of text.

Nothing cut was deleted: `aggregate.py` still emits all of it, and
`EXPERIMENTS.txt` carries the fuller form, including every launch individually.

---

## 7. Known limitations

Stated in full in `EXPERIMENTS.txt` §15; summarized here because a methodology
document that omits its own weaknesses is advertising.

1. **Virtualized guest.** Absolute latencies carry hypervisor overhead, and the
   cross-core penalty in particular may be inflated by virtual IPI cost. Only
   comparisons within one machine are claimed.
2. **One machine, one kernel.** Nothing here establishes generality across
   microarchitectures.
3. **Asymmetric ack.** "Half a round trip" is a convention that weakens as the
   payload grows; at large payloads the slope-derived copy bandwidth is the
   trustworthy number.
4. **`getrusage` granularity.** User+system can exceed wall by a fraction of a
   per cent (tick accounting vs `clock_gettime`), which is why the same-core
   residue is slightly negative. Under 1%, against a cross-core residue of
   ~61%, so nothing rests on it — but the table clamps it and says so.
5. **The unpinned anomaly.** Above 256 KiB, unpinned is worse than *either*
   fixed placement, and we do not have an explanation. Reported, not dropped.
6. **No hardware counters.** The residue is identified as wake-up cost by
   inference from the placement variable, not by direct measurement. A PMU or
   an `ftrace` `sched_wakeup` histogram would close that gap.
7. **Single writer, single reader, idle machine.** Nothing here speaks to
   contention — and contention is exactly what would change the scheduler
   behaviour that dominates the cross-core case.

---

## 8. What we would do next

- **Measure the wake-up path directly** rather than by subtraction, on a host
  where `perf` or `ftrace` is available. That converts the paper's central
  inference into a measurement.
- **Repeat on bare metal and on x86-64.** `Timer.h` already compiles for both;
  the calibration path on x86-64 would itself be worth reporting.
- **Explain the unpinned anomaly**, most likely by logging which CPU each
  process is on during a large transfer.
- **Add contention** — several pipe pairs at once — which is the case every real
  system is actually in.

---

## 9. Where everything lives

```
Timer.h              three clock sources behind one interface
timer_test.c         part 1   -> clock_precision.csv
pipe_latency.c       part 2   -> pipe_latency_<placement>-r<n>.csv
pipe_throughput.c    part 3   -> pipe_throughput_<placement>-r<n>.csv
pipe_capacity.c      part 4a  -> pipe_capacity.csv
pipe_resize.c        part 4b  -> pipe_resize_<placement>.csv
pipe_profile.c       part 4c  -> pipe_profile.csv
run_matrix.sh        the placement x launch matrix, one invocation
sync.sh              host -> guest source push (excludes build products)
scripts/aggregate.py         CSVs -> figures, tables, prose macros
scripts/make_experiment_log.py  everything -> EXPERIMENTS.txt
```

Chain of custody for any number in the paper:

```
benchmark -> results/raw/*.txt -> results/csv/*.csv -> scripts/aggregate.py
          -> report/figures/{*.dat, *_table.tex, numbers.tex} -> report/main.tex
```

Nothing in that chain is edited by hand. To reproduce from a clean checkout, see
`EXPERIMENTS.txt` §3; to check any individual number, see its raw output in
`EXPERIMENTS.txt` §7–§13 or its checksum in §17.
