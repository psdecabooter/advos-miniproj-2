/*
  Run "make throughput-test"

  Example output:
  --------------------
  ./throughput-test
  Measuring pipe throughput using 100 x 67108864 payload

  clock_gettime: 7667306925 nanoseconds, 7.667 seconds, 100 x 67108864 payload size
  clock_gettime: 7290748602 nanoseconds, 7.291 seconds, 100 x 67108864 payload size
  clock_gettime: 8130523060 nanoseconds, 8.131 seconds, 100 x 67108864 payload size
  clock_gettime: 10232669312 nanoseconds, 10.233 seconds, 100 x 67108864 payload size
  clock_gettime: 7800335433 nanoseconds, 7.800 seconds, 100 x 67108864 payload size
  clock_gettime: 9711121057 nanoseconds, 9.711 seconds, 100 x 67108864 payload size
  clock_gettime: 7972931777 nanoseconds, 7.973 seconds, 100 x 67108864 payload size
  clock_gettime: 8981007260 nanoseconds, 8.981 seconds, 100 x 67108864 payload size
  clock_gettime: 8321671155 nanoseconds, 8.322 seconds, 100 x 67108864 payload size
  clock_gettime: 8335952204 nanoseconds, 8.336 seconds, 100 x 67108864 payload size

  clock_gettime: 7257433 microseconds, 7.257 seconds, 100 x 67108864 payload size
  clock_gettime: 7669438 microseconds, 7.669 seconds, 100 x 67108864 payload size
  clock_gettime: 7637340 microseconds, 7.637 seconds, 100 x 67108864 payload size
  clock_gettime: 8236551 microseconds, 8.237 seconds, 100 x 67108864 payload size
  clock_gettime: 8885209 microseconds, 8.885 seconds, 100 x 67108864 payload size
  clock_gettime: 7465494 microseconds, 7.465 seconds, 100 x 67108864 payload size
  clock_gettime: 7829773 microseconds, 7.830 seconds, 100 x 67108864 payload size
  clock_gettime: 7221389 microseconds, 7.221 seconds, 100 x 67108864 payload size
  clock_gettime: 8216256 microseconds, 8.216 seconds, 100 x 67108864 payload size
  clock_gettime: 7987414 microseconds, 7.987 seconds, 100 x 67108864 payload size
*/
#include "Timer.h"
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

#define PSIZE (1 << 26)
#define ITERS (100)

void kill_kid(pid_t cpid) {
  if (cpid > 0) {
    kill(cpid, SIGTERM);
    waitpid(cpid, NULL, 0);
  }
}

void throughput_test(int p2c[2], int c2p[2], pid_t cpid) {
  close(p2c[0]);
  close(c2p[1]);

#ifndef PT_SILENT
  printf("Measuring pipe throughput using %d x %d payload\n", ITERS, PSIZE);
#endif

  char read_ack;

  {
    TimerCGT timer_cgt;
    long long int min = LLONG_MAX;

    for (int i = 0; i < 10; ++i) {
      min = LLONG_MAX;
      // Payload is 64MiB
      char *payload = calloc(PSIZE, 1);
      if (payload == NULL) {
        kill_kid(cpid);
        perror("malloc");
        exit(EXIT_FAILURE);
      }

      startTimerCGT(&timer_cgt);
      for (int pi = 0; pi < ITERS; ++pi) {
        if (write(p2c[1], payload, PSIZE) != PSIZE) {
          kill_kid(cpid);
          perror("write");
          exit(EXIT_FAILURE);
        }
      }
      if (read(c2p[0], &read_ack, 1) <= 0) {
        kill_kid(cpid);
        perror("read");
        exit(EXIT_FAILURE);
      }
      long long int test = getTimerCGTNano(&timer_cgt);
      if (test < min) {
        min = test;
      }

#ifndef PT_SILENT
      printf("clock_gettime: %lld nanoseconds, %.3lf seconds, %d x %d payload "
             "size\n",
             min, (double)min / 1000000000, ITERS, PSIZE);
#endif
    }
  }

  {
    TimerGTOD timer_gtod;
    long long int min = LLONG_MAX;

    for (int i = 0; i < 10; ++i) {
      min = LLONG_MAX;
      // Payload is 64MiB
      char *payload = calloc(PSIZE, 1);
      if (payload == NULL) {
        kill_kid(cpid);
        perror("malloc");
        exit(EXIT_FAILURE);
      }

      startTimerGTOD(&timer_gtod);
      for (int pi = 0; pi < ITERS; ++pi) {
        if (write(p2c[1], payload, PSIZE) != PSIZE) {
          kill_kid(cpid);
          perror("write");
          exit(EXIT_FAILURE);
        }
      }
      if (read(c2p[0], &read_ack, 1) <= 0) {
        kill_kid(cpid);
        perror("read");
        exit(EXIT_FAILURE);
      }
      long long int test = getTimerGTODMicro(&timer_gtod);
      if (test < min) {
        min = test;
      }

#ifndef PT_SILENT
      printf("clock_gettime: %lld microseconds, %.3lf seconds, %d x %d payload "
             "size\n",
             min, ((double)min) / 1000000., ITERS, PSIZE);
#endif
    }
  }

  kill_kid(cpid);
  exit(EXIT_SUCCESS);
}

void throughput_watcher(int p2c[2], int c2p[2]) {
  close(p2c[1]);
  close(c2p[0]);

  char *buf = malloc(PSIZE);
  if (buf == NULL) {
    perror("malloc");
    exit(EXIT_FAILURE);
  }
  char ack = 1;
  for (int i = 0; i < 2 * 10; ++i) {
    for (int pi = 0; pi < ITERS; ++pi) {
      long long int bytes_read = 0;
      // read
      while (bytes_read < PSIZE) {
        long long int just_read = read(p2c[0], buf, PSIZE);
        if (just_read <= 0) {
          perror("read");
          exit(EXIT_FAILURE);
        }
        bytes_read += just_read;
      }
    }
    // ack
    if (write(c2p[1], &ack, 1) != 1) {
      perror("write");
      exit(EXIT_FAILURE);
    }
  }
}

int main(int argc, char *argv[]) {
  int p2c[2];
  int c2p[2];
  pid_t cpid;

  if (pipe(p2c) == -1 || pipe(c2p) == -1) {
    perror("pipe");
    exit(EXIT_FAILURE);
  }

  cpid = fork();
  if (cpid == -1) {
    perror("fork");
    exit(EXIT_FAILURE);
  }

  if (cpid == 0) { // child
    throughput_watcher(p2c, c2p);
  } else { // parent
    throughput_test(p2c, c2p, cpid);
  }
}