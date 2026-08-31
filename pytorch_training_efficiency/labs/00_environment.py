from __future__ import annotations

import json
import os
import platform
import sys

import torch


def main() -> None:
    report: dict[str, object] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "torch": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "cudnn": torch.backends.cudnn.version(),
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "num_threads": torch.get_num_threads(),
        "num_interop_threads": torch.get_num_interop_threads(),
        "devices": [],
    }
    devices: list[dict[str, object]] = []
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(index)
            devices.append(
                {
                    "index": index,
                    "name": props.name,
                    "capability": f"{props.major}.{props.minor}",
                    "total_memory_bytes": props.total_memory,
                }
            )
    report["devices"] = devices
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
