"""The element tree and the render step.

Internal module. Import these names from the package boundary (``hint``), not from
here (``from hint import Element, render``) — except sibling internal modules and tests.
"""

from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from html import escape
from unicodedata import category


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
type StreamItem = tuple[str, Hole | None]
type Renderable = ElementOrStr | Document


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


@dataclass
class Document:
    """A full HTML document: a doctype line followed by a single root child."""

    child: Element


type Node = Callable[[list[ElementOrStr], dict[str, str]], Element]
type VoidNode = Callable[[dict[str, str]], Element]


_NAME_BREAKERS = frozenset("\"'<>/=")


def _is_sensible_name(name: str) -> bool:
    """Whether ``name`` stays one name inside a tag: no character that would end it."""
    return bool(name) and not any(
        character.isspace()
        or character in _NAME_BREAKERS
        or category(character) == "Cc"
        for character in name
    )


def _check_tag_name(name: str) -> None:
    if not (_is_sensible_name(name) and name[0].isascii() and name[0].isalpha()):
        message = f"invalid tag name {name!r}"
        raise ValueError(message)


def _check_attribute_names(tag: str, attrs: dict[str, str]) -> None:
    for name in attrs:
        if not _is_sensible_name(name):
            message = f"invalid attribute name {name!r} on <{tag}>"
            raise ValueError(message)


def element(name: str) -> Node:
    """Return a constructor for ``name`` elements: ``element("div")([...], {...})``.

    Raises ``ValueError`` for a tag name — here — or an attribute name — when the
    constructor is called — that could break out of the tag: empty, or containing
    whitespace, a quote, ``<``, ``>``, ``/``, ``=`` or a control character. A tag name
    must also start with an ASCII letter. Names come from code, so the error lands on
    the line that wrote them; no escaping of a name would be meaningful.
    """
    _check_tag_name(name)

    def construct(content: list[ElementOrStr], attrs: dict[str, str]) -> Element:
        _check_attribute_names(name, attrs)
        return Element(name=name, content=content, attrs=attrs)

    return construct


def void_element(name: str) -> VoidNode:
    """Return a constructor for a void ``name`` element: ``void_element("br")({...})``.

    Void elements have no children in HTML, so the constructor takes attributes only —
    there is no content parameter to pass (and none to silently drop). Not part of the
    public API: the package boundary imports it internally to build the void tags.
    Refuses the same names as :func:`element`.
    """
    _check_tag_name(name)

    def construct(attrs: dict[str, str]) -> Element:
        _check_attribute_names(name, attrs)
        return Element(name=name, attrs=attrs)

    return construct


def style(content: str) -> Element:
    """Wrap CSS in a ``<style>`` element, emitting it verbatim (not escaped)."""
    return Element(name="style", content=[RawHtml(content)], attrs={})


def document(child: Element) -> Document:
    """Wrap a root element as a full document: a doctype line then the child.

    ``Document`` is intentionally outside ``ElementOrStr``, so a nested
    ``document(...)`` is a type error — a doctype is only valid at the top.
    """
    return Document(child=child)


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


def _walk(
    node: Renderable,
) -> Generator[str | Hole, list[ElementOrStr] | None]:
    """Recursively stream a tree as fine-grained ``str`` / ``Hole`` items.

    Internal to the streaming layer: :func:`render_stream` coalesces these into
    ``(run, hole)`` tuples. Yields a :class:`Hole` at each placeholder and splices
    back the ``list[ElementOrStr]`` the consumer sends.
    """
    if isinstance(node, Document):
        yield "<!DOCTYPE html>\n"
        yield from _walk(node.child)
        return
    if isinstance(node, RawHtml):
        yield node.content
        return
    if isinstance(node, Hole):
        filling = yield node
        if filling:  # None (priming/advance artifact) or [] both render empty
            for child in filling:
                yield from _walk(child)
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
        yield from _walk(child)
    yield f"</{node.name}>"


def render_stream(
    node: Renderable,
) -> Generator[StreamItem, list[ElementOrStr] | None]:
    """Stream a tree as ``(run, hole)`` tuples.

    Each item is the coalesced HTML run up to the next placeholder, paired with that
    :class:`Hole` — or ``(run, None)`` for the final run. The consumer emits ``run``
    and, when ``hole`` is not ``None``, sends back the ``list[ElementOrStr]`` fill
    (spliced through the same walk, nested holes and all).
    """
    walk = _walk(node)
    buffer: list[str] = []
    to_inner: list[ElementOrStr] | None = None
    while True:
        try:
            item = walk.send(to_inner)
        except StopIteration:
            break
        to_inner = None
        if isinstance(item, Hole):
            fill = yield ("".join(buffer), item)
            buffer.clear()
            to_inner = fill
        else:
            buffer.append(item)
    if buffer:
        yield ("".join(buffer), None)
