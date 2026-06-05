import re
import subprocess
import shutil

class MetricsFetcher:
    """Handles data acquisition from system and GPU."""

    @staticmethod
    def fetch_gpu_limits():
        """
        Query GPU 0's hardware ceilings so gauges can use a device-correct
        full-scale instead of hardcoded guesses. Intended to run once at
        startup.

        Returns ``{"power_max": float|None, "temp_max": float|None}``; either
        entry is None when the value cannot be determined (old driver, missing
        field, nvidia-smi absent, etc.).
        """
        limits = {"power_max": None, "temp_max": None}
        if not shutil.which('nvidia-smi'):
            return limits

        # Power ceiling — exposed directly via --query-gpu on modern drivers.
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=power.max_limit',
                 '--format=csv,noheader,nounits', '--id=0'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                first = result.stdout.strip().splitlines()[0].strip()
                try:
                    limits["power_max"] = float(first)
                except ValueError:
                    pass
        except (subprocess.SubprocessError, OSError):
            pass

        # Temperature ceiling — only available in the verbose query output.
        try:
            result = subprocess.run(
                ['nvidia-smi', '-q', '-d', 'TEMPERATURE', '-i', '0'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                limits["temp_max"] = MetricsFetcher._parse_temp_limit(result.stdout)
        except (subprocess.SubprocessError, OSError):
            pass

        return limits

    @staticmethod
    def _parse_temp_limit(text):
        """
        Pull a full-scale temperature ceiling from the text of
        ``nvidia-smi -q -d TEMPERATURE``.

        Prefers the highest meaningful limit (shutdown), then slowdown, then
        the rated max operating temp. Returns a float, or None if none of the
        labels are present (label names vary across driver versions).
        """
        for label in ("GPU Shutdown Temp", "GPU Slowdown Temp", "GPU Max Operating Temp"):
            m = re.search(rf"{re.escape(label)}\s*:\s*(\d+)", text)
            if m:
                return float(m.group(1))
        return None

    @staticmethod
    def fetch_gpu_stats():
        """
        Fetch GPU stats for GPU 0 using nvidia-smi (no sudo).

        Returns (temperature, utilization, power) or (None, None, None) on any
        failure. Failures are returned as None rather than logged here: this
        runs once per polling cycle, so printing would spam stdout/nohup.out;
        the missing/blocked driver is surfaced once at startup via
        GPUMonitorApp._check_dependencies().
        """
        if not shutil.which('nvidia-smi'):
            return None, None, None

        cmd = [
            'nvidia-smi',
            '--query-gpu=temperature.gpu,utilization.gpu,power.draw',
            '--format=csv,noheader,nounits',
            '--id=0'
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return None, None, None

            parts = result.stdout.strip().split(',')
            if len(parts) < 3:
                return None, None, None

            def safe_float(v):
                v = v.strip().upper()
                if v in ('N/A', '-', 'NAN', 'INF', 'N/A '):
                    return None
                try:
                    return float(v)
                except ValueError:
                    return None

            return safe_float(parts[0]), safe_float(parts[1]), safe_float(parts[2])

        except subprocess.TimeoutExpired:
            return None, None, None
        except Exception:
            return None, None, None

    @staticmethod
    def fetch_system_memory():
        """
        Get system memory usage from /proc/meminfo (Linux, no sudo required).
        Returns (used_gb, total_gb, percentage) or (None, None, None) on failure.
        """
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    key = parts[0].rstrip(':')
                    meminfo[key] = int(parts[1])  # Value in kB

            total_kb = meminfo.get('MemTotal', 0)
            if total_kb <= 0:
                # Without a positive total we cannot compute a meaningful
                # percentage; report failure rather than a misleading 0%.
                return None, None, None

            available_kb = meminfo.get('MemAvailable')
            if available_kb is None:
                # Older kernels (< 3.14) lack MemAvailable. Estimate it the
                # documented way, from free memory plus reclaimable cache.
                available_kb = (
                    meminfo.get('MemFree', 0)
                    + meminfo.get('Buffers', 0)
                    + meminfo.get('Cached', 0)
                )

            used_kb = total_kb - available_kb
            total_gb = total_kb / (1024 * 1024)
            used_gb = used_kb / (1024 * 1024)
            percentage = (used_kb / total_kb) * 100

            return used_gb, total_gb, percentage

        except (IOError, OSError, KeyError, ValueError, IndexError):
            return None, None, None

    @staticmethod
    def fetch_total_memory_gb():
        """
        Get the total system memory in GB from /proc/meminfo (Linux, no sudo required).
        Returns total_gb as a float, or None on failure.
        """
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    key = parts[0].rstrip(':')
                    if key == 'MemTotal':
                        total_kb = int(parts[1])
                        if total_kb > 0:
                            return total_kb / (1024 * 1024)
                        return None
            return None
        except (IOError, OSError, ValueError, IndexError):
            return None

    @staticmethod
    def format_memory_gb(gb):
        """Format GB value nicely for display"""
        if gb is None:
            return "N/A"
        if gb >= 1000:
            return f"{gb:.0f} GB"
        return f"{gb:.1f} GB"