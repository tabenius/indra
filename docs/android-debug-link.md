# Asynchronous Android debug link

The host module `debug.bridge.DebugLink` connects Indra development tooling to
the debug endpoint in `ragbaz-bridge-android` (also called the Android bridge).
This is a separate local debug channel, not an OSHI transport or a released
Indra application. Upstream mesh identifiers and relay behavior are unchanged.

## Start

Build and install the bridge's debug APK, open its activity, then forward TCP:

```sh
adb shell am start -n com.ragbaz.bridge/.MainActivity
adb forward tcp:8769 tcp:8769
python3 -m debug
```

The Android listener binds `127.0.0.1:8769` only, starts only in a debuggable
application, and stops when the activity is destroyed. Each line on standard
input sends a debug message while incoming receipts and unsolicited heartbeats
are printed concurrently. Use `adb -s SERIAL forward ...` with multiple devices.

## Embed

```python
from debug import DebugLink

async with await DebugLink.connect() as link:
    # Run this independently of a receive loop in your application.
    sequence = await link.send("debug", {"event": "peer-observed"})
    record = await link.receive()
```

The two directions are independent; `receive()` may yield `hello`, `heartbeat`,
or `receipt` without a preceding request. The Android `DebugServer.publish()`
hook can emit application-specific events to connected clients. The endpoint
does not execute commands, send SMS, or change mesh configuration.

## Wire contract: `ragbaz.debug/1`

UTF-8 JSON objects terminated by LF, maximum 65,536 bytes including LF:

```json
{"schema":"ragbaz.debug/1","source":"indra","seq":1,"kind":"debug","utc_ns":1000000000,"monotonic_ns":500000000,"payload":{"event":"example"}}
```

Each direction has its own increasing sequence starting at 1 per connection.
Receipts include `reply_to`, identifying the sender's sequence. `utc_ns` is Unix
time in nanosecond units (Android wall clock has millisecond resolution).
`monotonic_ns` is process/device-local elapsed time: never subtract monotonic
timestamps from different devices. Host receive records contain
`received_utc_ns` and `received_monotonic_ns`; Android receipts include the
equivalent receive timestamps in their payload. Wall-clock comparison requires
clock synchronization; timestamps alone do not establish network latency.

Both host queues and the Android output queue are bounded to 128 messages.
The host applies backpressure; Android disconnects a peer when output cannot
be queued. EOF, invalid envelopes, or oversized frames terminate the connection.
`send()` means local TCP drain, while `receipt` confirms Android processing.
Reconnection is explicit and starts a new sequence; no messages are replayed.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_debug_bridge.py'
python3 tools/verify_indra.py
```

Host tests use real loopback TCP, including concurrent sending, unsolicited
events, timestamps, disconnects, malformed frames and size bounds. Device-side
build and actual adb-forwarded interaction are separate checks; loopback tests
do not prove installation or device behavior.

On 2026-10-09 the debug APK was built and installed on a connected Samsung
SM-G988B. A real adb-forwarded session verified the hello, a correlated receipt
with Android send/receive timestamps, and an unsolicited heartbeat. The temporary
host forwarding rule was removed after the probe.
