from hint import Hole, hole


def test_hole_constructor_builds_named_hole() -> None:
    assert hole("pr-list") == Hole(name="pr-list")


def test_hole_exposes_its_name() -> None:
    assert hole("rows").name == "rows"
