"""
Unit tests for gpu_monitor.metrics module.

Covers MetricsFetcher and format_memory_gb per FUN-01, FUN-02, FUN-03, FUN-05.
"""

import os
import sys
import unittest
from unittest.mock import patch, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gpu_monitor.metrics import MetricsFetcher


class TestFetchSystemMemory(unittest.TestCase):
    """FUN-02 — system memory reading from /proc/meminfo."""

    @patch("builtins.open", new_callable=mock_open, read_data="""MemTotal:       16777216 kB
MemFree:         4194304 kB
MemAvailable:    8388608 kB
Buffers:          524288 kB
Cached:          2097152 kB
SwapCached:            0 kB
""")
    def test_normal_values(self, mock_file):
        used_gb, total_gb, percent = MetricsFetcher.fetch_system_memory()
        # 16777216 kB / (1024*1024) = 16.0 GB
        self.assertAlmostEqual(total_gb, 16.0, places=1)
        # available = 8388608 kB => used = 16777216 - 8388608 = 8388608 kB
        # 8388608 / (1024*1024) = 8.0 GB
        self.assertAlmostEqual(used_gb, 8.0, places=1)
        self.assertEqual(percent, 50.0)

    def test_missing_mem_available_falls_back_to_free_plus_cache(self):
        # On older kernels (< 3.14) MemAvailable is absent. We estimate
        # available memory from MemFree + Buffers + Cached rather than
        # treating it as 0 (which would wrongly report 100% used).
        with patch("builtins.open", new_callable=mock_open, read_data="""MemTotal:       16777216 kB
MemFree:         4194304 kB
Buffers:          524288 kB
Cached:                0 kB
"""):
            used_gb, total_gb, percent = MetricsFetcher.fetch_system_memory()
            # available = 4194304 + 524288 + 0 = 4718592 kB
            # used = 16777216 - 4718592 = 12058624 kB => 11.5 GB
            self.assertAlmostEqual(total_gb, 16.0, places=1)
            self.assertAlmostEqual(used_gb, 11.5, places=1)
            self.assertAlmostEqual(percent, 71.875, places=2)

    def test_total_kb_zero_returns_none(self):
        with patch("builtins.open", new_callable=mock_open, read_data="""MemTotal:            0 kB
MemFree:             0 kB
MemAvailable:        0 kB
"""):
            # A zero/absent total has no meaningful percentage, so the
            # fetcher reports failure and the UI shows "N/A" (FUN-05).
            used_gb, total_gb, percent = MetricsFetcher.fetch_system_memory()
            self.assertIsNone(used_gb)
            self.assertIsNone(total_gb)
            self.assertIsNone(percent)

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_file_not_found_returns_none(self, mock_file):
        used_gb, total_gb, percent = MetricsFetcher.fetch_system_memory()
        self.assertIsNone(used_gb)
        self.assertIsNone(total_gb)
        self.assertIsNone(percent)

    @patch("builtins.open", new_callable=mock_open, read_data="""MemTotal:       16777216 kB
MemAvailable:   16777216 kB
""")
    def test_zero_used_percent(self, mock_file):
        used_gb, total_gb, percent = MetricsFetcher.fetch_system_memory()
        self.assertAlmostEqual(used_gb, 0.0, places=1)
        self.assertEqual(total_gb, 16.0)
        self.assertEqual(percent, 0.0)

    @patch("builtins.open", new_callable=mock_open, read_data="""MemTotal:       16777216 kB
MemAvailable:            0 kB
""")
    def test_100_percent_used(self, mock_file):
        used_gb, total_gb, percent = MetricsFetcher.fetch_system_memory()
        self.assertAlmostEqual(total_gb, 16.0, places=1)
        self.assertAlmostEqual(used_gb, 16.0, places=1)
        self.assertEqual(percent, 100.0)


class TestFetchGpuStats(unittest.TestCase):
    """FUN-01 — GPU stats via nvidia-smi."""

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_valid_output(self, mock_run, mock_which):
        nvidia_smi_output = (
            "75,92,350.5\n"
        )
        mock_run.return_value = unittest.mock.Mock(returncode=0, stdout=nvidia_smi_output, stderr="")

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertEqual(temp, 75.0)
        self.assertEqual(util, 92.0)
        self.assertAlmostEqual(power, 350.5, places=1)

    @patch("gpu_monitor.metrics.shutil.which", return_value=None)
    def test_nvidia_smi_not_found(self, mock_which):
        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertIsNone(temp)
        self.assertIsNone(util)
        self.assertIsNone(power)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_subprocess_timeout(self, mock_run, mock_which):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired(["nvidia-smi"], 30)

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertIsNone(temp)
        self.assertIsNone(util)
        self.assertIsNone(power)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_non_zero_return_code(self, mock_run, mock_which):
        mock_run.return_value = unittest.mock.Mock(returncode=1, stderr="Error: permission denied", stdout="")

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertIsNone(temp)
        self.assertIsNone(util)
        self.assertIsNone(power)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_permission_error_in_stderr(self, mock_run, mock_which):
        mock_run.return_value = unittest.mock.Mock(returncode=1, stderr="Not Supported", stdout="")

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertIsNone(temp)
        self.assertIsNone(util)
        self.assertIsNone(power)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_invalid_csv_format(self, mock_run, mock_which):
        mock_run.return_value = unittest.mock.Mock(returncode=0, stdout="invalid\n", stderr="")

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertIsNone(temp)
        self.assertIsNone(util)
        self.assertIsNone(power)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_partial_csv_fields(self, mock_run, mock_which):
        # Fewer fields than expected headers.
        # The code checks len(parts) < 3 and returns None, None, None.
        mock_run.return_value = unittest.mock.Mock(returncode=0, stdout="75\n", stderr="")

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertIsNone(temp)
        self.assertIsNone(util)
        self.assertIsNone(power)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_extra_csv_fields(self, mock_run, mock_which):
        # More fields than headers.
        mock_run.return_value = unittest.mock.Mock(returncode=0, stdout="75,92,350.5,extra_field\n", stderr="")

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertEqual(temp, 75.0)
        self.assertEqual(util, 92.0)
        self.assertAlmostEqual(power, 350.5, places=1)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_non_numeric_temperature(self, mock_run, mock_which):
        mock_run.return_value = unittest.mock.Mock(returncode=0, stdout="N/A,92,350.5\n", stderr="")

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertIsNone(temp)
        self.assertEqual(util, 92.0)
        self.assertAlmostEqual(power, 350.5, places=1)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_non_numeric_utilization(self, mock_run, mock_which):
        mock_run.return_value = unittest.mock.Mock(returncode=0, stdout="75,N/A,350.5\n", stderr="")

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertEqual(temp, 75.0)
        self.assertIsNone(util)
        self.assertAlmostEqual(power, 350.5, places=1)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_all_n_a(self, mock_run, mock_which):
        mock_run.return_value = unittest.mock.Mock(returncode=0, stdout="N/A,N/A,N/A\n", stderr="")

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertIsNone(temp)
        self.assertIsNone(util)
        self.assertIsNone(power)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_dash_values(self, mock_run, mock_which):
        mock_run.return_value = unittest.mock.Mock(returncode=0, stdout="-,-,-\n", stderr="")

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertIsNone(temp)
        self.assertIsNone(util)
        self.assertIsNone(power)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_general_exception(self, mock_run, mock_which):
        mock_run.side_effect = RuntimeError("some error")

        temp, util, power = MetricsFetcher.fetch_gpu_stats()
        self.assertIsNone(temp)
        self.assertIsNone(util)
        self.assertIsNone(power)


class TestParseTempLimit(unittest.TestCase):
    """_parse_temp_limit extracts a full-scale temperature ceiling."""

    def test_prefers_shutdown(self):
        text = (
            "        GPU Current Temp                  : 45 C\n"
            "        GPU Shutdown Temp                 : 98 C\n"
            "        GPU Slowdown Temp                 : 95 C\n"
            "        GPU Max Operating Temp            : 90 C\n"
        )
        self.assertEqual(MetricsFetcher._parse_temp_limit(text), 98.0)

    def test_falls_back_to_slowdown(self):
        text = "GPU Slowdown Temp : 95 C\nGPU Max Operating Temp : 90 C\n"
        self.assertEqual(MetricsFetcher._parse_temp_limit(text), 95.0)

    def test_falls_back_to_max_operating(self):
        self.assertEqual(
            MetricsFetcher._parse_temp_limit("GPU Max Operating Temp : 90 C\n"), 90.0
        )

    def test_none_when_absent(self):
        self.assertIsNone(MetricsFetcher._parse_temp_limit("GPU Current Temp : 45 C\n"))


class TestFetchGpuLimits(unittest.TestCase):
    """fetch_gpu_limits queries device power/temperature ceilings."""

    @patch("gpu_monitor.metrics.shutil.which", return_value=None)
    def test_no_nvidia_smi_returns_none(self, mock_which):
        self.assertEqual(
            MetricsFetcher.fetch_gpu_limits(), {"power_max": None, "temp_max": None}
        )

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_parses_power_and_temp(self, mock_run, mock_which):
        power = unittest.mock.Mock(returncode=0, stdout="350.00\n", stderr="")
        temp = unittest.mock.Mock(
            returncode=0, stdout="GPU Shutdown Temp : 98 C\n", stderr=""
        )
        mock_run.side_effect = [power, temp]
        limits = MetricsFetcher.fetch_gpu_limits()
        self.assertAlmostEqual(limits["power_max"], 350.0, places=1)
        self.assertEqual(limits["temp_max"], 98.0)

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run")
    def test_unparseable_values_yield_none(self, mock_run, mock_which):
        power = unittest.mock.Mock(returncode=0, stdout="[N/A]\n", stderr="")
        temp = unittest.mock.Mock(returncode=0, stdout="no temps here\n", stderr="")
        mock_run.side_effect = [power, temp]
        limits = MetricsFetcher.fetch_gpu_limits()
        self.assertIsNone(limits["power_max"])
        self.assertIsNone(limits["temp_max"])

    @patch("gpu_monitor.metrics.shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("gpu_monitor.metrics.subprocess.run", side_effect=OSError("boom"))
    def test_subprocess_failure_returns_none(self, mock_run, mock_which):
        self.assertEqual(
            MetricsFetcher.fetch_gpu_limits(), {"power_max": None, "temp_max": None}
        )


class TestFormatMemoryGb(unittest.TestCase):
    """Formatting helper for memory display."""

    def test_none_returns_n_a(self):
        self.assertEqual(MetricsFetcher.format_memory_gb(None), "N/A")

    def test_small_value(self):
        # 500 GB should display as 500.0 GB.
        result = MetricsFetcher.format_memory_gb(500)
        self.assertEqual(result, "500.0 GB")

    def test_zero(self):
        self.assertEqual(MetricsFetcher.format_memory_gb(0), "0.0 GB")

    def test_exact_gb(self):
        # 1024 GB should display as 1024 GB.
        self.assertEqual(MetricsFetcher.format_memory_gb(1024), "1024 GB")

    def test_large_value(self):
        # 16384 GB.
        self.assertEqual(MetricsFetcher.format_memory_gb(16384), "16384 GB")

    def test_hundred_gb(self):
        self.assertEqual(MetricsFetcher.format_memory_gb(100), "100.0 GB")


if __name__ == "__main__":
    unittest.main()