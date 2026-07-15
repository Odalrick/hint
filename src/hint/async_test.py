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


def test_holes_dispatch_in_parallel_and_emit_in_document_order() -> None:
    async def scenario() -> str:
        a_started = asyncio.Event()
        b_started = asyncio.Event()

        async def fill_a() -> list[ElementOrStr]:
            a_started.set()
            # a cannot finish until b has started → proves parallel
            await b_started.wait()
            return ["A"]

        async def fill_b() -> list[ElementOrStr]:
            b_started.set()
            return ["B"]

        tree = element("div")([hole("a"), hole("b")], {})
        fills = {"a": fill_a(), "b": fill_b()}
        # If dispatch were lazy (per-hole), fill_a would await b_started before fill_b
        # ever starts → deadlock; the timeout turns that failure mode into a clear fail.
        async with asyncio.timeout(1):
            return "".join([c async for c in render_stream_async(tree, fills)])

    assert asyncio.run(scenario()) == "<div>AB</div>"


def test_repeated_hole_name_resolves_once_with_identical_data() -> None:
    calls = 0

    async def fill() -> list[ElementOrStr]:
        nonlocal calls
        calls += 1
        return ["X"]

    async def scenario() -> str:
        tree = element("div")([hole("a"), hole("a")], {})
        return "".join([c async for c in render_stream_async(tree, {"a": fill()})])

    assert asyncio.run(scenario()) == "<div>XX</div>"
    assert calls == 1
