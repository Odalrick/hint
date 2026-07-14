# hint 1.1.0 Streaming Render Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a synchronous co-generator render (`render_stream` / `render_html_stream`) that streams HTML and suspends at named `Hole` placeholders for the consumer to fill via `.send()`, leaving the eager `render` / `render_html` API unchanged.

**Architecture:** `render_stream` is a recursive generator over the existing `ElementOrStr` tree, now widened with a fourth member `Hole`. It yields `str` output and yields a `Hole` (then receives a `list[ElementOrStr]` via `.send()`) when it reaches a placeholder; injected content is spliced in through the same walk via `yield from`, so nested holes work for free. `render` becomes a thin eager driver over `render_stream` that raises on any unresolved hole. One render walk serves both paths.

**Tech Stack:** Python 3.14, `uv`, ruff (`select = ["ALL"]`), pyright (strict), import-linter, pytest + hypothesis. Design spec: `docs/superpowers/specs/2026-07-14-hint-streaming-render-design.md`.

## Global Constraints

- Python **3.14** floor. Do **not** use `from __future__ import annotations` (project + user rule).
- `hint/__init__.py` is a **re-export boundary**: it re-exports and defines thin `tag: Node = element("tag")` lines only — no implementation logic. All new implementation lives in `hint/_core.py`.
- No new runtime dependencies. The import-linter pure-core contract must stay green.
- Calling convention is fixed: `tag([children], {attrs})`; **no** keyword args or defaults. `hole(name)` is a plain constructor like `style()`, not an HTML tag.
- Escaping is never bypassed: text children and attribute names/values go through `html.escape`; `RawHtml` is the only pass-through.
- Booleans are only for `if` — never store one in a model or pass one across a function boundary. (No `HAS_*` flags.)
- Every file ends with a newline. Conventional commits; scopes here: `core`, `render`, `docs`.
- Run `make check` (ruff + pyright + import-linter + pytest) and see it green **before every commit**.

---

### Task 1: `Hole` placeholder type and `hole()` constructor

**Files:**
- Modify: `src/hint/_core.py` (add `Hole`, `hole`, widen `ElementOrStr`)
- Modify: `src/hint/__init__.py` (re-export `Hole`, `hole`)
- Test: `src/hint/stream_test.py` (create)

**Interfaces:**
- Consumes: `ElementOrStr` from `hint._core`.
- Produces:
  - `class Hole` — frozen-shaped dataclass with a single field `name: str`.
  - `def hole(name: str) -> Hole` — constructor returning `Hole(name=name)`.
  - `ElementOrStr = Element | str | RawHtml | Hole`.
  - Re-exported from the boundary as `hint.Hole`, `hint.hole`.

- [ ] **Step 1: Write the failing test**

Create `src/hint/stream_test.py`:

```python
from hint import Hole, hole


def test_hole_constructor_builds_named_hole() -> None:
    assert hole("pr-list") == Hole(name="pr-list")


def test_hole_exposes_its_name() -> None:
    assert hole("rows").name == "rows"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest src/hint/stream_test.py -v`
Expected: FAIL with `ImportError: cannot import name 'Hole' from 'hint'` (or `hole`).

- [ ] **Step 3: Write minimal implementation**

In `src/hint/_core.py`, add the `Hole` dataclass and `hole` constructor near `RawHtml`, and widen the union. Place `Hole` before the `ElementOrStr` alias:

```python
@dataclass
class Hole:
    """A named placeholder that :func:`render_stream` suspends at, to be filled by the consumer."""

    name: str


type ElementOrStr = Element | str | RawHtml | Hole
```

Add the constructor below `style` (or near the other constructors):

```python
def hole(name: str) -> Hole:
    """Return a named :class:`Hole` placeholder for streaming render to suspend at."""
    return Hole(name=name)
```

Note: `Element` is defined after `RawHtml`; keep the existing order (`RawHtml`, then `Element`, then the `type ElementOrStr = ...` line) and just add `Hole` to it. If `Hole` references nothing from `Element`, define `Hole` right after `RawHtml`. The `type` alias line already sits after `Element`, so widen it in place.

In `src/hint/__init__.py`, add `Hole` and `hole` to the `from hint._core import (...)` block (alphabetical, `X as X` form):

```python
    Hole as Hole,
    ...
    hole as hole,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest src/hint/stream_test.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Gate and commit**

Run: `make check`
Expected: all four gates pass.

```bash
git add src/hint/_core.py src/hint/__init__.py src/hint/stream_test.py
git commit -m "feat(core): add Hole placeholder and hole() constructor"
```

---

### Task 2: `render_stream` walk and `render` driven through it

**Files:**
- Modify: `src/hint/_core.py` (add `StreamItem`, `render_stream`; refactor `render`)
- Modify: `src/hint/__init__.py` (re-export `render_stream`, `StreamItem`)
- Test: `src/hint/stream_test.py`

**Interfaces:**
- Consumes: `Hole`, `Element`, `RawHtml`, `ElementOrStr`, `_VOID_ELEMENTS`, `escape` from Task 1 / existing `_core`.
- Produces:
  - `type StreamItem = str | Hole`.
  - `def render_stream(node: ElementOrStr) -> Generator[StreamItem, list[ElementOrStr] | None, None]` — yields `str` output; yields a `Hole` at a placeholder. In this task the hole is surfaced only (renders empty; the `.send()` fill lands in Task 3).
  - `render(node) -> str` refactored to drive `render_stream`, raising `ValueError` on any `Hole`.
  - Re-exported as `hint.render_stream`, `hint.StreamItem`.

- [ ] **Step 1: Write the failing tests**

Append to `src/hint/stream_test.py`. First add the imports at the top of the file (merge with the existing Task 1 import line):

```python
from hint import Element, Hole, RawHtml, element, hole, render, render_stream

from hypothesis import given, strategies as st
import pytest
```

Then the tests:

```python
_NON_VOID_NAMES = ["div", "span", "p", "ul", "li", "section"]


def _hole_free_trees() -> st.SearchStrategy[ElementOrStr]:
    leaves = st.one_of(st.text(), st.builds(RawHtml, st.text()))
    return st.recursive(
        leaves,
        lambda children: st.builds(
            lambda name, kids, attrs: Element(
                name=name, content=list(kids), attrs=attrs
            ),
            st.sampled_from(_NON_VOID_NAMES),
            st.lists(children, max_size=3),
            st.dictionaries(st.text(min_size=1), st.text(), max_size=2),
        ),
        max_leaves=15,
    )


@given(_hole_free_trees())
def test_stream_joins_to_the_eager_render(tree: ElementOrStr) -> None:
    streamed = "".join(part for part in render_stream(tree) if isinstance(part, str))
    assert streamed == render(tree)


def test_render_raises_on_an_unresolved_hole() -> None:
    with pytest.raises(ValueError, match="pr-list"):
        render(element("div")([hole("pr-list")], {}))


def test_stream_surfaces_the_hole_as_a_hole_item() -> None:
    items = list(render_stream(element("div")([hole("rows")], {})))
    assert items == ["<div>", Hole(name="rows"), "</div>"]
```

`ElementOrStr` is imported for the strategy annotation — add it to the import line: `from hint import Element, ElementOrStr, Hole, RawHtml, element, hole, render, render_stream`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src/hint/stream_test.py -v`
Expected: FAIL — `render_stream` does not exist (`ImportError`).

- [ ] **Step 3: Write the implementation**

In `src/hint/_core.py`, extend the imports:

```python
from collections.abc import Callable, Generator
```

Add the `StreamItem` alias after the `type ElementOrStr = ...` line:

```python
type StreamItem = str | Hole
```

Replace the existing `render` function with `render_stream` plus a driving `render`:

```python
def render_stream(
    node: ElementOrStr,
) -> Generator[StreamItem, list[ElementOrStr] | None, None]:
    """Stream a description tree as HTML chunks, suspending at each :class:`Hole`.

    Yields ``str`` output; yields a :class:`Hole` when it reaches a placeholder and
    (in the filled form) splices back the ``list[ElementOrStr]`` the consumer sends.
    """
    if isinstance(node, RawHtml):
        yield node.content
        return
    if isinstance(node, Hole):
        yield node
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
        yield from render_stream(child)
    yield f"</{node.name}>"


def render(node: ElementOrStr) -> str:
    """Render a description tree to an HTML string, escaping text and attributes.

    Drives :func:`render_stream` and joins its output. Raises ``ValueError`` if the
    tree contains a :class:`Hole` — an eager render cannot resolve one.
    """
    parts: list[str] = []
    for item in render_stream(node):
        if isinstance(item, Hole):
            message = f"render() cannot resolve hole {item.name!r}; use render_stream"
            raise ValueError(message)
        parts.append(item)
    return "".join(parts)
```

Leave `render_html` as-is (it calls `render`).

In `src/hint/__init__.py`, add to the `_core` import block (alphabetical, `X as X`):

```python
    StreamItem as StreamItem,
    ...
    render_stream as render_stream,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest src/hint/stream_test.py src/hint/render_test.py -v`
Expected: PASS — including the existing `render_test.py` suite unchanged (the refactor is behaviour-preserving for hole-free trees).

- [ ] **Step 5: Gate and commit**

Run: `make check`
Expected: all four gates pass.

```bash
git add src/hint/_core.py src/hint/__init__.py src/hint/stream_test.py
git commit -m "feat(render): add render_stream and drive render through it"
```

---

### Task 3: Fill holes from sent content

**Files:**
- Modify: `src/hint/_core.py` (`render_stream` hole case)
- Test: `src/hint/stream_test.py`

**Interfaces:**
- Consumes: `render_stream` from Task 2.
- Produces: `render_stream`'s hole case now does `filling = yield node; if filling: for child in filling: yield from render_stream(child)`. Fill contract: consumer sends `list[ElementOrStr]` in response to a `Hole`; `[]` (and the protocol's priming/advance `None`) render empty. Signature unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `src/hint/stream_test.py`. Add a small consumer-drive helper (the documented drive loop), then the behaviour tests:

```python
def drive(node: ElementOrStr, fills: dict[str, list[ElementOrStr]]) -> str:
    """Drive render_stream to completion, filling each hole from `fills` by name."""
    generator = render_stream(node)
    parts: list[str] = []
    to_send: list[ElementOrStr] | None = None
    while True:
        try:
            item = generator.send(to_send)
        except StopIteration:
            break
        to_send = None
        if isinstance(item, Hole):
            to_send = fills.get(item.name, [])
        else:
            parts.append(item)
    return "".join(parts)


def test_hole_filled_with_a_single_element() -> None:
    tree = element("main")([hole("body")], {})
    filled = drive(tree, {"body": [element("p")(["hi"], {})]})
    assert filled == "<main><p>hi</p></main>"


def test_hole_filled_with_a_sibling_list_needs_no_wrapper() -> None:
    tree = element("tbody")([hole("rows")], {})
    rows = [element("tr")([element("td")([str(n)], {})], {}) for n in (1, 2)]
    filled = drive(tree, {"rows": rows})
    assert filled == "<tbody><tr><td>1</td></tr><tr><td>2</td></tr></tbody>"


def test_unfilled_hole_renders_empty() -> None:
    tree = element("div")(["a", hole("gap"), "b"], {})
    assert drive(tree, {}) == "<div>ab</div>"


def test_nested_hole_in_sent_content_is_fillable() -> None:
    tree = element("section")([hole("outer")], {})
    fills = {
        "outer": [element("div")([hole("inner")], {})],
        "inner": [element("span")(["deep"], {})],
    }
    assert drive(tree, fills) == "<section><div><span>deep</span></div></section>"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src/hint/stream_test.py -k "filled or nested or unfilled" -v`
Expected: FAIL — the single-element and sibling-list cases render `<main></main>` / `<tbody></tbody>` (hole surfaced but content dropped), so assertions fail.

- [ ] **Step 3: Write the implementation**

In `src/hint/_core.py`, replace the hole case in `render_stream`:

```python
    if isinstance(node, Hole):
        yield node
        return
```

with:

```python
    if isinstance(node, Hole):
        filling = yield node
        if filling:  # None (priming/advance artifact) or [] both render empty
            for child in filling:
                yield from render_stream(child)
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest src/hint/stream_test.py -v`
Expected: PASS — all stream tests, including Task 2's `test_stream_surfaces_the_hole_as_a_hole_item` (an unfilled hole still surfaces the same `Hole` item under `list()`, which never sends).

- [ ] **Step 5: Gate and commit**

Run: `make check`
Expected: all four gates pass.

```bash
git add src/hint/_core.py src/hint/stream_test.py
git commit -m "feat(render): fill holes from sent content in render_stream"
```

---

### Task 4: `render_html_stream` full-document co-generator

**Files:**
- Modify: `src/hint/_core.py` (add `render_html_stream`)
- Modify: `src/hint/__init__.py` (re-export `render_html_stream`)
- Test: `src/hint/stream_test.py`

**Interfaces:**
- Consumes: `render_stream`, `Element`, `Hole`, `StreamItem`, the `drive` helper.
- Produces: `def render_html_stream(root: Element) -> Generator[StreamItem, list[ElementOrStr] | None, None]` — yields exactly one `"<!DOCTYPE html>\n"`, requires an `<html>` root (`ValueError` otherwise), then `yield from render_stream(root)`. Re-exported as `hint.render_html_stream`.

- [ ] **Step 1: Write the failing tests**

Add `render_html_stream` to the import line, then append tests to `src/hint/stream_test.py`:

```python
def test_html_stream_prepends_exactly_one_doctype() -> None:
    items = list(render_html_stream(element("html")([], {})))
    assert items == ["<!DOCTYPE html>\n", "<html>", "</html>"]


def test_html_stream_rejects_a_non_html_root() -> None:
    with pytest.raises(ValueError, match="html"):
        list(render_html_stream(element("div")([], {})))


def test_html_stream_fills_holes_in_the_body() -> None:
    page = element("html")([element("body")([hole("main")], {})], {})
    filled = drive_html(page, {"main": [element("h1")(["Home"], {})]})
    assert filled == "<!DOCTYPE html>\n<html><body><h1>Home</h1></body></html>"
```

Add a `drive_html` helper mirroring `drive` but over `render_html_stream` (kept separate rather than parameterised — the two entry points are the documented public surface):

```python
def drive_html(root: Element, fills: dict[str, list[ElementOrStr]]) -> str:
    """Drive render_html_stream to completion, filling each hole from `fills` by name."""
    generator = render_html_stream(root)
    parts: list[str] = []
    to_send: list[ElementOrStr] | None = None
    while True:
        try:
            item = generator.send(to_send)
        except StopIteration:
            break
        to_send = None
        if isinstance(item, Hole):
            to_send = fills.get(item.name, [])
        else:
            parts.append(item)
    return "".join(parts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src/hint/stream_test.py -k html -v`
Expected: FAIL — `render_html_stream` does not exist (`ImportError`).

- [ ] **Step 3: Write the implementation**

In `src/hint/_core.py`, add after `render_html`:

```python
def render_html_stream(
    root: Element,
) -> Generator[StreamItem, list[ElementOrStr] | None, None]:
    """Stream a full ``<html>`` document, doctype first, suspending at each :class:`Hole`."""
    if root.name != "html":
        message = "render_html_stream requires an <html> root element"
        raise ValueError(message)
    yield "<!DOCTYPE html>\n"
    yield from render_stream(root)
```

In `src/hint/__init__.py`, add to the `_core` import block:

```python
    render_html_stream as render_html_stream,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest src/hint/stream_test.py -v`
Expected: PASS.

- [ ] **Step 5: Gate and commit**

Run: `make check`
Expected: all four gates pass.

```bash
git add src/hint/_core.py src/hint/__init__.py src/hint/stream_test.py
git commit -m "feat(render): add render_html_stream"
```

---

### Task 5: Documentation — README streaming section and BACKLOG update

**Files:**
- Modify: `README.md` (add a "Streaming" section under "Rendering")
- Modify: `BACKLOG.md` (replace "Streaming responses" with an async-driver follow-up)

**Interfaces:**
- Consumes: the public API shipped in Tasks 1–4.
- Produces: no code; documentation only.

- [ ] **Step 1: Add the README streaming section**

In `README.md`, after the `### Rendering` bullets (the `render` / `render_html` list, around line 114) and before `### Escaping and RawHtml`, insert:

````markdown
### Streaming

For pages whose content is expensive to produce (slow API calls, large lists), render
incrementally instead of building the whole string first. `render_stream` and
`render_html_stream` are synchronous **co-generators**: they yield HTML chunks as `str`,
and yield a `hint.Hole` when they reach a named placeholder. The consumer sends back a
`list[Element | str | RawHtml]` for that hole, which is spliced in — nested holes and all.

```python
page = hint.tbody([hint.hole("rows")], {})
```

Drive it with a loop that fills each hole by name (`[]` leaves a hole empty):

```python
generator = hint.render_stream(page)
to_send = None
while True:
    try:
        item = generator.send(to_send)   # first call primes with None
    except StopIteration:
        break
    to_send = None
    if isinstance(item, hint.Hole):
        to_send = build_rows(item.name)  # a list of <tr> elements
    else:
        emit(item)                       # a str chunk — write it to the socket
```

`hint` stays synchronous. Because the loop is yours, an async consumer (FastAPI
`StreamingResponse`) is free to `await` slow work between a hole and its `send`. The eager
`render` / `render_html` are unchanged; calling `render` on a tree that contains a hole
raises `ValueError`, since an eager render cannot fill it.

`render_html_stream(root)` is the full-document form — it emits `<!DOCTYPE html>` first and
requires an `<html>` root, otherwise identical.

> The high-value pattern — dispatching every hole's fetch up front so they run in parallel,
> then awaiting each as the walk reaches it — is left to the consumer for now; a helper for it
> is planned (see `BACKLOG.md`).
````

- [ ] **Step 2: Update BACKLOG.md**

In `BACKLOG.md`, replace the entire `## Streaming responses (1.1.0)` section (lines 6–11) with:

```markdown
## Async streaming driver

`render_stream` / `render_html_stream` (shipped in 1.1.0) are synchronous co-generators; the
consumer drives them and fills holes. The high-value consumer pattern dispatches every hole's
fetch up front as parallel tasks (total latency `max`, not `sum`), then awaits each task as the
walk reaches it, emitting in document order. Add an async helper that encapsulates this drive
loop given a `name -> awaitable` mapping — possibly alongside a `holes(node)` enumerator so the
set of names can be discovered from a tree. Consumer-side and general; kept out of the sync core.
```

- [ ] **Step 3: Verify docs render and nothing else regressed**

Run: `make check`
Expected: all gates pass (docs changes don't affect them, but confirm the tree is still green).

- [ ] **Step 4: Commit**

```bash
git add README.md BACKLOG.md
git commit -m "docs: document streaming render; retarget backlog to async driver"
```

---

## Self-Review

**Spec coverage:**
- `Hole` type + `hole` constructor + `ElementOrStr` widening → Task 1. ✓
- `render_stream` co-generator, yield channel `str | Hole`, `render` as eager driver raising on holes → Task 2. ✓
- Send channel `list[ElementOrStr]`, homogeneous list fill, empty-on-unfilled, nested holes → Task 3. ✓
- `render_html_stream` (doctype first, `<html>`-root check) → Task 4. ✓
- Module placement in `_core.py`, four re-exports (`Hole`, `hole`, `render_stream`, `render_html_stream`) plus `StreamItem` → Tasks 1, 2, 4. ✓
- Granularity (per-piece, no coalescing) → falls out of the Task 2 walk; documented in spec, no code needed. ✓
- Equivalence property test, render-raises, hole protocol, list fill, nested, unfilled, `render_html_stream`, full drive loop → Tasks 2–4 tests. ✓
- README streaming section + BACKLOG retarget → Task 5. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; every test step shows full test bodies. ✓

**Type consistency:** `render_stream` / `render_html_stream` return `Generator[StreamItem, list[ElementOrStr] | None, None]` in every task; `StreamItem = str | Hole`; fill lists typed `list[ElementOrStr]`; `drive` / `drive_html` helpers use the same send type. `Hole(name=...)` field name consistent across constructor, tests, and the `.name` reads. ✓

## Notes for the implementer

- The `isinstance` order in `render_stream` matters: check `RawHtml`, `Hole`, `str` (each returning) so pyright narrows the fall-through to `Element` for the attribute/tag block. Do not reorder so that the `Element` block sees a non-`Element`.
- `make check` runs ruff with `select = ["ALL"]`. If a rule genuinely conflicts at a site, use a per-site `# noqa: RULE` with intent — not a global ignore. None is anticipated for this change.
- Existing `render_test.py` must pass untouched after Task 2; if any case changes output, the refactor is wrong, not the test.
