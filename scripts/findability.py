#!/usr/bin/env python3
"""The smallest part the detector finds at a given distance — the datasheet's findability
table, from the D435 model (``perceptronics.synthscene.Sensor``), to be replaced by the real
measurement (AIR.md §3a). For each camera height over a level table and each part size: N
cells with one such part straight under the camera (± a little tilt and offset), read through
the realistic sensor, detected with a hand-eye off by up to 1°. Prints found %, the size error
(p95 of |measured − true| over length and width) and the height error, as Markdown.

    python3 scripts/findability.py                       # the table
    python3 scripts/findability.py -n 20 --json out.json

Pure stdlib. One line per (height, part); ~3 min for the defaults.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from perceptronics.partspec import PartSpec  # noqa: E402
from perceptronics.synthscene import Box, Sensor, camera_looking_at, render_depth, sense  # noqa: E402
from perceptronics.volume import find_parts  # noqa: E402
from urctl.pose import Transform  # noqa: E402

W, H = 424, 240  # the D435's 848×480 at half size (what the pick server runs at arm's length)
K = {"fx": 308.9, "fy": 309.1, "ppx": 213.3, "ppy": 121.7}
TABLE = 0.0
HEIGHTS_M = (0.30, 0.40, 0.50, 0.60, 0.80, 1.00, 1.20, 1.50)
# (length, width, height) mm: from a washer-sized part to a shoebox
PARTS_MM = (
    (20, 20, 8),
    (30, 20, 12),
    (40, 30, 15),
    (50, 30, 30),
    (60, 40, 20),
    (110, 70, 30),
    (150, 100, 50),
    (200, 150, 80),
)
REAL = Sensor(dropout=0.15)  # scripts/volume_bench.py's "real"


def one(seed: int, height: float, dims: tuple[int, int, int], cal_deg: float) -> dict:
    rng = random.Random(seed)
    L, Wd, Hh = (d / 1000.0 for d in dims)
    spec = PartSpec.from_mm(*dims)
    tilt = math.radians(rng.choice([0, 0, 5, 10]))
    head = rng.uniform(-math.pi, math.pi)
    target = (rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05), TABLE)
    eye = (
        target[0] - math.cos(head) * math.tan(tilt) * height,
        target[1] - math.sin(head) * math.tan(tilt) * height,
        TABLE + height,
    )
    T = camera_looking_at(eye, target, (math.cos(head + 1.3), math.sin(head + 1.3), 0.0))
    box = Box(
        target[0] + rng.uniform(-0.02, 0.02),
        target[1] + rng.uniform(-0.02, 0.02),
        L,
        Wd,
        Hh,
        rng.uniform(-math.pi, math.pi),
    )
    depth = render_depth(W, H, K, T, [box], table_z=TABLE)
    depth = sense(depth, W, H, K, T, [box], table_z=TABLE, sensor=REAL, seed=seed)
    ax = (rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))
    n = math.sqrt(sum(a * a for a in ax))
    ang = math.radians(rng.uniform(0, cal_deg))
    T_det = T.compose(
        Transform.from_pose([rng.gauss(0, 1) * 0.001 * cal_deg for _ in range(3)] + [a / n * ang for a in ax])
    )
    sc = find_parts(W, H, depth, 0.001, K, T_det, spec=spec)
    hit = None
    for p in sc.parts:
        if math.dist(p.centre[:2], (box.x, box.y)) < max(0.5 * Wd, 0.01) + 0.003 * height:
            hit = p
            break
    if hit is None:
        why = sorted((p.why or "?") for p in sc.rejected if p.near)
        return {"found": False, "why": why[0] if why else "nothing there"}
    return {
        "found": True,
        "size_err_mm": max(abs(hit.length_m - L), abs(hit.width_m - Wd)) * 1000,
        "height_err_mm": abs(hit.height_m - Hh) * 1000,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-n", type=int, default=12, help="cells per (height, part) (default 12)")
    ap.add_argument("--cal-deg", type=float, default=1.0)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    rows = []
    print("| camera height | " + " | ".join(f"{d[0]}×{d[1]}×{d[2]}" for d in PARTS_MM) + " |")
    print("| --- | " + " | ".join("---" for _ in PARTS_MM) + " |")
    for height in HEIGHTS_M:
        cells = []
        for dims in PARTS_MM:
            res = [
                one(1000 * int(height * 100) + 10 * PARTS_MM.index(dims) + i, height, dims, a.cal_deg)
                for i in range(a.n)
            ]
            found = [r for r in res if r["found"]]
            rate = len(found) / len(res)
            if found:
                se = sorted(r["size_err_mm"] for r in found)
                he = sorted(r["height_err_mm"] for r in found)
                p95 = se[min(len(se) - 1, int(0.95 * len(se)))]
                hp95 = he[min(len(he) - 1, int(0.95 * len(he)))]
            else:
                p95 = hp95 = None
            whys = sorted({r["why"] for r in res if not r["found"]})
            cells.append(
                {
                    "part_mm": dims,
                    "found": rate,
                    "size_err_p95_mm": p95,
                    "height_err_p95_mm": hp95,
                    "misses": whys,
                }
            )
        rows.append({"height_m": height, "cells": cells})

        def fmt(c):
            if c["found"] == 0:
                return f"— ({c['misses'][0]})" if c["misses"] else "—"
            s = f"{c['found'] * 100:.0f} %"
            if c["size_err_p95_mm"] is not None:
                s += f", ±{c['size_err_p95_mm']:.0f} mm"
            return s

        print(f"| {height:.2f} m | " + " | ".join(fmt(c) for c in cells) + " |", flush=True)
    if a.json:
        a.json.write_text(
            json.dumps({"n": a.n, "cal_deg": a.cal_deg, "sensor": "real", "rows": rows}, indent=1)
        )


if __name__ == "__main__":
    main()
