from __future__ import annotations

import argparse
from pathlib import Path

import torch
from torch import nn
from torch.profiler import ProfilerActivity, profile, record_function

from lab_utils import best_device, seed_everything


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a PyTorch operator table and Chrome trace.")
    parser.add_argument("--steps", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--output", default="artifacts/trace.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_everything(2026)
    device = best_device()
    model = nn.Sequential(
        nn.Linear(512, 1024),
        nn.GELU(),
        nn.Linear(1024, 10),
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters())
    inputs = torch.randn(args.batch_size, 512, device=device)
    targets = torch.randint(0, 10, (args.batch_size,), device=device)
    activities = [ProfilerActivity.CPU]
    if device.type == "cuda":
        activities.append(ProfilerActivity.CUDA)

    with profile(
        activities=activities,
        record_shapes=True,
        profile_memory=True,
    ) as profiler:
        for _ in range(args.steps):
            with record_function("train_step.forward"):
                loss = nn.functional.cross_entropy(model(inputs), targets)
            with record_function("train_step.backward_optimizer"):
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()
            profiler.step()

    sort_key = "self_cuda_time_total" if device.type == "cuda" else "self_cpu_time_total"
    print(profiler.key_averages().table(sort_by=sort_key, row_limit=15))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    profiler.export_chrome_trace(str(output))
    print(f"wrote {output}; open it with chrome://tracing or Perfetto")


if __name__ == "__main__":
    main()
