# hint

*hint is not templating.*

Build HTML as a tree of description values and render it to a string once, at the edge —
a constructor per tag, a single `render`. The same idea as Elm's `Html` or React's virtual
DOM, without the diffing.

Imported as `hint`; distributed as [`hint-html`](https://pypi.org/project/hint-html/).

```python
import hint

hint.render(
    hint.div([hint.a(["home"], {"href": "/"})], {"class": "nav"}),
)
```

Full documentation lands with the library. The design lives in
[`docs/superpowers/specs/2026-07-10-hint-extraction-design.md`](docs/superpowers/specs/2026-07-10-hint-extraction-design.md).
