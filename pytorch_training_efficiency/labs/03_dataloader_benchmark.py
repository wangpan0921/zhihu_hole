from __future__ import annotations

import argparse
import time

import torch
from torch.utils.data import DataLoader, Dataset

from lab_utils import write_json


class DelayedDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    """A deterministic dataset that simulates per-sample decode or storage latency."""

    def __init__(self, samples: int, features: int, delay_ms: float) -> None:
        self.samples = samples
        self.features = features
        self.delay_seconds = delay_ms / 1000

    def __len__(self) -> int:
        return self.samples

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        value = float(index % 97) / 97
        return torch.full((self.features,), value), torch.tensor(index % 4)


def benchmark(loader: DataLoader[tuple[torch.Tensor, torch.Tensor]], warmup_batches: int) -> dict[str, float]:
    iterator = iter(loader)
    for _ in range(warmup_batches):
        try:
            next(iterator)
        except StopIteration:
            break
    samples = 0
    batches = 0
    started = time.perf_counter()
    for inputs, _ in iterator:
        samples += inputs.shape[0]
        batches += 1
    elapsed = time.perf_counter() - started
    return {
        "measured_samples": samples,
        "measured_batches": batches,
        "elapsed_seconds": elapsed,
        "samples_per_second": samples / elapsed if elapsed else 0.0,
        "milliseconds_per_batch": elapsed * 1000 / batches if batches else 0.0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure DataLoader throughput across worker counts.")
    parser.add_argument("--workers", type=int, nargs="+", default=[0, 1, 2, 4])
    parser.add_argument("--samples", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--delay-ms", type=float, default=1.0)
    parser.add_argument("--warmup-batches", type=int, default=2)
    parser.add_argument("--output", default="artifacts/dataloader.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = DelayedDataset(args.samples, features=128, delay_ms=args.delay_ms)
    results: dict[str, dict[str, float]] = {}
    for workers in args.workers:
        if workers < 0:
            raise ValueError("worker count cannot be negative")
        loader = DataLoader(
            dataset,
            batch_size=args.batch_size,
            num_workers=workers,
            persistent_workers=workers > 0,
            prefetch_factor=2 if workers > 0 else None,
        )
        result = benchmark(loader, args.warmup_batches)
        results[str(workers)] = result
        print(
            f"workers={workers}: {result['samples_per_second']:.1f} samples/s, "
            f"{result['milliseconds_per_batch']:.2f} ms/batch"
        )
    write_json(
        args.output,
        {
            "samples": args.samples,
            "batch_size": args.batch_size,
            "simulated_delay_ms": args.delay_ms,
            "results_by_workers": results,
        },
    )


if __name__ == "__main__":
    main()
