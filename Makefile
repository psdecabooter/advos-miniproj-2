CC     = gcc
CFLAGS = -O3 -Wall -Wextra

BINS = timer-test latency-test throughput-test capacity-test resize-test profile-test

all: $(BINS)

timer-test: timer_test.c Timer.h
	$(CC) $(CFLAGS) timer_test.c -o $@

latency-test: pipe_latency.c Timer.h
	$(CC) $(CFLAGS) pipe_latency.c -o $@

throughput-test: pipe_throughput.c Timer.h
	$(CC) $(CFLAGS) pipe_throughput.c -o $@

capacity-test: pipe_capacity.c
	$(CC) $(CFLAGS) pipe_capacity.c -o $@

resize-test: pipe_resize.c Timer.h
	$(CC) $(CFLAGS) pipe_resize.c -o $@

profile-test: pipe_profile.c Timer.h
	$(CC) $(CFLAGS) pipe_profile.c -o $@

# Run targets. The benchmarks write their own CSVs into the working directory.
run-timer: timer-test
	./timer-test

run-latency: latency-test
	./latency-test

run-throughput: throughput-test
	./throughput-test

run-capacity: capacity-test
	./capacity-test

run-resize: resize-test
	./resize-test

run-all: run-timer run-latency run-throughput run-capacity run-resize

clean:
	rm -f $(BINS) *.csv

.PHONY: all run-timer run-latency run-throughput run-capacity run-resize run-all clean
