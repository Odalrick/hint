# PR B — streaming granularity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the streaming contract so each yield is the full HTML run up to the next hole, not one fine-grained fragment — `StreamItem = tuple[str, Hole | None]`, via a `_walk` (recursive, fine-grained) + `render_stream` (flat coalescing wrapper) split. This also removes the `None`-advance artifact from the send channel.

**Architecture:** The current recursive `render_stream` body becomes an internal `_walk` (yields `str | Hole`, unchanged logic). A new flat `render_stream` consumes `_walk`, buffering `str` fragments and yielding `("".join(buffer), hole)` at each hole (and `(run, None)` at the end), forwarding the consumer's fill inward. Coalescing then lives in exactly one place: `render` and the async `_drive` both adapt to consume tuples, and `_drive` stops doing any buffering of its own.

**Tech Stack:** Python 3.14, ruff (`select = ["ALL"]`), pyright strict, import-linter, pytest + hypothesis.

**Spec:** `docs/superpowers/specs/2026-07-16-render-contract-redesign-design.md` (this is PR B of two; PR A — the `document` node + API consolidation — is already merged to `main`).

## Global Constraints

- Python **3.14**; no `from __future__ import annotations`. No new dependencies. Files end with a newline.
- Positional-only calling convention; do not add keyword args/defaults.
- Internal modules (`_core`, `_helper`, `_async`, `_markdown`) import from `hint._core`, never the `hint` boundary.
- **Breaking change** to the (unreleased) streaming contract. The PR title (squash-merge subject) must carry a conventional-commit breaking marker (`fix(render)!:` or `feat(render)!:` with a `BREAKING CHANGE:` footer) so release-please classifies it. (It is a bugfix — the granularity was wrong — but it is breaking; use `fix(render)!:`.)
- The coalescing rule is fixed: `render_stream` coalesces to **hole boundaries** (one `(run, hole)` per run up to a hole, plus a final `(run, None)`). No configurable chunk sizing.
- Tests colocated as `src/hint/<name>_test.py`. Run `make check` before the final commit.
- British English in prose/docs.

## File structure

- `src/hint/_core.py` — `type StreamItem` becomes `tuple[str, Hole | None]`; the current `render_stream` body is renamed to `_walk` (recursive calls updated to `_walk`); a new flat coalescing `render_stream` wraps `_walk`.
- `src/hint/_helper.py` — `render` adapts to unpack `(run, hole)`; drops its now-unused `Hole` import.
- `src/hint/_async.py` — `_drive` adapts to unpack `(run, hole)` and stops buffering; drops its now-unused `Hole` import.
- `src/hint/stream_test.py` — `drive` helper rewritten; four protocol-level assertions updated to tuples; two new coalescing tests added.
- `src/hint/async_test.py` — the early-break test's chunk-boundary condition updated (now-coalesced first chunk).
- `README.md` — streaming section's protocol description + drive-loop example updated to the `(run, hole)` contract.

`render_test.py` uses only `render` (output unchanged) — it needs no edits; the final gate confirms it still passes.

---

### Task 1: Reshape the streaming contract to `(run, hole)` tuples

**Files:**
- Modify: `src/hint/_core.py`, `src/hint/_helper.py`, `src/hint/_async.py`
- Modify: `src/hint/stream_test.py`, `src/hint/async_test.py`

**Interfaces:**
- Consumes: current `render_stream(node) -> Generator[str | Hole, list[ElementOrStr] | None]`, `render`, `_drive`.
- Produces: `type StreamItem = tuple[str, Hole | None]`; internal `_walk(node) -> Generator[str | Hole, list[ElementOrStr] | None]`; `render_stream(node) -> Generator[StreamItem, list[ElementOrStr] | None]` yielding `(run, hole)`; `render` and `_drive` consuming tuples. Drive-loop shape: `run, hole = gen.send(to_send)`; emit `run`; `if hole is not None:` send its fill.

This is a single atomic change: the moment `render_stream` yields tuples, `render` and `_drive` must change with it, so it is one green commit. Write the new tests first, then make everything green together.

- [ ] **Step 1: Write the new failing tests (pin the tuple contract + coalescing)**

Add to `src/hint/stream_test.py` (it already imports `Hole`, `Renderable`, `element`, `hole`, `render_stream`):

```python
def test_render_stream_pairs_each_run_with_its_hole() -> None:
    tree = element("div")(["a", hole("x"), "b"], {})
    assert list(render_stream(tree)) == [("<div>a", Hole(name="x")), ("b</div>", None)]


def test_render_stream_coalesces_a_hole_free_tree_to_one_tuple() -> None:
    tree = element("div")(["a", element("span")(["b"], {}), "c"], {})
    assert list(render_stream(tree)) == [("<div>a<span>b</span>c</div>", None)]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest src/hint/stream_test.py -k "pairs_each_run or coalesces_a_hole_free" -v`
Expected: FAIL — current `render_stream` yields bare `str`/`Hole`, so the lists won't equal the tuple lists.

- [ ] **Step 3: `_core.py` — rename body to `_walk`, redefine `StreamItem`, add the wrapper**

Change the `StreamItem` alias:

```python
type StreamItem = tuple[str, Hole | None]
```

Rename the current `render_stream` function to `_walk`, updating **every internal recursive call** from `render_stream(...)` to `_walk(...)` and its return annotation to `str | Hole`. The full result:

```python
def _walk(
    node: Renderable,
) -> Generator[str | Hole, list[ElementOrStr] | None]:
    """Recursively stream a tree as fine-grained ``str`` / ``Hole`` items.

    Internal to the streaming layer: :func:`render_stream` coalesces these into
    ``(run, hole)`` tuples. Yields a :class:`Hole` at each placeholder and splices
    back the ``list[ElementOrStr]`` the consumer sends.
    """
    if isinstance(node, Document):
        yield "<!DOCTYPE html>\n"
        yield from _walk(node.child)
        return
    if isinstance(node, RawHtml):
        yield node.content
        return
    if isinstance(node, Hole):
        filling = yield node
        if filling:  # None (priming/advance artifact) or [] both render empty
            for child in filling:
                yield from _walk(child)
        return
    if isinstance(node, str):
        yield escape(node)
        return
    attributes = "".join(
        f' {escape(name, quote=True)}="{escape(value, quote=True)}"'
        for name, value in node.attrs.items()
    )
    if node.name in _VOID_ELEMENTS:
        yield f"<{node.name}{attributes}/>"
        return
    yield f"<{node.name}{attributes}>"
    for child in node.content:
        yield from _walk(child)
    yield f"</{node.name}>"
```

Add the new flat coalescing wrapper immediately after `_walk`:

```python
def render_stream(
    node: Renderable,
) -> Generator[StreamItem, list[ElementOrStr] | None]:
    """Stream a tree as ``(run, hole)`` tuples.

    Each item is the coalesced HTML run up to the next placeholder, paired with that
    :class:`Hole` — or ``(run, None)`` for the final run. The consumer emits ``run``
    and, when ``hole`` is not ``None``, sends back the ``list[ElementOrStr]`` fill
    (spliced through the same walk, nested holes and all).
    """
    walk = _walk(node)
    buffer: list[str] = []
    to_inner: list[ElementOrStr] | None = None
    while True:
        try:
            item = walk.send(to_inner)
        except StopIteration:
            break
        to_inner = None
        if isinstance(item, Hole):
            fill = yield ("".join(buffer), item)
            buffer.clear()
            to_inner = fill
        else:
            buffer.append(item)
    if buffer:
        yield ("".join(buffer), None)
```

- [ ] **Step 4: `_helper.py` — adapt `render` to unpack tuples**

Replace the `render` body's loop, and drop the now-unused `Hole` import (change `from hint._core import Hole, Renderable, render_stream` to `from hint._core import Renderable, render_stream`):

```python
def render(node: Renderable) -> str:
    """Render a description tree to an HTML string, escaping text and attributes.

    Drives :func:`render_stream` and joins its output. Raises ``ValueError`` if the
    tree contains a :class:`Hole` — an eager render cannot resolve one.
    """
    parts: list[str] = []
    for run, hole in render_stream(node):
        parts.append(run)
        if hole is not None:
            message = f"render() cannot resolve hole {hole.name!r}; use render_stream"
            # A Hole here is a valid, well-typed value that render() cannot resolve —
            # not a type-safety violation, so ValueError (not TypeError) is correct.
            raise ValueError(message)  # noqa: TRY004
    return "".join(parts)
```

- [ ] **Step 5: `_async.py` — adapt `_drive` (stop buffering) and drop the `Hole` import**

In `_async.py`, remove `Hole` from the `from hint._core import (...)` block (it is no longer referenced — `StreamItem` stays, `_resolve` takes a `str` name). Replace the `_drive` loop body:

```python
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
                run, hole = generator.send(to_send)
            except StopIteration:
                break
            if run:
                yield run
            to_send = None
            if hole is not None:
                to_send = await _resolve(hole.name, fills, tasks, results)
    finally:
        for task in tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
```

- [ ] **Step 6: Update the broken protocol-level tests in `stream_test.py`**

1. `test_stream_joins_to_the_eager_render` — replace its body line:

```python
    streamed = "".join(run for run, _hole in render_stream(tree))
```

2. `test_stream_surfaces_the_hole_as_a_hole_item` — rename to `test_stream_pairs_a_run_with_its_hole` and update the assertion:

```python
def test_stream_pairs_a_run_with_its_hole() -> None:
    items = list(render_stream(element("div")([hole("rows")], {})))
    assert items == [("<div>", Hole(name="rows")), ("</div>", None)]
```

3. The `drive` helper — rewrite to unpack tuples:

```python
def drive(node: Renderable, fills: dict[str, list[ElementOrStr]]) -> str:
    """Drive render_stream to completion, filling each hole from `fills` by name."""
    generator = render_stream(node)
    parts: list[str] = []
    to_send: list[ElementOrStr] | None = None
    while True:
        try:
            run, hole = generator.send(to_send)
        except StopIteration:
            break
        parts.append(run)
        to_send = None
        if hole is not None:
            to_send = fills.get(hole.name, [])
    return "".join(parts)
```

4. `test_stream_self_closes_a_void_element_with_escaped_attrs` — update the assertion:

```python
    assert items == [('<img src="/a&lt;b&gt;"/>', None)]
```

5. `test_document_streams_doctype_then_child` — the doctype + tags now coalesce into one tuple:

```python
    assert items == [("<!DOCTYPE html>\n<html></html>", None)]
```

(All other `stream_test.py` tests drive through the `drive` helper and assert the *joined* string, which is unchanged — leave them.)

- [ ] **Step 7: Update the chunk-boundary test in `async_test.py`**

In `test_early_break_cancels_outstanding_tasks`, the first emitted chunk is now the coalesced run `"<div>x"` (the walk buffers `"<div>"` and `"x"` before the `slow` hole). Update the break condition and its comment:

```python
        async with aclosing(render_stream_async(tree, {"slow": slow()})) as chunks:
            async for chunk in chunks:
                if chunk == "<div>x":
                    # render_stream coalesces "<div>" + "x" into one run before the
                    # "slow" hole, so this is the first (and only) chunk emitted before
                    # the driver would await slow. Yield once so slow actually starts,
                    # then break to trigger aclose()/cancellation.
                    await asyncio.sleep(0)
                    break
        assert cancelled.is_set()
```

(The other `async_test.py` tests join via `collect` or iterate-and-pass, so they are invariant under coalescing.)

- [ ] **Step 8: Run the new tests, then the full suite**

Run: `uv run pytest src/hint/stream_test.py -k "pairs or coalesces_a_hole_free" -v` — expect PASS.
Run: `uv run pytest src/hint -q` — expect ALL green (every suite: core render output unchanged, stream tuples correct, async coalesced). Run `uv run pytest src/hint -q -W error::RuntimeWarning` too, to confirm the early-break/cancellation tests emit no warnings.

- [ ] **Step 9: Lint/type/imports and commit**

Run: `uv run ruff check src/hint && uv run ruff format --check src/hint && uv run pyright src/hint && uv run lint-imports`
Expected: clean (ruff `F401` catches the dropped `Hole` imports if any reference was missed; pyright confirms the tuple unpacking types; import-linter 3/3).

```bash
git add src/hint/_core.py src/hint/_helper.py src/hint/_async.py src/hint/stream_test.py src/hint/async_test.py
git commit -m "fix(render)!: coalesce render_stream to (run, hole) tuples"
```

---

### Task 2: Docs and full gate

**Files:**
- Modify: `README.md`

**Interfaces:** none (documentation + final verification).

- [ ] **Step 1: Update the README streaming section**

In `README.md`'s `### Streaming` section:

Replace the protocol description paragraph — currently: "`render_stream` is a synchronous **co-generator**: it yields HTML chunks as `str`, and yields a `hint.Hole` when it reaches a named placeholder. The consumer sends back a `list[ElementOrStr]` …" — with a description of the tuple contract:

```markdown
For pages whose content is expensive to produce (slow API calls, large lists), render
incrementally instead of building the whole string first. `render_stream` is a synchronous
**co-generator**: each item is a `(run, hole)` tuple — the coalesced HTML run (a `str`) up to the
next named placeholder, paired with that `hint.Hole` (or `None` for the final run). The consumer
emits `run`, then, for a non-`None` hole, sends back a `list[ElementOrStr]` fill (which may itself
contain unfilled holes, spliced in — nested holes and all).
```

Replace the drive-loop code block with the tuple form:

```python
generator = hint.render_stream(page)
to_send = None
while True:
    try:
        run, hole = generator.send(to_send)   # first call primes with None
    except StopIteration:
        break
    emit(run)                            # the coalesced str run — write it to the socket
    to_send = None
    if hole is not None:
        to_send = build_rows(hole.name)  # a list of <tr> elements ([] leaves it empty)
```

(Leave the surrounding prose about `hint` staying synchronous, `document(...)`, and the async-driver subsection as-is — the async section already describes yielding `str` chunks in document order, which remains accurate now that each chunk is a coalesced run.)

- [ ] **Step 2: Full gate**

Run: `make check`
Expected: PASS — ruff (lint + format), pyright (strict), import-linter (3 contracts), pytest (all suites). Fix any doc-caused lint inline.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(render): document the (run, hole) streaming contract"
```

---

## Self-Review

**Spec coverage (PR B portion of the spec):**
- `StreamItem = tuple[str, Hole | None]` → Task 1 Step 3. ✓
- Two-layer `_walk` + coalescing `render_stream` wrapper → Task 1 Step 3. ✓
- `render` adapts (plain for-loop, raise on non-None hole) → Task 1 Step 4. ✓
- `_drive` stops buffering, unpacks tuples → Task 1 Step 5. ✓
- `None`-advance artifact gone (consumer only ever sends a fill for a real hole) → the new drive loops (Steps 5, 6, README). ✓
- Ripples: `stream_test` protocol assertions + `drive` helper → Task 1 Step 6; `async_test` early-break → Step 7; README → Task 2. ✓
- `render` output unchanged (render_test stands) → Global Constraints + Step 8 full suite. ✓
- Breaking marker for release-please → Global Constraints + Task 1 commit `!`. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `_walk(node: Renderable) -> Generator[str | Hole, list[ElementOrStr] | None]`; `render_stream(node: Renderable) -> Generator[StreamItem, list[ElementOrStr] | None]` with `StreamItem = tuple[str, Hole | None]`; consumers unpack `run, hole = ...gen.send(...)`; `render` and `_drive` both use `if hole is not None`. Consistent across all tasks. ✓
