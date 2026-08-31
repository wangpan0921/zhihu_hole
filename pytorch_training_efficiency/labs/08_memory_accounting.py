from __future__ import annotations

import argparse
from collections.abc import Iterable

import torch
from torch import nn

from lab_utils import best_device, format_bytes, seed_everything


def tensor_bytes(tensors: Iterable[torch.Tensor]) -> int:
    return sum(tensor.numel() * tensor.element_size() for tensor in tensors)


def optimizer_state_tensors(optimizer: torch.optim.Optimizer) -> list[torch.Tensor]:
    tensors: list[torch.Tensor] = []
    for state in optimizer.state.values():
        tensors.extend(value for value in state.values() if isinstance(value, torch.Tensor))
    return tensors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Account for training tensor memory by category.")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--layers", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seed_everything(2026)
    device = best_device()
    modules: list[nn.Module] = []
    for _ in range(args.layers):
        modules.extend([nn.Linear(args.width, args.width), nn.ReLU()])
    modules.append(nn.Linear(args.width, 10))
    model = nn.Sequential(*modules).to(device)
    optimizer = torch.optim.AdamW(model.parameters())
    inputs = torch.randn(args.batch_size, args.width, device=device)
    targets = torch.randint(0, 10, (args.batch_size,), device=device)

    activation_bytes = 0
    hooks: list[torch.utils.hooks.RemovableHandle] = []

    def count_output(_module: nn.Module, _inputs: tuple[torch.Tensor, ...], output: object) -> None:
        nonlocal activation_bytes
        if isinstance(output, torch.Tensor) and output.requires_grad:
            activation_bytes += output.numel() * output.element_size()

    for module in model.modules():
        if len(list(module.children())) == 0:
            hooks.append(module.register_forward_hook(count_output))

    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    loss = nn.functional.cross_entropy(model(inputs), targets)
    loss.backward()
    optimizer.step()  # AdamW allocates its moment states lazily on the first step.
    for hook in hooks:
        hook.remove()

    parameters = tensor_bytes(model.parameters())
    gradients = tensor_bytes(parameter.grad for parameter in model.parameters() if parameter.grad is not None)
    optimizer_states = tensor_bytes(optimizer_state_tensors(optimizer))
    categories = {
        "parameters": parameters,
        "gradients": gradients,
        "optimizer_states": optimizer_states,
        "forward_outputs_requiring_grad": activation_bytes,
    }
    for name, size in categories.items():
        print(f"{name:32s} {format_bytes(size):>12s} ({size} bytes)")
    accounted = sum(categories.values())
    print(f"{'accounted_total':32s} {format_bytes(accounted):>12s} ({accounted} bytes)")
    if device.type == "cuda":
        peak = torch.cuda.max_memory_allocated(device)
        print(f"{'cuda_peak_allocated':32s} {format_bytes(peak):>12s} ({peak} bytes)")
        print("The gap includes inputs, loss, temporary buffers, allocator effects, and tensors not counted by hooks.")
    else:
        print("CUDA peak measurement skipped; category byte counts are device-independent.")


if __name__ == "__main__":
    main()
