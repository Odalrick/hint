from html import escape

from hypothesis import given, strategies as st
import pytest

from hint import RawHtml, document, element, render, render_html, style


def test_renders_empty_element() -> None:
    assert render(element("div")([], {})) == "<div></div>"


def test_renders_attribute() -> None:
    assert render(element("a")(["home"], {"href": "/"})) == '<a href="/">home</a>'


def test_renders_children_in_order() -> None:
    tree = element("ul")([element("li")(["a"], {}), element("li")(["b"], {})], {})
    assert render(tree) == "<ul><li>a</li><li>b</li></ul>"


def test_escapes_text_content() -> None:
    rendered = render(element("p")(["<b> & </b>"], {}))
    assert rendered == "<p>&lt;b&gt; &amp; &lt;/b&gt;</p>"


def test_escapes_attribute_values() -> None:
    assert (
        render(element("a")([], {"title": '"x" & <y>'}))
        == '<a title="&quot;x&quot; &amp; &lt;y&gt;"></a>'
    )


def test_raw_html_passes_through_unescaped() -> None:
    assert render(element("div")([RawHtml("<b>hi</b>")], {})) == "<div><b>hi</b></div>"


def test_void_element_self_closes() -> None:
    assert render(element("br")([], {})) == "<br/>"
    assert render(element("img")([], {"src": "/x.png"})) == '<img src="/x.png"/>'


def test_attribute_names_are_escaped() -> None:
    assert render(element("a")([], {'x"y': "v"})) == '<a x&quot;y="v"></a>'


def test_non_void_element_always_has_a_closing_tag() -> None:
    assert render(element("script")([], {})) == "<script></script>"


def test_style_emits_css_verbatim() -> None:
    rendered = render(style("a > b { color: red }"))
    assert rendered == "<style>a > b { color: red }</style>"


def test_render_html_prepends_exactly_one_doctype() -> None:
    out = render_html(element("html")([], {}))
    assert out == "<!DOCTYPE html>\n<html></html>"
    assert out.count("<!DOCTYPE html>") == 1


def test_render_html_rejects_a_non_html_root() -> None:
    with pytest.raises(ValueError, match="html"):
        render_html(element("div")([], {}))


def test_document_renders_doctype_then_child() -> None:
    assert render(document(element("html")([], {}))) == "<!DOCTYPE html>\n<html></html>"


@given(st.text())
def test_text_never_leaks_unescaped_angle_brackets(text: str) -> None:
    inner = render(element("p")([text], {})).removeprefix("<p>").removesuffix("</p>")
    assert "<" not in inner
    assert ">" not in inner


@given(st.text())
def test_attribute_value_escaping_matches_stdlib(value: str) -> None:
    assert (
        render(element("span")([], {"data-x": value}))
        == f'<span data-x="{escape(value, quote=True)}"></span>'
    )
