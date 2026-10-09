"""Interactive debug sender with concurrent timestamped JSON receive output."""

import argparse
import asyncio
import json
import sys

from .bridge import DebugLink
from .heartbeat import monitor
from .auth import DEFAULT_KEY, load_key


async def run(port, heartbeat=False, interval=1, count=0, timeout=5,
              ntp_server="time.cloudflare.com", ntp_refresh=60, key_file=DEFAULT_KEY):
    async with await DebugLink.connect(port=port, key=load_key(key_file)) as link:
        if heartbeat:
            async for sample in monitor(link, interval=interval, count=count, timeout=timeout,
                                        ntp_server=ntp_server, ntp_refresh=ntp_refresh):
                print(json.dumps(sample), flush=True)
            return
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
    parser.add_argument("--key-file", default=str(DEFAULT_KEY))
    parser.add_argument("--heartbeat", action="store_true", help="measure RTT and NTP-referenced clock offsets")
    parser.add_argument("--interval", type=float, default=1, help="probe interval in seconds")
    parser.add_argument("--count", type=int, default=0, help="number of probes; 0 runs continuously")
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--ntp-server", default="time.cloudflare.com")
    parser.add_argument("--ntp-refresh", type=float, default=60)
    args = parser.parse_args()
    if args.interval <= 0 or args.timeout <= 0 or args.ntp_refresh <= 0 or args.count < 0:
        parser.error("interval, timeout and ntp-refresh must be positive; count must be nonnegative")
    try:
        asyncio.run(run(args.port, args.heartbeat, args.interval, args.count, args.timeout,
                        args.ntp_server, args.ntp_refresh, args.key_file))
    except (ConnectionError, OSError, ValueError, TimeoutError) as exc:
        parser.exit(1, f"debug link: {exc}\n")
