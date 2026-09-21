/*
  Run "make timer-test"

  In order to get a non-zero value for gettimeofday clock on the
  tight loop test, we added a filler operation

  Example Output:
  --------------------
  ./timer-test
  Avg 5sec over 5 runs
  clock_gettime: 5.0001 seconds
  gettimeofday: 5.2787 seconds

  Avg smallest time of dividing the sum of times by 25 over 25 loops
  clock_gettime: 53.16 nanoseconds
  gettimeofday: 0.08 microseconds
  --------------------
*/
#include "Timer.h"
#include <unistd.h>

int main(int argc, char *argv[]) {

  printf("Avg 5sec over 5 runs\n");
  TimerCGT cgt_timer;
  long long int sum = 0;
  for (int i = 0; i < 5; ++i) {
    startTimerCGT(&cgt_timer);
    sleep(5);
    sum += getTimerCGTNano(&cgt_timer);
  }

  printf("clock_gettime: %.4lf seconds\n", ((double)sum / 5) / 1000000000.);
  TimerGTOD gtod_timer;
  sum = 0;
  for (int i = 0; i < 5; ++i) {
    startTimerGTOD(&gtod_timer);
    sleep(5);
    sum += getTimerGTODMicro(&gtod_timer);
  }
  printf("gettimeofday: %.4lf seconds\n", ((double)sum / 5) / 1000000.);

  printf("Avg smallest time of dividing the sum of times by 25 over 25 loops\n");
  sum = 0;
  long long int filler = 0;
  for (int i = 0; i < 25; ++i) {
    startTimerCGT(&cgt_timer);
    filler += sum / 25;
    sum += getTimerCGTNano(&cgt_timer);
  }
  printf("clock_gettime: %.2lf nanoseconds\n", (double)sum / 25);

  sum = 0;
  for (int i = 0; i < 25; ++i) {
    startTimerGTOD(&gtod_timer);
    filler += sum / 25;
    sum += getTimerGTODMicro(&gtod_timer);
  }
  printf("gettimeofday: %.2lf microseconds\n", (double)sum / 25);
}