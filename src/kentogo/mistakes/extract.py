"""Make problems from a game: find the user's moves that lost many points.

The points lost are read from the SGF file, so this works without KataGo. When KaTrain
saved its analysis data (KT) on the move and on the node before it, the loss, the best move
and its sequence come from that data, which does not depend on KaTrain's language or wording
(see record.katrain_kt). Otherwise they are read from KaTrain's comments. The loss of each
candidate move in the problem position is kept too when the node before has analysis data.
In games analyzed in KentoGo's own mode (KGM[KentoGo] at the root), the losses are read in the
position before each move, from the best move (see record.katrain_kt.played_move_loss).

Problems are made from the moves of the real game (the main line). If the
setting include_undone_moves is on, problems are also made from the moves
that KaTrain took back automatically in a teaching game. These moves stay in
the file as short branches next to the main line.

A problem right after the opponent's big mistake is a punishment problem (see PunishmentChance),
unless the opponent only left the same point again: when the opponent's best move was already its
best move at its turn before, the loss was not made by this move. The punishment problems that are
not among the problems of a game (it has only problems_per_game of them) are kept apart
(ExtractResult.punishments), for the quiz that asks only punishment problems (see quiz.problem_kinds).

Whether the game was already decided is read from the analysis data of the position before the move
(before the opponent's mistake for a punishment problem). In a game with handicap stones, only the lead
gained since the start counts, not the winrate (see common.handicap).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace

from pysgf import GoNode

from kentogo.common import sgf
from kentogo.common.handicap import from_start
from kentogo.common.types import Move, Position, moves_from_gtp
from kentogo.mistakes.problem import Problem, Variation, problem_id_of
from kentogo.mistakes.selection import (
    DECIDED_LEAD,
    DECIDED_WINRATE,
    MoveChoice,
    Selection,
    choose_moves,
    choose_open_moves,
)
from kentogo.record.ai_comment import split_ai_comment
from kentogo.record.katrain_comment import KatrainMoveInfo, read_comment
from kentogo.record.katrain_kt import (
    KENTOGO_MODE,
    KENTOGO_MODE_PROPERTY,
    SUPPORTED_VERSION,
    KtEvaluation,
    candidate_losses,
    decode_kt,
    evaluate_katrain_move,
    evaluate_played_move,
    relative_candidate_losses,
    root_value,
)
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
        loss_stages: The thresholds of the staged problems, the biggest first (see quiz.stages),
            or () if they are not used. With stages, every open mistake that lost at least the
            smallest threshold becomes a problem (problems_per_game and min_points_lost are not used).
        punish_opponent_loss: A problem is a punishment problem (see PunishmentChance) when the
            opponent's move just before it lost at least this many points...
        punish_my_loss: ...and the user's move lost at least this many points.
    """

    my_names: tuple[str, ...] = ()
    problems_per_game: int = 5
    min_points_lost: float = 3.0
    skip_opening_moves: int = 0
    include_undone_moves: bool = False
    decided_winrate: float = DECIDED_WINRATE
    decided_lead: float = DECIDED_LEAD
    loss_stages: tuple[float, ...] = ()
    punish_opponent_loss: float = 15.0
    punish_my_loss: float = 5.0

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
                loss_stages=_stages(values.get("loss_stages", default.loss_stages)),
                punish_opponent_loss=float(values.get("punish_opponent_loss", default.punish_opponent_loss)),
                punish_my_loss=float(values.get("punish_my_loss", default.punish_my_loss)),
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
            "loss_stages": list(self.loss_stages),
            "punish_opponent_loss": self.punish_opponent_loss,
            "punish_my_loss": self.punish_my_loss,
        }

    def smallest_loss(self) -> float:
        """Return the smallest loss of a problem: the last stage, or min_points_lost without stages."""
        return self.loss_stages[-1] if self.loss_stages else self.min_points_lost


def _stages(value: object) -> tuple[float, ...]:
    """Return the thresholds of the staged problems from a list of numbers, the biggest first, without repeats.

    Raises:
        ValueError: If it is not a list, or a value is not a positive number.
    """
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"loss_stages must be a list of numbers: {value!r}")
    stages = {float(number) for number in value}
    if any(not stage > 0 for stage in stages):
        raise ValueError(f"loss_stages must be positive numbers: {value!r}")
    return tuple(sorted(stages, reverse=True))


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
        move_losses: The points lost by each of the user's moves of the main line whose loss is
            known, in the order played (also the moves that are not problems: they are counted
            in the report, see kentogo.report).
        punishments: The punishment problems (PUNISH) that are not among the problems, in open positions,
            in the order played: the quiz of punishment problems asks them too.
    """

    my_color: str | None
    problems: tuple[Problem, ...] = ()
    reason: str = ""
    move_losses: tuple[float, ...] = ()
    punishments: tuple[Problem, ...] = ()


@dataclass(frozen=True)
class _Game:
    """Information about the game that every problem from it needs."""

    sgf_path: str
    start: Position  # The empty board with setup stones, komi and rules.
    my_color: str
    kt_version: str = SUPPORTED_VERSION  # The version of KaTrain's analysis data (the KTV property).
    # How a move and the candidates are evaluated from the analysis data: KaTrain's way, or KentoGo's (KGM).
    evaluate: Callable[[dict, dict, str, str], KtEvaluation | None] = evaluate_katrain_move
    candidate_losses: Callable[[dict, str], dict[str, float]] = candidate_losses
    start_lead: float | None = None  # Black's score lead before the first move (for handicap games).


def _game(root: GoNode, sgf_path: str, start: Position, my_color: str) -> _Game:
    """Return the information about the game, with the evaluation of the mode that analyzed it."""
    version = str(root.get_property("KTV", SUPPORTED_VERSION))
    start_lead = _position_value(root, version)[1]
    if root.get_property(KENTOGO_MODE_PROPERTY, "") == KENTOGO_MODE:
        return _Game(sgf_path, start, my_color, version, evaluate_played_move, relative_candidate_losses, start_lead)
    return _Game(sgf_path, start, my_color, version, start_lead=start_lead)


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
    my_color = _my_color(root, sgf_path, settings, recorded_color)
    if my_color is None:
        return ExtractResult(None, (), REASON_UNKNOWN_COLOR)
    start = Position(sgf.board_size(root), sgf.komi(root), sgf.rules(root), sgf.setup_stones(root), (), "B")
    game = _game(root, sgf_path, start, my_color)
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
    losses = _move_losses(main_line, game)
    chosen = _choose(list(problems.values()), settings)
    return ExtractResult(my_color, chosen, move_losses=losses, punishments=_other_punishments(problems, chosen))


def _other_punishments(problems: dict[str, tuple[Problem, bool]], chosen: tuple[Problem, ...]) -> tuple[Problem, ...]:
    """Return the punishment problems in open positions that were not chosen, in the order played."""
    taken = {problem.problem_id for problem in chosen}
    others = [
        problem
        for problem, decided in problems.values()
        if problem.punishment == PUNISH and not decided and problem.problem_id not in taken
    ]
    return tuple(sorted(others, key=lambda problem: problem.move_number))


def _my_color(root: GoNode, sgf_path: str, settings: ExtractSettings, recorded_color: str) -> str | None:
    """Return the user's color in a game, or None when it cannot be found (see record.players)."""
    return detect_my_color(
        root.get_property("PB", ""),
        root.get_property("PW", ""),
        settings.my_names,
        ranks=(root.get_property("BR", ""), root.get_property("WR", "")),
        file_name=sgf_path,
        recorded_color=recorded_color,
    )


def _move_losses(main_line: list[GoNode], game: _Game) -> tuple[float, ...]:
    """Return the points lost by each of the user's moves of the main line whose loss is known (0.1 points)."""
    losses = []
    for node in main_line[1:]:
        move = sgf.node_move(node)
        if move is None or move.color != game.my_color:
            continue
        info = _evaluated(node, move, game)
        if info is not None and info.points_lost is not None:
            losses.append(round(info.points_lost, 1))
    return tuple(losses)


def _evaluated(node: GoNode, move: Move, game: _Game) -> KatrainMoveInfo | None:
    """Return the evaluation of a node's move (analysis data first, then KaTrain's comment), or None."""
    _, info = read_comment(split_ai_comment(str(node.get_property("C", ""))).rest)
    info = _with_analysis_data(info, node, move, game)
    return info if info is not None and (info.color, info.move) == (move.color, move.gtp()) else None


PUNISH = "punish"  # The opponent's mistake made a new chance: the user's best move is not the opponent's.
SHARED = "shared"  # Both missed the same point: the user's best move is the one the opponent should have played.


@dataclass(frozen=True)
class PunishmentChance:
    """A moment when the opponent made a big mistake and the user did not punish it.

    Attributes:
        move_number: The number of the user's move.
        opponent_move: The opponent's mistake just before it.
        opponent_loss: The points that the opponent's move lost.
        my_move: The user's move.
        my_loss: The points that the user's move lost (the chance it gave back).
        best_move: The best move in the position (the move that punishes), GTP, or None if unknown.
        opponent_best: The best move in the position before the opponent's mistake, GTP, or None if unknown.
        decided: The position before the opponent's mistake was decided (the same rule as the problems, see
            mistakes.selection; the mistake itself makes the lead bigger, so the position after it is not used).
    """

    move_number: int
    opponent_move: Move
    opponent_loss: float
    my_move: Move
    my_loss: float
    best_move: str | None
    opponent_best: str | None = None
    decided: bool = False

    @property
    def kind(self) -> str:
        """Return SHARED when both missed the same best move, otherwise PUNISH."""
        return punishment_kind(self.best_move, self.opponent_best)


def punishment_chances(
    root: GoNode,
    sgf_path: str,
    settings: ExtractSettings,
    opponent_loss: float,
    my_loss: float,
    recorded_color: str = "",
) -> list[PunishmentChance]:
    """Find the opponent's big mistakes that the user did not punish, in the main line of a game.

    A chance is the user's move right after an opponent's move that lost at least opponent_loss points,
    when the user's move lost at least my_loss points. Moves that are not problems count too
    (decided positions are marked, see PunishmentChance.decided), but a best move counts only once
    in a game: when both players keep missing the same point, only the first moment is kept.

    Args:
        root: The root node of the game.
        sgf_path: Path of the SGF file (used to find the user's color).
        settings: The quiz's conditions (the user's names).
        opponent_loss: The smallest loss of the opponent's move.
        my_loss: The smallest loss of the user's move.
        recorded_color: The user's color that the user gave for this game ("B" or "W"), or "".

    Returns:
        The chances in the order of the game (none when the user's color is not known).
    """
    my_color = _my_color(root, sgf_path, settings, recorded_color)
    if my_color is None:
        return []
    start = Position(sgf.board_size(root), sgf.komi(root), sgf.rules(root), sgf.setup_stones(root), (), "B")
    game = _game(root, sgf_path, start, my_color)
    main_line = sgf.main_line(root)
    chances = []
    for previous, node in zip(main_line[1:], main_line[2:], strict=False):
        chance = _chance(game, previous, node, settings)
        if chance is not None and chance.opponent_loss >= opponent_loss and chance.my_loss >= my_loss:
            chances.append(chance)
    return first_of_each_best_move(chances)


def first_of_each_best_move(chances: list[PunishmentChance]) -> list[PunishmentChance]:
    """Keep only the first chance of each best move (an unknown best move is always kept)."""
    seen: set[str] = set()
    kept = []
    for chance in chances:
        if chance.best_move is not None and chance.best_move in seen:
            continue
        if chance.best_move is not None:
            seen.add(chance.best_move)
        kept.append(chance)
    return kept


def _chance(game: _Game, previous: GoNode, node: GoNode, settings: ExtractSettings) -> PunishmentChance | None:
    """Return the opponent's move and the user's move after it with their losses, or None when not known."""
    theirs, mine = sgf.node_move(previous), sgf.node_move(node)
    if theirs is None or mine is None or mine.color != game.my_color or theirs.color == game.my_color:
        return None
    their_info, my_info = _evaluated(previous, theirs, game), _evaluated(node, mine, game)
    if their_info is None or my_info is None or their_info.points_lost is None or my_info.points_lost is None:
        return None
    if _left_again(previous, their_info.best_move, game):
        return None
    decided = _is_decided(previous.parent, game, settings)  # Before the opponent's mistake.
    return PunishmentChance(
        node.depth,
        theirs,
        their_info.points_lost,
        mine,
        my_info.points_lost,
        my_info.best_move,
        their_info.best_move,
        decided,
    )


def _choose(problems: list[tuple[Problem, bool]], settings: ExtractSettings) -> tuple[Problem, ...]:
    """Choose the problems of a game as mistakes.selection says, the biggest losses first."""
    choices = [
        MoveChoice(index, problem.points_lost, problem.best_move.gtp() if problem.best_move else None, decided)
        for index, (problem, decided) in enumerate(problems)
    ]
    selection = Selection.from_quiz(settings)
    if settings.loss_stages:
        numbers = choose_open_moves(choices, replace(selection, min_loss=settings.smallest_loss()))
    else:
        numbers = choose_moves(choices, selection)
    chosen = [problems[index][0] for index in numbers]
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
    info = _with_analysis_data(info, node, move, game)
    number = len(before) + 1
    if not _is_problem(move, info, number, settings):
        return None
    start = game.start
    position = Position(start.size, start.komi, start.rules, start.setup, before, move.color)
    problem = _make_problem(position, game.sgf_path, number, move, info, notes)
    losses = _candidate_losses(node.parent, move.color, game)
    problem = replace(problem, candidate_losses=losses, ai_comment=ai.move_text)
    problem = _with_opponent_move(problem, node, game, settings)
    # A punishment problem is decided by the position before the opponent's mistake, as the mistake itself
    # makes the lead much bigger.
    before = node.parent.parent if problem.punishment and node.parent is not None else node.parent
    return problem, _is_decided(before, game, settings)


def _with_opponent_move(problem: Problem, node: GoNode, game: _Game, settings: ExtractSettings) -> Problem:
    """Add the opponent's move just before the problem: its loss, its best move, and the kind of punishment."""
    previous = node.parent
    theirs = sgf.node_move(previous) if previous is not None else None
    if theirs is None or theirs.color == game.my_color:
        return problem
    info = _evaluated(previous, theirs, game)
    if info is None or info.points_lost is None:
        return problem
    best = problem.best_move.gtp() if problem.best_move is not None else None
    big = info.points_lost >= settings.punish_opponent_loss and problem.points_lost >= settings.punish_my_loss
    kind = punishment_kind(best, info.best_move) if big and not _left_again(previous, info.best_move, game) else ""
    return replace(problem, opponent_loss=info.points_lost, opponent_best=info.best_move, punishment=kind)


def _left_again(node: GoNode, best_move: str | None, game: _Game) -> bool:
    """True if the opponent's best move before its move at a node was already its best move at its turn before.

    The opponent then only left the same point again: the loss of its move was not made by that move.
    """
    if best_move is None or node.parent is None or node.parent.parent is None:
        return False
    before = node.parent.parent
    move = sgf.node_move(before)
    if move is None or move.color == game.my_color:
        return False
    info = _evaluated(before, move, game)
    return info is not None and info.best_move == best_move


def punishment_kind(best_move: str | None, opponent_best: str | None) -> str:
    """Return SHARED when the user's best move is the one the opponent should have played, otherwise PUNISH."""
    return SHARED if best_move is not None and best_move == opponent_best else PUNISH


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
        return info.points_lost >= settings.smallest_loss()


def _analysis(node: GoNode | None, version: str) -> dict | None:
    """Return KaTrain's analysis data of a node, or None if it has none.

    Broken or too new data counts as none, because the problem works without it.
    """
    values = node.get_list_property("KT") if node is not None else None
    if not values:
        return None
    try:
        return decode_kt(values, version)
    except ValueError:
        return None


def _with_analysis_data(info: KatrainMoveInfo | None, node: GoNode, move: Move, game: _Game) -> KatrainMoveInfo | None:
    """Take the loss, the best move and its sequence from the analysis data of the move and of the node before it.

    Without analysis data on both nodes, KaTrain's comment (info) is used as it is.
    """
    before, after = _analysis(node.parent, game.kt_version), _analysis(node, game.kt_version)
    has_both = before is not None and after is not None
    evaluation = game.evaluate(before, after, move.color, move.gtp()) if has_both else None
    if evaluation is None:
        return info
    base = info if info is not None and (info.color, info.move) == (move.color, move.gtp()) else _empty_info(move)
    return replace(
        base,
        points_lost=evaluation.points_lost,
        best_move=evaluation.best_move or base.best_move,
        pv=evaluation.pv or base.pv,
        pv_color=move.color if evaluation.pv else base.pv_color,
    )


def _empty_info(move: Move) -> KatrainMoveInfo:
    """Return an evaluation of a move with nothing known yet (for a move with analysis data but no comment)."""
    return KatrainMoveInfo("", 0, move.color, move.gtp(), None, None, None, (), False)


def _is_decided(parent: GoNode | None, game: _Game, settings: ExtractSettings) -> bool:
    """True if the game was already decided before a move (from the analysis data of the node before it).

    In a game with handicap stones, only the lead gained since the start counts (see common.handicap).
    """
    winrate, lead = _position_value(parent, game.kt_version)
    if game.start.setup:
        winrate, lead = from_start(winrate, lead, game.start_lead)
    return Selection.from_quiz(settings).is_decided(winrate, lead)


def _position_value(parent: GoNode | None, version: str) -> tuple[float | None, float | None]:
    """Return black's winrate and score lead before a move, from the analysis data of the node before it."""
    analysis = _analysis(parent, version)
    return root_value(analysis) if analysis is not None else (None, None)


def _candidate_losses(parent: GoNode | None, color: str, game: _Game) -> tuple[tuple[str, float], ...]:
    """Return the losses of the candidate moves from the analysis data of the node before the move."""
    analysis = _analysis(parent, game.kt_version)
    return tuple(sorted(game.candidate_losses(analysis, color).items())) if analysis is not None else ()


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
