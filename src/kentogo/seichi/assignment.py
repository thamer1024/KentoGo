"""Pair the rows and the columns of a square table of costs, with the lowest total cost.

This is the Hungarian method (Kuhn and Munkres), in the form with potentials that
takes about n * n * n steps for n rows. It is used to pair the stones that must move
with the points that need a stone, so that the stones move as little as possible in
total (see block_tidy).
"""

from __future__ import annotations

INFINITY = float("inf")


def cheapest_pairs(cost: list[list[float]]) -> list[int]:
    """Return, for each row, the column paired with it, so that the sum of the costs is the lowest.

    Args:
        cost: cost[row][column], a square table (as many rows as columns).

    Returns:
        The column of each row, in the order of the rows.

    Raises:
        ValueError: If the table is not square.
    """
    size = len(cost)
    if any(len(row) != size for row in cost):
        raise ValueError("the table of costs must be square")
    # Rows and columns are numbered from 1 here; row 0 and column 0 are helpers of the method.
    row_potential = [0.0] * (size + 1)
    column_potential = [0.0] * (size + 1)
    row_of_column = [0] * (size + 1)
    for row in range(1, size + 1):
        _add_row(cost, row, row_potential, column_potential, row_of_column)
    column_of_row = [0] * size
    for column in range(1, size + 1):
        if row_of_column[column]:
            column_of_row[row_of_column[column] - 1] = column - 1
    return column_of_row


def _add_row(
    cost: list[list[float]],
    row: int,
    row_potential: list[float],
    column_potential: list[float],
    row_of_column: list[int],
) -> None:
    """Pair one more row, changing the pairs found so far along the cheapest path (changes the lists)."""
    size = len(cost)
    row_of_column[0] = row
    column = 0
    least = [INFINITY] * (size + 1)  # The lowest reduced cost found to each column.
    came_from = [0] * (size + 1)
    used = [False] * (size + 1)
    while row_of_column[column]:
        used[column] = True
        current = row_of_column[column]
        step, next_column = INFINITY, 0
        costs = cost[current - 1]
        current_potential = row_potential[current]
        for other in range(1, size + 1):
            if used[other]:
                continue
            reduced = costs[other - 1] - current_potential - column_potential[other]
            if reduced < least[other]:
                least[other] = reduced
                came_from[other] = column
            if least[other] < step:
                step, next_column = least[other], other
        for other in range(size + 1):
            if used[other]:
                row_potential[row_of_column[other]] += step
                column_potential[other] -= step
            else:
                least[other] -= step
        column = next_column
    while column:  # Go back along the path, moving each pair one column.
        previous = came_from[column]
        row_of_column[column] = row_of_column[previous]
        column = previous
