"""Colour + depth fusion: the parts the depth alone can't measure.

Why (UR3e cell, 2026-10-08): white polyethylene foam blocks — and, worse, bare metal — are
translucent or shiny to the D435's IR projector, so their tops come back 10-60 % holes
(the grey table beside them 100 % valid). The depth-only detector (:mod:`.volume`) then
sees each block as a ring of fragments ("15 x 10 too short") and finds one of four. The
colour picture shows them plainly, and a colour blob measured against the depth gave
49 x 30 +-1 mm for 50 x 30 blocks, each block's base-frame position agreeing to 2-4 mm
across eight viewpoints, where the depth found 1.4 of 4 (Nick: "fuse the 2D and depth
view to make the selection more robust").

The rule, per colour blob (pixels that differ from the picture's dominant colour, the
table, in CIE Lab — Otsu picks the split, so it is not a white gate):

* **full depth on it, and it stands under half the part's height** → flat: paper, tape,
  a label, a mark. Not a part.
* **enough depth standing on it** → its height is the median of that depth.
* **holes in the depth** (under half of it valid) → a material the projector can't see,
  which the table is not: a part, its height the spec's — the face whose footprint the
  blob matches best.

The rectangle is the blob's minimum-area rectangle, back-projected onto the surface
lifted by that height, so it is the colour's outline, not the depth's. numpy + OpenCV
(the ``vision`` extra); :func:`available` says whether they import, and :func:`colour_parts`
answers ``[]`` without them so the stdlib path is unchanged on a PC without them.
"""

from __future__ import annotations

import math

from .partspec import PartSpec

try:  # the vision extra
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover - the stdlib path
    cv2 = None
    np = None

MIN_BLOB_PX = 300  # smaller is a mark, a glint, a cable's highlight
EDGE_PX = 2  # a blob this near the picture's edge is cut off by it
HOLE_FRAC = 0.5  # under this much valid depth on a blob: a material the projector can't see
FLAT_FRAC = 0.5  # with full depth, under this fraction of it standing: flat, not a part
MIN_STANDING = 20  # pixels of standing depth that make a height
OPEN_PX = 5  # the mask's morphological opening: joins pixels, drops specks
ERODE_PX = 5  # the blob's inner region (off its blurred edge) for the heights
RECT_FILL = 0.85  # a blob at least this much of its own rectangle: a clean outline, better than the depth's
DISTANCE_GAIN = 2.0  # Lab distance → 8-bit for Otsu (a 128-unit difference saturates)


def available() -> bool:
    """numpy + OpenCV import (the ``vision`` extra)?"""
    return cv2 is not None and np is not None


def _mask(rgb):
    """Pixels that differ from the picture's dominant colour (the table), Otsu's split of the
    Lab distance, opened."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    bg = np.median(lab.reshape(-1, 3), axis=0)
    d = np.linalg.norm(lab - bg, axis=2)
    d8 = np.clip(d * DISTANCE_GAIN, 0, 255).astype(np.uint8)
    _, m = cv2.threshold(d8, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = np.ones((OPEN_PX, OPEN_PX), np.uint8)
    return cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, k)


def _heights(w: int, h: int, depth: bytes, scale: float, K: dict, T, surf):
    """Per-pixel height above ``surf`` (m) in the base frame; NaN where there is no depth."""
    d = np.frombuffer(depth, np.uint16, count=w * h).reshape(h, w).astype(np.float64)
    z = d * scale
    z[d == 0] = np.nan
    u, v = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    pc = np.stack([(u - K["ppx"]) / K["fx"] * z, (v - K["ppy"]) / K["fy"] * z, z], axis=-1).reshape(-1, 3)
    R = np.array([T.rotate((1.0, 0.0, 0.0)), T.rotate((0.0, 1.0, 0.0)), T.rotate((0.0, 0.0, 1.0))]).T
    pb = pc @ R.T + np.array(T.translation)
    n = np.array(surf.normal)
    return ((pb - np.array(surf.origin)) @ n).reshape(h, w), z


def _on_plane(px: float, py: float, K: dict, T, surf, lift: float):
    """The base point where the pixel's ray meets the surface lifted by ``lift``."""
    d = T.rotate(((px - K["ppx"]) / K["fx"], (py - K["ppy"]) / K["fy"], 1.0))
    o = T.translation
    n = surf.normal
    p0 = [surf.origin[i] + n[i] * lift for i in range(3)]
    dn = sum(d[i] * n[i] for i in range(3))
    if abs(dn) < 1e-9:
        return None
    s = sum((p0[i] - o[i]) * n[i] for i in range(3)) / dn
    return [o[i] + s * d[i] for i in range(3)]


def _spec_height(spec: PartSpec | None, length_m: float, width_m: float) -> float | None:
    """The height of the spec's face whose footprint the blob matches best (None: no spec,
    or no height given)."""
    if spec is None:
        return None
    best = None
    for pl, pw, ph in spec.poses():
        if ph is None:
            continue
        err = abs(pl - length_m) / pl + abs(pw - width_m) / pw
        if best is None or err < best[0]:
            best = (err, ph)
    return None if best is None else best[1]


def colour_parts(
    w: int,
    h: int,
    channels: int,
    colour: bytes,
    depth: bytes,
    depth_scale_m: float,
    K: dict,
    T_bc,
    surf,
    spec: PartSpec | None,
    stride: int = 1,
) -> list:
    """The colour blobs measured against the depth, as :class:`.volume.Part` (``why`` unset:
    the caller gates size, reach and area like any other part). ``T_bc`` the colour
    camera's base pose, ``surf`` the fitted :class:`.volume.Surface`. ``[]`` without the
    vision extra, without a surface, or on a picture with no colour."""
    if not available() or surf is None or not colour or channels < 3:
        return []
    from .volume import BLUR_PER_M, FOOTPRINT_MARGIN_M, Part, _project, _wrap_half, robust_rect

    rgb = np.frombuffer(colour, np.uint8, count=w * h * channels).reshape(h, w, channels)[:, :, :3]
    mask = _mask(np.ascontiguousarray(rgb))
    hm, zmap = _heights(w, h, depth, depth_scale_m, K, T_bc, surf)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    k_er = np.ones((ERODE_PX, ERODE_PX), np.uint8)
    T_cb = T_bc.inverse()
    half_h = min(spec.heights()) / 2 if spec is not None and spec.heights() else 0.005
    out = []
    for i in range(1, n):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        if area < MIN_BLOB_PX:
            continue
        blob = lab == i
        near_edge = x <= EDGE_PX or y <= EDGE_PX or x + bw >= w - EDGE_PX or y + bh >= h - EDGE_PX
        inner = cv2.erode(blob.astype(np.uint8), k_er).astype(bool)
        if not inner.any():
            inner = blob
        hin = hm[inner]
        valid = hin[~np.isnan(hin)]
        vfrac = valid.size / max(1, int(inner.sum()))
        standing = valid[valid > half_h]
        # the rectangle first: the colour's outline, in pixels
        pts = np.column_stack(np.nonzero(blob))[:, ::-1].astype(np.float32)
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(pts)
        box = cv2.boxPoints(((cx, cy), (rw, rh), ang))
        rect_fill = float(area / max(1.0, rw * rh))  # 1 = the blob is its rectangle
        if vfrac >= HOLE_FRAC and standing.size < FLAT_FRAC * max(1, valid.size):
            continue  # flat: paper, tape, a label, a mark on the table
        height = None
        if vfrac < HOLE_FRAC:
            # a material the projector can't see: the spec's height for the face it matches. The
            # few depth pixels such a top does return are wrong, not noisy (foam: a consistent
            # 62 mm on a 30 mm block, 2026-10-08) — never a sparse median
            p0 = [_on_plane(px, py, K, T_bc, surf, 0.0) for px, py in box]
            if any(p is None for p in p0):
                continue
            a0 = math.dist(p0[0], p0[1])
            b0 = math.dist(p0[1], p0[2])
            height = _spec_height(spec, max(a0, b0), min(a0, b0))
            source = "colour+spec"
        if height is None and standing.size >= MIN_STANDING:
            height = float(np.median(standing))
            source = "colour"
        if height is None:
            continue
        corners = [_on_plane(px, py, K, T_bc, surf, height) for px, py in box]
        if any(c is None for c in corners):
            continue
        uv = [surf.local(c) for c in corners]
        cu, cv, ang_s, length, width = robust_rect(uv)
        if length < 1e-6 or width < 1e-6:
            continue
        centre = surf.point(cu, cv, height)
        ax = tuple(math.cos(ang_s) * surf.x_axis[j] + math.sin(ang_s) * surf.y_axis[j] for j in range(3))
        theta = math.atan2(ax[1], ax[0])
        ca, sa = math.cos(ang_s), math.sin(ang_s)
        rect = []
        for su, sv in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            du, dv = su * length / 2, sv * width / 2
            rect.append(surf.point(cu + du * ca - dv * sa, cv + du * sa + dv * ca, height))
        zin = zmap[blob]
        zin = zin[~np.isnan(zin)]
        if zin.size:
            zmed = float(np.median(zin))
        else:
            zmed = float(math.dist(T_bc.translation, centre))
        cells = int(area // (stride * stride)) or 1
        out.append(
            Part(
                source=source,
                depth_valid=vfrac,
                rect_fill=rect_fill,
                centre=tuple(centre),
                theta=_wrap_half(theta),
                length_m=length,
                width_m=width,
                height_m=height,
                corners=[tuple(c) for c in rect],
                pixel=_project(T_cb, K, centre),
                corners_px=[_project(T_cb, K, q) for q in rect],
                cells=cells,
                near_edge=near_edge,
                rect_uv=(cu, cv, ang_s, length, width),
                range_m=zmed,
                margin_m=max(FOOTPRINT_MARGIN_M, BLUR_PER_M * zmed * 2),
            )
        )
    return out


def grid_cells(w: int, h: int, channels: int, colour: bytes, part, stride: int) -> list[int]:
    """The coarse-grid cells (``stride``) under the part's picture rectangle — what
    :func:`.volume.clear_the_way` needs to know who pins whom."""
    if not available():
        return []
    gw, gh = (w + stride - 1) // stride, (h + stride - 1) // stride
    poly = np.array([[px, py] for px, py in part.corners_px], np.int32)
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [poly], 1)
    cells = []
    for j in range(gh):
        for i in range(gw):
            if m[j * stride, i * stride]:
                cells.append(j * gw + i)
    return cells
