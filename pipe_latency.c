/*
  Pipe latency benchmark for mini-project 2.

  Build and run:  make latency-test && ./latency-test

  Design:
    Parent and child are joined by two pipes.  The parent writes a payload of
    N bytes into p2c and then blocks reading a 1 byte ack out of c2p.  The
    elapsed time for that exchange is one round trip; one way latency is taken
    as half of it.

    The ack is only 1 byte, so the two legs of the round trip are not
    symmetric for large payloads.  Halving is still the conventional estimate,
    but the report should say so explicitly.

    Every payload size is measured with both clocks so that part 1's choice of
    clock can be justified against real data.  gettimeofday resolves only to a
    microsecond, so for the small payloads its per round trip samples quantize
    hard and its reported minimum is often 0.  That is a result, not a bug.

  Output:
    A readable table on stdout, plus pipe_latency.csv for plotting.
*/
#define _GNU_SOURCE
#include "Timer.h"
#include <limits.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

#define NSIZES 10
#define WARMUP 50

static const int payload_sizes[NSIZES] = {4,    16,    64,    256,    1024,
                                          4096, 16384, 65536, 262144, 524288};

/* Parent and child both derive the schedule from this, so they stay in step
   without any extra negotiation over the pipes. */
static int reps_for(int size) {
  /* The reported statistic is the minimum, so these counts are chosen for how
     well the minimum converges rather than for a tight error bar on the mean.
     A full sweep still costs only a few seconds, which is what allows five
     independent runs per configuration. */
  if (size <= 4096)
    return 20000;
  if (size <= 65536)
    return 5000;
  return 500;
}

static void write_all(int fd, const char *buf, size_t n) {
  size_t off = 0;
  while (off < n) {
    ssize_t w = write(fd, buf + off, n - off);
    if (w <= 0) {
      perror("write");
      exit(EXIT_FAILURE);
    }
    off += (size_t)w;
  }
}

static void read_all(int fd, char *buf, size_t n) {
  size_t off = 0;
  while (off < n) {
    ssize_t r = read(fd, buf + off, n - off);
    if (r <= 0) {
      perror("read");
      exit(EXIT_FAILURE);
    }
    off += (size_t)r;
  }
}

static void kill_kid(pid_t cpid) {
  if (cpid > 0) {
    kill(cpid, SIGTERM);
    waitpid(cpid, NULL, 0);
  }
}


/* ---------------------------------------------------------------------- */
/* Optional CPU pinning.                                                   */
/*                                                                          */
/* Wrapping the whole benchmark in taskset would confine parent and child   */
/* to one shared allowed set, which cannot express "parent on 0, child on   */
/* 1".  Pinning each process to its own CPU after the fork can.  That       */
/* distinction is the point of the experiment: same-core exchanges pay a    */
/* context switch, cross-core exchanges pay an IPI, a wakeup and whatever   */
/* the cache line migration costs.                                          */

static int g_parent_cpu = -1; /* -1 means leave the scheduler alone */
static int g_child_cpu = -1;
static const char *g_label = "unpinned";

static void pin_self(int cpu) {
  if (cpu < 0)
    return;
  cpu_set_t set;
  CPU_ZERO(&set);
  CPU_SET(cpu, &set);
  if (sched_setaffinity(0, sizeof(set), &set) != 0) {
    perror("sched_setaffinity");
    exit(EXIT_FAILURE);
  }
  sched_yield(); /* take the migration now, not mid-measurement */
}

static void parse_affinity_args(int argc, char **argv) {
  if (argc > 1)
    g_label = argv[1];
  if (argc > 2)
    g_parent_cpu = atoi(argv[2]);
  if (argc > 3)
    g_child_cpu = atoi(argv[3]);
  if (argc > 4) {
    fprintf(stderr, "usage: %s [label] [parent_cpu] [child_cpu]\n", argv[0]);
    exit(EXIT_FAILURE);
  }
}

/* Name the output after the configuration so that the three runs cannot
   silently overwrite one another. */
static void csv_name(char *out, size_t n, const char *stem) {
  snprintf(out, n, "%s_%s.csv", stem, g_label);
}

static void latency_parent(int p2c[2], int c2p[2], pid_t cpid) {
  close(p2c[0]);
  close(c2p[1]);

  char csvpath[256];
  csv_name(csvpath, sizeof(csvpath), "pipe_latency");
  FILE *csv = fopen(csvpath, "w");
  if (csv == NULL) {
    kill_kid(cpid);
    perror(csvpath);
    exit(EXIT_FAILURE);
  }
  fprintf(csv, "clock,payload_bytes,reps,mean,min,unit\n");

  printf("Pipe round trip latency, halved, payload sizes 4 B to 512 KiB\n");
  printf("%d warmup exchanges per size, then the rep count shown\n\n", WARMUP);

  char ack;

  /* Only clock_gettime.  Part 1 measured gettimeofday's granularity at 1 us,
     with 97% of consecutive reads landing in the same tick, which is coarser
     than the 728 ns round trip this benchmark has to resolve at small
     payloads.  Sweeping it a second time here would only re-measure that
     limitation. */
  printf("%-12s %10s %14s %14s\n", "clock", "payload", "mean (ns)",
         "min (ns)");
  for (int pi = 0; pi < NSIZES; ++pi) {
    int size = payload_sizes[pi];
    int reps = reps_for(size);
    char *payload = calloc(size, 1);
    if (payload == NULL) {
      kill_kid(cpid);
      perror("calloc");
      exit(EXIT_FAILURE);
    }

    for (int i = 0; i < WARMUP; ++i) {
      write_all(p2c[1], payload, size);
      read_all(c2p[0], &ack, 1);
    }

    TimerCGT timer;
    long long int sum = 0;              /* reset for every payload size */
    long long int best = LLONG_MAX;
    for (int i = 0; i < reps; ++i) {
      startTimerCGT(&timer);
      write_all(p2c[1], payload, size);
      read_all(c2p[0], &ack, 1);
      long long int rt = getTimerCGTNano(&timer);
      sum += rt;
      if (rt < best)
        best = rt;
    }

    double mean = ((double)sum / reps) / 2.0;
    double mn = (double)best / 2.0;
    printf("%-12s %10d %14.2lf %14.2lf\n", "clock_gettime", size, mean, mn);
    fprintf(csv, "clock_gettime,%d,%d,%.2lf,%.2lf,ns\n", size, reps, mean, mn);
    free(payload);
  }

  fclose(csv);
  printf("\nWrote %s\n", csvpath);
  kill_kid(cpid);
  exit(EXIT_SUCCESS);
}

/* Mirrors the parent's schedule and does nothing but acknowledge. */
static void latency_child(int p2c[2], int c2p[2]) {
  close(p2c[1]);
  close(c2p[0]);

  int max = 0;
  for (int pi = 0; pi < NSIZES; ++pi)
    if (payload_sizes[pi] > max)
      max = payload_sizes[pi];

  char *buf = malloc(max);
  if (buf == NULL) {
    perror("malloc");
    exit(EXIT_FAILURE);
  }
  char ack = 1;

  for (int pi = 0; pi < NSIZES; ++pi) {
    int size = payload_sizes[pi];
    int total = WARMUP + reps_for(size);
    for (int i = 0; i < total; ++i) {
      read_all(p2c[0], buf, size);
      write_all(c2p[1], &ack, 1);
    }
  }

  free(buf);
  exit(EXIT_SUCCESS);
}

int main(int argc, char **argv) {
  parse_affinity_args(argc, argv);

  int p2c[2];
  int c2p[2];

  if (pipe(p2c) == -1 || pipe(c2p) == -1) {
    perror("pipe");
    exit(EXIT_FAILURE);
  }

  pid_t cpid = fork();
  if (cpid == -1) {
    perror("fork");
    exit(EXIT_FAILURE);
  }

  if (cpid == 0) {
    pin_self(g_child_cpu);
    latency_child(p2c, c2p);
  } else {
    pin_self(g_parent_cpu);
    latency_parent(p2c, c2p, cpid);
  }

  return 0;
}
