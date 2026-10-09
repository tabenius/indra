"""Mutual PSK challenge/response and direction-separated frame authentication."""

import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import secrets

AUTH = "ragbaz.debug-auth/1"
MAX_FRAME = 65536
DEFAULT_KEY = Path.home() / ".config" / "indra" / "bridge.key"


def load_key(path=DEFAULT_KEY):
    path = Path(path)
    if path.stat().st_mode & 0o077:
        raise PermissionError(f"pairing key must be private (chmod 600): {path}")
    key = bytes.fromhex(path.read_text().strip())
    if len(key) != 32:
        raise ValueError("pairing key must contain 32 bytes encoded as hex")
    return key


def proof(key, role, server_nonce=b"", client_nonce=b""):
    transcript = AUTH.encode() + b"\0" + role.encode() + b"\0" + server_nonce + client_nonce
    return hmac.digest(key, transcript, "sha256")


def nonce(value):
    if not isinstance(value, str) or len(value) != 64:
        raise ConnectionError("invalid authentication nonce")
    try:
        decoded = bytes.fromhex(value)
    except ValueError as exc:
        raise ConnectionError("invalid authentication nonce") from exc
    if len(decoded) != 32:
        raise ConnectionError("invalid authentication nonce")
    return decoded


async def read_handshake(reader):
    frame = await reader.readline()
    if not frame.endswith(b"\n") or len(frame) > MAX_FRAME:
        raise ConnectionError("invalid authentication frame")
    message = json.loads(frame)
    if not isinstance(message, dict) or message.get("schema") != AUTH:
        raise ConnectionError("peer did not authenticate")
    return message


async def send_handshake(writer, **fields):
    writer.write(json.dumps(dict(schema=AUTH, **fields), separators=(",", ":")).encode() + b"\n")
    await writer.drain()


def session_keys(key, server_nonce, client_nonce):
    session = proof(key, "session", server_nonce, client_nonce)
    return proof(session, "host-to-bridge"), proof(session, "bridge-to-host")


async def authenticate_client(reader, writer, key, timeout=5):
    async def exchange():
        challenge = await read_handshake(reader)
        if challenge.get("kind") != "challenge":
            raise ConnectionError("expected bridge authentication challenge")
        server = nonce(challenge.get("nonce"))
        client = secrets.token_bytes(32)
        await send_handshake(writer, kind="proof", nonce=client.hex(),
                             proof=proof(key, "host", server, client).hex())
        reply = await read_handshake(reader)
        expected = proof(key, "bridge", server, client).hex()
        if reply.get("kind") != "accepted" or not isinstance(reply.get("proof"), str) or not hmac.compare_digest(reply["proof"], expected):
            raise ConnectionError("bridge authentication failed")
        return session_keys(key, server, client)
    if len(key) != 32:
        raise ValueError("pairing key must be 32 bytes")
    return await asyncio.wait_for(exchange(), timeout)


async def authenticate_server(reader, writer, key, timeout=5):
    """Reference server handshake, also used by the protocol tests."""
    async def exchange():
        server = secrets.token_bytes(32)
        await send_handshake(writer, kind="challenge", nonce=server.hex())
        reply = await read_handshake(reader)
        client = nonce(reply.get("nonce"))
        expected = proof(key, "host", server, client).hex()
        if reply.get("kind") != "proof" or not isinstance(reply.get("proof"), str) or not hmac.compare_digest(reply["proof"], expected):
            raise ConnectionError("host authentication failed")
        await send_handshake(writer, kind="accepted", proof=proof(key, "bridge", server, client).hex())
        return session_keys(key, server, client)
    return await asyncio.wait_for(exchange(), timeout)


def pack(message, key):
    body = json.dumps(message, allow_nan=False, separators=(",", ":"))
    mac = hmac.new(key, body.encode(), hashlib.sha256).hexdigest()
    frame = json.dumps(dict(body=body, mac=mac), separators=(",", ":")).encode() + b"\n"
    if len(frame) > MAX_FRAME:
        raise ValueError("authenticated debug frame exceeds 64 KiB")
    return frame


def unpack(frame, key):
    wrapper = json.loads(frame)
    if not isinstance(wrapper, dict) or not isinstance(wrapper.get("body"), str) or not isinstance(wrapper.get("mac"), str):
        raise ValueError("missing authenticated debug frame")
    expected = hmac.new(key, wrapper["body"].encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(wrapper["mac"], expected):
        raise ValueError("debug frame authentication failed")
    return json.loads(wrapper["body"])
