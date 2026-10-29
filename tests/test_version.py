"""Tests for reading the version of KentoGo (kentogo.version)."""

from kentogo.version import VERSION_FILE, app_version


def test_the_version_is_read_from_the_file(tmp_path):
    """The version is the text of the file, without the end of the line."""
    path = tmp_path / "version.txt"
    path.write_text("1.2.0\n", encoding="utf-8")
    assert app_version(path) == "1.2.0"


def test_a_byte_order_mark_is_not_part_of_the_version(tmp_path):
    """A file written by PowerShell with a byte order mark gives the same version."""
    path = tmp_path / "version.txt"
    path.write_text("1.2.0", encoding="utf-8-sig")
    assert app_version(path) == "1.2.0"


def test_no_version_without_the_file(tmp_path):
    """KentoGo run from the source has no file, and no version."""
    assert app_version(tmp_path / "version.txt") == ""


def test_no_version_when_the_file_is_empty(tmp_path):
    """An empty file gives no version."""
    path = tmp_path / "version.txt"
    path.write_text("\n", encoding="utf-8")
    assert app_version(path) == ""


def test_the_file_is_next_to_the_module():
    """The file is looked for where the programs put it (kentogo/version.txt, see packaging/*/kentogo.spec)."""
    assert VERSION_FILE.name == "version.txt" and VERSION_FILE.parent.name == "kentogo"
