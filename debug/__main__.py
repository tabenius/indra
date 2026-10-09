"""Interactive debug sender with concurrent timestamped JSON receive output."""

import argparse
import asyncio
import json
import sys

from .bridge import DebugLink


async def run(port):
    async with await DebugLink.connect(port=port) as link:
        async def incoming():
            while True:
                print(json.dumps(await link.receive()), flush=True)

        async def outgoing():
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            transport, _ = await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, sys.stdin)
            try:
                while line := await reader.readline():
                    await link.send("debug", {"text": line.decode().rstrip("\n")})
            finally:
                transport.close()

        tasks = [asyncio.create_task(incoming()), asyncio.create_task(outgoing())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8769)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.port))
    except (ConnectionError, OSError) as exc:
        parser.exit(1, f"debug link: {exc}\n")
