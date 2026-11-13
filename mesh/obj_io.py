"""Reading and writing Wavefront OBJ files.

Only the parts of the format this project needs are handled:
``v x y z`` vertex lines and ``f ...`` face lines. Everything else
(normals, texture coordinates, materials, groups) is ignored.

A mesh is always represented by two NumPy arrays:
    V : (n, 3) float64, one row per vertex position
    F : (m, 3) int64,   one row per triangle, holding 0-based vertex indices
"""

import os

import numpy as np


def _parse_index(token, n_vertices_so_far):
    """Turn one face token (``7``, ``7/2``, ``7//3`` or ``7/2/3``) into a 0-based index.

    OBJ counts vertices from 1, and a negative index counts back from the
    last vertex read so far (-1 = the most recent vertex).
    """
    i = int(token.split("/")[0])  # the vertex index is the number before the first '/'
    if i > 0:
        return i - 1
    if i < 0:
        return n_vertices_so_far + i
    raise ValueError("OBJ face index 0 is invalid (indices start at 1)")


def load_obj(path, merge_duplicates=True):
    """Load an OBJ file and return (V, F) with every polygon split into triangles.

    Polygons with more than three corners are split as a fan around their
    first corner: (0,1,2), (0,2,3), (0,3,4), ... This is correct for the
    convex quads and pentagons found in the test models.

    merge_duplicates=True merges vertices that sit at exactly the same
    position. Many files store a separate copy of a vertex for each UV seam;
    if those copies are not merged, the simplifier sees a cut in the surface
    and tears it open.
    """
    vertices = []
    faces = []
    with open(path, "r") as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "v":
                vertices.append([float(x) for x in parts[1:4]])
            elif parts[0] == "f":
                corners = [_parse_index(tok, len(vertices)) for tok in parts[1:]]
                for k in range(1, len(corners) - 1):  # fan triangulation
                    faces.append((corners[0], corners[k], corners[k + 1]))

    V = np.array(vertices, dtype=np.float64).reshape(-1, 3)
    F = np.array(faces, dtype=np.int64).reshape(-1, 3)
    if merge_duplicates:
        V, F = merge_duplicate_vertices(V, F)
    return V, F


def merge_duplicate_vertices(V, F, decimals=9):
    """Merge vertices with identical positions and drop faces that collapse.

    Positions are rounded to ``decimals`` places so that copies written with
    tiny floating-point differences still match. The first copy of each
    position is kept and the original vertex order is preserved, so a file
    without duplicates comes back unchanged.
    """
    rounded = np.round(V, decimals)
    _, first_index, inverse = np.unique(rounded, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.reshape(-1)  # NumPy versions differ in the shape they return

    # np.unique sorts the positions. Re-order the unique vertices by where
    # they first appear in the file so the output follows the input order.
    order = np.argsort(first_index)
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))

    V_new = V[first_index[order]]
    F_new = rank[inverse[F]]

    # A face whose corners merged together is now a line or a point: drop it.
    keep = (F_new[:, 0] != F_new[:, 1]) & (F_new[:, 1] != F_new[:, 2]) & (F_new[:, 2] != F_new[:, 0])
    return V_new, F_new[keep]


def save_obj(path, V, F):
    """Write (V, F) as an OBJ file with 6-decimal positions and 1-based faces."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w") as f:
        f.write(f"# meshkit: {len(V)} vertices, {len(F)} triangles\n")
        f.write("\n".join(f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in V))
        f.write("\n")
        f.write("\n".join(f"f {a + 1} {b + 1} {c + 1}" for a, b, c in F))
        f.write("\n")
