import asyncio
import json
import unittest

from debug.auth import authenticate_client, authenticate_server, pack, session_keys, unpack
from debug.bridge import DebugLink

KEY = bytes(range(32))


class AuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_pair_key_cannot_authenticate(self):
        rejected = asyncio.Event()

        async def server(reader, writer):
            try:
                await authenticate_server(reader, writer, KEY)
                self.fail("wrong-key client authenticated")
            except ConnectionError:
                rejected.set()
            finally:
                writer.close()
                await writer.wait_closed()
        listener = await asyncio.start_server(server, "127.0.0.1", 0)
        async with listener:
            with self.assertRaises(ConnectionError):
                await DebugLink.connect(port=listener.sockets[0].getsockname()[1], key=b"x" * 32)
            await asyncio.wait_for(rejected.wait(), 2)

    async def test_fake_bridge_cannot_authenticate_to_host(self):
        async def server(reader, writer):
            challenge = {"schema": "ragbaz.debug-auth/1", "kind": "challenge", "nonce": "00" * 32}
            writer.write(json.dumps(challenge).encode() + b"\n")
            await writer.drain()
            await reader.readline()
            writer.write(b'{"schema":"ragbaz.debug-auth/1","kind":"accepted","proof":"bad"}\n')
            await writer.drain()
            writer.close()
        listener = await asyncio.start_server(server, "127.0.0.1", 0)
        async with listener:
            with self.assertRaisesRegex(ConnectionError, "bridge authentication failed"):
                await DebugLink.connect(port=listener.sockets[0].getsockname()[1], key=KEY)

    def test_tampering_reflection_and_cross_session_replay_are_rejected(self):
        send, receive = session_keys(KEY, b"s" * 32, b"c" * 32)
        frame = pack({"value": "original"}, send)
        self.assertEqual(unpack(frame, send), {"value": "original"})
        with self.assertRaises(ValueError):
            unpack(frame.replace(b"original", b"tampered"), send)
        with self.assertRaises(ValueError):
            unpack(frame, receive)
        other_send, _ = session_keys(KEY, b"n" * 32, b"c" * 32)
        with self.assertRaises(ValueError):
            unpack(frame, other_send)


if __name__ == "__main__":
    unittest.main()
