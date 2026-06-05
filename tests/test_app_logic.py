"""
Unit tests for application logic in gpu_monitor.

The percentage<->absolute scaling logic lives in the tkinter-free
gpu_monitor.scaling module precisely so it can be imported and tested
directly here (app.py imports tkinter at module level and cannot be loaded
in a headless test run). These tests exercise the real functions.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gpu_monitor.config import (
    DEFAULT_THRESHOLDS,
    GAUGE_SIZES,
    UPDATE_INTERVAL_MIN_S,
    UPDATE_INTERVAL_MAX_S,
    DEFAULT_GAUGE_COLORS,
    DEFAULT_WINDOW_STATE,
)
from gpu_monitor.scaling import (
    pct_to_abs,
    resolve_ranges,
    DEFAULT_METRIC_RANGES,
)


def _pct_to_abs(metric: str, pct: float) -> float:
    """Thin wrapper over the real pct_to_abs using the default ranges."""
    return pct_to_abs(metric, pct, DEFAULT_METRIC_RANGES)


# ── Tests ────────────────────────────────────────────────────────────


class TestPctToAbs(unittest.TestCase):
    """Test _pct_to_abs helper — converts percentage thresholds to absolute values."""

    def test_temperature_90_pct(self):
        """90% of temperature range (0-95) = 85.5."""
        self.assertAlmostEqual(_pct_to_abs("temperature", 90), 85.5, places=1)

    def test_temperature_100_pct(self):
        """100% of temperature range (0-95) = 95."""
        self.assertAlmostEqual(_pct_to_abs("temperature", 100), 95.0, places=1)

    def test_temperature_0_pct(self):
        """0% of temperature range = 0."""
        self.assertAlmostEqual(_pct_to_abs("temperature", 0), 0.0, places=1)

    def test_temperature_50_pct(self):
        """50% of temperature range (0-95) = 47.5."""
        self.assertAlmostEqual(_pct_to_abs("temperature", 50), 47.5, places=1)

    def test_utilization_50_pct(self):
        """50% of utilization range (0-100) = 50."""
        self.assertAlmostEqual(_pct_to_abs("utilization", 50), 50.0, places=1)

    def test_utilization_98_pct(self):
        """98% of utilization range (0-100) = 98."""
        self.assertAlmostEqual(_pct_to_abs("utilization", 98), 98.0, places=1)

    def test_utilization_0_pct(self):
        """0% of utilization = 0."""
        self.assertAlmostEqual(_pct_to_abs("utilization", 0), 0.0, places=1)

    def test_power_80_pct(self):
        """80% of power range (0-140) = 112."""
        self.assertAlmostEqual(_pct_to_abs("power", 80), 112.0, places=1)

    def test_power_100_pct(self):
        """100% of power range (0-140) = 140."""
        self.assertAlmostEqual(_pct_to_abs("power", 100), 140.0, places=1)

    def test_power_50_pct(self):
        """50% of power range (0-140) = 70."""
        self.assertAlmostEqual(_pct_to_abs("power", 50), 70.0, places=1)

    def test_system_memory_90_pct(self):
        """90% of system memory range (0-64) = 57.6."""
        custom_ranges = {"system_memory": (0, 64)}
        self.assertAlmostEqual(pct_to_abs("system_memory", 90, custom_ranges), 57.6, places=1)

    def test_system_memory_100_pct(self):
        """100% of system memory range (0-64) = 64."""
        custom_ranges = {"system_memory": (0, 64)}
        self.assertAlmostEqual(pct_to_abs("system_memory", 100, custom_ranges), 64.0, places=1)

    def test_system_memory_0_pct(self):
        """0% of system memory = 0."""
        custom_ranges = {"system_memory": (0, 64)}
        self.assertAlmostEqual(pct_to_abs("system_memory", 0, custom_ranges), 0.0, places=1)

    def test_system_memory_default_is_zero_range(self):
        """Default system_memory range should be (0, 0) — max set dynamically."""
        self.assertEqual(DEFAULT_METRIC_RANGES["system_memory"], (0, 0))

    def test_invalid_metric_returns_zero(self):
        """Unknown metric should return 0."""
        self.assertAlmostEqual(_pct_to_abs("unknown_metric", 50), 0.0, places=1)


class TestPctToAbsEdgeCases(unittest.TestCase):
    """Edge cases for _pct_to_abs."""

    def test_negative_pct(self):
        """Negative percentage should produce values below min."""
        result = _pct_to_abs("temperature", -10)
        self.assertAlmostEqual(result, -9.5, places=1)

    def test_pct_above_100(self):
        """Percentage above 100 should produce values above max."""
        result = _pct_to_abs("temperature", 110)
        self.assertAlmostEqual(result, 104.5, places=1)

    def test_float_pct(self):
        """Float percentage should work correctly."""
        result = _pct_to_abs("temperature", 90.5)
        self.assertAlmostEqual(result, 86.0, places=1)


class TestResolveRanges(unittest.TestCase):
    """resolve_ranges overrides power/temperature ceilings with device limits."""

    def test_no_limits_returns_defaults(self):
        self.assertEqual(resolve_ranges(None, None), DEFAULT_METRIC_RANGES)

    def test_power_limit_applied(self):
        ranges = resolve_ranges(power_max=350.0, temp_max=None)
        self.assertEqual(ranges["power"], (0, 350.0))
        # Other metrics untouched.
        self.assertEqual(ranges["temperature"], DEFAULT_METRIC_RANGES["temperature"])
        self.assertEqual(ranges["utilization"], (0, 100))

    def test_temp_limit_applied(self):
        ranges = resolve_ranges(power_max=None, temp_max=100.0)
        self.assertEqual(ranges["temperature"], (0, 100.0))
        self.assertEqual(ranges["power"], DEFAULT_METRIC_RANGES["power"])

    def test_both_limits_applied(self):
        ranges = resolve_ranges(power_max=450, temp_max=105)
        self.assertEqual(ranges["power"], (0, 450.0))
        self.assertEqual(ranges["temperature"], (0, 105.0))

    def test_nonpositive_and_invalid_limits_ignored(self):
        for bad in (0, -10, "abc", None, True):
            ranges = resolve_ranges(power_max=bad, temp_max=bad)
            self.assertEqual(ranges["power"], DEFAULT_METRIC_RANGES["power"])
            self.assertEqual(ranges["temperature"], DEFAULT_METRIC_RANGES["temperature"])

    def test_does_not_mutate_defaults(self):
        resolve_ranges(power_max=999, temp_max=999)
        self.assertEqual(DEFAULT_METRIC_RANGES["power"], (0, 140))
        self.assertEqual(DEFAULT_METRIC_RANGES["temperature"], (0, 95))

    def test_pct_to_abs_uses_resolved_range(self):
        ranges = resolve_ranges(power_max=300.0)
        # 50% of a 0–300 W scale = 150 W (vs 70 W on the default 0–140 scale).
        self.assertAlmostEqual(pct_to_abs("power", 50, ranges), 150.0, places=1)


class TestDefaultThresholds(unittest.TestCase):
    """Test DEFAULT_THRESHOLDS configuration."""

    def test_all_metrics_present(self):
        for metric in ["temperature", "utilization", "power", "system_memory"]:
            self.assertIn(metric, DEFAULT_THRESHOLDS)
            self.assertIn("warn", DEFAULT_THRESHOLDS[metric])
            self.assertIn("crit", DEFAULT_THRESHOLDS[metric])

    def test_warn_below_crit(self):
        for metric in DEFAULT_THRESHOLDS:
            self.assertLess(
                DEFAULT_THRESHOLDS[metric]["warn"],
                DEFAULT_THRESHOLDS[metric]["crit"],
                f"{metric}: warn should be < crit",
            )

    def test_default_temperature_warn(self):
        self.assertEqual(DEFAULT_THRESHOLDS["temperature"]["warn"], 90)

    def test_default_temperature_crit(self):
        self.assertEqual(DEFAULT_THRESHOLDS["temperature"]["crit"], 98)

    def test_default_utilization_warn(self):
        self.assertEqual(DEFAULT_THRESHOLDS["utilization"]["warn"], 90)

    def test_default_utilization_crit(self):
        self.assertEqual(DEFAULT_THRESHOLDS["utilization"]["crit"], 98)

    def test_warn_equals_all_metrics(self):
        for metric in DEFAULT_THRESHOLDS:
            self.assertEqual(DEFAULT_THRESHOLDS[metric]["warn"], 90)

    def test_crit_equals_all_metrics(self):
        for metric in DEFAULT_THRESHOLDS:
            self.assertEqual(DEFAULT_THRESHOLDS[metric]["crit"], 98)


class TestGaugeSizes(unittest.TestCase):
    """Test GAUGE_SIZES configuration."""

    def test_contains_normal(self):
        self.assertIn("normal", GAUGE_SIZES)

    def test_contains_small(self):
        self.assertIn("small", GAUGE_SIZES)

    def test_exactly_two_sizes(self):
        self.assertEqual(len(GAUGE_SIZES), 2)


class TestUpdateInterval(unittest.TestCase):
    """Test UPDATE_INTERVAL constants."""

    def test_min_is_one(self):
        self.assertEqual(UPDATE_INTERVAL_MIN_S, 1)

    def test_max_is_ten(self):
        self.assertEqual(UPDATE_INTERVAL_MAX_S, 10)


class TestDefaultGaugeColors(unittest.TestCase):
    """Test DEFAULT_GAUGE_COLORS configuration."""

    def test_all_metrics_present(self):
        for metric in ["temperature", "utilization", "power", "system_memory"]:
            self.assertIn(metric, DEFAULT_GAUGE_COLORS)

    def test_all_states_present(self):
        for metric in DEFAULT_GAUGE_COLORS:
            for state in ("normal", "warn", "crit"):
                self.assertIn(state, DEFAULT_GAUGE_COLORS[metric])

    def test_critical_colors_same_for_all(self):
        """All critical gauges should be #FF4500."""
        for metric in DEFAULT_GAUGE_COLORS:
            self.assertEqual(DEFAULT_GAUGE_COLORS[metric]["crit"], "#FF4500")

    def test_warn_colors_same_for_all(self):
        """All warn gauges should be #FFD700."""
        for metric in DEFAULT_GAUGE_COLORS:
            self.assertEqual(DEFAULT_GAUGE_COLORS[metric]["warn"], "#FFD700")


class TestDefaultWindowState(unittest.TestCase):
    """Test DEFAULT_WINDOW_STATE configuration."""

    def test_has_horizontal_geometry(self):
        self.assertIn("horizontal_geometry", DEFAULT_WINDOW_STATE)

    def test_has_vertical_geometry(self):
        self.assertIn("vertical_geometry", DEFAULT_WINDOW_STATE)

    def test_has_layout(self):
        self.assertEqual(DEFAULT_WINDOW_STATE["layout"], "Horizontal")

    def test_has_update_interval(self):
        self.assertEqual(DEFAULT_WINDOW_STATE["update_interval_s"], 2)

    def test_has_gauge_size(self):
        self.assertEqual(DEFAULT_WINDOW_STATE["gauge_size"], "normal")

    def test_has_thresholds(self):
        self.assertIn("thresholds", DEFAULT_WINDOW_STATE)

    def test_has_gauge_colors(self):
        self.assertIn("gauge_colors", DEFAULT_WINDOW_STATE)

    def test_default_horizontal_geometry(self):
        self.assertEqual(DEFAULT_WINDOW_STATE["horizontal_geometry"], "900x320+100+50")

    def test_default_vertical_geometry(self):
        self.assertEqual(DEFAULT_WINDOW_STATE["vertical_geometry"], "250x650+100+50")


class TestCollectGaugeColors(unittest.TestCase):
    """Test _collect_gauge_colors logic.

    The _collect_gauge_colors function in app.py collects the current colour
    for each gauge based on the latest metric value and thresholds.  The
    algorithm:
      1. If the metric value is None → use 'normal'.
      2. If metric >= crit threshold → use 'crit'.
      3. If metric >= warn threshold  → use 'warn'.
      4. Otherwise → use 'normal'.
    """

    def _collect_gauge_colors(self, metric: str, value, thresholds, gauge_colors):
        """Reproduce the _collect_gauge_colors logic."""
        if value is None:
            return gauge_colors[metric]["normal"]
        if metric in thresholds:
            crit = thresholds[metric].get("crit", 98)
            warn = thresholds[metric].get("warn", 90)
            abs_crit = _pct_to_abs(metric, crit)
            abs_warn = _pct_to_abs(metric, warn)
            if value >= abs_crit:
                return gauge_colors[metric]["crit"]
            if value >= abs_warn:
                return gauge_colors[metric]["warn"]
        return gauge_colors[metric]["normal"]

    def test_none_value_returns_normal(self):
        colors = DEFAULT_GAUGE_COLORS
        thresholds = DEFAULT_THRESHOLDS
        self.assertEqual(
            self._collect_gauge_colors("temperature", None, thresholds, colors),
            colors["temperature"]["normal"],
        )

    def test_below_warn_returns_normal(self):
        # temperature 80 < warn (85.5) → normal
        colors = DEFAULT_GAUGE_COLORS
        thresholds = DEFAULT_THRESHOLDS
        self.assertEqual(
            self._collect_gauge_colors("temperature", 80.0, thresholds, colors),
            colors["temperature"]["normal"],
        )

    def test_at_warn_returns_warn(self):
        # temperature 85.5 >= warn (85.5) → warn
        colors = DEFAULT_GAUGE_COLORS
        thresholds = DEFAULT_THRESHOLDS
        self.assertEqual(
            self._collect_gauge_colors("temperature", 85.5, thresholds, colors),
            colors["temperature"]["warn"],
        )

    def test_above_warn_returns_warn(self):
        # temperature 90 > warn (85.5) but < crit (93.1) → warn
        colors = DEFAULT_GAUGE_COLORS
        thresholds = DEFAULT_THRESHOLDS
        self.assertEqual(
            self._collect_gauge_colors("temperature", 90.0, thresholds, colors),
            colors["temperature"]["warn"],
        )

    def test_at_crit_returns_crit(self):
        # temperature 93.1 >= crit (93.1) → crit
        abs_crit = _pct_to_abs("temperature", 98)
        colors = DEFAULT_GAUGE_COLORS
        thresholds = DEFAULT_THRESHOLDS
        self.assertEqual(
            self._collect_gauge_colors("temperature", abs_crit, thresholds, colors),
            colors["temperature"]["crit"],
        )

    def test_above_crit_returns_crit(self):
        # temperature 95 >= crit (93.1) → crit
        colors = DEFAULT_GAUGE_COLORS
        thresholds = DEFAULT_THRESHOLDS
        self.assertEqual(
            self._collect_gauge_colors("temperature", 95.0, thresholds, colors),
            colors["temperature"]["crit"],
        )

    def test_utilization_color_transition(self):
        colors = DEFAULT_GAUGE_COLORS
        thresholds = DEFAULT_THRESHOLDS
        abs_warn = _pct_to_abs("utilization", 90)
        # 89.9 < warn → normal
        self.assertEqual(
            self._collect_gauge_colors("utilization", 89.9, thresholds, colors),
            colors["utilization"]["normal"],
        )
        # 90.0 >= warn → warn
        self.assertEqual(
            self._collect_gauge_colors("utilization", abs_warn, thresholds, colors),
            colors["utilization"]["warn"],
        )


if __name__ == "__main__":
    unittest.main()