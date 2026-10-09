import asyncio
import struct
import unittest
from unittest.mock import patch

from debug.heartbeat import NtpSample, decode_ntp, encode_ntp, measurement, monitor, parse_ntp, query_ntp


class ClockTests(unittest.TestCase):
    def test_four_timestamp_offsets_and_signs(self):
        t1 = 10_000_000_000
        record = dict(message=dict(utc_ns=t1 + 26_000_000, monotonic_ns=106_000_000,
                                   payload=dict(received_utc_ns=t1 + 24_000_000,
                                                received_monotonic_ns=104_000_000)),
                      received_utc_ns=t1 + 10_000_000, received_monotonic_ns=210_000_000)
        ntp = NtpSample("test", 5_000_000, 2_000_000, 1_000_000, 210_000_000, 1)
        result = measurement(t1, 200_000_000, record, ntp)
        self.assertEqual(result["round_trip_ms"], 10)
        self.assertEqual(result["android_processing_ms"], 2)
        self.assertEqual(result["path_round_trip_ms"], 8)
        self.assertEqual(result["android_minus_host_ms"], 20)
        self.assertEqual(result["host_minus_ntp_ms"], -5)
        self.assertEqual(result["android_minus_ntp_ms"], 15)
        self.assertTrue(result["clock_skew_detected"])
        record["received_utc_ns"] += 100_000_000
        with self.assertRaisesRegex(ValueError, "clock stepped"):
            measurement(t1, 200_000_000, record, ntp)

    def test_ntp_validation_offset_and_era_rollover(self):
        t1 = 1_800_000_000_000_000_000
        stamp = encode_ntp(t1)
        response = bytearray(48)
        response[0], response[1] = 0x24, 2
        response[24:32] = stamp
        response[32:40] = encode_ntp(t1 + 8_000_000)
        response[40:48] = encode_ntp(t1 + 10_000_000)
        sample = parse_ntp(response, stamp, t1, t1 + 10_000_000, 10_000_000, "test")
        self.assertAlmostEqual(sample.offset_ns, 4_000_000, delta=1)
        self.assertAlmostEqual(sample.round_trip_ns, 8_000_000, delta=1)
        for offset, byte in ((0, 0xe4), (1, 0), (24, 255)):
            invalid = bytearray(response)
            invalid[offset] = byte
            with self.assertRaises(ValueError):
                parse_ntp(invalid, stamp, t1, t1 + 10_000_000, 10_000_000, "test")
        for seconds in (2_085_978_495, 2_085_978_497):
            utc = seconds * 1_000_000_000
            self.assertEqual(decode_ntp(encode_ntp(utc), utc), utc)


class NtpExchangeTest(unittest.IsolatedAsyncioTestCase):
    async def test_monitor_continues_when_ntp_is_unavailable(self):
        import time

        class Link:
            async def send(self, kind, payload):
                self.payload = payload
                self.stage = 0
                return 7

            async def receive(self):
                self.stage += 1
                if self.stage == 1:
                    return {"message": {"kind": "heartbeat", "payload": {}}}
                if self.stage == 2:
                    return {"message": {"kind": "receipt", "reply_to": 99, "payload": {}}}
                t2, m2 = time.time_ns(), time.monotonic_ns()
                await asyncio.sleep(0.001)
                t3, m3 = time.time_ns(), time.monotonic_ns()
                return dict(message=dict(kind="receipt", reply_to=7, utc_ns=t3,
                                         monotonic_ns=m3, payload=dict(payload=self.payload,
                                         received_utc_ns=t2, received_monotonic_ns=m2)),
                            received_utc_ns=time.time_ns(), received_monotonic_ns=time.monotonic_ns())

        with patch("debug.heartbeat.query_ntp", side_effect=TimeoutError("no NTP reply")):
            samples = [sample async for sample in monitor(Link(), count=2, interval=0.001)]
        self.assertEqual(len(samples), 2)
        self.assertTrue(all(sample["status"] == "ok" for sample in samples))
        self.assertTrue(all(sample["ntp_status"] == "unavailable" for sample in samples))
        self.assertNotIn("android_minus_ntp_ms", samples[0])
        self.assertEqual(samples[-1]["window_samples"], 2)

    async def test_silent_peer_times_out(self):
        class Link:
            async def send(self, kind, payload):
                return 1

            async def receive(self):
                await asyncio.Event().wait()

        with patch("debug.heartbeat.query_ntp", side_effect=TimeoutError("no NTP reply")):
            samples = [sample async for sample in monitor(Link(), count=1, timeout=0.01)]
        self.assertEqual(samples[0]["status"], "timeout")

    async def test_real_udp_exchange(self):
        import time

        class Server(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, request, peer):
                response = bytearray(48)
                response[0], response[1] = 0x24, 1
                response[24:32] = request[40:48]
                response[32:40] = encode_ntp(time.time_ns())
                response[40:48] = encode_ntp(time.time_ns())
                self.transport.sendto(response, peer)

        transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(Server, local_addr=("127.0.0.1", 0))
        try:
            sample = await asyncio.to_thread(query_ntp, "127.0.0.1", 2, transport.get_extra_info("sockname")[1])
            self.assertEqual(sample.stratum, 1)
            self.assertLess(abs(sample.offset_ns), 100_000_000)
        finally:
            transport.close()


if __name__ == "__main__":
    unittest.main()
