"""Tests for kentogo.gui.theme."""

from kentogo.gui import theme


def test_images_are_included():
    """The board, stone and menu images are in the package."""
    assert theme.BOARD_IMAGE.is_file()
    assert theme.MENU_IMAGE.is_file()
    assert all(path.is_file() for path in theme.STONE_IMAGES.values())
