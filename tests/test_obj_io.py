"""Tests for reading and writing OBJ files."""

import numpy as np

from mesh.obj_io import load_obj, save_obj


def test_round_trip(tmp_path, spot):
    """Saving and loading again gives the same mesh (positions to 6 decimals)."""
    V, F = spot
    path = tmp_path / "spot.obj"
    save_obj(str(path), V, F)
    V2, F2 = load_obj(str(path))
    assert np.allclose(V, V2, atol=1e-6)
    assert np.array_equal(F, F2)


def test_slash_tokens_and_quad_split(tmp_path):
    """'f 1/1/1 ...' tokens use the number before the first '/'; a quad becomes 2 triangles."""
    path = tmp_path / "quad.obj"
    path.write_text(
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
        "vt 0 0\nvn 0 0 1\n"
        "f 1/1/1 2/1/1 3//1 4\n"
    )
    V, F = load_obj(str(path))
    assert V.shape == (4, 3)
    assert F.tolist() == [[0, 1, 2], [0, 2, 3]]


def test_duplicate_vertices_merged(tmp_path):
    """Two triangles that store their shared edge twice end up sharing two vertices."""
    path = tmp_path / "dup.obj"
    path.write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"     # triangle 1
        "v 1 0 0\nv 0 1 0\nv 1 1 0\n"     # triangle 2 repeats two positions
        "f 1 2 3\nf 4 6 5\n"
    )
    V, F = load_obj(str(path))
    assert len(V) == 4
    assert F.tolist() == [[0, 1, 2], [1, 3, 2]]
    V_raw, _ = load_obj(str(path), merge_duplicates=False)
    assert len(V_raw) == 6
