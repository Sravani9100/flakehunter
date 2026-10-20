import asyncio
import random


async def fetch(name: str) -> str:
    await asyncio.sleep(random.uniform(0, 0.01))  # stands in for an HTTP call
    return name


async def fetch_all(names: list[str]) -> list[str]:
    results: list[str] = []

    async def worker(name: str) -> None:
        results.append(await fetch(name))

    await asyncio.gather(*(worker(n) for n in names))
    return results
