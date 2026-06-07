# Packaging GPU Monitor for Windows

This document provides instructions on how to package the GPU Monitor application into a standalone Windows executable (`.exe`) using PyInstaller.

## Prerequisites

- Python 3.10 or higher installed on Windows.
- A virtual environment with all project dependencies installed.
- `pyinstaller` installed in your environment.

## Packaging Steps

### 1. Prepare the Environment

Ensure you are working within your project's virtual environment and that all dependencies from `pyproject.toml` are installed:

```powers
pip install PySide6 qt-material paho-mqtt
pip install pyinstaller
```

### 2. Build the Executable

Run the following command from the root directory of the project (`d:\workspace\Python\gpu_monitor`):

```bash
pyinstaller --onefile --windowed --name gpu_monitor src/main.py
```

**Command Breakdown:**
- `--onefile`: Bundles everything into a single `.exe` file for easy distribution.
- `--windowed` (or `-w`): Ensures that no console window is opened when the application starts (since this is a GUI app).
- `--name gpu_monitor`: Sets the name of the resulting executable to `gpu_monitor.exe`.
- `src/main.py`: The entry point of the application.

### 3. Locate the Output

Once the build process completes, you will find the standalone executable in the `dist/` directory:

`D:\workspace\Python\gpu_monitor\dist\gpu_monitor.exe`

## Important Notes

- **Windows Compatibility**: While the core logic for GPU monitoring uses `nvidia-smi` (which is cross-platform), some system memory metrics in this version are specifically designed for Linux (`/proc/meminfo`). If running on Windows, these specific metrics may not be available, but the application will continue to function using MQTT remote mode or fallback defaults.
- **Dependencies**: The `--onefile` mode bundles all necessary Python libraries (PySide6, paho-mqtt, etc.) into the executable, so the end user does not need to install Python or any packages manually.
- **NVIDIA Drivers**: Ensure that NVIDIA drivers are installed on the target Windows machine so that `nvidia-smi` is available in the system PATH.