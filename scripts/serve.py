"""Uvicorn child with a private stop-file channel for graceful cross-platform shutdown."""

import argparse
import asyncio
from pathlib import Path

import uvicorn


async def run(args):
    server = uvicorn.Server(
        uvicorn.Config(
            args.factory, factory=True, host=args.host, port=args.port, workers=1, ws="websockets"
        )
    )

    async def watch():
        while not server.should_exit:
            if Path(args.stop_file).exists():
                server.should_exit = True
                return
            await asyncio.sleep(0.1)

    watcher = asyncio.create_task(watch())
    try:
        await server.serve()
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--stop-file", required=True)
    asyncio.run(run(parser.parse_args()))
