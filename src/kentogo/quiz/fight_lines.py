"""The sequences shown after a local fight, switched with Tab and played back and forward (no Kivy here).

After the fight is judged, three sequences from the fight's position can be shown, in this order:

- LINE_PLAYED: the moves played in the fight, the user's and KataGo's (shown first, to its end);
- LINE_AI: the sequence in which both sides play the human-like moves of their ranks until the place is settled
  (see quiz.fight_follow); KataGo makes it when it is asked for, so it may still be coming (the moves made so far
  can be shown);
- LINE_GAME: the moves of the game;
- LINE_STRONG: the sequence in which both sides play KataGo's best moves, added after them only when the sequence of
  the AIs did not conclude how the place ended (see start_strong_line); it is shown from its first move at once, and
  grows as KataGo makes it.

A sequence chosen with Tab (next) or Shift+Tab (previous) is shown from its first move; forward and back play
it one move at a time.
"""

from __future__ import annotations

from kentogo.common.types import Move
from kentogo.quiz.fight_follow import FollowEnd

LINE_PLAYED = "played"
LINE_AI = "ai"
LINE_GAME = "game"
LINE_STRONG = "strong"
LINES = (LINE_PLAYED, LINE_AI, LINE_GAME)  # The sequences that are always there, in the order of Tab.

AI_CALCULATING = "calculating"
AI_READY = "ready"
AI_FAILED = "failed"


class FightLines:
    """The sequences of a fight that has ended.

    Attributes:
        selected: The number of the sequence shown, among the sequences that can be shown (see count).
        step: How many moves of it are shown.
        ai_state: AI_CALCULATING until the sequence of the AIs has come, then AI_READY (or AI_FAILED).
        ai_end: Why the sequence of the AIs ended (None until it has come).
        strong_state: AI_CALCULATING until the sequence of the strongest AI has come, then AI_READY (or AI_FAILED).
        strong_end: Why the sequence of the strongest AI ended (None until it has come).
    """

    def __init__(self, played: tuple[Move, ...], game: tuple[Move, ...]):
        """Show the moves played, to their end (the sequence of the AIs is still coming)."""
        self._lines: dict[str, tuple[Move, ...]] = {LINE_PLAYED: played, LINE_AI: (), LINE_GAME: game}
        self._names = list(LINES)
        self.selected = 0
        self.step = len(played)
        self.ai_state = AI_CALCULATING
        self.ai_end: FollowEnd | None = None
        self.strong_state = AI_CALCULATING
        self.strong_end: FollowEnd | None = None

    @property
    def name(self) -> str:
        """The sequence shown: one of LINES, or LINE_STRONG once it was started."""
        return self._names[self.selected]

    @property
    def count(self) -> int:
        """The number of the sequences that can be shown."""
        return len(self._names)

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

    def set_ai_line(self, line: tuple[Move, ...], end: FollowEnd) -> None:
        """Keep the whole sequence of the AIs and why it ended (its first move is shown at once when it is shown)."""
        self.update_ai_line(line)
        self.ai_state = AI_READY
        self.ai_end = end

    def show_ai_line(self) -> None:
        """Show the sequence of the AIs from its first move."""
        self._select(LINES.index(LINE_AI))

    def ai_failed(self) -> None:
        """Tell that the sequence of the AIs could not be made."""
        self.ai_state = AI_FAILED

    @property
    def strong_asked(self) -> bool:
        """True once the sequence of the strongest AI was started."""
        return LINE_STRONG in self._names

    def start_strong_line(self) -> None:
        """Add the sequence of the strongest AI after the others, and show it from its first move (as it comes)."""
        self._names.append(LINE_STRONG)
        self._lines[LINE_STRONG] = ()
        self.strong_state, self.strong_end = AI_CALCULATING, None
        self._select(len(self._names) - 1)

    def show_strong_line(self) -> None:
        """Show the sequence of the strongest AI from its first move (nothing happens before it was started)."""
        if self.strong_asked:
            self._select(self._names.index(LINE_STRONG))

    def update_strong_line(self, line: tuple[Move, ...]) -> None:
        """Keep the moves of the strongest AI's sequence made so far (its first move is shown at once when it is shown)."""
        self._lines[LINE_STRONG] = line
        if self.name == LINE_STRONG and self.step == 0:
            self.step = min(1, len(line))

    def set_strong_line(self, line: tuple[Move, ...], end: FollowEnd) -> None:
        """Keep the whole sequence of the strongest AI and why it ended."""
        self.update_strong_line(line)
        self.strong_state = AI_READY
        self.strong_end = end

    def strong_failed(self) -> None:
        """Tell that the sequence of the strongest AI could not be made."""
        self.strong_state = AI_FAILED

    def next_line(self) -> None:
        """Show the next sequence (after the last, the first), from its first move."""
        self._select((self.selected + 1) % self.count)

    def previous_line(self) -> None:
        """Show the sequence before (before the first, the last), from its first move."""
        self._select((self.selected - 1) % self.count)

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
