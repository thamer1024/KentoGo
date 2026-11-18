"""The texts of the analysis of the games with KataGo."""

from __future__ import annotations

from kentogo.analysis_run import AnalysisSummary, FolderGames
from kentogo.gui import texts


def analysis_step_text(step: str, done: int, total: int) -> str:
    """Return the progress of a step of the analysis of a game (see analysis.game_analysis)."""
    return texts.text(f"analysis_step_{step}", done=done, total=total)


def analysis_outcome_text(name: str, outcome: str, detail: str) -> str:
    """Return how the analysis of a game ended (see analysis_run), with the reason of a failure."""
    if outcome == "written" and "could not be analyzed" in detail:
        return texts.text("analysis_outcome_incomplete", name=name)
    return texts.text(f"analysis_outcome_{outcome}", name=name, detail=detail)


def analysis_summary_text(summary: AnalysisSummary) -> str:
    """Return how a run of the analysis ended: the games written, skipped and failed, or why it could not run."""
    if summary.problem:
        return texts.text("analysis_problem", reason=summary.problem)
    counts = summary.outcomes
    key = "analysis_summary_stopped" if summary.stopped else "analysis_summary"
    return texts.text(key, written=counts["written"], skipped=counts["skipped"], failed=counts["failed"])


def analysis_folder_problem(games: FolderGames) -> str:
    """Return why the games of the analysis's folder cannot be listed (no folder set, no folder, no games), or ""."""
    if games.folder is None:
        return texts.text("analysis_no_folder_set")
    if not games.folder.is_dir():
        return texts.text("analysis_no_folder", folder=games.folder)
    if not games.games:
        return texts.text("analysis_no_games", folder=games.folder)
    return ""


def analysis_state_text(state: str) -> str:
    """Return what a game of the list of the games to analyze is (see analysis_run.GAME_NEW and the others)."""
    return texts.text(f"analysis_state_{state}")
