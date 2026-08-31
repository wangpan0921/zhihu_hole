from __future__ import annotations

import argparse
import os

import torch
import torch.distributed as dist
from torch import nn
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader, DistributedSampler, TensorDataset

from lab_utils import seed_everything


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A minimal DDP training and metric-reduction lab.")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=64, help="Per-rank batch size")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    required = ("RANK", "WORLD_SIZE", "LOCAL_RANK")
    if any(name not in os.environ for name in required):
        raise SystemExit(
            "Launch with: torchrun --standalone --nproc-per-node=2 labs/06_ddp_train.py"
        )

    rank = int(os.environ["RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    local_rank = int(os.environ["LOCAL_RANK"])
    use_cuda = torch.cuda.is_available()
    backend = "nccl" if use_cuda else "gloo"
    if use_cuda:
        torch.cuda.set_device(local_rank)
        device = torch.device("cuda", local_rank)
    else:
        device = torch.device("cpu")

    dist.init_process_group(backend=backend)
    try:
        seed_everything(2026)
        generator = torch.Generator().manual_seed(7)
        inputs = torch.randn(1024, 16, generator=generator)
        targets = (inputs[:, :4].sum(dim=1) > 0).long()
        dataset = TensorDataset(inputs, targets)
        sampler = DistributedSampler(
            dataset,
            num_replicas=world_size,
            rank=rank,
            shuffle=True,
            seed=2026,
        )
        loader = DataLoader(dataset, batch_size=args.batch_size, sampler=sampler)
        model = nn.Sequential(nn.Linear(16, 32), nn.ReLU(), nn.Linear(32, 2)).to(device)
        ddp_model = DistributedDataParallel(
            model,
            device_ids=[local_rank] if use_cuda else None,
        )
        optimizer = torch.optim.SGD(ddp_model.parameters(), lr=0.1)

        for epoch in range(args.epochs):
            sampler.set_epoch(epoch)
            local_loss_sum = torch.zeros((), device=device)
            local_correct = torch.zeros((), device=device, dtype=torch.long)
            local_samples = torch.zeros((), device=device, dtype=torch.long)
            for batch_inputs, batch_targets in loader:
                batch_inputs = batch_inputs.to(device)
                batch_targets = batch_targets.to(device)
                optimizer.zero_grad(set_to_none=True)
                logits = ddp_model(batch_inputs)
                loss = nn.functional.cross_entropy(logits, batch_targets)
                loss.backward()
                optimizer.step()
                local_loss_sum += loss.detach() * batch_inputs.shape[0]
                local_correct += (logits.argmax(dim=1) == batch_targets).sum()
                local_samples += batch_inputs.shape[0]

            totals = torch.stack(
                [local_loss_sum, local_correct.to(local_loss_sum.dtype), local_samples.to(local_loss_sum.dtype)]
            )
            dist.all_reduce(totals, op=dist.ReduceOp.SUM)
            if rank == 0:
                print(
                    f"epoch={epoch} global_loss={totals[0].item() / totals[2].item():.4f} "
                    f"global_accuracy={totals[1].item() / totals[2].item():.3f} "
                    f"samples={int(totals[2].item())}"
                )

        flat_parameters = torch.cat([parameter.detach().reshape(-1) for parameter in ddp_model.parameters()])
        rank_zero_parameters = flat_parameters.clone()
        dist.broadcast(rank_zero_parameters, src=0)
        max_difference = (flat_parameters - rank_zero_parameters).abs().max()
        dist.all_reduce(max_difference, op=dist.ReduceOp.MAX)
        if rank == 0:
            print(f"world_size={world_size} backend={backend} parameter_max_difference={max_difference.item():.3e}")
        assert max_difference.item() == 0.0, "DDP replicas ended with different parameters"
    finally:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
