"""Mesh simplification by greedy edge collapse with quadric error metrics.

How it works (Garland & Heckbert 1997):
  1. Give every vertex a quadric Q (quadrics.py) that measures squared
     distance to the planes of its original faces.
  2. For every edge (a, b), find the best point for the merged vertex
     under Q[a] + Q[b] and its cost. Put all edges in a priority queue.
  3. Repeatedly take the cheapest edge and collapse it: b is merged into a,
     a moves to the best point, and the 2 faces on the edge disappear.
  4. Q[a] becomes Q[a] + Q[b], so the merged vertex remembers the planes of
     both. The edges around a are re-costed and pushed again.
  5. Stop when the mesh has the target number of faces.

Two safety checks reject a collapse that would damage the mesh:
  * the link condition (topology: no pinches, Euler number stays the same)
  * the fold check (geometry: no triangle turns over)

The baseline method, vertex clustering (Rossignac & Borrel 1993), is at the
bottom of this file.
"""

import heapq
import itertools
import time

import numpy as np

from .mesh import bbox_diagonal, compact, dot3, edges, norm3, vertex_faces
from .quadrics import optimal_points_batch, vertex_quadrics


class Simplifier:
    """Holds a mesh while it is simplified step by step.

    run(target) can be called several times with smaller and smaller
    targets; result() after each call gives one level of detail. That way
    a single simplifier produces a whole LOD chain.
    """

    def __init__(self, V, F, boundary_weight=1000.0, check_flips=True, flip_threshold=0.2,
                 area_weighted=True, placement="optimal"):
        self.V = np.array(V, dtype=np.float64, copy=True)
        self.F = np.array(F, dtype=np.int64, copy=True)   # changed in place by collapses
        self.check_flips = check_flips
        self.flip_threshold = flip_threshold
        self.placement = placement

        n, m = len(self.V), len(self.F)
        self.f_alive = np.ones(m, dtype=bool)
        self.vf = vertex_faces(n, self.F)                 # vertex -> set of face ids
        self.v_alive = [len(s) > 0 for s in self.vf]      # plain lists: faster than
        self.version = [0] * n                            # NumPy for single items
        self.Q = vertex_quadrics(self.V, self.F, boundary_weight, area_weighted)
        self.faces_left = m
        self.stats = {"collapses": 0, "rejected_flip": 0, "rejected_link": 0, "seconds": 0.0}

        # A face normal (its length is twice the area) shorter than this
        # counts as zero: the face would be squashed flat.
        self.min_normal = 1e-12 * bbox_diagonal(self.V) ** 2

        # The counter is the 2nd element of every heap entry. When two costs
        # are equal Python compares the next element; without the counter it
        # would reach the NumPy point and raise "truth value is ambiguous".
        self.counter = itertools.count()
        self._build_heap()

    # ------------------------------------------------------------------ setup
    def _build_heap(self):
        """Cost every edge once (vectorised) and build the priority queue."""
        E = edges(self.F)
        a, b = E[:, 0], E[:, 1]
        cost, points = optimal_points_batch(self.Q[a] + self.Q[b], self.V[a], self.V[b], self.placement)

        # Remember each vertex's cheapest edge. This is exactly what the queue
        # sorts by, and run_experiments.py shows it as a heat map.
        self.initial_vertex_cost = np.full(len(self.V), np.inf)
        np.minimum.at(self.initial_vertex_cost, a, cost)
        np.minimum.at(self.initial_vertex_cost, b, cost)

        self.heap = [(c, next(self.counter), int(i), int(j), 0, 0, p)
                     for c, i, j, p in zip(cost.tolist(), a, b, points)]
        heapq.heapify(self.heap)

    # ---------------------------------------------------------------- helpers
    def neighbours(self, v):
        """The set of vertices joined to v by an edge."""
        ring = set(self.F[list(self.vf[v])].ravel().tolist())
        ring.discard(v)
        return ring

    def _passes_link_condition(self, a, b, shared):
        """True if collapsing (a, b) keeps the surface manifold.

        a and b may only have as many common neighbours as they have shared
        faces (2 inside, 1 on a boundary). An extra common neighbour c means
        the edges a-c and b-c would be merged into one edge used by 3 or 4
        faces: a pinch that changes the topology.
        """
        return len(self.neighbours(a) & self.neighbours(b)) == len(shared)

    def _causes_fold(self, a, b, shared, point):
        """True if moving a and b to `point` would flip or squash a face.

        Only the faces that survive the collapse matter (the shared ones are
        deleted). For each, compare the normal before and after the move.
        Vectorised because CAD meshes have vertices with 100+ faces; with a
        Python loop over the faces, Fandisk -> 2% took 6.6 s instead of 3.3 s
        (see DEVLOG.md).
        """
        others = list((self.vf[a] | self.vf[b]) - shared)
        if not others:
            return False
        tri = self.F[others]                         # (k, 3) vertex ids
        P = self.V[tri]                              # (k, 3, 3) corner positions
        old = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        P[(tri == a) | (tri == b)] = point           # move the merged corner
        new = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])

        len_old = norm3(old)
        len_new = norm3(new)
        if np.any(len_new <= self.min_normal):
            return True                              # face would become a line
        valid = len_old > self.min_normal            # an already-flat face has no direction
        cos = dot3(old[valid], new[valid]) / (len_old[valid] * len_new[valid])
        return bool(np.any(cos < self.flip_threshold))

    def _collapse(self, a, b, shared, point):
        """Merge vertex b into vertex a, which moves to `point`."""
        for f in shared:                             # the faces on edge (a, b) vanish
            self.f_alive[f] = False
            for v in self.F[f].tolist():
                self.vf[v].discard(f)

        rest = list(self.vf[b])                      # b's other faces now use a
        if rest:
            corners = self.F[rest]
            corners[corners == b] = a
            self.F[rest] = corners
            self.vf[a].update(rest)
        self.vf[b] = set()
        self.v_alive[b] = False

        self.V[a] = point
        self.Q[a] += self.Q[b]                       # quadrics add up
        self.version[a] += 1                         # old queue entries of a are now stale
        self.faces_left -= len(shared)
        self.stats["collapses"] += 1

    def _recost_around(self, a):
        """Push fresh entries for every edge (a, n) after a has moved."""
        ring = list(self.neighbours(a))
        if not ring:
            return
        Qs = self.Q[a] + self.Q[ring]
        P1 = np.broadcast_to(self.V[a], (len(ring), 3))
        cost, points = optimal_points_batch(Qs, P1, self.V[ring], self.placement)
        va = self.version[a]
        for n, c, p in zip(ring, cost.tolist(), points):
            heapq.heappush(self.heap, (c, next(self.counter), a, n, va, self.version[n], p))

    # -------------------------------------------------------------- main loop
    def run(self, target_faces):
        """Collapse the cheapest valid edges until at most target_faces remain."""
        start = time.perf_counter()
        while self.faces_left > target_faces and self.heap:
            _, _, a, b, va, vb, point = heapq.heappop(self.heap)

            # Lazy deletion: instead of removing outdated entries from the heap
            # (slow), we skip them when they come out. An entry is outdated if
            # a vertex died or moved since it was pushed.
            if not (self.v_alive[a] and self.v_alive[b]):
                continue
            if self.version[a] != va or self.version[b] != vb:
                continue
            shared = self.vf[a] & self.vf[b]
            if not shared:
                continue

            if not self._passes_link_condition(a, b, shared):
                self.stats["rejected_link"] += 1
                continue
            if self.check_flips and self._causes_fold(a, b, shared, point):
                self.stats["rejected_flip"] += 1
                continue

            self._collapse(a, b, shared, point)
            self._recost_around(a)
        self.stats["seconds"] += time.perf_counter() - start
        return self

    def result(self):
        """The current mesh as compact (V, F) arrays (copies)."""
        return compact(self.V, self.F[self.f_alive])


def simplify(V, F, ratio=None, target_faces=None, **kwargs):
    """Simplify (V, F) to `target_faces` triangles or to `ratio` of the original.

    Extra keyword arguments go to Simplifier (boundary_weight, check_flips,
    flip_threshold, area_weighted, placement). Returns (V2, F2, stats);
    stats["seconds"] includes building the queue.
    """
    if target_faces is None:
        if ratio is None:
            raise ValueError("give ratio or target_faces")
        target_faces = int(round(ratio * len(F)))
    start = time.perf_counter()
    s = Simplifier(V, F, **kwargs)
    s.run(target_faces)
    V2, F2 = s.result()
    stats = dict(s.stats)
    stats["seconds"] = time.perf_counter() - start
    return V2, F2, stats


def cluster_simplify(V, F, cells):
    """Baseline: vertex clustering on a uniform grid (Rossignac & Borrel 1993).

    The bounding box is cut into cubes of side (largest box side / cells).
    All vertices in the same cube are replaced by their average. Faces whose
    corners fall into fewer than 3 different cubes disappear. It is fast and
    simple but ignores the shape: flat and detailed areas get the same grid.
    """
    lo = V.min(axis=0)
    size = (V.max(axis=0) - lo).max() / cells
    cell = np.floor((V - lo) / size).astype(np.int64)
    cell = np.minimum(cell, cells - 1)               # the max corner falls exactly on the edge

    _, cluster = np.unique(cell, axis=0, return_inverse=True)
    cluster = cluster.reshape(-1)
    k = cluster.max() + 1
    total = np.zeros((k, 3))
    np.add.at(total, cluster, V)
    count = np.bincount(cluster, minlength=k)
    V2 = total / count[:, None]                      # average position per cube

    F2 = cluster[F]
    keep = (F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 2] != F2[:, 0])
    F2 = F2[keep]
    _, first = np.unique(np.sort(F2, axis=1), axis=0, return_index=True)
    F2 = F2[np.sort(first)]                          # drop duplicate faces, keep order
    return compact(V2, F2)
