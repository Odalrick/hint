"""Async driver for the sync streaming co-generator.

Internal module. A consumer-side convenience over :func:`hint._core.render_stream`
and :func:`hint._core.render_html_stream`: dispatch every known hole's awaitable up
front as a task (so total latency is ``max`` not ``sum``), then drive the sync walk,
awaiting each hole's result as it is reached and emitting ``str`` chunks in document
order. asyncio only.

Import these names from the package boundary (``hint``), not from here.
"""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Generator, Mapping

from hint._core import (
    Element,
    ElementOrStr,
    Hole,
    StreamItem,
    render_html_stream,
    render_stream,
)

type Fills = Mapping[str, Awaitable[list[ElementOrStr]]]


async def _resolve(
    name: str,
    fills: Fills,
    tasks: dict[str, asyncio.Future[list[ElementOrStr]]],
    results: dict[str, list[ElementOrStr]],
) -> list[ElementOrStr]:
    """Resolve one hole's fill: cache hit, dispatched task, dynamic add, or error."""
    if name in results:
        return results[name]
    if name in tasks:
        task = tasks[name]
    elif name in fills:
        task = tasks[name] = asyncio.ensure_future(fills[name])
    else:
        message = f"render_stream_async: no fill for hole {name!r}"
        raise ValueError(message)
    fill = await task
    results[name] = fill
    return fill


async def _drive(
    generator: Generator[StreamItem, list[ElementOrStr] | None],
    fills: Fills,
) -> AsyncGenerator[str]:
    """Drive a sync stream generator, awaiting holes; emit str in document order."""
    tasks: dict[str, asyncio.Future[list[ElementOrStr]]] = {
        name: asyncio.ensure_future(awaitable) for name, awaitable in fills.items()
    }
    results: dict[str, list[ElementOrStr]] = {}
    to_send: list[ElementOrStr] | None = None
    try:
        while True:
            try:
                item = generator.send(to_send)
            except StopIteration:
                break
            to_send = None
            if isinstance(item, Hole):
                to_send = await _resolve(item.name, fills, tasks, results)
            else:
                yield item
    finally:
        for task in tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)


def render_stream_async(node: ElementOrStr, fills: Fills) -> AsyncGenerator[str]:
    """Async-drive :func:`render_stream`, filling holes from ``fills`` in parallel.

    Dispatches every awaitable in ``fills`` up front, then walks ``node`` emitting
    HTML ``str`` chunks in document order, awaiting each hole's fill as reached. A
    hole with no entry in ``fills`` raises ``ValueError`` (unlike the lenient sync
    path). ``fills`` is read live, so a completing fill may add new (dynamic) holes.
    Equal hole names resolve to the exact same fill data.
    """
    return _drive(render_stream(node), fills)


def render_html_stream_async(root: Element, fills: Fills) -> AsyncGenerator[str]:
    """Async-drive :func:`render_html_stream`.

    Emits the doctype first, then behaves exactly as :func:`render_stream_async`.
    """
    return _drive(render_html_stream(root), fills)
