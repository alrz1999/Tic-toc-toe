import asyncio
import json


def json_encode(data, encoding: str) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode(encoding)


def json_decode(bin_data: bytes, encoding: str) -> dict:
    return json.loads(bin_data.decode(encoding))


async def async_input(prompt: str) -> str:
    return await asyncio.get_event_loop().run_in_executor(None, input, prompt)
