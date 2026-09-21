// Timer struct for mini-project 2
//
// Two timer modes:
//  - TimerCGT  (clock_gettime)
//  - TimerGTOD (gettimeofday)

#ifndef MP2_TIMER
#define MP2_TIMER

// Headers
#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>
#include <time.h>

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

#endif