import pytest

from hint import Element, RawHtml, element, render
from hint._core import void_element


def test_element_factory_builds_named_element() -> None:
    build = element("section")
    assert build(["x"], {"id": "s"}) == Element(
        name="section", content=["x"], attrs={"id": "s"}
    )


def test_element_dataclass_defaults_to_empty_content_and_attrs() -> None:
    assert Element(name="div") == Element(name="div", content=[], attrs={})


def test_raw_html_holds_its_content() -> None:
    assert RawHtml("<b>hi</b>").content == "<b>hi</b>"


_BAD_NAMES = [
    "",
    "x y",
    "x\ty",
    "x\u00a0y",
    'x"y',
    "x'y",
    "x<y",
    "x>y",
    "x/y",
    "x=y",
    "x\x00y",
    "x\x7fy",
    "x\x85y",
]


@pytest.mark.parametrize("name", [*_BAD_NAMES, "1x", "-x", "écrit"])
def test_element_refuses_a_bad_tag_name(name: str) -> None:
    with pytest.raises(ValueError, match="invalid tag name"):
        element(name)


@pytest.mark.parametrize("name", [*_BAD_NAMES, "1x", "-x", "écrit"])
def test_void_element_refuses_a_bad_tag_name(name: str) -> None:
    with pytest.raises(ValueError, match="invalid tag name"):
        void_element(name)


@pytest.mark.parametrize("name", _BAD_NAMES)
def test_element_refuses_a_bad_attribute_name(name: str) -> None:
    with pytest.raises(ValueError, match=r"invalid attribute name .* on <a>"):
        element("a")([], {name: "v"})


@pytest.mark.parametrize("name", _BAD_NAMES)
def test_void_element_refuses_a_bad_attribute_name(name: str) -> None:
    with pytest.raises(ValueError, match=r"invalid attribute name .* on <img>"):
        void_element("img")({name: "v"})


@pytest.mark.parametrize(
    "name", ["data-x", "aria-label", "xml:lang", "données", "onclick"]
)
def test_element_accepts_a_sensible_attribute_name(name: str) -> None:
    assert render(element("a")([], {name: "v"})) == f'<a {name}="v"></a>'


@pytest.mark.parametrize("name", ["div", "DIV", "my-widget", "h1"])
def test_element_accepts_a_sensible_tag_name(name: str) -> None:
    assert render(element(name)([], {})) == f"<{name}></{name}>"
