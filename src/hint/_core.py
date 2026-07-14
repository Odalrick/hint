"""The element tree and the render step.

Internal module. Import these names from the package boundary (``hint``), not from
here (``from hint import Element, render``) — except sibling internal modules and tests.
"""

from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from html import escape


@dataclass
class RawHtml:
    """Pre-rendered HTML that :func:`render` emits verbatim, without escaping."""

    content: str


@dataclass
class Hole:
    """A named placeholder that :func:`render_stream` suspends at.

    To be filled by the consumer.
    """

    name: str


type ElementOrStr = Element | str | RawHtml | Hole
type StreamItem = str | Hole


def _no_children() -> list[ElementOrStr]:
    return []


def _no_attrs() -> dict[str, str]:
    return {}


@dataclass
class Element:
    """A description of an HTML element: tag name, children, and attributes."""

    name: str
    content: list[ElementOrStr] = field(default_factory=_no_children)
    attrs: dict[str, str] = field(default_factory=_no_attrs)


type Node = Callable[[list[ElementOrStr], dict[str, str]], Element]
type VoidNode = Callable[[dict[str, str]], Element]


def element(name: str) -> Node:
    """Return a constructor for ``name`` elements: ``element("div")([...], {...})``."""

    def construct(content: list[ElementOrStr], attrs: dict[str, str]) -> Element:
        return Element(name=name, content=content, attrs=attrs)

    return construct


def void_element(name: str) -> VoidNode:
    """Return a constructor for a void ``name`` element: ``void_element("br")({...})``.

    Void elements have no children in HTML, so the constructor takes attributes only —
    there is no content parameter to pass (and none to silently drop). Not part of the
    public API: the package boundary imports it internally to build the void tags.
    """

    def construct(attrs: dict[str, str]) -> Element:
        return Element(name=name, attrs=attrs)

    return construct


def style(content: str) -> Element:
    """Wrap CSS in a ``<style>`` element, emitting it verbatim (not escaped)."""
    return Element(name="style", content=[RawHtml(content)], attrs={})


def hole(name: str) -> Hole:
    """Return a named :class:`Hole` placeholder for streaming render to suspend at."""
    return Hole(name=name)


# The HTML Living Standard void elements — they never have children or a closing tag.
_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    },
)


def render_stream(
    node: ElementOrStr,
) -> Generator[StreamItem, list[ElementOrStr] | None]:
    """Stream a description tree as HTML chunks, suspending at each :class:`Hole`.

    Yields ``str`` output; yields a :class:`Hole` when it reaches a placeholder and
    (in the filled form) splices back the ``list[ElementOrStr]`` the consumer sends.
    """
    if isinstance(node, RawHtml):
        yield node.content
        return
    if isinstance(node, Hole):
        filling = yield node
        if filling:  # None (priming/advance artifact) or [] both render empty
            for child in filling:
                yield from render_stream(child)
        return
    if isinstance(node, str):
        yield escape(node)
        return
    attributes = "".join(
        f' {escape(name, quote=True)}="{escape(value, quote=True)}"'
        for name, value in node.attrs.items()
    )
    if node.name in _VOID_ELEMENTS:
        yield f"<{node.name}{attributes}/>"
        return
    yield f"<{node.name}{attributes}>"
    for child in node.content:
        yield from render_stream(child)
    yield f"</{node.name}>"


def render(node: ElementOrStr) -> str:
    """Render a description tree to an HTML string, escaping text and attributes.

    Drives :func:`render_stream` and joins its output. Raises ``ValueError`` if the
    tree contains a :class:`Hole` — an eager render cannot resolve one.
    """
    parts: list[str] = []
    for item in render_stream(node):
        if isinstance(item, Hole):
            message = f"render() cannot resolve hole {item.name!r}; use render_stream"
            # A Hole here is a valid, well-typed value that render() cannot resolve —
            # not a type-safety violation, so ValueError (not TypeError) is correct.
            raise ValueError(message)  # noqa: TRY004
        parts.append(item)
    return "".join(parts)


def render_html(root: Element) -> str:
    """Render a full ``<html>`` document with the doctype line prepended."""
    if root.name != "html":
        message = "render_html requires an <html> root element"
        raise ValueError(message)
    return f"<!DOCTYPE html>\n{render(root)}"
