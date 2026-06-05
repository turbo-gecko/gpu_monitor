import os
import json
import re

# ── Paths ─────────────────────────────────────────────────────────────────────
CONFIG_DIR  = os.path.join(os.path.expanduser("~"), ".config", "gpu_monitor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LOG_FILE    = os.path.join(os.path.expanduser("~"), ".gpu_monitor.log")

# ── Interval constants ────────────────────────────────────────────────────────
UPDATE_INTERVAL_MIN_S = 1
UPDATE_INTERVAL_MAX_S = 10
UPDATE_INTERVAL_MS    = 2000

# ── Gauge sizes ───────────────────────────────────────────────────────────────
# Normal canvas: 200×200 px; small canvas: 100×100 px (FUN-13)
GAUGE_SIZES = ("normal", "small")

# ── Per-metric gauge colours (FUN-11) ─────────────────────────────────────────
DEFAULT_GAUGE_COLORS = {
    "temperature":   {"normal": "#4CAF50", "warn": "#FFD700", "crit": "#FF4500"},
    "utilization":   {"normal": "#2196F3", "warn": "#FFD700", "crit": "#FF4500"},
    "power":         {"normal": "#FF9800", "warn": "#FFD700", "crit": "#FF4500"},
    "system_memory": {"normal": "#9C27B0", "warn": "#FFD700", "crit": "#FF4500"},
}

# ── Thresholds as % of full-scale (FUN-10) ────────────────────────────────────
# All values in the range [0, 100] representing percentage of each gauge's
# full-scale (max_val − min_val).  Defaults: 90 % warn / 98 % crit.
# For system_memory, the default is stored as a percentage but applied as
# absolute GB values at runtime (see app.py).
DEFAULT_THRESHOLDS = {
    "temperature":   {"warn": 90, "crit": 98},
    "utilization":   {"warn": 90, "crit": 98},
    "power":         {"warn": 90, "crit": 98},
    "system_memory": {"warn": 90, "crit": 98},
}

# ── App-chrome colours (not user-configurable) ────────────────────────────────
COLORS = {
    "bg":             "#1e1e1e",
    "menu_bg":        "#2d2d2d",
    "menu_active_bg": "#404040",
    "text_main":      "white",
    "text_dim":       "#aaaaaa",
    "text_muted":     "#666666",
}

# ── Full default window state (FUN-09, FUN-12) ────────────────────────────────
# Geometry strings include a +X+Y position so the window is always placed at a
# known screen location on first launch (FUN-09).
DEFAULT_WINDOW_STATE = {
    "horizontal_geometry": "900x320+100+50",
    "vertical_geometry":   "250x650+100+50",
    "layout":              "Horizontal",
    "update_interval_s":   2,
    "gauge_size":          "normal",
    "thresholds":          DEFAULT_THRESHOLDS,
    "gauge_colors":        DEFAULT_GAUGE_COLORS,
}


# ── Validation helpers ────────────────────────────────────────────────────────
_GEOMETRY_RE = re.compile(r'^\d+x\d+[+-]\d+[+-]\d+$')


def _is_valid_geometry(value: str) -> bool:
    return isinstance(value, str) and bool(_GEOMETRY_RE.match(value))


def _is_valid_interval(value) -> bool:
    return isinstance(value, (int, float)) and UPDATE_INTERVAL_MIN_S <= value <= UPDATE_INTERVAL_MAX_S


def _is_valid_gauge_size(value) -> bool:
    return value in GAUGE_SIZES


def _is_valid_threshold_pct(value) -> bool:
    return isinstance(value, (int, float)) and 0 <= value <= 100


def _is_valid_color(value) -> bool:
    """Accept any non-empty string (Tkinter will raise its own error on bad colours)."""
    return isinstance(value, str) and len(value) > 0


def _validate_thresholds(raw) -> dict:
    """Return validated threshold dict, falling back per-key to defaults."""
    result = {}
    for metric, defaults in DEFAULT_THRESHOLDS.items():
        if not isinstance(raw, dict) or metric not in raw:
            result[metric] = defaults.copy()
            continue
        entry = raw[metric]
        if not isinstance(entry, dict):
            result[metric] = defaults.copy()
            continue
        warn = entry.get("warn")
        crit = entry.get("crit")
        if not _is_valid_threshold_pct(warn) or not _is_valid_threshold_pct(crit):
            result[metric] = defaults.copy()
        else:
            result[metric] = {"warn": warn, "crit": crit}
    return result


def _validate_gauge_colors(raw) -> dict:
    """Return validated gauge-colour dict, falling back per-key to defaults."""
    result = {}
    for metric, defaults in DEFAULT_GAUGE_COLORS.items():
        if not isinstance(raw, dict) or metric not in raw:
            result[metric] = defaults.copy()
            continue
        entry = raw[metric]
        if not isinstance(entry, dict):
            result[metric] = defaults.copy()
            continue
        validated = {}
        for state in ("normal", "warn", "crit"):
            val = entry.get(state)
            validated[state] = val if _is_valid_color(val) else defaults[state]
        result[metric] = validated
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def load_window_state() -> dict:
    """
    Load all user-configurable settings from CONFIG_FILE.

    If the file is absent, unparseable, or contains any key that is outside
    its permitted range the function silently falls back to ALL hardcoded
    defaults and continues normally (FUN-12).
    """
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)  # raises json.JSONDecodeError on bad JSON
        if not isinstance(raw, dict):
            raise ValueError("config root is not a JSON object")
    except (IOError, OSError, json.JSONDecodeError, ValueError):
        return _deep_copy_defaults()

    state = _deep_copy_defaults()

    # Layout
    if raw.get("layout") in ("Horizontal", "Vertical"):
        state["layout"] = raw["layout"]

    # Per-layout geometries
    for key in ("horizontal_geometry", "vertical_geometry"):
        val = raw.get(key)
        if _is_valid_geometry(str(val) if val else ""):
            state[key] = val

    # Update interval
    val = raw.get("update_interval_s")
    if _is_valid_interval(val):
        state["update_interval_s"] = int(val)

    # Gauge size
    val = raw.get("gauge_size")
    if _is_valid_gauge_size(val):
        state["gauge_size"] = val

    # Thresholds and colours (partial-key fallback handled inside helpers)
    state["thresholds"]   = _validate_thresholds(raw.get("thresholds"))
    state["gauge_colors"] = _validate_gauge_colors(raw.get("gauge_colors"))

    return state


def save_window_state(
    geometry: str,
    layout: str,
    update_interval_s: int = 2,
    gauge_size: str = "normal",
    thresholds: dict | None = None,
    gauge_colors: dict | None = None,
) -> None:
    """
    Persist all user-configurable settings to CONFIG_FILE (FUN-09, FUN-12).

    Reads the existing file first so that per-layout geometries saved under
    other layouts are not overwritten.
    """
    # Ensure the config directory exists (FUN-09)
    os.makedirs(CONFIG_DIR, exist_ok=True)

    # Load whatever is already on disk (best-effort)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if not isinstance(saved, dict):
            saved = {}
    except (IOError, OSError, json.JSONDecodeError):
        saved = {}

    # Update per-layout geometry key
    saved[layout.lower() + "_geometry"] = geometry
    saved["layout"] = layout
    # Clamp and persist the update interval (FUN-04)
    saved["update_interval_s"] = max(
        UPDATE_INTERVAL_MIN_S, min(UPDATE_INTERVAL_MAX_S, int(update_interval_s))
    )
    saved["gauge_size"] = gauge_size if gauge_size in GAUGE_SIZES else "normal"

    if thresholds is not None:
        saved["thresholds"] = thresholds
    elif "thresholds" not in saved:
        saved["thresholds"] = DEFAULT_THRESHOLDS

    if gauge_colors is not None:
        saved["gauge_colors"] = gauge_colors
    elif "gauge_colors" not in saved:
        saved["gauge_colors"] = DEFAULT_GAUGE_COLORS

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(saved, f, indent=2)
    except (IOError, OSError):
        pass  # non-fatal — settings simply won't survive restart


def get_geometry_for_layout(layout: str, state: dict | None = None) -> str:
    """
    Return the persisted geometry string for *layout*, or the default.

    Accepts an already-loaded *state* dict to avoid a redundant file read.
    """
    if state is None:
        state = load_window_state()
    key = layout.lower() + "_geometry"
    return state.get(key, DEFAULT_WINDOW_STATE.get(key, "900x320+100+50"))


def _deep_copy_defaults() -> dict:
    """Return a deep copy of DEFAULT_WINDOW_STATE safe for mutation."""
    import copy
    return copy.deepcopy(DEFAULT_WINDOW_STATE)


