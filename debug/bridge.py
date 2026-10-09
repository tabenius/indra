"""Bounded, asynchronous full-duplex JSON-lines link over adb-forwarded TCP."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

SCHEMA = "ragbaz.debug/1"
MAX_FRAME = 65536


def validate(message: Any) -> dict[str, Any]:
    if not isinstance(message, dict) or message.get("schema") != SCHEMA:
        raise ValueError("invalid debug envelope schema")
    for key in ("seq", "utc_ns", "monotonic_ns"):
        if type(message.get(key)) is not int or message[key] < 0:
            raise ValueError(f"invalid {key}")
    for key in ("source", "kind"):
        if not isinstance(message.get(key), str) or not message[key]:
            raise ValueError(f"invalid {key}")
    if not isinstance(message.get("payload"), dict):
        raise ValueError("payload must be an object")
    if "reply_to" in message and (type(message["reply_to"]) is not int or message["reply_to"] < 1):
        raise ValueError("invalid reply_to")
    return message


class DebugLink:
    """One connection, independent reader/writer tasks and bounded queues.

    send() acknowledges local transport drain, not peer processing. Receive
    records add host receive timestamps; monotonic clocks are not comparable
    across devices. EOF and malformed frames close the link and wake waiters.
    """

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 queue_size: int = 128):
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        self.reader, self.writer = reader, writer
        self.incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue(queue_size)
        self.outgoing: asyncio.Queue[tuple[bytes, asyncio.Future[None]]] = asyncio.Queue(queue_size)
        self.closed = asyncio.Event()
        self.error: Exception | None = None
        self.seq = 0
        self.send_lock = asyncio.Lock()
        self.tasks = [asyncio.create_task(self._read()), asyncio.create_task(self._write())]

    @classmethod
    async def connect(cls, host: str = "127.0.0.1", port: int = 8769,
                      queue_size: int = 128) -> DebugLink:
        reader, writer = await asyncio.open_connection(host, port, limit=MAX_FRAME)
        return cls(reader, writer, queue_size)

    async def _until_closed(self, operation):
        action = asyncio.create_task(operation)
        stop = asyncio.create_task(self.closed.wait())
        try:
            await asyncio.wait((action, stop), return_when=asyncio.FIRST_COMPLETED)
            if action.done():
                return action.result()
            raise ConnectionError("debug link closed") from self.error
        finally:
            for task in (action, stop):
                if not task.done():
                    task.cancel()
            await asyncio.gather(action, stop, return_exceptions=True)

    async def send(self, kind: str, payload: dict[str, Any], *, reply_to: int | None = None) -> int:
        async with self.send_lock:
            if self.closed.is_set():
                raise ConnectionError("debug link closed") from self.error
            self.seq += 1
            message = dict(schema=SCHEMA, source="indra", seq=self.seq, kind=kind,
                           utc_ns=time.time_ns(), monotonic_ns=time.monotonic_ns(), payload=payload)
            if reply_to is not None:
                message["reply_to"] = reply_to
            validate(message)
            frame = json.dumps(message, allow_nan=False, separators=(",", ":")).encode() + b"\n"
            if len(frame) > MAX_FRAME:
                raise ValueError("debug frame exceeds 64 KiB")
            receipt = asyncio.get_running_loop().create_future()
            await self._until_closed(self.outgoing.put((frame, receipt)))
            # Shield the receipt so caller cancellation does not cancel the writer.
            await self._until_closed(self._receipt(receipt))
            return self.seq

    @staticmethod
    async def _receipt(receipt):
        await asyncio.shield(receipt)

    async def receive(self) -> dict[str, Any]:
        if not self.incoming.empty():
            return self.incoming.get_nowait()
        return await self._until_closed(self.incoming.get())

    async def _read(self):
        try:
            last_seq = 0
            while True:
                frame = await self.reader.readline()
                if not frame:
                    raise EOFError("Android bridge disconnected")
                if not frame.endswith(b"\n") or len(frame) > MAX_FRAME:
                    raise ValueError("invalid or oversized debug frame")
                message = validate(json.loads(frame))
                if message["seq"] <= last_seq:
                    raise ValueError("peer sequence must increase")
                last_seq = message["seq"]
                record = dict(message=message, received_utc_ns=time.time_ns(),
                              received_monotonic_ns=time.monotonic_ns())
                await self.incoming.put(record)
        except Exception as exc:
            self.error = exc
        finally:
            self.closed.set()
            self.writer.close()

    async def _write(self):
        try:
            while True:
                frame, receipt = await self.outgoing.get()
                self.writer.write(frame)
                await self.writer.drain()
                if not receipt.done():
                    receipt.set_result(None)
        except Exception as exc:
            self.error = exc
        finally:
            self.closed.set()
            self.writer.close()

    async def close(self):
        self.closed.set()
        self.writer.close()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.writer.wait_closed()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()
