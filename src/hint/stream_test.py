from hypothesis import given, strategies as st
import pytest

from hint import (
    Element,
    ElementOrStr,
    Hole,
    RawHtml,
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
    streamed = "".join(part for part in render_stream(tree) if isinstance(part, str))
    assert streamed == render(tree)


def test_render_raises_on_an_unresolved_hole() -> None:
    with pytest.raises(ValueError, match="pr-list"):
        render(element("div")([hole("pr-list")], {}))


def test_stream_surfaces_the_hole_as_a_hole_item() -> None:
    items = list(render_stream(element("div")([hole("rows")], {})))
    assert items == ["<div>", Hole(name="rows"), "</div>"]
