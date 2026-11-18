"""What the screen of the local fight problems needs: the play of each fight against KataGo, and saving its answer.

The app makes it from the settings (see app._make_setup) when the screen is opened with the running KataGo. The
opponent is KataGo's strongest replies, or the human-like replies of the opponent's rank in the fight's game
(see kentogo.opponent_rank; without a rank, the strongest replies). Each reading uses the engine's max_visits.
The sequence of the AIs shown after a fight is always human-like (see quiz.fight_follow).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from kentogo.fight_answers import save_fight_answer
from kentogo.katago.evaluate import AnalysisEngine, EvaluationSettings
from kentogo.katago.human_moves import human_profile
from kentogo.mistakes.local_fight import LocalFight
from kentogo.quiz.fight_follow import follow_profiles
from kentogo.quiz.fight_judge import OPPONENT_RANK
from kentogo.quiz.fight_run import FightPlay, FightRun
from kentogo.quiz.fight_settings import FightSettings
from kentogo.quiz.human_line import PlayerRanks
from kentogo.review.history import AnswerHistory


@dataclass(frozen=True)
class FightTools:
    """What the screen of the local fights uses.

    Attributes:
        make_run: Makes the play of a fight against KataGo.
        save: Saves the answer of a fight that has ended (nothing is saved without a history).
    """

    make_run: Callable[[LocalFight], FightRun]
    save: Callable[[FightRun], None]


def fight_play(settings: FightSettings, evaluation: EvaluationSettings, ranks: PlayerRanks) -> FightPlay:
    """Return how KataGo plays a fight: the opponent of the settings, with the profiles of the players' ranks.

    The opponent's profile is used for its replies (with the human-like opponent only). The profiles of the sequence
    of the AIs after the fight are always made (see quiz.fight_follow.follow_profiles).
    """
    rank = settings.opponent == OPPONENT_RANK
    my_line_profile, line_profile = follow_profiles(ranks)
    return FightPlay(
        evaluation.max_visits,
        evaluation.wide_root_noise,
        settings.opponent,
        human_profile(ranks.theirs) if rank else "",
        settings.score_tolerance,
        my_line_profile,
        line_profile,
    )


def fight_tools(
    engine: AnalysisEngine,
    evaluation: EvaluationSettings,
    settings: FightSettings,
    history: AnswerHistory | None,
    ranks: Callable[[LocalFight], PlayerRanks],
    log_line: Callable[[dict], None] = lambda _record: None,
) -> FightTools:
    """Make the tools of the screen of the local fights.

    Args:
        engine: The running KataGo.
        evaluation: How KataGo analyzes the positions (its visits and noise are used).
        settings: How the local fights are played.
        history: The history of the fights, or None.
        ranks: Returns the ranks of the players of a fight's game.
        log_line: Told a record about how the sequence of the AIs ended (see line_log.log_line).
    """

    def make_run(fight: LocalFight) -> FightRun:
        return FightRun(engine, fight, replace(fight_play(settings, evaluation, ranks(fight)), log_line=log_line))

    def save(run: FightRun) -> None:
        if history is not None:
            save_fight_answer(history, run, evaluation.max_visits)

    return FightTools(make_run, save)
