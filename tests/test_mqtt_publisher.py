"""
Unit tests for gpu_monitor.mqtt_publisher (FUN-14).

Qt-free. A recording fake client is injected via the module-level
``_make_client`` factory so these tests run with or without ``paho-mqtt``
installed and never touch the network.
"""

import os
import unittest
from unittest.mock import patch

# Ensure src is on the path so relative imports within gpu_monitor work.
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from gpu_monitor import mqtt_publisher
from gpu_monitor.mqtt_publisher import MqttPublisher


class FakeClient:
    """Records publish calls; mimics the slice of the paho API we use."""

    def __init__(self, raise_on_publish=False):
        self.published = []          # list of (topic, payload, qos, retain)
        self.loop_started = False
        self.loop_stopped = False
        self.connected = None        # (host, port)
        self.disconnected = False
        self._raise_on_publish = raise_on_publish

    def connect_async(self, host, port):
        self.connected = (host, port)

    def loop_start(self):
        self.loop_started = True

    def loop_stop(self):
        self.loop_stopped = True

    def disconnect(self):
        self.disconnected = True

    def publish(self, topic, payload, qos=0, retain=False):
        if self._raise_on_publish:
            raise RuntimeError("broker exploded")
        self.published.append((topic, payload, qos, retain))


class TestHostname(unittest.TestCase):
    """FUN-14 — hostname prefix resolution."""

    def test_returns_socket_hostname(self):
        with patch("gpu_monitor.mqtt_publisher.socket.gethostname", return_value="myrig"):
            self.assertEqual(mqtt_publisher._hostname(), "myrig")

    def test_empty_falls_back_to_unknown(self):
        with patch("gpu_monitor.mqtt_publisher.socket.gethostname", return_value=""):
            self.assertEqual(mqtt_publisher._hostname(), "unknown")

    def test_exception_falls_back_to_unknown(self):
        with patch("gpu_monitor.mqtt_publisher.socket.gethostname", side_effect=OSError):
            self.assertEqual(mqtt_publisher._hostname(), "unknown")


class TestMqttPublisher(unittest.TestCase):

    def setUp(self):
        # Pin the hostname so topic assertions are deterministic.
        self._host_patcher = patch.object(mqtt_publisher, "_hostname", return_value="testhost")
        self._host_patcher.start()
        self.addCleanup(self._host_patcher.stop)

    def _patch_client(self, client):
        return patch.object(mqtt_publisher, "_make_client", return_value=client)

    def test_disabled_publishes_nothing(self):
        fake = FakeClient()
        with self._patch_client(fake):
            pub = MqttPublisher(enabled=False)
            pub.publish({"temperature": 50})
        self.assertEqual(fake.published, [])
        self.assertFalse(fake.loop_started)

    def test_enabled_connects_and_starts_loop(self):
        fake = FakeClient()
        with self._patch_client(fake):
            MqttPublisher(enabled=True, host="h", port=1884, base_topic="t")
        self.assertEqual(fake.connected, ("h", 1884))
        self.assertTrue(fake.loop_started)

    def test_publishes_one_topic_per_non_none_metric(self):
        fake = FakeClient()
        with self._patch_client(fake):
            pub = MqttPublisher(enabled=True, base_topic="gpu_monitor")
            pub.publish({
                "temperature":   45.0,
                "utilization":   30,
                "power":         120.5,
                "system_memory": 12.3,
            })
        topics = {t for (t, _p, _q, _r) in fake.published}
        self.assertEqual(topics, {
            "testhost/gpu_monitor/temperature",
            "testhost/gpu_monitor/utilization",
            "testhost/gpu_monitor/power",
            "testhost/gpu_monitor/system_memory",
        })
        # payloads are stringified, retained, qos 0
        for (_t, payload, qos, retain) in fake.published:
            self.assertIsInstance(payload, str)
            self.assertEqual(qos, 0)
            self.assertTrue(retain)

    def test_none_metrics_are_skipped(self):
        fake = FakeClient()
        with self._patch_client(fake):
            pub = MqttPublisher(enabled=True, base_topic="t")
            pub.publish({"temperature": None, "utilization": 50, "power": None,
                         "system_memory": None})
        self.assertEqual(fake.published, [("testhost/t/utilization", "50", 0, True)])

    def test_publish_failure_is_swallowed(self):
        fake = FakeClient(raise_on_publish=True)
        with self._patch_client(fake):
            pub = MqttPublisher(enabled=True)
            # must not raise
            pub.publish({"temperature": 50})

    def test_missing_paho_makes_inert_publisher(self):
        with patch.object(mqtt_publisher, "_make_client", return_value=None):
            pub = MqttPublisher(enabled=True)
            pub.publish({"temperature": 50})  # no client, no error

    def test_update_config_stops_old_and_starts_new(self):
        first = FakeClient()
        second = FakeClient()
        with patch.object(mqtt_publisher, "_make_client", side_effect=[first, second]):
            pub = MqttPublisher(enabled=True, host="a", port=1883, base_topic="x")
            pub.update_config(enabled=True, host="b", port=1884, base_topic="y")
            pub._teardown_thread.join(timeout=2)  # teardown of `first` runs off-thread
            pub.publish({"temperature": 1})
        self.assertTrue(first.loop_stopped)
        self.assertTrue(first.disconnected)
        self.assertEqual(second.connected, ("b", 1884))
        self.assertEqual(second.published, [("testhost/y/temperature", "1", 0, True)])

    def test_update_config_to_disabled_goes_inert(self):
        fake = FakeClient()
        with self._patch_client(fake):
            pub = MqttPublisher(enabled=True)
            pub.update_config(enabled=False)
            pub._teardown_thread.join(timeout=2)
            pub.publish({"temperature": 1})
        self.assertTrue(fake.loop_stopped)
        self.assertEqual(fake.published, [])

    def test_stop_is_best_effort(self):
        fake = FakeClient()
        with self._patch_client(fake):
            pub = MqttPublisher(enabled=True)
            pub.stop()
            pub._teardown_thread.join(timeout=2)
        self.assertTrue(fake.loop_stopped)
        self.assertTrue(fake.disconnected)


if __name__ == "__main__":
    unittest.main()
