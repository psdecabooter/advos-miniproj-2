import matplotlib.pyplot as plt


def timer_plots():
    groups = ["gettimeofday", "clock_gettime"]
    # 5 sec test
    plt.clf()
    averages = [5.2787, 5.0001]
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
    plt.ylim(4.9, 5.3)
    plt.legend()
    plt.tight_layout()
    # plt.show()
    plt.savefig("timer_5sec.png")

    # smallest time test
    plt.clf()
    averages = [80.0, 53.16]
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
    cgt_nanos = [
        72997.90,
        99936.15,
        133376.05,
        164895.10,
        194134.95,
        219065.10,
        264623.75,
        302401.55,
        430193.40,
        654020.35,
    ]
    gtod_micros = [
        25.15,
        55.75,
        84.60,
        110.00,
        132.70,
        161.05,
        214.70,
        253.25,
        378.15,
        563.65,
    ]
    gtod_nanos = [time * 1000 for time in gtod_micros]

    plt.clf()

    plt.plot(sizes, cgt_nanos, color="g", label="clock_gettime")
    plt.plot(sizes, gtod_nanos, color="b", label="gettimeofday")

    plt.ylabel("Time (nanoseconds)")
    plt.title("Avg Latency for Pipe Payloads")
    plt.legend()
    plt.xscale("log", base=2)
    # plt.ylim(4.9, 5.3)
    plt.tight_layout()
    plt.savefig("pipe_latency.png")


if __name__ == "__main__":
    timer_plots()
    pipe_latency_plots()
