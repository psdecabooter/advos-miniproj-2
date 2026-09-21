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
