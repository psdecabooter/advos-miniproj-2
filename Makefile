build:
	gcc -o test-gtod

timer-test:
	@gcc timer_test.c -O3 -o timer-test
	./timer-test
	@rm timer-test

latency-test:
	@gcc pipe_latency.c -O3 -o latency-test
	./latency-test
	@rm latency-test

throughput-test:
	@gcc pipe_throughput.c -O3 -o throughput-test
	./throughput-test
	@rm throughput-test

latency-debug:
	gcc pipe_latency.c -static -DPL_SILENT -O0 -g -fno-omit-frame-pointer -o latency-debug