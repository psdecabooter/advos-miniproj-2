import matplotlib.pyplot as plt


def timer_plots():
    groups = ["gettimeofday", "clock_gettime"]
    # 5 sec test
    plt.clf()
    averages = [5.0001, 5.0001]
    expected_value = 5.0

    plt.figure(figsize=(6, 4))
    bars = plt.bar(groups, averages, color=["b", "g"])

    plt.axhline(
        y=expected_value,
        color="crimson",
        linestyle="--",
        linewidth=2,
        label=f"Expected Value ({expected_value})",
    )

    plt.ylabel("Time (seconds)")
    plt.title("Timer Averages vs. Expected Target")
    plt.ylim(4.999, 5.001)
    plt.legend()
    plt.tight_layout()
    # plt.show()
    plt.savefig("timer_5sec.png")

    # smallest time test
    plt.clf()
    averages = [1000.0, 1308.00]
    plt.figure(figsize=(6, 4))
    bars = plt.bar(groups, averages, color=["b", "g"])

    plt.ylabel("Time (nanoseconds)")
    plt.title("Timer Averages for Smallest Measurement")
    # plt.ylim(4.9, 5.3)
    plt.tight_layout()
    plt.savefig("timer_smallest.png")


def pipe_latency_plots():
    # Halved-Round-Trip Latency
    sizes = [4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 524288]
    cgt_geomeans = [
        1,
        1.081640004,
        0.9984243248,
        1.004235687,
        0.9556540018,
        0.9704407552,
        1.163969096,
        2.434531666,
        7.279254321,
        14.67829787,
    ]
    gtod_geomeans = [
        1,
        0.9854323999,
        0.9853731751,
        1.088165924,
        1.028982802,
        1.32716879,
        0.9931614161,
        1.575698297,
        5.442259406,
        15.26321416,
    ]

    plt.clf()

    plt.plot(sizes, cgt_geomeans, color="g", label="clock_gettime")
    plt.plot(sizes, gtod_geomeans, color="b", label="gettimeofday")

    plt.ylabel("Time Geomean")
    plt.xlabel("Size of Payload in Bytes")
    # plt.title("Pipe Latency for Payload Sizes Relative to 4 Bytes")
    plt.legend()
    plt.xscale("log", base=2)
    # plt.ylim(4.9, 5.3)
    plt.tight_layout()
    plt.savefig("pipe_latency.png")


if __name__ == "__main__":
    timer_plots()
    pipe_latency_plots()
