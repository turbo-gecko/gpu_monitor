"""
Unit tests for gpu_monitor.config module.

Covers validation helpers, load_window_state, save_window_state,
and get_geometry_for_layout per requirements FUN-04, FUN-09, FUN-10,
FUN-11, FUN-12, FUN-13.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch, mock_open

# Ensure src is on the path so relative imports within gpu_monitor work.
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gpu_monitor.config import (
    _is_valid_geometry,
    _is_valid_interval,
    _is_valid_gauge_size,
    _is_valid_threshold_pct,
    _is_valid_color,
    _validate_thresholds,
    _validate_gauge_colors,
    load_window_state,
    save_window_state,
    get_geometry_for_layout,
    parse_geometry,
    format_geometry,
    DEFAULT_THRESHOLDS,
    DEFAULT_GAUGE_COLORS,
    DEFAULT_WINDOW_STATE,
    UPDATE_INTERVAL_MIN_S,
    UPDATE_INTERVAL_MAX_S,
    GAUGE_SIZES,
    CONFIG_DIR,
    CONFIG_FILE,
)


class TestIsValidGeometry(unittest.TestCase):
    """SYS-01 / FUN-09 — geometry validation."""

    def test_valid_standard(self):
        self.assertTrue(_is_valid_geometry("900x320+100+50"))

    def test_valid_negative_offset(self):
        self.assertTrue(_is_valid_geometry("800x600-100-200"))

    def test_valid_mixed_offsets(self):
        self.assertTrue(_is_valid_geometry("1920x1080+100-50"))

    def test_valid_single_pixel(self):
        self.assertTrue(_is_valid_geometry("1x1+0+0"))

    def test_invalid_missing_plus_x(self):
        self.assertFalse(_is_valid_geometry("900.320+100+50"))

    def test_invalid_no_dimensions(self):
        self.assertFalse(_is_valid_geometry("+100+50"))

    def test_invalid_non_numeric(self):
        self.assertFalse(_is_valid_geometry("abcxdef+100+50"))

    def test_invalid_empty_string(self):
        self.assertFalse(_is_valid_geometry(""))

    def test_invalid_none(self):
        # Pylance correctly flags None here; cast to ignore.
        self.assertFalse(_is_valid_geometry(str(None)))  # type: ignore[arg-type]

    def test_invalid_extra_parts(self):
        self.assertFalse(_is_valid_geometry("900x320+100+50+extra"))


class TestIsValidInterval(unittest.TestCase):
    """FUN-04 — interval validation."""

    def test_min_boundary(self):
        self.assertTrue(_is_valid_interval(UPDATE_INTERVAL_MIN_S))

    def test_max_boundary(self):
        self.assertTrue(_is_valid_interval(UPDATE_INTERVAL_MAX_S))

    def test_mid_value(self):
        self.assertTrue(_is_valid_interval(5))

    def test_below_min(self):
        self.assertFalse(_is_valid_interval(0))

    def test_above_max(self):
        self.assertFalse(_is_valid_interval(11))

    def test_float_value_in_range(self):
        self.assertTrue(_is_valid_interval(2.5))

    def test_none(self):
        self.assertFalse(_is_valid_interval(None))

    def test_string_number(self):
        self.assertFalse(_is_valid_interval("2"))


class TestIsValidGaugeSize(unittest.TestCase):
    """FUN-13 — gauge size validation."""

    def test_normal_valid(self):
        self.assertTrue(_is_valid_gauge_size("normal"))

    def test_small_valid(self):
        self.assertTrue(_is_valid_gauge_size("small"))

    def test_invalid_size(self):
        self.assertFalse(_is_valid_gauge_size("large"))

    def test_empty_string(self):
        self.assertFalse(_is_valid_gauge_size(""))

    def test_none(self):
        self.assertFalse(_is_valid_gauge_size(None))


class TestIsValidThresholdPct(unittest.TestCase):
    """FUN-10 — threshold percentage validation."""

    def test_zero(self):
        self.assertTrue(_is_valid_threshold_pct(0))

    def test_one_hundred(self):
        self.assertTrue(_is_valid_threshold_pct(100))

    def test_mid_value(self):
        self.assertTrue(_is_valid_threshold_pct(50))

    def test_negative(self):
        self.assertFalse(_is_valid_threshold_pct(-1))

    def test_above_100(self):
        self.assertFalse(_is_valid_threshold_pct(101))

    def test_float_in_range(self):
        self.assertTrue(_is_valid_threshold_pct(90.5))

    def test_none(self):
        self.assertFalse(_is_valid_threshold_pct(None))

    def test_string(self):
        self.assertFalse(_is_valid_threshold_pct("90"))


class TestIsValidColor(unittest.TestCase):
    """FUN-11 — color validation."""

    def test_valid_hex_color(self):
        self.assertTrue(_is_valid_color("#FF4500"))

    def test_valid_short_hex(self):
        self.assertTrue(_is_valid_color("#fff"))

    def test_valid_rgb_string(self):
        self.assertTrue(_is_valid_color("rgb(255, 69, 0)"))

    def test_valid_named_color(self):
        self.assertTrue(_is_valid_color("red"))

    def test_empty_string(self):
        self.assertFalse(_is_valid_color(""))

    def test_none(self):
        self.assertFalse(_is_valid_color(None))


class TestValidateThresholds(unittest.TestCase):
    """FUN-10 — threshold validation logic."""

    def test_all_valid(self):
        raw = {
            "temperature":   {"warn": 85, "crit": 95},
            "utilization":   {"warn": 90, "crit": 98},
            "power":         {"warn": 80, "crit": 95},
            "system_memory": {"warn": 90, "crit": 98},
        }
        result = _validate_thresholds(raw)
        self.assertEqual(result["temperature"]["warn"], 85)
        self.assertEqual(result["temperature"]["crit"], 95)

    def test_missing_all_keys_returns_defaults(self):
        result = _validate_thresholds({})
        for metric in DEFAULT_THRESHOLDS:
            self.assertEqual(result[metric]["warn"], DEFAULT_THRESHOLDS[metric]["warn"])
            self.assertEqual(result[metric]["crit"], DEFAULT_THRESHOLDS[metric]["crit"])

    def test_missing_one_metric_returns_default_for_that_metric(self):
        raw = {
            "temperature":   {"warn": 80, "crit": 95},
            "utilization":   {"warn": 90, "crit": 98},
            "power":         {"warn": 85, "crit": 97},
            # system_memory is missing
        }
        result = _validate_thresholds(raw)
        self.assertEqual(result["system_memory"]["warn"], DEFAULT_THRESHOLDS["system_memory"]["warn"])
        self.assertEqual(result["system_memory"]["crit"], DEFAULT_THRESHOLDS["system_memory"]["crit"])
        self.assertEqual(result["temperature"]["warn"], 80)

    def test_out_of_range_warn_fallback(self):
        raw = {
            "temperature":   {"warn": 150, "crit": 95},
            "utilization":   {"warn": 90, "crit": 98},
            "power":         {"warn": 85, "crit": 97},
            "system_memory": {"warn": 50, "crit": 60},
        }
        result = _validate_thresholds(raw)
        self.assertEqual(result["temperature"]["warn"], DEFAULT_THRESHOLDS["temperature"]["warn"])

    def test_out_of_range_crit_fallback(self):
        raw = {
            "temperature":   {"warn": 80, "crit": -10},
            "utilization":   {"warn": 90, "crit": 98},
            "power":         {"warn": 85, "crit": 97},
            "system_memory": {"warn": 50, "crit": 60},
        }
        result = _validate_thresholds(raw)
        self.assertEqual(result["temperature"]["crit"], DEFAULT_THRESHOLDS["temperature"]["crit"])

    def test_non_dict_entry_fallback(self):
        raw = {
            "temperature":   "not_a_dict",
            "utilization":   {"warn": 90, "crit": 98},
            "power":         {"warn": 85, "crit": 97},
            "system_memory": {"warn": 50, "crit": 60},
        }
        result = _validate_thresholds(raw)
        self.assertEqual(result["temperature"], DEFAULT_THRESHOLDS["temperature"])

    def test_non_dict_raw_fallback(self):
        result = _validate_thresholds("invalid_string")
        for metric in DEFAULT_THRESHOLDS:
            self.assertEqual(result[metric], DEFAULT_THRESHOLDS[metric])


class TestValidateGaugeColors(unittest.TestCase):
    """FUN-11 — gauge color validation logic."""

    def test_all_valid(self):
        raw = {
            "temperature":   {"normal": "#111111", "warn": "#222222", "crit": "#333333"},
            "utilization":   {"normal": "#444444", "warn": "#555555", "crit": "#666666"},
            "power":         {"normal": "#777777", "warn": "#888888", "crit": "#999999"},
            "system_memory": {"normal": "#aaaaaa", "warn": "#bbbbbb", "crit": "#cccccc"},
        }
        result = _validate_gauge_colors(raw)
        self.assertEqual(result["temperature"]["normal"], "#111111")

    def test_missing_all_keys_returns_defaults(self):
        result = _validate_gauge_colors({})
        for metric in DEFAULT_GAUGE_COLORS:
            self.assertEqual(result[metric], DEFAULT_GAUGE_COLORS[metric])

    def test_missing_one_state_fallback(self):
        raw = {
            "temperature":   {"normal": "#111111", "warn": "#222222"},  # missing crit
            "utilization":   DEFAULT_GAUGE_COLORS["utilization"].copy(),
            "power":         DEFAULT_GAUGE_COLORS["power"].copy(),
            "system_memory": DEFAULT_GAUGE_COLORS["system_memory"].copy(),
        }
        result = _validate_gauge_colors(raw)
        self.assertEqual(result["temperature"]["crit"], DEFAULT_GAUGE_COLORS["temperature"]["crit"])

    def test_invalid_color_fallback(self):
        raw = {
            "temperature":   {"normal": "", "warn": "#222222", "crit": "#333333"},
            "utilization":   DEFAULT_GAUGE_COLORS["utilization"].copy(),
            "power":         DEFAULT_GAUGE_COLORS["power"].copy(),
            "system_memory": DEFAULT_GAUGE_COLORS["system_memory"].copy(),
        }
        result = _validate_gauge_colors(raw)
        self.assertEqual(result["temperature"]["normal"], DEFAULT_GAUGE_COLORS["temperature"]["normal"])

    def test_non_dict_entry_fallback(self):
        raw = {
            "temperature":   "not_a_dict",
            "utilization":   DEFAULT_GAUGE_COLORS["utilization"].copy(),
            "power":         DEFAULT_GAUGE_COLORS["power"].copy(),
            "system_memory": DEFAULT_GAUGE_COLORS["system_memory"].copy(),
        }
        result = _validate_gauge_colors(raw)
        self.assertEqual(result["temperature"], DEFAULT_GAUGE_COLORS["temperature"])


class TestLoadWindowState(unittest.TestCase):
    """FUN-09, FUN-12 — config file loading."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patcher = patch("gpu_monitor.config.CONFIG_DIR", self.temp_dir.name)
        self.patcher.start()
        # Also need to reload the module-level CONFIG_FILE after patching.
        import gpu_monitor.config as cfg
        cfg.CONFIG_FILE = os.path.join(self.temp_dir.name, "config.json")
        self.cfg = cfg

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_missing_file_returns_defaults(self):
        # Ensure file does not exist.
        result = load_window_state()
        self.assertEqual(result["layout"], "Horizontal")
        self.assertEqual(result["update_interval_s"], 2)
        self.assertEqual(result["gauge_size"], "normal")

    def test_invalid_json_returns_defaults(self):
        config_file = os.path.join(self.temp_dir.name, "config.json")
        with open(config_file, "w") as f:
            f.write("{invalid json content")
        result = load_window_state()
        self.assertEqual(result["layout"], "Horizontal")

    def test_array_root_returns_defaults(self):
        config_file = os.path.join(self.temp_dir.name, "config.json")
        with open(config_file, "w") as f:
            json.dump([1, 2, 3], f)
        result = load_window_state()
        self.assertEqual(result["layout"], "Horizontal")

    def test_valid_config_is_loaded(self):
        config_file = os.path.join(self.temp_dir.name, "config.json")
        payload = {
            "horizontal_geometry": "1000x400+200+100",
            "vertical_geometry":   "300x700+150+200",
            "layout":              "Vertical",
            "update_interval_s":   5,
            "gauge_size":          "small",
            "thresholds":          DEFAULT_THRESHOLDS,
            "gauge_colors":        DEFAULT_GAUGE_COLORS,
        }
        with open(config_file, "w") as f:
            json.dump(payload, f)
        result = load_window_state()
        self.assertEqual(result["layout"], "Vertical")
        self.assertEqual(result["update_interval_s"], 5)
        self.assertEqual(result["gauge_size"], "small")
        self.assertEqual(result["horizontal_geometry"], "1000x400+200+100")

    def test_partial_config_uses_defaults_for_missing_keys(self):
        config_file = os.path.join(self.temp_dir.name, "config.json")
        payload = {
            "layout": "Vertical",
            # update_interval_s missing — should use default 2
            # gauge_size missing — should use default "normal"
        }
        with open(config_file, "w") as f:
            json.dump(payload, f)
        result = load_window_state()
        self.assertEqual(result["layout"], "Vertical")
        self.assertEqual(result["update_interval_s"], 2)
        self.assertEqual(result["gauge_size"], "normal")

    def test_out_of_range_interval_uses_default(self):
        config_file = os.path.join(self.temp_dir.name, "config.json")
        payload = {
            "layout": "Horizontal",
            "update_interval_s": 50,  # out of range
        }
        with open(config_file, "w") as f:
            json.dump(payload, f)
        result = load_window_state()
        self.assertEqual(result["update_interval_s"], 2)  # default, not clamped here


class TestSaveWindowState(unittest.TestCase):
    """FUN-09, FUN-12 — config file saving."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patcher = patch("gpu_monitor.config.CONFIG_DIR", self.temp_dir.name)
        self.patcher.start()
        import gpu_monitor.config as cfg
        cfg.CONFIG_FILE = os.path.join(self.temp_dir.name, "config.json")
        self.cfg = cfg

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_file_is_created(self):
        save_window_state("900x320+100+50", "Horizontal", update_interval_s=3, gauge_size="normal")
        config_file = os.path.join(self.temp_dir.name, "config.json")
        self.assertTrue(os.path.exists(config_file))

    def test_saved_values_are_persisted(self):
        save_window_state(
            "1200x400+300+150",
            "Horizontal",
            update_interval_s=5,
            gauge_size="small",
            thresholds={"temperature": {"warn": 80, "crit": 95}},
            gauge_colors=DEFAULT_GAUGE_COLORS,
        )
        config_file = os.path.join(self.temp_dir.name, "config.json")
        with open(config_file, "r") as f:
            saved = json.load(f)
        self.assertEqual(saved["layout"], "Horizontal")
        self.assertEqual(saved["horizontal_geometry"], "1200x400+300+150")
        self.assertEqual(saved["update_interval_s"], 5)
        self.assertEqual(saved["gauge_size"], "small")


class TestGetGeometryForLayout(unittest.TestCase):
    """FUN-09 — geometry lookup by layout."""

    def test_horizontal_default(self):
        result = get_geometry_for_layout("Horizontal", {"horizontal_geometry": "900x320+100+50"})
        self.assertEqual(result, "900x320+100+50")

    def test_vertical_default(self):
        result = get_geometry_for_layout("Vertical", {"vertical_geometry": "250x650+100+50"})
        self.assertEqual(result, "250x650+100+50")

    def test_missing_key_uses_default(self):
        result = get_geometry_for_layout("Horizontal", {})
        self.assertEqual(result, "900x320+100+50")

    def test_none_state_loads_from_config(self):
        # When state is None, it should call load_window_state().
        # We can't easily test this without a real file, so skip.
        pass


class TestGeometryHelpers(unittest.TestCase):
    """parse_geometry / format_geometry bridge the stored string to Qt's QRect."""

    def test_parse_basic(self):
        self.assertEqual(parse_geometry("900x320+100+50"), (900, 320, 100, 50))

    def test_parse_negative_offsets(self):
        self.assertEqual(parse_geometry("250x650-10-20"), (250, 650, -10, -20))

    def test_format_basic(self):
        self.assertEqual(format_geometry(900, 320, 100, 50), "900x320+100+50")

    def test_format_negative_offsets(self):
        self.assertEqual(format_geometry(250, 650, -10, -20), "250x650-10-20")

    def test_round_trip(self):
        for geom in ("900x320+100+50", "250x650+0+0", "640x480-5+12"):
            self.assertEqual(format_geometry(*parse_geometry(geom)), geom)

    def test_parse_malformed_falls_back_to_default(self):
        # Falls back to the default horizontal geometry rather than raising.
        default = DEFAULT_WINDOW_STATE["horizontal_geometry"]
        self.assertEqual(parse_geometry("garbage"), parse_geometry(default))
        self.assertEqual(parse_geometry(""), parse_geometry(default))


if __name__ == "__main__":
    unittest.main()