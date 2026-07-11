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

hint.render_html(page)
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
- `hint.render_html(root)` → prepends `<!DOCTYPE html>` and requires the root to be `<html>`
  (raises `ValueError` otherwise).

### Escaping and `RawHtml`

`render` escapes every `str` child and attribute value. The single escape hatch is
`hint.RawHtml("...")`, whose content is emitted unchanged — for pre-rendered HTML you trust,
such as rendered Markdown or an inline stylesheet:

```python
hint.style("body { margin: 0 }")   # a <style> element; its CSS is emitted verbatim
hint.RawHtml("<!-- trusted -->")   # anything you have already vetted
```

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
