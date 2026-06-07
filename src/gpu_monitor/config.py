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

# ── MQTT publishing (FUN-14) ──────────────────────────────────────────────────
# Opt-in: disabled by default so users without a broker are unaffected. Each
# metric is published to "<hostname>/<base_topic>/<metric>" when enabled.
DEFAULT_MQTT = {
    "enabled":    False,
    "host":       "localhost",
    "port":       1883,
    "base_topic": "gpu_monitor",
}

# ── MQTT subscribe / remote monitoring (FUN-15) ───────────────────────────────
# Opt-in remote mode: instead of reading local nvidia-smi/proc, subscribe to the
# metrics another machine publishes (per FUN-14) at "<machine>/<base_topic>/+".
# Mutually exclusive with publishing (enforced on load and in the dialog).
DEFAULT_MQTT_SUBSCRIBE = {
    "enabled":    False,
    "host":       "localhost",
    "port":       1883,
    "base_topic": "gpu_monitor",
    "machine":    "",
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
    "mqtt":                DEFAULT_MQTT,
    "mqtt_subscribe":      DEFAULT_MQTT_SUBSCRIBE,
}


# ── Validation helpers ────────────────────────────────────────────────────────
_GEOMETRY_RE = re.compile(r'^\d+x\d+[+-]\d+[+-]\d+$')


def _is_valid_geometry(value: str) -> bool:
    return isinstance(value, str) and bool(_GEOMETRY_RE.match(value))


def parse_geometry(value: str) -> tuple[int, int, int, int]:
    """
    Parse an X11 geometry string ``"WxH+X+Y"`` into ``(width, height, x, y)``.

    The format is framework-agnostic (used by both Tk and the config file); this
    helper bridges the stored string to Qt's ``setGeometry(x, y, w, h)`` API.
    Falls back to the default horizontal geometry on a malformed string so the
    window always opens somewhere sensible (FUN-09, FUN-12).
    """
    m = re.match(r'^(\d+)x(\d+)([+-]\d+)([+-]\d+)$', value or "")
    if m is None:
        m = re.match(r'^(\d+)x(\d+)([+-]\d+)([+-]\d+)$',
                     DEFAULT_WINDOW_STATE["horizontal_geometry"])
    assert m is not None  # default is always well-formed
    w, h, x, y = m.groups()
    return int(w), int(h), int(x), int(y)


def format_geometry(width: int, height: int, x: int, y: int) -> str:
    """Format ``(width, height, x, y)`` back into an ``"WxH+X+Y"`` string."""
    return f"{int(width)}x{int(height)}{int(x):+d}{int(y):+d}"


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


def _is_valid_port(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535


def _validate_mqtt(raw) -> dict:
    """Return validated MQTT settings, falling back per-key to defaults."""
    result = dict(DEFAULT_MQTT)
    if not isinstance(raw, dict):
        return result
    enabled = raw.get("enabled")
    if isinstance(enabled, bool):
        result["enabled"] = enabled
    host = raw.get("host")
    if isinstance(host, str) and len(host) > 0:
        result["host"] = host
    if _is_valid_port(raw.get("port")):
        result["port"] = raw["port"]
    base_topic = raw.get("base_topic")
    if isinstance(base_topic, str) and len(base_topic) > 0:
        result["base_topic"] = base_topic
    return result


def _validate_mqtt_subscribe(raw) -> dict:
    """Return validated MQTT subscribe settings, falling back per-key to defaults."""
    result = dict(DEFAULT_MQTT_SUBSCRIBE)
    if not isinstance(raw, dict):
        return result
    enabled = raw.get("enabled")
    if isinstance(enabled, bool):
        result["enabled"] = enabled
    host = raw.get("host")
    if isinstance(host, str) and len(host) > 0:
        result["host"] = host
    if _is_valid_port(raw.get("port")):
        result["port"] = raw["port"]
    base_topic = raw.get("base_topic")
    if isinstance(base_topic, str) and len(base_topic) > 0:
        result["base_topic"] = base_topic
    machine = raw.get("machine")
    if isinstance(machine, str):  # may be empty until the user fills it in
        result["machine"] = machine
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

    # MQTT publishing and subscription (per-key fallback handled inside helpers)
    state["mqtt"]           = _validate_mqtt(raw.get("mqtt"))
    state["mqtt_subscribe"] = _validate_mqtt_subscribe(raw.get("mqtt_subscribe"))

    # Mutual exclusivity (FUN-15): publishing and subscribing can never both be
    # active. If a hand-edited config enables both, publishing wins.
    if state["mqtt"]["enabled"] and state["mqtt_subscribe"]["enabled"]:
        state["mqtt_subscribe"] = {**state["mqtt_subscribe"], "enabled": False}

    return state


def save_window_state(
    geometry: str,
    layout: str,
    update_interval_s: int = 2,
    gauge_size: str = "normal",
    thresholds: dict | None = None,
    gauge_colors: dict | None = None,
    mqtt: dict | None = None,
    mqtt_subscribe: dict | None = None,
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

    if mqtt is not None:
        saved["mqtt"] = mqtt
    elif "mqtt" not in saved:
        saved["mqtt"] = DEFAULT_MQTT

    if mqtt_subscribe is not None:
        saved["mqtt_subscribe"] = mqtt_subscribe
    elif "mqtt_subscribe" not in saved:
        saved["mqtt_subscribe"] = DEFAULT_MQTT_SUBSCRIBE

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


