"""Where the camera sits on the robot, and how a camera-frame point becomes a
base-frame target the robot can move to.

Frames (all right-handed):

* **colour camera** — what :meth:`perceptronics.rgbd.RgbdFrame.point_at` and the
  segment features (``point_m``) are expressed in: x right, y down, z out of
  the lens (aligned depth lives on the colour grid, so the colour optical
  centre is the origin).
* **depth camera** — the left imager. The SDK's extrinsics (``p_color = R
  p_depth + t``, read at open, see ``RealSenseCamera.extrinsics_depth_to_color``)
  relate the two; on a D435 that is ~15 mm along x.
* **flange** — UR's tool-flange frame (origin at the flange face centre, +Z
  out of the flange). The bracket's nominal placement of the depth origin in
  this frame is :data:`BRACKET_NOMINAL`.
* **base** — UR's base frame, what ``get_actual_tcp_pose()`` / ``movel`` use.
  The flange pose in the base comes from the controller
  (``Robot.get_flange_pose``).

``p_base = T_base_flange · T_flange_depth · T_depth_color · p_color``.

:data:`BRACKET_SEEDS` are *seeds*, one per print (``eseries`` / ``ur20`` /
``uf850``, picked by ``PERCEPTRONICS_BRACKET``): derived from the bracket geometry
(``hardware/d435-tool-bracket/README.md`` §3) and the camera's published
imager position, not from a calibration. Expect a few mm
and ~1° of error from a printed part; a hand-eye calibration replaces it via
``PERCEPTRONICS_T_FLANGE_CAMERA`` (a UR pose ``[x, y, z, rx, ry, rz]`` of the depth
frame in the flange frame, metres + rotation vector) or :meth:`HandEye.from_pose`.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from urctl.pose import Transform, Vec3, pose_inv, pose_trans

# Bracket README §3 (Rev C), one seed per print (``hardware/d435-tool-bracket/
# bracket.py`` VARIANTS; the numbers are ``out/build_info.json`` →
# ``export.variants.<variant>.derived`` and the unit tests hold them to it).
#
# ``eseries`` (UR3e/UR5e/UR10e/UR16e, ISO-50 flange), ARM_ANGLE_DEG = 90 — the
# camera hangs beside the wrist on +Y (the tool-I/O connector side) on a seat
# drafted 5° (CAM_TILT_DEG), so the optical axis tips 5° in toward the flange
# axis: camera axes in flange axes are x_cam = −X, y_cam = (0, −cos 5°, −sin 5°)
# (image-down points at the mounting wall), z_cam = (0, −sin 5°, cos 5°); depth
# origin (left imager) at (17.5, 63.9, 0.6) mm — wall r = 48…51 beside the Ø90
# wrist, the camera leaning about its outer front edge on the tool face (z = 6),
# zero-depth plane 4.3 mm behind the front plate (Intel's URDF: 4.2 glass + 0.1).
_TILT = math.radians(5.0)
_CT, _ST = math.cos(_TILT), math.sin(_TILT)
BRACKET_NOMINAL_ESERIES = Transform.from_axes(
    (-1.0, 0.0, 0.0), (0.0, -_CT, -_ST), (0.0, -_ST, _CT), (0.0175, 0.063922336, 0.000626916)
)
# ``ur20`` (UR20/UR30, ISO-50 + ISO-80 on a Ø96 plate): the wall is clocked to
# 30° (UR20_ARM_ANGLE_DEG, 60° off the M8 socket — Rev C's seat is 95 wide) and
# sits 5 mm further out (wall r = 53…56), so the camera axes are the e-Series
# ones rotated −60° about Z and the depth origin lands at (68.4, 19.3, 0.6) mm.
_C30, _S30 = math.sqrt(3.0) / 2.0, 0.5
BRACKET_NOMINAL_UR20 = Transform.from_axes(
    (-_S30, _C30, 0.0),
    (-_CT * _C30, -_CT * _S30, -_ST),
    (-_ST * _C30, -_ST * _S30, _CT),
    (0.068438494, 0.019305723, 0.000626916),
)
# ``uf850`` (UFACTORY 850, ISO-50 + two more M6): the wall clocked to 3 o'clock
# (UF850_ARM_ANGLE_DEG = 0, clear of the connector block) and pulled in to the Ø84
# housing (wall r = 45…48). UFACTORY's flange frame has the dowel at −Y where the
# bracket's has it at +Y, so these are the bracket's numbers turned 180° about Z
# (``derived()["depth_origin_robot_flange_mm"]``): depth origin (−60.9, 17.5, 0.6) mm,
# x_cam = −Y, y_cam = (cos 5°, 0, −sin 5°), z_cam = (sin 5°, 0, cos 5°).
BRACKET_NOMINAL_UF850 = Transform.from_axes(
    (0.0, -1.0, 0.0), (_CT, 0.0, -_ST), (_ST, 0.0, _CT), (-0.060922336, 0.0175, 0.000626916)
)
BRACKET_SEEDS: dict[str, Transform] = {
    "eseries": BRACKET_NOMINAL_ESERIES,
    "ur20": BRACKET_NOMINAL_UR20,
    "uf850": BRACKET_NOMINAL_UF850,
}
DEFAULT_BRACKET = "eseries"
# Kept for callers that predate the second print.
BRACKET_NOMINAL = BRACKET_NOMINAL_ESERIES
ENV_BRACKET = "PERCEPTRONICS_BRACKET"
# A saved touch-and-click calibration (perceptronics.calibrate). Env wins over it.
ENV_HANDEYE_FILE = "PERCEPTRONICS_HANDEYE_FILE"
DEFAULT_HANDEYE_DIR = "captures/calibration"


def default_handeye_path(env: Mapping[str, str] | None = None) -> str:
    """``$PERCEPTRONICS_HANDEYE_FILE`` or ``captures/calibration/handeye_<cell>.json``
    (``handeye.json`` when no cell is selected)."""
    env = os.environ if env is None else env
    explicit = env.get(ENV_HANDEYE_FILE, "").strip()
    if explicit:
        return explicit
    cell = env.get("UR_CELL", "").strip()
    return os.path.join(DEFAULT_HANDEYE_DIR, f"handeye_{cell}.json" if cell else "handeye.json")


ENV_T_FLANGE_CAMERA = "PERCEPTRONICS_T_FLANGE_CAMERA"


def seed_calibration_file(path: str | os.PathLike, pose: Sequence[float], *, source: str) -> bool:
    """Write ``pose`` as the saved hand-eye at ``path`` — the file
    :meth:`HandEye.from_env` reads and a calibration's Apply overwrites — unless one is
    already there (a calibration made on this machine is newer than any profile). Returns
    whether it wrote. A pick PC keeps its hand-eye here, not in the environment: an
    environment value would win over every later calibration (``deploy/pi/install.sh``)."""
    vals = [float(v) for v in pose]
    if len(vals) != 6 or not all(math.isfinite(v) for v in vals):
        raise ValueError("a hand-eye pose is 6 finite numbers [x, y, z, rx, ry, rz]")
    target = os.fspath(path)
    if os.path.exists(target):
        return False
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    body = {"flange_to_depth_pose": vals, "source": source}
    tmp = f"{target}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=2)
    os.replace(tmp, target)
    return True


DEFAULT_STANDOFF_M = 0.10
# What the standoff is measured from:
#   "tcp" (the default, and the only one a cell gets) — the controller's **active
#       TCP**: the tool as the operator set it on the pendant. The camera computer
#       owns no tool length of its own (Nick, 2026-10-08: "You must only use tool
#       offsets inside of the robot not your own"); until then a cell carried
#       PERCEPTRONICS_TIP_M and every move forced the TCP to those fingertips.
#   "flange" — the tool flange, along the camera ray: what the hand-eye
#       calibration and the flange-referenced tools ask for explicitly.
APPROACH_REFERENCES = ("tcp", "flange")
DEFAULT_APPROACH_REFERENCE = "tcp"
ENV_STANDOFF_M = "PERCEPTRONICS_STANDOFF_M"
# Retired 2026-10-08 with the tool offset moving to the robot: still-set values are
# ignored, and `perceptronics doctor` / the cell loader say so.
RETIRED_VARIABLES = ("PERCEPTRONICS_TIP_M", "PERCEPTRONICS_APPROACH_REFERENCE")


VIEW_HEIGHT_M = 0.40  # the camera over the work surface for a picture: the middle of the D435's good zone
VIEW_MIN_OUT_M = 0.05  # past the base's keep-out radius when a point has to be pushed out


def view_pose(
    handeye: HandEye | Sequence[float],
    flange_now: Sequence[float],
    point_base: Sequence[float],
    *,
    height_m: float = VIEW_HEIGHT_M,
    keep_out_m: float | None = None,
) -> dict:
    """The straight-down picture pose (Nick, 2026-10-08: the 3D Pick view "looking straight
    down and slightly outreached"): the **flange** pose that puts the colour camera
    ``height_m`` straight above ``point_base`` looking straight down (its optical axis along
    base −Z), the picture's X kept as near as it is now (the least wrist roll). A point
    nearer the base axis than ``keep_out_m`` (the arm's base radius + its margin) is pushed
    out along its bearing to ``keep_out_m + VIEW_MIN_OUT_M`` — the view is of the table in
    front of the robot, not of its own base. Returns ``{flange_target_pose, point_m
    (as used), height_m, pushed_out_m}``; ValueError when the camera's X cannot be kept
    (it looks along ±Z now and the roll is free: the base X is taken)."""
    T_fc = handeye.flange_to_color if isinstance(handeye, HandEye) else Transform.from_pose(handeye)
    p = [float(v) for v in point_base]
    if len(p) != 3 or not all(math.isfinite(v) for v in p):
        raise ValueError("point_base must be 3 finite numbers")
    if not (math.isfinite(height_m) and 0.2 <= height_m <= 2.0):
        raise ValueError("height_m must be within 0.2..2 m")
    pushed = 0.0
    if keep_out_m is not None and keep_out_m > 0:
        r = math.hypot(p[0], p[1])
        want = keep_out_m + VIEW_MIN_OUT_M
        if r < want:
            if r < 1e-6:
                bearing = Transform.from_pose(flange_now).translation
                r0 = math.hypot(bearing[0], bearing[1])
                ux, uy = (bearing[0] / r0, bearing[1] / r0) if r0 > 1e-6 else (1.0, 0.0)
            else:
                ux, uy = p[0] / r, p[1] / r
            pushed = want - r
            p = [ux * want, uy * want, p[2]]
    T_bc_now = Transform.from_pose(flange_now).compose(T_fc)
    z = [0.0, 0.0, -1.0]
    x_cam = T_bc_now.rotate((1.0, 0.0, 0.0))
    x = [x_cam[0], x_cam[1], 0.0]
    n = math.hypot(*x)
    if n < 1e-6:
        x = [1.0, 0.0, 0.0]
        n = 1.0
    x = [v / n for v in x]
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    origin = [p[0], p[1], p[2] + height_m]
    T_bf = Transform.from_axes(x, y, z, origin).compose(T_fc.inverse())
    return {
        "flange_target_pose": T_bf.to_pose(),
        "point_m": p,
        "height_m": float(height_m),
        "pushed_out_m": round(pushed, 4),
    }


def transform_from_extrinsics(ext: Mapping | None) -> Transform:
    """The SDK's ``{rotation: 3x3 row-major, translation: [3]}`` → :class:`Transform`
    (``p_color = R p_depth + t``). ``None`` → identity."""
    if not ext:
        return Transform()
    rot = ext["rotation"]
    rotation = tuple(tuple(float(v) for v in row) for row in rot)
    t = ext["translation"]
    return Transform(rotation, (float(t[0]), float(t[1]), float(t[2])))  # type: ignore[arg-type]


def parse_pose_text(text: str) -> list[float]:
    """``"[x, y, z, rx, ry, rz]"``, ``"x,y,z,rx,ry,rz"`` or ``{"pose": [...]}`` → 6 floats."""
    text = text.strip()
    if not text:
        raise ValueError("empty pose")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = [p for p in text.replace(";", ",").split(",")]
    if isinstance(obj, Mapping):
        obj = obj.get("pose")
    if not isinstance(obj, Sequence) or len(obj) != 6:
        raise ValueError(f"expected 6 numbers [x, y, z, rx, ry, rz], got {text!r}")
    vals = [float(v) for v in obj]
    if not all(math.isfinite(v) for v in vals):
        raise ValueError("pose values must be finite")
    return vals


@dataclass(frozen=True)
class HandEye:
    """``flange_to_depth`` (the calibration, or the bracket seed) and
    ``depth_to_color`` (the SDK extrinsics) — everything needed to move a
    colour-frame point into the flange frame."""

    flange_to_depth: Transform = BRACKET_NOMINAL_ESERIES
    depth_to_color: Transform = Transform()
    source: str = "bracket-nominal:eseries"

    @classmethod
    def from_pose(cls, pose: Sequence[float], *, source: str = "explicit") -> HandEye:
        return cls(Transform.from_pose(pose), Transform(), source)

    @classmethod
    def for_bracket(cls, variant: str = DEFAULT_BRACKET) -> HandEye:
        """The nominal seed for one of the two prints (``eseries`` / ``ur20``)."""
        key = (variant or DEFAULT_BRACKET).strip().lower()
        if key not in BRACKET_SEEDS:
            raise ValueError(f"unknown bracket variant {variant!r}; one of {sorted(BRACKET_SEEDS)}")
        return cls(BRACKET_SEEDS[key], Transform(), f"bracket-nominal:{key}")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> HandEye:
        """:data:`ENV_T_FLANGE_CAMERA` if set, else a saved calibration file
        (:func:`default_handeye_path`), else the seed for the bracket print
        named by :data:`ENV_BRACKET` (default ``eseries``)."""
        env = os.environ if env is None else env
        raw = env.get(ENV_T_FLANGE_CAMERA, "")
        if raw.strip():
            return cls.from_pose(parse_pose_text(raw), source=f"env:{ENV_T_FLANGE_CAMERA}")
        path = default_handeye_path(env)
        if os.path.isfile(path):
            from .calibrate import load_calibration_pose

            return cls.from_pose(load_calibration_pose(path), source=f"file:{path}")
        return cls.for_bracket(env.get(ENV_BRACKET, DEFAULT_BRACKET))

    @property
    def calibrated(self) -> bool:
        """False while the seed is the printed-bracket nominal (mm + ~1° of error)."""
        return not self.source.startswith("bracket-nominal")

    def with_extrinsics(self, ext: Mapping | None) -> HandEye:
        """Attach the camera's depth→colour extrinsics (from ``describe()``)."""
        return replace(self, depth_to_color=transform_from_extrinsics(ext))

    @property
    def flange_to_color(self) -> Transform:
        # depth_to_color maps depth→colour; we need colour→depth, then depth→flange.
        return self.flange_to_depth.compose(self.depth_to_color.inverse())

    def camera_to_flange(self, point_cam: Sequence[float]) -> Vec3:
        return self.flange_to_color.apply(point_cam)

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "calibrated": self.calibrated,
            "flange_to_depth_pose": self.flange_to_depth.to_pose(),
            "depth_to_color_translation": list(self.depth_to_color.translation),
            "flange_to_color_pose": self.flange_to_color.to_pose(),
        }


def _check_point(point: Sequence[float], name: str) -> tuple[float, float, float]:
    if len(point) != 3:
        raise ValueError(f"{name} must be [x, y, z], got {len(point)} values")
    vals = tuple(float(v) for v in point)
    if not all(math.isfinite(v) for v in vals):
        raise ValueError(f"{name} must be finite")
    return vals  # type: ignore[return-value]


def locate(
    handeye: HandEye,
    flange_pose: Sequence[float],
    point_cam: Sequence[float],
    *,
    tcp_pose: Sequence[float],
    standoff_m: float = DEFAULT_STANDOFF_M,
    max_reach_m: float | None = None,
    reference: str = DEFAULT_APPROACH_REFERENCE,
    tcp_offset: Sequence[float] | None = None,
) -> dict:
    """Turn a colour-camera point into base coordinates and an **approach pose**
    for the tool: the TCP placed ``standoff_m`` short of the point along the
    camera's viewing ray, keeping the tool's current orientation.

    ``flange_pose``/``tcp_pose`` are the live UR poses (base frame). The
    approach keeps the current rotation vector, so the tool comes in the way
    it was already pointing — with the camera looking along the flange +Z
    axis that is straight down the tool axis. Returns every intermediate
    frame so the cockpit can show its work before anything moves.

    ``reference`` picks what sits ``standoff_m`` short of the point:

    * ``"tcp"`` (the default) — the controller's active TCP — the tool as the
      pendant has it — along the camera ray; ``approach_pose`` is a pose of that
      TCP and the move runs with it as it is.
    * ``"flange"`` — the flange, along the camera ray; needs ``tcp_offset`` (the
      live active-TCP offset) to express it as the active-TCP pose.

    The move always keeps the tool's current orientation, so ``flange_target_pose``
    is reported whenever it can be computed.

    ``max_reach_m`` (the arm's datasheet reach — ``SafetyEnvelope.max_reach``)
    adds ``reachable`` / ``approach_distance_m`` so the verdict is on screen
    *before* Move: an approach beyond the arm's reach is a move the envelope
    will refuse, and a point beyond it can't be picked from this base at all.
    """
    p_cam = _check_point(point_cam, "point_cam")
    if not math.isfinite(standoff_m) or standoff_m < 0.0 or standoff_m > 1.0:
        raise ValueError("standoff_m must be within 0..1 m")
    base_from_flange = Transform.from_pose(flange_pose)
    tcp = [float(v) for v in tcp_pose]
    if len(tcp) != 6:
        raise ValueError("tcp_pose must have 6 elements")
    if reference not in APPROACH_REFERENCES:
        raise ValueError(f"reference must be one of {APPROACH_REFERENCES}, not {reference!r}")
    offset = None
    if tcp_offset is not None:
        offset = [float(v) for v in tcp_offset]
        if len(offset) != 6 or not all(math.isfinite(v) for v in offset):
            raise ValueError("tcp_offset must be 6 finite numbers")
    if reference == "flange" and offset is None:
        raise ValueError("reference='flange' needs the active tcp_offset")
    p_flange = handeye.camera_to_flange(p_cam)
    p_base = base_from_flange.apply(p_flange)
    ray_base = base_from_flange.rotate(handeye.flange_to_color.rotate((0.0, 0.0, 1.0)))
    short = tuple(p - standoff_m * r for p, r in zip(p_base, ray_base, strict=True))
    flange_now = [float(v) for v in flange_pose]
    if reference == "flange":
        flange_target = [*short, *flange_now[3:]]
        target = pose_trans(flange_target, offset)  # the TCP pose that puts the flange there
    else:
        target = [*short, *tcp[3:]]
        flange_target = pose_trans(target, pose_inv(offset)) if offset is not None else None
    approach = tuple(target[:3])
    approach_dist = math.sqrt(sum(v * v for v in approach))
    point_dist = math.sqrt(sum(v * v for v in p_base))
    # Reach is judged on the flange when the move overrides the TCP (flange): the
    # datasheet radius is to the flange, and the active TCP pose is a virtual point
    # that can sit nearer the base than the flange does.
    commanded = flange_target if reference == "flange" else target
    commanded_dist = math.sqrt(sum(v * v for v in commanded[:3]))
    reachable = None if max_reach_m is None else bool(commanded_dist <= max_reach_m)
    return {
        "approach_distance_m": approach_dist,
        "commanded_distance_m": commanded_dist,
        "point_distance_m": point_dist,
        "max_reach_m": None if max_reach_m is None else float(max_reach_m),
        "reachable": reachable,
        "reference": reference,
        "flange_target_pose": flange_target,
        "tcp_offset": offset,
        "point_cam_m": list(p_cam),
        "point_flange_m": list(p_flange),
        "point_base_m": list(p_base),
        "view_ray_base": list(ray_base),
        "standoff_m": float(standoff_m),
        "approach_pose": target,
        "flange_pose": [float(v) for v in flange_pose],
        "tcp_pose": tcp,
        "handeye": handeye.as_dict(),
    }
