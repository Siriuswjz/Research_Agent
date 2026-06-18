"""GPU 检测与并行 worker 数推断。无 torch 也能跑（返回 0）。"""
import os
import subprocess

# 显存阈值：少于这么多 MB 视为"忙"，不分配任务
MIN_FREE_MB = int(os.getenv("MIN_FREE_MB", "8000"))   # 默认 8GB


def free_memory_per_gpu() -> list[int]:
    """
    返回每张物理 GPU 的空闲显存（MB）。失败返回空列表。
    通过 nvidia-smi 实时查询，反映其他进程占用情况。
    """
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode().strip()
        return [int(line) for line in out.splitlines() if line.strip()]
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return []


def pick_free_gpus(n_needed: int) -> list[int]:
    """
    挑出 n_needed 张最空闲的 GPU（按 free memory 降序），
    过滤掉 free < MIN_FREE_MB 的。返回物理 GPU id 列表。
    若 nvidia-smi 不可用，退化为 [0, 1, ..., n_needed-1]。
    """
    free = free_memory_per_gpu()
    if not free:
        # 无法查询，按顺序分配
        return list(range(n_needed))

    # 按 free 降序排
    indexed = sorted(enumerate(free), key=lambda x: -x[1])
    usable = [i for i, mb in indexed if mb >= MIN_FREE_MB]
    if not usable:
        # 所有 GPU 都忙，仍然返回最空闲的那张作为兜底（让 torch 报错而非默认 0 撞墙）
        return [indexed[0][0]]
    return usable[:n_needed]


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

    # auto：用 nvidia-smi 实测的可用 GPU 数（过滤掉显存不足的）
    free = free_memory_per_gpu()
    if free:
        n_usable = sum(1 for mb in free if mb >= MIN_FREE_MB)
        if n_usable >= 2 and total_items >= 2:
            return min(n_usable, total_items)
        return 1
    # 查不到时退化到总卡数
    n_gpu = gpu_count()
    if n_gpu >= 2 and total_items >= 2:
        return min(n_gpu, total_items)
    return 1


def describe_device() -> str:
    """一句话描述设备状态，启动时打印用"""
    n = gpu_count()
    if n == 0:
        return "CPU"
    free = free_memory_per_gpu()
    if free:
        usable = [i for i, mb in enumerate(free) if mb >= MIN_FREE_MB]
        free_str = ", ".join(f"GPU{i}={mb}MB" for i, mb in enumerate(free))
        if len(usable) < 2:
            return f"{n} 张 GPU 中 {len(usable)} 张可用 [{free_str}] → 串行"
        return f"{n} 张 GPU 中 {len(usable)} 张可用 [{free_str}] → 并行"
    return f"{n} 张 GPU（nvidia-smi 查询失败，按顺序分配）"
