"""Conveniences built on the core render/stream vocabulary.

Internal module. These are *just* helpers over :func:`hint._core.render_stream` —
the public boundary re-exports them flat, so callers do not see the distinction, but
internally they live here, apart from the core vocabulary, and this module is expected
to grow. Import these names from the package boundary (``hint``), not from here.
"""

from hint._core import Hole, Renderable, render_stream


def render(node: Renderable) -> str:
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
