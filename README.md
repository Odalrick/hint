# hint

[![CI](https://github.com/Odalrick/hint/actions/workflows/ci.yml/badge.svg)](https://github.com/Odalrick/hint/actions/workflows/ci.yml)

*hint is not templating.*

Build HTML as a tree of plain description values and render it to a string **once**, at the
edge. A constructor per tag builds the tree; a single `render` walks it. Same idea as Elm's
`Html` or React's virtual DOM — without the diffing, because the tree is rendered once,
server-side, and sent to the browser as text.

Imported as `hint`; distributed as `hint-html`.

```python
import hint

page = hint.html(
    [
        hint.head([hint.title(["Home"], {})], {}),
        hint.body(
            [
                hint.h1(["Welcome"], {}),
                hint.p(["Built in code, not a template."], {}),
            ],
            {},
        ),
    ],
    {},
)

hint.render(hint.document(page))
# '<!DOCTYPE html>\n<html><head><title>Home</title></head>...'
```

## Why code, not templates

- **Type safety.** Page-builder functions take typed data and return typed `Element`s.
  Mistakes surface at type-check time, not at request time.
- **Composability.** A page is a function of data. Subcomponents are functions returning
  elements; pages are functions calling them. No template inheritance, no block/yield/super,
  no second language.
- **No second runtime.** No template loader, cache, or syntax errors at request time, and no
  questions about auto-escaping defaults. Escaping happens in `render`, once, predictably.

## Install

Until `hint-html` is on PyPI, install from Git:

```console
uv add "hint-html @ git+https://github.com/Odalrick/hint"
```

Markdown support is an optional extra (see [Markdown](#markdown)):

```console
uv add "hint-html[markdown] @ git+https://github.com/Odalrick/hint"
```

hint requires Python 3.14+, ships type information (`py.typed`), and has **no runtime
dependencies** (the `markdown` extra aside).

## The API

### Constructors

There is a constructor for every element in the current HTML Living Standard: `div`, `span`,
`a`, `form`, `table`, … Each takes **content** (a list of children) and **attrs** (a dict):

```python
hint.a(["home"], {"href": "/", "class": "nav-link"})
```

The signature is `(content, attrs)` — both positional, both required. Empty cases are spelled
out: `hint.div([], {})`. This is deliberate; it keeps every call site uniform. Children may be
`Element`s, plain `str` (escaped on render), or `RawHtml`.

**Void elements** (`br`, `img`, `input`, `hr`, `link`, `meta`, …) take **attrs only** — they
have no children in HTML, so their constructor has no content parameter:

```python
hint.br({})
hint.img({"src": "/logo.png", "alt": "Logo"})
```

Passing children to a void element is a type error, not a silent drop — `hint.br(["x"], {})`
does not type-check.

A page-builder is just a function that returns an `Element`, composing freely:

```python
def thing_row(thing: Thing) -> hint.Element:
    return hint.div(
        [
            hint.a([thing.name], {"href": f"/thing/{thing.id}"}),
            hint.span([thing.kind], {"class": "kind-badge"}),
        ],
        {"class": "thing-row"},
    )

def thing_list(things: list[Thing]) -> hint.Element:
    return hint.ul([hint.li([thing_row(t)], {}) for t in things], {})
```

Two element names collide with Python and are spelled accordingly: `<del>` is `hint.del_`
(`del` is a keyword), and `hint.input` / `hint.map` / `hint.object` shadow builtins but are
safe to use as `hint.input(...)` (qualified access shadows nothing).

### Rendering

- `hint.render(node)` → HTML string. Escapes text and attribute values; self-closes void
  elements (`<br/>`, `<img .../>`); passes `RawHtml` through verbatim.

For a full document, wrap the `<html>` root in a `document(...)` node — it emits
`<!DOCTYPE html>` first. Because it is just a node, the *same* `render`,
`render_stream`, and `render_stream_async` handle it — there is no separate
`_html` function:

```python
render(document(hint.html([...], {})))                       # eager
render_stream(document(hint.html([...], {})))                # sync stream
render_stream_async(document(hint.html([...], {})), fills)   # async
```

A `document` node is only valid at the top of the tree — nesting one is a type error.

### Streaming

For pages whose content is expensive to produce (slow API calls, large lists), render
incrementally instead of building the whole string first. `render_stream` is a synchronous
**co-generator**: each item is a `(run, hole)` tuple — the coalesced HTML run (a `str`) up to the
next named placeholder, paired with that `hint.Hole` (or `None` for the final run). The consumer
emits `run`, then, for a non-`None` hole, sends back a `list[ElementOrStr]` fill (which may itself
contain unfilled holes, spliced in — nested holes and all).

```python
page = hint.tbody([hint.hole("rows")], {})
```

Drive it with a loop that fills each hole by name (`[]` leaves a hole empty):

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

`hint` stays synchronous. Because the loop is yours, an async consumer (FastAPI
`StreamingResponse`) is free to `await` slow work between a hole and its `send`. The eager
`render` is unchanged; calling it on a tree that contains a hole raises `ValueError`, since an
eager render cannot fill it.

Wrapping the root in `document(...)` (see [Rendering](#rendering)) works the same way here — the
doctype simply opens the first run, coalesced with the tree up to the first hole.

#### Async driver: parallel fetches, document order

`render_stream_async` encapsulates the high-value pattern: given a
`name -> awaitable` mapping, it dispatches every known hole's fetch **up front** (so total latency
is `max`, not `sum`), then drives the walk and `await`s each hole as it is reached, yielding `str`
chunks in document order. asyncio only.

```python
fills = {
    "header": fetch_header(),   # coroutines; the driver wraps each into a task up front
    "rows": fetch_rows(),
    "footer": fetch_footer(),
}
async for chunk in hint.render_stream_async(page, fills):
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

If you stop consuming early (a `break` out of the `async for`), wrap the iterator in
`contextlib.aclosing()` so the outstanding fetches are cancelled promptly — a bare `break`
leaves them running until the async generator is finalised.

### Escaping and `RawHtml`

`render` escapes every `str` child and attribute value. The single escape hatch is
`hint.RawHtml("...")`, whose content is emitted unchanged — for pre-rendered HTML you trust,
such as an inline stylesheet or a snippet you have already vetted:

```python
hint.style("body { margin: 0 }")   # a <style> element; its CSS is emitted verbatim
hint.RawHtml("<!-- trusted -->")   # anything you have already vetted
```

For Markdown, don't render it yourself and wrap the result in `RawHtml` — that puts escaping
safety back on you. Reach for the built-in [`hint.markdown`](#markdown) (the optional
`hint[markdown]` extra) instead: it escapes raw HTML in the input by default, so it stays safe
on untrusted text, and returns `RawHtml` for you.

### Markdown

With the `markdown` extra installed, `hint.markdown(text)` renders CommonMark (tables
enabled) to `RawHtml`:

```python
hint.div([hint.markdown("# Title\n\nBody **text**.")], {})
```

Without the extra, `hint.markdown(text)` falls back to a `<pre>` element containing the raw
text. The choice is resolved **once**, at import — there is no per-call dependency check.

Raw HTML embedded in the Markdown *input* is escaped (the parser runs with `html=False`) and
link schemes are validated, so `hint.markdown` is safe to call on untrusted input.

### Adding a tag

There is nothing to register. If a tag is somehow missing, add one line:

```python
figure: hint.Node = hint.element("figure")
```

`hint.element(name)` is the factory every constructor is built from; `hint.Node` is its type.

## A note on currying

The uniform `(content, attrs)` arity is shaped to curry cleanly: in a language with automatic
currying, `div(content)` would yield a partial awaiting `attrs`, and `element` is already
`name → content → attrs → Element`. Python doesn't auto-curry, so the shape is latent rather
than exploited — but it is why the argument order is what it is.

## Acknowledgements

- **[Elm](https://elm-lang.org/)** — for doing this right: a typed `Html` tree rendered once,
  the model this library follows.
- **[React](https://react.dev/)** — for introducing the author to building UI as a tree of
  description values in the first place.

## License

MIT. See [LICENSE](LICENSE).
