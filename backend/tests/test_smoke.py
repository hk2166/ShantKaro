from shant.cli import main


def test_package_imports() -> None:
    assert callable(main)
