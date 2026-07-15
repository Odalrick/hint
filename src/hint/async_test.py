import asyncio
from collections.abc import Awaitable

from hint import (
    ElementOrStr,
    element,
    hole,
    render_stream_async,
)


def collect(node: ElementOrStr, fills: dict[str, Awaitable[list[ElementOrStr]]]) -> str:
    """Drive render_stream_async to completion and join its chunks."""

    async def drain() -> str:
        return "".join([chunk async for chunk in render_stream_async(node, fills)])

    return asyncio.run(drain())


def test_single_hole_is_filled() -> None:
    async def fill() -> list[ElementOrStr]:
        return [element("p")(["hi"], {})]

    tree = element("main")([hole("body")], {})
    assert collect(tree, {"body": fill()}) == "<main><p>hi</p></main>"
