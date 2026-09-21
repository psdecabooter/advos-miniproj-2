/*
  Part 4b: move the knee on purpose.

  The throughput sweep in part 3 falls off around the default 64 KiB pipe
  capacity, but only when writer and reader sit on different cores.  Pinned to
  one core the curve has no knee at all.  A correlation with capacity at one
  fixed capacity is not evidence of a cause, so here the capacity itself is
  the independent variable: set it with F_SETPIPE_SZ to 4 KiB, 16 KiB, 64 KiB,
  256 KiB and 1 MiB, and re-run a reduced sweep at each.

  If the knee follows the configured capacity, capacity causes it.  If the
  knee stays put while capacity moves, something else does, and the part 3
  story has to be rewritten.

  F_SETPIPE_SZ rounds up to a page and to a power of two, and is capped by
  /proc/sys/fs/pipe-max-size for unprivileged callers.  The value the kernel
  actually adopted is read back with F_GETPIPE_SZ and that is what gets
  recorded, never the requested value.

  Usage: ./resize-test [label] [parent_cpu] [child_cpu]
*/
#define _GNU_SOURCE
#include "Timer.h"
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

#define NCAPS 5
#define NCHUNKS 9
#define TRIALS 3

static const int capacities[NCAPS] = {4096, 16384, 65536, 262144, 1048576};
static const int chunk_sizes[NCHUNKS] = {1024,  4096,   8192,   16384, 32768,
                                         65536, 131072, 262144, 524288};

static int g_parent_cpu = -1, g_child_cpu = -1;
static const char *g_label = "unpinned";

static void pin_self(int cpu) {
  if (cpu < 0)
    return;
  cpu_set_t set;
  CPU_ZERO(&set);
  CPU_SET(cpu, &set);
  if (sched_setaffinity(0, sizeof(set), &set) != 0)
    perror("sched_setaffinity");
  sched_yield();
}

static void write_all(int fd, const char *buf, size_t n) {
  size_t off = 0;
  while (off < n) {
    ssize_t w = write(fd, buf + off, n - off);
    if (w <= 0) {
      if (w < 0)
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
      if (r < 0)
        perror("read");
      exit(EXIT_FAILURE);
    }
    off += (size_t)r;
  }
}

/* Keep every run moving the same total volume so that the comparison across
   chunk sizes is a comparison of rate and not of work done. */
static long long writes_for(int chunk) {
  long long n = (32LL << 20) / chunk;
  return n < 16 ? 16 : n;
}

int main(int argc, char **argv) {
  if (argc > 1)
    g_label = argv[1];
  if (argc > 2)
    g_parent_cpu = atoi(argv[2]);
  if (argc > 3)
    g_child_cpu = atoi(argv[3]);

  int maxchunk = chunk_sizes[NCHUNKS - 1];
  char path[256];
  snprintf(path, sizeof(path), "pipe_resize_%s.csv", g_label);
  FILE *csv = fopen(path, "w");
  if (!csv) {
    perror(path);
    return 1;
  }
  fprintf(csv, "requested_capacity,actual_capacity,chunk_bytes,total_bytes,"
               "best_MiB_per_s,chunk_over_capacity\n");

  printf("Pipe resize sweep (%s). Capacity is the independent variable.\n\n",
         g_label);
  printf("%12s", "cap \\ chunk");
  for (int ci = 0; ci < NCHUNKS; ++ci)
    printf("%9d", chunk_sizes[ci]);
  printf("\n");

  for (int capi = 0; capi < NCAPS; ++capi) {
    int want = capacities[capi];
    int actual = -1;
    double best_row[NCHUNKS];

    for (int ci = 0; ci < NCHUNKS; ++ci) {
      int chunk = chunk_sizes[ci];
      long long nwrites = writes_for(chunk);
      double best = 0;

      for (int t = 0; t < TRIALS; ++t) {
        int p2c[2], c2p[2];
        if (pipe(p2c) == -1 || pipe(c2p) == -1) {
          perror("pipe");
          return 1;
        }

        /* Resize before the fork so both ends see the same pipe. */
        if (fcntl(p2c[1], F_SETPIPE_SZ, want) == -1) {
          fprintf(stderr, "F_SETPIPE_SZ(%d) failed; is it above "
                          "/proc/sys/fs/pipe-max-size?\n", want);
          return 1;
        }
        actual = fcntl(p2c[1], F_GETPIPE_SZ);

        pid_t cpid = fork();
        if (cpid == -1) {
          perror("fork");
          return 1;
        }

        if (cpid == 0) { /* reader */
          pin_self(g_child_cpu);
          close(p2c[1]);
          close(c2p[0]);
          char *buf = malloc(maxchunk);
          if (!buf)
            _exit(1);
          for (long long i = 0; i < nwrites; ++i)
            read_all(p2c[0], buf, chunk);
          char ack = 1;
          write_all(c2p[1], &ack, 1); /* one ack for the whole transfer */
          free(buf);
          _exit(0);
        }

        /* writer */
        pin_self(g_parent_cpu);
        close(p2c[0]);
        close(c2p[1]);
        char *buf = calloc(1, maxchunk);
        if (!buf)
          return 1;

        TimerCGT timer;
        startTimerCGT(&timer);
        for (long long i = 0; i < nwrites; ++i)
          write_all(p2c[1], buf, chunk);
        char ack;
        read_all(c2p[0], &ack, 1);
        long long ns = getTimerCGTNano(&timer);

        double mib = (double)(nwrites * chunk) / (1024.0 * 1024.0);
        double rate = mib / ((double)ns / 1e9);
        if (rate > best)
          best = rate; /* best of TRIALS, per the minimum-time principle */

        free(buf);
        close(p2c[1]);
        close(c2p[0]);
        waitpid(cpid, NULL, 0);
      }

      best_row[ci] = best;
      fprintf(csv, "%d,%d,%d,%lld,%.2f,%.4f\n", want, actual, chunk,
              nwrites * chunk, best, (double)chunk / (double)actual);
    }

    printf("%12d", actual);
    for (int ci = 0; ci < NCHUNKS; ++ci)
      printf("%9.0f", best_row[ci]);
    printf("\n");
  }

  printf("\n(values are MiB/s, best of %d trials)\n", TRIALS);
  fclose(csv);
  printf("Wrote %s\n", path);
  return 0;
}
