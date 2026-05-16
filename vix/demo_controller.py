from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Iterable

import httpx

DEFAULT_INSTRUMENT_URLS = [
    "http://localhost:8101",
    "http://localhost:8102",
    "http://localhost:8103",
]


async def drive_phase(phase: str, clients: Iterable[httpx.AsyncClient]) -> list[dict]:
    async def _one(c: httpx.AsyncClient) -> dict:
        r = await c.post("/scenario/phase", json={"phase": phase}, timeout=5.0)
        r.raise_for_status()
        return r.json()

    return await asyncio.gather(*(_one(c) for c in clients))


async def _main(phase: str, urls: list[str]) -> int:
    clients = [httpx.AsyncClient(base_url=u) for u in urls]
    try:
        results = await drive_phase(phase, clients)
    finally:
        for c in clients:
            await c.aclose()
    for u, r in zip(urls, results):
        print(f"{u} -> {r}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--phase", required=True, choices=["baseline", "failure", "recovery"])
    p.add_argument("--urls", nargs="*", default=DEFAULT_INSTRUMENT_URLS)
    args = p.parse_args()
    sys.exit(asyncio.run(_main(args.phase, args.urls)))


if __name__ == "__main__":
    main()
