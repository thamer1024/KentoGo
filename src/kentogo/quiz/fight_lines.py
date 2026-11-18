"""The sequences shown after a local fight, switched with Tab and played back and forward (no Kivy here).

After the fight is judged, three sequences from the fight's position can be shown, in this order:

- LINE_PLAYED: the moves played in the fight, the user's and KataGo's (shown first, to its end);
- LINE_AI: the sequence in which both sides play the human-like moves of their ranks until the place is settled
  (see quiz.fight_follow); KataGo makes it when it is asked for, so it may still be coming (the moves made so far
  can be shown);
- LINE_GAME: the moves of the game.

A sequence chosen with Tab (next) or Shift+Tab (previous) is shown from its first move; forward and back play
it one move at a time.
"""

from __future__ import annotations

from kentogo.common.types import Move

LINE_PLAYED = "played"
LINE_AI = "ai"
LINE_GAME = "game"
LINES = (LINE_PLAYED, LINE_AI, LINE_GAME)

AI_CALCULATING = "calculating"
AI_READY = "ready"
AI_FAILED = "failed"


class FightLines:
    """The sequences of a fight that has ended.

    Attributes:
        selected: The number of the sequence shown, in LINES.
        step: How many moves of it are shown.
        ai_state: AI_CALCULATING until the sequence of the AIs has come, then AI_READY (or AI_FAILED).
    """

    def __init__(self, played: tuple[Move, ...], game: tuple[Move, ...]):
        """Show the moves played, to their end (the sequence of the AIs is still coming)."""
        self._lines: dict[str, tuple[Move, ...]] = {LINE_PLAYED: played, LINE_AI: (), LINE_GAME: game}
        self.selected = 0
        self.step = len(played)
        self.ai_state = AI_CALCULATING

    @property
    def name(self) -> str:
        """The sequence shown: one of LINES."""
        return LINES[self.selected]

    @property
    def length(self) -> int:
        """The number of moves of the sequence shown."""
        return len(self._lines[self.name])

    def shown(self) -> tuple[Move, ...]:
        """Return the moves shown on the board."""
        return self._lines[self.name][: self.step]

    def update_ai_line(self, line: tuple[Move, ...]) -> None:
        """Keep the moves of the sequence of the AIs made so far (its first move is shown at once when it is shown)."""
        self._lines[LINE_AI] = line
        if self.name == LINE_AI and self.step == 0:
            self.step = min(1, len(line))

    def set_ai_line(self, line: tuple[Move, ...]) -> None:
        """Keep the whole sequence of the AIs (its first move is shown at once when it is the sequence shown)."""
        self.update_ai_line(line)
        self.ai_state = AI_READY

    def show_ai_line(self) -> None:
        """Show the sequence of the AIs from its first move."""
        self._select(LINES.index(LINE_AI))

    def ai_failed(self) -> None:
        """Tell that the sequence of the AIs could not be made."""
        self.ai_state = AI_FAILED

    def next_line(self) -> None:
        """Show the next sequence (after the last, the first), from its first move."""
        self._select((self.selected + 1) % len(LINES))

    def previous_line(self) -> None:
        """Show the sequence before (before the first, the last), from its first move."""
        self._select((self.selected - 1) % len(LINES))

    def forward(self) -> None:
        """Show one move more (not after the last)."""
        self.step = min(self.step + 1, self.length)

    def back(self) -> None:
        """Show one move less (not before the position)."""
        self.step = max(self.step - 1, 0)

    def _select(self, index: int) -> None:
        """Show a sequence from its first move."""
        self.selected = index
        self.step = min(1, self.length)
