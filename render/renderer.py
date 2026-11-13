"""A small software renderer for the result images.

It follows the viewing pipeline from the course, step by step:
  1. modelling transform  - rotate the model (Rz . Ry . Rx, homogeneous-style 3x3)
  2. window-to-viewport   - orthographic projection, scale the model's 2D box
                            to 88% of the image and flip y (screen y points down)
  3. back-face culling    - drop faces whose normal points away from the viewer
  4. lighting             - ambient + diffuse (two lights) + Blinn-Phong specular,
                            one colour per face (flat shading)
  5. hidden surfaces      - painter's algorithm: sort faces far to near and paint
  6. anti-aliasing        - draw at 2x size and shrink with a Lanczos filter

Pillow is used only to fill the projected triangles and to save the PNG.
"""

import numpy as np
from PIL import Image, ImageDraw

KEY_LIGHT = np.array([-0.4, 0.6, 0.7]) / np.linalg.norm([-0.4, 0.6, 0.7])
FILL_LIGHT = np.array([0.5, -0.3, 0.6]) / np.linalg.norm([0.5, -0.3, 0.6])
VIEW = np.array([0.0, 0.0, 1.0])                 # the camera looks down -z
HALF = (KEY_LIGHT + VIEW) / np.linalg.norm(KEY_LIGHT + VIEW)   # Blinn half-vector


def rotation_matrix(rx, ry, rz):
    """Rotation by rx, then ry, then rz degrees about the x, y and z axes."""
    x, y, z = np.radians([rx, ry, rz])
    Rx = np.array([[1, 0, 0], [0, np.cos(x), -np.sin(x)], [0, np.sin(x), np.cos(x)]])
    Ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    Rz = np.array([[np.cos(z), -np.sin(z), 0], [np.sin(z), np.cos(z), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def shade(normals, base):
    """Flat shading: one RGB colour (0..1) per face from its unit normal.

    colour = ambient + diffuse + specular
           = base*0.25 + base*0.75*diffuse + 0.22*specular
    with diffuse from a key light and a weaker fill light, and a Blinn-Phong
    highlight (n . H)^40 from the key light.
    """
    diffuse = 0.75 * np.maximum(0, normals @ KEY_LIGHT) + 0.30 * np.maximum(0, normals @ FILL_LIGHT)
    specular = np.maximum(0, normals @ HALF) ** 40
    base = np.broadcast_to(base, normals.shape)
    colour = base * 0.25 + base * 0.75 * diffuse[:, None] + 0.22 * specular[:, None]
    return np.clip(colour, 0, 1)


def render(V, F, size=600, rot=(0, 0, 0), base=(0.80, 0.62, 0.45), wire=False,
           face_colors=None, frame_V=None, supersample=2, cull=True, background=(255, 255, 255)):
    """Draw the mesh (V, F) and return a PIL image of size x size pixels.

    frame_V: if given (usually the original mesh), it decides the centre and
    the scale, so every simplified version of a model is framed identically
    and the images can be compared side by side.
    face_colors: optional (m, 3) colours in 0..1, replacing `base` per face.
    cull=False draws back faces too (with flipped normals), needed for open
    meshes like Suzanne where you can see inside.
    """
    R = rotation_matrix(*rot)
    frame = V if frame_V is None else frame_V
    centre = 0.5 * (frame.min(axis=0) + frame.max(axis=0))

    # 1. modelling transform: centre, then rotate
    P = (V - centre) @ R.T
    framed = (frame - centre) @ R.T

    # 2. window-to-viewport (orthographic: just drop z)
    S = size * supersample
    lo, hi = framed[:, :2].min(axis=0), framed[:, :2].max(axis=0)
    scale = 0.88 * S / max(hi - lo)
    offset = S / 2 - scale * (lo + hi) / 2
    screen_x = P[:, 0] * scale + offset[0]
    screen_y = S - (P[:, 1] * scale + offset[1])   # screen y grows downwards

    # face normals in view space
    tri = P[F]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(n, axis=1)
    n = n / np.where(length > 0, length, 1)[:, None]

    # 3. back-face culling (or, for open meshes, turn back faces around)
    if cull:
        visible = n[:, 2] > 0
    else:
        visible = length > 0
        n[n[:, 2] < 0] *= -1

    # 4. lighting
    base_colour = np.asarray(base) if face_colors is None else np.asarray(face_colors)
    if base_colour.ndim == 2:
        base_colour = base_colour[visible]
    colours = (shade(n[visible], base_colour) * 255).astype(np.uint8)

    # 5. painter's algorithm: far (small z) first, near last.
    # A stable sort keeps faces at exactly equal depth in index order. The
    # default sort is not stable and NumPy picks its SIMD version by CPU, so
    # ties came out in a different order on different machines (DEVLOG.md).
    faces = F[visible]
    depth = P[faces, 2].mean(axis=1)
    order = np.argsort(depth, kind="stable")

    img = Image.new("RGB", (S, S), background)
    draw = ImageDraw.Draw(img)
    edge_colour = (40, 40, 40)
    for i in order:
        a, b, c = faces[i]
        polygon = [(screen_x[a], screen_y[a]), (screen_x[b], screen_y[b]), (screen_x[c], screen_y[c])]
        fill = tuple(colours[i].tolist())
        draw.polygon(polygon, fill=fill, outline=edge_colour if wire else fill)

    # 6. anti-aliasing by supersampling
    if supersample > 1:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def heat_colours(values):
    """Map values to colours blue -> yellow -> red on a log scale.

    Collapse costs span many orders of magnitude, so we take log10 and clip
    to the 5th..99th percentile; otherwise a few extreme values would turn
    everything else the same colour. Returns (k, 3) RGB in 0..1.
    """
    v = np.log10(np.maximum(np.asarray(values, dtype=float), 1e-30))
    finite = np.isfinite(v)                   # an unused vertex has cost inf
    lo, hi = np.percentile(v[finite], [5, 99])
    v = np.where(finite, v, hi)
    t = np.clip((v - lo) / max(hi - lo, 1e-12), 0, 1)[:, None]
    blue, yellow, red = np.array([0.20, 0.35, 0.85]), np.array([0.98, 0.85, 0.25]), np.array([0.85, 0.12, 0.10])
    first_half = blue + (yellow - blue) * np.clip(2 * t, 0, 1)
    second_half = yellow + (red - yellow) * np.clip(2 * t - 1, 0, 1)
    return np.where(t < 0.5, first_half, second_half)
