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

## 2026-11-13: Simplification results depended on the CPU

**What happened.** After the stable-sort fix I pushed to main and `results.yml` ran again
(pull request #3). This time 33 *numbers* changed, not just pixels: for example Spot at 2%
went from a mean error of 0.618% to 0.595%, and Fandisk at 2% from 859 to 668 fold
rejections, although the code was the same (`flip_threshold` was 0.2 on main; I checked).
My laptop gives identical numbers run after run.

**How I found the cause.** The CI log showed the runner simplified Spot about 4x faster than
my laptop, so it was a different CPU. My laptop only has AVX2 (NumPy reports `X86_V3` and
no `X86_V4`/AVX-512); GitHub's runners vary. NumPy chooses SIMD code by CPU, and some of it
does not round exactly the same way: `einsum` adds products in a different order, and the
vectorised `sin`, `cos`, `pow` and `log` use different routines on AVX-512. Switching
OpenBLAS kernels on my laptop (`OPENBLAS_CORETYPE=Haswell`/`Prescott`) did not change
anything, so BLAS alone was not it. A difference in the last bit of an edge cost decides
which of two nearly equal edges is collapsed first, and every later step of the greedy
algorithm then differs. Flat regions (Fandisk, the bunny's base) are full of such near-ties.

**Fix.** All arithmetic that decides the collapse order, plus the renderer and the error
measurement, now uses only element-wise `*`, `+`, `/` and `sqrt`, which IEEE 754 defines
exactly, so they give the same bits on every CPU:
- `dot3` / `norm3` in `mesh/mesh.py` instead of `einsum` and `np.linalg.norm`;
- `det3` (cofactor expansion) and `solve3` (Cramer's rule) in `mesh/quadrics.py` instead of
  `np.linalg.det` / `np.linalg.solve`;
- `math.fsum` for the sums behind area-weighted sampling and the mean error;
- in the renderer: rotation as three explicit plane rotations with Python's `math.sin/cos`,
  light directions with `dot3`, (n·H)^40 by repeated squaring, and the heat map's log values
  rounded to 9 decimals.

**Before/after on my laptop.** The new arithmetic is itself a third rounding variant, so the
greedy path changed slightly once more: bunny 2% mean error 0.079% -> 0.080% (max 0.675%
unchanged), bunny 1% max error 1.071% -> 1.288%, Spot 2% mean 0.618% -> 0.602%, Fandisk 2%
fold rejections 859 -> 621 and link rejections 3 -> 0. QEM vs clustering is still 3.0x to
4.6x. README.md and PITCH.md now quote the new numbers. The real test of the fix is that
GitHub's run reproduces these files exactly and opens no pull request.

**Confirmed.** After pushing the fix, `results.yml` ran three times on main, on three
different runners, and each time reproduced every number and every pixel of the run from my
laptop (Intel Core 7 150U, AVX2), so no pull request was opened. Two runs logged their CPU:
AMD EPYC 7763 (no AVX-512) and AMD EPYC 9V74 (with AVX-512, the kind of machine that had
diverged before). A side effect: the hand-written 3x3 arithmetic is faster than the
general library calls; the test suite went from about 20 s to 7.5 s.

## 2026-11-13: The image-diff demo (pull request #2)

To show what the results workflow is for, the branch `demo/flip-threshold-0` changes one
default: `flip_threshold` 0.2 -> 0.0 (a collapse is rejected only when a face normal turns by
more than 90 degrees). Running `results.yml` on that branch opened pull request #2. After the
determinism fixes above were merged into the branch, the diff is clean: 25 image files and
80 numbers changed, and every one of them depends on the default threshold.

What the diff shows:
- Bunny 2%: 1,389 -> 1,388 triangles, max error 0.675% -> 0.706%, mean 0.080% -> 0.079%.
- Bunny 1%: the fold check rejects 150 collapses instead of 179, turned-over faces rise from
  0.29% to 0.43%, max error 1.288% -> 1.184%. These are exactly the numbers of the
  "threshold 0" row of ablation A5 on main, as they should be.
- QEM at clustering grid 20: max error 0.416% -> 1.008%, a single bad spot, while the mean
  error is unchanged.
- Unchanged, as expected: the original renders, all subdivision strips (icosahedron, cube,
  Suzanne) and A5, which passes its thresholds explicitly.

The first version of this PR (before the fixes) also listed `bunny_100pct.png` and
`suzanne_strip.png`, which cannot depend on the threshold; that is how the rendering bug above
was found. The PR stays open as a demonstration; main keeps 0.2.
