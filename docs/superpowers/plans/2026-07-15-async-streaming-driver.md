# Async streaming driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `render_stream_async` / `render_html_stream_async` — an async consumer-side driver that dispatches every known hole's awaitable up front (parallel, `max`-latency), drives the sync `render_stream` co-generator, and emits `str` chunks in document order.

**Architecture:** A new internal module `hint/_async.py` holds one shared async generator `_drive(sync_generator, fills)` plus two thin public entry points that hand it `render_stream(node)` or `render_html_stream(root)`. Two dicts do the work: `tasks` (in-flight `ensure_future` dispatches — the parallelism) and `results` (the value cache — the caching guarantee). A `finally` cancels and awaits outstanding tasks. asyncio only; the pure sync core is untouched.

**Tech Stack:** Python 3.14, stdlib `asyncio`, pytest + hypothesis (tests use `asyncio.run`, no `pytest-asyncio`), ruff (`select = ["ALL"]`), pyright strict, import-linter.

## Global Constraints

- Python **3.14** floor. No `from __future__ import annotations`.
- **No new runtime or test dependencies.** stdlib `asyncio` only; tests drive via `asyncio.run`.
- Internal module `hint/_async.py` imports `hint._core` **only** (never the `hint` boundary). It is re-exported *from* the boundary; nothing outside the package imports it directly.
- The pure core (`hint/_core.py`) stays **sync** — it gains no `asyncio` import (guarded in Task 10).
- Calling convention is positional-only: `element("div")([children], {attrs})`; void as attrs-only. No keyword args / defaults added.
- Test files are `src/hint/<name>_test.py` (no leading underscore — matches `stream_test.py`), colocated, `testpaths = ["src"]`.
- Conventional commits. Scope for this work: `render`. Additive public surface → this ships as a **minor** (`feat(render): …`); release-please computes the version — no manual version edit.
- Run `make check` (ruff + pyright + import-linter + pytest) before the final commit; do not let CI catch lint.
- British English in prose/docs.
- Files end with a newline.

**The full target `hint/_async.py`** (tasks build up to exactly this; shown once here so every task knows the final shape — do not paste it wholesale, build it test-by-test):

```python
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
    """Async-drive :func:`render_html_stream`: doctype first, else as
    :func:`render_stream_async`."""
    return _drive(render_html_stream(root), fills)
```

Note the two public functions are **plain `def`** returning the `_drive(...)` async generator directly (not `async def` wrappers). This avoids a second async-generator layer, so `aclose()`/`break` propagates straight into `_drive`'s `finally`. The `<html>`-root `ValueError` from `render_html_stream` surfaces on the first `async for` step (the sync generator raises when `_drive` first advances it).

---

### Task 1: Module scaffold + single-hole happy path

**Files:**
- Create: `src/hint/_async.py`
- Create: `src/hint/async_test.py`
- Modify: `src/hint/__init__.py:16-32` (add two re-exports)

**Interfaces:**
- Consumes: `hint._core.render_stream`, `render_html_stream`, `Element`, `ElementOrStr`, `Hole`, `StreamItem`.
- Produces: `render_stream_async(node: ElementOrStr, fills: Mapping[str, Awaitable[list[ElementOrStr]]]) -> AsyncGenerator[str]`; `render_html_stream_async(root: Element, fills) -> AsyncGenerator[str]`; internal `_drive`, `_resolve`, and the `Fills` type alias. All later tasks rely on these names/signatures.

- [ ] **Step 1: Write the failing test**

In `src/hint/async_test.py`:

```python
import asyncio
from collections.abc import Awaitable

import pytest

from hint import (
    Element,
    ElementOrStr,
    element,
    hole,
    render_html_stream_async,
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest src/hint/async_test.py -v`
Expected: FAIL — `ImportError: cannot import name 'render_stream_async' from 'hint'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/hint/_async.py` with the **full module contents** shown in Global Constraints above (it is the minimal correct implementation — the `finally`/cancellation is load-bearing for later tasks and harmless here).

Then add to `src/hint/__init__.py`, inside the `from hint._core import (...)` block is **wrong** — these live in `_async`. Add a new import block immediately after the `from hint._core import (...)` block (before the `from hint._markdown import markdown` line):

```python
from hint._async import (
    render_html_stream_async as render_html_stream_async,
    render_stream_async as render_stream_async,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest src/hint/async_test.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hint/_async.py src/hint/async_test.py src/hint/__init__.py
git commit -m "feat(render): async streaming driver — single-hole happy path"
```

---

### Task 2: Parallel dispatch + document order

**Files:**
- Modify: `src/hint/async_test.py` (add test)

**Interfaces:**
- Consumes: `render_stream_async` from Task 1. No production changes — this proves Task 1's up-front dispatch and ordering.

- [ ] **Step 1: Write the failing test**

Add to `src/hint/async_test.py`:

```python
def test_holes_dispatch_in_parallel_and_emit_in_document_order() -> None:
    async def scenario() -> str:
        a_started = asyncio.Event()
        b_started = asyncio.Event()

        async def fill_a() -> list[ElementOrStr]:
            a_started.set()
            await b_started.wait()  # a cannot finish until b has started → proves parallel
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
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `uv run pytest src/hint/async_test.py::test_holes_dispatch_in_parallel_and_emit_in_document_order -v`
Expected: PASS (Task 1 already dispatches up front). If it *hangs to timeout*, dispatch is not up-front — fix `_drive`'s `tasks` comprehension to run before the walk.

- [ ] **Step 3: (no implementation change expected)**

This test guards Task 1's behaviour. If Step 2 passed, proceed.

- [ ] **Step 4: Re-run the full async file**

Run: `uv run pytest src/hint/async_test.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/hint/async_test.py
git commit -m "test(render): async driver dispatches in parallel, emits in order"
```

---

### Task 3: Caching guarantee — equal names, one await, same data

**Files:**
- Modify: `src/hint/async_test.py` (add test)

**Interfaces:**
- Consumes: `render_stream_async`. Guards the `results` value cache in `_resolve`.

- [ ] **Step 1: Write the failing test**

Add to `src/hint/async_test.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest src/hint/async_test.py::test_repeated_hole_name_resolves_once_with_identical_data -v`
Expected: PASS (`results` cache means the second `"a"` never re-awaits). If `calls == 2` or it errors with "cannot reuse already awaited coroutine", the value cache is missing from `_resolve`.

- [ ] **Step 3: (no implementation change expected)**

The `if name in results: return results[name]` branch already provides this.

- [ ] **Step 4: Re-run the full async file**

Run: `uv run pytest src/hint/async_test.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/hint/async_test.py
git commit -m "test(render): async driver caches equal hole names to identical data"
```

---

### Task 4: List fills — empty renders empty, multiple splice without a wrapper

**Files:**
- Modify: `src/hint/async_test.py` (add tests)

**Interfaces:**
- Consumes: `render_stream_async`. Covers the fill-list contract (`[]` → empty; `[a, b]` → siblings), matching the sync path's semantics.

- [ ] **Step 1: Write the failing tests**

Add to `src/hint/async_test.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest src/hint/async_test.py -k "empty_list or splices or escaped" -v`
Expected: PASS (splicing and escaping come from the shared sync walk).

- [ ] **Step 3: (no implementation change expected)**

Behaviour is inherited from `render_stream`.

- [ ] **Step 4: Re-run the full async file**

Run: `uv run pytest src/hint/async_test.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/hint/async_test.py
git commit -m "test(render): async driver honours empty and multi-element fills"
```

---

### Task 5: Missing fill raises (the deliberate divergence from sync)

**Files:**
- Modify: `src/hint/async_test.py` (add test)

**Interfaces:**
- Consumes: `render_stream_async`. Guards the `else: raise ValueError` branch in `_resolve`. Divergence: the sync path renders an unfilled hole empty; the async driver treats a missing fill as caller error.

- [ ] **Step 1: Write the failing test**

Add to `src/hint/async_test.py`:

```python
def test_hole_with_no_fill_raises_naming_the_hole() -> None:
    async def scenario() -> list[str]:
        tree = element("div")([hole("orphan")], {})
        return [c async for c in render_stream_async(tree, {})]

    with pytest.raises(ValueError, match="orphan"):
        asyncio.run(scenario())
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest src/hint/async_test.py::test_hole_with_no_fill_raises_naming_the_hole -v`
Expected: PASS — `_resolve` raises `ValueError` naming `orphan` when the name is absent from both `tasks` and `fills`.

- [ ] **Step 3: (no implementation change expected)**

The `raise ValueError(f"render_stream_async: no fill for hole {name!r}")` branch already covers it.

- [ ] **Step 4: Re-run the full async file**

Run: `uv run pytest src/hint/async_test.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/hint/async_test.py
git commit -m "test(render): async driver raises on a hole with no fill"
```

---

### Task 6: Dynamic holes — a completing fill adds to the live `fills`

**Files:**
- Modify: `src/hint/async_test.py` (add tests)

**Interfaces:**
- Consumes: `render_stream_async`. Guards `_resolve`'s `elif name in fills` (live-read) branch and the nested-hole walk. `fills` is passed as a mutable `dict`; the driver reads it live.

- [ ] **Step 1: Write the failing tests**

Add to `src/hint/async_test.py`:

```python
def test_static_nested_hole_in_fills_is_resolved() -> None:
    async def outer() -> list[ElementOrStr]:
        return [element("div")([hole("inner")], {})]

    async def inner() -> list[ElementOrStr]:
        return [element("span")(["deep"], {})]

    tree = element("section")([hole("outer")], {})
    fills = {"outer": outer(), "inner": inner()}
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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest src/hint/async_test.py -k "nested_hole or dynamic_hole" -v`
Expected: PASS. The static case resolves `inner` from the up-front `tasks`; the dynamic case resolves it via the live-`fills` branch (`ensure_future` on reach).

- [ ] **Step 3: (no implementation change expected)**

Live-read + nested walk already implemented.

- [ ] **Step 4: Re-run the full async file**

Run: `uv run pytest src/hint/async_test.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/hint/async_test.py
git commit -m "test(render): async driver resolves static and dynamic nested holes"
```

---

### Task 7: A failing fill propagates and cancels its siblings

> **Risk task.** This and Task 8 exercise the `finally` cancellation + `await asyncio.gather(..., return_exceptions=True)` hygiene — the spec's named abort trigger. If making cancellation deterministic proves non-obvious (e.g. "Task was destroyed but it is pending" warnings, or the gather deadlocking under `GeneratorExit`), stop, keep the design + this plan, and write a short reflection instead of forcing it.

**Files:**
- Modify: `src/hint/async_test.py` (add test)

**Interfaces:**
- Consumes: `render_stream_async`. Guards `_drive`'s `finally` (cancel not-done tasks, then gather).

- [ ] **Step 1: Write the failing test**

Add to `src/hint/async_test.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest src/hint/async_test.py::test_failing_fill_propagates_and_cancels_siblings -v -W error::RuntimeWarning`
Expected: PASS with no warnings. `boom` (first hole) raises → `_drive` `finally` cancels `slow`'s pending task and `gather` awaits the cancellation (so `cancelled` is set) → `RuntimeError` propagates. `-W error::RuntimeWarning` turns any "coroutine was never awaited" into a failure.

- [ ] **Step 3: (implementation already present; fix only if the test fails)**

If `cancelled` is not set, the `finally` is missing the `await asyncio.gather(*tasks.values(), return_exceptions=True)` after the cancel loop — that await is what lets the cancellation be delivered. If a "Task was destroyed but it is pending" warning appears, same fix.

- [ ] **Step 4: Re-run the full async file**

Run: `uv run pytest src/hint/async_test.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add src/hint/async_test.py
git commit -m "test(render): async driver propagates fill errors and cancels siblings"
```

---

### Task 8: Early stop (`break`/`aclose`) cancels outstanding tasks

**Files:**
- Modify: `src/hint/async_test.py` (add test)

**Interfaces:**
- Consumes: `render_stream_async`. Guards that `finally` runs on consumer `break` (which triggers `aclose()` on the generator).

- [ ] **Step 1: Write the failing test**

Add to `src/hint/async_test.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest src/hint/async_test.py::test_early_break_cancels_outstanding_tasks -v -W error::RuntimeWarning`
Expected: PASS. Breaking the `async for` calls `aclose()`, which throws `GeneratorExit` into `_drive`; the `finally` cancels and gathers the still-pending `slow` task, so `cancelled` is set.

- [ ] **Step 3: (implementation already present; fix only if the test fails)**

Deterministic delivery depends on the `await asyncio.gather(...)` in `finally` (see Task 7). If `cancelled` is not set, aclose returned before cancellation was delivered — the gather is what awaits it.

- [ ] **Step 4: Re-run the full async file**

Run: `uv run pytest src/hint/async_test.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/hint/async_test.py
git commit -m "test(render): async driver cancels outstanding tasks on early stop"
```

---

### Task 9: `render_html_stream_async` — doctype first, non-`<html>` root rejected

**Files:**
- Modify: `src/hint/async_test.py` (add tests)

**Interfaces:**
- Consumes: `render_html_stream_async` (from Task 1). Confirms it reuses the sync `render_html_stream` twin — doctype prefix and root validation for free.

- [ ] **Step 1: Write the failing tests**

Add to `src/hint/async_test.py`:

```python
def collect_html(root: Element, fills: dict[str, Awaitable[list[ElementOrStr]]]) -> str:
    async def drain() -> str:
        return "".join([c async for c in render_html_stream_async(root, fills)])

    return asyncio.run(drain())


def test_html_async_prepends_doctype_and_fills_the_body() -> None:
    async def main() -> list[ElementOrStr]:
        return [element("h1")(["Home"], {})]

    page = element("html")([element("body")([hole("main")], {})], {})
    expected = "<!DOCTYPE html>\n<html><body><h1>Home</h1></body></html>"
    assert collect_html(page, {"main": main()}) == expected


def test_html_async_rejects_a_non_html_root() -> None:
    async def scenario() -> list[str]:
        return [c async for c in render_html_stream_async(element("div")([], {}), {})]

    with pytest.raises(ValueError, match="html"):
        asyncio.run(scenario())
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest src/hint/async_test.py -k "html_async" -v`
Expected: PASS. The doctype and the non-`<html>` `ValueError` come from `render_html_stream`, which `_drive` advances.

- [ ] **Step 3: (no implementation change expected)**

`render_html_stream_async` already delegates to `_drive(render_html_stream(root), fills)`.

- [ ] **Step 4: Re-run the full async file**

Run: `uv run pytest src/hint/async_test.py -v`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add src/hint/async_test.py
git commit -m "test(render): render_html_stream_async doctype and root validation"
```

---

### Task 10: Guards, docs, backlog, and full gate

**Files:**
- Modify: `pyproject.toml:85-96` (add an import-linter contract: core stays sync)
- Modify: `README.md:153-155` (replace the "planned" note with an async subsection)
- Modify: `BACKLOG.md:6-13` (remove the "Async streaming driver" item)
- Modify: `CLAUDE.md` (package-structure section: note `hint/_async.py`)

**Interfaces:**
- Consumes: the finished `hint/_async.py`. Produces the invariant guard, user docs, and backlog/CLAUDE bookkeeping.

- [ ] **Step 1: Add the "core stays sync" import-linter contract**

Append to `pyproject.toml` after the existing `[[tool.importlinter.contracts]]` blocks (after line 104):

```toml
[[tool.importlinter.contracts]]
name = "The pure core stays synchronous (no asyncio)"
type = "forbidden"
source_modules = ["hint._core"]
forbidden_modules = ["asyncio"]
```

- [ ] **Step 2: Verify the guard actually catches a violation**

Temporarily add `import asyncio` to the top of `src/hint/_core.py`, then:

Run: `uv run lint-imports`
Expected: FAIL naming the "The pure core stays synchronous (no asyncio)" contract (`hint._core -> asyncio`).

Then **revert** the temporary edit to `src/hint/_core.py` and re-run:

Run: `uv run lint-imports`
Expected: PASS (all contracts kept).

If the guard does **not** fail in the first run (import-linter not graphing the stdlib import), remove the contract block added in Step 1 and note in the commit body that the sync-core invariant remains convention-enforced (as it was before this work); do not block on it.

- [ ] **Step 3: Replace the README "planned" note with an async subsection**

In `README.md`, replace the blockquote at lines 153-155:

```markdown
> The high-value pattern — dispatching every hole's fetch up front so they run in parallel,
> then awaiting each as the walk reaches it — is left to the consumer for now; a helper for it
> is planned (see `BACKLOG.md`).
```

with:

```markdown
#### Async driver: parallel fetches, document order

`render_stream_async` / `render_html_stream_async` encapsulate the high-value pattern: given a
`name -> awaitable` mapping, they dispatch every known hole's fetch **up front** (so total latency
is `max`, not `sum`), then drive the walk and `await` each hole as it is reached, yielding `str`
chunks in document order. asyncio only.

```python
fills = {
    "header": fetch_header(),   # coroutines; the driver wraps each into a task up front
    "rows": fetch_rows(),
    "footer": fetch_footer(),
}
async for chunk in hint.render_html_stream_async(page, fills):
    await response.write(chunk)
```

Each awaitable resolves to a `list[ElementOrStr]` — the same fill contract as the sync path.
Three guarantees worth knowing:

- **Caching:** equal hole names resolve to the *exact same fill data* (resolved once, cached).
- **Dynamic holes:** `fills` is read live, so a completing fill may invent a new hole and add its
  awaitable to the mapping. The inventor is expected to start that fetch itself — by the time the
  walk reaches a dynamic hole, its siblings are already emitted.
- **Strict fills:** a hole with no entry in `fills` raises `ValueError` (spell "deliberately empty"
  as an awaitable resolving to `[]`). This is stricter than the low-level co-generator, which
  renders an unreached hole empty.

Document order is deliberate: a single HTTP response body is an in-order byte stream in every
version of the protocol, so this maps 1:1 onto the wire with no client-side runtime.
```

(Note: the inner ```` ``` ```` fences above are part of the README content being inserted.)

- [ ] **Step 4: Remove the backlog item**

In `BACKLOG.md`, delete the entire "## Async streaming driver" section (lines 6-13), including its trailing blank line, so the file flows from the intro paragraph straight into "## Content negotiation".

- [ ] **Step 5: Note the module in CLAUDE.md**

In `CLAUDE.md`, in the "Package structure" bullet list (the `hint/_core.py` / `hint/_markdown.py` bullets), add after the `_markdown.py` bullet:

```markdown
- `hint/_async.py` — the optional async driver (`render_stream_async`, `render_html_stream_async`).
  asyncio-only; imports `hint._core`, never the package boundary. Keeps the sync core sync.
```

- [ ] **Step 6: Run the full gate**

Run: `make check`
Expected: PASS — ruff (lint + format), pyright (strict), import-linter (all contracts, including the new one), pytest (all suites incl. the 13 async tests). Fix any ruff/pyright findings inline (e.g. missing docstrings, import sort order) until green.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml README.md BACKLOG.md CLAUDE.md
git commit -m "docs(render): document the async streaming driver; guard the sync core"
```

---

## Self-Review

**Spec coverage:**
- `render_stream_async` / `render_html_stream_async` async generators → Tasks 1, 9. ✓
- `max`-latency up-front dispatch → Task 2. ✓
- Document-order emission → Task 2 (order assertion), Task 9. ✓
- Caching guarantee → Task 3. ✓
- Dynamic holes via live `fills` → Task 6. ✓
- Strict missing-fill `ValueError` divergence → Task 5. ✓
- Fill-list contract (`[]`/multi/escaping) → Task 4. ✓
- Error propagation + cancellation, `aclose`/early stop → Tasks 7, 8. ✓
- `asyncio`-only, no new deps → Global Constraints; tests use `asyncio.run`. ✓
- `_async.py` placement + boundary re-export + import-linter → Tasks 1, 10. ✓
- Sync core stays sync (no asyncio) → Task 10 guard. ✓
- Deferred `holes()` → not built (correct; it is a non-goal). ✓
- README / BACKLOG / CLAUDE updates → Task 10. ✓
- Minor version via release-please → Global Constraints (commit types), no manual edit. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the one deliberate `# pragma: no cover` marks genuinely-unreachable post-cancel returns. ✓

**Type consistency:** `render_stream_async(node, fills)` / `render_html_stream_async(root, fills)`, `_drive(generator, fills)`, `_resolve(name, fills, tasks, results)`, `Fills = Mapping[str, Awaitable[list[ElementOrStr]]]`, `tasks: dict[str, asyncio.Future[list[ElementOrStr]]]`, `results: dict[str, list[ElementOrStr]]` — used identically across all tasks. ✓
