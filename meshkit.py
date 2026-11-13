"""meshkit command-line tool.

Examples:
    python meshkit.py info models/stanford-bunny.obj
    python meshkit.py simplify models/stanford-bunny.obj -o out/bunny_2.obj --ratio 0.02
    python meshkit.py subdivide out/bunny_2.obj -o out/bunny_smooth.obj --levels 2
    python meshkit.py render out/bunny_2.obj -o out/bunny_2.png --wire
"""

import argparse
import os
import sys

from mesh.mesh import boundary_edges, euler_characteristic
from mesh.metrics import shape_error
from mesh.obj_io import load_obj, save_obj
from mesh.simplify import simplify
from mesh.subdivide_loop import loop_subdivide
from render.renderer import render


def kilobytes(path):
    return os.path.getsize(path) / 1024


def cmd_info(args):
    V, F = load_obj(args.obj)
    print(f"file      {args.obj} ({kilobytes(args.obj):.0f} KB)")
    print(f"vertices  {len(V)}")
    print(f"triangles {len(F)}")
    print(f"euler     {euler_characteristic(V, F)}")
    print(f"boundary  {len(boundary_edges(F))} edges")


def cmd_simplify(args):
    V, F = load_obj(args.obj)
    V2, F2, stats = simplify(
        V, F, ratio=args.ratio, target_faces=args.faces,
        check_flips=not args.no_flip_check, boundary_weight=args.boundary_weight,
        placement=args.placement,
    )
    save_obj(args.output, V2, F2)
    err = shape_error(V, F, V2, F2)
    print(f"{len(F)} -> {len(F2)} triangles ({100 * len(F2) / len(F):.2f}%) in {stats['seconds']:.1f}s")
    print(f"mean error {err['mean_pct']:.3f}% , max error {err['max_pct']:.3f}% of bbox diagonal")
    print(f"file {kilobytes(args.obj):.0f} KB -> {kilobytes(args.output):.0f} KB")


def cmd_subdivide(args):
    V, F = load_obj(args.obj)
    V2, F2 = loop_subdivide(V, F, args.levels)
    save_obj(args.output, V2, F2)
    print(f"{len(F)} -> {len(F2)} triangles after {args.levels} Loop level(s)")


def cmd_render(args):
    V, F = load_obj(args.obj)
    rot = tuple(float(x) for x in args.rot.split(","))
    folder = os.path.dirname(args.output)
    if folder:
        os.makedirs(folder, exist_ok=True)
    render(V, F, size=args.size, rot=rot, wire=args.wire).save(args.output)
    print(f"saved {args.output}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mesh simplification (QEM), Loop subdivision and rendering.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("info", help="print vertex/triangle counts and topology")
    p.add_argument("obj")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("simplify", help="reduce the triangle count with QEM edge collapse")
    p.add_argument("obj")
    p.add_argument("-o", "--output", required=True)
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--ratio", type=float, help="fraction of triangles to keep, e.g. 0.02")
    target.add_argument("--faces", type=int, help="target number of triangles")
    p.add_argument("--no-flip-check", action="store_true", help="turn off the fold check")
    p.add_argument("--boundary-weight", type=float, default=1000.0)
    p.add_argument("--placement", choices=["optimal", "midpoint", "endpoint"], default="optimal")
    p.set_defaults(func=cmd_simplify)

    p = sub.add_parser("subdivide", help="smooth a mesh with Loop subdivision")
    p.add_argument("obj")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--levels", type=int, default=1)
    p.set_defaults(func=cmd_subdivide)

    p = sub.add_parser("render", help="render a PNG with the software renderer")
    p.add_argument("obj")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--rot", default="0,0,0", help="rotation in degrees, rx,ry,rz")
    p.add_argument("--size", type=int, default=600)
    p.add_argument("--wire", action="store_true", help="draw triangle edges")
    p.set_defaults(func=cmd_render)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
