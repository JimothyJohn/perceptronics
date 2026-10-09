"""Colour + depth fusion (:mod:`perceptronics.fusion`): the parts the depth can't see.

Real frames from the UR3e cell, 2026-10-08 (``tests/fixtures/d435/foam_*``): white foam blocks
whose tops return 10-60 % depth. The depth alone finds one or two of four; with the colour
outline all four, 50 x 30 +-5 mm, and the e-stop box beside them when its size is asked for.
Synthetic frames hold the two rules the fixtures can't isolate: a flat white thing on the
table is not a part, and a hole in the depth the size of the part is one."""

from __future__ import annotations

import json
import math
import zlib
from pathlib import Path

import pytest

from perceptronics import fusion
from perceptronics.partspec import PartSpec
from perceptronics.volume import Surface, find_parts
from urctl.pose import Transform

pytestmark = pytest.mark.skipif(
    not fusion.available(), reason="numpy + OpenCV (the vision extra) not installed"
)

REAL = Path(__file__).parent / "fixtures" / "d435"
FOAM = sorted(p.stem[: -len(".colour")] for p in REAL.glob("foam_*.colour.jpg"))


def real(name: str, spec: PartSpec, colour: bool = True):
    import cv2

    meta = json.loads((REAL / f"{name}.json").read_text())
    depth = zlib.decompress((REAL / f"{name}.depth.zlib").read_bytes())
    rgb = cv2.cvtColor(cv2.imread(str(REAL / f"{name}.colour.jpg")), cv2.COLOR_BGR2RGB)
    T = Transform.from_pose(meta["flange_pose"]).compose(Transform.from_pose(meta["flange_to_color_pose"]))
    sc = find_parts(
        meta["width"],
        meta["height"],
        depth,
        meta["depth_scale_m"],
        meta["intrinsics"],
        T,
        spec=spec,
        colour=rgb.tobytes() if colour else None,
        colour_channels=3,
    )
    return meta, sc


@pytest.mark.parametrize("name", FOAM)
def test_the_colour_outline_finds_every_foam_block_the_depth_cannot(name):
    meta, sc = real(name, PartSpec.from_mm(*meta_part(name)))
    assert len(sc.parts) == meta["count"], [(p.pixel, p.why) for p in sc.rejected if p.near]
    for px in meta["pixels"]:
        assert min(math.dist(px, p.pixel) for p in sc.parts) < 15
    for p in sc.parts:
        # the colour outline reads 49-51 x 29-31; a depth-measured foam top (enough depth to keep
        # the depth's rectangle) is the one that can be 6 mm off — the D435's limit on this material
        assert abs(p.length_m * 1000 - 50) <= 8 and abs(p.width_m * 1000 - 30) <= 8, (p.length_m, p.width_m)
        assert abs(p.height_m * 1000 - 30) <= 6, p.height_m


def meta_part(name: str) -> list[int]:
    return json.loads((REAL / f"{name}.json").read_text())["part_mm"]


@pytest.mark.parametrize("name", ["foam_blocks_0p40m", "foam_blocks_and_estop_0p42m"])
def test_the_depth_alone_misses_foam_blocks(name):
    # what the fusion is for: the same frame without the colour finds fewer (1-2 of 4)
    meta, sc = real(name, PartSpec.from_mm(50, 30, 30), colour=False)
    assert len(sc.parts) < meta["count"]


@pytest.mark.parametrize("name", [n for n in FOAM if "estop" in n])
def test_the_estop_box_is_a_part_of_about_its_own_size_and_not_of_the_blocks(name):
    # not a clean test object (a cable and a connector hang off it, a button stands on it): the
    # depth's half-height footprint at a 44 mm spec takes the connector in (124 x 105), the colour
    # outline reads 113 x 84. Either is "the box"; neither is ever a 50 x 30 block.
    meta, sc = real(name, PartSpec.from_mm(108, 84, 44))
    if "estop_pixel" not in meta or not sc.parts:
        pytest.skip("the box is cut off by the picture's edge in this view")
    assert len(sc.parts) == 1, [(p.pixel, p.length_m, p.width_m, p.why) for p in sc.parts + sc.rejected]
    assert math.dist(meta["estop_pixel"], sc.parts[0].pixel) < 40
    assert 100 <= sc.parts[0].length_m * 1000 <= 130 and 75 <= sc.parts[0].width_m * 1000 <= 110
    _, blocks = real(name, PartSpec.from_mm(50, 30, 30))
    assert all(math.dist(meta["estop_pixel"], p.pixel) > 30 for p in blocks.parts)


# -- synthetic: the two rules ----------------------------------------------------------------------

W, H = 320, 240
K = {"fx": 300.0, "fy": 300.0, "ppx": W / 2, "ppy": H / 2, "width": W, "height": H}
Z = 0.40  # the camera 0.40 m over a level table, looking straight down


def frame(square_px: tuple[int, int, int, int], *, holes: bool, raised_mm: float = 0.0):
    """A grey table with a white square on it: ``holes`` = no depth inside the square;
    ``raised_mm`` = the square's depth stands that much above the table."""
    import numpy as np

    rgb = np.full((H, W, 3), 120, np.uint8)
    x0, y0, x1, y1 = square_px
    rgb[y0:y1, x0:x1] = 245
    depth = np.full((H, W), round(Z / 0.001), np.uint16)
    if holes:
        depth[y0 + 2 : y1 - 2, x0 + 2 : x1 - 2] = 0
    elif raised_mm:
        depth[y0:y1, x0:x1] = round((Z - raised_mm / 1000) / 0.001)
    return rgb.tobytes(), depth.tobytes()


T_DOWN = Transform.from_pose([0.0, 0.0, Z, 0.0, math.pi, 0.0])  # camera z down the base's -z
SURF = Surface.level(0.0)


def test_a_flat_white_thing_on_the_table_is_not_a_part():
    rgb, depth = frame((120, 90, 200, 150), holes=False)
    parts = fusion.colour_parts(W, H, 3, rgb, depth, 0.001, K, T_DOWN, SURF, PartSpec.from_mm(100, 75, 30))
    assert parts == []


def test_a_hole_in_the_depth_the_size_of_the_part_is_the_part_at_the_specs_height():
    rgb, depth = frame((120, 90, 200, 150), holes=True)
    parts = fusion.colour_parts(W, H, 3, rgb, depth, 0.001, K, T_DOWN, SURF, PartSpec.from_mm(100, 75, 30))
    assert len(parts) == 1
    (p,) = parts
    assert p.source == "colour+spec" and p.depth_valid < fusion.HOLE_FRAC
    assert p.height_m == pytest.approx(0.030)
    # 80 x 60 px of white, opened and eroded a few px: ~100 x 75 mm on the table
    assert p.length_m * 1000 == pytest.approx(100, abs=10) and p.width_m * 1000 == pytest.approx(75, abs=10)


def test_a_raised_white_thing_with_full_depth_takes_its_height_from_the_depth():
    rgb, depth = frame((120, 90, 200, 150), holes=False, raised_mm=25)
    parts = fusion.colour_parts(W, H, 3, rgb, depth, 0.001, K, T_DOWN, SURF, PartSpec.from_mm(100, 75, 30))
    assert len(parts) == 1 and parts[0].source == "colour"
    assert parts[0].height_m == pytest.approx(0.025, abs=0.002)


def test_without_the_vision_extra_the_depth_path_is_unchanged(monkeypatch):
    monkeypatch.setattr(fusion, "cv2", None)
    rgb, depth = frame((120, 90, 200, 150), holes=True)
    assert not fusion.available()
    assert (
        fusion.colour_parts(W, H, 3, rgb, depth, 0.001, K, T_DOWN, SURF, PartSpec.from_mm(100, 75, 30)) == []
    )
