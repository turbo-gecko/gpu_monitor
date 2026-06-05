import tkinter as tk
from .config import COLORS

# Canvas dimensions for each size mode (FUN-13).
# "small" is exactly 50 % of "normal" in both linear dimensions.
GAUGE_CANVAS = {
    "normal": {
        "size": 200, "pad": 20, "arc_end": 180,
        "cx": 100, "cy": 100, "warn_cy": 130,
        "font_val": 18, "font_alert": 18, "font_title": 12, "font_sub": 9,
        "arc_width": 16, "track_outline": 12,
    },
    "small": {
        "size": 100, "pad": 10, "arc_end": 90,
        "cx": 50, "cy": 50, "warn_cy": 65,
        "font_val": 9, "font_alert": 9, "font_title": 7, "font_sub": 6,
        "arc_width": 8, "track_outline": 6,
    },
}


class Gauge(tk.Frame):
    """
    Canvas-drawn arc gauge with configurable colours, thresholds, and sizes.
    Satisfies FUN-06, FUN-07, FUN-11, FUN-13.
    """

    def __init__(
        self,
        parent,
        title: str,
        min_val: float,
        max_val: float,
        normal_color: str,
        warn_color: str = "#FFD700",
        crit_color: str = "#FF4500",
        warn_threshold=None,
        crit_threshold=None,
        size: str = "normal",
    ):
        """
        Parameters
        ----------
        title           : Label shown below the canvas.
        min_val/max_val : Full-scale range for arc extent calculation.
        normal_color    : Arc colour when value < warn_threshold.
        warn_color      : Arc colour when warn_threshold <= value < crit_threshold.
        crit_color      : Arc colour when value >= crit_threshold.
        warn_threshold  : Absolute value (same units as update_value calls).
        crit_threshold  : Absolute value.
        size            : "normal" (200x200 px) or "small" (100x100 px).
        """
        super().__init__(parent, bg=COLORS["bg"])
        self.title          = title
        self.min_val        = min_val
        self.max_val        = max_val
        self.normal_color   = normal_color
        self.warn_color     = warn_color
        self.crit_color     = crit_color
        self.warn_threshold = warn_threshold
        self.crit_threshold = crit_threshold
        self.value          = min_val
        self.state          = "normal"   # "normal" | "warning" | "critical"
        self._alert_active  = False
        self._current_size  = size

        d = GAUGE_CANVAS[size]

        # Canvas
        self.canvas = tk.Canvas(
            self, width=d["size"], height=d["size"],
            bg=COLORS["bg"], highlightthickness=0,
        )
        self.canvas.pack(side="top", pady=15)

        # Background track -- ARC style (stroke, not fill) (FUN-06)
        self.arc_bg_id = self.canvas.create_arc(
            d["pad"], d["pad"], d["arc_end"], d["arc_end"],
            start=135, extent=270,
            style=tk.ARC, width=d["track_outline"], outline="#333333",
        )

        # Progress arc -- ARC style so it matches the track (FUN-06, FUN-07)
        self.arc_id = self.canvas.create_arc(
            d["pad"], d["pad"], d["arc_end"], d["arc_end"],
            start=135, extent=0,
            style=tk.ARC, width=d["arc_width"], outline=self.normal_color,
        )

        # Alert icon (hidden until a threshold is breached)
        self.warn_text = self.canvas.create_text(
            d["cx"], d["warn_cy"],
            text="", fill=COLORS["text_main"],
            font=("Segoe UI", d["font_alert"]),
            state="hidden",
        )

        # Numeric value
        self.text_id = self.canvas.create_text(
            d["cx"], d["cy"],
            text="", fill=COLORS["text_main"],
            font=("Segoe UI", d["font_val"], "bold"),
        )

        # Subtitle label (e.g. "3.2 GB / 16.0 GB")
        self.subtitle_label = tk.Label(
            self, text="",
            fg=COLORS["text_muted"], bg=COLORS["bg"],
            font=("Segoe UI", d["font_sub"]),
        )
        self.subtitle_label.pack(side="bottom", pady=(0, 5))

        # Static title label
        self.title_label = tk.Label(
            self, text=title,
            fg=COLORS["text_dim"], bg=COLORS["bg"],
            font=("Segoe UI", d["font_title"]),
        )
        self.title_label.pack(side="bottom", pady=(0, 10))

    # Public API

    def update_value(self, val: float, subtitle_text: str = "") -> None:
        """
        Redraw the gauge to reflect val.

        Colour selection (FUN-07):
          val >= crit_threshold  -> crit_color
          val >= warn_threshold  -> warn_color
          otherwise              -> normal_color
        Colour is applied immediately without requiring a restart.
        """
        self.value = val
        val_range  = self.max_val - self.min_val
        pct        = max(0.0, min(1.0, (val - self.min_val) / val_range)) if val_range > 0 else 0.0
        extent     = 270 * pct

        if self.crit_threshold is not None and val >= self.crit_threshold:
            self.state = "critical"
            arc_color  = self.crit_color
            show_alert = True
            icon       = "\U0001f525"
        elif self.warn_threshold is not None and val >= self.warn_threshold:
            self.state = "warning"
            arc_color  = self.warn_color
            show_alert = True
            icon       = "\u26a0\ufe0f"
        else:
            self.state = "normal"
            arc_color  = self.normal_color
            show_alert = False
            icon       = ""

        self.canvas.itemconfigure(self.arc_id,    extent=extent, outline=arc_color)
        self.canvas.itemconfigure(self.text_id,   text=f"{val:.1f}")
        self.canvas.itemconfigure(
            self.warn_text, text=icon,
            state="normal" if show_alert else "hidden",
        )
        self.title_label.config(text=self.title)
        self.subtitle_label.config(text=subtitle_text)

        if show_alert and not self._alert_active:
            self._alert_active = True
            self._pulse_alert()
        elif not show_alert:
            self._alert_active = False

    def show_na(self) -> None:
        """Reset the gauge and display N/A -- satisfies FUN-05."""
        self._alert_active = False
        self.state         = "normal"
        self.canvas.itemconfigure(self.arc_id,    extent=0, outline=self.normal_color)
        self.canvas.itemconfigure(self.text_id,   text="N/A")
        self.canvas.itemconfigure(self.warn_text, text="", state="hidden")
        self.title_label.config(text=self.title)
        self.subtitle_label.config(text="")

    def resize(self, size: str) -> None:
        """
        Switch between "normal" (200x200 px) and "small" (100x100 px) -- FUN-13.
        Both width and height are halved independently.
        """
        if size == self._current_size:
            return
        self._current_size = size
        d = GAUGE_CANVAS[size]

        self.canvas.configure(width=d["size"], height=d["size"])

        self.canvas.coords(self.arc_bg_id, d["pad"], d["pad"], d["arc_end"], d["arc_end"])
        self.canvas.itemconfigure(self.arc_bg_id, width=d["track_outline"])

        self.canvas.coords(self.arc_id, d["pad"], d["pad"], d["arc_end"], d["arc_end"])
        self.canvas.itemconfigure(self.arc_id, width=d["arc_width"])

        self.canvas.coords(self.text_id,   d["cx"], d["cy"])
        self.canvas.coords(self.warn_text, d["cx"], d["warn_cy"])

        self.canvas.itemconfigure(self.text_id,   font=("Segoe UI", d["font_val"], "bold"))
        self.canvas.itemconfigure(self.warn_text, font=("Segoe UI", d["font_alert"]))
        self.title_label.configure(   font=("Segoe UI", d["font_title"]))
        self.subtitle_label.configure(font=("Segoe UI", d["font_sub"]))

    # Private

    def _pulse_alert(self) -> None:
        """Toggle the alert icon visibility to create a pulsing effect."""
        if self.state in ("warning", "critical") and self._alert_active:
            current = self.canvas.itemcget(self.warn_text, "state")
            self.canvas.itemconfigure(
                self.warn_text,
                state="hidden" if current == "normal" else "normal",
            )
            self.after(400, self._pulse_alert)
