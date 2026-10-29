"""Make problems from a game: find the user's moves that lost many points.

The points lost are read from KaTrain's comments in the SGF file, so this
works without KataGo. When KaTrain also saved its analysis data (KT), the loss
of each candidate move in the problem position is kept too (see katrain_kt).

Problems are made from the moves of the real game (the main line). If the
setting include_undone_moves is on, problems are also made from the moves
that KaTrain took back automatically in a teaching game. These moves stay in
the file as short branches next to the main line.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace

from pysgf import GoNode

from kentogo.common import sgf
from kentogo.common.types import Move, Position, moves_from_gtp
from kentogo.mistakes.problem import Problem, Variation, problem_id_of
from kentogo.mistakes.selection import DECIDED_LEAD, DECIDED_WINRATE, MoveChoice, Selection, choose_moves
from kentogo.record.ai_comment import split_ai_comment
from kentogo.record.katrain_comment import KatrainMoveInfo, read_comment
from kentogo.record.katrain_kt import SUPPORTED_VERSION, candidate_losses, decode_kt, root_value
from kentogo.record.players import detect_my_color

# Reasons why no problem was made from a game.
REASON_UNKNOWN_COLOR = "unknown_color"  # The user's color was not found.
REASON_NO_ANALYSIS = "no_analysis"  # The game has neither KaTrain's comments nor its analysis data (KT).


@dataclass(frozen=True)
class ExtractSettings:
    """Conditions for choosing problems. They are kept in the "quiz" part of settings.json.

    Attributes:
        my_names: Names that the user uses, such as the user name on Fox Weiqi.
        problems_per_game: Maximum number of problems from one game.
            The moves that lost the most points are chosen.
        min_points_lost: Only moves that lost at least this many points become problems.
        skip_opening_moves: Moves up to this number are not used (0 means all moves are used).
        include_undone_moves: Also use moves that KaTrain took back in a teaching game.
        decided_winrate: A position where one side's winrate (in percent) is at least this is
            decided: its moves are used only when there are not enough other problems
            (see mistakes.selection, which the AI commentary uses too).
        decided_lead: A position where one side leads by more than this many points is decided.
    """

    my_names: tuple[str, ...] = ()
    problems_per_game: int = 5
    min_points_lost: float = 3.0
    skip_opening_moves: int = 0
    include_undone_moves: bool = False
    decided_winrate: float = DECIDED_WINRATE
    decided_lead: float = DECIDED_LEAD

    @classmethod
    def from_dict(cls, values: dict) -> ExtractSettings:
        """Make the settings from a dict read from settings.json.

        Args:
            values: The "quiz" part of the settings. Missing keys get the default values,
                and unknown keys are ignored.

        Returns:
            The settings.

        Raises:
            ValueError: If a value has a wrong type.
        """
        default = cls()
        include_undone_moves = values.get("include_undone_moves", default.include_undone_moves)
        if not isinstance(include_undone_moves, bool):
            raise ValueError(
                f"wrong quiz setting: include_undone_moves must be true or false: {include_undone_moves!r}"
            )
        try:
            return cls(
                my_names=tuple(str(name) for name in values.get("my_names", default.my_names)),
                problems_per_game=int(values.get("problems_per_game", default.problems_per_game)),
                min_points_lost=float(values.get("min_points_lost", default.min_points_lost)),
                skip_opening_moves=int(values.get("skip_opening_moves", default.skip_opening_moves)),
                include_undone_moves=include_undone_moves,
                decided_winrate=_percent(values.get("decided_winrate", default.decided_winrate)),
                decided_lead=float(values.get("decided_lead", default.decided_lead)),
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"wrong quiz setting: {error}") from error

    def to_dict(self) -> dict:
        """Return the settings as a dict that can be written to settings.json."""
        return {
            "my_names": list(self.my_names),
            "problems_per_game": self.problems_per_game,
            "min_points_lost": self.min_points_lost,
            "skip_opening_moves": self.skip_opening_moves,
            "include_undone_moves": self.include_undone_moves,
            "decided_winrate": self.decided_winrate,
            "decided_lead": self.decided_lead,
        }


def _percent(value: object) -> float:
    """Return a winrate in percent, from 50 to 100.

    Raises:
        ValueError: If it is not a number in that range.
    """
    number = float(value)
    if not 50 <= number <= 100:
        raise ValueError(f"decided_winrate must be from 50 to 100: {value!r}")
    return number


@dataclass(frozen=True)
class ExtractResult:
    """The problems made from one game.

    Attributes:
        my_color: The user's color, or None if it was not found.
        problems: The problems, from the largest loss to the smallest.
        reason: Why no problem was made (such as REASON_UNKNOWN_COLOR), or "" otherwise.
    """

    my_color: str | None
    problems: tuple[Problem, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class _Game:
    """Information about the game that every problem from it needs."""

    sgf_path: str
    start: Position  # The empty board with setup stones, komi and rules.
    my_color: str
    kt_version: str = SUPPORTED_VERSION  # The version of KaTrain's analysis data (the KTV property).


def extract_problems(root: GoNode, sgf_path: str, settings: ExtractSettings, recorded_color: str = "") -> ExtractResult:
    """Make problems from the user's moves that lost many points.

    If a taken-back move and a main line move are in the same position,
    only the main line move is used, because a problem is one position.

    Args:
        root: The root node of the game.
        sgf_path: Path of the SGF file, kept in each problem.
        settings: Conditions for choosing problems.
        recorded_color: The user's color that the user gave for this game ("B" or "W"), or "".

    Returns:
        The user's color and the problems.
    """
    my_color = detect_my_color(
        root.get_property("PB", ""),
        root.get_property("PW", ""),
        settings.my_names,
        ranks=(root.get_property("BR", ""), root.get_property("WR", "")),
        file_name=sgf_path,
        recorded_color=recorded_color,
    )
    if my_color is None:
        return ExtractResult(None, (), REASON_UNKNOWN_COLOR)
    start = Position(sgf.board_size(root), sgf.komi(root), sgf.rules(root), sgf.setup_stones(root), (), "B")
    game = _Game(sgf_path, start, my_color, str(root.get_property("KTV", SUPPORTED_VERSION)))
    main_line = sgf.main_line(root)
    if not _has_analysis(main_line):
        return ExtractResult(my_color, (), REASON_NO_ANALYSIS)

    problems: dict[str, tuple[Problem, bool]] = {}  # Each problem, and whether its game was decided.
    for node, before in _with_moves_before(main_line):
        made = _make_problem_from_node(game, node, before, settings)
        if made is not None:
            problems[made[0].problem_id] = made
    if settings.include_undone_moves:
        for node, before in _undone_moves(main_line):
            made = _make_problem_from_node(game, node, before, settings)
            if made is not None and made[0].problem_id not in problems:
                problems[made[0].problem_id] = made
    return ExtractResult(my_color, _choose(list(problems.values()), settings))


def _choose(problems: list[tuple[Problem, bool]], settings: ExtractSettings) -> tuple[Problem, ...]:
    """Choose the problems of a game as mistakes.selection says, the biggest losses first."""
    choices = [
        MoveChoice(index, problem.points_lost, problem.best_move.gtp() if problem.best_move else None, decided)
        for index, (problem, decided) in enumerate(problems)
    ]
    chosen = [problems[index][0] for index in choose_moves(choices, Selection.from_quiz(settings))]
    return tuple(sorted(chosen, key=lambda problem: (-problem.points_lost, problem.move_number)))


def _has_analysis(main_line: list[GoNode]) -> bool:
    """Return True if any move of the game has KaTrain's comment or KaTrain's analysis data (KT)."""
    for node in main_line[1:]:
        if node.get_property("KT") is not None:
            return True
        _, info = read_comment(node.get_property("C", ""))
        if info is not None:
            return True
    return False


def _with_moves_before(main_line: list[GoNode]) -> Iterator[tuple[GoNode, tuple[Move, ...]]]:
    """Yield each node of the main line after the root, with the moves played before it."""
    played: list[Move] = []
    for node in main_line[1:]:
        yield node, tuple(played)
        move = sgf.node_move(node)
        if move is not None:
            played.append(move)


def _undone_moves(main_line: list[GoNode]) -> Iterator[tuple[GoNode, tuple[Move, ...]]]:
    """Yield the moves that KaTrain took back, with the moves played before them.

    A taken-back move is a branch next to a main line node, and its comment says
    that it was taken back. Other branches (moves tried by the user) are not used.
    """
    on_main_line = {id(node) for node in main_line}
    for node, before in _with_moves_before(main_line):
        for sibling in node.parent.children:
            if id(sibling) in on_main_line:
                continue
            _, info = read_comment(sibling.get_property("C", ""))
            if info is not None and info.teaching_undo:
                yield sibling, before


def _make_problem_from_node(
    game: _Game, node: GoNode, before: tuple[Move, ...], settings: ExtractSettings
) -> tuple[Problem, bool] | None:
    """Make a problem from a node if its move is one of the user's big mistakes.

    Args:
        game: Information about the game.
        node: A node with a move.
        before: The moves played before the node.
        settings: Conditions for choosing problems.

    Returns:
        The problem and whether the game was decided before the move, or None if the move
        should not be a problem.
    """
    move = sgf.node_move(node)
    if move is None or move.color != game.my_color:
        return None
    ai = split_ai_comment(str(node.get_property("C", "")))
    notes, info = read_comment(ai.rest)
    number = len(before) + 1
    if not _is_problem(move, info, number, settings):
        return None
    start = game.start
    position = Position(start.size, start.komi, start.rules, start.setup, before, move.color)
    problem = _make_problem(position, game.sgf_path, number, move, info, notes)
    losses = _candidate_losses(node.parent, move.color, game.kt_version)
    winrate, lead = _position_value(node.parent, game.kt_version)
    decided = Selection.from_quiz(settings).is_decided(winrate, lead)
    return replace(problem, candidate_losses=losses, ai_comment=ai.move_text), decided


def _is_problem(move: Move, info: KatrainMoveInfo | None, number: int, settings: ExtractSettings) -> bool:
    """Return True if the user's move is a mistake that should become a problem.

    Args:
        move: The user's move.
        info: KaTrain's evaluation of the move, or None if there is none.
        number: The number of the move in the game.
        settings: Conditions for choosing problems.
    """
    if info is None or info.points_lost is None:
        return False
    elif (info.color, info.move) != (move.color, move.gtp()):
        return False  # The comment is not about this move, so it cannot be trusted.
    elif number <= settings.skip_opening_moves:
        return False
    else:
        return info.points_lost >= settings.min_points_lost


def _position_value(parent: GoNode | None, version: str) -> tuple[float | None, float | None]:
    """Return black's winrate and score lead before a move, from the analysis data of the node before it."""
    values = parent.get_list_property("KT") if parent is not None else None
    if not values:
        return None, None
    try:
        return root_value(decode_kt(values, version))
    except ValueError:
        return None, None


def _candidate_losses(parent: GoNode | None, color: str, version: str) -> tuple[tuple[str, float], ...]:
    """Return the losses of the candidate moves from the analysis data of the node before the move.

    A broken or too new analysis is ignored, because the problem works without it.
    """
    values = parent.get_list_property("KT") if parent is not None else None
    if not values:
        return ()
    try:
        losses = candidate_losses(decode_kt(values, version), color)
    except ValueError:
        return ()
    return tuple(sorted(losses.items()))


def _make_problem(
    position: Position, sgf_path: str, number: int, move: Move, info: KatrainMoveInfo, notes: str
) -> Problem:
    """Make a problem from a mistake and KaTrain's evaluation of it.

    Args:
        position: The position just before the mistake.
        sgf_path: Path of the SGF file.
        number: The number of the mistake in the game.
        move: The mistake.
        info: KaTrain's evaluation of the mistake.
        notes: The user's notes on the mistake.

    Returns:
        The problem.
    """
    best_move = Move.from_gtp(info.best_move, move.color) if info.best_move else None
    variations = ()
    if info.pv:
        variations = (Variation(moves_from_gtp(info.pv, info.pv_color), "katrain"),)
    return Problem(
        problem_id=problem_id_of(position),
        sgf_path=sgf_path,
        move_number=number,
        position=position,
        actual_move=move,
        best_move=best_move,
        points_lost=info.points_lost,
        variations=variations,
        notes=notes,
    )
