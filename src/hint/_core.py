"""The element tree and the render step.

Internal module. Import these names from the package boundary (``hint``), not from
here (``from hint import Element, render``) — except sibling internal modules and tests.
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
        f' {escape(name, quote=True)}="{escape(value, quote=True)}"'
        for name, value in node.attrs.items()
    )
    if node.name in _VOID_ELEMENTS:
        # Void elements have no children and no closing tag. Content passed to a void
        # constructor is intentionally dropped in 1.0.0: supporting it would need a
        # void-specific factory or Element subclass, which would break the uniform
        # tag([children], {attrs}) signature — and HTML has no custom void elements.
        return f"<{node.name}{attributes}/>"
    children = "".join(render(child) for child in node.content)
    return f"<{node.name}{attributes}>{children}</{node.name}>"


def render_html(root: Element) -> str:
    """Render a full ``<html>`` document with the doctype line prepended."""
    if root.name != "html":
        message = "render_html requires an <html> root element"
        raise ValueError(message)
    return f"<!DOCTYPE html>\n{render(root)}"
