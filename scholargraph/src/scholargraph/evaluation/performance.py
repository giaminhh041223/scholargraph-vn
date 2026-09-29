"""End-to-end latency / memory profiling helpers (SG-040).

Rules (card SG-040): measure REAL inference (encode + search + fusion on live
components) — cache lookups must never be reported as full-pipeline inference.
Every figure carries its hardware/workload context; unmeasurable quantities are
null with a reason, never 0. No optimisation happens here (profile before
optimising); rankings are never modified for speed.
"""

from __future__ import annotations

import math
import os
import platform
import sys
import time
from typing import Any, Callable, Sequence


class PerformanceError(Exception):
    """Fatal profiling input or measurement problem."""


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile (q in [0, 100])."""
    if not (0.0 <= q <= 100.0) or not math.isfinite(q):
        raise PerformanceError(f"q must be within [0, 100], got {q!r}")
    data = [float(v) for v in values]
    if not data:
        raise PerformanceError("Refusing percentiles of an empty sample")
    if any(not math.isfinite(v) for v in data):
        raise PerformanceError("Non-finite timing sample")
    ordered = sorted(data)
    if len(ordered) == 1:
        return ordered[0]
    rank = (q / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    frac = rank - low
    if low + 1 >= len(ordered):
        return ordered[-1]
    return ordered[low] + frac * (ordered[low + 1] - ordered[low])


def summarize_timings(samples: Sequence[float]) -> dict[str, Any]:
    """P50/P95/min/max/mean/n over a timing sample (seconds)."""
    data = [float(v) for v in samples]
    if not data:
        raise PerformanceError("Refusing summary of an empty sample")
    if any((not math.isfinite(v)) or v < 0 for v in data):
        raise PerformanceError("Timing samples must be finite and non-negative")
    return {
        "n": len(data),
        "mean_s": sum(data) / len(data),
        "min_s": min(data),
        "p50_s": percentile(data, 50.0),
        "p95_s": percentile(data, 95.0),
        "max_s": max(data),
    }


def peak_rss_bytes() -> int | None:
    """Peak resident set size of this process (bytes) or None with no fallback.

    Windows: PeakWorkingSetSize via ctypes. POSIX: resource.getrusage peak
    (ru_maxrss units differ per OS and are converted). Any failure returns
    None — callers must record the gap, never substitute 0.
    """
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class _MemCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE, ctypes.POINTER(_MemCounters), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            counters = _MemCounters()
            counters.cb = ctypes.sizeof(_MemCounters)
            if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(),
                                          ctypes.byref(counters), counters.cb):
                return int(counters.PeakWorkingSetSize)
            return None
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return int(peak)  # bytes on macOS
        return int(peak) * 1024  # KiB on Linux
    except Exception:
        return None


def hardware_context() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
        "gpu_measured_here": False,
        "gpu_note": "No GPU measured in this local run; see SG-002 Colab T4 pilot for GPU reference.",
    }


def time_call(fn: Callable[[], Any], *, repeat: int = 1) -> tuple[Any, list[float]]:
    """Run fn repeat times, returning (last_result, per-run seconds)."""
    if repeat < 1:
        raise PerformanceError(f"repeat must be >= 1, got {repeat!r}")
    samples: list[float] = []
    result: Any = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn()
        samples.append(time.perf_counter() - t0)
    return result, samples
