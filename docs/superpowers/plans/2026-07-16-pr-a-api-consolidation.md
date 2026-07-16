# PR A — API consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `render_html` / `render_html_stream` / `render_html_stream_async` cross-product with a single `document(...)` node handled across all eval modes, and move the eager `render` helper into a new `hint/_helper.py`.

**Architecture:** Doctype becomes a description value: a `Document` node whose walk emits `<!DOCTYPE html>\n` then its single child. Because `Document` stays out of `ElementOrStr` (render entry points take `Renderable = ElementOrStr | Document`), nesting a document is a type error — "doctype only at top" for free. The three `_html` functions are then deleted; `render` moves to `_helper.py` (conveniences over `render_stream`).

**Tech Stack:** Python 3.14, ruff (`select = ["ALL"]`), pyright strict, import-linter, pytest + hypothesis.

**Spec:** `docs/superpowers/specs/2026-07-16-render-contract-redesign-design.md` (this is PR A of two; PR B — the `StreamItem` tuple granularity change — is a separate plan and does NOT belong here).

## Global Constraints

- Python **3.14**; no `from __future__ import annotations`.
- No new dependencies. Files end with a newline.
- Calling convention positional-only: `element("div")([children], {attrs})`; **do not** add keyword args/defaults. `document(child)` takes one positional `Element`.
- Internal modules (`_core`, `_helper`, `_async`, `_markdown`) import from `hint._core`, never the `hint` boundary. The boundary (`hint/__init__.py`) re-exports the public API flat with redundant aliases (`X as X`).
- The yield protocol is **unchanged in this PR**: `render_stream` still yields `StreamItem = str | Hole`. (The tuple change is PR B.)
- `document` performs **no runtime validation** of its child (deferred; the type already prevents nesting).
- Tests colocated as `src/hint/<name>_test.py`. Run `make check` (ruff + pyright + import-linter + pytest) before the final commit.
- **Breaking change:** this PR removes public functions. The PR title (squash-merge subject) must carry a conventional-commit breaking marker (`feat(render)!: …` or a `BREAKING CHANGE:` footer) so release-please classifies it. (Whether the resulting bump is major/2.0.0 vs folding into an unreleased 1.x is a release-time decision for the maintainer via release-please; not a plan concern.)
- British English in prose/docs.

## File structure

- `src/hint/_core.py` — gains `Document` (dataclass), `document()` (constructor), `Renderable` (type alias); `render_stream` gains a `Document` branch and its signature widens to `Renderable`; `render`'s signature widens to `Renderable` (Task 1) then `render` is removed (Task 4); `render_html` and `render_html_stream` are removed (Task 3).
- `src/hint/_helper.py` — **new**; holds `render` (moved) with a "these are just helpers" docblock.
- `src/hint/_async.py` — `render_stream_async` signature widens to `Renderable` (Task 2); `render_html_stream_async` removed (Task 3); imports adjusted.
- `src/hint/__init__.py` — re-export `Document`, `document`, `Renderable`; import `render` from `_helper`; drop the three `_html` re-exports.
- `src/hint/{render,stream,async}_test.py` — add `document` tests; remove obsolete `_html` tests.
- `README.md`, `CLAUDE.md` — docs.

---

### Task 1: The `document` node (add, additive)

**Files:**
- Modify: `src/hint/_core.py`
- Modify: `src/hint/__init__.py`
- Test: `src/hint/render_test.py`, `src/hint/stream_test.py`

**Interfaces:**
- Produces: `Document` (dataclass, field `child: Element`); `document(child: Element) -> Document`; `type Renderable = ElementOrStr | Document`. `render_stream(node: Renderable)` and `render(node: Renderable)` now accept a `Document`. A `Document` walks as `"<!DOCTYPE html>\n"` then its child.

- [ ] **Step 1: Write the failing tests**

In `src/hint/render_test.py`, add `document` to the import from `hint` (line 6 becomes `from hint import RawHtml, document, element, render, render_html, style` — keep alphabetical for ruff isort), and add:

```python
def test_document_renders_doctype_then_child() -> None:
    assert render(document(element("html")([], {}))) == "<!DOCTYPE html>\n<html></html>"
```

In `src/hint/stream_test.py`, add `document` to the `from hint import (...)` block (alphabetical), widen the existing `drive` helper's signature from `node: ElementOrStr` to `node: Renderable` (add `Renderable` to the same import block), and add:

```python
def test_document_streams_doctype_then_child() -> None:
    items = list(render_stream(document(element("html")([], {}))))
    assert items == ["<!DOCTYPE html>\n", "<html>", "</html>"]


def test_document_with_a_hole_in_the_body_is_filled() -> None:
    page = document(element("html")([element("body")([hole("main")], {})], {}))
    filled = drive(page, {"main": [element("h1")(["Home"], {})]})
    assert filled == "<!DOCTYPE html>\n<html><body><h1>Home</h1></body></html>"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest src/hint/render_test.py src/hint/stream_test.py -k document -v`
Expected: FAIL — `ImportError: cannot import name 'document'` (and `Renderable`).

- [ ] **Step 3: Implement in `_core.py`**

Add the `Document` dataclass immediately after the `Element` dataclass (after its definition, before `type Node = ...`):

```python
@dataclass
class Document:
    """A full HTML document: a doctype line followed by a single root child."""

    child: Element
```

Add the `Renderable` alias immediately after the existing `type StreamItem = str | Hole` line:

```python
type Renderable = ElementOrStr | Document
```

Add the `document` constructor immediately after the `style` function:

```python
def document(child: Element) -> Document:
    """Wrap a root element as a full document: a doctype line then the child.

    ``Document`` is intentionally outside ``ElementOrStr``, so a nested
    ``document(...)`` is a type error — a doctype is only valid at the top.
    """
    return Document(child=child)
```

Widen `render_stream`'s signature and add the `Document` branch as the FIRST check in its body:

```python
def render_stream(
    node: Renderable,
) -> Generator[StreamItem, list[ElementOrStr] | None]:
    """Stream a description tree as HTML chunks, suspending at each :class:`Hole`.

    Yields ``str`` output; yields a :class:`Hole` when it reaches a placeholder and
    (in the filled form) splices back the ``list[ElementOrStr]`` the consumer sends.
    """
    if isinstance(node, Document):
        yield "<!DOCTYPE html>\n"
        yield from render_stream(node.child)
        return
    if isinstance(node, RawHtml):
        ...
```

(Leave the rest of `render_stream` unchanged.)

Widen `render`'s signature from `node: ElementOrStr` to `node: Renderable` (its body is unchanged — it already drives `render_stream`).

- [ ] **Step 4: Re-export from the boundary**

In `src/hint/__init__.py`, add to the `from hint._core import (...)` block (keep the block's existing alphabetical-ish ordering; ruff isort will enforce):

```python
    Document as Document,
    Renderable as Renderable,
    document as document,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest src/hint/render_test.py src/hint/stream_test.py -k document -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Lint/type and commit**

Run: `uv run ruff check src/hint/_core.py src/hint/__init__.py src/hint/render_test.py src/hint/stream_test.py && uv run ruff format --check src/hint && uv run pyright src/hint/_core.py`
Expected: clean.

```bash
git add src/hint/_core.py src/hint/__init__.py src/hint/render_test.py src/hint/stream_test.py
git commit -m "feat(render): add document node for the doctype"
```

---

### Task 2: `render_stream_async` accepts a `Document`

**Files:**
- Modify: `src/hint/_async.py`
- Test: `src/hint/async_test.py`

**Interfaces:**
- Consumes: `Document`, `document`, `Renderable` from Task 1.
- Produces: `render_stream_async(node: Renderable, fills)` — the async driver now streams a `Document` (doctype first) because it drives `render_stream`, which handles it.

- [ ] **Step 1: Write the failing test**

In `src/hint/async_test.py`, add `Renderable` and `document` to the `from hint import (...)` block (alphabetical), widen the existing `collect` helper's signature from `node: ElementOrStr` to `node: Renderable`, and add:

```python
def test_document_streams_doctype_first_over_async() -> None:
    async def main() -> list[ElementOrStr]:
        return [element("h1")(["Home"], {})]

    page = document(element("html")([element("body")([hole("main")], {})], {}))
    expected = "<!DOCTYPE html>\n<html><body><h1>Home</h1></body></html>"
    assert collect(page, {"main": main()}) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest src/hint/async_test.py -k document -v`
Expected: FAIL — pyright/`collect` rejects `Document` (or `ImportError` for `document`/`Renderable`) before the signature is widened.

- [ ] **Step 3: Widen `render_stream_async`**

In `src/hint/_async.py`: add `Renderable` to the `from hint._core import (...)` block, and change `render_stream_async`'s signature:

```python
def render_stream_async(node: Renderable, fills: Fills) -> AsyncGenerator[str]:
```

(Its body — `return _drive(render_stream(node), fills)` — is unchanged; `render_stream` already handles `Document`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest src/hint/async_test.py -k document -v`
Expected: PASS.

- [ ] **Step 5: Lint/type and commit**

Run: `uv run ruff check src/hint/_async.py src/hint/async_test.py && uv run pyright src/hint/_async.py`
Expected: clean.

```bash
git add src/hint/_async.py src/hint/async_test.py
git commit -m "feat(render): async driver streams a document node"
```

---

### Task 3: Drop the three `_html` functions

**Files:**
- Modify: `src/hint/_core.py`, `src/hint/_async.py`, `src/hint/__init__.py`
- Modify: `src/hint/render_test.py`, `src/hint/stream_test.py`, `src/hint/async_test.py`

**Interfaces:**
- Removes public `render_html`, `render_html_stream`, `render_html_stream_async`. Their behaviour is subsumed by `document(...)` (Tasks 1–2). No new interfaces.

- [ ] **Step 1: Remove the functions and re-exports**

In `src/hint/_core.py`, delete `render_html` (the `def render_html(root: Element) -> str:` block) and `render_html_stream` (the `def render_html_stream(...)` block) in full.

In `src/hint/_async.py`, delete `render_html_stream_async` (the `def render_html_stream_async(...)` block). Then remove now-unused imports from its `from hint._core import (...)`: drop `render_html_stream`, and drop `Element` (it was only used by the deleted function's `root: Element` param — confirm no other use remains in the file).

In `src/hint/__init__.py`, remove these three re-export lines: `render_html as render_html,` and `render_html_stream as render_html_stream,` (from the `_core` block) and `render_html_stream_async as render_html_stream_async,` (from the `_async` block).

- [ ] **Step 2: Remove the obsolete tests**

- `src/hint/render_test.py`: delete `test_render_html_prepends_exactly_one_doctype` and `test_render_html_rejects_a_non_html_root`; remove `render_html` from the `from hint import` line. (The doctype case is now `test_document_renders_doctype_then_child`; the "rejects non-html root" case is intentionally gone — `document` does not validate, and nesting is a type error.)
- `src/hint/stream_test.py`: delete `drive_html`, `test_html_stream_prepends_exactly_one_doctype`, `test_html_stream_rejects_a_non_html_root`, and `test_html_stream_fills_holes_in_the_body`; remove `render_html_stream` from the import block. (Doctype + body-fill are now covered by the Task 1 `document` tests.)
- `src/hint/async_test.py`: delete `collect_html`, `test_html_async_prepends_doctype_and_fills_the_body`, `test_html_async_rejects_a_non_html_root`; remove `render_html_stream_async` from the import block, and remove `Element` from the import if `collect_html` was its only user (confirm — otherwise keep it).

- [ ] **Step 3: Run the suite to verify nothing references the removed names**

Run: `uv run pytest src/hint -q`
Expected: PASS (no `ImportError`/`AttributeError`, no failures). Then `grep -rn "render_html" src/hint` — expected: no matches.

- [ ] **Step 4: Lint/type and commit**

Run: `uv run ruff check src/hint && uv run pyright src/hint && uv run lint-imports`
Expected: clean (ruff catches any leftover unused import; import-linter still green).

```bash
git add src/hint/_core.py src/hint/_async.py src/hint/__init__.py src/hint/render_test.py src/hint/stream_test.py src/hint/async_test.py
git commit -m "feat(render)!: drop render_html variants in favour of the document node"
```

---

### Task 4: Move `render` to `hint/_helper.py`

**Files:**
- Create: `src/hint/_helper.py`
- Modify: `src/hint/_core.py`, `src/hint/__init__.py`

**Interfaces:**
- Consumes: `render_stream`, `Renderable`, `Hole` from `_core`.
- Produces: `render(node: Renderable) -> str` now lives in `hint._helper` (re-exported unchanged from the boundary). No behaviour change.

- [ ] **Step 1: Create `_helper.py` with `render` moved verbatim**

Create `src/hint/_helper.py`:

```python
"""Conveniences built on the core render/stream vocabulary.

Internal module. These are *just* helpers over :func:`hint._core.render_stream` —
the public boundary re-exports them flat, so callers do not see the distinction, but
internally they live here, apart from the core vocabulary, and this module is expected
to grow. Import these names from the package boundary (``hint``), not from here.
"""

from hint._core import Hole, Renderable, render_stream


def render(node: Renderable) -> str:
    """Render a description tree to an HTML string, escaping text and attributes.

    Drives :func:`render_stream` and joins its output. Raises ``ValueError`` if the
    tree contains a :class:`Hole` — an eager render cannot resolve one.
    """
    parts: list[str] = []
    for item in render_stream(node):
        if isinstance(item, Hole):
            message = f"render() cannot resolve hole {item.name!r}; use render_stream"
            # A Hole here is a valid, well-typed value that render() cannot resolve —
            # not a type-safety violation, so ValueError (not TypeError) is correct.
            raise ValueError(message)  # noqa: TRY004
        parts.append(item)
    return "".join(parts)
```

(This is the current `render` body copied verbatim, only relocated. Note the `# noqa: TRY004` — the project catalogues this suppression in CLAUDE.md.)

- [ ] **Step 2: Remove `render` from `_core.py` and re-point the boundary**

In `src/hint/_core.py`, delete the `def render(node: Renderable) -> str:` block.

In `src/hint/__init__.py`, remove `render as render,` from the `from hint._core import (...)` block, and add a new import block for it (place it so ruff isort is satisfied — `hint._core` sorts before `hint._helper`, which sorts before `hint._markdown`):

```python
from hint._helper import render as render
```

- [ ] **Step 3: Verify nothing broke (render unchanged; imports still clean)**

Run: `uv run pytest src/hint -q && uv run lint-imports`
Expected: PASS — every existing `render` test still passes (behaviour identical), and import-linter is green (`_helper` imports `_core` only; `include_external_packages`/forbidden contracts unaffected). If import-linter reports a new violation, `_helper` must import `hint._core`, never `hint`.

- [ ] **Step 4: Lint/type and commit**

Run: `uv run ruff check src/hint && uv run pyright src/hint`
Expected: clean.

```bash
git add src/hint/_helper.py src/hint/_core.py src/hint/__init__.py
git commit -m "refactor(render): move render into hint/_helper.py"
```

---

### Task 5: Docs and full gate

**Files:**
- Modify: `README.md`, `CLAUDE.md`

**Interfaces:** none (documentation + final verification).

- [ ] **Step 1: Update the README**

In `README.md`, find every reference to `render_html`, `render_html_stream`, and `render_html_stream_async` and replace the "full document" story with the `document(...)` node. Concretely: wherever the docs previously said "use `render_html(root)` for the full-document form" (eager) or the `render_html_stream` / async equivalents, replace with a single explanation that a document is a `document(...)` node that works across every eval mode:

```markdown
For a full document, wrap the `<html>` root in a `document(...)` node — it emits
`<!DOCTYPE html>` first. Because it is just a node, the *same* `render`,
`render_stream`, and `render_stream_async` handle it — there is no separate
`_html` function:

​```python
render(document(hint.html([...], {})))                       # eager
render_stream(document(hint.html([...], {})))                # sync stream
render_stream_async(document(hint.html([...], {})), fills)   # async
​```

A `document` node is only valid at the top of the tree — nesting one is a type error.
```

(Adjust surrounding prose so no dangling reference to the removed functions remains — `grep -n "render_html" README.md` must return nothing after editing.)

- [ ] **Step 2: Update CLAUDE.md**

In `CLAUDE.md`, in the "Package structure" bullet list: update the `hint/_core.py` bullet to reflect its current contents (it now includes `Document`/`document`/`Renderable` and no longer holds `render`/`render_html`), and add a new bullet after the `_core.py` one:

```markdown
- `hint/_helper.py` — conveniences over the core (`render`, and more over time). Imports
  `hint._core`, never the package boundary. The public API re-exports them flat.
```

- [ ] **Step 3: Full gate**

Run: `make check`
Expected: PASS — ruff (lint + format), pyright (strict), import-linter (all contracts), pytest (all suites; the `document` tests present, no `render_html` references anywhere). Fix any finding inline.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs(render): document the document node; note hint/_helper.py"
```

---

## Self-Review

**Spec coverage (PR A portion of the spec):**
- `document` node + `document()` + `Renderable` (Document out of `ElementOrStr`) → Task 1. ✓
- `document` works across eager / sync stream / async → Tasks 1 (eager, sync), 2 (async). ✓
- Drop `render_html` / `render_html_stream` / `render_html_stream_async` → Task 3. ✓
- Move `render` to `_helper.py` with "just helpers" docblock → Task 4. ✓
- No runtime validation of `document` child (type prevents nesting) → Task 1 (docstring + `Renderable` design). ✓
- README + CLAUDE.md → Task 5. ✓
- Yield protocol unchanged (tuple change is PR B) → Global Constraints; `render_stream` still yields `str | Hole`. ✓
- Breaking-change marker for release-please → Global Constraints + Task 3 commit `!`. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. The README block uses a zero-width-space before its inner fences (`​```) purely so this plan's own fences don't terminate early — the implementer writes plain ``` fences. ✓

**Type consistency:** `Document` (field `child: Element`), `document(child: Element) -> Document`, `Renderable = ElementOrStr | Document`, `render(node: Renderable) -> str`, `render_stream(node: Renderable) -> Generator[StreamItem, list[ElementOrStr] | None]`, `render_stream_async(node: Renderable, fills: Fills) -> AsyncGenerator[str]` — consistent across all tasks. ✓
