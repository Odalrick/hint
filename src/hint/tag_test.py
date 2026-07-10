import hint


def test_tag_renders_with_its_own_name() -> None:
    rendered = hint.render(hint.section([hint.p(["x"], {})], {}))
    assert rendered == "<section><p>x</p></section>"


def test_del_alias_renders_a_del_element() -> None:
    assert hint.render(hint.del_(["gone"], {})) == "<del>gone</del>"


def test_builtin_shadowing_tags_are_available_and_correct() -> None:
    assert hint.render(hint.input([], {"type": "text"})) == '<input type="text"/>'
    assert hint.render(hint.object([], {})) == "<object></object>"
    assert hint.render(hint.map([], {})) == "<map></map>"


def test_void_tags_self_close() -> None:
    assert hint.render(hint.br([], {})) == "<br/>"
    assert hint.render(hint.hr([], {})) == "<hr/>"
    assert hint.render(hint.img([], {"src": "/x"})) == '<img src="/x"/>'


def test_style_is_the_helper_not_a_plain_constructor() -> None:
    # `<style>` has no plain constructor; the style() helper emits CSS verbatim.
    assert hint.render(hint.style("a>b{}")) == "<style>a>b{}</style>"
    assert not hasattr(hint.style, "__wrapped__")


def test_vocabulary_covers_a_representative_sample_across_categories() -> None:
    names = [
        "html",
        "head",
        "title",
        "body",
        "article",
        "figure",
        "dialog",
        "template",
        "slot",
        "search",
        "picture",
        "ruby",
        "output",
        "meter",
        "colgroup",
        "fieldset",
        "blockquote",
        "hgroup",
    ]
    for name in names:
        construct = getattr(hint, name)
        assert construct([], {}).name == name
