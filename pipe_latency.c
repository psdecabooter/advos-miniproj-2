/*
  Run "make latency-test"

  Example output:
  --------------------
  Measuring halved-round-trip latency for a variety of message sizes: 4, 16, 64,
  256, 1K, 4K, 16K, 64K, 256K, and 512K bytes Testing each 10 times, finding min

  clock_gettime: 19005.00 nanoseconds, 4 payload size
  clock_gettime: 19104.50 nanoseconds, 16 payload size
  clock_gettime: 19787.00 nanoseconds, 64 payload size
  clock_gettime: 16071.50 nanoseconds, 256 payload size
  clock_gettime: 17941.50 nanoseconds, 1024 payload size
  clock_gettime: 16415.50 nanoseconds, 4096 payload size
  clock_gettime: 19811.50 nanoseconds, 16384 payload size
  clock_gettime: 27716.00 nanoseconds, 65536 payload size
  clock_gettime: 106124.00 nanoseconds, 262144 payload size
  clock_gettime: 202888.00 nanoseconds, 524288 payload size

  gettimeofday: 10.50 microseconds, 4 payload size
  gettimeofday: 18.00 microseconds, 16 payload size
  gettimeofday: 11.00 microseconds, 64 payload size
  gettimeofday: 18.50 microseconds, 256 payload size
  gettimeofday: 11.00 microseconds, 1024 payload size
  gettimeofday: 11.00 microseconds, 4096 payload size
  gettimeofday: 20.00 microseconds, 16384 payload size
  gettimeofday: 29.50 microseconds, 65536 payload size
  gettimeofday: 107.00 microseconds, 262144 payload size
  gettimeofday: 195.00 microseconds, 524288 payload size
  --------------------
*/
#include "Timer.h"
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

#define ITERS (25)

const int MAX_SIZE = 524288;
const int payload_sizes[] = {4,    16,    64,    256,    1024,
                             4096, 16384, 65536, 262144, 524288};

long long int DATA[10][ITERS];

void kill_kid(pid_t cpid) {
  if (cpid > 0) {
    kill(cpid, SIGTERM);
    waitpid(cpid, NULL, 0);
  }
}

void latency_test(int p2c[2], int c2p[2], pid_t cpid) {
  close(p2c[0]);
  close(c2p[1]);

#ifndef PL_SILENT
  printf("Measuring halved-round-trip latency for a variety of message sizes: "
         "4, 16, "
         "64, 256, "
         "1K, 4K, 16K, 64K, 256K, and 512K bytes\n");
  printf("Testing each %d times, finding min\n", ITERS);
#endif

  char read_ack;

  {
    TimerCGT timer_cgt;
    long long int min = LLONG_MAX;
    for (int pi = 0; pi < 10; ++pi) {
      min = LLONG_MAX;
      int size = payload_sizes[pi];
      char *payload = malloc(size);
      if (payload == NULL) {
        kill_kid(cpid);
        perror("malloc");
        exit(EXIT_FAILURE);
      }

      for (int i = 0; i < ITERS; ++i) {
        startTimerCGT(&timer_cgt);

        if (write(p2c[1], payload, size) != size) {
          kill_kid(cpid);
          perror("write");
          exit(EXIT_FAILURE);
        }

        if (read(c2p[0], &read_ack, 1) <= 0) {
          kill_kid(cpid);
          perror("read");
          exit(EXIT_FAILURE);
        }

        long long int test = getTimerCGTNano(&timer_cgt);
        DATA[pi][i] = test;
        if (test < min) {
          min = test;
        }
      }

      free(payload);
#ifndef PL_SILENT
      printf("clock_gettime: %.2lf nanoseconds, %d payload size\n",
             (((double)min) / 2.), size);
#endif
    }
#ifndef PL_SILENT
    for (int j = 0; j < 10; ++j) {
      printf("Payload size: %d\n", payload_sizes[j]);
      for (int k = 0; k < ITERS; ++k) {
        printf("%.2lf\n", (double)DATA[j][k] / 2.);
      }
    }
#endif
  }

  {
    TimerGTOD timer_gtod;
    long long int min = LLONG_MAX;
    for (int pi = 0; pi < 10; ++pi) {
      min = LLONG_MAX;
      int size = payload_sizes[pi];
      char *payload = malloc(size);
      if (payload == NULL) {
        kill_kid(cpid);
        perror("malloc");
        exit(EXIT_FAILURE);
      }

      for (int i = 0; i < ITERS; ++i) {
        startTimerGTOD(&timer_gtod);

        if (write(p2c[1], payload, size) != size) {
          perror("write");
          exit(EXIT_FAILURE);
        }

        if (read(c2p[0], &read_ack, 1) <= 0) {
          perror("read");
          exit(EXIT_FAILURE);
        }

        long long int test = getTimerGTODMicro(&timer_gtod);
        DATA[pi][i] = test;
        if (test < min) {
          min = test;
        }
      }

      free(payload);
#ifndef PL_SILENT
      printf("gettimeofday: %.2lf microseconds, %d payload size\n",
             (((double)min) / 2.), size);
#endif
    }
#ifndef PL_SILENT
    for (int j = 0; j < 10; ++j) {
      printf("Payload size: %d\n", payload_sizes[j]);
      for (int k = 0; k < ITERS; ++k) {
        printf("%.2lf\n", (double)DATA[j][k] / 2.);
      }
    }
#endif
  }

  kill_kid(cpid);
  exit(EXIT_SUCCESS);
}

/*
  Just acks
*/
void latency_watcher(int p2c[2], int c2p[2]) {
  close(p2c[1]);
  close(c2p[0]);
  // Buff is as large as the pipe
  char buf[MAX_SIZE];
  char ack = 1;
  for (int ti = 0; ti < 2; ++ti) {
    for (int pi = 0; pi < 10; ++pi) {
      int size = payload_sizes[pi];
      for (int i = 0; i < ITERS; ++i) {
        int bytes_read = 0;

        // Keep reading from the pipe until done
        while (bytes_read < size) {
          int just_read = read(p2c[0], buf, MAX_SIZE);
          if (just_read <= 0) {
            perror("read");
            exit(EXIT_FAILURE);
          }
          bytes_read += just_read;
        }

        // ack
        if (write(c2p[1], &ack, 1) != 1) {
          perror("write");
          exit(EXIT_FAILURE);
        }
      }
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
    latency_watcher(p2c, c2p);
  } else { // parent
    latency_test(p2c, c2p, cpid);
  }
}
