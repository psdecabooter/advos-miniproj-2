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

latency-debug:
	gcc pipe_latency.c -DPL_SILENT -O3 -g -fno-omit-frame-pointer -o latency-debug