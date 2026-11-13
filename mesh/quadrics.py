"""Quadric error metrics (Garland & Heckbert, SIGGRAPH 1997).

Idea in one paragraph
---------------------
Every triangle lies in a plane a*x + b*y + c*z + d = 0 with (a, b, c) a unit
normal. The squared distance of a point v = (x, y, z, 1) from that plane is
(p . v)^2 = v^T (p p^T) v, where p = [a, b, c, d]. So the 4x4 matrix
K = p p^T "measures" squared distance to one plane. Matrices can be added,
so the sum Q of the K's of all faces around a vertex measures the sum of
squared distances to all those planes. When two vertices merge we just add
their Q's, which is why QEM is fast: the cost of any candidate point is one
small matrix product, no matter how many original faces it stands for.

Note on the arithmetic: the 3x3 determinant and solve are written out by
hand (cofactors and Cramer's rule) and dot products use mesh.dot3, instead
of np.linalg / np.einsum. Those library routines can round differently on
different CPUs, which changed the simplified meshes between my laptop and
GitHub's machines (DEVLOG.md). The hand-written versions give the same bits
everywhere.
"""

import numpy as np

from .mesh import boundary_edges_with_faces, dot3, face_areas, face_normals, norm3


def face_quadrics(V, F, area_weighted=True):
    """The 4x4 quadric K = p p^T of every face, shape (m, 4, 4).

    area_weighted=True multiplies each K by the face's area, so a big face
    counts more than a sliver. Without it, a region made of many tiny
    triangles would count as much as a large flat area.
    """
    n = face_normals(V, F, unit=True)
    d = -dot3(n, V[F[:, 0]])                       # plane passes through corner 0
    p = np.column_stack([n, d])                    # (m, 4): [a, b, c, d]
    K = p[:, :, None] * p[:, None, :]              # outer product per face
    if area_weighted:
        K *= face_areas(V, F)[:, None, None]
    return K


def vertex_quadrics(V, F, boundary_weight=1000.0, area_weighted=True):
    """Q for every vertex: the sum of K over the faces touching it, shape (n, 4, 4)."""
    K = face_quadrics(V, F, area_weighted)
    Q = np.zeros((len(V), 4, 4))
    for corner in range(3):
        # np.add.at adds correctly even when a vertex index repeats
        np.add.at(Q, F[:, corner], K)
    if boundary_weight > 0:
        add_boundary_quadrics(Q, V, F, boundary_weight)
    return Q


def add_boundary_quadrics(Q, V, F, weight):
    """Add a heavy "wall" plane along every boundary edge so holes keep their shape.

    A boundary edge (a, b) has a face on only one side, so moving its
    vertices sideways along the surface costs nothing in the normal
    quadrics. The hole would shrink. We add a plane that contains the edge
    and stands perpendicular to the face (normal m = edge x face normal);
    moving off the rim then costs weight * |e|^2 * distance^2.
    """
    B, owner = boundary_edges_with_faces(F)
    if len(B) == 0:
        return Q
    a, b = B[:, 0], B[:, 1]
    e = V[b] - V[a]
    n = face_normals(V, F[owner], unit=True)
    m = np.cross(e, n)
    m /= np.maximum(norm3(m), 1e-300)[:, None]
    p = np.column_stack([m, -dot3(m, V[a])])
    K = p[:, :, None] * p[:, None, :] * (weight * dot3(e, e))[:, None, None]
    np.add.at(Q, a, K)
    np.add.at(Q, b, K)
    return Q


def det3(A):
    """Determinant of 3x3 matrices A[..., 3, 3] by cofactor expansion along the first row."""
    return (A[..., 0, 0] * (A[..., 1, 1] * A[..., 2, 2] - A[..., 1, 2] * A[..., 2, 1])
            - A[..., 0, 1] * (A[..., 1, 0] * A[..., 2, 2] - A[..., 1, 2] * A[..., 2, 0])
            + A[..., 0, 2] * (A[..., 1, 0] * A[..., 2, 1] - A[..., 1, 1] * A[..., 2, 0]))


def solve3(A, b, det):
    """Solve A x = b for 3x3 systems with Cramer's rule: x_i = det(A with column i := b) / det(A)."""
    x = np.empty(b.shape)
    for i in range(3):
        Ai = A.copy()
        Ai[..., :, i] = b
        x[..., i] = det3(Ai) / det
    return x


def _is_well_conditioned(A, det):
    """True where |det A| is large compared with the size of A's entries.

    A is (nearly) singular when all planes are parallel, e.g. in a flat
    area: every point on the plane is then equally good and the solve is
    unstable, so we fall back to simple candidates instead.
    """
    scale = np.abs(A).max(axis=(-2, -1))
    return (scale > 0) & (np.abs(det) > 1e-9 * scale ** 3)


def _batch_cost(Qs, P):
    """Quadric error of point P[i] under Qs[i]: v^T A v + 2 b.v + c (clamped at 0)."""
    A, b, c = Qs[:, :3, :3], Qs[:, :3, 3], Qs[:, 3, 3]
    Av = A[:, :, 0] * P[:, 0, None] + A[:, :, 1] * P[:, 1, None] + A[:, :, 2] * P[:, 2, None]
    return np.maximum(dot3(P, Av) + 2.0 * dot3(b, P) + c, 0.0)


def quadric_cost(Q, v):
    """Error of point v under one quadric Q."""
    return float(_batch_cost(Q[None], np.asarray(v, dtype=float)[None])[0])


def optimal_point(Q, p1, p2, placement="optimal"):
    """Best position for the merged vertex of edge (p1, p2) and its cost.

    placement:
      "optimal"  - solve A v = -b for the point of least error, if it is safe
      "midpoint" - always the middle of the edge (ablation study)
      "endpoint" - the cheaper of the two ends (ablation study)

    Returns (cost, point). This is the readable one-edge version; the
    simplifier uses optimal_points_batch, which follows the same rules.
    """
    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    mid = 0.5 * (p1 + p2)
    if placement == "midpoint":
        return quadric_cost(Q, mid), mid
    if placement == "endpoint":
        c1, c2 = quadric_cost(Q, p1), quadric_cost(Q, p2)
        return (c1, p1.copy()) if c1 <= c2 else (c2, p2.copy())

    A, b = Q[:3, :3], Q[:3, 3]
    det = det3(A)
    if _is_well_conditioned(A, det):
        v = solve3(A, -b, det)
        # Distance guard: a badly conditioned solve can land far away and
        # create a spike. Accept only points close to the edge.
        if norm3(v - mid) <= 2.0 * norm3(p2 - p1):
            return quadric_cost(Q, v), v

    # Fallback: the cheapest of the two ends and the middle.
    candidates = [(quadric_cost(Q, p), i) for i, p in enumerate((p1, p2, mid))]
    cost, i = min(candidates)
    return cost, (p1, p2, mid)[i].copy()


def optimal_points_batch(Qs, P1, P2, placement="optimal"):
    """optimal_point for k edges at once: Qs (k,4,4), P1 and P2 (k,3).

    Same rules as optimal_point, written with NumPy batch operations
    because the simplifier calls it after every collapse for all edges
    around the merged vertex (and once for all edges at the start).
    Returns (costs (k,), points (k,3)).
    """
    mid = 0.5 * (P1 + P2)
    if placement == "midpoint":
        return _batch_cost(Qs, mid), mid

    # Cost of the three simple candidates: end 1, end 2, middle.
    cands = np.stack([P1, P2, mid])                                # (3, k, 3)
    cand_cost = np.stack([_batch_cost(Qs, c) for c in cands])      # (3, k)
    if placement == "endpoint":
        pick = np.argmin(cand_cost[:2], axis=0)
    else:
        pick = np.argmin(cand_cost, axis=0)
    k = np.arange(len(Qs))
    best_cost = cand_cost[pick, k]
    best_point = cands[pick, k]
    if placement == "endpoint":
        return best_cost, best_point

    # Try the optimal point where A is well conditioned (same test as above).
    A, b = Qs[:, :3, :3], Qs[:, :3, 3]
    det = det3(A)
    idx = np.nonzero(_is_well_conditioned(A, det))[0]
    if len(idx):
        v = solve3(A[idx], -b[idx], det[idx])
        near = norm3(v - mid[idx]) <= 2.0 * norm3(P2[idx] - P1[idx])
        idx, v = idx[near], v[near]
        best_cost[idx] = _batch_cost(Qs[idx], v)
        best_point[idx] = v
    return best_cost, best_point
