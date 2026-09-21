/*
  Part 1, clock selection.   Run "make timer-test".

  Three candidate clocks are compared: clock_gettime(CLOCK_MONOTONIC),
  gettimeofday, and the hardware cycle counter (cntvct_el0 on arm64, rdtsc on
  x86-64).  Three experiments.

    A. Accuracy.  Time a known interval, sleep(5), with each clock.  A clock
       that cannot recover a known interval is unusable regardless of how fine
       its resolution claims to be.

    B. Resolution and call cost.  Take a large number of back-to-back readings
       into a preallocated array and post-process.  Reports the mean cost of a
       single call, the smallest nonzero delta between consecutive readings
       (the effective resolution), and the fraction of consecutive deltas that
       are exactly zero (the quantization rate).  A high zero fraction means
       the clock cannot distinguish two events as far apart as one of its own
       calls, which is disqualifying for measuring anything at that scale.

    C. Cycle counter caveats.  The assignment warns that a cycle counter may
       not track real time under frequency scaling, and may not be comparable
       across cores.  Both are tested rather than assumed: A already covers
       the first, and C pins to each CPU in turn and reports the offset.

  Nothing is printed or computed inside a timing loop.

  Results are written to clock_precision.csv.
*/
#define _GNU_SOURCE
#include "Timer.h"
#include <sched.h>
#include <string.h>
#include <unistd.h>

#define SLEEP_SECONDS 5
#define SLEEP_TRIALS 5
#define NSAMPLES 1000000

static FILE *csv;

/* ---------------------------------------------------------------- */
/* Experiment A: recover a known interval.                           */

static void experiment_a(uint64_t cc_hz) {
  double cgt_sum = 0, gtod_sum = 0, cc_sum = 0;

  printf("Experiment A: recovering a known interval, sleep(%d) x %d\n\n",
         SLEEP_SECONDS, SLEEP_TRIALS);

  for (int i = 0; i < SLEEP_TRIALS; ++i) {
    TimerCGT cgt;
    TimerGTOD gtod;
    TimerCC cc;

    /* All three clocks time the same sleep, so they see identical intervals
       and any disagreement is the clocks' and not the interval's. */
    startTimerCGT(&cgt);
    startTimerGTOD(&gtod);
    startTimerCC(&cc);
    sleep(SLEEP_SECONDS);
    cc_sum += ticksToNano(getTimerCCTicks(&cc), cc_hz) / 1e9;
    gtod_sum += (double)getTimerGTODMicro(&gtod) / 1e6;
    cgt_sum += (double)getTimerCGTNano(&cgt) / 1e9;
  }

  double cgt = cgt_sum / SLEEP_TRIALS;
  double gtod = gtod_sum / SLEEP_TRIALS;
  double cc = cc_sum / SLEEP_TRIALS;
  double target = (double)SLEEP_SECONDS;

  printf("  %-16s %14s %14s\n", "clock", "mean (s)", "error (ppm)");
  printf("  %-16s %14.6f %14.1f\n", "clock_gettime", cgt,
         1e6 * (cgt - target) / target);
  printf("  %-16s %14.6f %14.1f\n", "gettimeofday", gtod,
         1e6 * (gtod - target) / target);
  printf("  %-16s %14.6f %14.1f\n", CC_NAME, cc,
         1e6 * (cc - target) / target);
  printf("\n");

  fprintf(csv, "accuracy,clock_gettime,mean_seconds,%.9f\n", cgt);
  fprintf(csv, "accuracy,gettimeofday,mean_seconds,%.9f\n", gtod);
  fprintf(csv, "accuracy,%s,mean_seconds,%.9f\n", CC_NAME, cc);
  fprintf(csv, "accuracy,clock_gettime,error_ppm,%.3f\n",
          1e6 * (cgt - target) / target);
  fprintf(csv, "accuracy,gettimeofday,error_ppm,%.3f\n",
          1e6 * (gtod - target) / target);
  fprintf(csv, "accuracy,%s,error_ppm,%.3f\n", CC_NAME,
          1e6 * (cc - target) / target);
}

/* ---------------------------------------------------------------- */
/* Experiment B: resolution and call cost.                           */

/* Post-process one sample array.  Deltas are in the array's native unit;
   unit_ns converts one unit to nanoseconds. */
static void summarize(const char *name, const long long *v, int n,
                      double unit_ns) {
  long long smallest_nonzero = -1;
  long long zero_deltas = 0;
  long long backward = 0;

  for (int i = 1; i < n; ++i) {
    long long d = v[i] - v[i - 1];
    if (d == 0) {
      ++zero_deltas;
    } else if (d < 0) {
      ++backward; /* must never happen on a monotonic source */
    } else if (smallest_nonzero < 0 || d < smallest_nonzero) {
      smallest_nonzero = d;
    }
  }

  /* Total span divided by the number of calls is the mean cost of one call:
     the loop did nothing else. */
  double span_ns = (double)(v[n - 1] - v[0]) * unit_ns;
  double call_ns = span_ns / (double)(n - 1);
  double res_ns = smallest_nonzero < 0 ? 0.0 : (double)smallest_nonzero * unit_ns;
  double zero_frac = (double)zero_deltas / (double)(n - 1);

  printf("  %-16s %12.2f %12.2f %12.4f %10lld\n", name, call_ns, res_ns,
         zero_frac, backward);

  fprintf(csv, "resolution,%s,mean_call_ns,%.4f\n", name, call_ns);
  fprintf(csv, "resolution,%s,smallest_nonzero_delta_ns,%.4f\n", name, res_ns);
  fprintf(csv, "resolution,%s,zero_delta_fraction,%.6f\n", name, zero_frac);
  fprintf(csv, "resolution,%s,backward_deltas,%lld\n", name, backward);
  fprintf(csv, "resolution,%s,samples,%d\n", name, n);
}

static void experiment_b(uint64_t cc_hz) {
  long long *v = malloc((size_t)NSAMPLES * sizeof(long long));
  if (!v) {
    perror("malloc");
    exit(1);
  }

  printf("Experiment B: resolution and call cost, %d back-to-back readings\n",
         NSAMPLES);
  printf("  (zero fraction is the share of consecutive reads the clock could "
         "not tell apart)\n\n");
  printf("  %-16s %12s %12s %12s %10s\n", "clock", "call (ns)", "res (ns)",
         "zero frac", "backward");

  /* Touch every page first so that page faults land outside the timed loop. */
  memset(v, 0, (size_t)NSAMPLES * sizeof(long long));

  for (int i = 0; i < NSAMPLES; ++i) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    v[i] = 1000000000LL * ts.tv_sec + ts.tv_nsec;
  }
  summarize("clock_gettime", v, NSAMPLES, 1.0);

  for (int i = 0; i < NSAMPLES; ++i) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    v[i] = 1000000LL * tv.tv_sec + tv.tv_usec;
  }
  summarize("gettimeofday", v, NSAMPLES, 1000.0);

  for (int i = 0; i < NSAMPLES; ++i)
    v[i] = (long long)readCycleCounter();
  summarize(CC_NAME, v, NSAMPLES, 1e9 / (double)cc_hz);

  printf("\n");
  free(v);
}

/* ---------------------------------------------------------------- */
/* Experiment C: cycle counter cross-core consistency.               */

static int pin_to(int cpu) {
  cpu_set_t set;
  CPU_ZERO(&set);
  CPU_SET(cpu, &set);
  return sched_setaffinity(0, sizeof(set), &set);
}

static void experiment_c(uint64_t cc_hz) {
  int ncpu = (int)sysconf(_SC_NPROCESSORS_ONLN);
  if (ncpu > 8)
    ncpu = 8;

  printf("Experiment C: %s consistency across cores\n", CC_NAME);
  printf("  cntfrq/calibrated rate: %llu Hz, period %.3f ns, %s\n\n",
         (unsigned long long)cc_hz, 1e9 / (double)cc_hz,
         CC_FREQ_IS_MEASURED ? "calibrated against CLOCK_MONOTONIC"
                             : "reported by hardware");
  printf("  %-8s %22s %16s\n", "cpu", "counter vs monotonic", "skew (ns)");

  /* Read the cycle counter and CLOCK_MONOTONIC together on each CPU in turn.
     If the counter were per-core, the offset between the two would jump from
     one core to the next.  CLOCK_MONOTONIC is the shared reference. */
  double base = 0;
  for (int c = 0; c < ncpu; ++c) {
    if (pin_to(c) != 0) {
      perror("sched_setaffinity");
      continue;
    }
    sched_yield(); /* make sure the migration has happened */

    struct timespec ts;
    uint64_t ticks = readCycleCounter();
    clock_gettime(CLOCK_MONOTONIC, &ts);

    double cc_ns = ticksToNano(ticks, cc_hz);
    double mono_ns = 1e9 * (double)ts.tv_sec + (double)ts.tv_nsec;
    double offset = cc_ns - mono_ns;

    if (c == 0)
      base = offset;
    printf("  %-8d %22.0f %16.1f\n", c, offset, offset - base);
    fprintf(csv, "cross_core,%s,cpu%d_skew_ns,%.1f\n", CC_NAME, c,
            offset - base);
  }

  /* Restore an unrestricted mask so nothing later inherits the pinning. */
  cpu_set_t all;
  CPU_ZERO(&all);
  for (int c = 0; c < ncpu; ++c)
    CPU_SET(c, &all);
  sched_setaffinity(0, sizeof(all), &all);

  fprintf(csv, "cross_core,%s,frequency_hz,%llu\n", CC_NAME,
          (unsigned long long)cc_hz);
  fprintf(csv, "cross_core,%s,period_ns,%.4f\n", CC_NAME, 1e9 / (double)cc_hz);
  printf("\n");
}

/* ---------------------------------------------------------------- */

int main(void) {
  uint64_t cc_hz = cycleCounterHz();

  csv = fopen("clock_precision.csv", "w");
  if (!csv) {
    perror("fopen clock_precision.csv");
    return 1;
  }
  fprintf(csv, "experiment,clock,metric,value\n");

  printf("Clock selection, part 1.  Cycle counter is %s at %llu Hz.\n\n",
         CC_NAME, (unsigned long long)cc_hz);

  experiment_b(cc_hz); /* cheap, run first */
  experiment_c(cc_hz);
  experiment_a(cc_hz); /* 25 seconds of sleeping, run last */

  fclose(csv);
  printf("Wrote clock_precision.csv\n");
  return 0;
}
