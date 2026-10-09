# Asynchronous Android debug link

The host module `debug.bridge.DebugLink` connects Indra development tooling to
the debug endpoint in `ragbaz-bridge-android` (also called the Android bridge).
This is a separate local debug channel, not an OSHI transport or a released
Indra application. Upstream mesh identifiers and relay behavior are unchanged.

## Start

Build and install the bridge's debug APK, provision the pair's key, open its
activity, then forward TCP:

```sh
python3 -m debug.pair --serial SERIAL
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

## Authenticated pair

Both peers must prove possession of the same random 256-bit pairing key before
any hello, heartbeat, debug event or receipt is accepted. Provisioning uses the
authorized adb connection and `run-as com.ragbaz.bridge`:

- Host: `~/.config/indra/bridge.key`, mode `0600`.
- Android: the app's private `files/indra-debug.key`, mode `0600`.
- For several devices, use a distinct `--key-file` for each pair, both when
  provisioning and when connecting. Re-running pairing reuses that file's key;
  choose a new file to rotate, and provision it to the intended device.

The bridge sends a fresh 32-byte nonce, the host responds with its own fresh
nonce and an HMAC-SHA256 host proof, and the bridge returns a distinct bridge
proof. Both proofs bind both nonces and the `ragbaz.debug-auth/1` domain. The
host verifies the bridge proof before creating the debug link. The bridge
verifies the host proof before starting its event/receipt threads.

The transcript derives session keys separately for host-to-bridge and
bridge-to-host. Every subsequent line is an authenticated wrapper:

```json
{"body":"<serialized ragbaz.debug/1 envelope>","mac":"<HMAC-SHA256 hex>"}
```

The MAC covers the exact UTF-8 body bytes. Fresh session keys prevent
cross-session replay; direction-separated keys prevent reflection; increasing
sequence checks reject duplicate frames within a session. MAC failures close
the connection. There is no unauthenticated compatibility fallback. The key is
never sent on this TCP channel, printed, placed on argv, or committed to Git.
This authenticates messages; it does not encrypt their contents. The channel is
loopback TCP carried through the authorized adb connection.

## Heartbeat Δt and NTP comparison

```sh
python3 -m debug --heartbeat --interval 1 --ntp-server time.cloudflare.com
# Bounded measurement run:
python3 -m debug --heartbeat --count 10
```

Probes are correlated by sequence and a random probe ID. Output is JSON-lines:
RTT, Android processing time, path RTT, rolling minimum/mean/p95, Android minus
host offset, and (when NTP responds) host minus NTP and Android minus NTP offset.
Positive offsets mean the named clock is ahead. `clock_skew_detected` means the
Android-to-NTP offset exceeds the uncertainty estimate, not that its frequency
drift has been measured.

Four timestamps are used: host send `t1`, Android receive `t2`, Android send `t3`,
host receive `t4`. Android-minus-host offset is
`((t2 - t1) + (t3 - t4)) / 2`. RTT uses the host monotonic clock; Android
processing time uses only Android's monotonic clock. Path RTT subtracts that
processing interval. Scheduling and output-queue time remain part of this
end-to-end measurement. Offset uncertainty includes half the path RTT and
Android's millisecond wall-clock resolution. This assumes approximately
symmetric delays; offset estimates are not exact one-way latency measurements.

NTP is queried read-only every 60 seconds. Replies must match the request's
originate timestamp and declare synchronized server mode and a valid stratum.
Root delay/dispersion and reference age are included in the clock-offset
uncertainty estimate (100 ppm drift allowance). The query is ordinary SNTP,
not authenticated NTS; it is a time reference rather than an authentication
authority. It does not adjust either clock. An NTP timeout reports
`ntp_status: unavailable`, while heartbeat latency measurements continue.
Wall-clock steps detected during an exchange invalidate that measurement.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_debug_*.py'
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

The authenticated revision was subsequently installed and paired on the same
device. Live tests rejected a wrong pairing key and disconnected on a forged
message MAC. Five authenticated heartbeat probes measured 18–30 ms RTT;
Android was approximately 453–458 ms ahead of the NTP reference, exceeding
the estimated 23–30 ms uncertainty. These are observations from that run,
not fixed performance guarantees.
