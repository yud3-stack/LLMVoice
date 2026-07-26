from __future__ import annotations

from dataclasses import dataclass

from llmvoice.core.exceptions import EngineError


@dataclass(frozen=True)
class DeviceInfo:
    kind: str
    label: str


def resolve_device(requested: str) -> DeviceInfo:
    try:
        import torch
    except ImportError as exc:
        raise EngineError(
            "PyTorch is not installed. Install the CPU or CUDA build described in README.md."
        ) from exc

    cuda_available = bool(torch.cuda.is_available())
    if requested == "cuda" and not cuda_available:
        raise EngineError(
            "CUDA was requested but PyTorch cannot access a CUDA GPU. "
            "Install a compatible NVIDIA driver and CUDA-enabled PyTorch, or use device 'cpu'."
        )
    if requested == "cpu" or not cuda_available:
        suffix = " (CUDA unavailable; CPU fallback)" if requested == "auto" else ""
        return DeviceInfo(kind="cpu", label=f"CPU{suffix}")
    try:
        gpu_name = torch.cuda.get_device_name(0)
    except Exception:
        gpu_name = "NVIDIA GPU"
    return DeviceInfo(kind="cuda", label=f"{gpu_name} / CUDA")

