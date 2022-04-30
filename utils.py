import asyncio
import json
from asyncio import Task


def json_encode(data, encoding: str) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode(encoding)


def json_decode(bin_data: bytes, encoding: str) -> dict:
    return json.loads(bin_data.decode(encoding))


async def async_input(prompt: str) -> str:
    return await asyncio.get_event_loop().run_in_executor(None, input, prompt)


async def wait_until_first_completed(tasks: list[Task]):
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        feature, = done
        return feature.result()
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
