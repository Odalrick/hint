# `hint` — render/stream contract redesign — Design

*hint is not templating.* This redesign reshapes the render/stream public contract. It is driven
by two flaws that the async-streaming-driver spike (PR #17,
`docs/superpowers/specs/2026-07-15-hint-async-streaming-driver-design.md`) made obvious:

1. **API cross-product explosion.** The render surface grew into a 3×2 grid — {eager, sync stream,
   async stream} × {fragment, full `<html>` document} — six functions, where the whole "full
   document" column is a thin "prepend doctype + require `<html>` root" wrapper duplicated per
   eval mode.
2. **Wrong yield granularity.** `render_stream` yields one *sync-walk fragment* per step
   (`"<div>"`, `"a"`, `"</div>"`), not the *full run up to the next hole*. The async driver just
   passes those tiny fragments through, so a consumer writing to a socket pays one write per
   element. The `None`-on-the-send-channel "advance" artifact is the same design fact seen from the
   other side: strings are yielded one at a time, so the consumer must `send(None)` to step past
   each one.

Both are contract-level, so both are **breaking changes**. Nothing past `hint-html-v1.0.0` is
released (the streaming work and the async driver sit on `main` unreleased), so this reshapes an
as-yet-unshipped surface; release-please will fold it into the next release from the commit types.

## Target contract (end state after both PRs)

**Render functions — three, no `_html` variants:**

- `render(node) -> str` — eager: drive `render_stream`, join, raise `ValueError` on any unresolved
  hole. A convenience over `render_stream`.
- `render_stream(node) -> Generator[StreamItem, list[ElementOrStr] | None]` — the core streaming
  co-generator.
- `render_stream_async(node, fills) -> AsyncGenerator[str]` — the async driver (unchanged in
  purpose; adapted to the new `StreamItem`).

**Description values / constructors:** `Element`, `RawHtml`, `Hole`, and a new `Document`; built by
`element`, `void_element`, `hole`, `style`, and a new `document`. The three render entry points take
`type Renderable = ElementOrStr | Document` (`Document` stays out of the child union — see PR A).

**Streaming item type:** `StreamItem = tuple[str, Hole | None]` — each yield is "the coalesced
string run, then the next hole (or `None` at the end)."

**Doctype** is a property of the tree (a `Document` node), not a family of functions.

**Module layout:**

- `hint/_core.py` — description values + their constructors (`element`, `void_element`, `hole`,
  `style`, `document`, the `RawHtml`/`Element`/`Hole`/`Document` types, the void set), the
  fine-grained `_walk`, and the coalescing `render_stream`. The core vocabulary.
- `hint/_helper.py` — conveniences built on the core. Today: `render`. Its module docblock states
  plainly that these are *just* helpers over `render_stream`, expected to grow over time. (The
  public boundary re-exports them flat; the "helper" status is internal-only, documented here.)
- `hint/_async.py` — `render_stream_async` and the `_drive` driver (adapted to the tuple contract).
- `hint/_markdown.py` — unchanged.

The boundary (`hint/__init__.py`) re-exports the public API flat, as today.

## Non-goals

- **Validation in `document`.** `document(child)` accepts any node and emits the doctype before it.
  Requiring the child to be `<html>`, or forbidding a nested `<html>`, is deferred — but `document`
  being a function means that guard has one obvious home if it ever earns its place.
- **Configurable coalescing / chunk sizing.** `render_stream` coalesces to hole boundaries, full
  stop. No flush-every-N-bytes knob.
- **Changing `render`'s output or the eager path's semantics** beyond adapting to the tuple type.
- **`holes(node)` enumerator** — still deferred (from the async spec).

---

## PR A — API consolidation (breaking)

Self-contained and shippable on its own. Does **not** touch the yield protocol.

### The `document` node

```python
@dataclass
class Document:
    """A full HTML document: a doctype line followed by a single root child."""
    child: Element


def document(child: Element) -> Document:
    """Wrap a root element as a full document: renders <!DOCTYPE html> then the child."""
    return Document(child=child)
```

- `Document` is **deliberately not** in `ElementOrStr` (the child union). Instead the render entry
  points accept a top-level type `type Renderable = ElementOrStr | Document`, and `render`,
  `render_stream`, `render_stream_async` (and `_walk`) take `Renderable`. Because `Document.child`
  is an `Element` and element children are `ElementOrStr`, a nested `document(...)` is a **type
  error** — "doctype only at top" is enforced for free by the type system, no runtime validator.
  (This is orthogonal to the deferred *html-element* validation — it constrains the `Document` node,
  not the `<html>` tag.)
- The walk handles `Document` by emitting `"<!DOCTYPE html>\n"` then walking `child`. Single child
  (a document has one root), not a list.
- No runtime validation of `child` (non-goal); the type already prevents nesting.

Usage across every eval mode, no per-mode function:

```python
render(document(html([...], {})))
render_stream(document(html([...], {})))
render_stream_async(document(html([...], {})), fills)
```

### Drop the `_html` functions

Remove `render_html`, `render_html_stream`, `render_html_stream_async` from `_core`/`_async` and
from the boundary re-exports. Their sole behaviour (doctype + `<html>`-root check) is subsumed by
`document`, uniformly, for all three eval modes.

### Move `render` to `_helper.py`

- Create `hint/_helper.py`; move `render` there. It imports `hint._core` only (never the boundary),
  same convention as `_markdown`/`_async`. Module docblock: "Conveniences over `render_stream`.
  These are *just* helpers — the public API re-exports them flat, but internally they live here,
  apart from the core vocabulary, and this module is expected to grow."
- `import-linter`: no new contract is strictly required (the existing "core free of web frameworks"
  contract already spans all of `hint`, and the core-stays-sync guard is scoped to `_core`, both
  unaffected). Verify `make imports` stays green; `_helper` importing `_core` is allowed.

### Docs / bookkeeping (PR A)

- README: replace the `render_html` / `render_html_stream` / async-`_html` references with the
  `document(...)` node; show it works across eager/sync-stream/async.
- CLAUDE.md: note `hint/_helper.py` in the package-structure section; update the `_core.py` bullet
  (now also holds `document`).
- This design doc lands with PR A.

### Tests (PR A)

- `document` renders `<!DOCTYPE html>\n` + child for eager (`render`), sync stream, and async.
- `document` with a hole inside streams/awaits correctly (doctype first).
- Existing `render_html*` tests are removed or rewritten against `document`.
- `make check` green.

---

## PR B — streaming granularity (breaking)

Self-contained and shippable; lands after PR A. Does **not** touch doctype/`document`.

### `StreamItem = tuple[str, Hole | None]` via a two-layer split

Coalescing cannot be done inside the recursive walk (a child's trailing text must merge with the
parent's *next* output; `yield from` would fragment at every element boundary). So:

- **`_walk(node)`** — today's `render_stream` body, unchanged: recursive, yields `str | Hole`
  fine-grained, receives the fill via `send`. (Renamed from `render_stream`; still handles
  `Document` after PR A.)
- **`render_stream(node)`** — a flat coalescing wrapper over `_walk`:

```python
def render_stream(
    node: Renderable,
) -> Generator[StreamItem, list[ElementOrStr] | None]:
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
            fill = yield ("".join(buffer), item)   # (run, hole); receive the fill
            buffer.clear()
            to_inner = fill                         # forward the fill to the inner walk
        else:
            buffer.append(item)
    if buffer:
        yield ("".join(buffer), None)              # trailing run, no hole
```

`StreamItem` becomes `type StreamItem = tuple[str, Hole | None]`.

### The consumer drive loop (the payoff)

```python
to_send = None
while True:
    try:
        run, hole = gen.send(to_send)
    except StopIteration:
        break
    emit(run)                        # one coalesced str: the full run up to the hole
    to_send = None
    if hole is not None:
        to_send = fill_for(hole)     # only ever send a fill — never None-to-advance
```

The `None`-advance artifact is gone: strings ride *with* the hole, so a fill is the only thing ever
sent back.

### Adapt `render` and `_drive`

- `render` (in `_helper.py`) becomes a plain for-loop:

```python
def render(node: Renderable) -> str:
    parts: list[str] = []
    for run, hole in render_stream(node):
        parts.append(run)
        if hole is not None:
            message = f"render() cannot resolve hole {hole.name!r}; use render_stream"
            raise ValueError(message)  # noqa: TRY004  (a Hole is a valid value render can't fill)
    return "".join(parts)
```

- The async `_drive` **stops buffering** (coalescing now lives in `render_stream`) and unpacks
  tuples:

```python
run, hole = generator.send(to_send)
if run:
    yield run                        # already coalesced
to_send = None
if hole is not None:
    to_send = await _resolve(hole.name, fills, tasks, results)
```

The `tasks`/`results` structures, up-front dispatch, caching, dynamic-holes, and the cancel-then-
gather `finally` are unchanged.

### Ripples / tests (PR B)

- `stream_test.py`: every assertion on the `str | Hole` protocol becomes a tuple assertion, e.g.
  `list(render_stream(element("div")([hole("rows")], {}))) == [("<div>", Hole("rows")), ("</div>",
  None)]`. The `drive`/`drive_html` helpers adapt to unpack `(run, hole)`.
- `render_test.py`: `render`'s *output* is unchanged, so these largely stand; verify.
- `async_test.py`: the `collect`-based tests join and are invariant; the early-break test keys on a
  now-coalesced first chunk (`"<div>x"` rather than `"<div>"`) — update it (this is the coalescing
  behaviour, now real at the source instead of in the driver).
- README: document the coalesced granularity ("each chunk is the full run up to the next hole") and
  the `(run, hole)` drive loop; drop the `None`-advance description.
- `make check` green.

---

## Versioning

Both PRs are breaking changes to the (unreleased) contract. Conventional commits with a
`BREAKING CHANGE:` footer (or `!`) so release-please classifies correctly; no manual version edit.
Because 1.1.0 has not shipped, these can land in the same eventual release as the streaming/async
work rather than churning a released API.

## Rollout

PR A then PR B, each off `main`, each green through `make check`, each its own review. `render` is
*moved* in A and *adapted* in B — clean as long as A merges first.
