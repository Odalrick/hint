# `hint` 1.1.0 — Streaming render with holes — Design

*hint is not templating.* This is the design for the 1.1.0 streaming feature promised by the 1.0.0
extraction (see `BACKLOG.md` → "Streaming responses" and the 1.0.0 design's note that `render` was
"kept factored so that 1.1.0's `render_stream` is a trivial addition").

The feature turned out to be richer than the backlog's bare "yield the output string in chunks". The
motivating consumer — the `pr_dashboard` in the notes repo — makes slow GitHub API calls, and the value
is not chunking an already-built string but **deferring** the regions that need slow data: emit the page
shell immediately for fast time-to-first-byte, block only where slow data is actually needed, in
document order.

## The idea: a co-generator with holes

`render_stream` is a **synchronous generator** (a coroutine / "co-generator"). It walks the tree yielding
HTML chunks. The tree may contain named **hole** placeholders; when the walk reaches a hole it *yields the
hole and suspends*. The consumer `.send()`s content back for that hole, which is rendered inline (through
the same walk, so injected content may itself contain holes), and the walk continues.

`hint` stays **sync**. The consumer's async event loop drives the generator and is free to `await` slow
work between a hole-yield and the matching `.send()`. Async driving is entirely the consumer's concern —
`hint` provides only the sync substrate (see Non-goals).

```python
page = hint.tbody([hint.hole("rows")], {})

gen = hint.render_stream(page)
item = next(gen)                       # prime → "<tbody>"
while True:
    try:
        if isinstance(item, hint.Hole):
            item = gen.send(build_rows(item.name))   # send list[ElementOrStr]
        else:
            emit(item)                               # str output chunk
            item = next(gen)
    except StopIteration:
        break
```

## Goals

- Add `render_stream` and `render_html_stream` co-generators that stream HTML and fill named holes.
- Keep the eager `render` / `render_html` surface **unchanged** for every existing caller.
- One recursive render walk shared by eager and streaming paths — no duplicated logic.
- No new dependencies; the pure-core and boundary invariants (import-linter) are untouched.

## Non-goals (1.1.0)

- **Async driver helper.** The real expected usage dispatches all hole fetches up front as parallel tasks
  (so total latency is `max` not `sum`), then drives the generator and `await`s each hole's task when the
  walk reaches it — often already resolved — while emission stays in document order. This is general and
  worth building, but it is a **follow-up** (a `BACKLOG.md` item), possibly alongside a `holes(node)`
  name-enumerator. The sync co-generator designed here is already sufficient substrate for it: the
  parallelism lives entirely in the consumer's async loop, so nothing below forecloses it.
- Out-of-order / client-side slot filling (React-Suspense style). Holes fill in document order.
- Coalescing/buffering of output chunks (see "Granularity").

## API surface

Two new public functions and one new type/constructor, re-exported from the `hint` boundary:

```python
type StreamItem = str | Hole

def render_stream(node: ElementOrStr) -> Generator[StreamItem, list[ElementOrStr] | None, None]: ...
def render_html_stream(root: Element) -> Generator[StreamItem, list[ElementOrStr] | None, None]: ...

@dataclass
class Hole:
    name: str

def hole(name: str) -> Hole: ...   # a plain constructor, like style(); not an HTML tag
```

The eager surface is unchanged in signature and behaviour:

- `render(node) -> str` — the everyday case. It drives `render_stream` internally and returns the joined
  string. Because the common tree has no holes, the hole machinery is invisible. If it *does* encounter a
  hole it cannot fill, it raises `ValueError` naming the hole.
- `render_html(root) -> str` — unchanged; prepends the doctype, requires an `<html>` root.

## Core semantics

### `Hole` is a fourth member of `ElementOrStr`

```python
type ElementOrStr = Element | str | RawHtml | Hole
```

A hole is a **pure placeholder** — no wrapper tag, no attributes. It is a legal child anywhere a child is
legal. To wrap it, write the wrapper yourself: `div([hole("x")], {"id": "x"})`.

### The generator protocol

`render_stream` is a recursive generator. The four `ElementOrStr` cases:

- `RawHtml` → `yield node.content` (verbatim).
- `str` → `yield escape(node)`.
- `Element` → `yield "<name attrs>"`, then `yield from render_stream(child)` per child, then
  `yield "</name>"`. Void elements `yield "<name attrs/>"` and stop.
- `Hole` → surface the hole, receive the fill, splice it in:

  ```python
  filling = yield node          # yields the Hole; receives list[ElementOrStr]
  if filling:                   # None (priming/advance artifact) or [] → empty hole
      for child in filling:
          yield from render_stream(child)
  ```

**Yield channel** (`StreamItem = str | Hole`): output is yielded as `str`; a request for content is the
`Hole` instance itself (consumer reads `item.name`). The consumer discriminates with `isinstance(item,
Hole)`.

**Send channel** (`list[ElementOrStr] | None`): the hole-fill contract is a homogeneous
`list[ElementOrStr]` — one node is `[node]`, an empty hole is `[]`, siblings are `[a, b, c]` (this is why
a `hole` inside a `<tbody>` can expand to many `<tr>`s with no wrapper). The `| None` in the type is a
protocol artifact only: Python forces the priming call to be `next(gen)` / `.send(None)`, and every
advance past an output chunk is likewise a bare `next()`. `None` therefore flows in only for priming and
advancing; it never means "fill this hole" — that is always a list.

**Nested holes** work for free: injected content is rendered through the same `render_stream` walk via
`yield from`, and `.send()`s propagate to the sub-generator transparently.

### `render` and `render_html` drive the generator

```python
def render(node: ElementOrStr) -> str:
    parts: list[str] = []
    for item in render_stream(node):     # for-loop advances with next() (sends None)
        if isinstance(item, Hole):
            message = f"render() cannot resolve hole {item.name!r}; use render_stream"
            raise ValueError(message)
        parts.append(item)
    return "".join(parts)
```

A hole reached during an eager `render` is a mistake (you meant to stream), so it raises a clear
`ValueError` rather than letting `"".join` choke on a non-`str`. `render_html` is unchanged and inherits
this behaviour through `render`.

### Full-document streaming

```python
def render_html_stream(root: Element) -> Generator[StreamItem, list[ElementOrStr] | None, None]:
    if root.name != "html":
        message = "render_html_stream requires an <html> root element"
        raise ValueError(message)
    yield "<!DOCTYPE html>\n"
    yield from render_stream(root)
```

Same yield/send types as `render_stream`, so the consumer drives it identically. `render_html` stays eager
and unchanged.

### Granularity

Output is yielded **per piece**: one yield for an element's open tag (attributes rendered into a single
string), one per child's output, one for the close tag. There is no coalescing buffer — a text-heavy page
produces many small yields, and the consuming server's socket buffer handles batching. Deliberately not
optimised further (YAGNI); noted here so the choice is explicit rather than accidental.

## Module layout

Everything lands in `hint/_core.py` (the boundary rule: `__init__.py` re-exports, never holds logic):

- `Hole` dataclass; `hole(name)` constructor.
- `ElementOrStr` union gains `Hole`.
- `render_stream`, `render_html_stream`.
- `render`, `render_html` refactored to drive the generator (no behavioural change).

`hint/__init__.py` gains four re-exports: `Hole`, `hole`, `render_stream`, `render_html_stream`.

No new dependencies (pure `collections.abc` / stdlib). The pure-core and `markdown_it`-only-in-`_markdown`
import-linter contracts are unaffected.

## Testing (TDD; hypothesis where it fits)

- **Equivalence (refactor guard):** for arbitrary hole-free trees, `"".join(render_stream(t)) ==
  render(t)`. The existing `render_test.py` cases keep passing unchanged.
- **`render` raises** `ValueError` naming the hole when the tree contains one.
- **Hole protocol:** `render_stream` yields the `Hole` at the correct position; `.send([...])` splices the
  content inline there; output before and after is in document order.
- **List fill:** a single `hole` fills with multiple siblings (`[tr, tr, tr]`) with no wrapper; `[]`
  renders empty.
- **Nested holes:** a hole inside sent content is surfaced and fillable in turn.
- **Unfilled hole:** advancing past a hole without sending a list (i.e. `None` arrives) renders empty.
- **`render_html_stream`:** yields exactly one doctype line first, rejects a non-`html` root with
  `ValueError`, then streams the body; drives identically to `render_stream`.
- **Full drive loop:** an end-to-end test running the consumer loop against a name→content map and
  asserting the assembled document.

Internal helpers are covered through the public surface (project testing convention).

## Versioning, commits, branch

- **release-please** bumps to **1.1.0** from the `feat:` commits (new public API, backward compatible).
- Conventional-commit scopes: primarily `render` and `core`; `docs` for README.
- Built on a fresh `feat/` branch off `main`, **after** the current `chore/drop-release-as` PR merges —
  not stacked on it.

## Documentation

`README.md` gains a "Streaming" section: the hole concept, `render_stream` / `render_html_stream`, the
`hint.hole` constructor, the `list[ElementOrStr]` fill contract, and the FastAPI consumer drive loop
(noting the parallel-dispatch async driver as planned follow-up). `BACKLOG.md`'s "Streaming responses"
section is replaced by a new "Async streaming driver" follow-up item.

## Open questions

None outstanding. Surface (`render_stream` + `render_html_stream`, unified co-generator, `render` as the
eager helper), the `list[ElementOrStr]` fill contract, empty-on-unfilled, and the sync-only scope are all
settled above.
