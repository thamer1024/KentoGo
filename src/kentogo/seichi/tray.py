"""How the prisoners in a tray are shown: stones one by one, and groups of ten.

When there are many prisoners, ten stones are shown as one "x10" group. There are
always 1 to 10 single stones (when there is at least one prisoner), so a group of
ten is opened into ten single stones only when the single stones run out: with
21 prisoners there are two groups and one stone; after one is used, one group and
ten stones. When stones come back, eleven become one group and one stone again.
"""

from __future__ import annotations

GROUP = 10  # The number of stones in a group.


def tray_layout(count: int) -> tuple[int, int]:
    """Return how to show a number of prisoners, as (groups of ten, single stones).

    Args:
        count: The number of prisoners (0 or more).
    """
    if count <= 0:
        return 0, 0
    groups = (count - 1) // GROUP
    return groups, count - groups * GROUP
