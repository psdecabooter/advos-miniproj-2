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
#include "Timer.h"
#include <limits.h>
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
  if (size <= 4096)
    return 2000;
  if (size <= 65536)
    return 1000;
  return 200;
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

static void latency_parent(int p2c[2], int c2p[2], pid_t cpid) {
  close(p2c[0]);
  close(c2p[1]);

  FILE *csv = fopen("pipe_latency.csv", "w");
  if (csv == NULL) {
    kill_kid(cpid);
    perror("fopen");
    exit(EXIT_FAILURE);
  }
  fprintf(csv, "clock,payload_bytes,reps,mean,min,unit\n");

  printf("Pipe round trip latency, halved, payload sizes 4 B to 512 KiB\n");
  printf("%d warmup exchanges per size, then the rep count shown\n\n", WARMUP);

  char ack;

  /* clock_gettime */
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

  /* gettimeofday */
  printf("\n%-12s %10s %14s %14s\n", "clock", "payload", "mean (us)",
         "min (us)");
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

    TimerGTOD timer;
    long long int sum = 0;              /* reset for every payload size */
    long long int best = LLONG_MAX;
    for (int i = 0; i < reps; ++i) {
      startTimerGTOD(&timer);
      write_all(p2c[1], payload, size);
      read_all(c2p[0], &ack, 1);
      long long int rt = getTimerGTODMicro(&timer);
      sum += rt;
      if (rt < best)
        best = rt;
    }

    double mean = ((double)sum / reps) / 2.0;
    double mn = (double)best / 2.0;
    printf("%-12s %10d %14.2lf %14.2lf\n", "gettimeofday", size, mean, mn);
    fprintf(csv, "gettimeofday,%d,%d,%.2lf,%.2lf,us\n", size, reps, mean, mn);
    free(payload);
  }

  fclose(csv);
  printf("\nWrote pipe_latency.csv\n");
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

  for (int clockmode = 0; clockmode < 2; ++clockmode) {
    for (int pi = 0; pi < NSIZES; ++pi) {
      int size = payload_sizes[pi];
      int total = WARMUP + reps_for(size);
      for (int i = 0; i < total; ++i) {
        read_all(p2c[0], buf, size);
        write_all(c2p[1], &ack, 1);
      }
    }
  }

  free(buf);
  exit(EXIT_SUCCESS);
}

int main(void) {
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

  if (cpid == 0)
    latency_child(p2c, c2p);
  else
    latency_parent(p2c, c2p, cpid);

  return 0;
}
