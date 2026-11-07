"""The sequences after a move read deeply until the place settles (段階4: 一段落までの手順).

For each deep node (see analysis.analyze), two lines are read from the position before the move:
the played move ("played_line") and KataGo's best move ("best_line"), each followed by KataGo's
sequence. The line is played on a few moves at a time (LineSettings.step), and the position is read
each time with its areas (ownership), until the place has settled:

- KataGo's next move is away from that place (more than LineSettings.radius points from the first
  move, or a pass): the players would leave it there. A move of KataGo's sequence that is away from
  the place ends the line before it, in the same way; or
- the areas around the first move change by less than LineSettings.change on average since the last
  reading (0 does not use this: KataGo's areas already expect the sequence, so in real games they
  hardly change even while the fight goes on).

A line that does not settle stops at LineSettings.max_moves. The first reading of each line is the one
already made: the deep reading of the played move's position, and the tenuki reading "best_after". Whether the place settles is not decided
by the score (passing in the middle game always costs about one move's value, see kentogo_reading).

What is kept of a line (see record.kentogo_data): its moves (GTP points, from the first move), whether
it settled, the score, win rate and visits at each reading, and the areas at its end, where it settled.
The areas just after the move are already elsewhere (the KT of the move's node, and "best_after").
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pysgf import GoNode
from pysgf import Move as SgfMove

from kentogo.analysis.game_analysis import Engine, GameAnalysis, NodeStep, Progress, analyze_with_retries
from kentogo.analysis.kentogo_reading import PASS, best_move
from kentogo.analysis.query import QuerySettings, query_after
from kentogo.vendor.katrain_analysis import var_to_grid

LINES_STEP = "lines"  # The name of these readings in the progress.
PLAYED_LINE = "played_line"
BEST_LINE = "best_line"


@dataclass(frozen=True)
class LineSettings:
    """When a line has settled (the analysis settings settle_radius, settle_change, settle_step and settle_max_moves).

    Attributes:
        radius: The place of a move: the points within this distance (in rows and columns) of it.
        change: The place has settled when its areas change by less than this on average (0 to 2 per point).
        step: How many moves are played on between two readings.
        max_moves: The longest line, in moves from the first one.
    """

    radius: int
    change: float
    step: int
    max_moves: int


@dataclass
class _Line:
    """A line that is being read."""

    node: GoNode
    moves: list[tuple[str, str]]  # (player, GTP point), from the first move.
    length: int = 1  # How many of the moves are played in the position read next.
    places: list[tuple[int, int]] = field(default_factory=list)  # The points around the first move.
    last_areas: list[float] | None = None
    steps: list[dict] = field(default_factory=list)
    end: dict | None = None
    settled: bool = False
    done: bool = False
    leaving: bool = False  # The next move of the sequence leaves the place: the position read next is the end.


def read_lines(
    engine: Engine,
    game: GameAnalysis,
    visits: int,
    wide_root_noise: float,
    priority: int,
    progress: Progress,
    retries: int,
    settings: LineSettings,
) -> None:
    """Read the played line and the best line of every deep node, and keep them in game.readings."""
    query_settings = QuerySettings(visits, wide_root_noise, priority)
    lines = {
        name: {id(node): line for node in game.deep_nodes if (line := _start(game, node, name, settings))}
        for name in (PLAYED_LINE, BEST_LINE)
    }
    total = sum(len(found) for found in lines.values())
    for name, found in lines.items():
        for line in found.values():
            first = _first_answer(game, line.node, name)
            if first is not None:
                _next(line, first, settings)
    while any(not line.done for found in lines.values() for line in found.values()):
        for name, found in lines.items():
            step = NodeStep(_query(found, query_settings), _keep(found, settings))
            nodes = [line.node for line in found.values() if not line.done]
            finished = sum(line.done for found_ in lines.values() for line in found_.values())
            analyze_with_retries(
                engine, game, nodes, step, lambda _done, _all: progress(LINES_STEP, finished, total), retries
            )
            for node in game.failed_nodes:  # A line that KataGo could not read stops where it is.
                if id(node) in found:
                    found[id(node)].done = True
        progress(LINES_STEP, sum(line.done for found in lines.values() for line in found.values()), total)
    for name, found in lines.items():
        for line in found.values():
            game.readings.setdefault(id(line.node), {})[name] = _kept(line)


def _start(game: GameAnalysis, node: GoNode, name: str, settings: LineSettings) -> _Line | None:
    """Return a new line of a deep node: its first move and KataGo's sequence after it, or None."""
    player = node.move.player
    if name == PLAYED_LINE:
        first = node.move.gtp()
        after = game.analysis(node)
        top = _top(after) if after is not None else None
        sequence = [first, *(top.get("pv", []) if top else [])]
    else:
        first = best_move(game, node)
        if first is None or first == PASS:
            return None
        values = game.analysis(node.parent)["moves"].get(first, {})
        sequence = values.get("pv") or [first]
    size = node.board_size
    line = _Line(node, _with_players(sequence, player))
    line.places = _places(first, size, settings.radius)
    return line


def _query(lines: dict[int, _Line], settings: QuerySettings):
    def query(node: GoNode) -> dict | None:
        line = lines[id(node)]
        found = query_after(node.parent, settings, line.moves[: line.length])
        if found is None:  # KaTrain's way does not analyze this position (stones removed): the line stops.
            line.done = True
        return found

    return query


def _keep(lines: dict[int, _Line], settings: LineSettings):
    def keep(game: GameAnalysis, node: GoNode, answer: dict) -> None:
        _next(lines[id(node)], answer, settings)

    return keep


def _next(line: _Line, answer: dict, settings: LineSettings) -> None:
    """Take the answer of the position at the end of the line: keep it, and see whether the line goes on."""
    root = answer["rootInfo"]
    line.steps.append(
        {"length": line.length, **{key: root[key] for key in ("scoreLead", "winrate", "visits") if key in root}}
    )
    size = line.node.board_size
    areas = _areas(answer.get("ownership"), size, line.places)
    line.end = {**line.steps[-1], "ownership": answer.get("ownership")}
    if line.leaving:
        line.settled = line.done = True
        return
    top = _top_of_answer(answer)
    if settings.change > 0 and line.last_areas is not None and areas is not None:
        change = sum(abs(a - b) for a, b in zip(areas, line.last_areas, strict=True)) / max(1, len(areas))
        if change < settings.change:
            line.settled = line.done = True
            return
    if top is None or top["move"] == PASS or not _near(top["move"], line.places, size):
        line.settled = line.done = True  # The players would leave the place.
        return
    if line.length >= settings.max_moves:
        line.done = True
        return
    line.last_areas = areas
    wanted = min(line.length + settings.step, settings.max_moves)
    if len(line.moves) < wanted:  # KataGo's sequence is shorter: go on with its sequence from here.
        next_player = "W" if line.moves[line.length - 1][0] == "B" else "B"
        line.moves = line.moves[: line.length] + _with_players(top.get("pv", [top["move"]]), next_player)
    wanted = min(wanted, len(line.moves))
    for index in range(line.length, wanted):
        point = line.moves[index][1]
        if point == PASS or not _near(point, line.places, size):  # The sequence leaves the place here.
            if index == line.length:
                line.settled = line.done = True
                return
            wanted, line.leaving = index, True
            break
    line.length = wanted


def _first_answer(game: GameAnalysis, node: GoNode, name: str) -> dict | None:
    """Return the reading already made of the position after the first move of a line, as KataGo's answer."""
    if name == PLAYED_LINE:
        analysis = game.analysis(node)
        if analysis is None or not analysis.get("ownership"):
            return None
        infos = sorted(analysis["moves"].values(), key=lambda values: values.get("order", 999))
        return {"rootInfo": analysis["root"], "moveInfos": infos, "ownership": analysis["ownership"]}
    reading = game.readings.get(id(node), {}).get("best_after")
    if reading is None or not reading.get("ownership"):
        return None
    root = {key: reading[key] for key in ("scoreLead", "winrate", "visits") if key in reading}
    infos = [{"move": reading["next"], "order": 0, "pv": reading.get("pv", [])}] if "next" in reading else []
    return {"rootInfo": root, "moveInfos": infos, "ownership": reading["ownership"]}


def _kept(line: _Line) -> dict:
    """Return what is kept of a line (see the module's docstring)."""
    kept = {"moves": [point for _, point in line.moves[: line.length]], "settled": line.settled, "steps": line.steps}
    if line.end is not None:
        kept["end"] = {key: value for key, value in line.end.items() if value is not None}
    return kept


def _with_players(points: list[str], first_player: str) -> list[tuple[str, str]]:
    """Return the moves of a sequence with their players, the first one played by first_player."""
    players = (first_player, "W" if first_player == "B" else "B")
    return [(players[index % 2], point) for index, point in enumerate(points)]


def _places(point: str, size: tuple[int, int], radius: int) -> list[tuple[int, int]]:
    """Return the points within radius of a point (in rows and columns), on the board."""
    x, y = SgfMove.from_gtp(point).coords
    return [
        (column, row)
        for column in range(max(0, x - radius), min(size[0], x + radius + 1))
        for row in range(max(0, y - radius), min(size[1], y + radius + 1))
    ]


def _near(point: str, places: list[tuple[int, int]], size: tuple[int, int]) -> bool:
    coords = SgfMove.from_gtp(point).coords
    return coords is not None and tuple(coords) in set(places)


def _areas(ownership: list[float] | None, size: tuple[int, int], places: list[tuple[int, int]]) -> list[float] | None:
    """Return the areas (ownership) of the place, or None without them."""
    if not ownership:
        return None
    grid = var_to_grid(ownership, size)
    return [grid[y][x] for x, y in places]


def _top(analysis: dict) -> dict | None:
    return next((values for values in analysis["moves"].values() if values.get("order") == 0), None)


def _top_of_answer(answer: dict) -> dict | None:
    return next((info for info in answer.get("moveInfos", []) if info.get("order") == 0), None)
