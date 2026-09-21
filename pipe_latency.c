/*
  Run "make latency-test"

  Example output:
  --------------------
  Measuring halved-round-trip latency for a variety of message sizes: 4, 16, 64,
  256, 1K, 4K, 16K, 64K, 256K, and 512K bytes Testing each 10 times

  clock_gettime:  72997.90 nanoseconds, 4 payload size
  clock_gettime:  99936.15 nanoseconds, 16 payload size
  clock_gettime: 133376.05 nanoseconds, 64 payload size
  clock_gettime: 164895.10 nanoseconds, 256 payload size
  clock_gettime: 194134.95 nanoseconds, 1024 payload size
  clock_gettime: 219065.10 nanoseconds, 4096 payload size
  clock_gettime: 264623.75 nanoseconds, 16384 payload size
  clock_gettime: 302401.55 nanoseconds, 65536 payload size
  clock_gettime: 430193.40 nanoseconds, 262144 payload size
  clock_gettime: 654020.35 nanoseconds, 524288 payload size

  gettimeofday:  25.15 microseconds, 4 payload size
  gettimeofday:  55.75 microseconds, 16 payload size
  gettimeofday:  84.60 microseconds, 64 payload size
  gettimeofday: 110.00 microseconds, 256 payload size
  gettimeofday: 132.70 microseconds, 1024 payload size
  gettimeofday: 161.05 microseconds, 4096 payload size
  gettimeofday: 214.70 microseconds, 16384 payload size
  gettimeofday: 253.25 microseconds, 65536 payload size
  gettimeofday: 378.15 microseconds, 262144 payload size
  gettimeofday: 563.65 microseconds, 524288 payload size
  --------------------
*/
#include "Timer.h"
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

const int payload_sizes[] = {4,    16,    64,    256,    1024,
                             4096, 16384, 65536, 262144, 524288};

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
  printf("Testing each 10 times\n");
  #endif

  char read_ack;

  {
    TimerCGT timer_cgt;
    long long int sum = 0;
    for (int pi = 0; pi < 10; ++pi) {
      int size = payload_sizes[pi];
      char *payload = malloc(size);
      if (payload == NULL) {
        kill_kid(cpid);
        perror("malloc");
        exit(EXIT_FAILURE);
      }

      for (int i = 0; i < 10; ++i) {
        startTimerCGT(&timer_cgt);

        if (write(p2c[1], payload, size) != size) {
          perror("write");
          exit(EXIT_FAILURE);
        }

        if (read(c2p[0], &read_ack, 1) <= 0) {
          perror("read");
          exit(EXIT_FAILURE);
        }

        sum += getTimerCGTNano(&timer_cgt);
      }

      free(payload);
      #ifndef PL_SILENT
      printf("clock_gettime: %.2lf nanoseconds, %d payload size\n",
             (((double)sum / 10.) / 2.), size);
      #endif
    }
  }

  {
    TimerGTOD timer_gtod;
    long long int sum = 0;
    for (int pi = 0; pi < 10; ++pi) {
      int size = payload_sizes[pi];
      char *payload = malloc(size);
      if (payload == NULL) {
        kill_kid(cpid);
        perror("malloc");
        exit(EXIT_FAILURE);
      }

      for (int i = 0; i < 10; ++i) {
        startTimerGTOD(&timer_gtod);

        if (write(p2c[1], payload, size) != size) {
          perror("write");
          exit(EXIT_FAILURE);
        }

        if (read(c2p[0], &read_ack, 1) <= 0) {
          perror("read");
          exit(EXIT_FAILURE);
        }

        sum += getTimerGTODMicro(&timer_gtod);
      }

      free(payload);
      #ifndef PL_SILENT
      printf("gettimeofday: %.2lf microseconds, %d payload size\n",
             (((double)sum / 10.) / 2.), size);
      #endif
    }
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
  char buf[PIPE_BUF];
  char ack = 1;
  for (int ti = 0; ti < 2; ++ti) {
    for (int pi = 0; pi < 10; ++pi) {
      int size = payload_sizes[pi];
      for (int i = 0; i < 10; ++i) {
        int bytes_read = 0;

        // Keep reading from the pipe until done
        while (bytes_read < size) {
          int just_read = read(p2c[0], buf, PIPE_BUF);
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
