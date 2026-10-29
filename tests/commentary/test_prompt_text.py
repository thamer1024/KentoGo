"""Tests for kentogo.commentary.prompt_text."""

from kentogo.commentary.language import PROMPT_ENGLISH, PROMPT_JAPANESE, CommentaryLanguage
from kentogo.commentary.prompt_text import (
    DEFAULT_FILES,
    PROBLEM_MISSING,
    PROBLEM_UNKNOWN,
    PROBLEM_UNREADABLE,
    SECTIONS,
    USER_FILE_NAMES,
    create_user_prompt_file,
    default_prompt_text,
    load_prompt_text,
    parse_sections,
    user_prompt_path,
)


def test_parse_sections():
    """Each part goes from its line to the next part. Lines before the first part are ignored."""
    text = "ignored\n[[system]]\n\nrole\n\n[[rules]]\n1. a\n2. b\n"
    assert parse_sections(text) == {"system": "role", "rules": "1. a\n2. b"}


def test_default_files_have_all_parts():
    """The default file of each language has all parts, and the intro has the place for the color."""
    for language in (PROMPT_JAPANESE, PROMPT_ENGLISH):
        assert set(parse_sections(DEFAULT_FILES[language].read_text(encoding="utf-8"))) == set(SECTIONS)
        assert "{color}" in default_prompt_text(CommentaryLanguage(language)).intro


def test_without_user_file_the_default_is_used(tmp_path):
    """Without the user's file, the default is used without problems."""
    assert load_prompt_text(tmp_path / "settings.json") == (default_prompt_text(), [])


def test_user_file_with_missing_and_unknown_parts(tmp_path):
    """The user's parts are used; a missing part comes from the default, and the problems are told."""
    path = user_prompt_path(tmp_path / "settings.json")
    path.write_text("[[system]]\nmy role\n[[rules]]\nmy rules\n[[other]]\nx\n", encoding="utf-8")
    text, problems = load_prompt_text(tmp_path / "settings.json")
    assert (text.system, text.rules, text.intro) == ("my role", "my rules", default_prompt_text().intro)
    assert [(p.kind, p.section) for p in problems] == [
        (PROBLEM_MISSING, "intro"),
        (PROBLEM_MISSING, "about_me"),
        (PROBLEM_UNKNOWN, "other"),
    ]


def test_unreadable_user_file(tmp_path):
    """A file that is not UTF-8 text is not used, and the problem is told."""
    user_prompt_path(tmp_path / "settings.json").write_bytes(b"\xff\xfe\xfa")
    text, problems = load_prompt_text(tmp_path / "settings.json")
    assert text == default_prompt_text() and [p.kind for p in problems] == [PROBLEM_UNREADABLE]


def test_create_user_file(tmp_path):
    """The user's file is made from the default once, and is not overwritten later."""
    path = create_user_prompt_file(tmp_path / "sub" / "settings.json")
    assert path.read_text(encoding="utf-8") == DEFAULT_FILES[PROMPT_JAPANESE].read_text(encoding="utf-8")
    path.write_text("[[system]]\nchanged\n", encoding="utf-8")
    assert (
        create_user_prompt_file(tmp_path / "sub" / "settings.json")
        .read_text(encoding="utf-8")
        .startswith("[[system]]\nchanged")
    )


def test_each_language_has_its_own_user_file(tmp_path):
    """The English prompt uses its own file and default, and keeps the language; the Japanese file is not used."""
    english = CommentaryLanguage(PROMPT_ENGLISH, "German")
    user_prompt_path(tmp_path / "settings.json").write_text("[[system]]\n日本語\n", encoding="utf-8")
    text, problems = load_prompt_text(tmp_path / "settings.json", english)
    assert (text, problems) == (default_prompt_text(english), []) and text.language == english
    path = create_user_prompt_file(tmp_path / "settings.json", PROMPT_ENGLISH)
    assert path.name == USER_FILE_NAMES[PROMPT_ENGLISH]
    assert path.read_text(encoding="utf-8") == DEFAULT_FILES[PROMPT_ENGLISH].read_text(encoding="utf-8")
