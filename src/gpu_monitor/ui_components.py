from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .config import COLORS

# Drawing dimensions for each size mode (FUN-13).
# "small" is exactly 50 % of "normal" in the gauge square; the label strip
# below the arc (title + subtitle) scales with it. ``total_h`` is the full
# widget height (arc square + label strip) used by ``setFixedSize``.
GAUGE_CANVAS = {
    "normal": {
        "size": 200, "pad": 20, "arc_end": 180,
        "cx": 100, "cy": 100, "warn_cy": 130,
        "font_val": 18, "font_alert": 18, "font_title": 12, "font_sub": 9,
        "arc_width": 16, "track_outline": 12,
        "title_h": 26, "sub_h": 20,
    },
    "small": {
        "size": 100, "pad": 10, "arc_end": 90,
        "cx": 50, "cy": 50, "warn_cy": 65,
        "font_val": 9, "font_alert": 9, "font_title": 7, "font_sub": 6,
        "arc_width": 8, "track_outline": 6,
        "title_h": 15, "sub_h": 12,
    },
}

_TRACK_COLOR = "#333333"
_FONT_FAMILY = "Segoe UI"


class Gauge(QWidget):
    """
    QPainter-drawn 180° arc gauge with configurable colours, thresholds and
    sizes. Satisfies FUN-06, FUN-07, FUN-11, FUN-13.

    The public surface mirrors the previous Tk widget so app.py is unchanged in
    spirit: ``update_value(val, subtitle="")``, ``show_na()``, ``resize(size)``
    plus the ``.value`` / ``.state`` / colour / threshold attributes.
    """

    def __init__(
        self,
        title: str,
        min_val: float,
        max_val: float,
        normal_color: str,
        warn_color: str = "#FFD700",
        crit_color: str = "#FF4500",
        warn_threshold=None,
        crit_threshold=None,
        size: str = "normal",
        parent=None,
    ):
        """
        Parameters
        ----------
        title           : Label shown below the arc.
        min_val/max_val : Full-scale range for arc extent calculation.
        normal_color    : Arc colour when value < warn_threshold.
        warn_color      : Arc colour when warn_threshold <= value < crit_threshold.
        crit_color      : Arc colour when value >= crit_threshold.
        warn_threshold  : Absolute value (same units as update_value calls).
        crit_threshold  : Absolute value.
        size            : "normal" (200x200 px) or "small" (100x100 px).
        """
        super().__init__(parent)
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
        self._current_size  = size

        # Render state mutated by update_value / show_na and consumed in paintEvent.
        self._extent      = 0.0          # degrees of progress arc, 0..180
        self._arc_color   = normal_color
        self._value_text  = ""
        self._subtitle    = ""
        self._icon        = ""
        self._show_alert  = False
        self._alert_active = False
        self._alert_visible = True       # toggled by the pulse timer

        # Pulse timer toggles the alert glyph every 400 ms (replaces after()).
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(400)
        self._pulse_timer.timeout.connect(self._toggle_alert)

        self._apply_size(size)

    # ── Public API ────────────────────────────────────────────────────────────

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
        self._extent = 180.0 * pct

        if self.crit_threshold is not None and val >= self.crit_threshold:
            self.state      = "critical"
            self._arc_color = self.crit_color
            self._show_alert = True
            self._icon       = "\U0001f525"
        elif self.warn_threshold is not None and val >= self.warn_threshold:
            self.state      = "warning"
            self._arc_color = self.warn_color
            self._show_alert = True
            self._icon       = "⚠️"
        else:
            self.state      = "normal"
            self._arc_color = self.normal_color
            self._show_alert = False
            self._icon       = ""

        self._value_text = f"{val:.1f}"
        self._subtitle   = subtitle_text

        if self._show_alert and not self._alert_active:
            self._alert_active  = True
            self._alert_visible = True
            self._pulse_timer.start()
        elif not self._show_alert and self._alert_active:
            self._alert_active = False
            self._pulse_timer.stop()

        self.update()

    def show_na(self) -> None:
        """Reset the gauge and display N/A -- satisfies FUN-05."""
        self._alert_active = False
        self._pulse_timer.stop()
        self.state       = "normal"
        self._extent     = 0.0
        self._arc_color  = self.normal_color
        self._value_text = "N/A"
        self._icon       = ""
        self._show_alert = False
        self._subtitle   = ""
        self.update()

    def set_size(self, size: str) -> None:
        """
        Switch between "normal" (200x200 px) and "small" (100x100 px) -- FUN-13.
        """
        if size == self._current_size:
            return
        self._current_size = size
        self._apply_size(size)
        self.update()

    # ── Painting ────────────────────────────────────────────────────────────

    def _apply_size(self, size: str) -> None:
        d = GAUGE_CANVAS[size]
        self.setFixedSize(d["size"], d["size"] + d["title_h"] + d["sub_h"])

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        d = GAUGE_CANVAS[self._current_size]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Gauge background, kept dark to preserve the original look and contrast.
        painter.fillRect(self.rect(), QColor(COLORS["bg"]))

        # Arc bounding box: (pad, pad) to (arc_end, arc_end), matching the old
        # Tk canvas coordinates. Qt arc angles are 1/16°, counter-clockwise from
        # 3 o'clock — the same convention the Tk start/extent math used.
        box = QRectF(d["pad"], d["pad"], d["arc_end"] - d["pad"], d["arc_end"] - d["pad"])

        # Background track: full 180° arch.
        track_pen = QPen(QColor(_TRACK_COLOR), d["track_outline"])
        track_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(track_pen)
        painter.drawArc(box, 0 * 16, 180 * 16)

        # Progress arc: fills left → top → right as the value grows.
        if self._extent > 0:
            arc_pen = QPen(QColor(self._arc_color), d["arc_width"])
            arc_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(arc_pen)
            start_angle = int(round((180.0 - self._extent) * 16))
            span_angle  = int(round(self._extent * 16))
            painter.drawArc(box, start_angle, span_angle)

        # Numeric value, centred in the arc square.
        painter.setPen(QColor(COLORS["text_main"]))
        painter.setFont(QFont(_FONT_FAMILY, d["font_val"], QFont.Weight.Bold))
        painter.drawText(QRectF(0, 0, d["size"], d["size"]),
                         Qt.AlignmentFlag.AlignCenter, self._value_text)

        # Pulsing alert glyph, below centre.
        if self._show_alert and self._alert_visible and self._icon:
            painter.setFont(QFont(_FONT_FAMILY, d["font_alert"]))
            icon_h = d["font_alert"] * 2
            painter.drawText(
                QRectF(0, d["warn_cy"] - icon_h / 2, d["size"], icon_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, self._icon,
            )

        # Title strip.
        painter.setPen(QColor(COLORS["text_dim"]))
        painter.setFont(QFont(_FONT_FAMILY, d["font_title"]))
        painter.drawText(
            QRectF(0, d["size"], d["size"], d["title_h"]),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, self.title,
        )

        # Subtitle strip.
        if self._subtitle:
            painter.setPen(QColor(COLORS["text_muted"]))
            painter.setFont(QFont(_FONT_FAMILY, d["font_sub"]))
            painter.drawText(
                QRectF(0, d["size"] + d["title_h"], d["size"], d["sub_h"]),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, self._subtitle,
            )

        painter.end()

    # ── Private ────────────────────────────────────────────────────────────

    def _toggle_alert(self) -> None:
        """Flip the alert-glyph visibility to create the pulsing effect."""
        if self._alert_active and self.state in ("warning", "critical"):
            self._alert_visible = not self._alert_visible
            self.update()
