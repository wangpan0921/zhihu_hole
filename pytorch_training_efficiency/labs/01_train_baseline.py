from __future__ import annotations

import argparse
import time

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from lab_utils import best_device, seed_everything, synchronize, write_json


def make_dataset(samples: int, features: int, classes: int, seed: int) -> TensorDataset:
    generator = torch.Generator().manual_seed(seed)
    inputs = torch.randn(samples, features, generator=generator)
    teacher = torch.randn(features, classes, generator=generator)
    logits = inputs @ teacher + 0.1 * torch.randn(samples, classes, generator=generator)
    targets = logits.argmax(dim=1)
    return TensorDataset(inputs, targets)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a small reproducible classifier baseline.")
    parser.add_argument("--steps", type=int, default=10000)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", help="Optional JSON result path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_everything(args.seed)
    device = best_device()
    dataset = make_dataset(samples=4096, features=32, classes=4, seed=args.seed)
    loader_generator = torch.Generator().manual_seed(args.seed)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, generator=loader_generator)
    model = nn.Sequential(nn.Linear(32, 64), nn.ReLU(), nn.Linear(64, 4)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-3)

    model.train()
    losses: list[float] = []
    processed = 0
    iterator = iter(loader)
    synchronize(device)
    started = time.perf_counter()
    for _ in range(args.steps):
        try:
            inputs, targets = next(iterator)
        except StopIteration:
            iterator = iter(loader)
            inputs, targets = next(iterator)
        inputs = inputs.to(device)
        targets = targets.to(device)
        optimizer.zero_grad(set_to_none=True)
        loss = nn.functional.cross_entropy(model(inputs), targets)
        loss.backward()
        optimizer.step()
        losses.append(loss.item())
        processed += inputs.shape[0]
    synchronize(device)
    elapsed = time.perf_counter() - started

    model.eval()
    correct = 0
    with torch.no_grad():
        for inputs, targets in DataLoader(dataset, batch_size=512):
            predictions = model(inputs.to(device)).argmax(dim=1).cpu()
            correct += int((predictions == targets).sum())
    accuracy = correct / len(dataset)
    window = min(10, len(losses))
    first_loss = sum(losses[:window]) / window
    final_loss = sum(losses[-window:]) / window
    result = {
        "device": str(device),
        "seed": args.seed,
        "steps": args.steps,
        "samples_per_second": processed / elapsed,
        "first_loss": first_loss,
        "final_loss": final_loss,
        "accuracy": accuracy,
    }
    print(result)
    write_json(args.output, result)

    if args.steps >= 50:
        assert final_loss < first_loss * 0.75, "loss did not decrease enough"
        assert accuracy > 0.75, "accuracy is below the baseline acceptance threshold"


if __name__ == "__main__":
    main()
