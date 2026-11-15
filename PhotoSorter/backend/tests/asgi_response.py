"""Drive an HTTP response in-process, including completion of its ASGI call."""
import asyncio


def http_scope(*, headers=(), version="2.4"):
    return {
        "type": "http",
        "asgi": {"spec_version": version},
        "method": "GET",
        "path": "/file",
        "headers": list(headers),
    }


async def receive():
    # There is no incoming body or disconnect in a completed response.
    await asyncio.Event().wait()


async def response_bytes(response):
    contents = bytearray()

    async def send(message):
        if message["type"] == "http.response.body":
            contents.extend(message.get("body", b""))

    await response(http_scope(), receive, send)
    return bytes(contents)
