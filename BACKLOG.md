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
