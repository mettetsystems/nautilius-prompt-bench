from __future__ import annotations

from dataclasses import dataclass

from prompt_piper.setup.gpu_detect import GpuInfo, detect_gpu

_MIN_VRAM_MB_FOR_EMBEDDING_CUDA = 4096
_MIN_CUDA_MAJOR_CAPABILITY = 7


@dataclass(frozen=True)
class EmbeddingDeviceDecision:
    device: str
    reason: str
    gpu: GpuInfo | None = None


def resolve_embedding_device(gpu: GpuInfo | None = None) -> EmbeddingDeviceDecision:
    """Pick cpu or cuda for sentence-transformers based on hardware and PyTorch support."""
    resolved_gpu = detect_gpu() if gpu is None else gpu
    if resolved_gpu is None:
        return EmbeddingDeviceDecision("cpu", "No GPU detected; embeddings use CPU")

    if resolved_gpu.vendor != "nvidia":
        return EmbeddingDeviceDecision(
            "cpu",
            f"{resolved_gpu.name}: non-NVIDIA GPU; embeddings use CPU",
            gpu=resolved_gpu,
        )

    if (
        resolved_gpu.vram_mb is not None
        and resolved_gpu.vram_mb < _MIN_VRAM_MB_FOR_EMBEDDING_CUDA
    ):
        return EmbeddingDeviceDecision(
            "cpu",
            (
                f"{resolved_gpu.name} has {resolved_gpu.vram_mb}MB VRAM; "
                "embeddings use CPU to reserve GPU for llama"
            ),
            gpu=resolved_gpu,
        )

    probe = _probe_pytorch_cuda(resolved_gpu)
    if probe is not None:
        return EmbeddingDeviceDecision(probe.device, probe.reason, gpu=resolved_gpu)

    return EmbeddingDeviceDecision(
        "cpu",
        f"{resolved_gpu.name}: PyTorch CUDA probe unavailable; embeddings use CPU",
        gpu=resolved_gpu,
    )


def _probe_pytorch_cuda(gpu: GpuInfo | None = None) -> EmbeddingDeviceDecision | None:
    try:
        import torch
    except ImportError:
        return None

    if not torch.cuda.is_available():
        return EmbeddingDeviceDecision("cpu", "PyTorch CUDA is not available")

    try:
        index = 0
        if gpu is not None:
            matching = [i for i in range(torch.cuda.device_count()) if torch.cuda.get_device_name(i) == gpu.name]
            if not matching:
                return EmbeddingDeviceDecision("cpu", "Detected GPU is not visible to this PyTorch build")
            index = matching[0]
        device = "cuda" if index == 0 else f"cuda:{index}"
        device_name = torch.cuda.get_device_name(index)
        major, minor = torch.cuda.get_device_capability(index)
    except Exception as exc:
        return EmbeddingDeviceDecision("cpu", f"PyTorch CUDA probe failed: {exc}")

    if major < _MIN_CUDA_MAJOR_CAPABILITY:
        return EmbeddingDeviceDecision(
            "cpu",
            (
                f"{device_name} (compute {major}.{minor}) is not supported by the "
                "installed PyTorch CUDA build"
            ),
        )

    try:
        weights = torch.zeros(32, 32, device=device)
        indices = torch.tensor([0], device=device)
        torch.nn.functional.embedding(indices, weights)
        torch.cuda.synchronize(index)
    except Exception as exc:
        return EmbeddingDeviceDecision(
            "cpu",
            f"{device_name} failed PyTorch CUDA embedding probe: {exc}",
        )

    return EmbeddingDeviceDecision(
        device,
        f"{device_name} passed PyTorch CUDA embedding probe",
    )
