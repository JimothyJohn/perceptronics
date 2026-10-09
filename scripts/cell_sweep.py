#!/usr/bin/env python3
"""Verify the detector on the cell: move the camera through a set of views over the parts and
record, at each, what the pick server finds — the routine behind TESTING.md.

    python3 scripts/cell_sweep.py sweep TAG --part 50x30x30 --centre -0.36 0.01
    python3 scripts/cell_sweep.py sweep TAG --part 75x75x18 --shape cyl --centre -0.29 0.03 --no-sides
    python3 scripts/cell_sweep.py view NAME --point -0.36 0.01 0.0 --height 0.35 [--yaw 90]
    python3 scripts/cell_sweep.py view NAME --cam -0.24 0.01 0.38 --at -0.36 0.01 0.0   # oblique
    python3 scripts/cell_sweep.py view NAME --point ... --no-move                         # just look

A client of the running cockpit on the pick PC (``--cockpit``, default the cell address): every
pose comes from ``POST /api/robot/view`` (straight down over a base point) or is built here for an
oblique look-at through the cockpit's hand-eye; every move is ``POST /api/robot/move`` at 0.1 m/s
with the cockpit's safety envelope and the controller's IK in front of it; a refused move is
reported, not retried. The pendant must be in Remote. At each view the pick server is asked
``GET /api/pick/scene`` with the program's own options for the part, and the colour and depth
pictures are saved — ``<out>/<tag>_<view>_{color,depth}.png`` and ``.json`` — so a view that
misbehaves becomes a labelled fixture.

The sweep's views: straight down 0.35 m over the parts' centroid, the parts toward each side of the
picture (``--no-sides`` when the parts sit past ~0.36 m out on a UR3e: those poses protective-stop),
an 18° oblique from nearer the base, the camera at its 0.28 m floor, the picture turned 90°, and
a park straight down again. It ends with one table: parts found and their sizes per view, and each
part's position spread and heading range across views. Pure stdlib + ``urctl.pose``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from urctl.pose import Transform, pose_trans  # noqa: E402

DEFAULT_COCKPIT = "http://192.168.3.20:7621"
VIEWS = [
    ("down35", "--point {x} {y} 0.0 --height 0.35"),
    ("sidepy", "--point {x} {yp} 0.0 --height 0.35"),
    ("sidemy", "--point {x} {ym} 0.0 --height 0.35"),
    ("obl18", "--cam {xc} {y} 0.38 --at {x} {y} 0.0"),
    ("low28", "--point {x} {y} 0.0 --height 0.28"),
    ("turn90", "--point {x} {y} 0.0 --height 0.35 --yaw 90"),
    ("park", "--point {x} {y} 0.0 --height 0.35"),
]


class Cockpit:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def post(self, path: str, body: dict, timeout: float = 60.0) -> dict:
        req = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)

    def get(self, path: str, timeout: float = 15.0) -> bytes:
        with urllib.request.urlopen(self.base + path, timeout=timeout) as r:
            return r.read()

    def scene(self, opts: str) -> dict:
        return json.loads(self.get(f"/api/pick/scene?opts={urllib.parse.quote(opts)}"))


def part_options(part: str, tol: int, shape: str, grip: int | None) -> str:
    dims = part.lower().split("x")
    height = float(dims[2]) if len(dims) == 3 else 30.0
    if grip is None:
        grip = max(2, min(15, int(height) - 4))  # the node refuses a grip that lands on the table
    return (
        f"part={part} tol={tol}{' shape=cyl' if shape == 'cyl' else ''} order=LR,FB grip={grip} approach=25"
        " gripcheck=1 room=20 arm=UR3 node=sweep loc=1 locs=1 proto=3"
    )


def fmt_part(p: dict) -> str:
    size = p.get("size_mm") or [p.get("length_mm"), p.get("width_mm")]
    at = [round(v, 3) for v in p.get("centre", [])]
    return f"{size} x {p.get('height_mm')} mm at {at} heading {p.get('theta_deg')}"


def look_at_pose(c: Cockpit, cam: list[float], at: list[float]) -> tuple[list[float], float]:
    """The flange pose that puts the colour camera at ``cam`` looking at ``at`` (image x kept near base X)."""
    info = json.loads(c.get("/api/info"))
    T_fc = Transform.from_pose(info["robot"]["handeye"]["flange_to_color_pose"])
    z = [t - k for t, k in zip(at, cam, strict=True)]
    n = math.sqrt(sum(v * v for v in z))
    z = [v / n for v in z]
    d = z[0]
    x = [1.0 - d * z[0], -d * z[1], -d * z[2]]
    n = math.sqrt(sum(v * v for v in x))
    x = [v / n for v in x]
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    pose = Transform.from_axes(x, y, z, cam).compose(T_fc.inverse()).to_pose()
    return pose, math.degrees(math.acos(max(-1.0, min(1.0, -z[2]))))


def view(c: Cockpit, a: argparse.Namespace, out_dir: Path, part_opts: str) -> dict:
    """One view: the pose, the move (unless --no-move), the scene, the pictures. Returns the record."""
    rec: dict = {"name": a.name, "point": a.point, "height": a.height, "cam": a.cam, "at": a.at, "yaw": a.yaw}
    if a.cam and a.at:
        pose, tilt = look_at_pose(c, a.cam, a.at)
        print(f"{a.name}: camera at {a.cam} looking at {a.at}, {tilt:.0f}° from straight down")
    else:
        got = c.post("/api/robot/view", {"arm": a.arm, "point_m": a.point, "height_m": a.height})
        if not got.get("ok"):
            rec["refused"] = f"view: {got.get('error')}"
            print(f"{a.name}: {rec['refused']}")
            return rec
        pose = got["polyscope_pose"]
        print(f"{a.name}: camera {a.height:.2f} m over {a.point}; IK reachable={got.get('reachable')}")
    if a.yaw:
        pose = pose_trans(pose, [0, 0, 0, 0, 0, math.radians(a.yaw)])
    rec["pose"] = pose
    if not a.no_move:
        mv = c.post("/api/robot/move", {"pose": pose, "velocity": 0.1}, timeout=120)
        if not mv.get("ok"):
            why = mv.get("error") or (mv.get("safety") or {}).get("violations") or "the move did not confirm"
            rec["refused"] = f"move: {why}"
            print(f"  refused: {why}")
            return rec
        print(f"  landed {[round(v, 3) for v in (mv.get('landed') or [])]}")
        time.sleep(1.5)
    st = c.post("/api/robot/state", {})
    rec["robot"] = {k: st.get(k) for k in ("robot_mode", "safety_mode", "control_mode")}
    print(f"  robot {st.get('safety_mode')} ; {st.get('control_mode')}")
    d = c.scene(part_opts)
    rec["scene"] = d
    surf = d.get("surface") or {}
    print(
        f"  status={d.get('status')} {str(d.get('reason'))[:60]} | table tilt {surf.get('tilt_deg')}°"
        f" src {surf.get('source')}"
    )
    for n in d.get("notes", []):
        print("     note:", n[:120])
    for p in d.get("parts", []):
        print(f"     PART #{p.get('order')} {fmt_part(p)}")
    for p in d.get("rejected", [])[:6]:
        print(f"     reject {fmt_part(p)} near={p.get('near')}: {p.get('why')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{a.name}_color.png").write_bytes(c.get("/api/color.png"))
    (out_dir / f"{a.name}_depth.png").write_bytes(c.get("/api/depth.png"))
    (out_dir / f"{a.name}.json").write_text(json.dumps(rec, indent=1))
    return rec


def sweep(c: Cockpit, a: argparse.Namespace, out_dir: Path, part_opts: str) -> None:
    x, y = a.centre
    fmt = dict(x=x, y=y, yp=y + 0.09, ym=y - 0.09, xc=x + 0.12)
    rows = []
    for name, args in VIEWS:
        if a.no_sides and name in ("sidepy", "sidemy"):
            continue
        va = parse_view_args(f"{a.tag}_{name}", args.format(**fmt).split(), a)
        rows.append((name, view(c, va, out_dir, part_opts)))
    print(f"\n== {a.tag}: part {a.part} ±{a.tol} % ({'cylinder' if a.shape == 'cyl' else 'box'})")
    tracks: dict = {}
    for name, rec in rows:
        if rec.get("refused"):
            print(f"{name:8} REFUSED  {rec['refused'][:100]}")
            continue
        sc = rec.get("scene") or {}
        parts = sc.get("parts", [])
        near = [p for p in sc.get("rejected", []) if p.get("near")]
        tilt = (sc.get("surface") or {}).get("tilt_deg")
        sizes = ", ".join(f"{p['size_mm'][0]}x{p['size_mm'][1]}x{p['height_mm']}" for p in parts)
        whys = "; ".join(f"{p['size_mm'][0]}x{p['size_mm'][1]}x{p['height_mm']} {p['why']}" for p in near)
        print(
            f"{name:8} found {len(parts)}  table {tilt}°  [{sizes}]"
            + (f"  near-miss: {whys}" if whys else "")
        )
        for p in parts:
            cxy = p["centre"][:2]
            key = min(tracks, key=lambda k: math.dist(k, cxy), default=None)
            if key is None or math.dist(key, cxy) > 0.03:
                key = (round(cxy[0], 3), round(cxy[1], 3))
                tracks[key] = []
            tracks[key].append((name, p["centre"], p.get("theta_deg")))
    print("-- position spread across views (mm) and heading range (deg):")
    for key, hits in tracks.items():
        xs = [h[1][0] for h in hits]
        ys = [h[1][1] for h in hits]
        th = [h[2] for h in hits if h[2] is not None]
        print(
            f"   part near {key}: seen in {len(hits)} views, x spread {1000 * (max(xs) - min(xs)):.0f},"
            f" y spread {1000 * (max(ys) - min(ys)):.0f}, heading {min(th):.1f}..{max(th):.1f}"
        )
    print(f"pictures and records: {out_dir}")


def add_view_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--point", type=float, nargs=3, help="straight down over this base point (m)")
    ap.add_argument("--height", type=float, help="camera height over --point (m)")
    ap.add_argument("--cam", type=float, nargs=3, help="oblique: the camera here (base m) ...")
    ap.add_argument("--at", type=float, nargs=3, help="... looking at this base point")
    ap.add_argument("--yaw", type=float, default=0.0, help="deg about the flange Z (the picture turned)")
    ap.add_argument("--no-move", action="store_true", help="look from where the arm is")


def parse_view_args(name: str, argv: list[str], base: argparse.Namespace) -> argparse.Namespace:
    ap = argparse.ArgumentParser(add_help=False)
    add_view_args(ap)
    va = ap.parse_args(argv)
    va.name, va.arm, va.no_move = name, base.arm, False
    return va


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cockpit", default=os.environ.get("PERCEPTRONICS_COCKPIT", DEFAULT_COCKPIT))
    ap.add_argument("--arm", default="UR3e", help="the robot model, for the base keep-out")
    ap.add_argument(
        "--out", help="directory for the pictures and records (default captures/sweeps/<tag or name>)"
    )
    ap.add_argument("--part", default="50x30x30", help="LxWxH mm (a cylinder: DxDxH)")
    ap.add_argument("--tol", type=int, default=25)
    ap.add_argument("--shape", choices=["box", "cyl"], default="box")
    ap.add_argument(
        "--grip", type=int, default=None, help="grip depth mm below the top (default: from the height)"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("view", help="one view")
    v.add_argument("name")
    add_view_args(v)
    s = sub.add_parser("sweep", help="the standard views, then a table")
    s.add_argument("tag")
    s.add_argument(
        "--centre", type=float, nargs=2, default=[-0.355, 0.01], help="the parts' centroid (base x y, m)"
    )
    s.add_argument(
        "--no-sides", action="store_true", help="skip the two side views (parts far out on a UR3e)"
    )
    a = ap.parse_args()
    if a.cmd == "view" and not ((a.point and a.height is not None) or (a.cam and a.at)):
        ap.error("view needs --point X Y Z --height H, or --cam X Y Z --at X Y Z")
    c = Cockpit(a.cockpit)
    opts = part_options(a.part, a.tol, a.shape, a.grip)
    out_dir = Path(a.out) if a.out else Path("captures/sweeps") / (a.tag if a.cmd == "sweep" else a.name)
    if a.cmd == "view":
        rec = view(c, a, out_dir, opts)
        return 1 if rec.get("refused") else 0
    sweep(c, a, out_dir, opts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
