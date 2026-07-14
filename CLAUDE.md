# hint — project conventions

`hint` is a small, pure-Python library for building HTML as a tree of description values and
rendering it to a string once. *hint is not templating.* Start with `README.md` for the API and
`docs/superpowers/specs/2026-07-10-hint-extraction-design.md` for the design rationale.

## Commands

```bash
uv sync --locked                        # install: dev deps + editable package
make check                              # all four gates (run before every push)
make format                             # ruff format + ruff check --fix
uv run pytest src/hint/render_test.py   # a single test file
uv run pytest -k void                   # tests matching a name
```

Install as a dependency (until PyPI): `uv add "hint-html @ git+https://github.com/Odalrick/hint"`.

## Package structure — a re-export boundary

`hint/__init__.py` is a **boundary**: it re-exports the public API and defines the tag constructors,
and holds no implementation logic (the thin `tag: Node = element("tag")` lines count as re-exports).
See the "boundary package" rule in add-comply's CLAUDE.md.

- `hint/_core.py` — implementation: `RawHtml`, `Element`, `ElementOrStr`, `element`/`Node`,
  `void_element`/`VoidNode`, `style`, the void-element set, `render`, `render_html`.
- `hint/_markdown.py` — the optional `markdown` binding. Imports `hint._core`, never the package
  boundary, so there is no import cycle.
- Internal modules are imported from the boundary, not from outside the package. `import-linter`
  guards this and the pure-core invariant.

## The calling convention

- Normal elements: `tag([children], {attrs})` — both positional, both required, empty spelled
  `div([], {})`. Deliberate and uniform; **do not** add keyword args or defaults.
- **Void elements** (`br`, `img`, `input`, …) take **attrs only**: `br({})`. They are built by the
  internal `void_element` factory (typed `VoidNode`) so passing children is a *type error*, not a
  silent drop. HTML's void set is fixed, so there is no public way to add a void tag.
- Add a normal tag with one line: `figure: Node = element("figure")`. No class, no registry.

## Escaping

`render` escapes text children, attribute **names**, and attribute **values**. `RawHtml("...")` is the
single escape hatch (rendered Markdown, inline `style()`). Never bypass it.

## Markdown

Optional extra `hint[markdown]` (`markdown-it-py`). The renderer is resolved **once** at import into a
bound strategy — `RawHtml` when installed, a `<pre>` fallback when not — never a per-call check and never
a `HAS_MARKDOWN` boolean. Parser runs with `html=False` (raw HTML in input is escaped) — safe on
untrusted input.

## Tooling

- Python **3.14** floor. `uv` (`uv sync --locked`). setuptools + `src/` layout. Ships `py.typed`.
- `make check` runs the four gates: **ruff** (`select = ["ALL"]`, lint + format), **pyright** (strict),
  **import-linter**, **pytest + hypothesis**. Run it before every push.
- Type checker is **pyright**, not mypy. A mypy compatibility gate is deferred to the PyPI milestone
  (see `BACKLOG.md`).
- Tests are colocated as `src/hint/*_test.py` (`testpaths = ["src"]`).

### Lint suppressions (why they exist)

- File-scoped `# ruff: noqa: A001` atop `__init__.py`: tag names `input`/`map`/`object` shadow builtins
  by design; every use site is qualified (`hint.input`).
- Global ignore of `TC001`/`TC002`/`TC003` in `pyproject.toml`: flake8-type-checking assumes stringized
  annotations, but this project evaluates annotations at runtime (no `from __future__ import annotations`).
- Per-site `# noqa: PLC0415` on the lazy `markdown_it` import — that lazy import is the point.
- Per-site `# noqa: TRY004` on `render`'s `raise ValueError` for an unresolved `Hole`: TRY004 wants a
  `TypeError` after an `isinstance` check, but a `Hole` is a valid, well-typed value `render` simply
  cannot resolve (you meant to stream) — a `ValueError`, not a type error.

## Versioning & commits

- Conventional commits. Scopes: `core`, `tags`, `markdown`, `render`, `build`, `ci`, `docs`, `deps`.
- **release-please** drives versioning/changelog/releases. The first release is forced to `1.0.0` via
  `release-as`; **remove that key after 1.0.0 ships** (BACKLOG) or every release pins to 1.0.0.

## Related

- `~/Config/claude/html-rendering-pattern.md` — the broader server-rendered-HTML pattern `hint` serves.
- `BACKLOG.md` — deferred work; the headline is **1.1.0 streaming** (`render_stream`), which `render` is
  already factored for.
