# Backlog

Possible future work for `hint`. One section per idea — none of it is committed to, and the
list is expected to churn. See `docs/superpowers/specs/` for designs once an item is picked up.

## Content negotiation

Extract the `substrate.negotiate` helpers (serve HTML or JSON from one handler by `Accept`
header). It is FastAPI-coupled, so it belongs in its own package (or a `hint`-adjacent one),
not in the zero-dependency core.

## Pagination helpers

The prev/next-bar + page-number-row pattern (stable prev/next positions, disabled current-page
form as a `<span>`, top and bottom bars identical). Currently reimplemented per project.

## Canonical query parameters

Sorted-key query-string canonicalisation plus a `301`-to-canonical redirect helper, so one view
has one URL (which the current-path/active-link logic depends on).

## Chrome / layout vocabulary

The shared `water` / `plain` / `application` / `holy_grail` layout-function vocabulary. Today
these are project-local by design; revisit whether any baseline is worth sharing.

## SVG / MathML vocabularies

Constructors for the SVG and MathML element sets. They are separate namespaces with different
void-element and escaping rules, so they need their own handling rather than being folded into
the HTML vocabulary.

## Publish `hint-html` to PyPI

Publish the package (the name is reserved-in-intent). At that point also add a **mypy
compatibility gate** to CI: pyright is the day-to-day checker, but many consumers type-check with
mypy, and pyright-clean is not always mypy-clean.

## Assertions against the element tree

A vocabulary for asserting against an `Element` tree before it becomes a string. Page tests in
consumers match rendered HTML — `'<code>g1</code>' in html` — which couples each assertion to
attribute order and to self-closing style. Both caught tests out while building a consumer:
an assertion written as `value="e7">` missed because the renderer emits `value="e7"/>`, and one
written as `name="year" value=""` missed because the attributes render in declaration order.

Not needed. The output is deterministic enough that string matching holds, and a query API is
a surface to maintain. Recorded because the failure mode is a test that fails for a reason
having nothing to do with what it is testing.

## Document that siblings are emitted without whitespace

`hint.li([hint.a([title], {...}), hint.code([id], {})])` renders as `<a>…</a><code>…</code>`
with nothing between them, so the two run together in the text stream. Double-clicking the id
selects the tail of the title with it — `Final Fantasy X-2` yielding `201a0ec21-…`.

Nothing in the rendering looks wrong, and CSS cannot help: it moves boxes and cannot
reintroduce a word boundary into text. The fix in the consumer was a `<table>`, a cell boundary
being one the browser already honours. The caution belongs in the docs; the behaviour is
correct and should not change.

## Say in the design guide that a page wants a titled postfix

A title names a bookmark, a history entry and a tab group, so it is read far from the page and
has to carry its own context. `X-Change™ Life` says nothing about which tool it belongs to;
`X-Change™ Life — Game Library` does. Cheap to get right at the point a page is first written,
and easy to leave undone across every page of a tool.
