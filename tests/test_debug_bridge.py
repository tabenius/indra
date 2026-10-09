import asyncio
import json
import time
import unittest

from debug.bridge import DebugLink, MAX_FRAME, SCHEMA
from debug.auth import authenticate_server, pack, unpack

KEY = b"test-pair-key-not-for-production!".ljust(32, b"!")[:32]


class AuthReader:
    def __init__(self, reader, key):
        self.reader, self.key = reader, key

    async def readline(self):
        return json.dumps(unpack(await self.reader.readline(), self.key)).encode() + b"\n"

    async def read(self):
        return await self.reader.read()


class AuthWriter:
    def __init__(self, writer, key):
        self.writer, self.key = writer, key

    def write(self, frame):
        try:
            message = json.loads(frame)
        except (ValueError, UnicodeError):
            self.writer.write(frame)  # Deliberate malformed/oversized frames.
        else:
            self.writer.write(pack(message, self.key))

    async def drain(self):
        await self.writer.drain()

    def close(self):
        self.writer.close()


def envelope(seq, kind="heartbeat", payload=None):
    return dict(schema=SCHEMA, source="ragbaz-bridge-android", seq=seq, kind=kind,
                utc_ns=time.time_ns(), monotonic_ns=time.monotonic_ns(), payload=payload or {})


class DebugBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.handlers = []
        self.writers = []

    async def asyncTearDown(self):
        for writer in self.writers:
            writer.close()
        for task in self.handlers:
            task.cancel()
        await asyncio.gather(*self.handlers, return_exceptions=True)

    async def connect(self, handler):
        async def track(reader, writer):
            self.handlers.append(asyncio.current_task())
            self.writers.append(writer)
            receive_key, send_key = await authenticate_server(reader, writer, KEY)
            await handler(AuthReader(reader, receive_key), AuthWriter(writer, send_key))
        server = await asyncio.start_server(track, "127.0.0.1", 0)
        self.addAsyncCleanup(server.wait_closed)
        self.addCleanup(server.close)
        return await DebugLink.connect(port=server.sockets[0].getsockname()[1], key=KEY)

    async def test_unsolicited_events_and_concurrent_sends_have_timestamps(self):
        async def bridge(reader, writer):
            writer.write(json.dumps(envelope(1)).encode() + b"\n")
            await writer.drain()
            for seq in range(2, 22):
                message = json.loads(await reader.readline())
                self.assertEqual(message["seq"], seq - 1)
                self.assertGreater(message["utc_ns"], 0)
                self.assertGreater(message["monotonic_ns"], 0)
                reply = envelope(seq, "receipt", message["payload"])
                reply["reply_to"] = message["seq"]
                writer.write(json.dumps(reply).encode() + b"\n")
                await writer.drain()
            await reader.read()
        async with await self.connect(bridge) as link:
            heartbeat = await asyncio.wait_for(link.receive(), 2)
            self.assertEqual(heartbeat["message"]["kind"], "heartbeat")
            self.assertGreater(heartbeat["received_utc_ns"], 0)
            sends = asyncio.gather(*(link.send("debug", {"value": i}) for i in range(20)))
            replies = [await asyncio.wait_for(link.receive(), 2) for _ in range(20)]
            self.assertEqual(await sends, list(range(1, 21)))
            self.assertEqual([r["message"]["reply_to"] for r in replies], list(range(1, 21)))

    async def test_disconnect_wakes_receiver(self):
        async def bridge(reader, writer):
            writer.close()
        async with await self.connect(bridge) as link:
            with self.assertRaises(ConnectionError):
                await asyncio.wait_for(link.receive(), 2)
            with self.assertRaises(ConnectionError):
                await link.send("debug", {})

    async def test_invalid_peer_frames_close_link(self):
        for frame in (b"not-json\n", b'{}\n', b"x" * (MAX_FRAME + 1) + b"\n"):
            async def bridge(reader, writer):
                writer.write(frame)
                await writer.drain()
                await reader.read()
            async with await self.connect(bridge) as link:
                with self.assertRaises(ConnectionError):
                    await asyncio.wait_for(link.receive(), 2)

    async def test_oversized_send_rejected_without_killing_connection(self):
        async def bridge(reader, writer):
            message = json.loads(await reader.readline())
            writer.write(json.dumps(envelope(1, "receipt", message["payload"])).encode() + b"\n")
            await writer.drain()
            await reader.read()
        async with await self.connect(bridge) as link:
            with self.assertRaises(ValueError):
                await link.send("debug", {"text": "x" * MAX_FRAME})
            await link.send("debug", {"text": "small"})
            self.assertEqual((await asyncio.wait_for(link.receive(), 2))["message"]["payload"], {"text": "small"})


if __name__ == "__main__":
    unittest.main()
