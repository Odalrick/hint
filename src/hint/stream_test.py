from hypothesis import given, strategies as st
import pytest

from hint import (
    Element,
    ElementOrStr,
    Hole,
    RawHtml,
    Renderable,
    document,
    element,
    hole,
    render,
    render_html_stream,
    render_stream,
)


def test_hole_constructor_builds_named_hole() -> None:
    assert hole("pr-list") == Hole(name="pr-list")


def test_hole_exposes_its_name() -> None:
    assert hole("rows").name == "rows"


_NON_VOID_NAMES = ["div", "span", "p", "ul", "li", "section"]


def _build_element(
    name: str, kids: list[ElementOrStr], attrs: dict[str, str]
) -> Element:
    return Element(name=name, content=list(kids), attrs=attrs)


def _element_strategy(
    children: st.SearchStrategy[ElementOrStr],
) -> st.SearchStrategy[ElementOrStr]:
    return st.builds(
        _build_element,
        st.sampled_from(_NON_VOID_NAMES),
        st.lists(children, max_size=3),
        st.dictionaries(st.text(min_size=1), st.text(), max_size=2),
    )


def _hole_free_trees() -> st.SearchStrategy[ElementOrStr]:
    leaves = st.one_of(st.text(), st.builds(RawHtml, st.text()))
    return st.recursive(leaves, _element_strategy, max_leaves=15)


@given(_hole_free_trees())
def test_stream_joins_to_the_eager_render(tree: ElementOrStr) -> None:
    streamed = "".join(part for part in render_stream(tree) if isinstance(part, str))
    assert streamed == render(tree)


def test_render_raises_on_an_unresolved_hole() -> None:
    with pytest.raises(ValueError, match="pr-list"):
        render(element("div")([hole("pr-list")], {}))


def test_stream_surfaces_the_hole_as_a_hole_item() -> None:
    items = list(render_stream(element("div")([hole("rows")], {})))
    assert items == ["<div>", Hole(name="rows"), "</div>"]


def drive(node: Renderable, fills: dict[str, list[ElementOrStr]]) -> str:
    """Drive render_stream to completion, filling each hole from `fills` by name."""
    generator = render_stream(node)
    parts: list[str] = []
    to_send: list[ElementOrStr] | None = None
    while True:
        try:
            item = generator.send(to_send)
        except StopIteration:
            break
        to_send = None
        if isinstance(item, Hole):
            to_send = fills.get(item.name, [])
        else:
            parts.append(item)
    return "".join(parts)


def test_hole_filled_with_a_single_element() -> None:
    tree = element("main")([hole("body")], {})
    filled = drive(tree, {"body": [element("p")(["hi"], {})]})
    assert filled == "<main><p>hi</p></main>"


def test_hole_filled_with_a_sibling_list_needs_no_wrapper() -> None:
    tree = element("tbody")([hole("rows")], {})
    rows: list[ElementOrStr] = [
        element("tr")([element("td")([str(n)], {})], {}) for n in (1, 2)
    ]
    filled = drive(tree, {"rows": rows})
    assert filled == "<tbody><tr><td>1</td></tr><tr><td>2</td></tr></tbody>"


def test_unfilled_hole_renders_empty() -> None:
    tree = element("div")(["a", hole("gap"), "b"], {})
    assert drive(tree, {}) == "<div>ab</div>"


def test_nested_hole_in_sent_content_is_fillable() -> None:
    tree = element("section")([hole("outer")], {})
    fills: dict[str, list[ElementOrStr]] = {
        "outer": [element("div")([hole("inner")], {})],
        "inner": [element("span")(["deep"], {})],
    }
    assert drive(tree, fills) == "<section><div><span>deep</span></div></section>"


def drive_html(root: Element, fills: dict[str, list[ElementOrStr]]) -> str:
    """Drive render_html_stream to completion, filling each hole from fills."""
    generator = render_html_stream(root)
    parts: list[str] = []
    to_send: list[ElementOrStr] | None = None
    while True:
        try:
            item = generator.send(to_send)
        except StopIteration:
            break
        to_send = None
        if isinstance(item, Hole):
            to_send = fills.get(item.name, [])
        else:
            parts.append(item)
    return "".join(parts)


def test_html_stream_prepends_exactly_one_doctype() -> None:
    items = list(render_html_stream(element("html")([], {})))
    assert items == ["<!DOCTYPE html>\n", "<html>", "</html>"]


def test_html_stream_rejects_a_non_html_root() -> None:
    with pytest.raises(ValueError, match="html"):
        list(render_html_stream(element("div")([], {})))


def test_html_stream_fills_holes_in_the_body() -> None:
    page = element("html")([element("body")([hole("main")], {})], {})
    filled = drive_html(page, {"main": [element("h1")(["Home"], {})]})
    assert filled == "<!DOCTYPE html>\n<html><body><h1>Home</h1></body></html>"


def test_stream_self_closes_a_void_element_with_escaped_attrs() -> None:
    items = list(render_stream(element("img")([], {"src": "/a<b>"})))
    assert items == ['<img src="/a&lt;b&gt;"/>']


def test_fill_content_is_escaped() -> None:
    tree = element("div")([hole("x")], {})
    assert drive(tree, {"x": ["<script>"]}) == "<div>&lt;script&gt;</div>"


def test_bare_hole_in_a_fill_list_is_itself_filled() -> None:
    tree = element("div")([hole("a")], {})
    fills: dict[str, list[ElementOrStr]] = {
        "a": [hole("b")],
        "b": [element("span")(["z"], {})],
    }
    assert drive(tree, fills) == "<div><span>z</span></div>"


def test_hole_as_the_top_level_node_is_filled() -> None:
    assert drive(hole("x"), {"x": [element("p")(["hi"], {})]}) == "<p>hi</p>"


def test_document_streams_doctype_then_child() -> None:
    items = list(render_stream(document(element("html")([], {}))))
    assert items == ["<!DOCTYPE html>\n", "<html>", "</html>"]


def test_document_with_a_hole_in_the_body_is_filled() -> None:
    page = document(element("html")([element("body")([hole("main")], {})], {}))
    filled = drive(page, {"main": [element("h1")(["Home"], {})]})
    assert filled == "<!DOCTYPE html>\n<html><body><h1>Home</h1></body></html>"
