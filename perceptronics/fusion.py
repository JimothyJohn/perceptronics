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
lifted by that height, so it is the colour's outline, not the depth's — **clipped by the
depth where the depth is valid** (2026-10-09 on the UR3e): pixels of the blob with depth that
puts them well below the top are not the top — a side face showing at the picture's edge
(a block read 50 → 40 mm wide and was refused), a white cable lying off the block (block
plus cable read 59 × 37 and passed), a cylinder's lead. Holes stay (foam); only valid depth
below the top band is dropped, only past a blur width from the top (the depth's blurred ring
just inside the colour's sharp edge reads low too, and belongs to the top), and only when
enough of the blob remains.

**Parts touching are cut apart by the part's size** (2026-10-09 evening, the fixtures
``touch_*``): two blocks side by side read as one 59 × 51 outline, end to end 98 × 29, three
across 89 × 57 — the seam is faint or absent in colour. When :meth:`PartSpec.touching` says the
outline is n parts along one side (and m along the other), the rectangle is cut into those
cells; if every cell holds its share of the blob (:data:`SPLIT_FILL`) and measures as the
part, the cells are the parts. A leaner beside a block (74 × 49, also "two side by side" at
±25 %) is not cut: its face is no rectangle, so a cell comes up short.

**Too close, not foam** (the same day): a white outline with no depth under it is taken
for foam and given the part's height — but when the blob's expected top sits nearer the
camera than the D435 can measure (:data:`MIN_DEPTH_RANGE_M`), no depth means too close,
and the part is refused with that reason (a 57 mm stack at 0.28 m passed as a 30 mm block).
numpy + OpenCV
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
TOP_BAND_M = 0.008  # valid depth this far below the blob's top is not the top: a side face, a cable
SPLIT_FILL = (
    0.8  # a cell of a parts-touching cut holds at least this much of its rectangle, or it is not that cut
)
CLIP_KEEP_FRAC = 0.4  # a clip that keeps less of the blob than this is not trusted (the depth is lying)
# The D435 at 848 x 480 returned depth on a foam top 0.25 m away and none on one at 0.22 m, then
# 99 % on a stack's top at 0.214 m (UR3e, 2026-10-09, fixture ``stack_0p28m``): the floor is the
# material's as much as the sensor's. Only a top with *no* depth is judged by this, and "look from
# higher up" is the right advice for one this near either way.
MIN_DEPTH_RANGE_M = 0.24


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
    from .volume import BLUR_PER_M

    rgb = np.frombuffer(colour, np.uint8, count=w * h * channels).reshape(h, w, channels)[:, :, :3]
    mask = _mask(np.ascontiguousarray(rgb))
    hm, zmap = _heights(w, h, depth, depth_scale_m, K, T_bc, surf)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    k_er = np.ones((ERODE_PX, ERODE_PX), np.uint8)
    T_cb = T_bc.inverse()
    half_h = min(spec.heights()) / 2 if spec is not None and spec.heights() else 0.005
    ctx = _Ctx(K, T_bc, T_cb, surf, spec, hm, zmap, stride)
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
        # the outline clipped by the depth: a pixel with depth that says it is well below the
        # top (a side face, a cable off the block, the table under a ragged edge) is not the top;
        # holes stay. Under a top the depth measures, the band hangs from that top; with no
        # measured top (foam), from the half-height line
        if standing.size >= MIN_STANDING:
            floor = float(np.median(standing)) - TOP_BAND_M
        else:
            floor = half_h
        hb = hm[blob]
        low = ~np.isnan(hb) & (hb < floor)
        if low.any():
            kept = blob.copy()
            kept[blob] = ~low
            kernel = np.ones((OPEN_PX, OPEN_PX), np.uint8)
            kept = cv2.morphologyEx(kept.astype(np.uint8), cv2.MORPH_OPEN, kernel)
            # the depth's blurred ring just inside the colour's edge reads low too: give the
            # top a blur width back (within the outline) so only what is clearly past it goes
            r = max(1, math.ceil(BLUR_PER_M * K["fx"]))  # the blur in pixels: 0.8 % of the range
            kept = cv2.dilate(kept, np.ones((2 * r + 1, 2 * r + 1), np.uint8)).astype(bool) & blob
            if kept.sum() >= max(MIN_BLOB_PX, CLIP_KEEP_FRAC * area):
                kn, klab, kstats, _ = cv2.connectedComponentsWithStats(kept.astype(np.uint8), connectivity=8)
                big = 1 + int(np.argmax(kstats[1:, cv2.CC_STAT_AREA])) if kn > 1 else 0
                if big:
                    blob = klab == big
                    x, y, bw, bh, area = (int(v) for v in kstats[big])
                    near_edge = x <= EDGE_PX or y <= EDGE_PX or x + bw >= w - EDGE_PX or y + bh >= h - EDGE_PX
        whole = _measure(blob, area, near_edge, vfrac, valid, standing, half_h, ctx)
        if whole is None:
            continue
        part, rect_px = whole
        # parts touching: when the outline is n parts of the spec long (and m wide), the
        # rectangle is cut into those cells, and if every cell measures as the part and the
        # cells cover the blob, the cells are the parts (two 50 x 30 blocks read as one 59 x 51
        # or 98 x 29, three across as 89 x 57 — UR3e, 2026-10-09; the seam is faint or absent
        # in colour, so the part's size is what splits them)
        pieces = _split_touching(blob, part, rect_px, spec, near_edge, vfrac, valid, standing, half_h, ctx)
        out.extend(pieces if pieces else [part])
    return out


class _Ctx:
    """What measuring a blob needs besides the blob: the camera, the surface, the spec, the
    height and range maps."""

    def __init__(self, K, T_bc, T_cb, surf, spec, hm, zmap, stride):
        self.K, self.T_bc, self.T_cb, self.surf, self.spec = K, T_bc, T_cb, surf, spec
        self.hm, self.zmap, self.stride = hm, zmap, stride


def _measure(blob, area, near_edge, vfrac, valid, standing, half_h, ctx):
    """A blob's :class:`.volume.Part` and its picture rectangle ``(cx, cy, rw, rh, angle)``,
    or None when it is flat, has no height, or leaves the surface. ``vfrac``, ``valid`` and
    ``standing`` are the depth under its inner region (a cell of a split shares its whole's)."""
    from .volume import BLUR_PER_M, FOOTPRINT_MARGIN_M, Part, _project, _wrap_half, robust_rect

    K, T_bc, T_cb, surf, spec = ctx.K, ctx.T_bc, ctx.T_cb, ctx.surf, ctx.spec
    # the rectangle: the colour's outline, in pixels
    pts = np.column_stack(np.nonzero(blob))[:, ::-1].astype(np.float32)
    (cx, cy), (rw, rh), ang = cv2.minAreaRect(pts)
    box = cv2.boxPoints(((cx, cy), (rw, rh), ang))
    rect_fill = float(area / max(1.0, rw * rh))  # 1 = the blob is its rectangle
    if vfrac >= HOLE_FRAC and standing.size < FLAT_FRAC * max(1, valid.size):
        return None  # flat: paper, tape, a label, a mark on the table
    height = None
    why = None
    if vfrac < HOLE_FRAC:
        # a material the projector can't see: the spec's height for the face it matches. The
        # few depth pixels such a top does return are wrong, not noisy (foam: a consistent
        # 62 mm on a 30 mm block, 2026-10-08) — never a sparse median
        p0 = [_on_plane(px, py, K, T_bc, surf, 0.0) for px, py in box]
        if any(p is None for p in p0):
            return None
        a0 = math.dist(p0[0], p0[1])
        b0 = math.dist(p0[1], p0[2])
        height = _spec_height(spec, max(a0, b0), min(a0, b0))
        source = "colour+spec"
        if height is not None:
            # unless that top would be nearer than the camera can see: then the holes are
            # the range, and the thing is as likely a stack as a part
            top = _on_plane(cx, cy, K, T_bc, surf, height)
            if top is not None and math.dist(T_bc.translation, top) < MIN_DEPTH_RANGE_M:
                why = (
                    f"too close to the camera to measure ({math.dist(T_bc.translation, top):.2f} m):"
                    " look from higher up"
                )
    if height is None and standing.size >= MIN_STANDING:
        height = float(np.median(standing))
        source = "colour"
    if height is None:
        return None
    corners = [_on_plane(px, py, K, T_bc, surf, height) for px, py in box]
    if any(c is None for c in corners):
        return None
    uv = [surf.local(c) for c in corners]
    cu, cv, ang_s, length, width = robust_rect(uv)
    if length < 1e-6 or width < 1e-6:
        return None
    centre = surf.point(cu, cv, height)
    ax = tuple(math.cos(ang_s) * surf.x_axis[j] + math.sin(ang_s) * surf.y_axis[j] for j in range(3))
    theta = math.atan2(ax[1], ax[0])
    ca, sa = math.cos(ang_s), math.sin(ang_s)
    rect = []
    for su, sv in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        du, dv = su * length / 2, sv * width / 2
        rect.append(surf.point(cu + du * ca - dv * sa, cv + du * sa + dv * ca, height))
    zin = ctx.zmap[blob]
    zin = zin[~np.isnan(zin)]
    if zin.size:
        zmed = float(np.median(zin))
    else:
        zmed = float(math.dist(T_bc.translation, centre))
    cells = int(area // (ctx.stride * ctx.stride)) or 1
    part = Part(
        why=why,
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
    return part, (cx, cy, rw, rh, ang)


def _split_touching(blob, part, rect_px, spec, near_edge, vfrac, valid, standing, half_h, ctx) -> list:
    """The blob cut into the parts it is, when the spec says its outline is n parts touching
    and every cell of the cut measures as the part and holds its share of the blob; else
    ``[]``. The cut is along the blob's rectangle: n cells along the long side, m along the
    short (``PartSpec.touching``)."""
    from .volume import RANGE_SLACK

    if spec is None or part.why is not None:
        return []
    nm = spec.touching(part.length_m, part.width_m, part.height_m, RANGE_SLACK * part.range_m)
    if nm is None:
        return []
    cx, cy, rw, rh, ang = rect_px
    a = math.radians(ang)
    u, v = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))  # along rw, along rh
    if rw < rh:  # the long side first
        u, v, rw, rh = v, u, rh, rw
    n, m = nm
    cw, ch = rw / n, rh / m
    pieces = []
    for i in range(n):
        for j in range(m):
            du, dv = ((i + 0.5) / n - 0.5) * rw, ((j + 0.5) / m - 0.5) * rh
            ccx, ccy = cx + du * u[0] + dv * v[0], cy + du * u[1] + dv * v[1]
            poly = np.array(
                [
                    [
                        ccx + s_ * cw / 2 * u[0] + t * ch / 2 * v[0],
                        ccy + s_ * cw / 2 * u[1] + t * ch / 2 * v[1],
                    ]
                    for s_, t in ((1, 1), (-1, 1), (-1, -1), (1, -1))
                ],
                np.float32,
            )
            mask = np.zeros(blob.shape, np.uint8)
            cv2.fillPoly(mask, [np.round(poly).astype(np.int32)], 1)
            cell = blob & mask.astype(bool)
            area = int(cell.sum())
            if area < MIN_BLOB_PX or area < SPLIT_FILL * cw * ch:
                return []
            got = _measure(cell, area, near_edge, vfrac, valid, standing, half_h, ctx)
            if got is None:
                return []
            piece, _ = got
            if piece.why is not None or spec.why_not(
                piece.length_m, piece.width_m, piece.height_m, RANGE_SLACK * piece.range_m
            ):
                return []
            pieces.append(piece)
    return pieces


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
