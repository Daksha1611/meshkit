"""Shared test fixtures: small meshes built in code plus the Spot model."""

import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # so "import mesh" works when pytest runs from anywhere

from mesh.obj_io import load_obj  # noqa: E402
from mesh.simplify import simplify  # noqa: E402


@pytest.fixture(scope="session")
def spot():
    """Spot the cow: closed, 2,930 vertices, 5,856 triangles."""
    return load_obj(os.path.join(ROOT, "models", "spot.obj"))


@pytest.fixture(scope="session")
def spot_at(spot):
    """A function ratio -> simplify(Spot, ratio), cached so each ratio is computed once
    even though several tests look at the same simplified meshes."""
    cache = {}

    def get(ratio):
        if ratio not in cache:
            cache[ratio] = simplify(*spot, ratio=ratio)
        return cache[ratio]
    return get


def make_icosahedron():
    """Regular icosahedron with all 12 vertices on the unit sphere, 20 faces."""
    t = (1 + 5 ** 0.5) / 2
    V = np.array([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t],
                  [0, -1, -t], [0, 1, -t], [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], float)
    V /= np.linalg.norm(V, axis=1, keepdims=True)
    F = np.array([[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4],
                  [11, 10, 2], [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8],
                  [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]])
    return V, F


def make_cube():
    """Unit cube [0,1]^3: 8 vertices (index = 4x + 2y + z), 12 outward triangles."""
    V = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float)
    F = np.array([[0, 1, 3], [0, 3, 2],    # x = 0
                  [4, 6, 7], [4, 7, 5],    # x = 1
                  [0, 4, 5], [0, 5, 1],    # y = 0
                  [2, 3, 7], [2, 7, 6],    # y = 1
                  [0, 2, 6], [0, 6, 4],    # z = 0
                  [1, 5, 7], [1, 7, 3]])   # z = 1
    return V, F


def make_flat_grid(n=21):
    """n x n points in the plane z = 0, split into 2*(n-1)^2 triangles (800 for n = 21)."""
    xs, ys = np.meshgrid(np.arange(n, dtype=float), np.arange(n, dtype=float), indexing="ij")
    V = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(n * n)])
    F = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b, c, d = i * n + j, (i + 1) * n + j, (i + 1) * n + j + 1, i * n + j + 1
            F += [(a, b, c), (a, c, d)]
    return V, np.array(F)


@pytest.fixture
def icosahedron():
    return make_icosahedron()


@pytest.fixture
def cube():
    return make_cube()


@pytest.fixture
def flat_grid():
    return make_flat_grid()
