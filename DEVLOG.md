# Development log

Each entry records something that went wrong or changed during development:
what happened, how I found it, how I fixed it, and the numbers before and after.

## 2026-11-13: Project started

Set up the repository, the virtual environment (Python 3.12, NumPy 2.5, SciPy 1.18,
Matplotlib 3.11, Pillow 13) and downloaded the five test models. Face counts
match the expected values: bunny 69,451, Spot 5,856, Fandisk 12,946,
Suzanne 500 (quads), teapot 6,320.

## 2026-11-13: Phase 1, loader check

All models load (bunny in 0.27 s). Topology matches the expected values:
bunny 35,947 vertices, Euler characteristic -3, 223 boundary edges (holes in the
scanned base); Spot Euler 2 with 0 boundary edges; Fandisk Euler 2.
One surprise: `duplicate_faces` finds 1 duplicate triangle in `suzanne.obj`
(968 triangles after splitting quads). It is in the source file, not a loader bug
(the loader only splits quads and merges vertices). I left the file as it is;
Suzanne is only used for subdivision, where a duplicate face does no harm.

## 2026-11-13: Phase 3, simplifier timings and a difference from the reference

**Timings.** Bunny 69,451 -> 1% (695 triangles) with all seven LOD snapshots taken on
the way: 18.7 s cumulative. Spot -> 2%: 1.4 s. Fandisk -> 2%: 3.5 s. The triangle counts
at 50/20/10/5/2/1/0.5% are 34,726 / 13,890 / 6,944 / 3,472 / 1,389 / 695 / 346, and
the bunny keeps Euler characteristic -3 at every level.

**Extra topology check.** The spec's link condition only compares common neighbours with
shared faces. I was worried that two vertices on *different* hole rims of the bunny could
still be merged through an inside edge, creating a pinch (a vertex where two holes touch)
without changing the Euler number. So I counted vertices touching a number of boundary
edges other than 0 or 2, and edges used by more than 2 faces: 0 and 0 at 10%, 2%, 1% and
0.5%. No change needed.

**Fold check: loop vs vectorised.** I wrote the fold check with NumPy from the start, so I
did not hit the "Fandisk takes minutes" problem. To check that the vectorisation is worth
its complexity, I timed a plain Python loop version on Fandisk -> 2%: 6.6 s versus 3.3 s
(same final mesh). Here it is a 2x win, not a dramatic one; I corrected the comment in
`simplify.py`, which first claimed a bigger speed-up that I had not measured.

**Rejection counts differ from the reference.** Fandisk -> 2% rejects 859 collapses in the
fold check and 3 in the link condition; the reference run reported about 22,000 and about
1,100. My simplifier drops an edge after rejecting it and only re-costs it when one of its
two vertices changes, so the same bad edge is not popped again and again. The final meshes
are still valid (Euler 2, no degenerate faces), so I am reporting my own counts.
