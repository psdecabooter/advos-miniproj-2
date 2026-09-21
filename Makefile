CC     = gcc
CFLAGS = -O3 -Wall

BINS = timer-test latency-test throughput-test

all: $(BINS)

timer-test: timer_test.c Timer.h
	$(CC) $(CFLAGS) timer_test.c -o $@

latency-test: pipe_latency.c Timer.h
	$(CC) $(CFLAGS) pipe_latency.c -o $@

throughput-test: pipe_throughput.c Timer.h
	$(CC) $(CFLAGS) pipe_throughput.c -o $@

# Run targets. The benchmarks write their own CSVs into the working directory.
run-timer: timer-test
	./timer-test

run-latency: latency-test
	./latency-test

run-throughput: throughput-test
	./throughput-test

run-all: run-timer run-latency run-throughput

clean:
	rm -f $(BINS) pipe_latency.csv pipe_throughput.csv

.PHONY: all run-timer run-latency run-throughput run-all clean
