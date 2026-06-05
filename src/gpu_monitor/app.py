import queue
import threading
import tkinter as tk
from tkinter import messagebox, colorchooser

from .config import (
    COLORS, UPDATE_INTERVAL_MIN_S, UPDATE_INTERVAL_MAX_S,
    DEFAULT_THRESHOLDS, DEFAULT_GAUGE_COLORS,
    load_window_state, save_window_state, get_geometry_for_layout,
)
from .metrics import MetricsFetcher
from .scaling import pct_to_abs, resolve_ranges
from .ui_components import Gauge
from .logger import log_threshold_breach


class GPUMonitorApp:
    """Main Application class for the GPU & System Monitor."""

    def __init__(self, root):
        self.root = root
        self.root.title("NVIDIA GPU & System Monitor")
        self.root.configure(bg=COLORS["bg"])

        # ── Load persisted state (FUN-12) ─────────────────────────────────────
        self._state = load_window_state()
        layout      = self._state.get("layout", "Horizontal")
        interval_s  = self._state.get("update_interval_s", 2)
        self._thresholds_pct = self._state.get("thresholds",   DEFAULT_THRESHOLDS)
        self._gauge_colors   = self._state.get("gauge_colors", DEFAULT_GAUGE_COLORS)
        self._gauge_size     = self._state.get("gauge_size",   "normal")

        # Clamp interval (FUN-04)
        self.update_interval_ms = (
            max(UPDATE_INTERVAL_MIN_S, min(UPDATE_INTERVAL_MAX_S, int(interval_s))) * 1000
        )

        geometry = get_geometry_for_layout(layout, self._state)
        self.root.geometry(geometry)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.metrics      = MetricsFetcher()
        self.layout_var   = tk.StringVar(value=layout)
        self.current_layout = layout

        # Resolve device-correct full-scale ranges from the GPU's reported
        # limits, falling back to defaults when unavailable (e.g. no nvidia-smi).
        # Must be set before _setup_gauges, which reads it.
        limits = self.metrics.fetch_gpu_limits()
        self._metric_ranges = resolve_ranges(limits.get("power_max"),
                                             limits.get("temp_max"))

        # Background metric fetches hand their results back to the Tk thread
        # via this queue so the blocking nvidia-smi call never freezes the UI.
        self._metrics_queue = queue.Queue()

        self._setup_menu()
        self._setup_gauges()
        self._setup_bindings()

        # Apply gauge size loaded from config (FUN-13)
        if self._gauge_size == "small":
            for g in self._all_gauges():
                g.resize("small")

        if layout == "Vertical":
            self.set_vertical_layout(restoring=True)
        else:
            self.set_horizontal_layout(restoring=True)

        self._check_dependencies()
        self.update_gauges()

    # ── Dependency check (SYS-03, SYS-04) ────────────────────────────────────

    def _check_dependencies(self):
        import shutil, subprocess
        if not shutil.which("nvidia-smi"):
            messagebox.showerror(
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
                messagebox.showwarning(
                    "Permission Error — nvidia-smi Blocked",
                    "nvidia-smi requires elevated permissions on this system.\n\n"
                    "GPU metrics will be unavailable.\n\n"
                    "To fix, run this command once in a terminal:\n"
                    "    sudo chmod 4755 /usr/bin/nvidia-smi",
                )

    # ── Setup helpers ─────────────────────────────────────────────────────────

    def _setup_menu(self):
        menubar = tk.Menu(
            self.root, bg=COLORS["menu_bg"], fg=COLORS["text_main"],
            activebackground=COLORS["menu_active_bg"], activeforeground=COLORS["text_main"],
        )
        self.root.config(menu=menubar)

        layout_menu = tk.Menu(
            menubar, tearoff=0, bg=COLORS["menu_bg"], fg=COLORS["text_main"],
            activebackground=COLORS["menu_active_bg"], activeforeground=COLORS["text_main"],
        )
        menubar.add_cascade(label="Layout", menu=layout_menu)
        layout_menu.add_radiobutton(
            label="Horizontal", variable=self.layout_var,
            command=lambda: self.set_horizontal_layout(), accelerator="Ctrl+H",
        )
        layout_menu.add_radiobutton(
            label="Vertical", variable=self.layout_var,
            command=lambda: self.set_vertical_layout(), accelerator="Ctrl+V",
        )
        layout_menu.add_separator()
        layout_menu.add_command(label="Reset to Default", command=self.set_horizontal_layout)

        settings_menu = tk.Menu(
            menubar, tearoff=0, bg=COLORS["menu_bg"], fg=COLORS["text_main"],
            activebackground=COLORS["menu_active_bg"], activeforeground=COLORS["text_main"],
        )
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Preferences…", command=self._show_settings)

        help_menu = tk.Menu(
            menubar, tearoff=0, bg=COLORS["menu_bg"], fg=COLORS["text_main"],
            activebackground=COLORS["menu_active_bg"], activeforeground=COLORS["text_main"],
        )
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)
        help_menu.add_command(label="Quit", command=self.root.quit, accelerator="Ctrl+Q")

    def _setup_gauges(self):
        """Construct all four Gauge widgets, applying persisted colours and thresholds."""
        gc = self._gauge_colors
        r  = self._metric_ranges

        temp_lo, temp_hi = r["temperature"]
        self.gauge_temp = Gauge(
            self.root, "Temperature (°C)", temp_lo, temp_hi,
            normal_color=gc["temperature"]["normal"],
            warn_color=gc["temperature"]["warn"],
            crit_color=gc["temperature"]["crit"],
            warn_threshold=pct_to_abs("temperature", self._thresholds_pct["temperature"]["warn"], r),
            crit_threshold=pct_to_abs("temperature", self._thresholds_pct["temperature"]["crit"], r),
        )
        util_lo, util_hi = r["utilization"]
        self.gauge_util = Gauge(
            self.root, "GPU Utilization (%)", util_lo, util_hi,
            normal_color=gc["utilization"]["normal"],
            warn_color=gc["utilization"]["warn"],
            crit_color=gc["utilization"]["crit"],
            warn_threshold=pct_to_abs("utilization", self._thresholds_pct["utilization"]["warn"], r),
            crit_threshold=pct_to_abs("utilization", self._thresholds_pct["utilization"]["crit"], r),
        )
        power_lo, power_hi = r["power"]
        self.gauge_power = Gauge(
            self.root, "Power Usage (W)", power_lo, power_hi,
            normal_color=gc["power"]["normal"],
            warn_color=gc["power"]["warn"],
            crit_color=gc["power"]["crit"],
            warn_threshold=pct_to_abs("power", self._thresholds_pct["power"]["warn"], r),
            crit_threshold=pct_to_abs("power", self._thresholds_pct["power"]["crit"], r),
        )
        mem_lo, mem_hi = r["system_memory"]
        self.gauge_sys_mem = Gauge(
            self.root, "System Memory (%)", mem_lo, mem_hi,
            normal_color=gc["system_memory"]["normal"],
            warn_color=gc["system_memory"]["warn"],
            crit_color=gc["system_memory"]["crit"],
            warn_threshold=pct_to_abs("system_memory", self._thresholds_pct["system_memory"]["warn"], r),
            crit_threshold=pct_to_abs("system_memory", self._thresholds_pct["system_memory"]["crit"], r),
        )

    def _setup_bindings(self):
        self.root.bind("<Control-h>", lambda e: self.set_horizontal_layout())
        self.root.bind("<Control-v>", lambda e: self.set_vertical_layout())
        self.root.bind("<Control-q>", lambda e: self.root.quit())
        self.root.bind("<Alt-F4>",    lambda e: self.root.quit())

    def _all_gauges(self):
        return [self.gauge_temp, self.gauge_util, self.gauge_power, self.gauge_sys_mem]

    # ── Metric update loop ────────────────────────────────────────────────────

    def update_gauges(self):
        """
        Start one polling cycle.

        The actual metric fetch (a blocking nvidia-smi subprocess, up to 5 s)
        runs on a background thread so the Tk event loop stays responsive
        (NFR-01). The worker puts its result on ``self._metrics_queue``; the
        main thread drains it in ``_poll_metrics_queue`` and only then applies
        the UI update and schedules the next cycle. Because the next cycle is
        scheduled only after a result arrives, at most one fetch is ever
        in flight.
        """
        threading.Thread(target=self._fetch_worker, daemon=True).start()
        self._poll_metrics_queue()

    def _fetch_worker(self):
        """Run the blocking metric fetch off the Tk thread (NFR-01)."""
        gpu_stats = self.metrics.fetch_gpu_stats()
        mem_stats = self.metrics.fetch_system_memory()
        self._metrics_queue.put((gpu_stats, mem_stats))

    def _poll_metrics_queue(self):
        """Drain the worker result on the Tk thread, then apply + reschedule."""
        try:
            gpu_stats, mem_stats = self._metrics_queue.get_nowait()
        except queue.Empty:
            self.root.after(50, self._poll_metrics_queue)
            return
        self._apply_metrics(gpu_stats, mem_stats)
        self.root.after(self.update_interval_ms, self.update_gauges)

    def _apply_metrics(self, gpu_stats, mem_stats):
        """
        Update gauges and log any threshold breaches (runs on the Tk thread).

        FUN-08: a log entry is written on EVERY polling cycle in which a
        metric is at or above a threshold — not only on state transitions.
        """
        temp,  util, power          = gpu_stats if gpu_stats else (None, None, None)
        mem_used, mem_total, mem_pct = mem_stats if mem_stats else (None, None, None)

        # Temperature
        if temp is not None:
            self.gauge_temp.update_value(temp)
            if self.gauge_temp.state in ("warning", "critical"):
                log_threshold_breach("Temperature (°C)", temp, self.gauge_temp.state)
        else:
            self.gauge_temp.show_na()

        # GPU Utilisation
        if util is not None:
            self.gauge_util.update_value(util)
            if self.gauge_util.state in ("warning", "critical"):
                log_threshold_breach("GPU Utilization (%)", util, self.gauge_util.state)
        else:
            self.gauge_util.show_na()

        # Power
        if power is not None:
            self.gauge_power.update_value(power)
            if self.gauge_power.state in ("warning", "critical"):
                log_threshold_breach("Power Usage (W)", power, self.gauge_power.state)
        else:
            self.gauge_power.show_na()

        # System memory
        if mem_pct is not None:
            subtitle = (
                f"{self.metrics.format_memory_gb(mem_used)} / "
                f"{self.metrics.format_memory_gb(mem_total)}"
            )
            self.gauge_sys_mem.update_value(mem_pct, subtitle)
            if self.gauge_sys_mem.state in ("warning", "critical"):
                log_threshold_breach("System Memory (%)", mem_pct, self.gauge_sys_mem.state)
        else:
            self.gauge_sys_mem.show_na()

    # ── Layout switching ──────────────────────────────────────────────────────

    def set_horizontal_layout(self, restoring=False):
        if not restoring:
            # Remember the departing layout's current geometry in self._state so
            # switching back later restores its size/position (FUN-09). self._state
            # is the in-memory source for get_geometry_for_layout below; without
            # this it stays frozen at the values loaded on startup.
            self._state[self.current_layout.lower() + "_geometry"] = self.root.geometry()
            save_window_state(
                self.root.geometry(), self.current_layout,
                update_interval_s=self.update_interval_ms // 1000,
                gauge_size=self._gauge_size,
                thresholds=self._thresholds_pct,
                gauge_colors=self._collect_gauge_colors(),
            )
        for g in self._all_gauges():
            g.pack_forget()
        for g in self._all_gauges():
            g.pack(side="left", padx=10, pady=20)

        self.root.title("NVIDIA GPU & System Monitor (Horizontal)")
        self.layout_var.set("Horizontal")
        self.current_layout = "Horizontal"

        if not restoring:
            new_geo = get_geometry_for_layout("Horizontal", self._state)
            self._state["horizontal_geometry"] = new_geo
            save_window_state(
                new_geo, "Horizontal",
                update_interval_s=self.update_interval_ms // 1000,
                gauge_size=self._gauge_size,
                thresholds=self._thresholds_pct,
                gauge_colors=self._collect_gauge_colors(),
            )
            self.root.after(10, lambda: self.root.geometry(new_geo))

    def set_vertical_layout(self, restoring=False):
        if not restoring:
            # Remember the departing layout's geometry (see set_horizontal_layout).
            self._state[self.current_layout.lower() + "_geometry"] = self.root.geometry()
            save_window_state(
                self.root.geometry(), self.current_layout,
                update_interval_s=self.update_interval_ms // 1000,
                gauge_size=self._gauge_size,
                thresholds=self._thresholds_pct,
                gauge_colors=self._collect_gauge_colors(),
            )
        for g in self._all_gauges():
            g.pack_forget()
        for g in self._all_gauges():
            g.pack(side="top", fill="x", padx=20, pady=10)

        self.root.title("NVIDIA GPU & System Monitor (Vertical)")
        self.layout_var.set("Vertical")
        self.current_layout = "Vertical"

        if not restoring:
            new_geo = get_geometry_for_layout("Vertical", self._state)
            self._state["vertical_geometry"] = new_geo
            save_window_state(
                new_geo, "Vertical",
                update_interval_s=self.update_interval_ms // 1000,
                gauge_size=self._gauge_size,
                thresholds=self._thresholds_pct,
                gauge_colors=self._collect_gauge_colors(),
            )
            self.root.after(10, lambda: self.root.geometry(new_geo))

    # ── Settings dialog ───────────────────────────────────────────────────────

    def _show_settings(self):
        """
        Unified preferences dialog covering:
          FUN-04  Update interval
          FUN-10  Per-metric warning / critical thresholds (% of full-scale)
          FUN-11  Per-metric normal / warning / critical arc colours
          FUN-13  Gauge size (normal / small)
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("Preferences")
        dialog.configure(bg=COLORS["bg"])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        pad = {"padx": 10, "pady": 4}

        # ── Section header helper ─────────────────────────────────────────────
        def section(parent, text, row):
            tk.Label(
                parent, text=text,
                fg="#ffffff", bg=COLORS["menu_bg"],
                font=("Segoe UI", 10, "bold"),
                anchor="w", relief="flat",
            ).grid(row=row, column=0, columnspan=4, sticky="ew",
                   padx=0, pady=(12, 2))

        # ── Update interval (FUN-04) ──────────────────────────────────────────
        section(dialog, "  Update Interval", 0)
        tk.Label(
            dialog, text="Interval (seconds):",
            fg=COLORS["text_main"], bg=COLORS["bg"], font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w", **pad)
        current_s    = self.update_interval_ms // 1000
        interval_var = tk.IntVar(value=current_s)
        tk.Spinbox(
            dialog,
            from_=UPDATE_INTERVAL_MIN_S, to=UPDATE_INTERVAL_MAX_S,
            textvariable=interval_var, width=5,
            bg=COLORS["menu_bg"], fg=COLORS["text_main"],
            buttonbackground=COLORS["menu_active_bg"],
            font=("Segoe UI", 10),
        ).grid(row=1, column=1, sticky="w", **pad)

        # ── Gauge size (FUN-13) ───────────────────────────────────────────────
        section(dialog, "  Gauge Size", 2)
        size_var = tk.StringVar(value=self._gauge_size)
        for col, (label, val) in enumerate([("Normal (200×200)", "normal"),
                                            ("Small (100×100)",  "small")]):
            tk.Radiobutton(
                dialog, text=label, variable=size_var, value=val,
                bg=COLORS["bg"], fg=COLORS["text_main"],
                selectcolor=COLORS["menu_bg"],
                activebackground=COLORS["bg"], activeforeground=COLORS["text_main"],
                font=("Segoe UI", 10),
            ).grid(row=3, column=col, sticky="w", **pad)

        # ── Thresholds (FUN-10) ───────────────────────────────────────────────
        section(dialog, "  Thresholds (% of full-scale)", 4)

        METRIC_LABELS = [
            ("temperature",   "Temperature"),
            ("utilization",   "GPU Utilization"),
            ("power",         "Power"),
            ("system_memory", "System Memory"),
        ]

        # Column headers
        for col, hdr in enumerate(["Metric", "Warn %", "Crit %"], start=0):
            tk.Label(
                dialog, text=hdr,
                fg=COLORS["text_dim"], bg=COLORS["bg"],
                font=("Segoe UI", 9, "bold"),
            ).grid(row=5, column=col, sticky="w", **pad)

        thresh_vars = {}   # {metric_key: {"warn": IntVar, "crit": IntVar}}
        for i, (key, label) in enumerate(METRIC_LABELS):
            row = 6 + i
            tk.Label(
                dialog, text=label,
                fg=COLORS["text_main"], bg=COLORS["bg"], font=("Segoe UI", 10),
            ).grid(row=row, column=0, sticky="w", **pad)

            warn_var = tk.DoubleVar(value=self._thresholds_pct[key]["warn"])
            crit_var = tk.DoubleVar(value=self._thresholds_pct[key]["crit"])
            thresh_vars[key] = {"warn": warn_var, "crit": crit_var}

            for col, var in [(1, warn_var), (2, crit_var)]:
                tk.Spinbox(
                    dialog, from_=0, to=100, increment=1,
                    textvariable=var, width=6,
                    bg=COLORS["menu_bg"], fg=COLORS["text_main"],
                    buttonbackground=COLORS["menu_active_bg"],
                    font=("Segoe UI", 10),
                ).grid(row=row, column=col, sticky="w", **pad)

        # ── Gauge colours (FUN-11) ────────────────────────────────────────────
        section(dialog, "  Gauge Colours", 10)

        # Column headers
        for col, hdr in enumerate(["Metric", "Normal", "Warning", "Critical"], start=0):
            tk.Label(
                dialog, text=hdr,
                fg=COLORS["text_dim"], bg=COLORS["bg"],
                font=("Segoe UI", 9, "bold"),
            ).grid(row=11, column=col, sticky="w", **pad)

        # Map metric key -> Gauge instance
        gauge_map = {
            "temperature":   self.gauge_temp,
            "utilization":   self.gauge_util,
            "power":         self.gauge_power,
            "system_memory": self.gauge_sys_mem,
        }

        def _make_color_button(parent, row, col, gauge, attr, metric_key, state_key):
            """Create a colour-swatch button that opens the OS colour picker."""
            current = getattr(gauge, attr)
            btn = tk.Button(
                parent, bg=current, width=4,
                relief="raised", bd=2,
            )

            def _pick(b=btn, g=gauge, a=attr, mk=metric_key, sk=state_key):
                result = colorchooser.askcolor(color=getattr(g, a), parent=dialog,
                                               title=f"Choose {sk} colour")
                chosen = result[1]
                if chosen:
                    setattr(g, a, chosen)
                    b.configure(bg=chosen)
                    g.update_value(g.value)   # immediate redraw (FUN-11)

            btn.configure(command=_pick)
            btn.grid(row=row, column=col, sticky="w", **pad)

        COLOR_ATTRS = [("normal_color", "normal"), ("warn_color", "warn"), ("crit_color", "crit")]
        for i, (key, label) in enumerate(METRIC_LABELS):
            row = 12 + i
            tk.Label(
                dialog, text=label,
                fg=COLORS["text_main"], bg=COLORS["bg"], font=("Segoe UI", 10),
            ).grid(row=row, column=0, sticky="w", **pad)
            for col, (attr, state_key) in enumerate(COLOR_ATTRS, start=1):
                _make_color_button(dialog, row, col, gauge_map[key], attr, key, state_key)

        # ── OK / Cancel ───────────────────────────────────────────────────────
        def _apply():
            # ── Parse + validate thresholds first (FUN-10) ────────────────────
            # warn must not exceed crit, otherwise the warning band would be
            # unreachable (update_value checks crit before warn). Validate
            # before applying anything so a bad entry leaves all state untouched
            # and the dialog stays open for the user to fix.
            parsed = {}
            violations = []
            for key, label in METRIC_LABELS:
                try:
                    warn_pct = max(0.0, min(100.0, float(thresh_vars[key]["warn"].get())))
                    crit_pct = max(0.0, min(100.0, float(thresh_vars[key]["crit"].get())))
                except (ValueError, tk.TclError):
                    warn_pct = self._thresholds_pct[key]["warn"]
                    crit_pct = self._thresholds_pct[key]["crit"]
                if warn_pct > crit_pct:
                    violations.append(label)
                parsed[key] = {"warn": warn_pct, "crit": crit_pct}

            if violations:
                messagebox.showwarning(
                    "Invalid Thresholds",
                    "The warning threshold must not exceed the critical "
                    "threshold for:\n\n"
                    + "\n".join(f"  • {v}" for v in violations)
                    + "\n\nPlease adjust the values and try again.",
                    parent=dialog,
                )
                return  # keep the dialog open

            # Interval (FUN-04)
            try:
                chosen_s = int(interval_var.get())
            except (ValueError, tk.TclError):
                chosen_s = 2
            chosen_s = max(UPDATE_INTERVAL_MIN_S, min(UPDATE_INTERVAL_MAX_S, chosen_s))
            self.update_interval_ms = chosen_s * 1000

            # Gauge size (FUN-13)
            new_size = size_var.get()
            if new_size != self._gauge_size:
                self._gauge_size = new_size
                for g in self._all_gauges():
                    g.resize(new_size)

            # Thresholds (FUN-10) — push validated absolute values to gauges
            for key, _ in METRIC_LABELS:
                g = gauge_map[key]
                g.warn_threshold = pct_to_abs(key, parsed[key]["warn"], self._metric_ranges)
                g.crit_threshold = pct_to_abs(key, parsed[key]["crit"], self._metric_ranges)
            self._thresholds_pct = parsed

            # Persist everything
            save_window_state(
                self.root.geometry(), self.current_layout,
                update_interval_s=chosen_s,
                gauge_size=self._gauge_size,
                thresholds=self._thresholds_pct,
                gauge_colors=self._collect_gauge_colors(),
            )
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg=COLORS["bg"])
        btn_frame.grid(row=16, column=0, columnspan=4, pady=(12, 16))
        tk.Button(
            btn_frame, text="OK", command=_apply, width=8,
            bg=COLORS["menu_active_bg"], fg=COLORS["text_main"],
        ).pack(side="left", padx=6)
        tk.Button(
            btn_frame, text="Cancel", command=dialog.destroy, width=8,
            bg=COLORS["menu_active_bg"], fg=COLORS["text_main"],
        ).pack(side="left", padx=6)

        dialog.bind("<Return>", lambda e: _apply())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    # ── Persistence helpers ───────────────────────────────────────────────────

    def _collect_gauge_colors(self) -> dict:
        """Snapshot current arc colours from each Gauge instance."""
        return {
            "temperature":   {
                "normal": self.gauge_temp.normal_color,
                "warn":   self.gauge_temp.warn_color,
                "crit":   self.gauge_temp.crit_color,
            },
            "utilization":   {
                "normal": self.gauge_util.normal_color,
                "warn":   self.gauge_util.warn_color,
                "crit":   self.gauge_util.crit_color,
            },
            "power":         {
                "normal": self.gauge_power.normal_color,
                "warn":   self.gauge_power.warn_color,
                "crit":   self.gauge_power.crit_color,
            },
            "system_memory": {
                "normal": self.gauge_sys_mem.normal_color,
                "warn":   self.gauge_sys_mem.warn_color,
                "crit":   self.gauge_sys_mem.crit_color,
            },
        }

    def _on_closing(self):
        """Persist the full application state on window close (FUN-09, FUN-12)."""
        save_window_state(
            self.root.geometry(), self.current_layout,
            update_interval_s=self.update_interval_ms // 1000,
            gauge_size=self._gauge_size,
            thresholds=self._thresholds_pct,
            gauge_colors=self._collect_gauge_colors(),
        )
        self.root.quit()

    # ── About dialog ──────────────────────────────────────────────────────────

    def _show_about(self):
        messagebox.showinfo(
            "About",
            "NVIDIA GPU & System Monitor\n\n"
            "Displays GPU and system metrics in real-time.\n\n"
            "Keyboard shortcuts:\n"
            "  Ctrl+H  Horizontal layout\n"
            "  Ctrl+V  Vertical layout\n"
            "  Ctrl+Q  Quit",
        )
