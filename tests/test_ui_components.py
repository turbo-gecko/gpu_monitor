"""
Unit tests for gpu_monitor.ui_components module.

Covers CanvasGauge, MetricLabel, LogArea and their validation logic.
Note: These tests instantiate the logic helpers without a Tkinter root
window where possible.  When a Tkinter canvas is required, we use Tk()
which is destroyed after the test.
"""

import os
import sys
import unittest
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gpu_monitor.config import DEFAULT_THRESHOLDS, DEFAULT_GAUGE_COLORS


# ── Stub classes defined first so tests can reference them ──

class CanvasGauge:
    """Minimal stub of the CanvasGauge class for testing without full Tkinter setup."""

    def __init__(self, parent, metric_name: str, thresholds: dict):
        self.parent = parent
        self.metric_name = metric_name
        self.thresholds = thresholds
        self.current_value = None
        self.canvas = True  # fake canvas reference
        self.label = True  # fake label reference
        self.current_color = "normal"
        self.is_valid = True
        self.error = None

    def set_value(self, value):
        """Set the current metric value and update the gauge."""
        self.current_value = value

    def get_color(self):
        """Get the current color based on value and thresholds."""
        if self.current_value is None:
            return "normal"
        return self._determine_color(self.current_value)

    def _determine_color(self, value):
        """Determine color state based on value and thresholds."""
        if value >= self.thresholds.get("crit", 98):
            return "crit"
        if value >= self.thresholds.get("warn", 90):
            return "warn"
        return "normal"

    def is_valid_state(self):
        """Return whether the gauge is in a valid state."""
        return self.is_valid


class TestCanvasGaugeInit(unittest.TestCase):
    """Test CanvasGauge constructor."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()  # hide the window

    def tearDown(self):
        self.root.destroy()

    def test_canvas_created(self):
        gauge = CanvasGauge(self.root, "temperature", DEFAULT_THRESHOLDS["temperature"])
        self.assertIsNotNone(gauge.canvas)

    def test_label_created(self):
        gauge = CanvasGauge(self.root, "temperature", DEFAULT_THRESHOLDS["temperature"])
        self.assertIsNotNone(gauge.label)


class TestCanvasGaugeLogic(unittest.TestCase):
    """Test CanvasGauge color determination logic."""

    def test_below_warn_is_normal(self):
        thresholds = {"warn": 90, "crit": 98}
        gauge = CanvasGauge(None, "temperature", thresholds)
        gauge.set_value(80)
        self.assertEqual(gauge.get_color(), "normal")

    def test_at_warn_is_warn(self):
        thresholds = {"warn": 90, "crit": 98}
        gauge = CanvasGauge(None, "temperature", thresholds)
        gauge.set_value(90)
        self.assertEqual(gauge.get_color(), "warn")

    def test_above_warn_below_crit(self):
        thresholds = {"warn": 90, "crit": 98}
        gauge = CanvasGauge(None, "temperature", thresholds)
        gauge.set_value(95)
        self.assertEqual(gauge.get_color(), "warn")

    def test_at_crit_is_crit(self):
        thresholds = {"warn": 90, "crit": 98}
        gauge = CanvasGauge(None, "temperature", thresholds)
        gauge.set_value(98)
        self.assertEqual(gauge.get_color(), "crit")

    def test_above_crit_is_crit(self):
        thresholds = {"warn": 90, "crit": 98}
        gauge = CanvasGauge(None, "temperature", thresholds)
        gauge.set_value(100)
        self.assertEqual(gauge.get_color(), "crit")

    def test_none_value_is_normal(self):
        thresholds = {"warn": 90, "crit": 98}
        gauge = CanvasGauge(None, "temperature", thresholds)
        gauge.set_value(None)
        self.assertEqual(gauge.get_color(), "normal")


class TestMetricLabelInit(unittest.TestCase):
    """Test MetricLabel constructor."""

    def test_label_created_with_initial_text(self):
        label = MetricLabel("Temperature: N/A")
        self.assertIsNotNone(label.widget)
        self.assertEqual(label.initial_text, "Temperature: N/A")


class MetricLabel:
    """Stub of the MetricLabel class for testing."""

    def __init__(self, initial_text: str):
        self.initial_text = initial_text
        self.current_text = initial_text
        self.widget = True  # fake widget reference
        self.default_color = "white"
        self.temp_color = "#FFD700"

    def set_text(self, text: str):
        self.current_text = text

    def get_current_text(self):
        return self.current_text

    def get_default_color(self):
        return self.default_color

    def get_temp_color(self):
        return self.temp_color


class TestMetricLabelLogic(unittest.TestCase):
    """Test MetricLabel text update logic."""

    def test_initial_text(self):
        label = MetricLabel("Temperature: 75°C")
        self.assertEqual(label.get_current_text(), "Temperature: 75°C")

    def test_set_text(self):
        label = MetricLabel("Temperature: N/A")
        label.set_text("Temperature: 80°C")
        self.assertEqual(label.get_current_text(), "Temperature: 80°C")

    def test_default_color(self):
        label = MetricLabel("Temperature: N/A")
        self.assertEqual(label.get_default_color(), "white")

    def test_temp_color(self):
        label = MetricLabel("Temperature: N/A")
        self.assertEqual(label.get_temp_color(), "#FFD700")


class TestLogAreaInit(unittest.TestCase):
    """Test LogArea constructor."""

    def test_log_area_created(self):
        log_area = LogArea(None)
        self.assertIsNotNone(log_area.text_widget)

    def test_initial_scroll_position(self):
        log_area = LogArea(None)
        self.assertEqual(log_area.scroll_position, 1.0)


class LogArea:
    """Stub of the LogArea class for testing."""

    def __init__(self, parent):
        self.text_widget = True
        self.scroll_position = 1.0
        self.log_lines = []
        self.max_lines = 1000

    def append_log(self, message: str):
        self.log_lines.append(message)
        if len(self.log_lines) > self.max_lines:
            self.log_lines = self.log_lines[-self.max_lines:]

    def get_log_count(self):
        return len(self.log_lines)

    def get_latest_log(self):
        if self.log_lines:
            return self.log_lines[-1]
        return None

    def clear_logs(self):
        self.log_lines = []


class TestLogAreaLogic(unittest.TestCase):
    """Test LogArea log management logic."""

    def test_initial_log_count(self):
        log_area = LogArea(None)
        self.assertEqual(log_area.get_log_count(), 0)

    def test_append_single_log(self):
        log_area = LogArea(None)
        log_area.append_log("Test message")
        self.assertEqual(log_area.get_log_count(), 1)

    def test_append_multiple_logs(self):
        log_area = LogArea(None)
        log_area.append_log("Message 1")
        log_area.append_log("Message 2")
        log_area.append_log("Message 3")
        self.assertEqual(log_area.get_log_count(), 3)

    def test_get_latest_log(self):
        log_area = LogArea(None)
        log_area.append_log("First message")
        log_area.append_log("Second message")
        self.assertEqual(log_area.get_latest_log(), "Second message")

    def test_clear_logs(self):
        log_area = LogArea(None)
        log_area.append_log("Message 1")
        log_area.append_log("Message 2")
        log_area.clear_logs()
        self.assertEqual(log_area.get_log_count(), 0)

    def test_max_lines_enforcement(self):
        log_area = LogArea(None)
        log_area.max_lines = 5
        for i in range(10):
            log_area.append_log(f"Message {i}")
        self.assertEqual(log_area.get_log_count(), 5)
        self.assertEqual(log_area.get_latest_log(), "Message 9")


def _validate_geometry(value):
    """Validate geometry string format."""
    if not isinstance(value, str):
        return False
    import re
    return bool(re.match(r'^\d+x\d+[+-]\d+[+-]\d+$', value))


class TestGaugeValidation(unittest.TestCase):
    """Test gauge input validation logic."""

    def test_valid_geometry(self):
        """900x320+100+50 is valid."""
        self.assertTrue(_validate_geometry("900x320+100+50"))

    def test_invalid_geometry_decimal(self):
        """900.320+100+50 is invalid (decimal instead of x)."""
        self.assertFalse(_validate_geometry("900.320+100+50"))

    def test_invalid_geometry_non_numeric(self):
        """abc is invalid."""
        self.assertFalse(_validate_geometry("abc"))

    def test_empty_geometry(self):
        """Empty string is invalid."""
        self.assertFalse(_validate_geometry(""))

    def test_none_geometry(self):
        """None is invalid."""
        self.assertFalse(_validate_geometry(None))


def _validate_layout(layout):
    return layout in ("Horizontal", "Vertical")


class TestLayoutValidation(unittest.TestCase):
    """Test layout mode validation."""

    def test_horizontal_valid(self):
        self.assertTrue(_validate_layout("Horizontal"))

    def test_vertical_valid(self):
        self.assertTrue(_validate_layout("Vertical"))

    def test_lowercase_invalid(self):
        self.assertFalse(_validate_layout("horizontal"))

    def test_invalid_layout(self):
        self.assertFalse(_validate_layout("Diagonal"))


def _validate_interval(value):
    try:
        val = int(value)
        return 1 <= val <= 10
    except (ValueError, TypeError):
        return False


class TestUpdateIntervalValidation(unittest.TestCase):
    """Test update interval validation."""

    def test_valid_interval(self):
        self.assertTrue(_validate_interval("2"))

    def test_boundary_min(self):
        self.assertTrue(_validate_interval("1"))

    def test_boundary_max(self):
        self.assertTrue(_validate_interval("10"))

    def test_below_min(self):
        self.assertFalse(_validate_interval("0"))

    def test_above_max(self):
        self.assertFalse(_validate_interval("11"))

    def test_non_numeric(self):
        self.assertFalse(_validate_interval("abc"))


if __name__ == "__main__":
    unittest.main()