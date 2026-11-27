"""Conveniences built on the core vocabulary.

Internal module. These are *just* helpers over :mod:`hint._core` — the public boundary
re-exports them flat, so callers do not see the distinction, but internally they live
here, apart from the core vocabulary, and this module is expected to grow. Import these
names from the package boundary (``hint``), not from here.
"""

from urllib.parse import urlsplit, urlunsplit

from hint._core import Element, ElementOrStr, Renderable, element, render_stream

_WEB_SCHEMES = frozenset({"http", "https"})


def render(node: Renderable) -> str:
    """Render a description tree to an HTML string, escaping text and attributes.

    Drives :func:`render_stream` and joins its output. Raises ``ValueError`` if the
    tree contains a :class:`Hole` — an eager render cannot resolve one.
    """
    parts: list[str] = []
    for run, hole in render_stream(node):
        parts.append(run)
        if hole is not None:
            message = f"render() cannot resolve hole {hole.name!r}; use render_stream"
            raise ValueError(message)
    return "".join(parts)


def safe_a(content: list[ElementOrStr], attrs: dict[str, str]) -> Element:
    """Build an ``a`` that links only to a web page: ``http`` or ``https``, with a host.

    For addresses from stored data that someone else may have written. The ``href`` is
    parsed and the rendered one rebuilt from its parts, so the stored value never
    reaches the page — only what the check judged. A refused or missing address
    renders the children in a ``span`` with the other attributes, so a bad value
    degrades to text rather than failing the page. HTML attribute names ignore case,
    so ``HREF`` is checked too, and two spellings of it are refused.
    """
    addresses = [value for name, value in attrs.items() if name.lower() == "href"]
    others = {name: value for name, value in attrs.items() if name.lower() != "href"}
    if len(addresses) != 1:
        return element("span")(content, others)
    try:
        parts = urlsplit(addresses[0])
    except ValueError:
        return element("span")(content, others)
    if parts.scheme not in _WEB_SCHEMES or not parts.netloc:
        return element("span")(content, others)
    return element("a")(content, {**others, "href": urlunsplit(parts)})
