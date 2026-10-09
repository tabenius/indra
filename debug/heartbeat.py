"""Heartbeat RTT and four-timestamp clock offsets, with an SNTP reference."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import socket
import struct
import time
from uuid import uuid4

from .bridge import DebugLink

NANOSECOND = 1_000_000_000
NTP_EPOCH = 2_208_988_800


def encode_ntp(utc_ns: int) -> bytes:
    seconds, nanos = divmod(utc_ns, NANOSECOND)
    return struct.pack("!II", (seconds + NTP_EPOCH) & 0xffffffff,
                       (nanos << 32) // NANOSECOND)


def decode_ntp(raw: bytes, reference_ns: int) -> int:
    seconds, fraction = struct.unpack("!II", raw)
    # Unfold the 2036 rollover into the era nearest our local clock.
    reference = reference_ns // NANOSECOND + NTP_EPOCH
    era = (reference - seconds + (1 << 31)) // (1 << 32)
    return ((seconds + era * (1 << 32) - NTP_EPOCH) * NANOSECOND
            + fraction * NANOSECOND // (1 << 32))


@dataclass(frozen=True)
class NtpSample:
    server: str
    offset_ns: int  # NTP time minus host time; positive means host is behind.
    round_trip_ns: int
    uncertainty_ns: int
    sampled_monotonic_ns: int
    stratum: int


def parse_ntp(response: bytes, request_stamp: bytes, t1: int, t4: int,
              elapsed_ns: int, server: str) -> NtpSample:
    if len(response) < 48:
        raise ValueError("truncated NTP response")
    leap, version, mode = response[0] >> 6, (response[0] >> 3) & 7, response[0] & 7
    if leap == 3 or version not in (3, 4) or mode != 4 or not 1 <= response[1] <= 15:
        raise ValueError("NTP server unsynchronized or invalid (including kiss-of-death)")
    if response[24:32] != request_stamp:
        raise ValueError("NTP originate timestamp does not match request")
    if response[32:40] == bytes(8) or response[40:48] == bytes(8):
        raise ValueError("missing NTP timestamps")
    if abs((t4 - t1) - elapsed_ns) > 5_000_000:
        raise ValueError("host wall clock stepped during NTP measurement")
    t2 = decode_ntp(response[32:40], t4)
    t3 = decode_ntp(response[40:48], t4)
    processing = t3 - t2
    if processing < 0 or processing > elapsed_ns + 1_000_000:
        raise ValueError("invalid NTP processing interval")
    rtt = max(0, elapsed_ns - processing)
    root_delay = struct.unpack("!i", response[4:8])[0] * NANOSECOND // 65536
    dispersion = struct.unpack("!I", response[8:12])[0] * NANOSECOND // 65536
    uncertainty = rtt // 2 + max(0, root_delay) // 2 + dispersion
    return NtpSample(server, ((t2 - t1) + (t3 - t4)) // 2, rtt,
                     uncertainty, time.monotonic_ns(), response[1])


def query_ntp(server: str, timeout: float = 3, port: int = 123) -> NtpSample:
    """One read-only SNTP query. No system clock is adjusted."""
    addresses = socket.getaddrinfo(server, port, type=socket.SOCK_DGRAM)
    family, socktype, proto, _, address = addresses[0]
    with socket.socket(family, socktype, proto) as client:
        client.settimeout(timeout)
        client.connect(address)  # Only the configured peer's datagrams are received.
        request = bytearray(48)
        request[0] = 0x23  # Version 4, client mode.
        t1 = time.time_ns()
        start = time.monotonic_ns()
        request[40:48] = encode_ntp(t1)
        client.send(request)
        response = client.recv(512)
        end = time.monotonic_ns()
        t4 = time.time_ns()
    return parse_ntp(response, bytes(request[40:48]), t1, t4, end - start, server)


def measurement(start_utc: int, start_mono: int, record: dict,
                ntp: NtpSample | None = None) -> dict:
    message = record["message"]
    t2 = message["payload"]["received_utc_ns"]
    m2 = message["payload"]["received_monotonic_ns"]
    t3, m3 = message["utc_ns"], message["monotonic_ns"]
    t4, m4 = record["received_utc_ns"], record["received_monotonic_ns"]
    rtt = m4 - start_mono
    processing = m3 - m2
    if rtt < 0 or processing < 0 or processing > rtt + 1_000_000:
        raise ValueError("invalid heartbeat timestamp ordering")
    if abs((t4 - start_utc) - rtt) > 5_000_000 or abs((t3 - t2) - processing) > 5_000_000:
        raise ValueError("wall clock stepped during heartbeat measurement")
    path_rtt = max(0, rtt - processing)
    offset = ((t2 - start_utc) + (t3 - t4)) // 2  # Android minus host.
    uncertainty = path_rtt // 2 + 1_000_000  # Android wall-clock resolution is 1 ms.
    result = dict(schema="ragbaz.heartbeat/1", round_trip_ms=rtt / 1e6,
                  android_processing_ms=processing / 1e6, path_round_trip_ms=path_rtt / 1e6,
                  android_minus_host_ms=offset / 1e6, offset_uncertainty_ms=uncertainty / 1e6,
                  received_utc_ns=t4)
    if ntp is not None:
        ntp_age = max(0, m4 - ntp.sampled_monotonic_ns)
        # Allow 100 ppm of clock drift since the reference sample.
        combined = uncertainty + ntp.uncertainty_ns + ntp_age // 10000
        skew = offset - ntp.offset_ns  # Android minus NTP.
        result.update(ntp_server=ntp.server, ntp_sample_age_ms=ntp_age / 1e6,
                      host_minus_ntp_ms=-ntp.offset_ns / 1e6,
                      android_minus_ntp_ms=skew / 1e6,
                      ntp_offset_uncertainty_ms=combined / 1e6,
                      clock_skew_detected=abs(skew) > combined,
                      ntp_stratum=ntp.stratum)
    return result


async def probe(link: DebugLink, ntp: NtpSample | None, timeout: float) -> dict:
    """Owns receive() during the probe; ignores unsolicited or unrelated events."""
    async def exchange():
        probe_id = uuid4().hex
        start_utc, start_mono = time.time_ns(), time.monotonic_ns()
        sequence = await link.send("heartbeat-probe", {"probe_id": probe_id})
        while True:
            record = await link.receive()
            message = record["message"]
            if (message["kind"] == "receipt" and message.get("reply_to") == sequence
                    and message["payload"].get("payload", {}).get("probe_id") == probe_id):
                return measurement(start_utc, start_mono, record, ntp)
    return await asyncio.wait_for(exchange(), timeout)


async def monitor(link: DebugLink, *, interval: float = 1, count: int = 0,
                  timeout: float = 5, ntp_server: str = "time.cloudflare.com",
                  ntp_refresh: float = 60):
    """Yield heartbeat samples continuously, with explicit NTP/timeout failures."""
    ntp = None
    next_ntp = 0.0
    ntp_error = None
    history = deque(maxlen=128)
    index = 0
    while count == 0 or index < count:
        if time.monotonic() >= next_ntp:
            try:
                ntp = await asyncio.to_thread(query_ntp, ntp_server, min(timeout, 3))
                ntp_error = None
            except (OSError, ValueError) as exc:
                ntp = None
                ntp_error = str(exc)
            next_ntp = time.monotonic() + ntp_refresh
        started = time.monotonic()
        index += 1
        try:
            sample = await probe(link, ntp, timeout)
            history.append(sample["round_trip_ms"])
            ordered = sorted(history)
            sample.update(status="ok", sample=index, window_samples=len(history),
                          rtt_min_ms=ordered[0], rtt_mean_ms=sum(history) / len(history),
                          rtt_p95_ms=ordered[(95 * len(ordered) + 99) // 100 - 1],
                          ntp_status="ok" if ntp is not None else "unavailable")
            if ntp_error:
                sample["ntp_error"] = ntp_error
        except (TimeoutError, ValueError) as exc:
            sample = dict(schema="ragbaz.heartbeat/1", status="timeout" if isinstance(exc, TimeoutError)
                          else "invalid-timestamps", sample=index, detail=str(exc))
        yield sample
        if count == 0 or index < count:
            await asyncio.sleep(max(0, interval - (time.monotonic() - started)))
