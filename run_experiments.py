"""Regenerate every result: images, CSV tables, results/summary.json and the
data for the GitHub Pages viewer (docs/).

    python run_experiments.py

Every number quoted in README.md, PITCH.md and on the web page comes from the
files this script writes. Timings depend on the machine that ran it.
"""

import csv
import json
import os
import shutil
import time

import matplotlib
matplotlib.use("Agg")                       # draw to files, no window
import matplotlib.pyplot as plt             # noqa: E402
import numpy as np                          # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from mesh.mesh import boundary_edges, compact, drop_doubled_faces, edges, euler_characteristic  # noqa: E402
from mesh.metrics import flipped_fraction, shape_error  # noqa: E402
from mesh.obj_io import load_obj, save_obj  # noqa: E402
from mesh.simplify import Simplifier, cluster_simplify  # noqa: E402
from mesh.subdivide_loop import loop_subdivide  # noqa: E402
from render.renderer import heat_colours, render  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")
DOCS = os.path.join(ROOT, "docs")
FONT_DIR = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")

PANEL = 360                                  # pixel size of one rendered panel
CLAY = (0.80, 0.62, 0.45)
BLUE_GREY = (0.55, 0.65, 0.80)
QEM_COLOUR, CLUSTER_COLOUR = "#2a78d6", "#eb6834"

# Camera angles (degrees) that show each model well.
VIEWS = {"bunny": (0, 0, 0), "spot": (10, 120, 0), "fandisk": (-120, 0, 30),
         "suzanne": (0, 0, 0), "icosahedron": (20, 30, 0), "cube": (25, 35, 0)}
MODEL_FILES = {"bunny": "stanford-bunny.obj", "spot": "spot.obj", "fandisk": "fandisk.obj",
               "suzanne": "suzanne.obj"}


# ----------------------------------------------------------------- helpers
def out(*parts):
    """Path inside results/, creating the folder if needed."""
    path = os.path.join(RESULTS, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def kb(path):
    return os.path.getsize(path) / 1024


def load(name):
    """Load a test model without unused vertices.

    stanford-bunny.obj lists 1,113 vertices that no face uses (DEVLOG.md);
    compacting keeps vertex counts honest and keeps them out of the heat map.
    """
    return compact(*load_obj(os.path.join(ROOT, "models", MODEL_FILES[name])))


def label_pct(ratio):
    """0.02 -> '2', 0.005 -> '0.5' (for file names and captions)."""
    return f"{100 * ratio:g}"


def fmt_int(n):
    return f"{n:,}"


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def r3(x):
    """Round for the tables: 3 decimals is enough for error percentages."""
    return round(float(x), 3)


def panel_strip(images, captions, path, title, size=PANEL):
    """Paste images side by side with a bold title and a 2-line caption under each.

    captions: list of (bold first line, grey second line). Each caption must
    state facts that can be seen in, or measured from, its own image.
    """
    title_font = ImageFont.truetype(os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"), 20)
    bold = ImageFont.truetype(os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"), 15)
    regular = ImageFont.truetype(os.path.join(FONT_DIR, "DejaVuSans.ttf"), 13)
    title_h, caption_h = 46, 52
    strip = Image.new("RGB", (size * len(images), title_h + size + caption_h), "white")
    draw = ImageDraw.Draw(strip)
    draw.text((strip.width / 2, title_h / 2), title, font=title_font, fill=(20, 20, 20), anchor="mm")
    for i, (img, (line1, line2)) in enumerate(zip(images, captions)):
        strip.paste(img.resize((size, size), Image.LANCZOS), (i * size, title_h))
        x = i * size + size / 2
        draw.text((x, title_h + size + 14), line1, font=bold, fill=(20, 20, 20), anchor="mm")
        draw.text((x, title_h + size + 36), line2, font=regular, fill=(105, 105, 105), anchor="mm")
    strip.save(path)
    return path


def smooth_on_mesh(values, F, rounds=2):
    """Average each vertex value with its 1-ring neighbours, `rounds` times.

    Used only to make the heat map easier to read; the raw values are noisy
    from vertex to vertex.
    """
    E = edges(F)
    for _ in range(rounds):
        total = values.copy()
        count = np.ones(len(values))
        np.add.at(total, E[:, 0], values[E[:, 1]])
        np.add.at(total, E[:, 1], values[E[:, 0]])
        np.add.at(count, E.ravel(), 1)
        values = total / count
    return values


def boundary_length(V, F):
    B = boundary_edges(F)
    return float(np.linalg.norm(V[B[:, 0]] - V[B[:, 1]], axis=1).sum()) if len(B) else 0.0


# Simplifier runs with the default settings are reused by several experiments,
# so cache them by (model, target, settings).
_RUNS = {}


def simplified(name, target, **settings):
    key = (name, target, tuple(sorted(settings.items())))
    if key not in _RUNS:
        V, F = load(name)
        s = Simplifier(V, F, **settings)
        start = time.perf_counter()
        s.run(target)
        V2, F2 = s.result()
        _RUNS[key] = {"V": V2, "F": F2, "stats": dict(s.stats), "seconds": time.perf_counter() - start}
    return _RUNS[key]


# ------------------------------------------------------- 01 bunny LOD chain
def exp_bunny_lod(summary):
    print("01 bunny LOD chain")
    V, F = load("bunny")
    original_kb = kb(os.path.join(ROOT, "models", MODEL_FILES["bunny"]))
    levels = [0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005]
    rows = [{"kept_pct": 100, "triangles": len(F), "vertices": len(V), "obj_kb": round(original_kb),
             "size_saved_pct": 0.0, "mean_error_pct": 0.0, "max_error_pct": 0.0, "seconds": 0.0,
             "euler": euler_characteristic(V, F)}]
    images = {100: render(V, F, size=PANEL, rot=VIEWS["bunny"], frame_V=V)}
    images[100].save(out("01_bunny_lod", "bunny_100pct.png"))
    meshes = {}

    s = Simplifier(V, F)                      # one simplifier, run down in stages
    for ratio in levels:
        s.run(int(round(ratio * len(F))))
        V2, F2 = s.result()
        name = label_pct(ratio)
        obj_path = out("01_bunny_lod", f"bunny_{name}pct.obj")
        save_obj(obj_path, V2, F2)
        err = shape_error(V, F, V2, F2)
        img = render(V2, F2, size=PANEL, rot=VIEWS["bunny"], frame_V=V, wire=ratio <= 0.05)
        img.save(out("01_bunny_lod", f"bunny_{name}pct.png"))
        images[ratio * 100] = img
        meshes[ratio] = (V2, F2)
        rows.append({"kept_pct": 100 * ratio, "triangles": len(F2), "vertices": len(V2),
                     "obj_kb": round(kb(obj_path)), "size_saved_pct": round(100 * (1 - kb(obj_path) / original_kb), 1),
                     "mean_error_pct": r3(err["mean_pct"]), "max_error_pct": r3(err["max_pct"]),
                     "seconds": round(s.stats["seconds"], 1), "euler": euler_characteristic(V2, F2)})
        print(f"   {name:>4}%  {len(F2):6d} triangles  mean {err['mean_pct']:.3f}%  max {err['max_pct']:.3f}%"
              f"  {s.stats['seconds']:.1f}s")
    write_csv(out("01_bunny_lod", "metrics.csv"), rows)

    def caption(row):
        if row["kept_pct"] == 100:
            return (f"original · {fmt_int(row['triangles'])} tris", f"{fmt_int(row['obj_kb'])} KB")
        return (f"{row['kept_pct']:g}% · {fmt_int(row['triangles'])} tris",
                f"{row['obj_kb']} KB · mean error {row['mean_error_pct']:.3f}%")
    shown = [r for r in rows if r["kept_pct"] in (100, 10, 2, 1, 0.5)]
    panel_strip([images[r["kept_pct"]] for r in shown], [caption(r) for r in shown],
                out("01_bunny_lod", "bunny_lod_strip.png"),
                "Stanford Bunny simplified with QEM (errors as % of bounding-box diagonal)")

    summary["bunny_lod"] = rows
    summary["bunny_original_kb"] = round(original_kb)
    summary["bunny_lod_cumulative_seconds"] = round(s.stats["seconds"], 1)
    return meshes


# ------------------------------------------------- 02 Spot and Fandisk LODs
def exp_more_models(summary):
    print("02 more models")
    rows = []
    for name in ("spot", "fandisk"):
        V, F = load(name)
        original_path = os.path.join(ROOT, "models", MODEL_FILES[name])
        imgs, caps = [render(V, F, size=PANEL, rot=VIEWS[name], frame_V=V)], []
        caps.append((f"original · {fmt_int(len(F))} tris", f"{round(kb(original_path))} KB file"))
        imgs[0].save(out("02_more_models", f"{name}_100pct.png"))
        rows.append({"model": name, "kept_pct": 100, "triangles": len(F), "vertices": len(V),
                     "obj_kb": round(kb(original_path)), "mean_error_pct": 0.0, "max_error_pct": 0.0,
                     "seconds": 0.0, "rejected_flip": 0, "rejected_link": 0, "euler": euler_characteristic(V, F)})
        s = Simplifier(V, F)
        for ratio in (0.2, 0.05, 0.02):
            s.run(int(round(ratio * len(F))))
            V2, F2 = s.result()
            tag = label_pct(ratio)
            obj_path = out("02_more_models", f"{name}_{tag}pct.obj")
            save_obj(obj_path, V2, F2)
            err = shape_error(V, F, V2, F2)
            img = render(V2, F2, size=PANEL, rot=VIEWS[name], frame_V=V, wire=ratio <= 0.05)
            img.save(out("02_more_models", f"{name}_{tag}pct.png"))
            imgs.append(img)
            caps.append((f"{tag}% · {fmt_int(len(F2))} tris", f"mean error {err['mean_pct']:.3f}%"))
            rows.append({"model": name, "kept_pct": 100 * ratio, "triangles": len(F2), "vertices": len(V2),
                         "obj_kb": round(kb(obj_path)), "mean_error_pct": r3(err["mean_pct"]),
                         "max_error_pct": r3(err["max_pct"]), "seconds": round(s.stats["seconds"], 1),
                         "rejected_flip": s.stats["rejected_flip"], "rejected_link": s.stats["rejected_link"],
                         "euler": euler_characteristic(V2, F2)})
            print(f"   {name} {tag}%: {len(F2)} tris, mean {err['mean_pct']:.3f}%, {s.stats['seconds']:.1f}s")
        title = {"spot": "Spot the cow: QEM keeps the silhouette down to 2%",
                 "fandisk": "Fandisk (CAD part): flat faces need very few triangles"}[name]
        panel_strip(imgs, caps, out("02_more_models", f"{name}_strip.png"), title)
    write_csv(out("02_more_models", "metrics.csv"), rows)
    summary["more_models"] = rows


# ------------------------------------------------------------ 03 heat map
def exp_heatmap(summary):
    print("03 heat map")
    imgs, caps = [], []
    for name in ("spot", "bunny"):
        V, F = load(name)
        cost = Simplifier(V, F).initial_vertex_cost        # what the heap sorts by
        log_cost = np.log10(np.maximum(cost, 1e-30))
        smooth = 10 ** smooth_on_mesh(log_cost, F, rounds=2)  # display only
        vertex_rgb = heat_colours(smooth)
        face_rgb = vertex_rgb[F].mean(axis=1)
        img = render(V, F, size=PANEL + 120, rot=VIEWS[name], face_colors=face_rgb)
        img.save(out("03_error_heatmap", f"{name}_heatmap.png"))
        imgs.append(img)
        caps.append((f"{name.capitalize()} · {fmt_int(len(V))} vertices",
                     "cheapest collapse cost, log scale, 1-ring averaged x2"))
    panel_strip(imgs, caps, out("03_error_heatmap", "heatmap_strip.png"),
                "Blue = cheap to remove, red = keep", size=PANEL + 120)
    summary["heatmap"] = {"smoothing_rounds": 2, "scale": "log10, 5th-99th percentile"}


# ------------------------------------------------- 04 QEM vs clustering
def exp_qem_vs_clustering(summary):
    print("04 QEM vs clustering")
    V, F = load("bunny")
    clusters = {cells: cluster_simplify(V, F, cells) for cells in (8, 12, 20, 32, 50)}
    s = Simplifier(V, F)
    rows = []
    qem_at = {}
    for cells in sorted(clusters, reverse=True):         # largest count first: one simplifier
        Vc, Fc = clusters[cells]
        s.run(len(Fc))
        Vq, Fq = s.result()
        qem_at[cells] = (Vq, Fq)
        ec, eq = shape_error(V, F, Vc, Fc), shape_error(V, F, Vq, Fq)
        rows.append({"grid_cells": cells, "clustering_triangles": len(Fc), "qem_triangles": len(Fq),
                     "clustering_mean_pct": r3(ec["mean_pct"]), "qem_mean_pct": r3(eq["mean_pct"]),
                     "clustering_max_pct": r3(ec["max_pct"]), "qem_max_pct": r3(eq["max_pct"]),
                     "mean_ratio": round(ec["mean_pct"] / eq["mean_pct"], 1)})
        print(f"   grid {cells}: {len(Fc)} vs {len(Fq)} tris, clustering {ec['mean_pct']:.3f}% vs QEM {eq['mean_pct']:.3f}%")
    rows.sort(key=lambda r: r["grid_cells"])
    write_csv(out("04_qem_vs_clustering", "comparison.csv"), rows)

    Vc, Fc = clusters[20]
    Vq, Fq = qem_at[20]
    row = next(r for r in rows if r["grid_cells"] == 20)
    panel_strip(
        [render(V, F, size=PANEL, frame_V=V), render(Vc, Fc, size=PANEL, frame_V=V, wire=True),
         render(Vq, Fq, size=PANEL, frame_V=V, wire=True)],
        [(f"original · {fmt_int(len(F))} tris", "Stanford Bunny"),
         (f"clustering · {fmt_int(len(Fc))} tris", f"grid 20 · mean error {row['clustering_mean_pct']:.3f}%"),
         (f"QEM · {fmt_int(len(Fq))} tris", f"same budget · mean error {row['qem_mean_pct']:.3f}%")],
        out("04_qem_vs_clustering", "qem_vs_clustering.png"),
        f"Same triangle count: QEM error is {row['mean_ratio']:g}x lower than vertex clustering")
    ratios = [r["mean_ratio"] for r in rows]
    summary["qem_vs_clustering"] = {"rows": rows, "ratio_min": min(ratios), "ratio_max": max(ratios),
                                    "triangles_min": min(r["clustering_triangles"] for r in rows),
                                    "triangles_max": max(r["clustering_triangles"] for r in rows)}


# --------------------------------------------------------------- 05 graphs
def exp_graphs(summary):
    print("05 graphs")
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#888888", "axes.grid": True, "grid.color": "#e6e6e6"})
    q = summary["qem_vs_clustering"]
    rows = q["rows"]
    tris = [r["clustering_triangles"] for r in rows]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    ax.plot(tris, [r["qem_mean_pct"] for r in rows], "-o", color=QEM_COLOUR, lw=2, ms=8, label="QEM (this project)")
    ax.plot(tris, [r["clustering_mean_pct"] for r in rows], "-s", color=CLUSTER_COLOUR, lw=2, ms=8,
            label="Vertex clustering (baseline)")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.invert_xaxis()                         # fewer triangles to the right
    ax.set_xticks(tris)
    ax.set_xticklabels([f"{t:,}" for t in tris])
    ax.minorticks_off()
    ax.set_xlabel("triangles kept (log scale; fewer to the right)")
    ax.set_ylabel("mean surface error, % of bbox diagonal")
    ax.set_title(f"Bunny: QEM error is {q['ratio_min']:g}-{q['ratio_max']:g}x lower at every size", loc="left",
                 fontweight="bold")
    ax.annotate("QEM", (tris[0], rows[0]["qem_mean_pct"]), xytext=(8, 0), textcoords="offset points",
                va="center", color="#333333")
    ax.annotate("clustering", (tris[0], rows[0]["clustering_mean_pct"]), xytext=(8, 0),
                textcoords="offset points", va="center", color="#333333")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(out("05_graphs", "error_vs_triangles.png"), dpi=150)
    plt.close(fig)

    lod = summary["bunny_lod"]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    labels = ["original" if r["kept_pct"] == 100 else f"{r['kept_pct']:g}%" for r in lod]
    sizes = [r["obj_kb"] for r in lod]
    bars = ax.bar(labels, sizes, color=QEM_COLOUR, width=0.6)
    ax.set_yscale("log")
    ax.set_ylabel("OBJ file size, KB (log scale)")
    ax.set_xlabel("share of the original triangles kept")
    ax.grid(axis="x", visible=False)
    for bar, size in zip(bars, sizes):
        ax.annotate(f"{size:,}", (bar.get_x() + bar.get_width() / 2, size), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=9, color="#333333")
    two = next(r for r in lod if r["kept_pct"] == 2)
    ax.set_title(f"Bunny file size: {lod[0]['obj_kb']:,} KB -> {two['obj_kb']} KB at 2% of the triangles",
                 loc="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out("05_graphs", "file_size.png"), dpi=150)
    plt.close(fig)


# --------------------------------------------------------- 06 subdivision
def make_icosahedron():
    t = (1 + 5 ** 0.5) / 2
    V = np.array([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t],
                  [0, -1, -t], [0, 1, -t], [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], float)
    V /= np.linalg.norm(V, axis=1, keepdims=True)
    F = np.array([[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4],
                  [11, 10, 2], [10, 7, 6], [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8],
                  [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]])
    return V, F


def make_cube():
    V = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float)
    F = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                  [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    return V, F


def exp_subdivision(summary, bunny_meshes):
    print("06 subdivision")
    result = {}

    # Icosahedron 0-3: how round does it get?
    V, F = make_icosahedron()
    imgs, caps, spreads = [], [], []
    for level in range(4):
        V2, F2 = loop_subdivide(V, F, level)
        r = np.linalg.norm(V2 - V2.mean(axis=0), axis=1)
        spreads.append(round(100 * r.std() / r.mean(), 2))
        imgs.append(render(V2, F2, size=PANEL, rot=VIEWS["icosahedron"], base=BLUE_GREY, frame_V=V,
                           wire=len(F2) <= 1500))
        caps.append((f"level {level} · {fmt_int(len(F2))} tris", f"radius spread {spreads[-1]:.2f}%"))
    panel_strip(imgs, caps, out("06_subdivision", "icosahedron_strip.png"),
                "Loop subdivision turns an icosahedron into a sphere")
    result["icosahedron_radius_spread_pct"] = spreads

    # Cube 0-3: Loop rounds the corners and pulls the shape inwards.
    V, F = make_cube()
    imgs, caps = [], []
    for level in range(4):
        V2, F2 = loop_subdivide(V, F, level)
        imgs.append(render(V2, F2, size=PANEL, rot=VIEWS["cube"], base=BLUE_GREY, frame_V=V,
                           wire=len(F2) <= 1500))
        caps.append((f"level {level} · {fmt_int(len(F2))} tris",
                     f"x range {V2[:, 0].min():.2f} to {V2[:, 0].max():.2f}"))
    panel_strip(imgs, caps, out("06_subdivision", "cube_strip.png"),
                "Cube: corners round off and the shape shrinks inside [0,1]³")

    # Suzanne 0-2 (after removing the one doubled triangle, see DEVLOG.md).
    V, F = drop_doubled_faces(*load("suzanne"))
    imgs, caps = [], []
    for level in range(3):
        V2, F2 = loop_subdivide(V, F, level)
        imgs.append(render(V2, F2, size=PANEL, rot=VIEWS["suzanne"], base=BLUE_GREY, frame_V=V,
                           wire=len(F2) <= 1500, cull=False))
        caps.append((f"level {level} · {fmt_int(len(F2))} tris", f"Euler number {euler_characteristic(V2, F2)}"))
    panel_strip(imgs, caps, out("06_subdivision", "suzanne_strip.png"),
                "Suzanne: low-poly to smooth with 2 Loop levels")

    # Bunny: simplify to 1%, then subdivide (simplify-then-smooth).
    V, F = load("bunny")
    V1, F1 = bunny_meshes[0.01]
    imgs = [render(V, F, size=PANEL, frame_V=V)]
    caps = [(f"original · {fmt_int(len(F))} tris", "reference surface")]
    loop_rows = []
    for level in range(3):
        V2, F2 = loop_subdivide(V1, F1, level)
        err = shape_error(V, F, V2, F2)
        loop_rows.append({"loop_levels": level, "triangles": len(F2),
                          "mean_error_pct": r3(err["mean_pct"]), "max_error_pct": r3(err["max_pct"])})
        imgs.append(render(V2, F2, size=PANEL, frame_V=V, wire=len(F2) <= 1500))
        name = "1% QEM" if level == 0 else f"1% + {level} Loop"
        caps.append((f"{name} · {fmt_int(len(F2))} tris", f"mean error {err['mean_pct']:.3f}%"))
    panel_strip(imgs, caps, out("06_subdivision", "bunny_simplify_then_subdivide.png"),
                "Simplify to 1%, then smooth with Loop subdivision")
    write_csv(out("06_subdivision", "bunny_loop.csv"), loop_rows)
    result["bunny_1pct_loop"] = loop_rows
    summary["subdivision"] = result


# ---------------------------------------------------------- 07 ablations
def ablation_row(ablation, variant, name, V, F, run, V_ref, F_ref):
    """One row of ablations.csv, measured the same way for every variant."""
    V2, F2 = run["V"], run["F"]
    err = shape_error(V_ref, F_ref, V2, F2)
    return {"ablation": ablation, "variant": variant, "model": name,
            "kept_pct": round(100 * len(F2) / len(F_ref), 2), "triangles": len(F2),
            "mean_error_pct": r3(err["mean_pct"]), "max_error_pct": r3(err["max_pct"]),
            "flipped_faces_pct": round(100 * flipped_fraction(V_ref, F_ref, V2, F2), 2),
            "boundary_edges": len(boundary_edges(F2)),
            "boundary_length": round(boundary_length(V2, F2), 4),
            "rejected_flip": run["stats"].get("rejected_flip", 0),
            "rejected_link": run["stats"].get("rejected_link", 0),
            "seconds": round(run["seconds"], 1)}


def exp_ablations(summary):
    print("07 ablations")
    rows = []
    folder = "07_ablations"
    Vb, Fb = load("bunny")
    Vs, Fs = load("spot")
    b1, b2 = int(round(0.01 * len(Fb))), int(round(0.02 * len(Fb)))
    s2 = int(round(0.02 * len(Fs)))

    def strip(tag, panels, title):
        imgs = [p[0] for p in panels]
        caps = [p[1] for p in panels]
        panel_strip(imgs, caps, out(folder, f"{tag}.png"), title)

    # A1 fold check on / off
    print("   A1 fold check")
    panels = []
    for variant, check in (("on", True), ("off", False)):
        run = simplified("bunny", b1, check_flips=check)
        row = ablation_row("A1", f"fold check {variant}", "bunny", Vb, Fb, run, Vb, Fb)
        rows.append(row)
        panels.append((render(run["V"], run["F"], size=PANEL, frame_V=Vb, wire=True),
                       (f"fold check {variant}", f"flipped {row['flipped_faces_pct']:.2f}% · mean {row['mean_error_pct']:.3f}%")))
    strip("A1_fold_check", panels, "A1: fold check on vs off (bunny 1%)")

    # A2 boundary quadrics, seen from below where the holes are
    print("   A2 boundary quadrics")
    below = (-90, 0, 0)    # tips the base towards the camera (+90 would show the top; DEVLOG.md)
    panels = [(render(Vb, Fb, size=PANEL, rot=below, frame_V=Vb),
               ("original, from below", f"{len(boundary_edges(Fb))} boundary edges"))]
    original_length = boundary_length(Vb, Fb)
    for weight in (1000.0, 0.0):
        run = simplified("bunny", b2, boundary_weight=weight)
        row = ablation_row("A2", f"boundary weight {weight:g}", "bunny", Vb, Fb, run, Vb, Fb)
        row["boundary_length_vs_original_pct"] = round(100 * row["boundary_length"] / original_length, 1)
        rows.append(row)
        panels.append((render(run["V"], run["F"], size=PANEL, rot=below, frame_V=Vb, wire=True),
                       (f"weight {weight:g}", f"{row['boundary_edges']} boundary edges · rim {row['boundary_length_vs_original_pct']:g}% long")))
    strip("A2_boundary", panels, "A2: boundary quadrics keep the holes in the base (bunny 2%, from below)")

    # A3 area weighting on Spot
    print("   A3 area weighting")
    panels = [(render(Vs, Fs, size=PANEL, rot=VIEWS["spot"], frame_V=Vs), ("original", f"{fmt_int(len(Fs))} tris"))]
    for variant, weighted in (("on", True), ("off", False)):
        run = simplified("spot", s2, area_weighted=weighted)
        row = ablation_row("A3", f"area weighting {variant}", "spot", Vs, Fs, run, Vs, Fs)
        rows.append(row)
        panels.append((render(run["V"], run["F"], size=PANEL, rot=VIEWS["spot"], frame_V=Vs, wire=True),
                       (f"area weighting {variant}", f"mean {row['mean_error_pct']:.3f}% · max {row['max_error_pct']:.2f}%")))
    strip("A3_area_weighting", panels, "A3: area weighting on vs off (Spot 2%)")

    # A4 vertex placement
    print("   A4 placement")
    panels = []
    for placement in ("optimal", "midpoint", "endpoint"):
        run = simplified("bunny", b1, placement=placement)
        row = ablation_row("A4", placement, "bunny", Vb, Fb, run, Vb, Fb)
        rows.append(row)
        panels.append((render(run["V"], run["F"], size=PANEL, frame_V=Vb, wire=True),
                       (f"{placement} point", f"mean {row['mean_error_pct']:.3f}% · max {row['max_error_pct']:.2f}%")))
    strip("A4_placement", panels, "A4: where the merged vertex goes (bunny 1%)")

    # A5 fold threshold
    print("   A5 fold threshold")
    panels = []
    for threshold in (-1.0, 0.0, 0.2, 0.5):
        run = simplified("bunny", b1, flip_threshold=threshold)
        row = ablation_row("A5", f"threshold {threshold:g}", "bunny", Vb, Fb, run, Vb, Fb)
        rows.append(row)
        panels.append((render(run["V"], run["F"], size=PANEL, frame_V=Vb, wire=True),
                       (f"cos threshold {threshold:g}", f"{row['rejected_flip']} rejected · flipped {row['flipped_faces_pct']:.2f}%")))
    strip("A5_fold_threshold", panels, "A5: how strict the fold check is (bunny 1%)")

    # A6 Loop levels after simplification
    print("   A6 subdivision after simplification")
    panels = []
    base = simplified("bunny", b1)
    for level in range(4):
        V2, F2 = loop_subdivide(base["V"], base["F"], level)
        run = {"V": V2, "F": F2, "stats": {}, "seconds": 0.0}
        row = ablation_row("A6", f"{level} Loop levels", "bunny", Vb, Fb, run, Vb, Fb)
        rows.append(row)
        panels.append((render(V2, F2, size=PANEL, frame_V=Vb, wire=len(F2) <= 1500),
                       (f"{level} Loop levels · {fmt_int(len(F2))} tris", f"mean error {row['mean_error_pct']:.3f}%")))
    strip("A6_subdivision_levels", panels, "A6: Loop levels after simplifying the bunny to 1%")

    columns = ["ablation", "variant", "model", "kept_pct", "triangles", "mean_error_pct", "max_error_pct",
               "flipped_faces_pct", "boundary_edges", "boundary_length", "boundary_length_vs_original_pct",
               "rejected_flip", "rejected_link", "seconds"]
    write_csv(out(folder, "ablations.csv"), [{c: r.get(c, "") for c in columns} for r in rows])
    summary["ablations"] = rows
    write_ablation_readme(rows)


def write_ablation_readme(rows):
    """results/07_ablations/README.md: image, table and explanation per ablation.

    Generated from the same rows as ablations.csv so the text can never
    disagree with the numbers after a re-run.
    """
    def get(ablation, variant):
        return next(r for r in rows if r["ablation"] == ablation and r["variant"] == variant)

    def table(ablation, extra=()):
        cols = ["variant", "triangles", "mean_error_pct", "max_error_pct", "flipped_faces_pct", *extra]
        head = "| " + " | ".join(c.replace("_pct", " %").replace("_", " ") for c in cols) + " |"
        lines = [head, "|" + "---|" * len(cols)]
        for r in rows:
            if r["ablation"] == ablation:
                lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
        return "\n".join(lines)

    on, off = get("A1", "fold check on"), get("A1", "fold check off")
    w1, w0 = get("A2", "boundary weight 1000"), get("A2", "boundary weight 0")
    a_on, a_off = get("A3", "area weighting on"), get("A3", "area weighting off")
    opt, mid, end = get("A4", "optimal"), get("A4", "midpoint"), get("A4", "endpoint")
    t = {x: get("A5", f"threshold {x:g}") for x in (-1.0, 0.0, 0.2, 0.5)}
    l0, l3 = get("A6", "0 Loop levels"), get("A6", "3 Loop levels")

    text = f"""# Ablation study: what changes when one part of the algorithm is switched off

Each experiment changes exactly one setting, renders the same model from the same
camera, and measures it in the same way (`ablations.csv`; errors are % of the
bounding-box diagonal; "flipped" = new faces whose normal points opposite to the
nearest original face). This file is written by `run_experiments.py`.

## A1: fold check (bunny 1%)

![A1](A1_fold_check.png)

{table("A1", ["rejected_flip"])}

Without the fold check, {off['flipped_faces_pct']}% of the faces end up turned over, against
{on['flipped_faces_pct']}% with it. The mean error does not get worse ({on['mean_error_pct']}% on,
{off['mean_error_pct']}% off): the distance measure only asks how far the new surface is from the
old one, not which way it faces, so a turned-over triangle lying near the surface costs almost
nothing. That is why the fold check compares normals instead of distances.

## A2: boundary quadrics (bunny 2%, seen from below)

![A2](A2_boundary.png)

{table("A2", ["boundary_edges", "boundary_length_vs_original_pct"])}

With weight 0 nothing stops the rim vertices of the holes from sliding, so the holes in the base
grow (the rim is {w0['boundary_length_vs_original_pct']}% as long as the original, drawn with only
{w0['boundary_edges']} edges) and the max error rises from {w1['max_error_pct']}% to {w0['max_error_pct']}%.
The extra planes along each boundary edge make sliding off the rim expensive, so with weight 1000
the rim stays at {w1['boundary_length_vs_original_pct']}% of its original length.

## A3: area weighting (Spot 2%)

![A3](A3_area_weighting.png)

{table("A3")}

With area weighting on, the horns disappear at 2%: they are built from many tiny triangles, and
quadrics scaled by tiny areas make them cheap to remove. With it off every triangle counts the
same, so the horns survive (visible as two spikes), but the large body pays for it: the mean
error rises from {a_on['mean_error_pct']}% to {a_off['mean_error_pct']}% while the max error falls from
{a_on['max_error_pct']}% to {a_off['max_error_pct']}% (with weighting on, the worst point is at the horn tips).

## A4: where the merged vertex goes (bunny 1%)

![A4](A4_placement.png)

{table("A4", ["rejected_flip"])}

The optimal point has the lowest error ({opt['mean_error_pct']}% mean) because it is chosen to stay
close to all the original planes at once. The midpoint is worst ({mid['mean_error_pct']}%): on a
curved surface the middle of an edge lies inside or outside the surface; the better end point
({end['mean_error_pct']}%) at least keeps a vertex that was on the original surface.

## A5: how strict the fold check is (bunny 1%)

![A5](A5_fold_threshold.png)

{table("A5", ["rejected_flip"])}

A collapse is rejected when a face's normal turns so far that cos(old, new) falls below the
threshold. Raising it from -1 (off) to 0.5 rejects {t[-1.0]['rejected_flip']} -> {t[0.5]['rejected_flip']}
collapses and lowers the flipped faces from {t[-1.0]['flipped_faces_pct']}% to {t[0.5]['flipped_faces_pct']}%,
while the mean error stays between {min(t[x]['mean_error_pct'] for x in t)}% and {max(t[x]['mean_error_pct'] for x in t)}%.

## A6: Loop subdivision after simplification (bunny 1%)

![A6](A6_subdivision_levels.png)

{table("A6")}

Each Loop level multiplies the triangles by 4 and makes the surface look smooth, but the mean error
grows from {l0['mean_error_pct']}% (0 levels) to {l3['mean_error_pct']}% (3 levels). Loop subdivision
approximates its control mesh instead of passing through it, so it moves the vertices that QEM
placed on the surface (on convex parts it pulls them inwards): smoother is not the same as closer
to the original.
"""
    with open(out("07_ablations", "README.md"), "w") as f:
        f.write(text)


# ------------------------------------------------------------ docs/ data
def export_docs(summary):
    print("docs/ data for GitHub Pages")
    img_dir = os.path.join(DOCS, "img")
    model_dir = os.path.join(DOCS, "models")
    data_dir = os.path.join(DOCS, "data")
    for d in (img_dir, model_dir, data_dir):
        os.makedirs(d, exist_ok=True)

    images = ["01_bunny_lod/bunny_lod_strip.png", "01_bunny_lod/bunny_100pct.png", "01_bunny_lod/bunny_1pct.png",
              "02_more_models/spot_strip.png", "02_more_models/fandisk_strip.png",
              "03_error_heatmap/heatmap_strip.png", "04_qem_vs_clustering/qem_vs_clustering.png",
              "05_graphs/error_vs_triangles.png", "05_graphs/file_size.png",
              "06_subdivision/icosahedron_strip.png", "06_subdivision/cube_strip.png",
              "06_subdivision/suzanne_strip.png", "06_subdivision/bunny_simplify_then_subdivide.png",
              "07_ablations/A1_fold_check.png", "07_ablations/A2_boundary.png",
              "07_ablations/A3_area_weighting.png", "07_ablations/A4_placement.png",
              "07_ablations/A5_fold_threshold.png", "07_ablations/A6_subdivision_levels.png"]
    for rel in images:
        shutil.copy(os.path.join(RESULTS, rel), os.path.join(img_dir, os.path.basename(rel)))

    manifest = {"models": []}
    # Bunny: original + every LOD level
    levels = []
    for row in summary["bunny_lod"]:
        if row["kept_pct"] == 100:
            src, dst = os.path.join(ROOT, "models", MODEL_FILES["bunny"]), "bunny_100pct.obj"
        else:
            dst = f"bunny_{row['kept_pct']:g}pct.obj"
            src = os.path.join(RESULTS, "01_bunny_lod", dst)
        shutil.copy(src, os.path.join(model_dir, dst))
        levels.append({"label": "original" if row["kept_pct"] == 100 else f"{row['kept_pct']:g}%",
                       "file": f"models/{dst}", "triangles": row["triangles"],
                       "kb": round(kb(os.path.join(model_dir, dst))), "mean_error_pct": row["mean_error_pct"],
                       "kept_pct": row["kept_pct"]})
    manifest["models"].append({"name": "Bunny", "levels": levels})
    for name, title in (("spot", "Spot"), ("fandisk", "Fandisk")):
        levels = []
        for row in [r for r in summary["more_models"] if r["model"] == name]:
            if row["kept_pct"] == 100:
                src, dst = os.path.join(ROOT, "models", MODEL_FILES[name]), f"{name}_100pct.obj"
            else:
                dst = f"{name}_{row['kept_pct']:g}pct.obj"
                src = os.path.join(RESULTS, "02_more_models", dst)
            shutil.copy(src, os.path.join(model_dir, dst))
            levels.append({"label": "original" if row["kept_pct"] == 100 else f"{row['kept_pct']:g}%",
                           "file": f"models/{dst}", "triangles": row["triangles"],
                           "kb": round(kb(os.path.join(model_dir, dst))), "mean_error_pct": row["mean_error_pct"],
                           "kept_pct": row["kept_pct"]})
        manifest["models"].append({"name": title, "levels": levels})
    with open(os.path.join(data_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)


# -------------------------------------------------------------------- main
def main():
    start = time.perf_counter()
    summary = {}
    bunny_meshes = exp_bunny_lod(summary)
    exp_more_models(summary)
    exp_heatmap(summary)
    exp_qem_vs_clustering(summary)
    exp_graphs(summary)
    exp_subdivision(summary, bunny_meshes)
    before_ablations = time.perf_counter() - start
    exp_ablations(summary)
    export_docs(summary)

    two = next(r for r in summary["bunny_lod"] if r["kept_pct"] == 2)
    summary["headline"] = {
        "bunny_original_triangles": summary["bunny_lod"][0]["triangles"],
        "bunny_original_kb": summary["bunny_original_kb"],
        "bunny_2pct_triangles": two["triangles"], "bunny_2pct_kb": two["obj_kb"],
        "bunny_2pct_mean_error_pct": two["mean_error_pct"], "bunny_2pct_max_error_pct": two["max_error_pct"],
        "bunny_2pct_size_saved_pct": two["size_saved_pct"],
        "qem_vs_clustering_ratio_min": summary["qem_vs_clustering"]["ratio_min"],
        "qem_vs_clustering_ratio_max": summary["qem_vs_clustering"]["ratio_max"],
    }
    summary["runtime_seconds"] = {"without_ablations": round(before_ablations), "total": round(time.perf_counter() - start)}
    with open(out("summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"done in {time.perf_counter() - start:.0f} s (without ablations {before_ablations:.0f} s)")


if __name__ == "__main__":
    main()
