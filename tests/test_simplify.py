"""Tests for QEM simplification and the clustering baseline."""

import numpy as np
import pytest

from mesh.mesh import degenerate_faces, duplicate_faces, euler_characteristic, face_normals
from mesh.metrics import shape_error
from mesh.simplify import cluster_simplify, simplify

RATIOS = [0.5, 0.1, 0.02]


@pytest.mark.parametrize("ratio", RATIOS)
def test_euler_preserved(spot, spot_at, ratio):
    """The link condition keeps the topology: Spot stays a sphere (chi = 2)."""
    V2, F2, _ = spot_at(ratio)
    assert euler_characteristic(V2, F2) == euler_characteristic(*spot) == 2


@pytest.mark.parametrize("ratio", RATIOS)
def test_no_degenerate_or_duplicate_faces(spot_at, ratio):
    V2, F2, _ = spot_at(ratio)
    assert len(degenerate_faces(V2, F2)) == 0
    assert len(duplicate_faces(F2)) == 0


def test_target_faces_reached(spot):
    """Each collapse removes 2 faces, so the result lands just at or below the target."""
    V2, F2, _ = simplify(*spot, target_faces=500)
    assert 490 <= len(F2) <= 500


def test_ratio_one_does_nothing(spot):
    V, F = spot
    V2, F2, stats = simplify(V, F, ratio=1.0)
    assert stats["collapses"] == 0
    assert len(F2) == len(F)


def test_flat_grid_collapses_to_few_triangles(flat_grid):
    """A flat square has zero quadric cost inside: it can shrink to a handful of
    triangles without moving off the plane or changing its outline."""
    V, F = flat_grid
    V2, F2, _ = simplify(V, F, target_faces=2)
    assert len(F2) <= 8
    assert np.allclose(V2[:, 2], 0.0)
    assert shape_error(V, F, V2, F2)["mean_pct"] < 0.01


def test_normals_point_outward(spot_at):
    """More than 80% of the simplified faces still face away from Spot's centre."""
    V2, F2, _ = spot_at(0.02)
    outward = V2[F2].mean(axis=1) - V2.mean(axis=0)
    assert np.mean(np.einsum("ij,ij->i", face_normals(V2, F2), outward) > 0) > 0.8


def test_error_grows_as_triangles_drop(spot, spot_at):
    errors = [shape_error(*spot, *spot_at(r)[:2])["mean_pct"] for r in RATIOS]
    assert errors[0] < errors[1] < errors[2]


def test_qem_beats_clustering(spot):
    """At the same triangle count, QEM's mean error is lower than vertex clustering's."""
    V, F = spot
    Vc, Fc = cluster_simplify(V, F, cells=20)
    Vq, Fq, _ = simplify(V, F, target_faces=len(Fc))
    assert shape_error(V, F, Vq, Fq)["mean_pct"] < shape_error(V, F, Vc, Fc)["mean_pct"]
