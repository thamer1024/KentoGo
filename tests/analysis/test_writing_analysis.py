"""Tests for kentogo.analysis.sgf_writer and saving (writing the analysis into the SGF file: KentoGo's KGA, KaTrain-style comments)."""

from datetime import datetime

from pysgf import GoGame

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.analysis.analyze import DeepTargets, analyze_game
from kentogo.analysis.game_analysis import EngineValues
from kentogo.analysis.saving import back_up, backup_folder, write_game
from kentogo.analysis.sgf_writer import WriteSettings, kept_analysis, kept_problem_analysis, write_analysis
from kentogo.mistakes.extract import ExtractSettings, extract_problems
from kentogo.record.game_record import read_game_record
from kentogo.record.katrain_comment import INTERNAL_MARKER, SEPARATOR, read_comment
from kentogo.record.katrain_kt import encode_kt
from kentogo.record.kentogo_analysis import read_kentogo_analysis
from kentogo.record.kentogo_comment import KENTOGO_HEADER, split_kentogo_comment

HUMAN = f"Human (Normal Game){INTERNAL_MARKER}"
AI = f"AI (Human-like){INTERNAL_MARKER}"
OLD = f"\nMove 3: B A5\nOld text\nMove was automatically undone in teaching mode.\n{INTERNAL_MARKER}"
# Black (the user) plays C3, then A5 losing 8 points; the move has the user's note and KaTrain's old text.
GAME = f"(;SZ[5]KM[0.5]PB[{HUMAN}]PW[{AI}]C[game note];B[cc];W[bb];B[aa]C[my note{SEPARATOR}{OLD}])"
SCORES = {0: 0.0, 1: 1.0, 2: 3.0, 3: -5.0}  # White loses 2 points, black then 8.


class FakeEngine:
    """Answers at once, with a score that depends on the number of moves."""

    def query(self, request, callback):
        allowed = request.get("allowMoves")
        point = allowed[0]["moves"][0] if allowed else "E5"
        score = SCORES.get(len(request["moves"]) + (1 if allowed else 0), SCORES[3])  # Longer: KentoGo's readings.
        best = {"move": point, "order": 0, "visits": 9, "scoreLead": score, "winrate": 0.5, "pv": [point]}
        root = {"scoreLead": score, "winrate": 0.4 if score < 0 else 0.6, "visits": 9}
        callback({"id": "q", "rootInfo": root, "moveInfos": [best], "policy": [0.04] * 26, "ownership": [0.1] * 25})
        return "q"


def analyzed(settings: AnalysisSettings = AnalysisSettings()) -> object:
    root = GoGame.parse_sgf(GAME)
    game = analyze_game(FakeEngine(), root, settings, EngineValues(100, 0.0), lambda *_: None)
    write_analysis(game, WriteSettings("1.2.3"))
    return GoGame.parse_sgf(root.sgf())  # Written and read back.


def test_root_properties_and_comment():
    """The root gets AP, CA and KGM; its comment keeps only the user's note (KentoGo writes none)."""
    root = analyzed()
    assert (root.get_property("AP"), root.get_property("CA"), root.get_property("KTV")) == (
        "KentoGo:1.2.3",
        "UTF-8",
        None,
    )
    assert root.get_property("C") == "game note"


def test_every_node_gets_kentogos_own_analysis_data():
    """Each node gets KGA, not KaTrain's KT; the positions that cannot become problems keep no areas."""
    root = analyzed()
    for node in root.nodes_in_tree:
        assert read_kentogo_analysis(node)["completed"] is True and node.get_property("KT") is None
    assert read_kentogo_analysis(root.nodes_in_tree[1])["ownership"] is None


def test_katrains_own_kt_stays_and_an_older_kentogos_kt_is_removed():
    """KaTrain's KT (no KGM) is left as it is; the KT and KTV of an older KentoGo (KGM, no KGA) are removed."""
    kt = "KT[" + "][".join(encode_kt({"root": {"scoreLead": 9.0}, "moves": {}, "completed": True})) + "]"
    for mark, kept in (("", True), ("KGM[KentoGo]KTV[1.0]", False)):
        root = GoGame.parse_sgf(GAME.replace(";B[cc]", f";B[cc]{kt}", 1).replace("(;", f"(;{mark}", 1))
        game = analyze_game(FakeEngine(), root, AnalysisSettings(), EngineValues(100, 0.0), lambda *_: None)
        write_analysis(game, WriteSettings("1.2.3"))
        written = GoGame.parse_sgf(root.sgf())
        assert (written.nodes_in_tree[1].get_property("KT") is not None) == kept
        assert written.get_property("KTV") is None and read_kentogo_analysis(written.nodes_in_tree[1]) is not None


def test_comment_with_notes_and_katrains_text_kept():
    """The note stays at the top and KaTrain's own text stays; KentoGo adds nothing, and the move is taken back."""
    mistake = analyzed().nodes_in_tree[3]
    comment = mistake.get_property("C")
    notes, info = read_comment(comment)
    assert notes == "my note" and "Old text" in comment and info.teaching_undo
    assert split_kentogo_comment(comment).text == ""
    assert read_kentogo_analysis(mistake)["taken_back"] is True


def test_what_older_versions_of_kentogo_wrote_is_removed():
    """In a game that KentoGo analyzed before (KGM): its text in KaTrain's form (no KGA), KentoGo's part of the
    comment and the marks of the best moves go; the user's notes stay."""
    old_part = f"{SEPARATOR}\n{KENTOGO_HEADER}\nMove 3: B A5"
    game = GAME.replace("(;", "(;KGM[KentoGo]", 1).replace("C[game note]", f"C[game note{old_part}]", 1)
    root = GoGame.parse_sgf(game.replace(";B[aa]", ";B[aa]MA[ea]SQ[bb]", 1))
    analyzed_game = analyze_game(FakeEngine(), root, AnalysisSettings(), EngineValues(100, 0.0), lambda *_: None)
    write_analysis(analyzed_game, WriteSettings("1.2.3"))
    written = GoGame.parse_sgf(root.sgf())
    mistake = written.nodes_in_tree[3]
    assert written.get_property("C") == "game note" and mistake.get_property("C") == "my note"
    assert (mistake.get_property("MA"), mistake.get_property("SQ")) == (None, None)


def test_the_marks_of_a_game_not_analyzed_by_kentogo_stay():
    """Without KGM, the marks are not KentoGo's (KaTrain's or the user's): they stay."""
    root = GoGame.parse_sgf(GAME.replace(";B[aa]", ";B[aa]MA[ea]", 1))
    game = analyze_game(FakeEngine(), root, AnalysisSettings(), EngineValues(100, 0.0), lambda *_: None)
    write_analysis(game, WriteSettings("1.2.3"))
    assert GoGame.parse_sgf(root.sgf()).nodes_in_tree[3].get_property("MA") == "ea"


def test_kentogo_makes_a_problem_from_the_written_game():
    """The written game is read by KentoGo's own problem maker, from the analysis data."""
    result = extract_problems(analyzed(), "game.sgf", ExtractSettings())
    assert [(problem.move_number, problem.points_lost) for problem in result.problems] == [(3, 8.0)]


def test_backup_then_write(tmp_path):
    game = tmp_path / "game.sgf"
    game.write_bytes("(;C[元の棋譜])".encode("gb18030"))
    folder = backup_folder(tmp_path, "")
    copy = back_up(game, folder, datetime(2026, 11, 6, 17, 5, 9))
    assert copy == tmp_path / "backup" / "game 2026-11-06 170509.sgf"
    assert copy.read_bytes() == "(;C[元の棋譜])".encode("gb18030")  # Byte for byte.
    write_game(game, "(;C[新しい])")
    assert game.read_text(encoding="utf-8") == "(;C[新しい])"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["backup", "game.sgf"]  # No file left behind.
    assert backup_folder(tmp_path, "~/other").name == "other"


def test_the_root_is_marked_as_analyzed_by_kentogo():
    """KGM[KentoGo] tells that the losses are read in the position before each move."""
    assert analyzed().get_property("KGM") == "KentoGo"


def test_old_kentogo_data_is_removed_and_none_is_written():
    """The KGD that an older KentoGo wrote is removed, and no node gets one, even the moves read deeply."""
    root = GoGame.parse_sgf(GAME)
    root.nodes_in_tree[1].properties["KGD"] = ["old", "data"]
    targets = DeepTargets({"B": 5.0, "W": 5.0}, 400)
    game = analyze_game(FakeEngine(), root, AnalysisSettings(), EngineValues(100, 0.0), lambda *_: None, targets)
    write_analysis(game, WriteSettings("1.2.3"))
    nodes = GoGame.parse_sgf(root.sgf()).nodes_in_tree
    assert [node.depth for node in game.deep_nodes] == [3]
    assert not any("KGD" in node.properties for node in nodes)


def test_positions_that_cannot_become_problems_keep_only_what_is_used():
    """Only the position's values, KataGo's best move with its sequence and the moves played are kept, rounded."""
    best = {"move": "C3", "order": 0, "visits": 900, "scoreLead": 1.23456, "winrate": 0.612345, "prior": 0.3}
    best |= {"pv": ["C3", "D4"], "utility": 0.1, "humanPrior": 0.2, "ownership": [0.5] * 25}
    kept = kept_analysis(ANALYSIS | {"moves": {**ANALYSIS["moves"], "C3": best}}, {"A1"})
    assert set(kept) == {"root", "moves", "completed"} and set(kept["moves"]) == {"C3", "A1"}
    assert kept["moves"]["C3"] == {
        "move": "C3",
        "order": 0,
        "visits": 900,
        "scoreLead": 1.23,
        "winrate": 0.6123,
        "pv": ["C3", "D4"],
    }
    assert "pv" not in kept["moves"]["A1"]  # Only the best move keeps its sequence.
    assert kept["root"] == {"visits": 1000, "scoreLead": 1.0}
    assert "utility" in best  # The analysis itself is not changed.


def test_problem_positions_keep_the_candidates_read_enough():
    """A position that can become a problem also keeps the candidates read with at least 1 % of the visits."""
    kept = kept_problem_analysis(ANALYSIS, {"A1"})
    assert set(kept["moves"]) == {"C3", "D4", "A1"} and "pv" not in kept["moves"]["D4"]


ANALYSIS = {
    "root": {"visits": 1000, "scoreLead": 1.0, "humanWinrate": 0.55},
    "moves": {
        "C3": {"move": "C3", "order": 0, "visits": 900, "scoreLead": 1.0, "pv": ["C3"]},
        "D4": {"move": "D4", "order": 7, "visits": 50, "scoreLead": 0.0, "pv": ["D4"]},
        "E5": {"move": "E5", "order": 8, "visits": 5, "scoreLead": -1.0, "pv": ["E5"]},  # Below 1 %.
        "A1": {"move": "A1", "order": 999, "visits": 1, "scoreLead": -9.0, "pv": ["A1", "B2"]},  # Played.
    },
    "ownership": [0.5] * 25,
    "policy": [0.04] * 26,
    "completed": True,
}


def test_a_move_that_can_become_a_problem_keeps_its_first_instinct():
    """Move 3 (A5) can become a problem: its rank in the policy before it and the policy's first move are kept."""

    class WithPolicy(FakeEngine):
        def query(self, request, callback):
            policy = [0.01] * 26
            policy[0], policy[20] = 0.5, 0.2  # A5 (the top-left point) first, then A1.
            return super().query(request, lambda answer: callback({**answer, "policy": policy}))

    root = GoGame.parse_sgf(GAME)
    settings = AnalysisSettings()
    targets = DeepTargets({"B": 5.0}, 400)
    game = analyze_game(WithPolicy(), root, settings, EngineValues(100, 0.0), lambda *_: None, targets)
    write_analysis(game, WriteSettings("1.2.3"))
    nodes = GoGame.parse_sgf(root.sgf()).nodes_in_tree
    instincts = [read_kentogo_analysis(node).get("instinct") for node in nodes]
    assert instincts[:3] == [None, None, None]
    assert instincts[3] == {"rank": 1, "probability": 0.5, "best": "A5", "best_probability": 0.5}
    assert all(read_kentogo_analysis(node)["policy"] is None for node in nodes)  # The policy itself is not kept.


def test_the_game_record_reads_the_evaluations_from_kentogos_analysis_data():
    """Without KaTrain's text, the loss, the best move and the sequence come from KGA (for the viewer and the AI)."""
    root = GoGame.parse_sgf(GAME.replace(f"C[my note{SEPARATOR}{OLD}]", "", 1))
    game = analyze_game(FakeEngine(), root, AnalysisSettings(), EngineValues(100, 0.0), lambda *_: None)
    write_analysis(game, WriteSettings("1.2.3"))
    mistake = read_game_record(GoGame.parse_sgf(root.sgf())).moves[2]
    info = mistake.katrain
    assert (info.points_lost, info.best_move, info.pv, info.pv_color) == (8.0, "E5", ("E5",), "B")


def test_the_viewer_names_kentogos_sequence():
    """In a game that KentoGo analyzed, the viewer's predicted sequence is KentoGo's."""
    from kentogo.gui.viewer_model import SOURCE_KENTOGO, variations_at

    root = GoGame.parse_sgf(GAME.replace(f"C[my note{SEPARATOR}{OLD}]", "", 1))
    game = analyze_game(FakeEngine(), root, AnalysisSettings(), EngineValues(100, 0.0), lambda *_: None)
    write_analysis(game, WriteSettings("1.2.3"))
    record = read_game_record(GoGame.parse_sgf(root.sgf()))
    assert record.moves[2].kentogo_evaluation and variations_at(record, 3)[0].source == SOURCE_KENTOGO
