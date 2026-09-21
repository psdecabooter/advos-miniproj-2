/*
  Pipe throughput benchmark for mini-project 2.

  Build and run:  make throughput-test && ./throughput-test

  Design:
    Throughput is not the latency loop with a bigger payload.  In the latency
    test the pipe is empty almost all the time because the writer stops after
    every message and waits for an ack, so the round trip, not the pipe, sets
    the rate.  Here the parent streams a fixed total volume in chunks of N
    bytes with no per chunk acknowledgement, and the child drains the pipe as
    fast as it can.  The single 1 byte ack at the end of a run lets the parent
    stop the clock when the last byte has actually been consumed rather than
    when the last write returned into the kernel buffer.

    Chunk sizes are sampled finely around 64 KiB because that is the default
    Linux pipe capacity, 16 pages of 4 KiB.  If the curve has a knee, it should
    show up there.  Check getconf PAGESIZE on the machine under test, because a
    kernel built with larger pages moves the capacity and therefore the knee.

    clock_gettime is used throughout; part 1 establishes it as the better clock
    and a run here lasts long enough that clock resolution is irrelevant.

  Output:
    A readable table on stdout, plus pipe_throughput.csv for plotting.
*/
#include "Timer.h"
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

#define NSIZES 15
#define TRIALS 5
#define WARMUP 1

static const int chunk_sizes[NSIZES] = {
    4,     16,    64,    256,    1024,   4096,   8192, 16384,
    32768, 49152, 65536, 81920, 131072, 262144, 524288};

/* Parent and child both derive the schedule from this. */
static long long nwrites_for(int size) {
  long long target = 64LL << 20; /* aim for 64 MiB per run */
  long long n = target / size;
  if (n > 200000) /* cap the syscall count for tiny chunks */
    n = 200000;
  if (n < 64)
    n = 64;
  return n;
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

static void throughput_parent(int p2c[2], int c2p[2], pid_t cpid) {
  close(p2c[0]);
  close(c2p[1]);

  FILE *csv = fopen("pipe_throughput.csv", "w");
  if (csv == NULL) {
    kill_kid(cpid);
    perror("fopen");
    exit(EXIT_FAILURE);
  }
  fprintf(csv, "chunk_bytes,writes_per_run,total_bytes,trials,mean_MiB_per_s,"
               "max_MiB_per_s,mean_ns_per_write\n");

  printf("Pipe throughput, one way streaming, chunk sizes 4 B to 512 KiB\n");
  printf("%d warmup run and %d timed runs per chunk size\n\n", WARMUP, TRIALS);
  printf("%10s %10s %12s %14s %14s %16s\n", "chunk", "writes", "total (MiB)",
         "mean (MiB/s)", "max (MiB/s)", "mean ns/write");

  char ack;

  for (int ci = 0; ci < NSIZES; ++ci) {
    int size = chunk_sizes[ci];
    long long nwrites = nwrites_for(size);
    long long total = nwrites * size;

    char *buf = calloc(size, 1);
    if (buf == NULL) {
      kill_kid(cpid);
      perror("calloc");
      exit(EXIT_FAILURE);
    }

    double sum_mibps = 0.0;
    double best_mibps = 0.0;
    double sum_ns_per_write = 0.0;

    for (int t = 0; t < WARMUP + TRIALS; ++t) {
      TimerCGT timer;
      startTimerCGT(&timer);

      for (long long i = 0; i < nwrites; ++i)
        write_all(p2c[1], buf, size);

      /* Stop only once the child has consumed the whole stream. */
      read_all(c2p[0], &ack, 1);
      long long int elapsed = getTimerCGTNano(&timer);

      if (t < WARMUP)
        continue;

      double secs = (double)elapsed / 1e9;
      double mibps = ((double)total / (1024.0 * 1024.0)) / secs;
      sum_mibps += mibps;
      sum_ns_per_write += (double)elapsed / (double)nwrites;
      if (mibps > best_mibps)
        best_mibps = mibps;
    }

    double mean_mibps = sum_mibps / TRIALS;
    double mean_nspw = sum_ns_per_write / TRIALS;
    printf("%10d %10lld %12.2lf %14.2lf %14.2lf %16.2lf\n", size, nwrites,
           (double)total / (1024.0 * 1024.0), mean_mibps, best_mibps,
           mean_nspw);
    fprintf(csv, "%d,%lld,%lld,%d,%.2lf,%.2lf,%.2lf\n", size, nwrites, total,
            TRIALS, mean_mibps, best_mibps, mean_nspw);

    free(buf);
  }

  fclose(csv);
  printf("\nWrote pipe_throughput.csv\n");
  kill_kid(cpid);
  exit(EXIT_SUCCESS);
}

/* Drains the stream and acknowledges once per run. */
static void throughput_child(int p2c[2], int c2p[2]) {
  close(p2c[1]);
  close(c2p[0]);

  int max = 0;
  for (int ci = 0; ci < NSIZES; ++ci)
    if (chunk_sizes[ci] > max)
      max = chunk_sizes[ci];

  char *buf = malloc(max);
  if (buf == NULL) {
    perror("malloc");
    exit(EXIT_FAILURE);
  }
  char ack = 1;

  for (int ci = 0; ci < NSIZES; ++ci) {
    int size = chunk_sizes[ci];
    long long nwrites = nwrites_for(size);
    for (int t = 0; t < WARMUP + TRIALS; ++t) {
      for (long long i = 0; i < nwrites; ++i)
        read_all(p2c[0], buf, size);
      write_all(c2p[1], &ack, 1);
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
    throughput_child(p2c, c2p);
  else
    throughput_parent(p2c, c2p, cpid);

  return 0;
}
