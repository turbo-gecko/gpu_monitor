"""
MQTT publishing of GPU/system metrics (FUN-14).

Qt-free and defensively coded: like ``MetricsFetcher``, this module never
raises to its caller. A missing ``paho-mqtt`` package, an unreachable broker, or
a failed publish all degrade silently to a no-op so the monitor keeps running
(and the gauges keep updating) regardless of broker state. Networking happens on
paho's own background thread (``loop_start``) and ``publish`` is non-blocking, so
the GUI thread is never stalled (NFR-01).
"""

import socket
import threading

# The four canonical metric keys (matches scaling.DEFAULT_METRIC_RANGES).
METRIC_KEYS = ("temperature", "utilization", "power", "system_memory")

# Extra published value: the machine's total RAM (GB), so a remote subscriber
# can scale its memory gauge to this machine's full-scale (FUN-15). Not a gauge
# metric itself — handled specially on the subscribe side.
SYSTEM_MEMORY_TOTAL_KEY = "system_memory_total"

# Per-metric absolute warn/crit threshold topics (e.g. "temperature_warn"),
# published so a remote subscriber colours its gauges with the publisher's
# thresholds (FUN-15). Absolute values in native units — scale-independent.
THRESHOLD_BOUNDS = ("warn", "crit")
THRESHOLD_KEYS = tuple(f"{m}_{b}" for m in METRIC_KEYS for b in THRESHOLD_BOUNDS)


def _hostname():
    """
    Return the machine's hostname for namespacing topics, or "unknown" if it
    cannot be determined. Isolated into one function so tests can stub it.
    """
    try:
        name = socket.gethostname()
    except Exception:
        return "unknown"
    return name or "unknown"


def _make_client():
    """
    Create a fresh paho MQTT client, or return ``None`` if ``paho-mqtt`` is not
    installed. Isolated into one function so tests can stub the client out.
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return None
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


class MqttPublisher:
    """
    Publishes each metric to ``<hostname>/<base_topic>/<metric>`` once per call
    to :meth:`publish`. The hostname prefix namespaces metrics per machine so a
    single broker can serve many monitored hosts. Inert unless ``enabled`` and a
    broker connection could be started; all failures are swallowed.
    """

    def __init__(self, enabled=False, host="localhost", port=1883,
                 base_topic="gpu_monitor"):
        self._enabled = bool(enabled)
        self._host = host
        self._port = int(port)
        self._base_topic = base_topic
        self._hostname = _hostname()
        self._client = None
        self._teardown_thread = None
        self._start()

    def _start(self):
        """Bring up the background client connection if enabled (best-effort)."""
        if not self._enabled:
            return
        try:
            client = _make_client()
            if client is None:
                return  # paho-mqtt not installed → stay inert
            client.connect_async(self._host, self._port)
            client.loop_start()  # background networking thread + auto-reconnect
            self._client = client
        except Exception:
            self._client = None

    def publish(self, metrics):
        """
        Publish each non-``None`` value in *metrics* to its own retained topic
        ``<hostname>/<base_topic>/<metric>``, formatted to one decimal place.

        ``None`` values (an N/A metric) are skipped so consumers aren't fed a
        literal "None". Any failure is silent (FUN-14, FUN-05 philosophy).
        """
        if not self._enabled or self._client is None:
            return
        try:
            for key, value in metrics.items():
                if value is None:
                    continue
                self._client.publish(
                    f"{self._hostname}/{self._base_topic}/{key}",
                    f"{float(value):.1f}", qos=0, retain=True,
                )
        except Exception:
            pass

    def update_config(self, enabled=False, host="localhost", port=1883,
                      base_topic="gpu_monitor"):
        """Tear down any existing connection and re-start with new settings."""
        self.stop()
        self._enabled = bool(enabled)
        self._host = host
        self._port = int(port)
        self._base_topic = base_topic
        self._start()

    def stop(self):
        """
        Best-effort shutdown of the background connection.

        The publisher becomes inert immediately. The actual teardown runs on a
        throwaway daemon thread because ``loop_stop()`` joins paho's network
        thread, which can block for the socket connect timeout when the broker
        is unreachable — we must not freeze the GUI thread on close or on a
        Preferences change. paho's own loop thread is a daemon too, so a pending
        teardown never holds up process exit.
        """
        client = self._client
        self._client = None
        if client is None:
            return

        def _teardown():
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass

        t = threading.Thread(target=_teardown, name="mqtt-teardown", daemon=True)
        self._teardown_thread = t
        t.start()
