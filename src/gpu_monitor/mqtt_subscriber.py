"""
MQTT subscription of GPU/system metrics (FUN-15).

Remote-monitoring counterpart to :mod:`mqtt_publisher`: instead of reading local
hardware, subscribe to the metrics another machine publishes (per FUN-14) and
feed them to the gauges. Qt-free and defensively coded — never raises to its
caller; a missing ``paho-mqtt`` package, an unreachable broker, or a malformed
message all degrade silently.

Messages arrive on paho's network thread, so the ``on_metric`` callback must
marshal the update to the GUI thread itself (the app does this with a queued
Qt signal).
"""

import threading

from .mqtt_publisher import _make_client, METRIC_KEYS, SYSTEM_MEMORY_TOTAL_KEY

# Topics the subscriber accepts: the gauge metrics plus the total-RAM value.
_ALLOWED_KEYS = set(METRIC_KEYS) | {SYSTEM_MEMORY_TOTAL_KEY}


def _parse_message(topic, payload, prefix):
    """
    Parse an MQTT message into ``(key, value)`` or ``None``.

    Returns ``None`` when the topic is not ``<prefix>/<known-key>`` or the
    payload is not a number. *prefix* is ``"<machine>/<base_topic>"``. Accepts
    the four gauge metrics plus ``system_memory_total``.
    """
    expected = f"{prefix}/"
    if not topic.startswith(expected):
        return None
    key = topic[len(expected):]
    if key not in _ALLOWED_KEYS:
        return None
    try:
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8", "replace")
        value = float(payload)
    except (ValueError, TypeError):
        return None
    return key, value


class MqttSubscriber:
    """
    Subscribes to ``<machine>/<base_topic>/+`` and invokes ``on_metric(key,
    value)`` for each metric message. Inert unless ``enabled``, a ``machine`` is
    set, and a broker connection could be started; all failures are swallowed.
    """

    def __init__(self, enabled=False, host="localhost", port=1883,
                 base_topic="gpu_monitor", machine="", on_metric=None):
        self._enabled = bool(enabled)
        self._host = host
        self._port = int(port)
        self._base_topic = base_topic
        self._machine = machine
        self._on_metric = on_metric
        self._client = None
        self._teardown_thread = None
        self._start()

    @property
    def _prefix(self):
        return f"{self._machine}/{self._base_topic}"

    def _start(self):
        # A machine name is required to build the subscription topic.
        if not self._enabled or not self._machine:
            return
        try:
            client = _make_client()
            if client is None:
                return  # paho-mqtt not installed → stay inert
            client.on_connect = self._on_connect
            client.on_message = self._on_message
            client.connect_async(self._host, self._port)
            client.loop_start()  # background networking thread + auto-reconnect
            self._client = client
        except Exception:
            self._client = None

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """(Re)subscribe on every successful (re)connect."""
        try:
            client.subscribe(f"{self._prefix}/+")
        except Exception:
            pass

    def _on_message(self, client, userdata, msg):
        """Parse a metric message and hand it to the callback (paho thread)."""
        try:
            parsed = _parse_message(msg.topic, msg.payload, self._prefix)
            if parsed is None or self._on_metric is None:
                return
            self._on_metric(*parsed)
        except Exception:
            pass

    def update_config(self, enabled=False, host="localhost", port=1883,
                      base_topic="gpu_monitor", machine="", on_metric=None):
        """Tear down any existing connection and re-start with new settings.

        ``on_metric`` is preserved when not supplied so callers can change the
        broker/topic without re-wiring the callback.
        """
        self.stop()
        self._enabled = bool(enabled)
        self._host = host
        self._port = int(port)
        self._base_topic = base_topic
        self._machine = machine
        if on_metric is not None:
            self._on_metric = on_metric
        self._start()

    def stop(self):
        """
        Best-effort shutdown of the background connection.

        Teardown runs on a throwaway daemon thread because ``loop_stop()`` joins
        paho's network thread, which can block for the socket connect timeout
        when the broker is unreachable — we must not freeze the GUI thread.
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

        t = threading.Thread(target=_teardown, name="mqtt-sub-teardown", daemon=True)
        self._teardown_thread = t
        t.start()
