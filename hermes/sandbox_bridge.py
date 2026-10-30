#!/usr/bin/env python3
"""Bridge the two local servers into a cell sandbox that has no network of its own.

The sandbox (bwrap --unshare-net) has only a loopback interface. The model server (8355) and
the embedder (8360) are reached through unix sockets in the cell's directory:

  host side    sandbox_bridge.py host SOCK=HOST:PORT ...
               listens on each unix socket and forwards to HOST:PORT on the real network
  inside       sandbox_bridge.py inside PORT=SOCK ... -- COMMAND ...
               starts a forwarder from 127.0.0.1:PORT (and [::1]:PORT) to each socket in a
               child process, waits until every port accepts, then execs COMMAND

Nothing else is bridged, so no other host or port is reachable from inside. Bytes are copied
unchanged in both directions (HTTP and streamed responses alike).
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


def _handler(connect):
    async def handle(r1: asyncio.StreamReader, w1: asyncio.StreamWriter) -> None:
        try:
            r2, w2 = await connect()
        except Exception:
            w1.close()
            return
        await asyncio.gather(_pipe(r1, w2), _pipe(r2, w1))
    return handle


def _logged(connect, port: int):
    """Log every host-side connection with its destination port, as evidence of what was reached."""
    async def go():
        print(f"{time.time():.3f} connect 127.0.0.1:{port}", file=sys.stderr, flush=True)
        return await connect()
    return go


async def _serve_host(pairs: list[tuple[str, str, int]]) -> None:
    servers = []
    for sock, host, port in pairs:
        if os.path.exists(sock):
            os.unlink(sock)
        servers.append(await asyncio.start_unix_server(
            _handler(_logged(lambda h=host, p=port: asyncio.open_connection(h, p), port)), path=sock))
    await asyncio.gather(*(s.serve_forever() for s in servers))


async def _serve_inside(pairs: list[tuple[int, str]]) -> None:
    servers = []
    for port, sock in pairs:
        h = _handler(lambda s=sock: asyncio.open_unix_connection(s))
        servers.append(await asyncio.start_server(h, host="127.0.0.1", port=port))
        try:
            servers.append(await asyncio.start_server(h, host="::1", port=port))
        except OSError:
            pass  # no IPv6 loopback in this namespace
    await asyncio.gather(*(s.serve_forever() for s in servers))


def _wait_ports(ports: list[int], timeout: float = 15.0) -> bool:
    end = time.time() + timeout
    left = set(ports)
    while left and time.time() < end:
        for p in list(left):
            try:
                with socket.create_connection(("127.0.0.1", p), timeout=0.5):
                    left.discard(p)
            except OSError:
                pass
        if left:
            time.sleep(0.05)
    return not left


def main() -> int:
    mode, args = sys.argv[1], sys.argv[2:]
    if mode == "host":
        pairs = []
        for a in args:
            sock, hp = a.split("=", 1)
            host, port = hp.rsplit(":", 1)
            pairs.append((sock, host, int(port)))
        asyncio.run(_serve_host(pairs))
        return 0
    if mode == "serve-inside":
        asyncio.run(_serve_inside([(int(a.split("=", 1)[0]), a.split("=", 1)[1]) for a in args]))
        return 0
    if mode == "inside":
        cut = args.index("--")
        specs, cmd = args[:cut], args[cut + 1:]
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "serve-inside", *specs],
                         stdin=subprocess.DEVNULL, start_new_session=True)
        if not _wait_ports([int(s.split("=", 1)[0]) for s in specs]):
            print("ABORT: sandbox bridge did not come up", file=sys.stderr)
            return 3
        os.execv(cmd[0], cmd)
    print(f"unknown mode {mode!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
