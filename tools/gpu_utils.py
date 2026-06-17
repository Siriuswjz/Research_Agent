"""GPU 检测与并行 worker 数推断。无 torch 也能跑（返回 0）。"""
import os


def gpu_count() -> int:
    """返回可用 GPU 数。没装 torch 或无 CUDA 返回 0。"""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.device_count()
    except ImportError:
        pass
    # 尝试 MPS（Apple Silicon）—— 算 1 张"卡"
    try:
        import torch
        if torch.backends.mps.is_available():
            return 1
    except (ImportError, AttributeError):
        pass
    return 0


def recommended_workers(total_items: int, override: int | str = "auto") -> int:
    """
    自动推断并行 worker 数：
    - override="auto"：GPU >= 2 时用 min(GPU 数, 任务数)，否则 1（串行）
    - override=<int>：强制使用该值
    - override="disabled"：永远 1
    """
    if override == "disabled":
        return 1
    if isinstance(override, int):
        return max(1, min(override, total_items))
    if isinstance(override, str) and override.isdigit():
        return max(1, min(int(override), total_items))

    # auto
    n_gpu = gpu_count()
    if n_gpu >= 2 and total_items >= 2:
        return min(n_gpu, total_items)
    return 1


def describe_device() -> str:
    """一句话描述设备状态，启动时打印用"""
    n = gpu_count()
    if n == 0:
        return "CPU"
    if n == 1:
        return "1 张 GPU（串行）"
    return f"{n} 张 GPU（自动并行）"
