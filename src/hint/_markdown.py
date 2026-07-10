"""Optional Markdown rendering.

:data:`markdown` renders CommonMark to HTML when the ``markdown`` extra
(``markdown-it-py``) is installed, returning :class:`~hint.RawHtml`. Without it,
the text is placed in a ``<pre>`` element instead — escaped like any other text.

The choice is resolved **once**, at import time, by binding a strategy. There is
no per-call dependency check and no availability flag: :data:`markdown` simply
*is* whichever strategy applies in this environment.
"""

from collections.abc import Callable

from hint import Element, ElementOrStr, RawHtml, pre


def _render_as_pre(text: str) -> Element:
    return pre([text], {})


def _select_renderer() -> Callable[[str], ElementOrStr]:
    try:
        # Lazy: markdown_it is the optional dependency, imported only when installed.
        from markdown_it import MarkdownIt  # noqa: PLC0415
    except ImportError:
        return _render_as_pre

    # html=False escapes raw HTML embedded in the markdown *input*, so untrusted
    # markdown cannot inject markup. markdown_it also validates link schemes by
    # default (blocking javascript:/vbscript:). Output is safe, hence RawHtml.
    parser = MarkdownIt("commonmark", {"breaks": True, "html": False}).enable("table")

    def render_markdown(text: str) -> RawHtml:
        return RawHtml(parser.render(text))

    return render_markdown


markdown: Callable[[str], ElementOrStr] = _select_renderer()
