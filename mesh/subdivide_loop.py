"""Loop subdivision (Charles Loop, 1987).

Each level splits every triangle into 4 and moves the points so the mesh
gets smoother. In the limit (infinitely many levels) the surface is a
smooth "box-spline" surface, the triangle cousin of the cubic B-spline
from our splines lectures.

One level:
  1. Add a new "edge point" on every edge.
  2. Move every old vertex towards the average of its neighbours.
  3. Replace each triangle by 4 smaller ones using the new points.
"""

import numpy as np


def _edge_table(F):
    """Number every edge and record which edge each face side is.

    Returns (E, side_edge):
      E         : (e, 2) unique edges (smaller index first)
      side_edge : (m, 3), side_edge[f, k] = edge id of side k of face f,
                  where side 0 = (c0, c1), side 1 = (c1, c2), side 2 = (c2, c0).
    """
    sides = np.sort(F[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    E, inverse = np.unique(sides, axis=0, return_inverse=True)
    return E, inverse.reshape(-1, 3)


def _loop_beta(k):
    """Warren's weight for an inside vertex with k neighbours."""
    return np.where(k == 3, 3.0 / 16.0, 3.0 / (8.0 * np.maximum(k, 1)))


def _subdivide_once(V, F):
    n = len(V)
    E, side_edge = _edge_table(F)
    n_edges = len(E)

    # --- 1. Edge points -------------------------------------------------
    # The corner opposite side k of a face is corner (k + 2) % 3.
    faces_on_edge = np.bincount(side_edge.ravel(), minlength=n_edges)
    opposite_sum = np.zeros((n_edges, 3))
    for k in range(3):
        np.add.at(opposite_sum, side_edge[:, k], V[F[:, (k + 2) % 3]])
    a, b = V[E[:, 0]], V[E[:, 1]]
    inside = faces_on_edge == 2
    # Inside edge (a,b) with opposite corners c,d: 3/8 (a+b) + 1/8 (c+d).
    # Boundary edge: just the midpoint, so the border stays a curve of its own.
    edge_points = np.where(inside[:, None], 3.0 / 8.0 * (a + b) + 1.0 / 8.0 * opposite_sum, 0.5 * (a + b))

    # --- 2. Move the old vertices ----------------------------------------
    degree = np.bincount(E.ravel(), minlength=n)
    neighbour_sum = np.zeros((n, 3))
    np.add.at(neighbour_sum, E[:, 0], V[E[:, 1]])
    np.add.at(neighbour_sum, E[:, 1], V[E[:, 0]])
    beta = _loop_beta(degree)[:, None]
    new_V = (1.0 - degree[:, None] * beta) * V + beta * neighbour_sum

    # Boundary vertices follow the 1D cubic B-spline rule along the border:
    # 3/4 v + 1/8 (u + w), using only their two boundary neighbours u and w.
    B = E[faces_on_edge == 1]
    if len(B):
        b_degree = np.bincount(B.ravel(), minlength=n)
        b_sum = np.zeros((n, 3))
        np.add.at(b_sum, B[:, 0], V[B[:, 1]])
        np.add.at(b_sum, B[:, 1], V[B[:, 0]])
        on_boundary = b_degree > 0
        regular = b_degree == 2
        new_V[on_boundary] = V[on_boundary]                      # corners stay put
        new_V[regular] = 0.75 * V[regular] + 0.125 * b_sum[regular]

    # --- 3. Four triangles per old triangle --------------------------------
    # Edge point of edge id i gets vertex number n + i.
    c0, c1, c2 = F[:, 0], F[:, 1], F[:, 2]
    ab, bc, ca = (n + side_edge[:, 0], n + side_edge[:, 1], n + side_edge[:, 2])
    new_F = np.concatenate([
        np.column_stack([c0, ab, ca]),
        np.column_stack([c1, bc, ab]),
        np.column_stack([c2, ca, bc]),
        np.column_stack([ab, bc, ca]),
    ])
    return np.vstack([new_V, edge_points]), new_F


def loop_subdivide(V, F, levels=1):
    """Apply `levels` rounds of Loop subdivision. Faces grow 4x per level."""
    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    for _ in range(levels):
        V, F = _subdivide_once(V, F)
    return V, F
