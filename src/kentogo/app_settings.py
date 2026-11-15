"""All settings of the app together: the quiz, the engine, the reviews, the territory counting practice, the AI commentary
and the analysis of games.

Each feature has its own settings class and does not know the others. This
class puts them together for the settings file and the settings screens, in
the same way as app.py puts the features together.

In settings.json, the "quiz" part holds the quiz settings and the review
settings in one flat dict (the file has looked like this from the start), and
the "engine" part holds the engine settings, the "seichi" part holds the
settings of the territory counting practice, the "commentary" part holds the
settings of the AI commentary, and the "analysis" part holds the settings of the analysis of games. The
"fights" part holds the review settings of the local fight problems (see mistakes.local_fight): they are
reviewed in the same way as the mistake problems, but with their own settings (FIGHT_REVIEW at first), and
how the fights are played (quiz.fight_settings).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from kentogo.analysis.analysis_settings import AnalysisSettings
from kentogo.commentary.commentary_settings import CommentarySettings
from kentogo.katago.engine_settings import EngineSettings
from kentogo.quiz.fight_settings import FightSettings
from kentogo.quiz.quiz_settings import QuizSettings
from kentogo.review.review_settings import ReviewSettings
from kentogo.seichi.seichi_settings import SeichiSettings

# The review settings of the local fight problems at first: a fight takes longer than a mistake problem.
FIGHT_REVIEW = ReviewSettings(session_limit=5)


@dataclass(frozen=True)
class AppSettings:
    """All settings of the app.

    Attributes:
        quiz: The settings of the quiz (games, choosing and asking problems, judging).
        engine: The settings of KataGo.
        review: The settings of reviews and of how many problems are asked.
        seichi: The settings of the territory counting practice.
        commentary: The settings of the AI commentary.
        analysis: The settings of the analysis of games (KataGo, as KaTrain).
        fights: The review settings of the local fight problems, and how many are asked in a day.
        fight_play: How the local fight problems are played (the opponent, the score that may be lost).
    """

    quiz: QuizSettings = field(default_factory=QuizSettings)
    engine: EngineSettings = field(default_factory=EngineSettings)
    review: ReviewSettings = field(default_factory=ReviewSettings)
    seichi: SeichiSettings = field(default_factory=SeichiSettings)
    commentary: CommentarySettings = field(default_factory=CommentarySettings)
    analysis: AnalysisSettings = field(default_factory=AnalysisSettings)
    fights: ReviewSettings = FIGHT_REVIEW
    fight_play: FightSettings = field(default_factory=FightSettings)

    def sections(self) -> dict[str, dict]:
        """Return the settings as the parts of settings.json: {"quiz": {...}, "engine": {...}, ...}."""
        return {
            "quiz": {**self.quiz.to_dict(), **self.review.to_dict()},
            "engine": self.engine.to_dict(),
            "seichi": self.seichi.to_dict(),
            "commentary": self.commentary.to_dict(),
            "analysis": self.analysis.to_dict(),
            "fights": {**self.fights.to_dict(), **self.fight_play.to_dict()},
        }

    @classmethod
    def from_sections(cls, sections: dict[str, dict]) -> AppSettings:
        """Make the settings from the parts of settings.json. Missing parts and keys get default values.

        Raises:
            ValueError: If a value has a wrong type or is not allowed.
        """
        quiz = sections.get("quiz", {})
        return cls(
            QuizSettings.from_dict(quiz),
            EngineSettings.from_dict(sections.get("engine", {})),
            ReviewSettings.from_dict(quiz),
            SeichiSettings.from_dict(sections.get("seichi", {})),
            CommentarySettings.from_dict(sections.get("commentary", {})),
            AnalysisSettings.from_dict(sections.get("analysis", {})),
            ReviewSettings.from_dict(sections.get("fights", {}), FIGHT_REVIEW),
            FightSettings.from_dict(sections.get("fights", {})),
        )


def without_offer_answers(settings: AppSettings) -> AppSettings:
    """Return the settings as if no offer had been answered (see QuizSettings.ratio_asked_at and limit_asked_at).

    Used when the history is cleared: the answers are counted again from 0, so the offers come again after
    offer_window new answers. The pass ratio and the limit that the user chose are kept.
    """
    return replace(settings, quiz=replace(settings.quiz, ratio_asked_at=0, limit_asked_at=0))
