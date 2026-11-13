"""Tests for Loop subdivision."""

import numpy as np

from mesh.mesh import edges, euler_characteristic
from mesh.subdivide_loop import loop_subdivide


def test_counts_after_one_level(spot):
    """Every triangle becomes 4; every edge adds one new vertex."""
    V, F = spot
    V2, F2 = loop_subdivide(V, F, 1)
    assert len(F2) == 4 * len(F)
    assert len(V2) == len(V) + len(edges(F))


def test_icosahedron_three_levels(icosahedron):
    V2, F2 = loop_subdivide(*icosahedron, 3)
    assert len(F2) == 20 * 4 ** 3 == 1280


def test_euler_preserved(spot, icosahedron):
    for V, F in (spot, icosahedron):
        V2, F2 = loop_subdivide(V, F, 2)
        assert euler_characteristic(V2, F2) == euler_characteristic(V, F)


def test_icosahedron_becomes_round(icosahedron):
    """After 3 levels all vertices are nearly the same distance from the centre."""
    V2, _ = loop_subdivide(*icosahedron, 3)
    r = np.linalg.norm(V2, axis=1)
    assert r.std() / r.mean() < 0.01


def test_flat_grid_stays_flat(flat_grid):
    """Averages of points in a plane stay in that plane."""
    V2, _ = loop_subdivide(*flat_grid, 2)
    assert np.allclose(V2[:, 2], 0.0)


def test_cube_stays_inside(cube):
    """Loop's weights are positive and sum to 1, so new points are averages of
    old ones and cannot leave the cube."""
    V2, _ = loop_subdivide(*cube, 3)
    assert V2.min() >= -1e-12 and V2.max() <= 1 + 1e-12
