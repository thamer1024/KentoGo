"""The choices and messages of the AI commentary screens, without Kivy (so that they can be tested)."""

from __future__ import annotations

from kentogo.commentary.answer import AnswerProblem
from kentogo.commentary.batch import STATUS_DONE, STATUS_FAILED, GameOutcome
from kentogo.commentary.language import (
    CATEGORIES,
    COMMENT_HEADERS,
    PROMPT_ENGLISH,
    PROMPT_JAPANESE,
    CommentaryLanguage,
    CommentLabels,
)
from kentogo.commentary.prompt import RELATION_HIGHER, RELATION_LOWER, RELATION_SAME
from kentogo.commentary.prompt_text import PromptFileProblem
from kentogo.commentary.provider_base import ERROR_OTHER, Generation
from kentogo.commentary.sgf_writer import WriteResult
from kentogo.commentary.targets import RANKS, normalize_rank
from kentogo.gui import texts

# The values of the choices, in the order they are shown ("" means not given).
COLORS = ("", "B", "W")
RANK_CHOICES = ("", *reversed(RANKS))  # The strongest rank first, as in a list of ranks on a server.
RELATION_CHOICES = (RELATION_SAME, RELATION_HIGHER, RELATION_LOWER, "")

_RELATION_KEYS = {RELATION_SAME: "relation_same", RELATION_HIGHER: "relation_higher", RELATION_LOWER: "relation_lower"}

# The language of the AI's answer for each language of the screens (see texts.LANGUAGES), in English for the prompt.
ANSWER_LANGUAGES = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "ua": "Ukrainian",
    "es": "Spanish",
    "ru": "Russian",
    "cn": "Simplified Chinese",
    "tw": "Traditional Chinese",
    "ko": "Korean",
    "jp": "Japanese",
    "tr": "Turkish",
}
# The words of CommentLabels that are in the texts (the colors, categories and headers are made apart).
_NOT_TEXTS = ("black", "white", "categories", "move_header", "review_header")
_LABEL_NAMES = tuple(name for name in CommentLabels.__dataclass_fields__ if name not in _NOT_TEXTS)


def commentary_language() -> CommentaryLanguage:
    """Return the language of the AI commentary for the language of the screens used now.

    The Japanese prompt is used in Japanese; in every other language, the English prompt asks
    the AI to answer in that language. KentoGo's words in the SGF file follow the screens.
    """
    language = texts.language()
    prompt = PROMPT_JAPANESE if language == texts.SOURCE_LANGUAGE else PROMPT_ENGLISH
    return CommentaryLanguage(prompt, ANSWER_LANGUAGES[language], comment_labels(prompt))


def comment_labels(prompt: str) -> CommentLabels:
    """Return the words written into the SGF file with the AI's answer, in the language of the screens.

    Args:
        prompt: The language of the prompt (see commentary.language), which chooses the headers.
    """
    move_header, review_header = COMMENT_HEADERS[prompt]
    return CommentLabels(
        **{name: texts.template(f"comment_{name}") for name in _LABEL_NAMES},
        black=texts.text("black"),
        white=texts.text("white"),
        categories=tuple(texts.text(f"comment_category_{category}") for category in CATEGORIES),
        move_header=move_header,
        review_header=review_header,
    )


def color_label(color: str) -> str:
    """Return the name of a color, or "choose" for ""."""
    return texts.color_name(color) if color in ("B", "W") else texts.text("color_none")


def rank_label(rank: str) -> str:
    """Return a rank in the language of the screens, such as "18級" or "3段", or "not given" for ""."""
    rank = normalize_rank(rank)
    if not rank:
        return texts.text("rank_none")
    return texts.text("rank_kyu" if rank.endswith("k") else "rank_dan", number=int(rank[:-1]))


def relation_label(relation: str) -> str:
    """Return the rank of the opponent compared with the user, or "not given" for ""."""
    return texts.text(_RELATION_KEYS.get(relation, "relation_none"))


def answer_problems_text(problems: tuple[AnswerProblem, ...]) -> str:
    """Return one line for each problem of the AI's answer."""
    return "\n".join(f"・{_answer_problem(problem)}" for problem in problems)


def _answer_problem(problem: AnswerProblem) -> str:
    """Return the line of one problem of the AI's answer."""
    where = texts.text("answer_move", move=problem.move) if problem.move else texts.text("answer_summary")
    return texts.text(
        f"answer_problem_{problem.kind}", move=problem.move, field=problem.field, detail=problem.detail, where=where
    )


def prompt_file_problems_text(problems: list[PromptFileProblem]) -> str:
    """Return one line for each problem of the user's prompt file."""
    return "\n".join(
        texts.text(f"prompt_file_{p.kind}", path=p.path, section=p.section, detail=p.detail) for p in problems
    )


def written_text(result: WriteResult) -> str:
    """Return the message after the AI commentary was written into the SGF file."""
    return texts.text("commentary_written", moves=", ".join(map(str, result.moves)), backup=result.backup)


def provider_error_text(kind: str, detail: str, api_key_env: str) -> str:
    """Return the message for an AI that could not be asked (see commentary.provider_base.ProviderError).

    Args:
        kind: The kind of the error, one of the ERROR_ constants.
        detail: The message of the API ("" if none).
        api_key_env: The name of the environment variable of the API key (for ERROR_NO_KEY).
    """
    key = f"provider_error_{kind}"
    if key not in texts.TEXTS:
        key = f"provider_error_{ERROR_OTHER}"
    return texts.text(key, detail=detail or "-", env=api_key_env)


def tokens_text(generation: Generation) -> str:
    """Return the numbers of tokens of an answer, and a warning if it was cut at the largest length."""
    line = texts.text("commentary_tokens", input=generation.input_tokens, output=generation.output_tokens)
    return f"{line}\n{texts.text('commentary_truncated')}" if generation.truncated else line


def status_text(outcome: GameOutcome, api_key_env: str) -> str:
    """Return the short status of a game after the AI was asked (for the list of games)."""
    if outcome.status == STATUS_FAILED and outcome.error_kind:
        return provider_error_text(outcome.error_kind, outcome.detail, api_key_env)
    return texts.text(f"commentary_status_{outcome.status}", detail=outcome.detail)


def outcome_text(outcome: GameOutcome, api_key_env: str) -> str:
    """Return the whole message about a game: its status, what was written, the problems and the tokens."""
    lines = [status_text(outcome, api_key_env)]
    if outcome.status == STATUS_DONE and outcome.backup is not None:
        lines.append(texts.text("commentary_backup", backup=outcome.backup))
    problems = answer_problems_text(outcome.problems)
    if problems:
        lines.append(problems)
    if outcome.generation is not None:
        lines.append(tokens_text(outcome.generation))
    return "\n".join(lines)


def players_text(black: str, white: str, result: str) -> str:
    """Return the line about the players and the result of a game in the list."""
    return texts.text("commentary_players", black=black or "?", white=white or "?", result=result or "-")
