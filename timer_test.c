/*
  Run "make timer-test"

  In order to get a non-zero value for gettimeofday clock on the
  tight loop test, we added a filler operation

  Example Output:
  --------------------
  ./timer-test
  Min smallest time of dividing the sum of times by 25 over 25 loops
  clock_gettime: 1400.00 nanoseconds
  gettimeofday: 1.00 microseconds

  Min 5sec over 5 runs
  clock_gettime: 5.0001 seconds
  gettimeofday: 5.0002 seconds
  --------------------
*/
#include "Timer.h"
#include <limits.h>
#include <unistd.h>

void sleep_test() {
  printf("Min 5sec over 5 runs\n");
  TimerCGT cgt_timer;
  long long int min = LLONG_MAX;
  for (int i = 0; i < 5; ++i) {
    startTimerCGT(&cgt_timer);
    sleep(5);
    long long int test = getTimerCGTNano(&cgt_timer);
    if (test < min) {
      min = test;
    }
  }

  printf("clock_gettime: %.4lf seconds\n", ((double)min) / 1000000000.);
  TimerGTOD gtod_timer;
  min = LLONG_MAX;
  for (int i = 0; i < 5; ++i) {
    startTimerGTOD(&gtod_timer);
    sleep(5);
    long long int test = getTimerGTODMicro(&gtod_timer);
    if (test < min) {
      min = test;
    }
  }
  printf("gettimeofday: %.4lf seconds\n", ((double)min) / 1000000.);
}

void short_test() {
  printf(
      "Min smallest time of adding to one number 100 times over 10 loops\n");
  TimerCGT cgt_timer;
  TimerGTOD gtod_timer;
  long long int min = LLONG_MAX;
  long long int filler = 0;
  for (int i = 0; i < 10; ++i) {
    startTimerCGT(&cgt_timer);
    int sum = 0;
    for (int i = 0; i<100; ++i) {
      sum += i;
    }
    printf("%d\n",sum);
    long long int test = getTimerCGTNano(&cgt_timer);
    if (test < min) {
      min = test;
    }
  }
  printf("clock_gettime: %.2lf nanoseconds\n", (double)min);

  min = LLONG_MAX;
  for (int i = 0; i < 10; ++i) {
    startTimerGTOD(&gtod_timer);
    int sum = 0;
    for (int i = 0; i<100; ++i) {
      sum += i;
    }
    printf("%d\n",sum);
    long long int test = getTimerGTODMicro(&gtod_timer);
    // printf("%lld\n",test);
    if (test < min) {
      min = test;
    }
  }
  printf("gettimeofday: %.2lf microseconds\n", (double)min);
}

int main(int argc, char *argv[]) {
  short_test();
  sleep_test();
}