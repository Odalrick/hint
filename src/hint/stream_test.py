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
    streamed = "".join(run for run, _hole in render_stream(tree))
    assert streamed == render(tree)


def test_render_stream_pairs_each_run_with_its_hole() -> None:
    tree = element("div")(["a", hole("x"), "b"], {})
    assert list(render_stream(tree)) == [("<div>a", Hole(name="x")), ("b</div>", None)]


def test_render_stream_coalesces_a_hole_free_tree_to_one_tuple() -> None:
    tree = element("div")(["a", element("span")(["b"], {}), "c"], {})
    assert list(render_stream(tree)) == [("<div>a<span>b</span>c</div>", None)]


def test_render_raises_on_an_unresolved_hole() -> None:
    with pytest.raises(ValueError, match="pr-list"):
        render(element("div")([hole("pr-list")], {}))


def test_stream_pairs_a_run_with_its_hole() -> None:
    items = list(render_stream(element("div")([hole("rows")], {})))
    assert items == [("<div>", Hole(name="rows")), ("</div>", None)]


def drive(node: Renderable, fills: dict[str, list[ElementOrStr]]) -> str:
    """Drive render_stream to completion, filling each hole from `fills` by name."""
    generator = render_stream(node)
    parts: list[str] = []
    to_send: list[ElementOrStr] | None = None
    while True:
        try:
            run, hole = generator.send(to_send)
        except StopIteration:
            break
        parts.append(run)
        to_send = None
        if hole is not None:
            to_send = fills.get(hole.name, [])
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


def test_stream_self_closes_a_void_element_with_escaped_attrs() -> None:
    items = list(render_stream(element("img")([], {"src": "/a<b>"})))
    assert items == [('<img src="/a&lt;b&gt;"/>', None)]


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
    assert items == [("<!DOCTYPE html>\n<html></html>", None)]


def test_document_with_a_hole_in_the_body_is_filled() -> None:
    page = document(element("html")([element("body")([hole("main")], {})], {}))
    filled = drive(page, {"main": [element("h1")(["Home"], {})]})
    assert filled == "<!DOCTYPE html>\n<html><body><h1>Home</h1></body></html>"
