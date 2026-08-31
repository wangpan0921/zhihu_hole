from __future__ import annotations

import argparse
import statistics
import time
from collections.abc import Callable

import torch

from lab_utils import best_device, percentile, seed_everything, synchronize, write_json


def measure(operation: Callable[[], torch.Tensor], device: torch.device, warmup: int, repeats: int) -> dict[str, object]:
    for _ in range(warmup):
        operation()
    synchronize(device)
    samples_ms: list[float] = []
    for _ in range(repeats):
        synchronize(device)
        started = time.perf_counter()
        result = operation()
        synchronize(device)
        samples_ms.append((time.perf_counter() - started) * 1000)
        if result.numel() == 0:
            raise AssertionError("operation returned an empty result")
    return {
        "median_ms": statistics.median(samples_ms),
        "p95_ms": percentile(samples_ms, 0.95),
        "min_ms": min(samples_ms),
        "raw_ms": samples_ms,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare a Python loop with a vectorized tensor operation.")
    parser.add_argument("--rows", type=int, default=512)
    parser.add_argument("--columns", type=int, default=512)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--output", default="artifacts/benchmark.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_everything(2026)
    device = best_device()
    tensor = torch.randn(args.rows, args.columns, device=device)

    def loop_sum() -> torch.Tensor:
        return torch.stack([row.sum() for row in tensor])

    def vectorized_sum() -> torch.Tensor:
        return tensor.sum(dim=1)

    # The reduction order differs, so normal floating-point roundoff is expected.
    assert torch.allclose(loop_sum(), vectorized_sum(), atol=1e-4, rtol=1e-5)
    loop = measure(loop_sum, device, args.warmup, args.repeats)
    vectorized = measure(vectorized_sum, device, args.warmup, args.repeats)
    speedup = float(loop["median_ms"]) / float(vectorized["median_ms"])
    report = {
        "device": str(device),
        "shape": [args.rows, args.columns],
        "warmup": args.warmup,
        "repeats": args.repeats,
        "python_loop": loop,
        "vectorized": vectorized,
        "median_speedup": speedup,
    }
    print(f"loop median: {loop['median_ms']:.3f} ms")
    print(f"vectorized median: {vectorized['median_ms']:.3f} ms")
    print(f"speedup: {speedup:.2f}x")
    write_json(args.output, report)


if __name__ == "__main__":
    main()
