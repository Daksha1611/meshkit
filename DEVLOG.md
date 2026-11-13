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
