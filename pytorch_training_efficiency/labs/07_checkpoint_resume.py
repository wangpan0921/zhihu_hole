from __future__ import annotations

import argparse
import random
import tempfile
from pathlib import Path

import torch
from torch import nn

from lab_utils import atomic_torch_save, seed_everything, torch_load


def make_training_state() -> tuple[nn.Module, torch.optim.Optimizer]:
    model = nn.Sequential(nn.Linear(8, 16), nn.ReLU(), nn.Linear(16, 2))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-2)
    return model, optimizer


def train_steps(model: nn.Module, optimizer: torch.optim.Optimizer, steps: int) -> None:
    for _ in range(steps):
        inputs = torch.randn(32, 8)
        targets = torch.randint(0, 2, (32,))
        optimizer.zero_grad(set_to_none=True)
        loss = nn.functional.cross_entropy(model(inputs), targets)
        loss.backward()
        optimizer.step()


def save_checkpoint(path: Path, model: nn.Module, optimizer: torch.optim.Optimizer, step: int) -> None:
    atomic_torch_save(
        {
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "step": step,
            "python_rng_state": random.getstate(),
            "torch_rng_state": torch.get_rng_state(),
        },
        path,
    )


def load_checkpoint(
    path: Path, model: nn.Module, optimizer: torch.optim.Optimizer
) -> int:
    checkpoint = torch_load(path)
    model.load_state_dict(checkpoint["model"])
    optimizer.load_state_dict(checkpoint["optimizer"])
    random.setstate(checkpoint["python_rng_state"])
    torch.set_rng_state(checkpoint["torch_rng_state"])
    return int(checkpoint["step"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prove deterministic checkpoint resume equivalence.")
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--split-step", type=int, default=5)
    parser.add_argument("--checkpoint", help="Optional checkpoint path; a temporary path is used by default")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0 < args.split_step < args.steps:
        raise ValueError("split-step must be between 0 and steps")

    seed_everything(2026)
    uninterrupted_model, uninterrupted_optimizer = make_training_state()
    train_steps(uninterrupted_model, uninterrupted_optimizer, args.steps)

    seed_everything(2026)
    interrupted_model, interrupted_optimizer = make_training_state()
    train_steps(interrupted_model, interrupted_optimizer, args.split_step)

    temporary_directory = None
    if args.checkpoint:
        checkpoint_path = Path(args.checkpoint)
    else:
        temporary_directory = tempfile.TemporaryDirectory(prefix="pytorch-checkpoint-lab-")
        checkpoint_path = Path(temporary_directory.name) / "checkpoint.pt"
    save_checkpoint(checkpoint_path, interrupted_model, interrupted_optimizer, args.split_step)

    resumed_model, resumed_optimizer = make_training_state()
    resumed_step = load_checkpoint(checkpoint_path, resumed_model, resumed_optimizer)
    train_steps(resumed_model, resumed_optimizer, args.steps - resumed_step)

    differences = [
        (left - right).abs().max().item()
        for left, right in zip(uninterrupted_model.parameters(), resumed_model.parameters())
    ]
    max_difference = max(differences)
    print(f"checkpoint={checkpoint_path}")
    print(f"uninterrupted vs resumed parameter max abs difference: {max_difference:.3e}")
    assert max_difference == 0.0, "resume did not reproduce uninterrupted training"
    if temporary_directory is not None:
        temporary_directory.cleanup()


if __name__ == "__main__":
    main()
