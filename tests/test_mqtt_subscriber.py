"""
Unit tests for gpu_monitor.mqtt_subscriber (FUN-15).

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

from gpu_monitor import mqtt_subscriber
from gpu_monitor.mqtt_subscriber import MqttSubscriber, _parse_message


class FakeClient:
    """Records the slice of the paho API the subscriber uses."""

    def __init__(self):
        self.on_connect = None
        self.on_message = None
        self.subscribed = []
        self.connected = None
        self.loop_started = False
        self.loop_stopped = False
        self.disconnected = False

    def connect_async(self, host, port):
        self.connected = (host, port)

    def loop_start(self):
        self.loop_started = True

    def loop_stop(self):
        self.loop_stopped = True

    def disconnect(self):
        self.disconnected = True

    def subscribe(self, topic):
        self.subscribed.append(topic)


class Msg:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload


class TestParseMessage(unittest.TestCase):
    """FUN-15 — topic/payload parsing."""

    PREFIX = "Bishop/gpu_monitor"

    def test_valid_string_payload(self):
        self.assertEqual(_parse_message("Bishop/gpu_monitor/temperature", "45.0", self.PREFIX),
                         ("temperature", 45.0))

    def test_valid_bytes_payload(self):
        self.assertEqual(_parse_message("Bishop/gpu_monitor/power", b"120.5", self.PREFIX),
                         ("power", 120.5))

    def test_wrong_prefix_returns_none(self):
        self.assertIsNone(_parse_message("Other/gpu_monitor/power", "1", self.PREFIX))

    def test_unknown_metric_returns_none(self):
        self.assertIsNone(_parse_message("Bishop/gpu_monitor/fan_speed", "1", self.PREFIX))

    def test_system_memory_total_is_accepted(self):
        self.assertEqual(
            _parse_message("Bishop/gpu_monitor/system_memory_total", "64.0", self.PREFIX),
            ("system_memory_total", 64.0))

    def test_non_numeric_payload_returns_none(self):
        self.assertIsNone(_parse_message("Bishop/gpu_monitor/temperature", "N/A", self.PREFIX))

    def test_nested_metric_not_matched(self):
        # A deeper topic level is not one of the known metric keys.
        self.assertIsNone(_parse_message("Bishop/gpu_monitor/gpu/temperature", "1", self.PREFIX))


class TestMqttSubscriber(unittest.TestCase):

    def _patch_client(self, client):
        return patch.object(mqtt_subscriber, "_make_client", return_value=client)

    def test_disabled_does_not_connect(self):
        fake = FakeClient()
        with self._patch_client(fake):
            MqttSubscriber(enabled=False, machine="Bishop")
        self.assertIsNone(fake.connected)
        self.assertFalse(fake.loop_started)

    def test_enabled_without_machine_is_inert(self):
        fake = FakeClient()
        with self._patch_client(fake):
            MqttSubscriber(enabled=True, machine="")
        self.assertIsNone(fake.connected)

    def test_enabled_connects_and_starts_loop(self):
        fake = FakeClient()
        with self._patch_client(fake):
            MqttSubscriber(enabled=True, host="h", port=1884,
                           base_topic="t", machine="Bishop")
        self.assertEqual(fake.connected, ("h", 1884))
        self.assertTrue(fake.loop_started)
        self.assertIsNotNone(fake.on_connect)
        self.assertIsNotNone(fake.on_message)

    def test_on_connect_subscribes_to_machine_wildcard(self):
        fake = FakeClient()
        with self._patch_client(fake):
            MqttSubscriber(enabled=True, base_topic="gpu_monitor", machine="Bishop")
        fake.on_connect(fake, None, None, 0)
        self.assertEqual(fake.subscribed, ["Bishop/gpu_monitor/+"])

    def test_on_message_invokes_callback_with_parsed_value(self):
        received = []
        fake = FakeClient()
        with self._patch_client(fake):
            MqttSubscriber(enabled=True, base_topic="gpu_monitor", machine="Bishop",
                           on_metric=lambda k, v: received.append((k, v)))
        fake.on_message(fake, None, Msg("Bishop/gpu_monitor/utilization", b"30"))
        self.assertEqual(received, [("utilization", 30.0)])

    def test_on_message_ignores_unrelated_topic(self):
        received = []
        fake = FakeClient()
        with self._patch_client(fake):
            MqttSubscriber(enabled=True, base_topic="gpu_monitor", machine="Bishop",
                           on_metric=lambda k, v: received.append((k, v)))
        fake.on_message(fake, None, Msg("Other/gpu_monitor/power", b"1"))
        self.assertEqual(received, [])

    def test_on_message_swallows_callback_errors(self):
        def boom(k, v):
            raise RuntimeError("handler blew up")
        fake = FakeClient()
        with self._patch_client(fake):
            MqttSubscriber(enabled=True, base_topic="t", machine="Bishop", on_metric=boom)
        # must not raise
        fake.on_message(fake, None, Msg("Bishop/t/temperature", b"50"))

    def test_missing_paho_makes_inert_subscriber(self):
        with patch.object(mqtt_subscriber, "_make_client", return_value=None):
            sub = MqttSubscriber(enabled=True, machine="Bishop")
            self.assertIsNone(sub._client)

    def test_update_config_restarts_and_preserves_callback(self):
        received = []
        first, second = FakeClient(), FakeClient()
        with patch.object(mqtt_subscriber, "_make_client", side_effect=[first, second]):
            sub = MqttSubscriber(enabled=True, base_topic="t", machine="A",
                                 on_metric=lambda k, v: received.append((k, v)))
            sub.update_config(enabled=True, host="b", port=1884,
                              base_topic="t", machine="B")  # no on_metric passed
            sub._teardown_thread.join(timeout=2)
            second.on_message(second, None, Msg("B/t/power", b"99"))
        self.assertTrue(first.loop_stopped)
        self.assertEqual(second.connected, ("b", 1884))
        self.assertEqual(received, [("power", 99.0)])  # original callback preserved

    def test_stop_is_best_effort(self):
        fake = FakeClient()
        with self._patch_client(fake):
            sub = MqttSubscriber(enabled=True, machine="Bishop")
            sub.stop()
            sub._teardown_thread.join(timeout=2)
        self.assertTrue(fake.loop_stopped)
        self.assertTrue(fake.disconnected)


if __name__ == "__main__":
    unittest.main()
