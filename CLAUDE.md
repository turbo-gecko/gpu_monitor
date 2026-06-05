# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Tkinter desktop app that polls NVIDIA GPU metrics (via `nvidia-smi`) and Linux system memory (via `/proc/meminfo`) and renders them as live arc gauges. Linux-only, no third-party runtime dependencies (stdlib `tkinter` only), no `sudo` required. Every behavior is traceable to an `FUN-`/`SYS-`/`NFR-` requirement ID in `docs/gpu_monitor_requirements.md` — that spec is the source of truth, and the implementation matrix at the bottom of it maps each requirement to file/class/method. Read it before changing behavior.

## Commands

```bash
# Run the app (uses the project venv; nohup wrapper, paths resolved relative to the script)
./gpu_monitor.sh
# or directly:
.venv/bin/python src/main.py
# or, after `pip install -e .`, via the console entry point:
gpu-monitor

# Run the full test suite (uses stdlib unittest — pytest is NOT installed)
.venv/bin/python -m unittest discover -s tests

# Run a single test module / case / method
.venv/bin/python -m unittest tests.test_config
.venv/bin/python -m unittest tests.test_config.TestLoadWindowState
.venv/bin/python -m unittest tests.test_config.TestLoadWindowState.test_missing_file_returns_defaults
```

Tests prepend `../src` to `sys.path` themselves, so they run from the repo root without installing the package.

## Architecture

The launch logic lives in `src/gpu_monitor/cli.py:main` (creates the Tk root, hands it to `GPUMonitorApp`, runs the mainloop). `src/main.py` is a thin shim that calls it, and `pyproject.toml` exposes it as the `gpu-monitor` console script. The package lives under `src/gpu_monitor/` with a deliberate separation:

- **`metrics.py`** — `MetricsFetcher`, pure data acquisition. All fetch methods are static and return `None` (or a tuple of `None`s) on *any* failure rather than raising — missing `nvidia-smi`, non-zero exit, timeout, parse error, missing `/proc` keys. Callers rely on this `None` contract to drive the "N/A" display (FUN-05). This module has no UI or config dependency.

- **`ui_components.py`** — `Gauge`, a self-contained `tk.Frame` canvas widget. Holds its own colours and **absolute** thresholds, computes its own `state` (`"normal"`/`"warning"`/`"critical"`) on each `update_value()`. The `GAUGE_CANVAS` dict drives all dimensions for the two sizes; `resize()` re-lays-out an existing widget in place rather than rebuilding it.

- **`config.py`** — all persistence and the single source of defaults (`DEFAULT_*`, `COLORS`, `METRIC` constants). `load_window_state()` is defensive: on a missing/corrupt file, or *any* out-of-range value, it silently falls back to hardcoded defaults per-key (FUN-12) — never raises, never shows an error. `save_window_state()` read-modify-writes so per-layout geometries don't clobber each other. Config lives at `~/.config/gpu_monitor/config.json`; the breach log at `~/.gpu_monitor.log`.

- **`logger.py`** — `log_threshold_breach()`. Lazily creates a `FileHandler` on first breach (no log file until then), and logs on **every** polling cycle a metric is at/above threshold — not on state transitions (FUN-08). Recovery is never logged.

- **`app.py`** — `GPUMonitorApp`, the orchestrator. Owns the poll loop, the menu, the unified preferences dialog, layout switching, and persistence wiring. The poll loop is threaded: `update_gauges` spawns a daemon worker (`_fetch_worker`) that runs the blocking `nvidia-smi` fetch off the Tk thread and puts the result on `self._metrics_queue`; the main thread drains it in `_poll_metrics_queue`, applies the UI update in `_apply_metrics`, then schedules the next cycle. The next cycle is scheduled only after a result arrives, so at most one fetch is ever in flight (no overlap, no UI freeze).

### Two conventions that matter

1. **Percentage thresholds vs. absolute values.** Config stores all thresholds as a *percentage of each gauge's full-scale range* (0–100). `Gauge` works in *absolute* metric units. The bridge lives in **`scaling.py`** (`pct_to_abs`, `resolve_ranges`, `DEFAULT_METRIC_RANGES`) — a deliberately tkinter-free module so the logic is unit-tested directly rather than copied into the tests. The full-scale ranges are **device-aware**: at startup `app.__init__` calls `MetricsFetcher.fetch_gpu_limits()` (queries `power.max_limit` and parses the temperature ceiling from `nvidia-smi -q -d TEMPERATURE`) and feeds the result through `resolve_ranges()` into `self._metric_ranges`, which both `_setup_gauges` and the preferences dialog use. Missing/old-driver limits fall back to the conservative defaults (`temperature` 0–95, `power` 0–140; `utilization`/`system_memory` are fixed 0–100).

2. **State persists on many triggers, not just exit.** Layout changes and the preferences "OK" both call `save_window_state()`, in addition to `_on_closing`. Each call must pass the *complete* current state (geometry, layout, interval, gauge_size, thresholds, gauge_colors) gathered via `_collect_gauge_colors()` and friends — partial saves would drop settings. Geometry is saved per-layout (`horizontal_geometry`/`vertical_geometry`) so each layout reopens at its own remembered position and size.

### Testing constraint

`app.py` and `ui_components.py` import `tkinter` at module top level, so they can't be imported in a headless test run (no `$DISPLAY`). Tests therefore cover the tkinter-free modules directly: `config.py`, `metrics.py`, and `scaling.py`. When adding testable logic, put it in one of those modules (or a new tkinter-free one) rather than in `app.py` — that's exactly why the scaling logic was extracted into `scaling.py`. Avoid re-implementing production logic inside tests; import and exercise the real function.

The preferences dialog validates that `warn ≤ crit` per metric before applying anything (`app._show_settings._apply`); on violation it shows a messagebox and leaves all state untouched so the user can correct it.
