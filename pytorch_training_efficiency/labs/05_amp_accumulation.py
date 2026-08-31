from __future__ import annotations

import argparse
import copy
import time

import torch
from torch import nn

from lab_utils import best_device, seed_everything, synchronize


def make_model(device: torch.device) -> nn.Module:
    return nn.Sequential(nn.Linear(32, 64), nn.ReLU(), nn.Linear(64, 4)).to(device)


def verify_accumulation(device: torch.device, batch_size: int, micro_batch: int) -> float:
    if batch_size % micro_batch:
        raise ValueError("batch size must be divisible by micro-batch size")
    seed_everything(2026)
    inputs = torch.randn(batch_size, 32, device=device)
    targets = torch.randint(0, 4, (batch_size,), device=device)
    large_batch_model = make_model(device)
    accumulated_model = copy.deepcopy(large_batch_model)
    large_optimizer = torch.optim.SGD(large_batch_model.parameters(), lr=0.1)
    accumulated_optimizer = torch.optim.SGD(accumulated_model.parameters(), lr=0.1)

    large_optimizer.zero_grad(set_to_none=True)
    nn.functional.cross_entropy(large_batch_model(inputs), targets, reduction="mean").backward()
    large_optimizer.step()

    accumulated_optimizer.zero_grad(set_to_none=True)
    for start in range(0, batch_size, micro_batch):
        micro_inputs = inputs[start : start + micro_batch]
        micro_targets = targets[start : start + micro_batch]
        # Sum each micro-batch, then normalize by the global batch exactly once.
        loss = nn.functional.cross_entropy(
            accumulated_model(micro_inputs), micro_targets, reduction="sum"
        ) / batch_size
        loss.backward()
    accumulated_optimizer.step()

    differences = [
        (left - right).abs().max().item()
        for left, right in zip(large_batch_model.parameters(), accumulated_model.parameters())
    ]
    return max(differences)


def amp_smoke_test(device: torch.device, steps: int, batch_size: int) -> None:
    if device.type != "cuda":
        print("AMP timing skipped: CUDA is not available")
        return
    inputs = torch.randn(batch_size, 32, device=device)
    targets = torch.randint(0, 4, (batch_size,), device=device)

    for use_amp in (False, True):
        seed_everything(2026)
        model = make_model(device)
        optimizer = torch.optim.AdamW(model.parameters())
        scaler = torch.cuda.amp.GradScaler(enabled=use_amp)
        synchronize(device)
        started = time.perf_counter()
        final_loss = 0.0
        for _ in range(steps):
            optimizer.zero_grad(set_to_none=True)
            with torch.cuda.amp.autocast(enabled=use_amp):
                loss = nn.functional.cross_entropy(model(inputs), targets)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            final_loss = loss.item()
        synchronize(device)
        elapsed = time.perf_counter() - started
        mode = "AMP FP16" if use_amp else "FP32"
        print(f"{mode}: {steps * batch_size / elapsed:.1f} samples/s, final loss={final_loss:.4f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify gradient accumulation and optionally time CUDA AMP.")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--micro-batch", type=int, default=16)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--amp", action="store_true", help="Run an additional CUDA AMP timing smoke test")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = best_device()
    max_difference = verify_accumulation(device, args.batch_size, args.micro_batch)
    print(f"large-batch vs accumulated parameter max abs difference: {max_difference:.3e}")
    assert max_difference < 1e-6, "gradient accumulation is not equivalent to the large batch"
    if args.amp:
        amp_smoke_test(device, args.steps, args.batch_size)


if __name__ == "__main__":
    main()
