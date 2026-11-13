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

## 2026-11-13: Phase 4, centroid lookup gives fake errors on Fandisk

**What happened.** The plan warned that a distance based only on the 16 triangles with
the nearest centroids can be badly wrong on CAD models, so I wrote `point_to_surface`
with a second bound from the start, then tested what the centroid lookup alone would have
reported. On the simplified Fandisk it gives a max error of 8.9% of the diagonal for a
mesh whose real max error is 0.3%.

**How I found it.** I measured each Fandisk level twice, once with the centroid lookup alone
and once also using a second bound (distance to the nearest of 300,000 random points on
the surface), and printed the shape of the simplified triangles. Simplifying the large flat
CAD faces leaves long, thin triangles (worst aspect ratio 460 at 20%; median 2.6). The
centroid of such a triangle is far from the parts of it near the query point, so the
right triangle is not among the 16 candidates and the distance is overestimated.

**Fix.** Return the minimum of the two upper bounds.

| Fandisk | centroid only (mean / max) | both bounds (mean / max) |
|---|---|---|
| 20% | 0.113% / 8.866% | 0.006% / 0.293% |
| 5% | 0.113% / 8.630% | 0.011% / 0.282% |
| 2% | 0.076% / 6.490% | 0.027% / 0.437% |

Sanity checks after the fix: Spot against itself gives a mean of about 1e-15%; a copy
shifted by 1% of the diagonal gives a max of 1.000% and a mean of 0.530%.

## 2026-11-13: Phase 5, Suzanne's Euler number jumped after subdivision

**What happened.** Loop subdivision kept the Euler number on the icosahedron (2 at every
level) and on Spot, but Suzanne went from 1 to 4 after one level and to 16 after two.

**How I found it.** Counting faces per edge showed one edge of Suzanne used by 4 faces.
Two of those faces are the same triangle (vertices 70, 135, 136 after merging) stored
twice with opposite winding. In `suzanne.obj` the quads on lines 1170 and 1171
(`71 197 139 138` and `71 138 139 198`) share vertex 71 and edge 138-139, so the fan split
around vertex 71 produces the triangle 71-138-139 from both. Subdivision then splits both
copies, and the non-manifold edges multiply: 1 -> 5 -> 22.

**Fix.** New helper `drop_doubled_faces` removes every copy of a repeated triangle (removing
just one copy still leaves an edge with 3 faces). The cleaned Suzanne has 966 triangles,
0 non-manifold edges, 42 boundary edges and Euler characteristic 0, which stays 0 after
1 and 2 levels of subdivision. The experiments clean Suzanne this way before subdividing it.

Other numbers from this phase: icosahedron radius spread (std / mean) after 1, 2, 3 levels
is 1.36%, 0.89%, 0.80%.

## 2026-11-13: Phase 9, experiments

**NaN colours in the heat map.** The first full run printed two warnings
(`invalid value encountered in subtract` inside `np.percentile`, and an invalid cast in the
renderer). The bunny heat map was the cause: `stanford-bunny.obj` lists 35,947 vertices but
faces use only 34,834. The other 1,113 have no edges, so their "cheapest collapse cost" is
infinity, and the percentile of a list containing infinity is NaN. I checked that the stray
vertices do not change any error figure: all 1,113 lie inside the bounding box of the
surface, so the diagonal is the same (0.250247) with or without them.
Fix: the experiment script loads every model through `compact`, so vertex counts in the
tables now mean "vertices used by faces" (bunny: 34,834), and `heat_colours` ignores
non-finite values when choosing its colour range. `meshkit.py info` prints both counts.

**Camera for the "from below" view.** The plan says `rot=(90,0,0)` to see the bunny's base.
In my renderer (Rz·Ry·Rx, camera looking down -z, y up) a +90° turn about x brings the
*top* of the bunny towards the camera; the first A2 image showed no holes at all. With
`rot=(-90,0,0)` the base faces the camera and the holes are visible.

**Results that differ from the reference run (reported as measured).**
- QEM vs clustering: mean error 3.0x to 4.6x lower for QEM, the same range as the reference.
  The first runs said 2.9x at the smallest size (368 triangles). That run still loaded the
  1,113 unused bunny vertices, and vertex clustering averages *every* vertex in a grid cell,
  used or not, so the stray vertices nudged the baseline's merged positions. After loading
  through `compact`, the clustering error at grid 8 is 0.844% instead of 0.841% and the
  ratio rounds to 3.0x. A small effect, but a real side effect of the unused vertices.
- A1: switching the fold check off does *not* raise the mean error at bunny 1% (0.156% on,
  0.148% off); it raises the share of turned-over faces from 0.29% to 2.59%. The error
  measure only looks at distance, not facing direction, so it cannot see this damage.
- A3: Spot at 2% loses its horns with area weighting on, as expected. With it off the horns
  survive, the mean error rises (0.618% -> 0.715%) and the max error falls (5.088% -> 4.053%).
  I checked where the max error sits with weighting on: the worst sample is at y = 0.949,
  just below the top of the model (y max 0.954), i.e. a horn tip; with it off, the worst
  sample moves to the legs (y = -0.539).

**Run time.** 346 s in total on my laptop, 93 s of it before the ablation study
(the ablations re-run the full bunny simplification 8 times).

## 2026-11-13: First CI run, results reproduce exactly but every PNG "changed"

**What happened.** The first push to GitHub triggered `results.yml`, which re-ran all the
experiments on a GitHub runner (NumPy 2.4.6, SciPy 1.17.1; my laptop has NumPy 2.5.4,
SciPy 1.18.1) and opened pull request #1. Its body said 0 numbers changed in
`summary.json` (only timings differ), but it listed all 54 PNG files as changed.

**How I found the cause.** I downloaded two of the CI images and compared them with mine
pixel by pixel: 0 pixels differ. Only the compressed bytes differ (the runner's zlib
compresses differently), so GitHub would have shown 54 "changed" images that look identical.
The good news hidden in this: every error figure, triangle count and file size came out
exactly the same on a different machine with different library versions.

**Fix.** `scripts/summary_diff.py` now compares changed PNGs with the committed version
pixel by pixel and restores the ones that only differ in bytes, and it tells the workflow
whether anything besides timings changed. `results.yml` opens a pull request only in that
case, and a run started on a branch other than main gets its own PR branch
(`auto/update-results-<branch>`), so a demo run cannot overwrite the main one.
Tested locally: the CI copy of `A1_fold_check.png` is restored and reported as unchanged;
a copy with a painted square is reported as changed. PR #1 was closed because it contained
no visible change.

## 2026-11-13: The renders were not deterministic across machines

**What happened.** For the image-diff demo I pushed a branch that loosens the fold check
(`flip_threshold` 0.2 -> 0.0) and ran `results.yml` on it (pull request #2). Most changed
images made sense, but two could not have been affected: `bunny_100pct.png` (the original,
unsimplified bunny: 53 pixels differ, by at most 7 colour levels) and `suzanne_strip.png`
(subdivision only: 754 pixels, up to 53 levels). In PR #1, made on another runner, the
original bunny had been pixel-identical.

**Cause.** The painter's algorithm sorts faces with `np.argsort(depth)`. The default sort is
not stable, and NumPy chooses a SIMD sorting routine based on the CPU, so faces at exactly
the same depth can be drawn in a different order on a different machine. Ties are common:
Suzanne is mirror-symmetric, so all 15,456 faces of the level-2 mesh share their depth with
their mirror twin, and 11,512 of the bunny's 69,451 faces share a depth with another face. On
my laptop, the default and the stable sort already order 7,667 of Suzanne's faces differently.

**Fix.** `np.argsort(depth, kind="stable")`: equal depths keep their face order everywhere.
I re-ran the experiments and pushed to main; the check is that `results.yml` on GitHub
now produces pixel-identical images and therefore opens no pull request.
