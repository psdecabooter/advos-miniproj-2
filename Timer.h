// Timer struct for mini-project 2
//
// Three timer modes:
//  - TimerCGT  (clock_gettime)
//  - TimerGTOD (gettimeofday)
//  - TimerCC   (the hardware cycle counter)
//
// The cycle counter is the assignment's "rdtsc or its analogue".  On x86-64
// that is rdtsc.  This machine is arm64, where the analogue is the generic
// timer's virtual count register cntvct_el0, scaled by the fixed frequency in
// cntfrq_el0.  Both registers are readable from userspace under Linux.
//
// Note the asymmetry between the two architectures.  rdtsc counts at
// something near the core clock and has to be calibrated against a known
// clock, and it is the register the assignment's caveats about frequency
// scaling and per-core skew are written about.  cntvct_el0 instead counts at
// a fixed, architecturally system-wide rate that the hardware reports to us,
// so it needs no calibration and is immune to both caveats -- but it is
// correspondingly coarse.  Which of those two properties matters more is an
// empirical question, which is what timer_test.c answers.

#ifndef MP2_TIMER
#define MP2_TIMER

// Headers
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

typedef struct TimerCGT {
  struct timespec start_time;
} TimerCGT;

static inline void startTimerCGT(TimerCGT *timer) {
  if (clock_gettime(CLOCK_MONOTONIC, &timer->start_time) != 0) {
    perror("clock_gettime");
    exit(1);
  }
}

static inline long long int getTimerCGTNano(const TimerCGT *timer) {
  struct timespec end_time;
  if (clock_gettime(CLOCK_MONOTONIC, &end_time) != 0) {
    perror("clock_gettime");
    exit(1);
  }
  return 1000000000 * (end_time.tv_sec - timer->start_time.tv_sec) +
         end_time.tv_nsec - timer->start_time.tv_nsec;
}

typedef struct TimerGTOD {
  struct timeval start_time;
} TimerGTOD;

static inline void startTimerGTOD(TimerGTOD *timer) {
  if (gettimeofday(&timer->start_time, NULL) != 0) {
    perror("gettimeofday");
    exit(1);
  }
}

static inline long long int getTimerGTODMicro(const TimerGTOD *timer) {
  struct timeval end_time;
  if (gettimeofday(&end_time, NULL) != 0) {
    perror("gettimeofday");
    exit(1);
  }
  return 1000000 * (end_time.tv_sec - timer->start_time.tv_sec) +
         (end_time.tv_usec - timer->start_time.tv_usec);
}

/* ---------------------------------------------------------------------- */
/* Cycle counter.                                                          */

#if defined(__aarch64__)
#define CC_NAME "cntvct_el0"

static inline uint64_t readCycleCounter(void) {
  uint64_t v;
  /* isb orders the read against surrounding instructions.  Without it the
     counter read can be hoisted or sunk across the code being timed, which
     is exactly the mistake the rdtsc literature warns about. */
  __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(v)::"memory");
  return v;
}

/* Reported by the hardware, so no calibration loop is needed. */
static inline uint64_t cycleCounterHz(void) {
  uint64_t f;
  __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(f));
  return f;
}

#define CC_FREQ_IS_MEASURED 0

#elif defined(__x86_64__)
#include <x86intrin.h>
#define CC_NAME "rdtsc"

static inline uint64_t readCycleCounter(void) {
  unsigned int aux;
  return __rdtscp(&aux); /* rdtscp is ordered; plain rdtsc is not */
}

/* x86 does not tell us the tsc rate, so calibrate against CLOCK_MONOTONIC.
   This is the step arm64 gets for free, and it is a source of error that
   cntfrq_el0 simply does not have. */
static inline uint64_t cycleCounterHz(void) {
  struct timespec t0, t1;
  uint64_t c0, c1;
  clock_gettime(CLOCK_MONOTONIC, &t0);
  c0 = readCycleCounter();
  usleep(100000); /* 100 ms */
  c1 = readCycleCounter();
  clock_gettime(CLOCK_MONOTONIC, &t1);
  {
    double ns = 1e9 * (double)(t1.tv_sec - t0.tv_sec) +
                (double)(t1.tv_nsec - t0.tv_nsec);
    return (uint64_t)((double)(c1 - c0) * 1e9 / ns);
  }
}

#define CC_FREQ_IS_MEASURED 1

#else
#error "no cycle counter available for this architecture"
#endif

typedef struct TimerCC {
  uint64_t start_ticks;
} TimerCC;

static inline void startTimerCC(TimerCC *timer) {
  timer->start_ticks = readCycleCounter();
}

static inline uint64_t getTimerCCTicks(const TimerCC *timer) {
  return readCycleCounter() - timer->start_ticks;
}

/* Ticks are only meaningful once scaled, and the scale factor is looked up
   once by the caller rather than per call. */
static inline double ticksToNano(uint64_t ticks, uint64_t hz) {
  return (double)ticks * 1e9 / (double)hz;
}

#endif