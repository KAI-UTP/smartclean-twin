"""10×10 indoor grid map for the SmartClean simulator.

Cell values:
  0 = accessible floor
  1 = obstacle / wall
"""

from __future__ import annotations

import numpy as np

# 1 = wall/obstacle, 0 = accessible floor
_LAYOUT = np.array([
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 1, 0, 0, 0, 0, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
], dtype=np.int8)

GRID_ROWS, GRID_COLS = _LAYOUT.shape
CELL_SIZE_M = 0.5  # each cell is 0.5 m × 0.5 m
HOME_ROW, HOME_COL = 1, 1  # starting cell


def is_accessible(row: int, col: int) -> bool:
    if 0 <= row < GRID_ROWS and 0 <= col < GRID_COLS:
        return _LAYOUT[row, col] == 0
    return False


def total_accessible_cells() -> int:
    return int(np.sum(_LAYOUT == 0))


def generate_dirt_map(seed: int = 42) -> np.ndarray:
    """Return a float32 array of dirt scores [0,1] for accessible cells."""
    rng = np.random.default_rng(seed)
    dirt = rng.uniform(0.0, 1.0, size=_LAYOUT.shape).astype(np.float32)
    dirt[_LAYOUT == 1] = 0.0
    return dirt


def lawnmower_path() -> list[tuple[int, int]]:
    """Return ordered list of (row, col) cells in lawnmower pattern."""
    path: list[tuple[int, int]] = []
    for row in range(1, GRID_ROWS - 1):
        cols = range(1, GRID_COLS - 1) if row % 2 == 1 else range(GRID_COLS - 2, 0, -1)
        for col in cols:
            if is_accessible(row, col):
                path.append((row, col))
    return path
