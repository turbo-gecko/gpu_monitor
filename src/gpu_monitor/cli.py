"""Console entry point for the GPU & System Monitor."""

import tkinter as tk

from .app import GPUMonitorApp
from .config import load_window_state


def main():
    root = tk.Tk()
    GPUMonitorApp(root)

    interval_s = load_window_state().get("update_interval_s", 2)
    print("🚀 GPU & System Monitor started. No sudo required.")
    print(f"🔄 Updating every {interval_s} second(s)")
    print("-" * 50)
    print("💡 Press Ctrl+H for horizontal, Ctrl+V for vertical layout")

    root.mainloop()


if __name__ == "__main__":
    main()
