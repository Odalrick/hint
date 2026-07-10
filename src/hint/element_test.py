from hint import Element, RawHtml, element


def test_element_factory_builds_named_element() -> None:
    build = element("section")
    assert build(["x"], {"id": "s"}) == Element(
        name="section", content=["x"], attrs={"id": "s"}
    )


def test_element_dataclass_defaults_to_empty_content_and_attrs() -> None:
    assert Element(name="div") == Element(name="div", content=[], attrs={})


def test_raw_html_holds_its_content() -> None:
    assert RawHtml("<b>hi</b>").content == "<b>hi</b>"
