"""Conveniences built on the core render/stream vocabulary.

Internal module. These are *just* helpers over :func:`hint._core.render_stream` —
the public boundary re-exports them flat, so callers do not see the distinction, but
internally they live here, apart from the core vocabulary, and this module is expected
to grow. Import these names from the package boundary (``hint``), not from here.
"""

from hint._core import Renderable, render_stream


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
