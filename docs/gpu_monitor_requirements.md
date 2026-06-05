# GPU Monitor Requirements Specification
**Version**: 1.5
**Status**: Draft
**Standard**: ISO/IEC/IEEE 29148
## Change History
| Version | Date | Description | Affected IDs |
| :--- | :--- | :--- | :--- |
| 1.5 | 2026-06-06 | ISO/IEC/IEEE 29148 review: clarified threshold-to-absolute mapping, logging severity, clamping storage, multi-metric colour priority, default window position, memory full-scale, layout recalculation, performance requirement, N/A recovery, quantified stability, change history completeness | FUN-02, FUN-07, FUN-08, FUN-09, FUN-10, FUN-13, FUN-05, NFR-02, Change History |
| 1.4 | 2026-06-06 | System Memory metric now displayed in GB (absolute value) instead of percentage; Preferences thresholds now shown in native units (°C, W, GB) matching the graph | FUN-02, FUN-10 |
| 1.3 | 2026-05-29 | Resolved ambiguities: FUN-04 clamping clarified; FUN-07 decoupled from hardcoded colours; FUN-08 logging cadence and recovery behaviour defined; FUN-09/FUN-12 config file path specified; FUN-10 units and defaults defined; FUN-11 colour picker mechanism specified; FUN-13 "50% size" clarified as linear dimensions | FUN-04, FUN-07, FUN-08, FUN-09, FUN-10, FUN-11, FUN-12, FUN-13 |
| 1.2 | 2026-05-29 | Added requirements: configurable thresholds and colours (FUN-10, FUN-11), explicit window position persistence (FUN-09 amended), full config restoration (FUN-12), gauge size selection (FUN-13) | FUN-09, FUN-10–13 |
| 1.1 | 2026-05-29 | Formalization: Added IDs, priorities, and clarified performance/error behaviors | All |
| 1.0 | 2026-05-29 | Initial baseline from code analysis | All |
## 1. System Constraints & Dependencies
These constraints define the environment in which the system must operate.
**SYS-01** — **OS Support** *(High)*: The system shall run on Linux.
*Acceptance*: Successful execution on a standard Linux distribution.
**SYS-02** — **Hardware** *(High)*: The system shall require an NVIDIA GPU.
*Acceptance*: Application detects NVIDIA hardware via `nvidia-smi`.
**SYS-03** — **Driver Dependency** *(High)*: The system shall depend on `nvidia-smi` being present in the system PATH.
*Acceptance*: Application fails gracefully with a clear error if `nvidia-smi` is missing.
**SYS-04** — **Permissions** *(Medium)*: The system shall require unprivileged access to `nvidia-smi`.
*Acceptance*: Application can execute `nvidia-smi` without sudo.
**SYS-05** — **Software** *(High)*: The system shall be implemented in Python 3.x using `tkinter` for the GUI.
*Acceptance*: Application launches a GUI window on a system with Python 3 and Tkinter installed.
**SYS-06** — **Multi-GPU Selection** *(Low)*: When multiple NVIDIA GPUs are present, the user shall be able to select which GPU to monitor.
*Acceptance*: The Settings menu lists all detected NVIDIA GPUs; selecting a different GPU updates all displayed metrics to that GPU's values.
## 2. Functional Requirements
These requirements define the specific behaviors of the system.
### 2.1 Data Acquisition
**FUN-01** — **GPU Metrics** *(High)*: The system shall fetch Temperature, Utilization, and Power Draw for GPU 0.
*Acceptance*: Metrics are correctly parsed from `nvidia-smi` output.
**FUN-02** — **System Memory** *(High)*: The system shall fetch Used (in GB), Total (in GB), and Percentage of system memory via `/proc/meminfo`. The gauge shall display the used memory in GB as the primary value with the total in GB as the full-scale reference (e.g., "24.6 GB / 63.4 GB (90%)"). The percentage is retained for informational display only. The gauge full-scale range for system memory is 0 to the detected total system memory in GB (which varies per system).
*Acceptance*: The gauge shows used memory in GB matching system state, with the gauge max set dynamically to the total system memory in GB. The threshold percentage applies to the gauge full-scale (total system memory in GB). For example, with 63.4 GB total and a 90% warning threshold, the warning triggers at 57.06 GB.
**FUN-03** — **Update Frequency** *(Medium)*: The system shall update metrics every 2 seconds by default.
*Acceptance*: UI refreshes every 2000ms.
**FUN-04** — **Configurable Interval** *(Low)*: The user shall be able to configure the update interval between 1 and 10 seconds. If a value outside this range is entered, the system shall silently clamp it to the nearest bound (1 or 10). The clamped value (not the original user input) shall be stored in the configuration file.
*Acceptance*: A value of 0 is stored as 1 and applied as 1 s; a value of 15 is stored as 10 and applied as 10 s; a value of 5 is stored as 5 and applied as 5 s.
**FUN-05** — **Error Handling** *(Medium)*: If a metric cannot be fetched, the system shall display "N/A" in the UI. Once the metric becomes available again, the gauge shall revert to displaying the current value on the next successful poll without requiring an application restart.
*Acceptance*: UI shows "N/A" instead of crashing or showing 0 when data is missing. When data becomes available again, the gauge automatically restores the correct value and arc display on the next poll cycle.
### 2.2 User Interface & Interaction
**FUN-06** — **Visual Gauges** *(Medium)*: The system shall display metrics using visual gauges.
*Acceptance*: Gauges visually represent the current value relative to a scale.
**FUN-07** — **Threshold Alerts** *(Medium)*: The system shall change the gauge arc colour when a metric value exceeds a configured threshold. Colour precedence shall be: critical colour (when value is at or above critical threshold), warning colour (when value is at or above warning threshold but below critical threshold), and normal colour (when value is below the warning threshold). The arc shall be drawn in the appropriate colour based on this precedence immediately upon each metric update.
*Acceptance*: Given any configured colour set, the gauge arc reflects the correct colour band based on the precedence order (critical > warning > normal) immediately upon each metric update. If a metric exceeds both warning and critical thresholds, the critical colour is displayed.
**FUN-08** — **Event Logging** *(Low)*: The system shall write a timestamped entry to a local log file (`~/.gpu_monitor.log`) on every polling cycle in which a metric value is at or above a warning or critical threshold. Critical threshold breaches shall be logged with a "CRITICAL" severity prefix, and warning threshold breaches (but not critical) shall be logged with a "WARNING" severity prefix. No entry shall be written when a metric value is below all thresholds (i.e., recovery events are not logged).
*Acceptance*: While a metric remains above its warning threshold but below its critical threshold across three consecutive polling cycles, three distinct timestamped entries with "WARNING" prefix appear in the log file. When the metric falls below the threshold, no further entries are written. When a metric reaches the critical threshold, entries with "CRITICAL" prefix are logged instead.
**FUN-09** — **State Persistence** *(Medium)*: The system shall save the window screen position (X, Y coordinates) and size (Width, Height) independently for each layout on exit, and restore both the position and size on the next startup. On first launch with no saved geometry, the window shall be centered on the primary screen with default dimensions. All state is persisted to `~/.config/gpu_monitor/config.json`.
*Acceptance*: Window opens at the exact screen position and with the same dimensions it had when last closed, for each layout independently. On first launch, the window is centered on the primary screen. Position is persisted as part of the full geometry string (e.g. `900x320+100+50`).
**FUN-10** — **Configurable Thresholds** *(Medium)*: The user shall be able to configure the warning and critical threshold values for each gauge metric (Temperature, Utilization, Power, System Memory) via the Settings menu. All threshold values shall be stored internally as a percentage of each gauge's full-scale range (0–100%) with the default warning threshold at 90% and the default critical threshold at 98% for every metric. The threshold percentage applies to the gauge full-scale to compute the absolute trigger value: `trigger_value = (threshold_percentage / 100) × full_scale_max`. In the Settings dialog, thresholds shall be displayed and edited using the native units of each metric: °C for Temperature, % for Utilization, W (Watts) for Power, and GB for System Memory. The gauge full-scale range determines the absolute unit range (e.g., 0–95°C for temperature, 0–350 W for power when the device max is 350 W, 0–Total GB for system memory where Total GB varies per system).
*Acceptance*: Given a metric at 95% of its full-scale range, the gauge is drawn in the warning colour when the warning threshold is set to 90% and the critical threshold is set to 98%. Updated threshold values are applied immediately to gauge colouring and alert logic without restarting the application, and are persisted to `~/.config/gpu_monitor/config.json` so they survive restarts. The Settings dialog shows threshold values in native units (°C, %, W, GB) matching the corresponding gauge display units.
**FUN-11** — **Configurable Gauge Colours** *(Low)*: The user shall be able to configure the normal, warning, and critical arc colours for each gauge via the Settings menu. Colour selection shall be performed using the standard OS colour picker dialog (`tkinter.colorchooser.askcolor`).
*Acceptance*: Opening the colour picker, selecting a colour, and confirming causes the corresponding gauge arc to be redrawn in the selected colour immediately. The chosen colour is persisted to `~/.config/gpu_monitor/config.json` and restored correctly on the next startup.
**FUN-12** — **Full Configuration Restoration** *(Medium)*: The system shall restore all user-configurable settings on startup from `~/.config/gpu_monitor/config.json`, including window geometry, layout, update interval, gauge thresholds, and gauge colours. The config file is considered corrupt if it cannot be parsed as valid JSON or if any required key is absent or holds a value outside its permitted range; in either case the system shall silently fall back to all hardcoded defaults and continue to operate normally.
*Acceptance*: After a restart the application state matches the state at the previous exit for every persisted setting. When the config file is deleted or replaced with malformed JSON, the application launches successfully using hardcoded defaults without displaying an error or crashing.
**FUN-13** — **Gauge Size Selection** *(Low)*: The user shall be able to select between a normal gauge size and a small gauge size via the Settings menu. The small size shall be exactly 50% of the normal size in both the horizontal (width) and vertical (height) linear dimensions independently (e.g., a normal canvas of 200 × 200 px becomes 100 × 100 px in small mode). When gauge size changes, the window dimensions shall be recalculated to fit the gauges with appropriate margins, and the new geometry shall be persisted on next exit.
*Acceptance*: Switching to small halves the canvas width and halves the canvas height of every gauge; switching back restores the full width and full height. The window resizes to accommodate the new gauge size. The selected size is persisted to `~/.config/gpu_monitor/config.json` and restored on startup.
## 3. Non-Functional Requirements
**NFR-01** — **Resource Usage** *(Medium)*: The system shall have negligible impact on system CPU and RAM.
*Acceptance*: CPU usage of the monitor process remains < 1% on average.
**NFR-02** — **Stability** *(Medium)*: The system shall remain operational for 24+ hours without memory leaks.
*Acceptance*: RAM usage shall not increase by more than 5% between the 1-hour and 24-hour marks of continuous operation.
**NFR-03** — **Startup Performance** *(Low)*: The system shall display the first metric reading within 5 seconds of launch.
*Acceptance*: Time from application launch to first displayed metric is ≤ 5 seconds on a system with NVIDIA GPU and nvidia-smi installed.
## 4. Implementation Matrix
**Note**: The "Implemented" annotations in this matrix reflect the author's claim of implementation at the time of writing. These claims should be verified against the actual codebase before use in formal reviews. This matrix is provided for traceability purposes and is not part of the ISO/IEC/IEEE 29148 requirements standard.

This matrix traces each requirement to the source file, class, and method where it is implemented.
| Req ID | Description | File | Class / Function | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **SYS-01** | OS Support | `gpu_monitor/metrics.py` | `MetricsFetcher.fetch_system_memory()` | Reads `/proc/meminfo`; Linux-only path assumed throughout |
| **SYS-02** | NVIDIA Hardware | `gpu_monitor/metrics.py` | `MetricsFetcher.fetch_gpu_stats()` | Targets GPU 0 via `--id=0` flag passed to `nvidia-smi` |
| **SYS-03** | Driver Dependency | `gpu_monitor/metrics.py` `gpu_monitor/app.py` | `fetch_gpu_stats()` `GPUMonitorApp._check_dependencies()` | `shutil.which('nvidia-smi')` guards both call-sites; GUI messagebox surfaced on failure |
| **SYS-04** | Unprivileged Access | `gpu_monitor/metrics.py` `gpu_monitor/app.py` | `fetch_gpu_stats()` `_check_dependencies()` | No `sudo`; probe run detects permission errors and warns via messagebox |
| **SYS-05** | Python 3 / tkinter | `gpu_monitor/app.py` `gpu_monitor/ui_components.py` | `GPUMonitorApp` `Gauge` | All UI built with `tkinter`; no third-party GUI deps |
| **FUN-01** | GPU Metrics | `gpu_monitor/metrics.py` | `MetricsFetcher.fetch_gpu_stats()` | Parses temperature, utilization, and power from `nvidia-smi --query-gpu` CSV output |
| **FUN-02** | System Memory | `gpu_monitor/metrics.py` | `MetricsFetcher.fetch_system_memory()` | Reads `MemTotal` / `MemAvailable` from `/proc/meminfo`; returns used GB, total GB, and % |
| **FUN-03** | Default 2 s Interval | `gpu_monitor/config.py` `gpu_monitor/app.py` | `UPDATE_INTERVAL_MS` `GPUMonitorApp.update_gauges()` | Constant set to `2000`; passed to `tkinter.after()` in the update loop |
| **FUN-04** | Configurable Interval | `gpu_monitor/config.py` `gpu_monitor/app.py` | `UPDATE_INTERVAL_MIN_S / MAX_S` `GPUMonitorApp._show_settings()` | Spinbox bounded to [1, 10] s; value clamped on load and on save via `save_window_state()` |
| **FUN-05** | N/A on Fetch Failure | `gpu_monitor/ui_components.py` `gpu_monitor/app.py` | `Gauge.show_na()` `GPUMonitorApp.update_gauges()` | `None` return from fetchers triggers `show_na()`, which resets arc and displays `"N/A"` |
| **FUN-06** | Visual Gauges | `gpu_monitor/ui_components.py` | `Gauge` | Canvas-drawn arc gauge; arc extent scaled to value as % of `[min_val, max_val]` |
| **FUN-07** | Threshold Alerts | `gpu_monitor/ui_components.py` `gpu_monitor/config.py` | `Gauge.update_value()` `THRESHOLDS` `COLORS` | Arc fill switches between the configured normal, warning, and critical colours based on threshold comparison; icon pulses via `_pulse_alert()` |
| **FUN-08** | Event Logging | `gpu_monitor/logger.py` `gpu_monitor/app.py` | `log_threshold_breach()` `GPUMonitorApp.update_gauges()` | Lazy `logging.FileHandler` writes to `~/.gpu_monitor.log`; fired on **every polling cycle** where a metric is at or above a threshold; recovery events are not logged |
| **FUN-09** | State Persistence | `gpu_monitor/config.py` `gpu_monitor/app.py` | `save_window_state()` `load_window_state()` `GPUMonitorApp._on_closing()` | Full geometry string (including X, Y position) saved per layout to `~/.config/gpu_monitor/config.json` and restored in `__init__`; default strings must include position offset |
| **FUN-10** | Configurable Thresholds | `gpu_monitor/config.py` `gpu_monitor/app.py` `gpu_monitor/ui_components.py` | `THRESHOLDS` `GPUMonitorApp._show_settings()` `Gauge.__init__()` | **Implemented.** Settings dialog exposes warn/crit percentage fields per metric; defaults 90% warn / 98% crit; values written to `~/.config/gpu_monitor/config.json` and pushed to each `Gauge` instance at runtime |
| **FUN-11** | Configurable Gauge Colours | `gpu_monitor/config.py` `gpu_monitor/app.py` `gpu_monitor/ui_components.py` | `COLORS` `GPUMonitorApp._show_settings()` `Gauge.update_value()` | **Implemented.** `tkinter.colorchooser.askcolor` used per gauge state in settings dialog; selected values persisted to `~/.config/gpu_monitor/config.json` and applied to canvas arc on next redraw |
| **FUN-12** | Full Configuration Restoration | `gpu_monitor/config.py` `gpu_monitor/app.py` | `load_window_state()` `GPUMonitorApp.__init__()` | **Implemented.** `load_window_state()` reads `~/.config/gpu_monitor/config.json`; falls back to all hardcoded defaults silently on absent or corrupt file (invalid JSON or out-of-range values); `__init__` consumes thresholds, colours, and gauge size in addition to geometry and interval |
| **FUN-13** | Gauge Size Selection | `gpu_monitor/ui_components.py` `gpu_monitor/app.py` `gpu_monitor/config.py` | `Gauge.__init__()` `GPUMonitorApp._show_settings()` | **Implemented.** Normal canvas: 200×200 px; small canvas: 100×100 px (50% of each linear dimension independently). Size applied at construction or via a `resize()` method; selection persisted to `~/.config/gpu_monitor/config.json` |
| **NFR-01** | Low CPU Usage | `gpu_monitor/app.py` | `GPUMonitorApp.update_gauges()` | Polling via `tkinter.after()` — no busy-wait loop or background threads |
| **NFR-02** | 24 h Stability | `gpu_monitor/app.py` `gpu_monitor/ui_components.py` | `update_gauges()` `Gauge.update_value()` | Metrics overwritten in-place each cycle; no unbounded data structures accumulate |