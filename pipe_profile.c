/*
  Part 4c: where the time goes.

  The latency and throughput sweeps say what the cost is.  This says what the
  cost is made of.  One payload size, one affinity placement, a fixed number
  of round trips, and then an accounting of where the wall clock went:

    - user time and system time, from getrusage
    - voluntary context switches (ru_nvcsw), which is a process blocking on an
      empty or full pipe and handing the CPU away
    - involuntary context switches (ru_nivcsw), which is the scheduler
      preempting it
    - the same figures for the child, via RUSAGE_CHILDREN

  Run it under "strace -c -f" separately to get the syscall breakdown.  Do not
  read wall-clock numbers from a straced run: ptrace stops both processes on
  every syscall entry and exit, which inflates the very thing being measured.
  The two runs answer different questions and are reported separately.

  Usage: ./profile-test <payload_bytes> <reps> [parent_cpu] [child_cpu]
*/
#define _GNU_SOURCE
#include "Timer.h"
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

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
    if (w <= 0)
      _exit(EXIT_FAILURE);
    off += (size_t)w;
  }
}

static void read_all(int fd, char *buf, size_t n) {
  size_t off = 0;
  while (off < n) {
    ssize_t r = read(fd, buf + off, n - off);
    if (r <= 0)
      _exit(EXIT_FAILURE);
    off += (size_t)r;
  }
}

static double secs(struct timeval tv) {
  return (double)tv.tv_sec + (double)tv.tv_usec / 1e6;
}

int main(int argc, char **argv) {
  if (argc < 3) {
    fprintf(stderr, "usage: %s <payload_bytes> <reps> [parent_cpu] [child_cpu]\n",
            argv[0]);
    return 1;
  }
  int size = atoi(argv[1]);
  long reps = atol(argv[2]);
  int pcpu = argc > 3 ? atoi(argv[3]) : -1;
  int ccpu = argc > 4 ? atoi(argv[4]) : -1;

  int p2c[2], c2p[2];
  if (pipe(p2c) == -1 || pipe(c2p) == -1) {
    perror("pipe");
    return 1;
  }

  pid_t cpid = fork();
  if (cpid == -1) {
    perror("fork");
    return 1;
  }

  if (cpid == 0) {
    pin_self(ccpu);
    close(p2c[1]);
    close(c2p[0]);
    char *buf = malloc(size);
    char ack = 1;
    if (!buf)
      _exit(1);
    for (long i = 0; i < reps; ++i) {
      read_all(p2c[0], buf, size);
      write_all(c2p[1], &ack, 1);
    }
    free(buf);
    _exit(0);
  }

  pin_self(pcpu);
  close(p2c[0]);
  close(c2p[1]);
  char *buf = calloc(1, size);
  if (!buf)
    return 1;
  char ack;

  TimerCGT t;
  startTimerCGT(&t);
  for (long i = 0; i < reps; ++i) {
    write_all(p2c[1], buf, size);
    read_all(c2p[0], &ack, 1);
  }
  long long ns = getTimerCGTNano(&t);

  close(p2c[1]);
  close(c2p[0]);
  waitpid(cpid, NULL, 0);

  struct rusage me, kid;
  getrusage(RUSAGE_SELF, &me);
  getrusage(RUSAGE_CHILDREN, &kid);

  double wall = (double)ns / 1e9;
  double u = secs(me.ru_utime) + secs(kid.ru_utime);
  double s = secs(me.ru_stime) + secs(kid.ru_stime);
  long vcsw = me.ru_nvcsw + kid.ru_nvcsw;
  long icsw = me.ru_nivcsw + kid.ru_nivcsw;

  /* Per round trip.  One round trip is 2 writes and 2 reads by definition of
     the ping-pong, so the syscall count is known a priori and strace is used
     to confirm it rather than to discover it. */
  double rt_ns = (double)ns / (double)reps;

  printf("payload=%d reps=%ld parent_cpu=%d child_cpu=%d\n", size, reps, pcpu,
         ccpu);
  printf("  wall                 %10.4f s   (%8.0f ns / round trip)\n", wall,
         rt_ns);
  printf("  user   (both procs)  %10.4f s   (%5.1f%% of wall)\n", u,
         100 * u / wall);
  printf("  system (both procs)  %10.4f s   (%5.1f%% of wall)\n", s,
         100 * s / wall);
  printf("  unaccounted          %10.4f s   (%5.1f%% of wall)  <- blocked/idle\n",
         wall - u - s, 100 * (wall - u - s) / wall);
  printf("  voluntary ctx sw     %10ld     (%8.2f / round trip)\n", vcsw,
         (double)vcsw / (double)reps);
  printf("  involuntary ctx sw   %10ld     (%8.2f / round trip)\n", icsw,
         (double)icsw / (double)reps);

  const char *cfg = (pcpu < 0) ? "unpinned" : (pcpu == ccpu ? "same" : "cross");
  FILE *csv = fopen("pipe_profile.csv", "a");
  if (csv) {
    if (ftell(csv) == 0)
      fprintf(csv, "config,payload_bytes,reps,wall_s,ns_per_roundtrip,user_s,"
                   "system_s,unaccounted_s,vol_ctxsw,invol_ctxsw,"
                   "vol_ctxsw_per_rt\n");
    fprintf(csv, "%s,%d,%ld,%.6f,%.1f,%.6f,%.6f,%.6f,%ld,%ld,%.4f\n", cfg, size,
            reps, wall, rt_ns, u, s, wall - u - s, vcsw, icsw,
            (double)vcsw / (double)reps);
    fclose(csv);
  }

  free(buf);
  return 0;
}
