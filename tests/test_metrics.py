"""Tests for the surface-distance measurement."""

import numpy as np

from mesh.mesh import bbox_diagonal, boundary_edges, euler_characteristic
from mesh.metrics import closest_point_on_triangles, point_to_surface, shape_error, surface_samples


def test_self_error_is_zero(spot):
    assert shape_error(*spot, *spot)["mean_pct"] < 0.001


def test_shift_measured(spot):
    """Moving a copy by 1% of the diagonal gives a max error close to (at most) 1%."""
    V, F = spot
    direction = np.array([1.0, 1.0, 1.0]) / np.sqrt(3)
    err = shape_error(V, F, V + 0.01 * bbox_diagonal(V) * direction, F)
    assert 0.2 < err["max_pct"] < 1.05


def test_closest_point_regions():
    """One query point in each kind of region: above the face, beyond a corner, beside an edge."""
    A = np.array([[0.0, 0, 0]] * 3)
    B = np.array([[1.0, 0, 0]] * 3)
    C = np.array([[0.0, 1, 0]] * 3)
    P = np.array([[0.2, 0.2, 5.0],      # above the face   -> straight down
                  [-1.0, -1.0, 0.0],    # beyond corner A  -> A
                  [0.5, -2.0, 1.0]])    # beside edge AB   -> foot on AB
    Q = closest_point_on_triangles(P, A, B, C)
    assert np.allclose(Q, [[0.2, 0.2, 0.0], [0.0, 0.0, 0.0], [0.5, 0.0, 0.0]])


def test_samples_lie_on_surface(spot):
    V, F = spot
    S = surface_samples(V, F, 2000, seed=3)
    d = point_to_surface(S, V, F, dense=0)   # exact distance only
    assert d.max() < 1e-9 * bbox_diagonal(V)


def test_spot_is_closed(spot):
    V, F = spot
    assert len(boundary_edges(F)) == 0
    assert euler_characteristic(V, F) == 2
