"""All settings of the app together: the quiz, the engine, the reviews, the territory counting practice and the AI commentary.

Each feature has its own settings class and does not know the others. This
class puts them together for the settings file and the settings screens, in
the same way as app.py puts the features together.

In settings.json, the "quiz" part holds the quiz settings and the review
settings in one flat dict (the file has looked like this from the start), and
the "engine" part holds the engine settings, the "seichi" part holds the
settings of the territory counting practice, and the "commentary" part holds the
settings of the AI commentary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kentogo.commentary.commentary_settings import CommentarySettings
from kentogo.katago.engine_settings import EngineSettings
from kentogo.quiz.quiz_settings import QuizSettings
from kentogo.review.review_settings import ReviewSettings
from kentogo.seichi.seichi_settings import SeichiSettings


@dataclass(frozen=True)
class AppSettings:
    """All settings of the app.

    Attributes:
        quiz: The settings of the quiz (games, choosing and asking problems, judging).
        engine: The settings of KataGo.
        review: The settings of reviews and of how many problems are asked.
        seichi: The settings of the territory counting practice.
        commentary: The settings of the AI commentary.
    """

    quiz: QuizSettings = field(default_factory=QuizSettings)
    engine: EngineSettings = field(default_factory=EngineSettings)
    review: ReviewSettings = field(default_factory=ReviewSettings)
    seichi: SeichiSettings = field(default_factory=SeichiSettings)
    commentary: CommentarySettings = field(default_factory=CommentarySettings)

    def sections(self) -> dict[str, dict]:
        """Return the settings as the parts of settings.json: {"quiz": {...}, "engine": {...}, ...}."""
        return {
            "quiz": {**self.quiz.to_dict(), **self.review.to_dict()},
            "engine": self.engine.to_dict(),
            "seichi": self.seichi.to_dict(),
            "commentary": self.commentary.to_dict(),
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
        )
