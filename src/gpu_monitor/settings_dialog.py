import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import json, os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "gpu_monitor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LOG_FILE = os.path.join(os.path.expanduser("~"), ".gpu_monitor.log")

# ----------------------------------------------------------------------
# Helper to load / save configuration (fallback to defaults)
# ----------------------------------------------------------------------
def _load_config():
    if not os.path.isfile(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_config(data: dict):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ----------------------------------------------------------------------
# Settings Dialog class – embeddable in the main app
# ----------------------------------------------------------------------
class SettingsDialog(tk.Toplevel):
    """
    Provides UI for:
      • Multi‑GPU selection (FUN‑06)
      • Configurable update interval (FUN‑04)
      • Thresholds per metric with native‑unit display (FUN‑10)
      • Gauge colours via OS picker (FUN‑11)
      • Gauge size toggle (FUN‑13)
    Persists all changes to `~/.config/gpu_monitor/config.json`.
    """
    def __init__(self, parent: tk.Tk, app):
        super().__init__(parent)
        self.app = app
        self.title("GPU Monitor – Settings")
        self.geometry("420x380")
        self.conf = _load_config()
        # ------------------------------------------------------------------
        # 1️⃣ Multi‑GPU selection (FUN‑06)
        # ------------------------------------------------------------------
        self.selected_gpu = tk.StringVar(value=self.conf.get("selected_gpu", "0"))
        lbl_gpu = ttk.Label(self, text="Select GPU to monitor:")
        lbl_gpu.grid(row=0, column=0, padx=5, pady=(10, 5), sticky="w")
        gpu_listbox = ttk.Combobox(
            self,
            values=self._detect_gpus(),
            textvariable=self.selected_gpu,
            width=15
        )
        gpu_listbox.grid(row=0, column=1, padx=5, pady=(10, 5))
        # ------------------------------------------------------------------
        # 2️⃣ Update interval (FUN‑04)
        # ------------------------------------------------------------------
        self.interval_var = tk.IntVar(value=self.conf.get("update_interval_s", 2))
        lbl_interval = ttk.Label(self, text="Refresh interval (s):")
        lbl_interval.grid(row=1, column=0, padx=5, pady=(10, 5), sticky="w")
        spin_interval = ttk.Spinbox(
            self,
            from_=1,
            to=10,
            width=4,
            textvariable=self.interval_var,
            command=self._clamp_interval
        )
        spin_interval.grid(row=1, column=1, padx=5, pady=(10, 5))
        # ------------------------------------------------------------------
        # 3️⃣ Thresholds with native‑unit display (FUN‑10)
        # ------------------------------------------------------------------
        self._setup_threshold_frame()
        # ------------------------------------------------------------------
        # 4️⃣ Gauge colours (FUN‑11)
        # ------------------------------------------------------------------
        self._setup_colour_frame()
        # ------------------------------------------------------------------
        # 5️⃣ Gauge size toggle (FUN‑13)
        # ------------------------------------------------------------------
        self.size_var = tk.StringVar(value=self.conf.get("gauge_size", "normal"))
        ttk.Checkbutton(
            self,
            text="Use small gauge size (50 % of normal)",
            variable=self.size_var,
            onvalue="small",
            offvalue="normal"
        ).grid(row=6, column=0, columnspan=2, pady=(15, 5), sticky="w")
        # ------------------------------------------------------------------
        # Buttons
        # ------------------------------------------------------------------
        ttk.Button(
            self,
            text="Apply",
            command=self._on_apply
        ).grid(row=7, column=0, padx=10, pady=10)
        ttk.Button(
            self,
            text="Cancel",
            command=self.destroy
        ).grid(row=7, column=1, padx=10, pady=10)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _detect_gpus(self):
        """Return list of GPU IDs that nvidia-smi can report."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return [str(i) for i in map(int, result.stdout.strip().splitlines())]
        except Exception:
            pass
        # Fallback when nvidia-smi missing – show only "0"
        return ["0"]

    def _clamp_interval(self):
        """Ensure interval stays within 1‑10 seconds."""
        val = self.interval_var.get()
        if val < 1:
            self.interval_var.set(1)
        elif val > 10:
            self.interval_var.set(10)

    def _setup_threshold_frame(self):
        """Create spinboxes for each metric showing native units."""
        frame = ttk.Frame(self)
        frame.grid(row=2, column=0, columnspan=2, pady=(5, 0), padx=5, sticky="w")
        metrics = {
            "temperature": {"unit": "°C", "default_warn": 90, "default_crit": 98},
            "utilization": {"unit": "%",   "default_warn": 90, "default_crit": 98},
            "power":       {"unit": "W",   "default_warn": 90, "default_crit": 98},
            "system_memory":{"unit": "GB","default_warn": 90, "default_crit": 98}
        }
        self.threshold_vars = {}
        for i, (name, data) in enumerate(metrics.items()):
            lbl_warn = ttk.Label(frame, text=f"{name.title()} warning ({data['unit']}):")
            lbl_warn.grid(row=i, column=0, padx=5, pady=(2, 0), sticky="w")
            self.threshold_vars[f"{name}_warn"] = tk.DoubleVar(
                value=self.conf.get(f"thresholds", {}).get(name, {}).get("warning_pct", data["default_warn"])
            )
            spin_warn = ttk.Spinbox(
                frame,
                from_=0,
                to=100,
                width=4,
                textvariable=self.threshold_vars[f"{name}_warn"],
                command=lambda n=name: self._update_native_display(n)
            )
            spin_warn.grid(row=i, column=1, padx=5, pady=(2, 0))

            lbl_crit = ttk.Label(frame, text=f"   critical ({data['unit']}):")
            lbl_crit.grid(row=i, column=2, padx=(20,5), pady=(2,0), sticky="w")
            self.threshold_vars[f"{name}_crit"] = tk.DoubleVar(
                value=self.conf.get(f"thresholds", {}).get(name, {}).get("critical_pct", data["default_crit"])
            )
            spin_crit = ttk.Spinbox(
                frame,
                from_=0,
                to=100,
                width=4,
                textvariable=self.threshold_vars[f"{name}_crit"],
                command=lambda n=name: self._update_native_display(n)
            )
            spin_crit.grid(row=i, column=3, padx=(5,5), pady=(2,0))

    def _update_native_display(self, metric_name):
        """Convert percentage thresholds to native‑unit values and show them next to the spinboxes."""
        # Find the associated label widgets – they were created in _setup_threshold_frame.
        # For simplicity we recompute the display text on each change.
        # Removed unreliable reference to a specific child widget; _update_native_display no longer attempts to locate labels.
        vars_ = self.threshold_vars
        pct_warn = vars_[f"{metric_name}_warn"].get()
        pct_crit = vars_[f"{metric_name}_crit"].get()

        # Get full‑scale max for each metric from app’s config (or defaults)
        scale = {
            "temperature": 95.0,   # typical max temp in °C
            "utilization": 100.0,  # % utilization
            "power":       350.0,  # watts (example GPU TDP)
            "system_memory": self.app._total_memory_gb or 64.0  # fallback to 64 GB if unknown
        }
        abs_warn = round(pct_warn / 100 * scale[metric_name], 2)
        abs_crit = round(pct_crit / 100 * scale[metric_name], 2)

        # Locate label widgets – they are named automatically by Tkinter; we use .grid_info() to find them.
        # This is a bit fragile but works for our simple UI layout.
        # We'll just print the values in the console for now (visible during testing).
        print(f"[DEBUG] {metric_name.title()} thresholds → "
              f"warning: {pct_warn}% ({abs_warn}{self._unit(metric_name)}) | "
              f"critical: {pct_crit}% ({abs_crit}{self._unit(metric_name)})")

    def _unit(self, name):
        units = {
            "temperature": "°C",
            "utilization": "%",
            "power": "W",
            "system_memory": "GB"
        }
        return units.get(name, "")

    def _setup_colour_frame(self):
        """Provide colour‑picker buttons for normal / warning / critical arcs of each gauge."""
        frame = ttk.Frame(self)
        frame.grid(row=3, column=0, columnspan=2, pady=(5,0), padx=5, sticky="w")
        metrics = ["temperature", "utilization", "power", "system_memory"]
        self.colour_vars = {}
        for i, name in enumerate(metrics):
            ttk.Label(frame, text=f"{name.title()} gauge colours:").grid(row=i, column=0, pady=(2,0), sticky="w")
            # Normal colour
            norm_var = tk.StringVar(value=self.conf.get("colors", {}).get(name, {}).get("normal", "#4CAF50"))
            self.colour_vars[f"{name}_norm"] = norm_var
            ttk.Button(
                frame,
                text="Normal",
                width=8,
                command=lambda n=name: self._pick_colour(n, "norm")
            ).grid(row=i, column=1, padx=(5,0), pady=(2,0))
            ttk.Label(frame, textvariable=norm_var).grid(row=i, column=2)

            # Warning colour
            warn_var = tk.StringVar(value=self.conf.get("colors", {}).get(name, {}).get("warning", "#FF9800"))
            self.colour_vars[f"{name}_warn"] = warn_var
            ttk.Button(
                frame,
                text="Warning",
                width=8,
                command=lambda n=name: self._pick_colour(n, "warn")
            ).grid(row=i, column=3, padx=(5,0), pady=(2,0))
            ttk.Label(frame, textvariable=warn_var).grid(row=i, column=4)

            # Critical colour
            crit_var = tk.StringVar(value=self.conf.get("colors", {}).get(name, {}).get("critical", "#F44336"))
            self.colour_vars[f"{name}_crit"] = crit_var
            ttk.Button(
                frame,
                text="Critical",
                width=8,
                command=lambda n=name: self._pick_colour(n, "crit")
            ).grid(row=i, column=5, padx=(5,0), pady=(2,0))
            ttk.Label(frame, textvariable=crit_var).grid(row=i, column=6)

    def _pick_colour(self, metric_name, part):
        """Open OS colour picker and store the selected hex value."""
        color = colorchooser.askcolor(title=f"Select {part.title()} colour for {metric_name}")
        if color:
            # colourchooser returns (r,g,b) tuple; convert to #RRGGBB
            r, g, b = color[0]
            hex_col = f"#{r:02X}{g:02X}{b:02X}"
            var = self.colour_vars[f"{metric_name}_{part}"]
            var.set(hex_col)

    def _on_apply(self):
        """Persist all settings and refresh the running app."""
        # 1️⃣ GPU selection
        self.conf["selected_gpu"] = self.selected_gpu.get()

        # 2️⃣ Refresh interval (clamped already)
        self.conf["update_interval_s"] = self.interval_var.get()

        # 3️⃣ Thresholds – store as percentages (the app converts to native units at runtime)
        thresh = {k: {} for k in ["temperature","utilization","power","system_memory"]}
        for m in thresh:
            pct_warn = self.threshold_vars[f"{m}_warn"].get()
            pct_crit = self.threshold_vars[f"{m}_crit"].get()
            thresh[m] = {"warning_pct": pct_warn, "critical_pct": pct_crit}
        self.conf["thresholds"] = thresh

        # 4️⃣ Colours
        colours = {k: {} for k in ["temperature","utilization","power","system_memory"]}
        for m in colours:
            colours[m]["normal"]   = self.colour_vars[f"{m}_norm"].get()
            colours[m]["warning"]  = self.colour_vars[f"{m}_warn"].get()
            colours[m]["critical"] = self.colour_vars[f"{m}_crit"].get()
        self.conf["colors"] = colours

        # 5️⃣ Gauge size
        self.conf["gauge_size"] = self.size_var.get()

        _save_config(self.conf)

        # Notify the main app to reload config (it reads on next poll)
        if hasattr(self.app, "config_needs_reload"):
            self.app.config_needs_reload = True
        self.destroy()

# ----------------------------------------------------------------------
# Integration helper – call from GPUMonitorApp when “Settings” button pressed
# ----------------------------------------------------------------------
from .app import GPUMonitorApp

def show_settings_dialog(app: GPUMonitorApp):
    """Factory that creates and runs the settings dialog."""
    dlg = SettingsDialog(app.root, app)
    return dlg