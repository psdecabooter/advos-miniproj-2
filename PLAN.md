# Mini-Project 2 Execution Plan

Plan for re-running the full IPC-through-pipes evaluation on a single machine,
plus the code additions needed to close out part 4. Written to be handed to
Claude Code as the working brief.

## 0. Context

Course is COMP SCI 736, Advanced OS. The deliverable is a two column LaTeX
report, `report/main.tex`, titled "Evaluation of IPC through Linux Pipes",
authored by Patrick DeCabooter and Shaw Liu.

Four parts are required.

1. Pick a clock, justified by two experiments run against both candidates.
2. Measure pipe latency across payload sizes.
3. Measure pipe throughput across chunk sizes.
4. Infer the underlying mechanism from the data.

Current repo state, on branch `benchmarks`.

- `Timer.h` wraps `clock_gettime(CLOCK_MONOTONIC)` and `gettimeofday`.
- `timer_test.c` implements part 1. Works, but the resolution experiment is
  weak and is revised in step 3 below.
- `pipe_latency.c` implements part 2. Rewritten, accumulator bug fixed.
- `pipe_throughput.c` implements part 3. New.
- `Makefile` has build targets and `run-*` targets. `make clean` removes
  binaries and CSVs.
- `report/main.tex` is a section skeleton with no content.

All prior numbers in the repo came from Patrick's x86-64 WSL2 machine and from
the buggy latency code. Discard them. Everything gets re-run.

## 1. Where this runs

Everything runs inside **kernel-vm**, not on macOS. macOS pipes are XNU and
behave differently, and the report is about Linux pipes.

- Host is an M1 MacBook, user `leo`. QEMU with hvf.
- Guest is Ubuntu 24.04 arm64 minimal, hostname `kernel-vm`, user `shawliu`,
  8 vCPUs, 12 GB RAM, ext4 root.
- Guest runs a custom Linux 7.2.4 build, arm64 defconfig, carrying the ext4
  fsync counter patch from Mini-Project 1. Stock 6.8.0 is the GRUB fallback.
- Reach it with `ssh -p 2222 shawliu@localhost`, key only, passwordless sudo.
- Shut down with `sudo shutdown -h now`.

Claude Code runs on the macOS host, so every benchmark command must be issued
over that SSH connection. Do not run the benchmarks on the host itself.

Get the repo into the guest by syncing from the host rather than cloning,
since the guest may not have GitHub credentials.

```
rsync -av --exclude '.git' -e 'ssh -p 2222' \
  "/Users/leo/Documents/COMP SCI 736/Projects/advos-miniproj-2/" \
  shawliu@localhost:~/advos-miniproj-2/
```

Results come back the same way, in reverse, and get committed on the host.

## 2. Preflight inside the guest

Record all of this into `shaw-computer-specs.txt`, mirroring the format of the
existing `partick-computer-specs.txt` so the report can cite both machines.

- `uname -a`, `lsb_release -a`, `gcc --version`, `nproc`.
- `getconf PAGESIZE`. This is load bearing. Linux pipe capacity is 16 pages,
  so 64 KiB at 4 KiB pages. If this kernel was built with 16 KiB or 64 KiB
  pages, the capacity and therefore the throughput knee move, and part 4 has
  to account for it.
- `cat /proc/sys/fs/pipe-max-size` and `/proc/sys/fs/pipe-user-pages-soft`.
- CPU model from `/proc/cpuinfo`, plus a note that this is a QEMU hvf guest,
  which is a caveat the report must state rather than hide.

Install `build-essential` if `gcc` is missing. Confirm both benchmarks build
clean with `-Wall -Wextra` before collecting anything.

Keep the machine quiet during runs. No editors, no builds, no other SSH
sessions doing work.

## 3. Part 1, clock selection

The existing resolution experiment averages 25 tight loop reads with a filler
add. That is too few samples and the filler pollutes the measurement. Revise
`timer_test.c` as follows.

**Experiment A, accuracy against a known interval.** Keep the existing design.
Time `sleep(5)` five times with each clock and report the mean. This shows
both clocks track wall time correctly.

**Experiment B, resolution and call cost.** Replace the 25 iteration loop.
Take 1,000,000 back to back readings of each clock into a preallocated array,
then post process. Report three things. The mean cost of one call, computed as
total elapsed divided by sample count. The smallest nonzero delta observed
between consecutive readings, which is the effective resolution. The fraction
of consecutive deltas that are exactly zero, which is the quantization rate.

Do not time anything inside the loop other than the clock call itself, and do
not print from inside the loop.

Expected shape of the result. `clock_gettime` resolves to tens of nanoseconds
with a near zero quantization rate. `gettimeofday` reports a 1 microsecond
resolution with a large fraction of zero deltas, because consecutive calls
complete inside one microsecond tick. That zero fraction is the argument for
choosing `clock_gettime`, and it should be stated as a number in the report,
not asserted.

**Experiment C, the cycle counter.** The assignment asks for `rdtsc` or its
analogue as the first thing to figure out. This is arm64, so there is no
`rdtsc`. The analogue is the generic timer virtual count register, read with
`mrs %0, cntvct_el0`, scaled by the frequency in `cntfrq_el0`. Both are
readable from userspace on Linux arm64. Add it to `Timer.h` as a third source
and run it through Experiments A and B unchanged, so all three clocks are
compared on the same footing.

Expect `cntfrq_el0` to report 24 MHz on Apple silicon, which is a 41.7 ns
period. If that holds, the cycle counter is *coarser* than `clock_gettime`,
which inverts the usual x86 intuition and is a finding worth stating rather
than burying. Report the measured `cntfrq_el0` value, do not assume it.

The assignment's two caveats about cycle counters, variable clock speed and
per core counter skew, are testable here rather than merely repeated. Read
`cntvct_el0` pinned to core 0 and to core 1 and report the offset. On arm64
the generic timer is architecturally system wide, so expect no skew, which is
the opposite of the x86 warning and ties directly into the same core versus
cross core latency configs in step 4.

Write results to `clock_precision.csv`.

## 4. Part 2, latency

Code is ready. Run it, but add one variable that matters for the analysis.

Run the latency benchmark three ways and keep all three datasets.

1. Unpinned, the default, both processes scheduled freely.
2. Both processes pinned to the same core, `taskset -c 0`.
3. Pinned to different cores, parent on 0 and child on 1.

Same core versus cross core separates the cost of the wakeup and the cross CPU
cache traffic from the copy cost itself, and it is one of the cleanest pieces
of evidence available for part 4. Implementing this cleanly means adding an
optional CLI argument to `pipe_latency.c` for the child's CPU, using
`sched_setaffinity` after the fork, or wrapping invocations with `taskset`
and accepting that both processes land on the same allowed set.

Collect at least 5 independent runs of each configuration, not just the 5
trials inside one process, so run to run variance is visible.

Report min first, mean second. The assignment states twice that the minimum
is the right summary here, and it is the least contaminated by scheduling
noise. The report leads with min and carries mean only to show the size of the
noise tail. Say so explicitly.

Never take an arithmetic mean of a throughput figure. Rates need the harmonic
mean, which is the point of the Smith paper the assignment cites and is item
one on Heiser's benchmarking crimes list that it also links.

Output goes to `pipe_latency.csv`, one file per configuration, suffixed.

## 5. Part 3, throughput

Code is ready. Run it the same three affinity ways, 5 independent runs each.

Output goes to `pipe_throughput.csv`, suffixed per configuration.

Watch for one thing. On the smoke test the curve peaked around half the pipe
capacity and fell off sharply at and beyond capacity. Confirm that shape
reproduces here. If it does not, that itself is the finding and part 4 has to
explain the difference, most likely through page size.

## 6. Part 4, mechanism

This is analysis plus two small targeted experiments. Both need new code.

### 6a. Measure pipe capacity directly, `pipe_capacity.c`

Set the read end nonblocking, write single bytes into the pipe until `write`
returns `EAGAIN`, and count. That number is the pipe capacity, measured rather
than assumed. Compare it against 16 times `getconf PAGESIZE` and against
`fcntl(fd, F_GETPIPE_SZ)`.

Also report whether the capacity reported by `F_GETPIPE_SZ` matches what the
byte counting finds, since the kernel accounts in whole pages.

### 6b. Move the knee on purpose, `pipe_resize.c`

Use `fcntl(fd, F_SETPIPE_SZ, n)` to set capacity to 4 KiB, 16 KiB, 64 KiB,
256 KiB and 1 MiB, and re-run a reduced throughput sweep at each. If the knee
in the throughput curve tracks the configured capacity, the causal claim is
established rather than inferred from a single correlation. This is the
strongest result available in this project and it is cheap to produce.

Note that `F_SETPIPE_SZ` above `/proc/sys/fs/pipe-max-size` needs privilege,
so either stay under that ceiling or raise it with sudo and say so.

Output goes to `pipe_capacity.csv` and `pipe_resize.csv`.

### 6c. Where the time actually goes, profiling

Parts 6a and 6b are black box. They establish causality for the throughput
knee, but the assignment explicitly asks for perf, strace or ftrace and for a
chart or table attributing time to the test program, to parts of the kernel,
and to context switches. That table is the deliverable here.

Tooling constraint, already checked on the guest. `perf` and `strace` are not
installed, the ftrace `tracing/` directory is not available, and `linux-tools`
is packaged only for 6.8.0, so no distro `perf` matches the custom 7.2.4
kernel. Decision: stay on 7.2.4 and use software events only. All benchmark
and profiling data then comes from one kernel, with no cross kernel caveat.

- `apt install strace`. Run `strace -c -f` on latency and throughput at a small
  and a large size, to get syscall counts and time per syscall. Confirm the
  syscall count per exchange is exactly what the code implies, two `write` and
  two `read` per round trip. A mismatch means short reads, which is itself a
  finding.
- `strace -T -f` on a short run for the per call time distribution.
- For `perf`, software events do not need a PMU, which matters because QEMU
  with hvf almost certainly does not virtualize one. `perf stat -e
  context-switches,task-clock,page-faults` is the useful subset. If no usable
  `perf` binary can be obtained for 7.2.4, fall back to reading
  `voluntary_ctxt_switches` and `nonvoluntary_ctxt_switches` from
  `/proc/<pid>/status` before and after each run, which needs no tooling at
  all and answers the same question.
- Cross check against `getrusage(RUSAGE_SELF)` and `RUSAGE_CHILDREN` for user
  versus system time split, which is free to add to both benchmarks.

The target artifact is one table with a row per component, user time, system
time, context switches, and per syscall cost, at a small payload where fixed
cost dominates and a large one where copy cost dominates. Output to
`profile.csv`.

Do not claim a PMU derived number if no PMU is present. State the limitation.

### 6d. The argument the report has to make

Assemble the evidence into a single mechanism story, with each claim tied to a
specific measured number.

- The flat latency region at small payloads gives the fixed cost per exchange,
  which is two syscalls plus a wakeup, and it should roughly match the clock
  call cost plus scheduling overhead from part 1 and the same core versus
  cross core delta.
- Latency growing linearly with payload past some size gives the per byte copy
  cost. Fit a line and report the implied copy bandwidth.
- Throughput rising with chunk size is amortization of the fixed per write
  cost over more bytes. The `mean ns/write` column makes this explicit.
- Throughput peaking below capacity and collapsing at or above it is the
  writer blocking once the buffer fills, which serializes writer and reader
  instead of letting them overlap.
- The resize experiment in 6b shows the collapse point follows the configured
  capacity, which closes the argument.

## 7. Data handling

- Every run writes CSV. Never rely on numbers pasted into code comments, which
  is how the previous data was lost.
- Keep raw stdout too, `./run-x | tee results/raw/<config>-<timestamp>.txt`.
- Create a `results/` directory in the repo, committed. It is currently
  gitignored by the `*.csv` rule, so narrow that rule to the repo root rather
  than removing it.
- Plot with matplotlib into `report/figures/`, PDF output for LaTeX. Latency
  against payload size on log x. Throughput against chunk size on log x with a
  vertical marker at measured capacity. One figure for the resize experiment
  showing several curves, one per configured capacity.

## 8. Report

Fill `report/main.tex` section by section. Each results subsection needs at
least one figure and a quantitative claim, not prose alone. State the QEMU hvf
virtualization caveat in the introduction.

**Two pages is a hard limit**, two column, 11 point, 1 inch margins. That is
roughly 1300 words and four figures, total. The budget is fixed in advance so
that content gets cut deliberately rather than by whatever runs out of room
last.

- Figure 1, clock resolution and call cost, three clocks.
- Figure 2, latency against payload size, log x, three affinity configs.
- Figure 3, throughput against chunk size, log x, vertical marker at measured
  capacity.
- Figure 4, the resize sweep, one curve per configured capacity.
- Table 1, the time breakdown from 6c. Compact, it competes with prose.

**Patrick's WSL2 x86-64 dataset is cut.** A cross platform subsection cannot
be fit alongside the resize experiment and the profiling table, and those two
carry the mechanism argument. Do not reintroduce it without cutting something
named above.

The rubric grades structure against the experimental method, so variables,
hypothesis, apparatus, results and conclusions each have to be visible. The
current skeleton has Design and Results subsections only, with no hypothesis
stated anywhere and no apparatus section. Add both. A hypothesis per part,
one sentence, stated in terms of the experimental variables and written before
the numbers are discussed.

## 9. Git

Work on branch `benchmarks`, off `ab97d90`. `master` currently matches
`origin/master` and should stay that way until this is ready to merge.
Commit code changes and results separately. Push with
`git push -u origin benchmarks` when the suite is green.

## 10. Done criteria

- `shaw-computer-specs.txt` exists and records page size and pipe max size.
- All four parts have committed CSV data from kernel-vm.
- Latency and throughput each have unpinned, same core and cross core data.
- Measured pipe capacity is reported, and the resize experiment shows the
  throughput knee following the configured capacity.
- Every figure in the report is generated from a committed CSV by a committed
  script, reproducible from a clean checkout.
