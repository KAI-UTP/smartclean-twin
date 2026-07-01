"""Unit tests: grid map and coverage calculation."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "robot-simulator"))

import pytest
import numpy as np
import grid_map as gm


class TestGridMap:
    def test_home_cell_is_accessible(self):
        assert gm.is_accessible(gm.HOME_ROW, gm.HOME_COL)

    def test_border_cells_are_obstacles(self):
        # All four corners must be obstacles (walls)
        assert not gm.is_accessible(0, 0)
        assert not gm.is_accessible(0, gm.GRID_COLS - 1)
        assert not gm.is_accessible(gm.GRID_ROWS - 1, 0)
        assert not gm.is_accessible(gm.GRID_ROWS - 1, gm.GRID_COLS - 1)

    def test_total_accessible_cells_positive(self):
        total = gm.total_accessible_cells()
        assert total > 0
        assert total < gm.GRID_ROWS * gm.GRID_COLS

    def test_out_of_bounds_is_not_accessible(self):
        assert not gm.is_accessible(-1, 0)
        assert not gm.is_accessible(0, -1)
        assert not gm.is_accessible(100, 100)

    def test_lawnmower_path_covers_accessible_cells(self):
        path = gm.lawnmower_path()
        assert len(path) > 0
        for row, col in path:
            assert gm.is_accessible(row, col), f"Cell ({row},{col}) in path but not accessible"

    def test_lawnmower_path_no_duplicates(self):
        path = gm.lawnmower_path()
        assert len(path) == len(set(path)), "Path contains duplicate cells"

    def test_dirt_map_shape(self):
        dirt = gm.generate_dirt_map(seed=42)
        assert dirt.shape == (gm.GRID_ROWS, gm.GRID_COLS)

    def test_dirt_map_obstacles_are_zero(self):
        import numpy as _np
        dirt = gm.generate_dirt_map(seed=42)
        # Wall cells (value 1 in layout) must have 0 dirt
        from grid_map import _LAYOUT
        obstacle_mask = _LAYOUT == 1
        assert _np.all(dirt[obstacle_mask] == 0.0)

    def test_dirt_map_values_in_range(self):
        dirt = gm.generate_dirt_map(seed=42)
        assert float(dirt.min()) >= 0.0
        assert float(dirt.max()) <= 1.0

    def test_dirt_map_deterministic(self):
        d1 = gm.generate_dirt_map(seed=7)
        d2 = gm.generate_dirt_map(seed=7)
        import numpy as _np
        assert _np.array_equal(d1, d2)
