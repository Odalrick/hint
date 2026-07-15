import asyncio
from collections.abc import Awaitable

import pytest

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


def test_empty_list_fill_renders_empty() -> None:
    async def fill() -> list[ElementOrStr]:
        return []

    tree = element("div")(["a", hole("gap"), "b"], {})
    assert collect(tree, {"gap": fill()}) == "<div>ab</div>"


def test_list_fill_splices_siblings_without_a_wrapper() -> None:
    async def rows() -> list[ElementOrStr]:
        return [element("tr")([element("td")([str(n)], {})], {}) for n in (1, 2)]

    tree = element("tbody")([hole("rows")], {})
    expected = "<tbody><tr><td>1</td></tr><tr><td>2</td></tr></tbody>"
    assert collect(tree, {"rows": rows()}) == expected


def test_fill_content_is_escaped() -> None:
    async def fill() -> list[ElementOrStr]:
        return ["<script>"]

    tree = element("div")([hole("x")], {})
    assert collect(tree, {"x": fill()}) == "<div>&lt;script&gt;</div>"


def test_hole_with_no_fill_raises_naming_the_hole() -> None:
    async def scenario() -> list[str]:
        tree = element("div")([hole("orphan")], {})
        return [c async for c in render_stream_async(tree, {})]

    with pytest.raises(ValueError, match="orphan"):
        asyncio.run(scenario())


def test_static_nested_hole_in_fills_is_resolved() -> None:
    async def outer() -> list[ElementOrStr]:
        return [element("div")([hole("inner")], {})]

    async def inner() -> list[ElementOrStr]:
        return [element("span")(["deep"], {})]

    tree = element("section")([hole("outer")], {})
    fills: dict[str, Awaitable[list[ElementOrStr]]] = {
        "outer": outer(),
        "inner": inner(),
    }
    expected = "<section><div><span>deep</span></div></section>"
    assert collect(tree, fills) == expected


def test_dynamic_hole_added_by_a_completing_fill_is_resolved() -> None:
    async def scenario() -> str:
        fills: dict[str, Awaitable[list[ElementOrStr]]] = {}

        async def inner() -> list[ElementOrStr]:
            return ["deep"]

        async def outer() -> list[ElementOrStr]:
            fills["inner"] = inner()  # invent a new hole + register its fetch
            return [element("div")([hole("inner")], {})]

        fills["outer"] = outer()
        tree = element("section")([hole("outer")], {})
        return "".join([c async for c in render_stream_async(tree, fills)])

    assert asyncio.run(scenario()) == "<section><div>deep</div></section>"


def test_failing_fill_propagates_and_cancels_siblings() -> None:
    cancelled = asyncio.Event()

    async def scenario() -> None:
        async def boom() -> list[ElementOrStr]:
            message = "nope"
            raise RuntimeError(message)

        async def slow() -> list[ElementOrStr]:
            try:
                await asyncio.Event().wait()  # never completes on its own
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return []  # pragma: no cover

        tree = element("div")([hole("boom"), hole("slow")], {})
        fills = {"boom": boom(), "slow": slow()}
        async for _ in render_stream_async(tree, fills):
            pass

    with pytest.raises(RuntimeError, match="nope"):
        asyncio.run(scenario())
    assert cancelled.is_set()


def test_early_break_cancels_outstanding_tasks() -> None:
    cancelled = asyncio.Event()

    async def scenario() -> None:
        async def slow() -> list[ElementOrStr]:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return []  # pragma: no cover

        # "slow" is dispatched up front; we break before the walk reaches its hole.
        tree = element("div")(["x", hole("slow")], {})
        async for chunk in render_stream_async(tree, {"slow": slow()}):
            if chunk == "<div>":
                break  # exiting the async-for calls aclose() → _drive.finally runs

    asyncio.run(scenario())
    assert cancelled.is_set()
