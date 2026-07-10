import hint


def test_package_is_importable() -> None:
    assert hint.__doc__ is not None
