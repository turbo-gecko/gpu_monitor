"""
Threshold breach event logger — satisfies FUN-08.

Writes a timestamped entry to LOG_FILE whenever a gauge transitions into
a warning or critical state.  The logger is lazily initialised on first use
so that no file is created until an actual breach occurs.
"""

import logging
from .config import LOG_FILE


def _get_logger() -> logging.Logger:
    """Return the singleton file logger, initialising it on first call."""
    logger = logging.getLogger("gpu_monitor.threshold")
    if not logger.handlers:
        try:
            handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        except (IOError, OSError) as exc:
            # If the log file cannot be opened, fall back to a no-op handler
            # so the rest of the application is unaffected.
            handler = logging.NullHandler()
            print(f"⚠️  Could not open log file '{LOG_FILE}': {exc}")
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                              datefmt="%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        # Prevent messages propagating to the root logger / console.
        logger.propagate = False
    return logger


def log_threshold_breach(metric: str, value: float, state: str) -> None:
    """
    Write a timestamped threshold-breach entry to the log file.

    Parameters
    ----------
    metric : str
        Human-readable metric name (e.g. "Temperature (°C)").
    value  : float
        The value that triggered the breach.
    state  : str
        Either "warning" or "critical".
    """
    level = logging.CRITICAL if state == "critical" else logging.WARNING
    _get_logger().log(
        level,
        "THRESHOLD BREACH | metric=%-25s value=%7.1f  state=%s",
        metric,
        value,
        state.upper(),
    )