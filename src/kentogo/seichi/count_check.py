"""The check of the user's seichi (整地終了).

After the user has done the seichi, the territory on the board (counted as a person does: an
area belongs to the color of most of the stones around it, see territory.majority_owners) must
be the right one. Prisoners that could not be put into the territory (when it is too small) are
taken off the territory of their color, as if they had been put there.

The right territory is the territory when the end of the game was confirmed, less the
prisoners that go into it (Japanese rules: the black prisoners go into black's territory).
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.seichi.territory import TerritoryCount


@dataclass(frozen=True)
class CountCheck:
    """The result of the check.

    Attributes:
        right: The right territory after the seichi.
        board: The territory on the board now.
        prisoners_left: The prisoners still in the trays, by the color of the stones.
    """

    right: TerritoryCount
    board: TerritoryCount
    prisoners_left: dict[str, int]

    @property
    def counted(self) -> TerritoryCount:
        """The territory on the board less the prisoners still in the trays."""
        return right_territory(self.board, self.prisoners_left)

    @property
    def passed(self) -> bool:
        """True if the territory, counted with the prisoners still in the trays, is the right one."""
        return self.counted == self.right


def right_territory(confirmed: TerritoryCount, prisoners: dict[str, int]) -> TerritoryCount:
    """Return the territory after the seichi: the confirmed territory less the prisoners that go into it.

    Args:
        confirmed: The territory when the end of the game was confirmed.
        prisoners: The prisoners in the trays then, by the color of the stones.
    """
    return TerritoryCount(confirmed.black - prisoners["B"], confirmed.white - prisoners["W"])
