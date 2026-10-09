"""The pick server — what the PolyScope 5 **Perceptronic Pick** program node talks to.

The node's URScript runs *inside* the robot program the operator plays from the
pendant, so it runs in Local mode, needs no Primary connection and no cockpit robot
link. At the node the controller opens a plain TCP socket to this server (the
cockpit's host, ``--pick-port``, default 7622), sends one line with its own flange
pose, and reads back one parenthesised list of numbers — the shape URScript's
``socket_read_ascii_float`` parses. The controller then does the moving itself.

Requests (one line each, ASCII, ≤ 1 kB; the pose is URScript's ``to_str(pose)``):

``FIND p[x, y, z, rx, ry, rz] [u=<px> v=<px>] [lean=<deg>]``
    Detect the white blocks in a colour+depth frame taken *after* the request
    arrived (the arm has stopped by then), place them in the base frame through the
    hand-eye and the flange pose sent, and pick one: the block nearest pixel
    ``(u, v)`` — the spot the operator tapped when teaching the node — or, without
    one, the block nearest the image centre.

``REFINE p[x, y, z, rx, ry, rz] p[cx, cy, cz, 0, 0, 0] [lean=<deg>]``
    The second, closer look: the block whose top centre lies within 60 mm of
    ``(cx, cy, cz)`` (the FIND answer), seen from the flange pose sent.

``LOOK p[x, y, z, rx, ry, rz] p[cx, cy, cz, 0, 0, 0]``
    Where to take the closer look from: the flange pose that puts the camera **straight
    above the block's top centre, looking straight down** — like the approach, with the
    camera where the tool will be — halfway down from its height now (never nearer than
    :data:`LOOK_MIN_M`; the D435 has no depth closer than ~0.28 m), the block in the
    middle of the picture (:data:`LOOK_AIM_DEG` = 0 since 2026-10-08: Nick, at the cell,
    "the closer look is supposed to move above the part similar to the approach
    position" — the slanted, 12°-aimed look of 0.3.0–0.9.1 "moved up then at an angle";
    a non-zero aim keeps the block off the fingers), backed up until the fingertips
    clear the top by :data:`LOOK_TIP_CLEAR_M`. Status -6 when no such pose exists (the
    node then measures again from where it is).

``part=<L>x<W>[x<H>] [tol=<pct>]`` (FIND and REFINE, optional): the part's rough size in
mm — a box with a height on any of its faces, a cylinder on its end — and how far off it may measure
(default 25 %). Only candidates that size are considered
(:class:`perceptronics.partspec.PartSpec`); without it, anything foam-block-sized.

``LOG <text>``
    The robot program saying where it is (``start``, ``FIND status 1``, ``hover`` …):
    written to the server's log, printable ASCII only, capped; **no reply**.

``lean`` (0–30°, default 0): the grasp is **straight down** — the work surface is
flat and parallel to the base XY plane (Nick, 2026-09-27) — unless the program's own
IK check found that unsolvable and asks again leaned outward (the pick-cycle's
0 → 12 → 24° ladder, :func:`perceptronics.pickcycle.grasp_rotation`).

**Protocol 3 (the 0.10.0 node, 2026-10-08 — Nick: "You must only use tool offsets inside
of the robot not your own"):** the pose a request carries is the robot's **TCP pose under
its active TCP** (``get_actual_tcp_pose()``) and every request also carries that offset,
``tcp=p[x, y, z, rx, ry, rz]`` (``get_tcp_offset()``); the server recovers the flange
(``tcp ∘ tcp⁻¹``) for the camera and answers **poses of the TCP frame** — the tool's own
frame, as the pendant has it: its origin (the fingertips, or whatever the operator set as
the TCP) on the part's top centre, its Z straight down (or leaned), its heading kept from
the pose sent and turned so the fingers — along the TCP frame's Y — close across the
block's short side. The node moves to those poses with the operator's TCP as it is
(``movej(get_inverse_kin(pose))``), so the server never needs, and no longer has, a tool
length of its own. A request of protocol 1 or 2 (a node before 0.10.0, which zeroed the
TCP and expected flange poses for a 163 mm tool) is answered -14: the server cannot know
that tool.

Reply: ``(status, cx, cy, cz, x, y, z, rx, ry, rz)`` (protocol 2 and 3: 16 numbers,
:func:`format_reply2`). ``status`` is one of :data:`STATUS`; on 1, ``c*`` is the block's
top-face centre (base, m) and the pose is the TCP-frame pose above. The node derives
hover and grip from it with ``pose_trans`` along the tool axis. On any other status the
numbers are 0.

The server never moves anything and never talks to the robot: it answers questions
about the image. It shares the cockpit's (unauthenticated, trusted-cell) network
exposure — bind it the same way.
"""

from __future__ import annotations

import math
import re
import socketserver
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from urctl.pose import Transform, pose_inv, pose_trans

from . import partspec
from .partspec import PartSpec
from .pickcycle import Block, detect_blocks, grasp_rotation, grasp_yaw_deg, tip_pose
from .volume import Reach, Scene, Surface, find_parts, parse_order

DEFAULT_PICK_PORT = 7622
MAX_LINE = 1024
REFINE_RADIUS_M = 0.06
LOOK_MIN_M = 0.30  # camera to the block's top: past the D435's blind zone with room for the gripper
LOOK_AIM_DEG = 0.0  # the block's bearing off the optical axis (0 = dead centre; Nick, 2026-10-08)
LEANS_DEG = (0.0, 12.0, 24.0)  # the program's ladder when straight down has no joint solution
LOOK_TIP_CLEAR_M = 0.06  # the TCP (the fingertips) above the top at the look pose
LOOK_MAX_TILT_DEG = 60.0  # tool Z from straight down
MAX_LOG_TEXT = 240
DEFAULT_STROKE_M = 0.050  # Hand-E
FRESH_FRAMES = 2  # frames after the request's arrival before one is trusted still

STATUS = {
    1: "found",
    0: "no block in view",
    -1: "the block is wider than the gripper's stroke",
    -2: "the block is too close to the robot's base",
    -3: "the cockpit has no hand-eye calibration",
    -4: "no fresh camera frame",
    -5: "the second look did not find the block again",
    -6: "no closer look keeps the camera in range and the fingertips clear",
    -7: "something is in view, but nothing the size of the part",
    -9: "malformed request",
    # protocol 2 (the 0.5.0 node): why a location had nothing to pick
    -10: "the only parts in view are out of reach",
    -11: "no room for the open fingers beside any part",
    -12: "the parts in view are outside the pick area",
    -13: "the only part in view is cut off by the edge of the picture",
    # protocol 3 (the 0.10.0 node): the tool offset comes from the robot with every request
    -14: "the 3D Pick node is older than this camera computer — update the Perceptronic URCap",
}
PROTOCOL = 3  # what this server speaks; older nodes are answered -14
ZERO_POSE = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_POSE_RX = re.compile(
    rf"p\[\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*\]"
)
_KV_RX = re.compile(r"\b([uv])=(-?\d{1,5})\b")
_LEAN_RX = re.compile(rf"\blean=({_NUM})")
MAX_LEAN_DEG = 30.0


class RequestError(ValueError):
    """The line is not a request this server answers."""


def parse_request(line: str) -> dict:
    """``{"verb", "tcp_pose" (as sent), "tcp_offset" (``tcp=``, else zero), "flange"
    (``tcp_pose ∘ tcp_offset⁻¹``), "near" (REFINE, LOOK), "pixel" (FIND, optional), "part"
    (FIND, REFINE: a PartSpec or None)}``, ``{"verb": "LOG", "text"}``, or RequestError."""
    text = line.strip()
    if text[:4].upper() in ("LOG", "LOG "):  # the program never reads a reply to LOG: never refuse one
        said = text[3:].strip()[: MAX_LOG_TEXT * 2]
        clean = "".join(c if " " <= c <= "~" else "?" for c in said)[:MAX_LOG_TEXT]
        return {"verb": "LOG", "text": clean}
    if not text or len(text) > MAX_LINE:
        raise RequestError("empty or oversized request")
    verb = text.split(None, 1)[0].upper()
    if verb not in ("FIND", "REFINE", "LOOK", "NEXT"):
        raise RequestError(f"unknown verb {verb[:16]!r}")
    opts = parse_options(text)
    bare = _TCP_RX.sub("", _PLANE_RX.sub("", text))
    poses = [[float(g) for g in m.groups()] for m in _POSE_RX.finditer(bare)]
    if not poses or not all(math.isfinite(v) and abs(v) < 100.0 for p in poses for v in p):
        raise RequestError("no plausible pose p[x, y, z, rx, ry, rz] in the request")
    offset = list(opts.tcp_offset or ZERO_POSE)
    out: dict = {
        "verb": verb,
        "tcp_pose": poses[0],
        "tcp_offset": offset,
        "flange": pose_trans(poses[0], pose_inv(offset)) if opts.tcp_offset else poses[0],
        "lean": 0.0,
        "options": opts,
    }
    lean = _LEAN_RX.search(text)
    if lean:
        out["lean"] = float(lean.group(1))
        if not (0.0 <= out["lean"] <= MAX_LEAN_DEG):
            raise RequestError(f"lean must be within 0..{MAX_LEAN_DEG:.0f} deg")
    out["part"] = opts.part if verb != "LOOK" else None
    if verb == "NEXT":
        if not opts.node:
            raise RequestError("NEXT needs node=<id>")
        return out
    if verb in ("REFINE", "LOOK"):
        if len(poses) < 2:
            raise RequestError(f"{verb} needs the flange pose and the block centre")
        out["near"] = poses[1][:3]
    else:
        kv = {k: int(v) for k, v in _KV_RX.findall(text)}
        if "u" in kv and "v" in kv and kv["u"] >= 0 and kv["v"] >= 0:
            out["pixel"] = (kv["u"], kv["v"])
    return out


# -- protocol 2: the options every request of the 0.5.0 node carries -------------------------

_POSE_BODY = rf"\[\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*\]"
_PLANE_RX = re.compile(r"\bplane=p" + _POSE_BODY)
_TCP_RX = re.compile(r"\btcp=p" + _POSE_BODY)
_AREA_RX = re.compile(rf"\barea=({_NUM})[xX]({_NUM})(?![\w.])")
_ORDER_RX = re.compile(r"\border=([A-Za-z]{2},[A-Za-z]{2})\b")
_REACH_RX = re.compile(rf"\breach=({_NUM}),({_NUM})(?![\w.])")
_MM_RX = {k: re.compile(rf"\b{k}=({_NUM})(?![\w.])") for k in ("grip", "stroke")}
_NODE_RX = re.compile(r"\bnode=([0-9A-Za-z]{1,12})\b")
_INT_RX = {k: re.compile(rf"\b{k}=(\d{{1,3}})\b") for k in ("loc", "locs", "proto")}
_MM_RX["approach"] = re.compile(rf"\bapproach=({_NUM})(?![\w.])")
_GRIPCHECK_RX = re.compile(r"\bgripcheck=([01])(?=\s|$)")
_MM_RX["room"] = re.compile(rf"\broom=({_NUM})(?![\w.])")
_ACROSS_RX = re.compile(r"\bacross=(short|long)(?=\s|$)")
_ARM_RX = re.compile(r"\barm=([A-Za-z0-9]{1,8})(?=\s|$)")
MAX_LOCS = 32
QUEUE_TTL_S = 120.0  # a part seen at a picture point stays queued this long
RUN_TTL_S = 90.0  # a program that stops talking (a protective stop, the pendant's Stop) is over after this
QUIET_REASON = (
    "the program is running: the picture is measured only where the program asks (FIND, REFINE) —"
    " what it saw last is shown, nothing else is judged in between"
)
PROTO2_FIELDS = 16


@dataclass(frozen=True)
class PickOptions:
    """What the 0.5.0 node tells the server with every request (all optional; the defaults
    are protocol 1's behaviour): ``part=LxWxH tol=T``, the taught surface ``plane=p[...]``
    with ``area=<x>x<y>`` (mm, along the plane's X / Y from its origin), the pick
    ``order=LR,FB``, ``reach=<min>,<max>`` (m from the base axis), the grip depth
    ``grip=<mm>`` and the gripper's ``stroke=<mm>`` (for the finger-room check), and the
    node's identity ``node=<id> loc=<i> locs=<n> proto=2``.

    The 0.7.0 node (2026-09-30) sends no ``reach=``: it names the arm (``arm=UR3``) and the
    server asks the arm's own kinematics (:mod:`perceptronics.armik`) whether the approach
    (``approach=<mm>`` over the top) and the grip have a joint solution — straight down or
    leaned, the program's ladder — keeping only the base's keep-out radius. ``gripcheck=0``
    drops the two checks of the gripper against the *measured* part (wider than the open
    fingers, no room beside it): the part's size is known, and a width the camera reads a
    few mm wide must not veto a part the fingers fit.

    The 0.8.0 node (2026-10-01) does not drive a gripper at all — the program opens it before
    the node and closes it after — so it knows no stroke. Its grip check is ``room=<mm>``:
    that much clear space on each side of the part along the grip axis (default 20), and no
    stroke test. ``across=long`` grips a box across its long side instead of its short one.

    The 0.10.0 node (protocol 3, 2026-10-08) sends ``tcp=p[...]``: the controller's active
    TCP offset, under which its pose is reported and in whose frame every answer is given
    (:data:`tcp_offset`; the module docstring). Without it the TCP is taken to be the
    flange."""

    part: PartSpec | None = None
    tcp_offset: tuple[float, ...] | None = None  # protocol 3: the robot's active TCP offset
    surface: Surface | None = None
    order: tuple[str, str] = ("LR", "FB")
    reach: Reach | None = None
    grip_below_m: float = 0.015
    stroke_m: float = DEFAULT_STROKE_M
    approach_m: float = 0.025
    grip_check: bool = True
    room_m: float | None = None  # 0.8.0: the clear space wanted on each side of the part
    across: str = "short"  # which side of a box the fingers close across
    arm: str = ""
    node: str = ""
    loc: int = 0
    locs: int = 1
    proto: int = 1

    def fingers(self) -> dict:
        out: dict = {"grasp_below_m": self.grip_below_m, "stroke_m": self.stroke_m, "across": self.across}
        if self.room_m is not None:
            out["room_m"] = self.room_m
        return out


def parse_options(text: str) -> PickOptions:
    """The :class:`PickOptions` in a request line (or the teach screen's query); RequestError
    when one is present but malformed or out of range."""
    try:
        part = partspec.parse(text)
    except ValueError as exc:
        raise RequestError(str(exc)) from None
    kw: dict = {"part": part}
    m = _PLANE_RX.search(text)
    if m:
        pose = [float(g) for g in m.groups()]
        if not all(math.isfinite(v) and abs(v) < 100 for v in pose):
            raise RequestError("plane must be a pose p[x, y, z, rx, ry, rz]")
        size = None
        a = _AREA_RX.search(text)
        if a:
            size = (float(a.group(1)) / 1000.0, float(a.group(2)) / 1000.0)
            if not all(0.005 <= abs(v) <= 3.0 for v in size):
                raise RequestError("area must be 5..3000 mm each way")
        kw["surface"] = Surface.from_pose(pose, size)
    elif re.search(r"\bplane=", text):
        raise RequestError("plane must be a pose p[x, y, z, rx, ry, rz]")
    o = _ORDER_RX.search(text)
    if o:
        try:
            kw["order"] = parse_order(o.group(1))
        except ValueError as exc:
            raise RequestError(str(exc)) from None
    elif re.search(r"\border=", text):
        raise RequestError("order must be like order=LR,FB")
    r = _REACH_RX.search(text)
    if r:
        lo, hi = float(r.group(1)), float(r.group(2))
        if not (0.0 <= lo < 3.0 and 0.0 <= hi <= 3.0 and (hi == 0 or hi > lo)):
            raise RequestError("reach must be min,max in metres with max > min (max 0: no limit)")
        kw["reach"] = Reach(lo, hi)
    for key, name, lo, hi in (
        ("grip", "grip_below_m", 0.0, 60.0),
        ("stroke", "stroke_m", 10.0, 300.0),
        ("approach", "approach_m", 0.0, 300.0),
        ("room", "room_m", 0.0, 100.0),
    ):
        g = _MM_RX[key].search(text)
        if g:
            mm = float(g.group(1))
            if not lo <= mm <= hi:
                raise RequestError(f"{key} must be {lo:.0f}..{hi:.0f} mm")
            kw[name] = mm / 1000.0
        elif key == "room" and re.search(r"\broom=", text):
            raise RequestError("room must be a distance in mm, like room=20")
    g = _GRIPCHECK_RX.search(text)
    if g:
        kw["grip_check"] = g.group(1) == "1"
    elif re.search(r"\bgripcheck=", text):
        raise RequestError("gripcheck must be 0 or 1")
    side = _ACROSS_RX.search(text)
    if side:
        kw["across"] = side.group(1)
    elif re.search(r"\bacross=", text):
        raise RequestError("across must be short or long")
    arm = _ARM_RX.search(text)
    if arm:
        kw["arm"] = arm.group(1)
    elif re.search(r"\barm=", text):
        raise RequestError("arm must be a robot model, like arm=UR3")
    t = _TCP_RX.search(text)
    if t:
        off = [float(g) for g in t.groups()]
        if not all(math.isfinite(v) for v in off) or any(abs(v) > 2.0 for v in off[:3]):
            raise RequestError("tcp must be the active TCP offset, a pose p[x, y, z, rx, ry, rz] within 2 m")
        kw["tcp_offset"] = tuple(off)
    elif re.search(r"\btcp=", text):
        raise RequestError("tcp must be a pose p[x, y, z, rx, ry, rz]")
    n = _NODE_RX.search(text)
    if n:
        kw["node"] = n.group(1)
    for key in ("loc", "locs", "proto"):
        i = _INT_RX[key].search(text)
        if i:
            kw[key] = int(i.group(1))
    if not 0 <= kw.get("loc", 0) <= MAX_LOCS or not 1 <= kw.get("locs", 1) <= MAX_LOCS:
        raise RequestError(f"loc and locs must be within 1..{MAX_LOCS}")
    if kw.get("proto", 1) not in (1, 2, 3):
        raise RequestError("proto must be 1, 2 or 3")
    return PickOptions(**kw)


def keep_out(opts: PickOptions) -> Reach | None:
    """The radial limits the detector applies: the node's ``reach=`` when it sent one (0.5 /
    0.6), else only the base's keep-out for ``arm=`` — its outer radius +
    :data:`perceptronics.volume.REACH_MARGIN_M`; how far *out* the arm gets is the
    kinematics' answer (:meth:`PickPlanner.reachable`), not a ring's."""
    if opts.reach is not None:
        return opts.reach
    if not opts.arm:
        return None
    ring = Reach.for_model(opts.arm)
    return None if ring is None else Reach(ring.min_m, 0.0)


def format_reply2(
    status: int,
    centre: Sequence[float] | None = None,
    pose: Sequence[float] | None = None,
    *,
    loc: int = 0,
    order: int = 0,
    remaining: int = 0,
    dims_mm: Sequence[float] | None = None,
) -> str:
    """Protocol 2's line: ``(status, cx, cy, cz, x, …, rz, loc, order, remaining, L, W, H)``
    — :data:`PROTO2_FIELDS` numbers, the part's measured size in mm last."""
    vals = (
        [float(status)]
        + [float(v) for v in (centre or (0.0,) * 3)]
        + [float(v) for v in (pose or (0.0,) * 6)]
        + [float(loc), float(order), float(remaining)]
        + [float(v) for v in (dims_mm or (0.0,) * 3)]
    )
    return "(" + ",".join(f"{v:.6f}" for v in vals) + ")\n"


_SIZE_WHYS = {"too long", "too wide", "too short", "too narrow", "too tall", "too flat", "not a block"}


def scene_status(scene: Scene) -> int:
    """Why a picture had nothing to pick, as the most useful status code."""
    if scene.parts:
        return 1
    whys = [p.why or "" for p in scene.rejected]
    for code, test in (
        (-7, lambda w: w in _SIZE_WHYS or "touching" in w),
        (-1, lambda w: w.startswith("wider than")),
        (-11, lambda w: w.startswith("no room")),
        (-2, lambda w: w.startswith("too close to the base")),
        (-10, lambda w: w.startswith("out of reach")),
        (-12, lambda w: w.startswith("outside the pick area")),
        (-13, lambda w: w.startswith("cut off")),
    ):
        if any(test(w) for w in whys):
            return code
    return 0


def format_reply(
    status: int, centre: Sequence[float] | None = None, pose: Sequence[float] | None = None
) -> str:
    """One ``socket_read_ascii_float`` line: ``(status, cx, cy, cz, x, …, rz)``."""
    vals = (
        [float(status)]
        + [float(v) for v in (centre or (0.0,) * 3)]
        + [float(v) for v in (pose or (0.0,) * 6)]
    )
    return "(" + ",".join(f"{v:.6f}" for v in vals) + ")\n"


def look_pose(
    flange: Sequence[float],
    top: Sequence[float],
    handeye: Sequence[float],
    tcp_offset: Sequence[float],
    *,
    min_m: float = LOOK_MIN_M,
    tip_clear_m: float = LOOK_TIP_CLEAR_M,
    max_tilt_deg: float = LOOK_MAX_TILT_DEG,
    aim_deg: float = LOOK_AIM_DEG,
    stroke_m: float = DEFAULT_STROKE_M,
    finger_axis: str = "y",
) -> list[float] | None:
    """The **TCP-frame** pose for the closer look (see ``LOOK``; ``tcp_offset`` is the
    robot's active TCP, where the fingertips are), or None when none will do.

    The camera goes straight above ``top`` and looks straight down — the approach's
    geometry with the camera in the tool's place — halfway down from its height now
    (never nearer than ``min_m``), turned so ``top`` sits ``aim_deg`` off its optical
    axis on the side away from the gripper (0 = dead centre, the default since
    2026-10-08; the 12° aim of 0.3.0–0.9.1 kept the block out from behind the open
    fingers but, on a slanted line from the picture point, read as "moved up then at
    an angle" on the UR3e). The image X is kept as close as it was (the least wrist
    roll). If the TCP would come within ``tip_clear_m`` of the top's height, the
    camera backs straight up; a tool tilted past ``max_tilt_deg`` from straight down
    is refused."""
    T_fc = Transform.from_pose(handeye)
    T_ft = Transform.from_pose(tcp_offset)
    T_bc = Transform.from_pose(flange).compose(T_fc)
    cam = T_bc.translation
    d0 = cam[2] - top[2]  # height above the top
    if d0 < 1e-6:
        return None
    unit = [0.0, 0.0, 1.0]
    z = [0.0, 0.0, -1.0]  # the optical axis: straight down
    x_cam = T_bc.rotate((1.0, 0.0, 0.0))
    dot = sum(x_cam[i] * z[i] for i in range(3))
    x = [x_cam[i] - dot * z[i] for i in range(3)]
    if math.hypot(*x) < 1e-6:
        return None
    n = math.hypot(*x)
    x = [v / n for v in x]
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    # turn the camera so the ray to the block leaves the axis away from the gripper:
    # R_new · ray = z, with ray = the axis tipped aim_deg about k = (gy, -gx, 0)
    gx, gy = gripper_bearing(handeye, tcp_offset, stroke_m, finger_axis)
    aim = math.radians(aim_deg)
    turn = Transform.from_pose([0.0, 0.0, 0.0, -aim * gy, aim * gx, 0.0])
    start = max(min_m, d0 / 2.0)
    far = max(d0, start + 0.10)
    steps = 20
    for k in range(steps + 1):
        d = start + (far - start) * k / steps
        origin = [top[i] + unit[i] * d for i in range(3)]
        T_bf = Transform.from_axes(x, y, z, origin).compose(turn).compose(T_fc.inverse())
        T_bt = T_bf.compose(T_ft)  # the TCP frame: where the node moves to
        tip = T_bt.translation
        tool_z = T_bt.rotate((0.0, 0.0, 1.0))
        if math.degrees(math.acos(max(-1.0, min(1.0, -tool_z[2])))) > max_tilt_deg:
            return None
        if tip[2] >= top[2] + tip_clear_m:
            return T_bt.to_pose()
    return None


def gripper_bearing(
    handeye: Sequence[float],
    tcp_offset: Sequence[float],
    stroke_m: float = DEFAULT_STROKE_M,
    finger_axis: str = "y",
) -> tuple[float, float]:
    """Where the gripper is in the picture: the unit direction (image x, y) from the optical
    axis toward whichever of the fingertips — the TCP (``tcp_offset``, flange → tool) and
    the two open fingers, half the stroke either side along the TCP frame's ``finger_axis``
    — sits nearest that axis. ``(0, 0)`` when it is on the axis itself or behind the camera
    (no side to prefer)."""
    T_ct = Transform.from_pose(handeye).inverse().compose(Transform.from_pose(tcp_offset))
    half = stroke_m / 2.0
    side = (0.0, half, 0.0) if finger_axis == "y" else (half, 0.0, 0.0)
    best: tuple[float, float, float] | None = None
    for sign in (0.0, 1.0, -1.0):
        px, py, pz = T_ct.apply((sign * side[0], sign * side[1], 0.0))
        if pz <= 1e-6:
            continue
        r = math.hypot(px, py)
        if best is None or r / pz < best[0]:
            best = (r / pz, px, py)
    if best is None or math.hypot(best[1], best[2]) < 1e-6:
        return 0.0, 0.0
    n = math.hypot(best[1], best[2])
    return best[1] / n, best[2] / n


def choose(blocks: list[Block], pixel: tuple[int, int] | None, width: int, height: int) -> Block | None:
    """The block nearest ``pixel`` (the taught tap), else nearest the image centre."""
    if not blocks:
        return None
    u, v = pixel if pixel is not None else (width / 2.0, height / 2.0)
    return min(blocks, key=lambda b: (b.pixel[0] - u) ** 2 + (b.pixel[1] - v) ** 2)


class PickPlanner:
    """Frames in, one answer out. ``frame_source(after_seq)`` returns
    ``(seq, w, h, ch, rgb, depth, depth_scale_m, K)`` for a frame newer than
    ``after_seq`` (or None); ``latest_seq()`` the newest sequence number;
    ``handeye()`` the flange → colour-camera pose (or None)."""

    def __init__(
        self,
        frame_source: Callable[[int], tuple | None],
        latest_seq: Callable[[], int],
        handeye: Callable[[], Sequence[float] | None],
        *,
        stroke_m: float = DEFAULT_STROKE_M,
        min_radius_m: float = 0.2,
        finger_axis: str = "y",
        log: Callable[[str, bool], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.frame_source, self.latest_seq, self.handeye = frame_source, latest_seq, handeye
        self.clock = clock
        self._lock = threading.Lock()
        self._queues: dict[str, dict] = {}  # node id -> {"t", "pointer", "items": [...]}
        self.stroke_m, self.min_radius_m, self.finger_axis = stroke_m, min_radius_m, finger_axis
        self.log = log or (lambda text, ok: None)
        # the program's run (Nick, 2026-10-08: "disable errors while it's not actually in a
        # measurement feedback state"): from its first request or "LOG start" until its "LOG at the
        # grip" / "LOG no pick", or RUN_TTL_S of silence; while it runs the teach screens are told
        # to stay quiet and get the program's own last measurement instead of judging every frame
        self._run_since: float | None = None
        self._run_last: float | None = None
        self.last_measurement: dict | None = None

    # -- the program's run -----------------------------------------------------------------

    def _note_request(self) -> None:
        now = self.clock()
        with self._lock:
            if self._run_since is None:
                self._run_since = now
            self._run_last = now

    def _note_log(self, text: str) -> None:
        low = text.strip().lower()
        with self._lock:
            if low.startswith("start"):
                self._run_since = self._run_last = self.clock()
            elif low.startswith(("at the grip", "no pick")):
                self._run_since = self._run_last = None

    def running(self) -> bool:
        """Is a program talking to this server right now (its run not ended, not silent for
        :data:`RUN_TTL_S`)?"""
        with self._lock:
            if self._run_since is None:
                return False
            if self.clock() - (self._run_last or self._run_since) > RUN_TTL_S:
                self._run_since = self._run_last = None
                return False
            return True

    def quiet(self) -> bool:
        """Should a teach screen stay quiet — no judging of frames, no errors — now?"""
        return self.running()

    def run_state(self) -> dict:
        running = self.running()
        now = self.clock()
        last = self.last_measurement
        return {
            "running": running,
            "since_s": None if not running else round(now - (self._run_since or now), 1),
            "last_request_s": None if self._run_last is None else round(now - self._run_last, 1),
            "last_measurement": None
            if last is None
            else {
                "verb": last.get("verb"),
                "loc": last.get("loc"),
                "age_s": round(now - last.get("t", now), 1),
            },
        }

    def answer(self, line: str) -> str:
        try:
            req = parse_request(line)
        except RequestError as exc:
            self.log(f"pick request refused: {exc}", False)
            # a protocol-2/3 program reads 16 numbers: answer in its shape, or it sees a timeout
            return format_reply2(-9) if re.search(r"\bproto=[23]\b", line) else format_reply(-9)
        if req["verb"] == "LOG":
            self.log(f"robot: {req['text']}", True)
            self._note_log(req["text"])
            return ""  # the program does not read a reply to LOG
        self._note_request()
        proto = req["options"].proto
        if proto < PROTOCOL and req["options"].tcp_offset is None:
            # a node before 0.10.0 zeroed the TCP, never sent it, and expected flange poses for a
            # tool length of the server's: answering it in the TCP frame would drive the flange
            # into the part. (Protocol 1 with a tcp= is the legacy detector in the TCP frame.)
            self.log(f"pick {req['verb']} refused: protocol {proto} node — {STATUS[-14]}", False)
            return format_reply2(-14) if proto == 2 else format_reply(-14)
        if proto >= 2 and req["verb"] != "LOOK":
            return self._answer2(req)
        status, centre, pose = self._look(req) if req["verb"] == "LOOK" else self._plan(req)
        what = STATUS.get(status, "?")
        where = f" top {[round(c, 3) for c in centre]}" if centre else ""
        self.log(f"pick {req['verb']}: {what}{where}", status == 1)
        return format_reply(status, centre, pose)

    def plan(
        self,
        flange: Sequence[float],
        pixel: tuple[int, int] | None = None,
        lean: float = 0.0,
        part: PartSpec | None = None,
        tcp_offset: Sequence[float] | None = None,
    ) -> dict:
        """A FIND for a caller that already has the flange pose (the node's teach-time
        check through the cockpit): ``{status, reason, centre, top_pose}`` — ``top_pose`` a
        pose of the TCP frame ``tcp_offset`` (flange → tool; default the flange itself)."""
        off = list(tcp_offset or ZERO_POSE)
        req = {
            "verb": "FIND",
            "flange": [float(v) for v in flange],
            "tcp_pose": pose_trans([float(v) for v in flange], off),
            "tcp_offset": off,
            "lean": float(lean),
            "part": part,
        }
        if pixel is not None:
            req["pixel"] = pixel
        status, centre, pose = self._plan(req)
        return {"status": status, "reason": STATUS.get(status, "?"), "centre": centre, "top_pose": pose}

    def _look(self, req: dict) -> tuple[int, list[float] | None, list[float] | None]:
        he = self.handeye()
        if not he:
            return -3, None, None
        pose = look_pose(
            req["flange"],
            req["near"],
            he,
            req["tcp_offset"],
            stroke_m=req["options"].stroke_m,
            finger_axis=self.finger_axis,
        )
        return (1, list(req["near"]), pose) if pose else (-6, list(req["near"]), None)

    def _plan(self, req: dict) -> tuple[int, list[float] | None, list[float] | None]:
        he = self.handeye()
        if not he:
            return -3, None, None
        arrived = self.latest_seq()
        frame = self.frame_source(arrived + FRESH_FRAMES - 1)
        if frame is None:
            return -4, None, None
        _, w, h, ch, rgb, depth, scale, K = frame
        flange = req["flange"]
        part = req.get("part")
        rejects: list[dict] = []
        blocks = detect_blocks(
            w,
            h,
            ch,
            rgb,
            depth,
            scale,
            K,
            Transform.from_pose(he),
            Transform.from_pose(flange),
            part=part,
            rejects=rejects,
        )
        if part is not None and rejects:
            seen = ", ".join(f"{r['size_mm'][0]}x{r['size_mm'][1]} mm {r['why']}" for r in rejects[:4])
            self.log(f"pick {req['verb']}: not the part ({part.token()}): {seen}", False)
        if req["verb"] == "REFINE":
            near = req["near"]
            close = [b for b in blocks if math.dist(b.centre_base[:2], near[:2]) < REFINE_RADIUS_M]
            if not close:
                return -5, None, None
            blk = min(close, key=lambda b: math.dist(b.centre_base[:2], near[:2]))
        else:
            blk = choose(blocks, req.get("pixel"), w, h)
            if blk is None:
                return (-7 if part is not None and rejects else 0), None, None
        if blk.minor_m > self.stroke_m - 0.006:
            return -1, blk.centre_base, None
        if self.min_radius_m and math.hypot(blk.centre_base[0], blk.centre_base[1]) < self.min_radius_m:
            return -2, blk.centre_base, None
        rot = grasp_rotation(req["tcp_pose"], blk.centre_base, req["lean"])
        yaw = grasp_yaw_deg(rot, blk.theta + math.pi / 2, self.finger_axis)
        return 1, list(blk.centre_base), tip_pose(blk.centre_base, rot, 0.0, yaw)

    # -- protocol 2 ----------------------------------------------------------------------

    def _answer2(self, req: dict) -> str:
        opts: PickOptions = req["options"]
        verb = req["verb"]
        if verb == "NEXT":
            got = self._next(opts)
        elif verb == "FIND":
            got = self._find2(req, opts)
        else:
            got = self._refine2(req, opts)
        status = got["status"]
        what = "nothing queued" if verb == "NEXT" and status == 0 else STATUS.get(status, "?")
        at = got.get("loc", 0)
        where = f" #{got.get('order', 0)} at {at}" if status == 1 else f" (next: {at})"
        self.log(f"pick {verb} [{opts.node or '-'}]: {what}{where}", status in (0, 1))
        return format_reply2(
            status,
            got.get("centre"),
            got.get("pose"),
            loc=got.get("loc", 0),
            order=got.get("order", 0),
            remaining=got.get("remaining", 0),
            dims_mm=got.get("dims_mm"),
        )

    def _queue(self, node: str) -> dict:
        q = self._queues.get(node)
        if q is None:
            q = self._queues[node] = {"t": self.clock(), "pointer": 1, "items": []}
        return q

    def _next(self, opts: PickOptions) -> dict:
        """The next part already seen (no picture needed), else where to look next."""
        with self._lock:
            q = self._queue(opts.node)
            if q["items"] and self.clock() - q["t"] <= QUEUE_TTL_S:
                item = q["items"].pop(0)
                return {**item, "status": 1, "remaining": len(q["items"])}
            q["items"] = []
            if not 1 <= q["pointer"] <= opts.locs:
                q["pointer"] = 1
            return {"status": 0, "loc": q["pointer"]}

    def scene(self, flange: Sequence[float] | None, opts: PickOptions, after: int | None = None):
        """``(status, scene, frame)`` for a picture newer than ``after`` (default: the
        request's arrival) seen from ``flange`` (None: camera-only)."""
        he = self.handeye()
        if flange is not None and not he:
            return -3, None, None
        arrived = self.latest_seq() if after is None else after
        frame = self.frame_source(arrived + FRESH_FRAMES - 1)
        if frame is None:
            return -4, None, None
        _, w, h, ch, rgb, depth, scale, K = frame
        T_bc = None if flange is None else Transform.from_pose(flange).compose(Transform.from_pose(he))
        scene = find_parts(
            w,
            h,
            depth,
            scale,
            K,
            T_bc,
            colour=rgb,
            colour_channels=ch,
            spec=opts.part,
            surface=opts.surface,
            reach=keep_out(opts),
            order=opts.order,
            fingers=opts.fingers() if T_bc is not None and opts.grip_check else None,
        )
        for p in list(scene.parts):
            why = None
            if opts.grip_check and opts.room_m is None and p.width_m > opts.stroke_m - 0.006:
                why = f"wider than the open gripper ({p.width_m * 1000:.0f} mm)"
            elif flange is not None and not self.reachable(p, flange, opts):
                why = "out of reach (no joint solution)"
            if why is not None:
                p.why = why
                scene.parts.remove(p)
                scene.rejected.append(p)
        for n, p in enumerate(scene.parts, 1):
            p.order = n
        return 1, scene, frame

    def report(self, scene: Scene, frame: tuple, flange: Sequence[float] | None, opts: PickOptions) -> dict:
        """``scene`` as a teach screen draws it (:func:`scene_report`'s body): every part with its
        outline in picture pixels, its pick-order number and its grasp (a pose of the TCP frame
        ``opts.tcp_offset``), every rejected candidate with why, the surface used."""
        seq, w, h = frame[0], frame[1], frame[2]
        out = scene.as_dict()
        if flange is not None:
            # the grasp for each part (the TCP on its top centre): the teach screen's "Check
            # approach" backs it off along the tool axis for PolyScope's move screen
            tcp_now = pose_trans(flange, list(opts.tcp_offset or ZERO_POSE))
            for d, p in zip(out["parts"], scene.parts, strict=True):
                d["grasp_pose"] = [round(v, 6) for v in self._grasp(p, tcp_now, 0.0, opts)]
        out.update(
            ok=True,
            seq=seq,
            width=w,
            height=h,
            base_frame=flange is not None,
            status=scene_status(scene),
            reason=STATUS.get(scene_status(scene), "?"),
            part=None if opts.part is None else opts.part.as_dict(),
            order=list(opts.order),
        )
        if flange is None:
            out["notes"].append("no live robot pose: reach and the pick area are not checked")
        return out

    def reachable(self, part, flange: Sequence[float], opts: PickOptions) -> bool:
        """Does ``opts.arm`` have a joint solution for the approach and the grip on ``part`` —
        straight down, or at one of the leans the program tries next? True when the arm is
        not named or not in the table: the controller's own IK decides in the program. The
        kinematics answer for the flange: the TCP-frame poses go back through ``tcp_offset``."""
        from .armik import has_solution

        if not opts.arm:
            return True
        offset = list(opts.tcp_offset or ZERO_POSE)
        back = pose_inv(offset)
        tcp_now = pose_trans(flange, offset)
        for lean in LEANS_DEG:
            top = self._grasp(part, tcp_now, lean, opts)
            hover = pose_trans(pose_trans(top, [0.0, 0.0, -opts.approach_m, 0.0, 0.0, 0.0]), back)
            grip = pose_trans(pose_trans(top, [0.0, 0.0, opts.grip_below_m, 0.0, 0.0, 0.0]), back)
            answers = [has_solution(hover, opts.arm), has_solution(grip, opts.arm)]
            if None in answers or all(answers):
                return True
        return False

    def _grasp(
        self, part, tcp_pose: Sequence[float], lean: float, opts: PickOptions | None = None
    ) -> list[float]:
        """The grasp as a pose of the TCP frame: its origin on the part's top centre, its Z
        straight down (or leaned), its heading kept from ``tcp_pose`` and turned so the
        fingers (the frame's Y) close across the side asked for."""
        rot = grasp_rotation(tcp_pose, part.centre_base, lean)
        if opts is not None and opts.part is not None and opts.part.is_round:
            return tip_pose(part.centre_base, rot, 0.0, 0.0)  # no long side: the wrist stays
        long_way = opts is not None and opts.across == "long"
        # the fingers travel across the short side (perpendicular to the long one) — or along it
        heading = part.theta if long_way else part.theta + math.pi / 2
        yaw = grasp_yaw_deg(rot, heading, self.finger_axis)
        return tip_pose(part.centre_base, rot, 0.0, yaw)

    def _item(
        self, part, tcp_pose: Sequence[float], lean: float, loc: int, opts: PickOptions | None = None
    ) -> dict:
        return {
            "centre": list(part.centre_base),
            "pose": self._grasp(part, tcp_pose, lean, opts),
            "loc": loc,
            "order": part.order,
            "dims_mm": [round(v * 1000, 1) for v in (part.length_m, part.width_m, part.height_m)],
        }

    def _remember(
        self, verb: str, loc: int, scene, frame, flange: Sequence[float], opts: PickOptions
    ) -> None:
        """Keep what the program just measured: the teach screens show it while the program runs."""
        got = self.report(scene, frame, flange, opts)
        got.update(verb=verb, loc=loc, t=self.clock())
        with self._lock:
            self.last_measurement = got

    def _find2(self, req: dict, opts: PickOptions) -> dict:
        loc = opts.loc or 1
        ok, scene, frame = self.scene(req["flange"], opts)
        if ok != 1:
            return {"status": ok, "loc": loc}
        self._remember("FIND", loc, scene, frame, req["flange"], opts)
        for note in scene.notes:
            self.log(f"pick FIND at {loc}: {note}", False)
        for p in scene.rejected[:6]:
            self.log(
                f"pick FIND at {loc}: not picking {p.length_m * 1000:.0f}x{p.width_m * 1000:.0f}x"
                f"{p.height_m * 1000:.0f} mm at {[round(c, 3) for c in p.centre]}: {p.why}",
                False,
            )
        items = [self._item(p, req["tcp_pose"], req["lean"], loc, opts) for p in scene.parts]
        with self._lock:
            q = self._queue(opts.node or "-")
            q["t"] = self.clock()
            if not items:
                q["items"] = []
                q["pointer"] = loc % max(1, opts.locs) + 1  # this location is empty: the next one
                return {"status": scene_status(scene), "loc": q["pointer"]}
            q["pointer"] = loc  # when the queue drains, look here again: picks may uncover more
            q["items"] = items[1:]
            return {**items[0], "status": 1, "remaining": len(items) - 1}

    def _refine2(self, req: dict, opts: PickOptions) -> dict:
        ok, scene, frame = self.scene(req["flange"], opts)
        if ok != 1:
            return {"status": ok, "loc": opts.loc}
        self._remember("REFINE", opts.loc, scene, frame, req["flange"], opts)
        near = req["near"]
        # the close look sees the part from nearer: its neighbours may now be cut off or out of
        # the area, but the part itself is judged only by its size
        edge = [p for p in scene.rejected if (p.why or "").startswith(("cut off", "no room"))]
        pool = list(scene.parts) + edge
        close = [p for p in pool if math.dist(p.centre[:2], near[:2]) < REFINE_RADIUS_M]
        if not close:
            with self._lock:
                self._queue(opts.node or "-")["items"] = []  # what was queued was seen before this change
            return {"status": -5, "loc": opts.loc}
        part = min(close, key=lambda p: math.dist(p.centre[:2], near[:2]))
        if part.why and part.why.startswith("no room"):
            return {"status": -11, "loc": opts.loc, "centre": list(part.centre)}
        item = self._item(part, req["tcp_pose"], req["lean"], opts.loc, opts)
        with self._lock:
            remaining = len(self._queue(opts.node or "-")["items"])
        return {**item, "status": 1, "order": 0, "remaining": remaining}


# -- the node's teach screen (the cockpit's routes and the stand-alone pick server's) ---------


def parse_preview_request(payload: dict) -> tuple[tuple[int, int] | None, float, float]:
    """``POST /api/pick/preview``'s body -> ``(pixel, grip_below_mm, hover_mm)``;
    ValueError when a field isn't a number or is out of range. The body's ``part`` /
    ``tol`` are :func:`perceptronics.partspec.from_payload`'s."""
    try:
        u, v = int(payload.get("u", -1)), int(payload.get("v", -1))
        grip = float(payload.get("grip_below_mm", 15.0))
        hover = float(payload.get("hover_mm", 40.0))
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(str(exc)) from None
    if not (0.0 <= grip <= 60.0 and 0.0 <= hover <= 300.0):
        raise ValueError("grip_below_mm must be 0..60 and hover_mm 0..300")
    return ((u, v) if u >= 0 and v >= 0 else None), grip, hover


def preview(
    planner: PickPlanner,
    flange_pose: dict,
    pixel: tuple[int, int] | None,
    *,
    grip_below_mm: float = 15.0,
    hover_mm: float = 40.0,
    part: PartSpec | None = None,
) -> dict:
    """The node's teach-time check: what the program would do from where the arm is
    now. ``flange_pose`` is a ``get_flange_pose`` result (``flange``, ``tcp_offset``,
    ``tcp_offset_consistent``); one FIND, and the hover and grip poses in the controller's
    **active** TCP frame — the ``polyscope_*`` names (what PolyScope's hold-to-move screen
    takes) are the same poses, kept for the 0.9.x screens. Moves nothing."""
    fp = flange_pose
    if not fp.get("ok") or not fp.get("flange"):
        return {"ok": False, "error": fp.get("error") or "could not read the flange pose", "robot": fp}
    offset = fp.get("tcp_offset")
    if offset is not None and fp.get("tcp_offset_consistent") is False:
        offset = None
    planned = planner.plan(fp["flange"], pixel, part=part, tcp_offset=offset)
    out: dict = {"ok": planned["status"] == 1, **planned, "flange_pose": fp["flange"]}
    out["tcp_offset"] = list(offset) if offset is not None else None
    if planned["status"] != 1:
        out["error"] = planned["reason"]
        return out
    top = planned["top_pose"]
    out["hover_pose"] = pose_trans(top, [0.0, 0.0, -hover_mm / 1000.0, 0.0, 0.0, 0.0])
    out["grip_pose"] = pose_trans(top, [0.0, 0.0, grip_below_mm / 1000.0, 0.0, 0.0, 0.0])
    if offset is not None:
        out["polyscope_hover_pose"] = list(out["hover_pose"])
        out["polyscope_grip_pose"] = list(out["grip_pose"])
    else:
        out["polyscope_note"] = (
            "the controller's active TCP offset is unknown or inconsistent: "
            "these poses take the TCP at the flange"
        )
    return out


def detect_report(
    frame: tuple,
    *,
    pick_port: int | None,
    handeye: bool,
    part: PartSpec | None = None,
) -> dict:
    """What the node's teach screen draws: the blocks the pick server would choose
    among, in image pixels, from one ``(seq, w, h, ch, rgb, depth, scale, K)`` frame
    (camera frame — no robot needed) — and, as ``rejected``, the candidates that were
    the wrong size (for ``part`` when given) with why, so the operator can see what
    the filter is doing."""
    seq, w, h, ch, rgb, depth, scale, K = frame
    rejects: list[dict] = []
    blocks = detect_blocks(
        w, h, ch, rgb, depth, scale, K, Transform(), Transform(), part=part, rejects=rejects
    )
    return {
        "ok": True,
        "seq": seq,
        "width": w,
        "height": h,
        "pick_port": pick_port,
        "handeye": handeye,
        "part": None if part is None else part.as_dict(),
        "blocks": [
            {
                "pixel": list(b.pixel),
                "size_mm": [round(b.major_m * 1000), round(b.minor_m * 1000)],
                "height_mm": None if b.height_m is None else round(b.height_m * 1000),
                "distance_m": round(b.centre_base[2], 3),
            }
            for b in blocks
        ],
        "rejected": rejects,
    }


def scene_report(
    planner: PickPlanner,
    flange: Sequence[float] | None,
    opts: PickOptions,
    *,
    pick_port: int | None = None,
) -> dict:
    """What the 0.5.0 node's teach screen draws, computed exactly as the program's FIND
    would from ``flange`` (the live pose; None: camera-only, no reach or pick area):
    every part with its outline in picture pixels and its pick-order number, every
    candidate that isn't picked with why, the surface used; each part's ``grasp_pose`` is
    a pose of the TCP frame ``opts.tcp_offset`` (the flange when none). Moves nothing."""
    if planner.quiet():
        # Nick, 2026-10-08: as the arm comes down to the part the camera is inside its own
        # minimum range and every frame would be judged wrong — the program is told nothing
        # between its own FIND / REFINE, and neither is the operator
        last = planner.last_measurement
        return {
            "ok": False,
            "quiet": True,
            "running": True,
            "status": 0,
            "error": QUIET_REASON,
            "reason": QUIET_REASON,
            "pick_port": pick_port,
            "run": planner.run_state(),
            "last": None if last is None else {**last, "pick_port": pick_port},
        }
    ok, scene, frame = planner.scene(flange, opts, after=max(0, planner.latest_seq() - FRESH_FRAMES))
    if ok != 1:
        return {"ok": False, "status": ok, "error": STATUS.get(ok, "?")}
    out = planner.report(scene, frame, flange, opts)
    out["pick_port"] = pick_port
    return out


class _Handler(socketserver.StreamRequestHandler):
    timeout = 30.0  # a controller that connects and goes quiet does not hold a thread

    def handle(self) -> None:
        planner: PickPlanner = self.server.planner  # type: ignore[attr-defined]
        while True:
            try:
                raw = self.rfile.readline(MAX_LINE + 1)
            except OSError:
                return
            if not raw:
                return
            if len(raw) > MAX_LINE:
                self.wfile.write(format_reply(-9).encode())
                return  # a line that long is not a controller; drop the connection
            try:
                line = raw.decode("ascii")
            except UnicodeDecodeError:
                if raw.lstrip()[:3].upper() == b"LOG":  # never answered, whatever it holds
                    planner.answer(raw.decode("ascii", errors="replace"))
                    continue
                self.wfile.write(format_reply(-9).encode())
                continue
            answer = planner.answer(line)
            if answer:
                self.wfile.write(answer.encode())


class PickServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, bind: str, port: int, planner: PickPlanner):
        super().__init__((bind, port), _Handler)
        self.planner = planner
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self.serve_forever, name="pick-server", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
