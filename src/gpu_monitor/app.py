from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QActionGroup, QColor, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup, QColorDialog, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)

from .config import (
    UPDATE_INTERVAL_MIN_S, UPDATE_INTERVAL_MAX_S,
    DEFAULT_THRESHOLDS, DEFAULT_GAUGE_COLORS,
    load_window_state, save_window_state, get_geometry_for_layout,
    parse_geometry, format_geometry,
)
from .metrics import MetricsFetcher
from .scaling import pct_to_abs, resolve_ranges, DEFAULT_METRIC_RANGES
from .ui_components import Gauge
from .logger import log_threshold_breach

# Metric metadata: (config key, display label, unit symbol).
METRIC_META = [
    ("temperature",   "Temperature",     "°C"),
    ("utilization",   "GPU Utilization", "%"),
    ("power",         "Power",           "W"),
    ("system_memory", "System Memory",   "GB"),
]
# Gauge colour attribute ↔ state key.
COLOR_ATTRS = [("normal_color", "normal"), ("warn_color", "warn"), ("crit_color", "crit")]


class _FetchWorker(QObject):
    """
    Runs the blocking metric fetch off the GUI thread (NFR-01).

    Lives on a dedicated QThread; ``fetch`` is invoked via a queued signal and
    emits ``finished`` with the result, which a main-thread slot consumes.
    """

    finished = Signal(object, object)

    def __init__(self, metrics: MetricsFetcher):
        super().__init__()
        self._metrics = metrics

    @Slot()
    def fetch(self):
        gpu_stats = self._metrics.fetch_gpu_stats()
        mem_stats = self._metrics.fetch_system_memory()
        self.finished.emit(gpu_stats, mem_stats)


class GPUMonitorApp(QMainWindow):
    """Main application window for the GPU & System Monitor."""

    # Emitted from the GUI thread to ask the worker (on its own thread) to fetch.
    _fetch_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NVIDIA GPU & System Monitor")

        # ── Load persisted state (FUN-12) ─────────────────────────────────────
        self._state = load_window_state()
        layout      = self._state.get("layout", "Horizontal")
        interval_s  = self._state.get("update_interval_s", 2)
        self._thresholds_pct = self._state.get("thresholds",   DEFAULT_THRESHOLDS)
        self._gauge_colors   = self._state.get("gauge_colors", DEFAULT_GAUGE_COLORS)
        self._gauge_size     = self._state.get("gauge_size",   "normal")
        self.current_layout  = layout

        self._total_memory_gb = None

        # Clamp interval (FUN-04)
        self.update_interval_ms = (
            max(UPDATE_INTERVAL_MIN_S, min(UPDATE_INTERVAL_MAX_S, int(interval_s))) * 1000
        )

        self.metrics = MetricsFetcher()

        # Resolve device-correct full-scale ranges from the GPU's reported limits,
        # falling back to defaults when unavailable (e.g. no nvidia-smi). Must be
        # set before _setup_gauges, which reads it.
        limits = self.metrics.fetch_gpu_limits()
        self._metric_ranges = resolve_ranges(limits.get("power_max"),
                                              limits.get("temp_max"))

        self._total_memory_gb = MetricsFetcher.fetch_total_memory_gb()
        if self._total_memory_gb is not None and self._total_memory_gb > 0:
            self._metric_ranges["system_memory"] = (0, self._total_memory_gb)
        else:
            self._metric_ranges["system_memory"] = DEFAULT_METRIC_RANGES["system_memory"]

        self._setup_gauges()
        self._setup_menu()

        # Apply persisted gauge size (FUN-13) before laying out.
        if self._gauge_size == "small":
            for g in self._all_gauges():
                g.set_size("small")

        # Apply persisted layout + geometry (FUN-09).
        self._relayout(layout)
        self.setWindowTitle(f"NVIDIA GPU & System Monitor ({layout})")
        w, h, x, y = parse_geometry(get_geometry_for_layout(layout, self._state))
        self.setGeometry(x, y, w, h)

        # Background fetch worker on its own thread.
        self._thread = QThread(self)
        self._worker = _FetchWorker(self.metrics)
        self._worker.moveToThread(self._thread)
        self._fetch_requested.connect(self._worker.fetch)
        self._worker.finished.connect(self._on_metrics)
        self._thread.start()

        self._check_dependencies()
        self.update_gauges()

    # ── Dependency check (SYS-03, SYS-04) ────────────────────────────────────

    def _check_dependencies(self):
        import shutil, subprocess
        if not shutil.which("nvidia-smi"):
            QMessageBox.critical(
                self,
                "Missing Dependency — nvidia-smi Not Found",
                "nvidia-smi was not found in PATH.\n\n"
                "GPU metrics will be unavailable until NVIDIA drivers are "
                "installed and nvidia-smi is accessible.\n\n"
                "Install drivers from: https://www.nvidia.com/drivers",
            )
            return
        probe = subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
        if probe.returncode != 0:
            err = probe.stderr.decode(errors="replace").lower()
            if "permission" in err or "not supported" in err:
                QMessageBox.warning(
                    self,
                    "Permission Error — nvidia-smi Blocked",
                    "nvidia-smi requires elevated permissions on this system.\n\n"
                    "GPU metrics will be unavailable.\n\n"
                    "To fix, run this command once in a terminal:\n"
                    "    sudo chmod 4755 /usr/bin/nvidia-smi",
                )

    # ── Setup helpers ─────────────────────────────────────────────────────────

    def _setup_menu(self):
        menubar = self.menuBar()

        layout_menu = menubar.addMenu("Layout")
        self._layout_group = QActionGroup(self)
        self._layout_group.setExclusive(True)

        act_h = layout_menu.addAction("Horizontal")
        act_h.setCheckable(True)
        act_h.setShortcut(QKeySequence("Ctrl+H"))
        act_h.triggered.connect(self.set_horizontal_layout)
        self._layout_group.addAction(act_h)

        act_v = layout_menu.addAction("Vertical")
        act_v.setCheckable(True)
        act_v.setShortcut(QKeySequence("Ctrl+V"))
        act_v.triggered.connect(self.set_vertical_layout)
        self._layout_group.addAction(act_v)

        (act_v if self.current_layout == "Vertical" else act_h).setChecked(True)
        self._act_horizontal, self._act_vertical = act_h, act_v

        layout_menu.addSeparator()
        layout_menu.addAction("Reset to Default", self.set_horizontal_layout)

        settings_menu = menubar.addMenu("Settings")
        settings_menu.addAction("Preferences…", self._show_settings)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self._show_about)
        quit_act = help_menu.addAction("Quit", self.close)
        quit_act.setShortcut(QKeySequence("Ctrl+Q"))

    def _setup_gauges(self):
        """Construct all four Gauge widgets, applying persisted colours and thresholds."""
        gc = self._gauge_colors
        r  = self._metric_ranges

        def make(key, title):
            lo, hi = r[key]
            return Gauge(
                title, lo, hi,
                normal_color=gc[key]["normal"],
                warn_color=gc[key]["warn"],
                crit_color=gc[key]["crit"],
                warn_threshold=pct_to_abs(key, self._thresholds_pct[key]["warn"], r),
                crit_threshold=pct_to_abs(key, self._thresholds_pct[key]["crit"], r),
            )

        self.gauge_temp    = make("temperature",   "Temperature (°C)")
        self.gauge_util    = make("utilization",   "GPU Utilization (%)")
        self.gauge_power   = make("power",         "Power Usage (W)")
        self.gauge_sys_mem = make("system_memory", "System Memory (GB)")

    def _all_gauges(self):
        return [self.gauge_temp, self.gauge_util, self.gauge_power, self.gauge_sys_mem]

    def _gauge_map(self):
        return {
            "temperature":   self.gauge_temp,
            "utilization":   self.gauge_util,
            "power":         self.gauge_power,
            "system_memory": self.gauge_sys_mem,
        }

    # ── Metric update loop ────────────────────────────────────────────────────

    def update_gauges(self):
        """
        Start one polling cycle by requesting a fetch on the worker thread.

        The worker emits ``finished`` when the blocking nvidia-smi call returns;
        ``_on_metrics`` applies the UI update on the GUI thread and only then
        schedules the next cycle, so at most one fetch is ever in flight (NFR-01).
        """
        self._fetch_requested.emit()

    @Slot(object, object)
    def _on_metrics(self, gpu_stats, mem_stats):
        self._apply_metrics(gpu_stats, mem_stats)
        QTimer.singleShot(self.update_interval_ms, self.update_gauges)

    def _apply_metrics(self, gpu_stats, mem_stats):
        """
        Update gauges and log any threshold breaches (runs on the GUI thread).

        FUN-08: a log entry is written on EVERY polling cycle in which a metric
        is at or above a threshold — not only on state transitions.
        """
        temp, util, power           = gpu_stats if gpu_stats else (None, None, None)
        mem_used, mem_total, mem_pct = mem_stats if mem_stats else (None, None, None)

        if temp is not None:
            self.gauge_temp.update_value(temp)
            if self.gauge_temp.state in ("warning", "critical"):
                log_threshold_breach("Temperature (°C)", temp, self.gauge_temp.state)
        else:
            self.gauge_temp.show_na()

        if util is not None:
            self.gauge_util.update_value(util)
            if self.gauge_util.state in ("warning", "critical"):
                log_threshold_breach("GPU Utilization (%)", util, self.gauge_util.state)
        else:
            self.gauge_util.show_na()

        if power is not None:
            self.gauge_power.update_value(power)
            if self.gauge_power.state in ("warning", "critical"):
                log_threshold_breach("Power Usage (W)", power, self.gauge_power.state)
        else:
            self.gauge_power.show_na()

        if mem_used is not None and mem_total is not None and mem_pct is not None:
            subtitle = f"{mem_used:.1f} GB / {mem_total:.1f} GB ({mem_pct:.0f}%)"
            self.gauge_sys_mem.update_value(mem_used, subtitle)
            if self.gauge_sys_mem.state in ("warning", "critical"):
                log_threshold_breach("System Memory (GB)", mem_used, self.gauge_sys_mem.state)
        else:
            self.gauge_sys_mem.show_na()

    # ── Layout switching ──────────────────────────────────────────────────────

    def _relayout(self, layout: str):
        """Reparent the four gauges into a fresh container with the given layout."""
        container = QWidget()
        if layout == "Vertical":
            box = QVBoxLayout(container)
            box.setContentsMargins(20, 10, 20, 10)
            box.setSpacing(10)
        else:
            box = QHBoxLayout(container)
            box.setContentsMargins(10, 20, 10, 20)
            box.setSpacing(10)
        for g in self._all_gauges():
            box.addWidget(g, alignment=Qt.AlignmentFlag.AlignCenter)
        # Replaces (and deletes) the previous central widget; gauges were already
        # reparented into ``container`` by addWidget above, so they survive.
        self.setCentralWidget(container)

    def _switch_layout(self, new_layout: str):
        # Remember the departing layout's geometry so switching back restores it
        # (FUN-09), then persist the full state.
        self._state[self.current_layout.lower() + "_geometry"] = self._current_geometry()
        save_window_state(
            self._current_geometry(), self.current_layout,
            update_interval_s=self.update_interval_ms // 1000,
            gauge_size=self._gauge_size,
            thresholds=self._thresholds_pct,
            gauge_colors=self._collect_gauge_colors(),
        )

        self._relayout(new_layout)
        self.current_layout = new_layout
        self.setWindowTitle(f"NVIDIA GPU & System Monitor ({new_layout})")
        (self._act_vertical if new_layout == "Vertical" else self._act_horizontal).setChecked(True)

        new_geo = get_geometry_for_layout(new_layout, self._state)
        self._state[new_layout.lower() + "_geometry"] = new_geo
        save_window_state(
            new_geo, new_layout,
            update_interval_s=self.update_interval_ms // 1000,
            gauge_size=self._gauge_size,
            thresholds=self._thresholds_pct,
            gauge_colors=self._collect_gauge_colors(),
        )
        w, h, x, y = parse_geometry(new_geo)
        self.setGeometry(x, y, w, h)

    def set_horizontal_layout(self):
        if self.current_layout == "Horizontal" and self.centralWidget() is not None:
            return
        self._switch_layout("Horizontal")

    def set_vertical_layout(self):
        if self.current_layout == "Vertical" and self.centralWidget() is not None:
            return
        self._switch_layout("Vertical")

    # ── Settings dialog ───────────────────────────────────────────────────────

    def _show_settings(self):
        """
        Unified preferences dialog covering:
          FUN-04  Update interval
          FUN-10  Per-metric warning / critical thresholds (native units)
          FUN-11  Per-metric normal / warning / critical arc colours
          FUN-13  Gauge size (normal / small)
        """
        PreferencesDialog(self).exec()

    # ── Persistence helpers ───────────────────────────────────────────────────

    def _current_geometry(self) -> str:
        g = self.geometry()
        return format_geometry(g.width(), g.height(), g.x(), g.y())

    def _collect_gauge_colors(self) -> dict:
        """Snapshot current arc colours from each Gauge instance."""
        gm = self._gauge_map()
        return {
            key: {
                "normal": gm[key].normal_color,
                "warn":   gm[key].warn_color,
                "crit":   gm[key].crit_color,
            }
            for key in gm
        }

    def closeEvent(self, event):  # noqa: N802 (Qt naming)
        """Persist the full application state on window close (FUN-09, FUN-12)."""
        save_window_state(
            self._current_geometry(), self.current_layout,
            update_interval_s=self.update_interval_ms // 1000,
            gauge_size=self._gauge_size,
            thresholds=self._thresholds_pct,
            gauge_colors=self._collect_gauge_colors(),
        )
        self._thread.quit()
        self._thread.wait()
        event.accept()

    # ── About dialog ──────────────────────────────────────────────────────────

    def _show_about(self):
        QMessageBox.information(
            self,
            "About",
            "NVIDIA GPU & System Monitor\n\n"
            "Displays GPU and system metrics in real-time.\n\n"
            "Keyboard shortcuts:\n"
            "  Ctrl+H  Horizontal layout\n"
            "  Ctrl+V  Vertical layout\n"
            "  Ctrl+Q  Quit",
        )


class PreferencesDialog(QDialog):
    """Modal preferences dialog (FUN-04, FUN-10, FUN-11, FUN-13)."""

    def __init__(self, app: GPUMonitorApp):
        super().__init__(app)
        self.app = app
        self.setWindowTitle("Preferences")
        self.setModal(True)

        grid = QGridLayout(self)
        row = 0

        # ── Update interval (FUN-04) ──────────────────────────────────────────
        grid.addWidget(self._header("Update Interval"), row, 0, 1, 5)
        row += 1
        grid.addWidget(QLabel("Interval (seconds):"), row, 0)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(UPDATE_INTERVAL_MIN_S, UPDATE_INTERVAL_MAX_S)
        self.interval_spin.setValue(app.update_interval_ms // 1000)
        grid.addWidget(self.interval_spin, row, 1)
        row += 1

        # ── Gauge size (FUN-13) ───────────────────────────────────────────────
        grid.addWidget(self._header("Gauge Size"), row, 0, 1, 5)
        row += 1
        self.size_group = QButtonGroup(self)
        self._rb_normal = QRadioButton("Normal (200×200)")
        self._rb_small  = QRadioButton("Small (100×100)")
        self.size_group.addButton(self._rb_normal)
        self.size_group.addButton(self._rb_small)
        (self._rb_small if app._gauge_size == "small" else self._rb_normal).setChecked(True)
        grid.addWidget(self._rb_normal, row, 0)
        grid.addWidget(self._rb_small, row, 1)
        row += 1

        # ── Thresholds (FUN-10), shown in native units ────────────────────────
        grid.addWidget(self._header("Thresholds"), row, 0, 1, 5)
        row += 1
        for col, hdr in enumerate(["Metric", "Warn", "", "Crit", ""]):
            grid.addWidget(QLabel(hdr), row, col)
        row += 1

        self.thresh_spins = {}  # {key: {"warn": QDoubleSpinBox, "crit": QDoubleSpinBox}}
        for key, label, unit in METRIC_META:
            lo, hi = app._metric_ranges[key]
            warn_abs = pct_to_abs(key, app._thresholds_pct[key]["warn"], app._metric_ranges)
            crit_abs = pct_to_abs(key, app._thresholds_pct[key]["crit"], app._metric_ranges)

            grid.addWidget(QLabel(label), row, 0)
            warn_spin = self._make_threshold_spin(lo, hi, warn_abs)
            crit_spin = self._make_threshold_spin(lo, hi, crit_abs)
            self.thresh_spins[key] = {"warn": warn_spin, "crit": crit_spin}
            grid.addWidget(warn_spin, row, 1)
            grid.addWidget(QLabel(unit), row, 2)
            grid.addWidget(crit_spin, row, 3)
            grid.addWidget(QLabel(unit), row, 4)
            row += 1

        # ── Gauge colours (FUN-11) ────────────────────────────────────────────
        grid.addWidget(self._header("Gauge Colours"), row, 0, 1, 5)
        row += 1
        for col, hdr in enumerate(["Metric", "Normal", "Warning", "Critical"]):
            grid.addWidget(QLabel(hdr), row, col)
        row += 1

        # Local working copy of colours, applied to the gauges only on OK.
        gm = app._gauge_map()
        self.colors: dict[str, dict[str, str]] = {}
        for key, _, _ in METRIC_META:
            g = gm[key]
            self.colors[key] = {
                "normal": g.normal_color,
                "warn":   g.warn_color,
                "crit":   g.crit_color,
            }
        self.color_buttons = {}
        for key, label, _ in METRIC_META:
            grid.addWidget(QLabel(label), row, 0)
            for col, (attr, state_key) in enumerate(COLOR_ATTRS, start=1):
                btn = self._make_color_button(key, state_key)
                self.color_buttons[(key, state_key)] = btn
                grid.addWidget(btn, row, col)
            row += 1

        # ── OK / Cancel ───────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        grid.addWidget(buttons, row, 0, 1, 5)

    # ── Widget factories ──────────────────────────────────────────────────────

    @staticmethod
    def _header(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; margin-top: 8px;")
        return lbl

    @staticmethod
    def _make_threshold_spin(lo, hi, value) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(float(lo), float(hi))
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setValue(float(value))
        return spin

    def _make_color_button(self, key: str, state_key: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedWidth(48)
        self._paint_button(btn, self.colors[key][state_key])
        btn.clicked.connect(lambda _=False, k=key, s=state_key: self._pick_color(k, s))
        return btn

    @staticmethod
    def _paint_button(btn: QPushButton, color: str):
        btn.setStyleSheet(f"background-color: {color}; border: 1px solid #555;")

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def _pick_color(self, key: str, state_key: str):
        current = QColor(self.colors[key][state_key])
        chosen = QColorDialog.getColor(current, self, f"Choose {state_key} colour")
        if chosen.isValid():
            hex_col = chosen.name()
            self.colors[key][state_key] = hex_col
            self._paint_button(self.color_buttons[(key, state_key)], hex_col)

    def _apply(self):
        app = self.app
        # ── Parse + validate thresholds (FUN-10) ─────────────────────────────
        # Thresholds are stored as percentages; convert the absolute spinbox
        # values back to percentages for persistence and re-validate warn ≤ crit.
        parsed = {}
        for key, label, _ in METRIC_META:
            lo, hi = app._metric_ranges[key]
            span = hi - lo if hi > lo else 1.0
            warn_abs = max(lo, min(hi, self.thresh_spins[key]["warn"].value()))
            crit_abs = max(lo, min(hi, self.thresh_spins[key]["crit"].value()))
            warn_pct = max(0.0, min(100.0, (warn_abs - lo) / span * 100.0))
            crit_pct = max(0.0, min(100.0, (crit_abs - lo) / span * 100.0))

            if warn_pct > crit_pct:
                QMessageBox.warning(
                    self, "Invalid Thresholds",
                    "The warning threshold must not exceed the critical "
                    f"threshold for:\n\n  • {label}\n\n"
                    "Please adjust the values and try again.",
                )
                return  # keep the dialog open, nothing applied

            parsed[key] = {"warn": warn_pct, "crit": crit_pct}

        # Interval (FUN-04)
        chosen_s = self.interval_spin.value()
        app.update_interval_ms = chosen_s * 1000

        # Gauge size (FUN-13)
        new_size = "small" if self._rb_small.isChecked() else "normal"
        if new_size != app._gauge_size:
            app._gauge_size = new_size
            for g in app._all_gauges():
                g.set_size(new_size)

        # Thresholds + colours pushed to the gauges.
        gm = app._gauge_map()
        for key, _, _ in METRIC_META:
            g = gm[key]
            g.warn_threshold = pct_to_abs(key, parsed[key]["warn"], app._metric_ranges)
            g.crit_threshold = pct_to_abs(key, parsed[key]["crit"], app._metric_ranges)
            g.normal_color = self.colors[key]["normal"]
            g.warn_color   = self.colors[key]["warn"]
            g.crit_color   = self.colors[key]["crit"]
            g.update_value(g.value)  # immediate redraw (FUN-11)
        app._thresholds_pct = parsed

        save_window_state(
            app._current_geometry(), app.current_layout,
            update_interval_s=chosen_s,
            gauge_size=app._gauge_size,
            thresholds=app._thresholds_pct,
            gauge_colors=app._collect_gauge_colors(),
        )
        self.accept()
