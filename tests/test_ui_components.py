"""
Unit tests for gpu_monitor.ui_components.Gauge (PySide6 / QPainter widget).

These exercise the real Gauge's state/threshold logic and size switching —
not pixels. They require a QApplication; run headless with the offscreen Qt
platform plugin:

    QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_ui_components

setUpModule forces the offscreen platform so the suite also passes under the
plain ``unittest discover`` run on a machine with no display.
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtWidgets import QApplication

from gpu_monitor.ui_components import Gauge, GAUGE_CANVAS

_app = None


def setUpModule():
    global _app
    _app = QApplication.instance() or QApplication([])


def _make_gauge(warn=90, crit=98, lo=0, hi=100):
    return Gauge(
        "Test", lo, hi, normal_color="#4CAF50",
        warn_color="#FFD700", crit_color="#FF4500",
        warn_threshold=warn, crit_threshold=crit,
    )


class TestGaugeState(unittest.TestCase):
    """update_value drives the normal/warning/critical state (FUN-07)."""

    def test_below_warn_is_normal(self):
        g = _make_gauge()
        g.update_value(80)
        self.assertEqual(g.state, "normal")
        self.assertEqual(g.value, 80)

    def test_at_warn_is_warning(self):
        g = _make_gauge()
        g.update_value(90)
        self.assertEqual(g.state, "warning")

    def test_between_warn_and_crit_is_warning(self):
        g = _make_gauge()
        g.update_value(95)
        self.assertEqual(g.state, "warning")

    def test_at_crit_is_critical(self):
        g = _make_gauge()
        g.update_value(98)
        self.assertEqual(g.state, "critical")

    def test_above_crit_is_critical(self):
        g = _make_gauge()
        g.update_value(100)
        self.assertEqual(g.state, "critical")

    def test_no_thresholds_stays_normal(self):
        g = _make_gauge(warn=None, crit=None)
        g.update_value(100)
        self.assertEqual(g.state, "normal")


class TestGaugeExtent(unittest.TestCase):
    """The progress arc extent scales 0..180° across the value range."""

    def test_min_is_zero(self):
        g = _make_gauge(lo=0, hi=100)
        g.update_value(0)
        self.assertAlmostEqual(g._extent, 0.0)

    def test_half_is_ninety_degrees(self):
        g = _make_gauge(lo=0, hi=100)
        g.update_value(50)
        self.assertAlmostEqual(g._extent, 90.0)

    def test_full_is_180_degrees(self):
        g = _make_gauge(lo=0, hi=100)
        g.update_value(100)
        self.assertAlmostEqual(g._extent, 180.0)

    def test_overshoot_is_clamped(self):
        g = _make_gauge(lo=0, hi=100)
        g.update_value(150)
        self.assertAlmostEqual(g._extent, 180.0)


class TestGaugeShowNA(unittest.TestCase):
    """show_na resets the gauge to a neutral N/A display (FUN-05)."""

    def test_show_na_resets(self):
        g = _make_gauge()
        g.update_value(99)            # critical, alert active
        g.show_na()
        self.assertEqual(g.state, "normal")
        self.assertEqual(g._extent, 0.0)
        self.assertEqual(g._value_text, "N/A")
        self.assertFalse(g._alert_active)


class TestGaugeResize(unittest.TestCase):
    """set_size switches between the two size modes (FUN-13)."""

    def test_default_is_normal(self):
        g = _make_gauge()
        self.assertEqual(g.width(), GAUGE_CANVAS["normal"]["size"])

    def test_set_small(self):
        g = _make_gauge()
        g.set_size("small")
        self.assertEqual(g.width(), GAUGE_CANVAS["small"]["size"])

    def test_set_same_size_is_noop(self):
        g = _make_gauge()
        g.set_size("normal")
        self.assertEqual(g.width(), GAUGE_CANVAS["normal"]["size"])


if __name__ == "__main__":
    unittest.main()
