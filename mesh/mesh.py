"""Basic facts about a triangle mesh (V, F).

Every function takes the vertex array V (n, 3) and/or the face array
F (m, 3) and returns plain NumPy arrays or Python containers. Nothing here
changes the mesh.
"""

import numpy as np


def _face_edges(F):
    """All 3*m edges of the faces, each with its two indices sorted (smaller first).

    Row 3*f + k is edge k of face f: (c0,c1), (c1,c2), (c2,c0).
    Sorting makes the edge a-b and the edge b-a look the same.
    """
    E = F[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
    return np.sort(E, axis=1)


def edges(F):
    """The unique undirected edges of the mesh as an (e, 2) array, sorted."""
    return np.unique(_face_edges(F), axis=0)


def edge_face_count(F):
    """A dict mapping each edge (a, b) with a < b to the number of faces using it.

    In a clean (manifold) mesh an inside edge has 2 faces and an edge on a
    hole or open border has exactly 1.
    """
    E, counts = np.unique(_face_edges(F), axis=0, return_counts=True)
    return {(int(a), int(b)): int(c) for (a, b), c in zip(E, counts)}


def boundary_edges(F):
    """The edges used by exactly one face (the rims of holes), as an (k, 2) array."""
    E, counts = np.unique(_face_edges(F), axis=0, return_counts=True)
    return E[counts == 1]


def boundary_edges_with_faces(F):
    """Boundary edges in the direction their single face walks them, plus that face.

    Returns (B, owner): B is (k, 2) with B[i] = (a, b) as it appears in face
    owner[i]. The quadric code needs the owning face to build a plane that
    stands upright on the hole's rim.
    """
    directed = F[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
    undirected = np.sort(directed, axis=1)
    _, first, counts = np.unique(undirected, axis=0, return_index=True, return_counts=True)
    rows = first[counts == 1]          # row number in the 3*m list of edges
    return directed[rows], rows // 3   # each face contributes 3 rows


def boundary_loops(F):
    """Number of separate holes: groups of boundary edges joined end to end."""
    B = boundary_edges(F)
    neighbours = {}
    for a, b in B.tolist():
        neighbours.setdefault(a, []).append(b)
        neighbours.setdefault(b, []).append(a)
    seen, loops = set(), 0
    for start in neighbours:
        if start in seen:
            continue
        loops += 1
        stack = [start]                       # walk around this hole
        while stack:
            v = stack.pop()
            if v not in seen:
                seen.add(v)
                stack.extend(neighbours[v])
    return loops


def euler_characteristic(V, F):
    """Euler characteristic chi = V - E + F, counting only vertices that faces use.

    A closed surface with g handles has chi = 2 - 2g, and every hole lowers
    chi by 1. So a sphere-like closed mesh gives 2. If a simplification step
    changes chi, it broke the topology.
    """
    used = len(np.unique(F))
    return used - len(edges(F)) + len(F)


def face_normals(V, F, unit=True):
    """Normal of each face from the cross product of two of its sides.

    The length of the raw cross product is twice the triangle's area;
    unit=True scales each normal to length 1 (zero-area faces stay 0).
    """
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    N = np.cross(b - a, c - a)
    if unit:
        length = np.linalg.norm(N, axis=1, keepdims=True)
        N = N / np.where(length > 0, length, 1.0)
    return N


def face_areas(V, F):
    """Area of each triangle: half the length of the cross product."""
    return 0.5 * np.linalg.norm(face_normals(V, F, unit=False), axis=1)


def vertex_faces(n, F):
    """For each of the n vertices, the set of face indices that use it."""
    vf = [set() for _ in range(n)]
    for f, (a, b, c) in enumerate(F.tolist()):
        vf[a].add(f)
        vf[b].add(f)
        vf[c].add(f)
    return vf


def compact(V, F):
    """Drop vertices that no face uses and renumber the faces to match."""
    used = np.unique(F)
    new_index = -np.ones(len(V), dtype=np.int64)
    new_index[used] = np.arange(len(used))
    return V[used].copy(), new_index[F]


def bbox_diagonal(V):
    """Length of the bounding-box diagonal. Errors are reported as a % of this."""
    return float(np.linalg.norm(V.max(axis=0) - V.min(axis=0)))


def degenerate_faces(V, F, eps=1e-12):
    """Indices of faces that repeat a vertex or have (almost) zero area.

    The area threshold is relative to the model size (eps * diagonal^2), so
    it means the same for a model 1 unit or 1000 units across.
    """
    repeated = (F[:, 0] == F[:, 1]) | (F[:, 1] == F[:, 2]) | (F[:, 2] == F[:, 0])
    tiny = face_areas(V, F) <= eps * bbox_diagonal(V) ** 2
    return np.nonzero(repeated | tiny)[0]


def duplicate_faces(F):
    """Indices of faces that use the same three vertices as an earlier face."""
    key = np.sort(F, axis=1)
    _, first = np.unique(key, axis=0, return_index=True)
    is_first = np.zeros(len(F), dtype=bool)
    is_first[first] = True
    return np.nonzero(~is_first)[0]


def drop_doubled_faces(V, F):
    """Remove every copy of any triangle that appears more than once.

    A triangle stored twice (usually back to back, with opposite winding) is a
    zero-thickness flap: its edge is shared by 4 faces, which is not a valid
    surface. Removing only one copy would leave a 3-face edge, so both go.
    suzanne.obj has one such pair (see DEVLOG.md).
    """
    _, inverse, counts = np.unique(np.sort(F, axis=1), axis=0, return_inverse=True, return_counts=True)
    keep = counts[inverse.reshape(-1)] == 1
    return compact(V, F[keep])
