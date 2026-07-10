# `hint` 1.0.0 — Design

*hint is not templating.* `hint` is a small, pure-Python library for building HTML as a tree of
description values and rendering it to a string once, at the edge. This document is the design for the
initial extraction (1.0.0): a faithful lift of an existing, copied-around library into a standalone,
CI'd, installable package — with the element vocabulary widened to the full HTML set.

## Background

The library already exists as four near-identical copies of one lineage, vendored as `substrate.html`
in `yog-sothoth`, `quick-portraits`, `easel-prompt`, and (an older Pydantic ancestor) in
`notes-jubilant-guacamole`. They share one shape:

- `element(name)` is a factory returning a `Node` — `Callable[[list[ElementOrStr], dict[str, str]], Element]`.
- Every tag is a `Node`: `div`, `span`, `a`, … Call sites are always `tag([children], {attrs})`.
- `Element` is a dataclass (`name`, `content`, `attrs`); `RawHtml` wraps pre-rendered, un-escaped content.
- `render(node)` recurses to an HTML string, escaping text and attribute values.
- `render_html(root)` prepends the doctype and requires the root to be `<html>`.
- Helpers: `style(css)`, and `markdown(text)` in some copies.

The canonical, best-behaved version is the dataclass implementation in `easel-prompt` /
`quick-portraits` (identical). The `notes` ancestor is Pydantic-based and — notably — does **not** escape
text content (an XSS hole the dataclass rewrite fixed); it is not the base.

The calling convention `tag([children], {attrs})` — both arguments positional and required, empty cases
spelled `div([], {})` — is **deliberate and stays unchanged**. It is exact, uniform, and abuses no
conventions. This is documented as load-bearing in `~/Config/claude/html-rendering-pattern.md` §3.1 and
is treated here as a fixed constraint, not a design variable.

The motivating reason to promote this from copied-code to a real library is a **1.1.0 streaming-response
feature** (see BACKLOG). 1.0.0 is a pure extraction plus CI; it must not foreclose streaming.

## Goals

- One installable, fully typed, zero-runtime-dependency library that replaces the four copies.
- Widen the element set from "tags each project happened to use" to the **full HTML Living Standard**
  element vocabulary — a library is expected to be complete.
- Correct escaping by default (the dataclass lineage's behaviour), with `RawHtml` as the only escape hatch.
- Optional Markdown rendering that costs nothing when unused and is resolved **once**, not per call.
- Maximum-strictness tooling and CI, versioned by conventional commits via release-please.

## Non-goals (1.0.0)

Everything below is deferred to `BACKLOG.md`, not designed here: streaming rendering, content negotiation
(`substrate.negotiate`), pagination helpers, canonical query-parameter handling, chrome/layout vocabulary,
SVG/MathML vocabularies, publishing to PyPI, and a mypy compatibility gate.

## Distribution & naming

- **Import package:** `hint`. **Distribution name:** `hint-html` (`hint` is taken on PyPI; `hint-html`
  is free and reads cleanly). The import/dist split is standard (`pillow`→`PIL`).
- **Now:** personal use, installed from GitHub as a git dependency.
- **Later (BACKLOG):** publish `hint-html` to PyPI. The name is fixed in `pyproject.toml` from day one so
  the eventual publish needs no rename.

## Architecture

### Module layout

```
src/hint/
    __init__.py       # core: RawHtml, Element, ElementOrStr, element, Node, all tag constructors,
                      #       style, render, render_html; re-exports markdown from _markdown
    _markdown.py      # optional-dependency binding + markdown()
    py.typed          # marks the package as typed (PEP 561)
    render_test.py    # tests colocated with source, house-style *_test.py under src/
    element_test.py
    markdown_test.py
docs/superpowers/specs/2026-07-10-hint-extraction-design.md
README.md
BACKLOG.md
pyproject.toml         # setuptools backend; [tool.ruff|pyright|pytest|importlinter] all live here
uv.lock
.python-version        # 3.14
Makefile               # check / lint / format / typecheck / imports / test (house style)
.github/workflows/ci.yml
.github/workflows/release-please.yml
```

Tests are colocated with source as `src/hint/*_test.py` with `testpaths = ["src"]`, matching house
style, rather than a separate top-level `tests/` directory.

Two modules rather than one so `import-linter` has a real invariant to guard: the core stays
dependency-free and `markdown_it` may be imported **only** from `hint._markdown`. Cheap now; load-bearing
as streaming and future extractions arrive.

### Core (`hint/__init__.py`)

Unchanged in shape from the canonical dataclass version:

```python
@dataclass
class RawHtml:
    """Pre-rendered HTML that render() must not escape."""
    content: str

type ElementOrStr = Element | str | RawHtml   # PEP 695 (Python 3.14)

@dataclass
class Element:
    name: str
    content: list[ElementOrStr] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)

type Node = Callable[[list[ElementOrStr], dict[str, str]], Element]

def element(name: str) -> Node: ...

def style(content: str) -> Element: ...      # <style> wrapping RawHtml(content)

def render(node: ElementOrStr) -> str: ...   # escapes str and attr values; RawHtml passes through

def render_html(root: Element) -> str: ...   # prepends "<!DOCTYPE html>\n"; requires root.name == "html"
```

`render` structure is kept factored so that 1.1.0's `render_stream(node) -> Iterator[str]` is a trivial
addition with `render` becoming `"".join(render_stream(node))`. No streaming code ships in 1.0.0.

### Element vocabulary

The full HTML Living Standard element set is exported, one `Node` per tag (`figure: Node = element("figure")`),
grouped by category with comments. Current elements only — obsolete elements (`font`, `center`, `marquee`,
`big`, `strike`, `tt`, `acronym`, `frame`/`frameset`, `applet`, `param`, `dir`) are excluded. SVG and MathML
vocabularies are excluded (separate namespaces with different void-element and escaping rules — a BACKLOG item).

Categories included: document metadata (`base`, `head`, `link`, `meta`, `style`, `title`); sectioning
(`address`, `article`, `aside`, `footer`, `header`, `h1`–`h6`, `hgroup`, `main`, `nav`, `section`, `search`,
`body`); text content (`blockquote`, `dd`, `div`, `dl`, `dt`, `figcaption`, `figure`, `hr`, `li`, `menu`,
`ol`, `p`, `pre`, `ul`); inline text (`a`, `abbr`, `b`, `bdi`, `bdo`, `br`, `cite`, `code`, `data`, `dfn`,
`em`, `i`, `kbd`, `mark`, `q`, `rp`, `rt`, `ruby`, `s`, `samp`, `small`, `span`, `strong`, `sub`, `sup`,
`time`, `u`, `var`, `wbr`); image/multimedia (`area`, `audio`, `img`, `map`, `track`, `video`); embedded
(`embed`, `iframe`, `object`, `picture`, `source`); scripting (`canvas`, `noscript`, `script`); edits
(`del_`, `ins`); tables (`caption`, `col`, `colgroup`, `table`, `tbody`, `td`, `tfoot`, `th`, `thead`, `tr`);
forms (`button`, `datalist`, `fieldset`, `form`, `input`, `label`, `legend`, `meter`, `optgroup`, `option`,
`output`, `progress`, `select`, `textarea`); interactive (`details`, `dialog`, `summary`); web components
(`slot`, `template`); root (`html`).

**Python name clashes:**

- `del` is a Python keyword and cannot be a bare name → exported as **`del_`** (trailing-underscore, PEP 8
  convention), constructing the `<del>` element.
- `input`, `map`, `object` shadow builtins at their definition lines only (ruff `A001`). Every use site is
  qualified attribute access — `hint.input`, `hint.map`, `hint.object` — which shadows nothing. The clash is
  intrinsic to a module whose entire purpose is defining tag-named constructors, so it is silenced with a
  **single file-scoped suppression** carrying a rationale, `# ruff: noqa: A001` at the top of `__init__.py`,
  rather than a per-line `# noqa` on each of the three lines. No other current elements shadow builtins.

**Void (self-closing) elements** — the official set: `area`, `base`, `br`, `col`, `embed`, `hr`, `img`,
`input`, `link`, `meta`, `source`, `track`, `wbr`. `render` emits `<tag .../>` (no close tag) for these.

### Markdown (`hint/_markdown.py`)

Optional extra `hint[markdown]`, pulling `markdown-it-py`. At **module load**, `_markdown` attempts the
import exactly once and binds a strategy:

- `markdown_it` importable → `markdown(text)` returns `RawHtml(MarkdownIt(...).render(text))`.
- not importable → `markdown(text)` returns `pre([text], {})` (an `Element`; the raw text, escaped by
  `render`, in a `<pre>`).

The resolution is done once, by binding a callable at import — **not** a per-invocation `try`/`except`, and
**not** a stored `HAS_MARKDOWN` boolean (booleans are only for `if`; here we bind the chosen function).
This is deliberately unlike the per-call optional-dependency check that made `duckdb` annoying.

`markdown` returns `ElementOrStr`, renderable by `render` in both branches.

## Rendering & escaping

- `str` children and all attribute values are escaped via stdlib `html.escape` (`quote=True` for attrs).
- `RawHtml.content` passes through verbatim — the single, explicit escape hatch (rendered Markdown, inline
  CSS via `style()`).
- Void elements emit no closing tag; all others emit `<name ...>children</name>`.
- `render_html` raises `ValueError` if the root element is not `<html>`.

## Tooling & CI

- **Python floor: 3.14.** Personal project targeting the latest runtime; enables PEP 695 `type` aliases.
- **uv** for dependency management; `uv sync --locked` in CI (fail on lock drift).
- **setuptools** build backend (`setuptools>=77` for SPDX `license`), `src/` layout, `py.typed` shipped —
  matches house style across the existing projects. Dev tooling lives in `[dependency-groups].dev` (PEP 735);
  the user-facing `markdown` extra lives in `[project.optional-dependencies]`.
- **ruff** — lint **and** format, `select = ["ALL"]`. Rule conflicts resolved per-site with `# noqa: RULE`;
  a rule disabled globally (in config) only with a rationale comment. The one file-scoped exception is
  `# ruff: noqa: A001` atop `__init__.py` (builtin-shadowing tag names — see Element vocabulary).
- **pyright — strict mode.** Single type checker (chosen over mypy for stronger inference, speed, and
  editor parity). A mypy compatibility gate is deferred to the PyPI milestone (BACKLOG).
- **import-linter** — contract(s): `hint` (core) importable without any third-party package; `markdown_it`
  reachable only through `hint._markdown`; forbidden imports of `fastapi`/`pydantic`/`jinja2` anywhere in
  `hint` (keeps the "pure HTML builder" invariant honest as the library grows).
- **pytest + hypothesis** for tests.
- **release-please** (python release type) drives version bumps, `CHANGELOG.md`, and GitHub releases from
  conventional commits. Starts at **1.0.0**.
- **GitHub Actions:** one CI workflow (ruff check, ruff format --check, pyright, import-linter, pytest) and
  one release-please workflow.

**Conventional-commit scopes for this repo:** `core`, `tags`, `markdown`, `render`, `build`, `ci`, `docs`,
`deps`.

## Testing

Port the existing `substrate/html/html_test.py` example cases, then add hypothesis property tests:

- **Escaping is never bypassed:** for arbitrary strings as text children and as attribute values, the
  rendered output contains no unescaped `<`, `>`, or `"` originating from the input.
- **`RawHtml` passes through** unchanged.
- **Structure round-trips:** children render in order; nesting depth is preserved.
- **Void elements** emit no closing tag and no children markup; **non-void** always emit a matching close.
- **`render_html`** rejects any non-`html` root with `ValueError` and prepends exactly one doctype line.
- **`markdown` fallback:** with `markdown_it` unavailable, `markdown(text)` renders as a `<pre>` whose
  content is the escaped text; with it available, output is `RawHtml`.

Internal helpers are covered through the public `render`/`render_html` surface; no dedicated tests for
privates (per project testing convention). The optional-dependency-absent branch is exercised by
constructing the fallback strategy directly (the binding is factored to be callable under test without
uninstalling the extra).

## Documentation

- **`README.md`** rehomes the conceptual + API material currently in `html-rendering-pattern.md`: the
  "why code, not templates" rationale (§2) and the `substrate.html` API description (§3.1), rewritten for
  the library (install, import `hint`, the `tag([children], {attrs})` convention, `RawHtml`, `render`,
  `render_html`, `markdown` extra, adding a tag). It also includes:
  - **Acknowledgements** — a nod to **Elm** for doing this right (a typed `Html` tree rendered once), and
    to **React** for introducing the author to the tree-of-descriptions pattern in the first place.
  - **A design note on currying** — the uniform `(content, attrs)` arity is deliberately shaped to
    auto-curry cleanly (`div(content)` yielding a partial awaiting `attrs`); Python simply doesn't
    auto-curry, so the shape is latent rather than exploited. Called out as intent, not a feature.
- **`~/Config/claude/html-rendering-pattern.md` is edited** as part of this work: the "vendored
  `substrate.html` / copy the union between projects / element-set drift is normal" guidance (§3.1) becomes
  obsolete once `hint` is a dependency and is replaced with "install `hint`"; the API description points at
  `hint`'s README. The rest of the pattern doc (§1, §3.2–3.9, `negotiate`) is unchanged.
- Consumer migration (repointing `yog-sothoth`/`quick-portraits`/`easel-prompt`/notes at `hint`) is
  **follow-up work per project**, not part of this repo's 1.0.0.

## BACKLOG.md (created in this work, one section per future item)

- **Streaming responses (1.1.0)** — `render_stream(node) -> Iterator[str]`; the motivating feature.
- **Content negotiation** — extract `substrate.negotiate` (FastAPI Accept-header content negotiation).
- **Pagination helpers** — the prev/next-bar + page-row pattern (pattern doc §3.8).
- **Canonical query parameters** — sorted-key canonicalisation + 301 redirect helper (pattern doc §3.9).
- **Chrome/layout vocabulary** — the `water`/`plain`/`application`/`holy_grail` shared naming (§3.4).
- **SVG / MathML vocabularies** — separate namespaces, distinct void/escaping rules.
- **Publish `hint-html` to PyPI** — plus a **mypy compatibility gate** in CI at that point.

## Open questions

None outstanding. The calling convention, element-set scope, naming, tooling, and distribution are all
settled above.
