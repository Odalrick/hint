from hypothesis import given, strategies as st
import pytest

from hint import render, safe_a


@pytest.mark.parametrize(
    "address",
    [
        "javascript:alert(1)",
        "javascript://example.com/%0aalert(1)",
        "JaVaScRiPt:alert(1)",
        "\x01javascript:alert(1)",
        "java\tscript:alert(1)",
        "data:text/html,x",
        "ftp://example.com/",
        "https:example.com",
        "/relative/path",
        "//example.com/",
        "",
        "   ",
        "http://[::1",
    ],
)
def test_refuses_a_non_web_address(address: str) -> None:
    rendered = render(safe_a(["x"], {"href": address, "class": "c"}))
    assert rendered == '<span class="c">x</span>'


def test_refuses_a_missing_href() -> None:
    assert render(safe_a(["x"], {"class": "c"})) == '<span class="c">x</span>'


@pytest.mark.parametrize(
    ("address", "rendered"),
    [
        ("https://example.com/a?b=1#c", "https://example.com/a?b=1#c"),
        ("http://example.com/", "http://example.com/"),
        ("HTTPS://Example.com/a", "https://Example.com/a"),
        ("ht\ttps://example.com/", "https://example.com/"),
        (" https://x.org", "https://x.org"),
        ("https://bücher.example/", "https://bücher.example/"),
    ],
)
def test_links_a_web_address_by_its_rebuilt_form(address: str, rendered: str) -> None:
    assert render(safe_a(["x"], {"href": address})) == f'<a href="{rendered}">x</a>'


def test_escapes_an_allowed_address() -> None:
    rendered = render(safe_a(["x"], {"href": 'https://x.org/"><b>'}))
    assert rendered == '<a href="https://x.org/&quot;&gt;&lt;b&gt;">x</a>'


@given(st.text())
def test_any_address_renders_as_text_or_a_web_link(address: str) -> None:
    rendered = render(safe_a([], {"href": address}))
    assert rendered == "<span></span>" or rendered.startswith(
        ('<a href="http://', '<a href="https://'),
    )
