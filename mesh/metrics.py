"""Measuring how much a simplified mesh differs from the original.

The question is "how far is the new surface from the old one?". We answer
it by scattering random points on one surface and measuring each point's
distance to the other surface, in both directions. The mean of those
distances is the typical error; the largest is an estimate of the Hausdorff
distance (the worst spot). Both are reported as a percentage of the
original model's bounding-box diagonal so that models of different sizes
can be compared.
"""

import math

import numpy as np
from scipy.spatial import cKDTree

from .mesh import bbox_diagonal, dot3, face_areas, face_normals, norm3


def surface_samples(V, F, n, seed=0):
    """n random points spread evenly over the surface (area-weighted).

    A face is chosen with probability proportional to its area, so a big
    triangle gets more points than a small one. Inside the triangle we use
    r1 = sqrt(u): without the square root the points would bunch up near
    corner a.
    """
    rng = np.random.default_rng(seed)
    area = face_areas(V, F)
    faces = rng.choice(len(F), size=n, p=area / math.fsum(area))   # fsum: exact, same on every CPU
    r1 = np.sqrt(rng.random(n))[:, None]
    r2 = rng.random(n)[:, None]
    a, b, c = V[F[faces, 0]], V[F[faces, 1]], V[F[faces, 2]]
    return (1 - r1) * a + r1 * (1 - r2) * b + r1 * r2 * c


def _safe_div(num, den):
    """num / den, giving 0 where den is 0 (only happens for zero-area triangles)."""
    return np.divide(num, den, out=np.zeros_like(num), where=den != 0)


def closest_point_on_triangles(P, A, B, C):
    """Exact closest point on triangle (A[i], B[i], C[i]) to point P[i], for all i.

    Follows Ericson, Real-Time Collision Detection, section 5.1.5. The plane
    around a triangle splits into 7 regions: near corner a, b or c, near
    edge ab, ac or bc, or above the face. Ericson's code tests them one by
    one and returns at the first match. Here every test is done for all
    points at once; we fill in the answers from the last test to the first,
    so the earliest matching test overwrites the later ones, giving the same
    result as the sequential code.
    """
    ab, ac = B - A, C - A
    ap, bp, cp = P - A, P - B, P - C
    d1, d2 = dot3(ab, ap), dot3(ac, ap)
    d3, d4 = dot3(ab, bp), dot3(ac, bp)
    d5, d6 = dot3(ab, cp), dot3(ac, cp)
    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4

    # 7. Inside the face: barycentric coordinates (u, v, w).
    denom = va + vb + vc
    v = _safe_div(vb, denom)
    w = _safe_div(vc, denom)
    result = A + ab * v[:, None] + ac * w[:, None]

    def put(mask, points):
        result[mask] = points[mask]

    # 6. Edge bc
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    t = _safe_div(d4 - d3, (d4 - d3) + (d5 - d6))
    put(m, B + (C - B) * t[:, None])
    # 5. Edge ac
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    put(m, A + ac * _safe_div(d2, d2 - d6)[:, None])
    # 4. Corner c
    put((d6 >= 0) & (d5 <= d6), C)
    # 3. Edge ab
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    put(m, A + ab * _safe_div(d1, d1 - d3)[:, None])
    # 2. Corner b
    put((d3 >= 0) & (d4 <= d3), B)
    # 1. Corner a
    put((d1 <= 0) & (d2 <= 0), A)
    return result


def point_to_surface(P, V, F, k=16, dense=300000, seed=1):
    """Distance from each point in P to the surface (V, F).

    Returns the smaller of two upper bounds on the true distance:
      1. the exact distance to the k triangles whose centroids are nearest;
      2. the distance to the nearest of `dense` random points on the surface.
    Bound 1 is exact whenever the right triangle is among the k, which is
    nearly always for evenly sized triangles. It fails for long, thin
    triangles, whose centroid can be far from the part of the triangle
    that is near P. Bound 2 does not care about triangle shape. Each is an
    upper bound, so the minimum is the better estimate.
    """
    k = min(k, len(F))
    centroids = V[F].mean(axis=1)
    _, nearest = cKDTree(centroids).query(P, k=k)
    nearest = nearest.reshape(len(P), k)

    best = np.full(len(P), np.inf)
    for j in range(k):                       # one batch per candidate rank keeps memory small
        tri = F[nearest[:, j]]
        q = closest_point_on_triangles(P, V[tri[:, 0]], V[tri[:, 1]], V[tri[:, 2]])
        best = np.minimum(best, norm3(P - q))

    if dense:
        samples = surface_samples(V, F, dense, seed)
        d_samples, _ = cKDTree(samples).query(P)
        best = np.minimum(best, d_samples)
    return best


def shape_error(V_ref, F_ref, V_new, F_new, n=30000, seed=0):
    """Two-sided surface distance between the original and the new mesh.

    Points on the original are measured against the new mesh (finds parts
    that were cut away), and points on the new mesh against the original
    (finds parts that bulge out). Returns mean and max as % of the
    original's bounding-box diagonal; the max approximates the Hausdorff
    distance.
    """
    on_ref = surface_samples(V_ref, F_ref, n, seed)
    on_new = surface_samples(V_new, F_new, n, seed + 1)
    d = np.concatenate([point_to_surface(on_ref, V_new, F_new),
                        point_to_surface(on_new, V_ref, F_ref)])
    diag = bbox_diagonal(V_ref)
    return {"mean_pct": 100.0 * math.fsum(d) / len(d) / diag, "max_pct": 100.0 * d.max() / diag}


def flipped_fraction(V_ref, F_ref, V_new, F_new):
    """Fraction of new faces that point the opposite way to the original surface.

    Each new face is paired with the original face whose centroid is
    nearest; a negative dot product of their normals means the new face is
    turned over (shows up as a dark patch in a render).
    """
    _, nearest = cKDTree(V_ref[F_ref].mean(axis=1)).query(V_new[F_new].mean(axis=1))
    n_new = face_normals(V_new, F_new)
    n_ref = face_normals(V_ref, F_ref)[nearest]
    return float(np.mean(dot3(n_new, n_ref) < 0))
