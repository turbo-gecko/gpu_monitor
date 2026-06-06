"""Console entry point for the GPU & System Monitor."""

import sys

from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from .app import GPUMonitorApp
from .config import load_window_state


def main():
    app = QApplication(sys.argv)
    apply_stylesheet(app, theme="dark_teal.xml")

    window = GPUMonitorApp()
    window.show()

    interval_s = load_window_state().get("update_interval_s", 2)
    print("🚀 GPU & System Monitor started. No sudo required.")
    print(f"🔄 Updating every {interval_s} second(s)")
    print("-" * 50)
    print("💡 Press Ctrl+H for horizontal, Ctrl+V for vertical layout")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
