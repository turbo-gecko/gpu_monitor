"""
Pure conversion helpers between gauge full-scale ranges and absolute values.

This module deliberately imports nothing from tkinter so the scaling logic can
be unit-tested directly. (``app.py`` and ``ui_components.py`` import tkinter at
module load time and therefore cannot be imported in a headless test run, which
is why this logic used to be duplicated inside the tests.)
"""

# Default full-scale (min, max) for each gauge metric. The power and
# temperature ceilings are conservative fallbacks; resolve_ranges() replaces
# them with the GPU's reported hardware limits when those are available.
DEFAULT_METRIC_RANGES = {
    "temperature":   (0, 95),
    "utilization":   (0, 100),
    "power":         (0, 140),
    "system_memory": (0, 0),  # Max is set dynamically from detected total RAM
}


def pct_to_abs(metric_key, pct, ranges=None):
    """
    Convert a threshold expressed as a percentage of full-scale into an
    absolute value in the metric's own units.

    Unknown metrics return 0.0 rather than raising, so a stray key in a
    persisted config can never crash gauge setup.
    """
    if ranges is None:
        ranges = DEFAULT_METRIC_RANGES
    if metric_key not in ranges:
        return 0.0
    lo, hi = ranges[metric_key]
    return lo + (pct / 100.0) * (hi - lo)


def resolve_ranges(power_max=None, temp_max=None):
    """
    Return a ``metric -> (min, max)`` mapping, overriding the power and
    temperature ceilings with device-reported limits when they are present and
    positive. Missing or invalid limits keep the conservative defaults, so this
    is always safe to call regardless of what the GPU reports.
    """
    ranges = dict(DEFAULT_METRIC_RANGES)
    if isinstance(power_max, (int, float)) and not isinstance(power_max, bool) and power_max > 0:
        ranges["power"] = (0, float(power_max))
    if isinstance(temp_max, (int, float)) and not isinstance(temp_max, bool) and temp_max > 0:
        ranges["temperature"] = (0, float(temp_max))
    return ranges
