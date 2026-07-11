import sys

import pytest

from hint import RawHtml, div, markdown, render

# Whitebox: with markdown_it installed (as in dev) the pre fallback is unreachable
# via the public `markdown`, so it is tested through the resolver directly.
from hint._markdown import (
    _render_as_pre,  # pyright: ignore[reportPrivateUsage]
    _select_renderer,  # pyright: ignore[reportPrivateUsage]
)


def test_markdown_renders_to_raw_html_when_available() -> None:
    result = markdown("# Title")
    assert isinstance(result, RawHtml)
    assert "<h1>" in result.content


def test_markdown_output_nests_and_renders() -> None:
    assert "<em>hi</em>" in render(div([markdown("*hi*")], {}))


def test_markdown_escapes_raw_html_in_untrusted_input() -> None:
    result = markdown("<script>alert(1)</script>")
    assert isinstance(result, RawHtml)
    assert "<script>" not in result.content
    assert "&lt;script&gt;" in result.content


def test_markdown_blocks_dangerous_link_schemes() -> None:
    dangerous = markdown("[x](javascript:alert)")
    assert isinstance(dangerous, RawHtml)
    assert 'href="javascript:' not in dangerous.content
    # a normal scheme still becomes a real link, so the block is scheme-specific
    safe = markdown("[ok](https://example.com)")
    assert isinstance(safe, RawHtml)
    assert 'href="https://example.com"' in safe.content


def test_pre_fallback_escapes_its_text() -> None:
    assert render(_render_as_pre("a < b & c")) == "<pre>a &lt; b &amp; c</pre>"


def test_selects_the_markdown_renderer_when_available() -> None:
    assert isinstance(_select_renderer()("# H"), RawHtml)


def test_selects_the_pre_fallback_when_markdown_it_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "markdown_it", None)
    renderer = _select_renderer()
    assert render(renderer("x < y")) == "<pre>x &lt; y</pre>"
