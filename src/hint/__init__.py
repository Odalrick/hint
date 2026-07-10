"""hint — build HTML as a tree of description values and render it once.

hint is not templating. HTML is built in code as a tree of plain description
values (:class:`Element`, :class:`RawHtml`, :class:`str`) by a constructor per tag,
and a single :func:`render` step converts the tree to a string at the edge.

The tag constructors (``div``, ``span``, …) are added in a later slice; this module
provides the machinery they are built from: :func:`element`, :func:`render`, and
:func:`render_html`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape


@dataclass
class RawHtml:
    """Pre-rendered HTML that :func:`render` emits verbatim, without escaping."""

    content: str


type ElementOrStr = Element | str | RawHtml


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


def element(name: str) -> Node:
    """Return a constructor for ``name`` elements: ``element("div")([...], {...})``."""

    def construct(content: list[ElementOrStr], attrs: dict[str, str]) -> Element:
        return Element(name=name, content=content, attrs=attrs)

    return construct


def style(content: str) -> Element:
    """Wrap CSS in a ``<style>`` element, emitting it verbatim (not escaped)."""
    return Element(name="style", content=[RawHtml(content)], attrs={})


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


def render(node: ElementOrStr) -> str:
    """Render a description tree to an HTML string, escaping text and attributes."""
    if isinstance(node, RawHtml):
        return node.content
    if isinstance(node, str):
        return escape(node)
    attributes = "".join(
        f' {name}="{escape(value, quote=True)}"' for name, value in node.attrs.items()
    )
    if node.name in _VOID_ELEMENTS:
        return f"<{node.name}{attributes}/>"
    children = "".join(render(child) for child in node.content)
    return f"<{node.name}{attributes}>{children}</{node.name}>"


def render_html(root: Element) -> str:
    """Render a full ``<html>`` document with the doctype line prepended."""
    if root.name != "html":
        message = "render_html requires an <html> root element"
        raise ValueError(message)
    return f"<!DOCTYPE html>\n{render(root)}"
