"""Small numeric and formatting helpers used by analysis/reporting code."""

import math
from typing import Any, Dict, List, Optional, Tuple


def _as_float(value: Any) -> Optional[float]:
    """Convert input to float when possible; otherwise return None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _as_int(value: Any) -> Optional[int]:
    """Convert input to int when possible; otherwise return None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _as_bool(value: Any) -> bool:
    """Convert common truthy/falsy strings and values to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes", "y"}:
            return True
        if v in {"false", "0", "no", "n"}:
            return False
    return bool(value)


def _join_warnings(warnings: Any) -> str:
    """Flatten warning values into a single pipe-separated string."""
    if warnings is None:
        return ""
    if isinstance(warnings, list):
        parts = []
        for w in warnings:
            if isinstance(w, dict):
                parts.append(str(w.get("type") or ""))
            else:
                parts.append(str(w))
        return "|".join([p for p in parts if p])
    if isinstance(warnings, dict):
        return str(warnings.get("type") or "")
    return str(warnings)


def _join_warning_types(value: Any) -> str:
    """Extract warning type names and join them with pipes."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        out = []
        for w in value:
            if isinstance(w, dict):
                t = str(w.get("type") or "").strip()
                if t:
                    out.append(t)
            else:
                s = str(w).strip()
                if s:
                    out.append(s)
        return "|".join(out)
    return ""


def _percentile(values: List[Optional[float]], p: float) -> float:
    """Compute percentile using linear interpolation over valid numbers."""
    xs = sorted([x for x in values if x is not None])
    if not xs:
        return 0.0
    k = (len(xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(xs[int(k)])
    d0 = xs[int(f)] * (c - k)
    d1 = xs[int(c)] * (k - f)
    return float(d0 + d1)


def _median(values: List[Optional[float]]) -> float:
    """Compute median over valid numbers."""
    xs = sorted([x for x in values if x is not None])
    if not xs:
        return 0.0
    n = len(xs)
    mid = n // 2
    if n % 2 == 1:
        return float(xs[mid])
    return float((xs[mid - 1] + xs[mid]) / 2.0)


def _clamp01(value: float) -> float:
    """Clamp numeric value to the inclusive range [0, 1]."""
    return max(0.0, min(1.0, float(value)))

def _warning_severity_counts(warnings: Any) -> Dict[str, int]:
    """Count low/medium/high warnings from rich or legacy warning shapes."""
    low = 0
    medium = 0
    high = 0
    if warnings is None:
        return {"low": 0, "medium": 0, "high": 0}

    # Warnings can be a list of dicts (rich) or a list of strings (legacy/public).
    items = warnings if isinstance(warnings, list) else [warnings]
    for w in items:
        if isinstance(w, dict):
            sev = str(w.get("severity") or "medium").strip().lower()
        else:
            sev = "medium"
        if sev == "low":
            low += 1
        elif sev == "high":
            high += 1
        else:
            medium += 1
    return {"low": low, "medium": medium, "high": high}


def _stability_from_warnings(warnings: Any) -> float:
    """Compute stability score from weighted warning severities."""
    counts = _warning_severity_counts(warnings)
    weighted = counts["low"] * 0.25 + counts["medium"] * 0.50 + counts["high"] * 1.00
    return round(1.0 / (1.0 + float(weighted)), 3)


def _avg(values: List[Optional[float]]) -> Optional[float]:
    """Return arithmetic mean for available numeric values."""
    xs = [x for x in values if x is not None]
    if not xs:
        return None
    return sum(xs) / len(xs)


def _std(values: List[Optional[float]]) -> Optional[float]:
    """Return sample standard deviation for available numeric values."""
    xs = [x for x in values if x is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _safe_div(numerator: float, denominator: float) -> float:
    """Safely divide values and return 0 when denominator is zero."""
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def _bootstrap_mean_ci95(values: List[float], rng_seed: int = 42, n: int = 2000) -> Tuple[float, float]:
    """Estimate 95% CI for the mean using bootstrap resampling."""
    import random

    if not values:
        return 0.0, 0.0
    rng = random.Random(int(rng_seed))
    k = len(values)
    means = []
    for _ in range(int(n)):
        sample = [values[rng.randrange(k)] for __ in range(k)]
        means.append(sum(sample) / k)
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    return float(lo), float(hi)

