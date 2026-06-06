# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A PySide6 (Qt) desktop app that polls NVIDIA GPU metrics (via `nvidia-smi`) and Linux system memory (via `/proc/meminfo`) and renders them as live arc gauges. Linux-only, no `sudo` required. Runtime deps: **PySide6** and **qt-material** (the chrome is themed with `apply_stylesheet(app, 'dark_teal.xml')`); the gauges themselves are custom-drawn with `QPainter`. Every behavior is traceable to an `FUN-`/`SYS-`/`NFR-` requirement ID in `docs/gpu_monitor_requirements.md` — that spec is the source of truth, and the implementation matrix at the bottom of it maps each requirement to file/class/method. Read it before changing behavior.

## Commands

```bash
# Run the app (uses the project venv; nohup wrapper, paths resolved relative to the script)
./gpu_monitor.sh
# or directly:
.venv/bin/python src/main.py
# or, after `pip install -e .`, via the console entry point:
gpu-monitor

# Run the full test suite (uses stdlib unittest — pytest is NOT installed)
# QT_QPA_PLATFORM=offscreen lets the Qt-dependent gauge tests run without a display.
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests

# Run a single test module / case / method
.venv/bin/python -m unittest tests.test_config
.venv/bin/python -m unittest tests.test_config.TestLoadWindowState
.venv/bin/python -m unittest tests.test_config.TestLoadWindowState.test_missing_file_returns_defaults
```

Tests prepend `../src` to `sys.path` themselves, so they run from the repo root without installing the package.

## Architecture

The launch logic lives in `src/gpu_monitor/cli.py:main` (creates the `QApplication`, applies the qt-material stylesheet, shows the `GPUMonitorApp` window, runs `app.exec()`). `src/main.py` is a thin shim that calls it, and `pyproject.toml` exposes it as the `gpu-monitor` console script. The package lives under `src/gpu_monitor/` with a deliberate separation:

- **`metrics.py`** — `MetricsFetcher`, pure data acquisition. All fetch methods are static and return `None` (or a tuple of `None`s) on *any* failure rather than raising — missing `nvidia-smi`, non-zero exit, timeout, parse error, missing `/proc` keys. Callers rely on this `None` contract to drive the "N/A" display (FUN-05). This module has no UI or config dependency.

- **`ui_components.py`** — `Gauge`, a self-contained `QWidget` that draws the 180° arch in `paintEvent` with `QPainter` (track + progress arc via `drawArc`, value/title/subtitle/alert text via `drawText`). Holds its own colours and **absolute** thresholds, computes its own `state` (`"normal"`/`"warning"`/`"critical"`) on each `update_value()`, then calls `self.update()` to schedule a repaint. The `GAUGE_CANVAS` dict drives all dimensions for the two sizes; `set_size()` resizes in place (named `set_size`, not `resize`, to avoid shadowing `QWidget.resize`). The pulsing alert glyph is driven by a `QTimer`, not `after()`.

- **`config.py`** — all persistence and the single source of defaults (`DEFAULT_*`, `COLORS`, `METRIC` constants). `load_window_state()` is defensive: on a missing/corrupt file, or *any* out-of-range value, it silently falls back to hardcoded defaults per-key (FUN-12) — never raises, never shows an error. `save_window_state()` read-modify-writes so per-layout geometries don't clobber each other. Geometry stays the X11 string format `"WxH+X+Y"`; `parse_geometry()`/`format_geometry()` (tkinter-free, unit-tested) bridge it to Qt's `setGeometry(x, y, w, h)` / `geometry()`. Config lives at `~/.config/gpu_monitor/config.json`; the breach log at `~/.gpu_monitor.log`.

- **`logger.py`** — `log_threshold_breach()`. Lazily creates a `FileHandler` on first breach (no log file until then), and logs on **every** polling cycle a metric is at/above threshold — not on state transitions (FUN-08). Recovery is never logged.

- **`app.py`** — `GPUMonitorApp` (a `QMainWindow`), the orchestrator. Owns the poll loop, the menu (`QMenuBar`/`QAction`, layout actions in a `QActionGroup` with `Ctrl+H`/`Ctrl+V`/`Ctrl+Q` shortcuts), the `PreferencesDialog` (a `QDialog`, also in this file), layout switching, and persistence wiring. The poll loop is threaded: a `_FetchWorker` `QObject` lives on a dedicated `QThread`; `update_gauges` emits the `_fetch_requested` signal (queued → runs the blocking `nvidia-smi` fetch off the GUI thread), the worker emits `finished`, and the main-thread slot `_on_metrics` applies the UI update in `_apply_metrics` then schedules the next cycle with `QTimer.singleShot`. The next cycle is scheduled only after a result arrives, so at most one fetch is ever in flight (no overlap, no UI freeze). Layout switching rebuilds a fresh central `QWidget` with a `QHBoxLayout`/`QVBoxLayout` and re-parents the four gauges into it. Persistence on close is via the `closeEvent` override (which also stops the worker thread).

### Two conventions that matter

1. **Percentage thresholds vs. absolute values.** Config stores all thresholds as a *percentage of each gauge's full-scale range* (0–100). `Gauge` works in *absolute* metric units. The bridge lives in **`scaling.py`** (`pct_to_abs`, `resolve_ranges`, `DEFAULT_METRIC_RANGES`) — a deliberately tkinter-free module so the logic is unit-tested directly rather than copied into the tests. The full-scale ranges are **device-aware**: at startup `app.__init__` calls `MetricsFetcher.fetch_gpu_limits()` (queries `power.max_limit` and parses the temperature ceiling from `nvidia-smi -q -d TEMPERATURE`) and feeds the result through `resolve_ranges()` into `self._metric_ranges`, which both `_setup_gauges` and the preferences dialog use. Missing/old-driver limits fall back to the conservative defaults (`temperature` 0–95, `power` 0–140; `utilization`/`system_memory` are fixed 0–100).

2. **State persists on many triggers, not just exit.** Layout changes and the preferences "OK" both call `save_window_state()`, in addition to the `closeEvent` override. Each call must pass the *complete* current state (geometry, layout, interval, gauge_size, thresholds, gauge_colors) gathered via `_collect_gauge_colors()` and friends — partial saves would drop settings. Geometry is saved per-layout (`horizontal_geometry`/`vertical_geometry`) so each layout reopens at its own remembered position and size.

### Testing constraint

`app.py` and `ui_components.py` import PySide6, and constructing any widget needs a `QApplication` + a Qt platform plugin. Tests run headless by forcing `QT_QPA_PLATFORM=offscreen` (set both in `tests/test_ui_components.py` via `os.environ.setdefault` and recommended on the command line). The pure-logic modules — `config.py`, `metrics.py`, `scaling.py` — have no Qt dependency and are tested directly. `tests/test_ui_components.py` exercises the real `Gauge` (state/extent/`show_na`/`set_size`) under offscreen Qt rather than re-implementing its logic. When adding testable logic, prefer the Qt-free modules (e.g. the geometry helpers in `config.py`, the scaling logic in `scaling.py`).

The preferences dialog validates that `warn ≤ crit` per metric before applying anything (`PreferencesDialog._apply`); on violation it shows a `QMessageBox` and leaves all state untouched so the user can correct it.
