"""The controller's binary state broadcast, decoded — the flange pose without a script.

Every UR controller streams a *robot state* message ~10 times a second to anyone
connected to the Primary (30001) or Secondary (30002) client port. It is sent
whatever the control mode: unlike a URScript ``textmsg`` query, which a real
e-Series in **Local** mode silently ignores (UR3e, PolyScope 5.25.1, 2026-09-27),
reading it needs no program, so it also never replaces a running one.

Three sub-packages of that message are enough to place the flange exactly:

* ``JOINT_DATA`` (type 1) — the six actual joint angles;
* ``KINEMATICS_INFO`` (type 5) — the robot's **calibrated** DH parameters (the
  deltas the factory calibration measured, not the datasheet's);
* ``CARTESIAN_INFO`` (type 4) — the TCP pose and the active TCP offset.

The flange comes from forward kinematics of the joints through the calibrated DH,
so it does not depend on which TCP the controller thinks is active (the active
offset has been wrong before: .claude/rules/ur-controller.md, "ur_flange_pose … wrong by tens of mm").
The Cartesian package then gives two things the kinematics cannot: the active TCP
offset — which a target for PolyScope's own move screen must be expressed in —
and a self-check: ``flange ∘ offset`` must land on the reported TCP pose.

Wire format (Client Interface, e-Series): a message is ``>iB`` (int32 length
including the header, uint8 type); robot state is type 16 and holds sub-packages,
each ``>iB`` (int32 length including the header, uint8 type) + payload, all
big-endian. Other message types (version, text, safety) are skipped by length.
"""

from __future__ import annotations

import math
import socket
import struct
import time
from collections.abc import Sequence

from .pose import Transform, pose_trans

MESSAGE_ROBOT_STATE = 16
PKG_JOINT_DATA = 1
PKG_CARTESIAN_INFO = 4
PKG_KINEMATICS_INFO = 5

# A robot-state message is a few kB; anything past this is a desynchronised stream.
MAX_MESSAGE_BYTES = 1 << 16

_JOINT_BYTES = 41  # q_actual, q_target, qd_actual (3 d), I, V, T_motor, T_micro (4 f), mode (B)
_CARTESIAN_POSE_BYTES = 48  # X Y Z Rx Ry Rz
_CARTESIAN_FULL_BYTES = 96  # + TCP offset X Y Z Rx Ry Rz
_KINEMATICS_BYTES = 24 + 4 * 48  # 6 uint32 checksums, then DH theta, a, d, alpha (6 d each)

# No joint angle (rad), position (m) or rotation vector of a real arm is this big.
PLAUSIBLE_ABS = 100.0
# Calibrated DH is another matter: UR's calibration folds large, cancelling link
# offsets into d2..d4 — the UR3e on the bench reports d = [0.1516, 100.06, -35.55,
# -64.38, 0.0851, 0.0917] (2026-09-27; d2+d3+d4 = the nominal 0.131 m).
PLAUSIBLE_DH_ABS = 1.0e4

# Beyond this the offset the controller reports is not the one its TCP pose used.
CONSISTENCY_TOLERANCE_M = 0.002


class StateFrameError(ValueError):
    """The bytes are not a well-formed robot-state stream."""


def iter_messages(buf: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    """Split ``buf`` into complete ``(type, payload)`` messages; return them and
    the unconsumed tail (a partial message still arriving)."""
    out: list[tuple[int, bytes]] = []
    i = 0
    while len(buf) - i >= 5:
        size, mtype = struct.unpack_from(">iB", buf, i)
        if size < 5 or size > MAX_MESSAGE_BYTES:
            raise StateFrameError(f"message length {size} is outside 5..{MAX_MESSAGE_BYTES}")
        if len(buf) - i < size:
            break
        out.append((mtype, buf[i + 5 : i + size]))
        i += size
    return out, buf[i:]


def parse_robot_state(payload: bytes) -> dict:
    """The sub-packages of one robot-state message this module needs:
    ``{"joints": [6], "tcp": [6], "tcp_offset": [6] | None, "dh": {...}}``,
    each key present only when its package was in the message."""
    out: dict = {}
    i = 0
    while len(payload) - i >= 5:
        size, ptype = struct.unpack_from(">iB", payload, i)
        if size < 5 or len(payload) - i < size:
            raise StateFrameError(f"sub-package length {size} overruns the message")
        body = payload[i + 5 : i + size]
        if ptype == PKG_JOINT_DATA and len(body) >= 6 * _JOINT_BYTES:
            out["joints"] = [struct.unpack_from(">d", body, k * _JOINT_BYTES)[0] for k in range(6)]
        elif ptype == PKG_CARTESIAN_INFO and len(body) >= _CARTESIAN_POSE_BYTES:
            out["tcp"] = list(struct.unpack_from(">6d", body, 0))
            out["tcp_offset"] = (
                list(struct.unpack_from(">6d", body, _CARTESIAN_POSE_BYTES))
                if len(body) >= _CARTESIAN_FULL_BYTES
                else None
            )
        elif ptype == PKG_KINEMATICS_INFO and len(body) >= _KINEMATICS_BYTES:
            theta, a, d, alpha = (list(struct.unpack_from(">6d", body, 24 + 48 * k)) for k in range(4))
            out["dh"] = {"theta": theta, "a": a, "d": d, "alpha": alpha}
        i += size
    for key in ("joints", "tcp", "tcp_offset"):
        _check(key, out.get(key))
    for key, vals in (out.get("dh") or {}).items():
        _check(f"DH {key}", vals, PLAUSIBLE_DH_ABS)
    return out


def _check(what: str, vals: Sequence[float] | None, bound: float = 0.0) -> None:
    """Finite and physically plausible: a corrupted byte can decode to 1e159, which
    is finite but overflows every rotation it touches."""
    if vals is None:
        return
    bound = bound or PLAUSIBLE_ABS
    if not all(math.isfinite(v) and abs(v) <= bound for v in vals):
        raise StateFrameError(f"implausible {what} in the robot state: {list(vals)}")


def _dh_matrix(theta: float, a: float, d: float, alpha: float) -> list[list[float]]:
    ct, st, ca, sa = math.cos(theta), math.sin(theta), math.cos(alpha), math.sin(alpha)
    return [
        [ct, -st * ca, st * sa, a * ct],
        [st, ct * ca, -ct * sa, a * st],
        [0.0, sa, ca, d],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _mul4(p: list[list[float]], q: list[list[float]]) -> list[list[float]]:
    return [[sum(p[r][k] * q[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def flange_from_joints(joints: Sequence[float], dh: dict) -> list[float]:
    """Forward kinematics (standard DH, UR's convention: ``Rz(θ+q)·Tz(d)·Tx(a)·Rx(α)``
    per joint) → the flange pose ``[x, y, z, rx, ry, rz]`` in the base frame."""
    if len(joints) != 6 or any(len(dh[k]) != 6 for k in ("theta", "a", "d", "alpha")):
        raise ValueError("forward kinematics needs 6 joints and 6 DH rows")
    m = [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
    for k in range(6):
        m = _mul4(m, _dh_matrix(dh["theta"][k] + joints[k], dh["a"][k], dh["d"][k], dh["alpha"][k]))
    rot = tuple(tuple(m[r][c] for c in range(3)) for r in range(3))
    return Transform(rot, (m[0][3], m[1][3], m[2][3])).to_pose()  # type: ignore[arg-type]


def flange_state(state: dict) -> dict:
    """What :func:`read_flange_state` returns, from one parsed robot state.

    ``flange`` is the kinematic flange when joints and DH are both known; without
    the DH (a controller that never sent it) it falls back to ``tcp ∘ offset⁻¹``
    and says so in ``flange_source``. ``consistency_m`` is how far
    ``flange ∘ offset`` lands from the reported TCP pose (position only)."""
    tcp, offset, joints, dh = state.get("tcp"), state.get("tcp_offset"), state.get("joints"), state.get("dh")
    out: dict = {"tcp": tcp, "tcp_offset": offset, "joints": joints, "flange": None, "flange_source": None}
    if joints is not None and dh is not None:
        out["flange"] = flange_from_joints(joints, dh)
        out["flange_source"] = "kinematics"
    elif tcp is not None and offset is not None:
        out["flange"] = Transform.from_pose(tcp).compose(Transform.from_pose(offset).inverse()).to_pose()
        out["flange_source"] = "tcp_offset"
    if out["flange"] is not None and tcp is not None and offset is not None:
        at = pose_trans(out["flange"], offset)
        out["consistency_m"] = math.dist(at[:3], tcp[:3])
    else:
        out["consistency_m"] = None
    return out


def read_robot_state(
    host: str,
    port: int,
    *,
    timeout_s: float = 3.0,
    need: Sequence[str] = (),
    want: Sequence[str] = (),
    want_s: float = 1.0,
) -> dict:
    """Listen to the state broadcast on ``host:port`` until the robot-state messages
    have supplied every key in ``need`` — and every key in ``want``, or ``want_s``
    has passed since ``need`` was met (merged across messages: the kinematics package
    may come in a different message from the joints). Sends nothing."""
    deadline = time.monotonic() + timeout_s
    soft_deadline: float | None = None
    merged: dict = {}
    buf = b""
    with socket.create_connection((host, port), timeout=timeout_s) as sock:
        while True:
            now = time.monotonic()
            if soft_deadline is not None and now >= soft_deadline:
                return merged
            if now >= deadline:
                if all(k in merged for k in need):
                    return merged
                missing = [k for k in need if k not in merged]
                raise TimeoutError(f"the state broadcast on {host}:{port} gave no {', '.join(missing)}")
            stop = deadline if soft_deadline is None else min(deadline, soft_deadline)
            sock.settimeout(max(0.01, stop - now))
            try:
                chunk = sock.recv(65536)
            except TimeoutError:
                continue
            if not chunk:
                raise ConnectionError(f"{host}:{port} closed the state broadcast")
            messages, buf = iter_messages(buf + chunk)
            for mtype, payload in messages:
                if mtype != MESSAGE_ROBOT_STATE:
                    continue
                state = parse_robot_state(payload)
                # joints and the TCP must come from the same message: they describe one instant
                if "joints" in state or "tcp" in state:
                    for key in ("joints", "tcp", "tcp_offset"):
                        merged.pop(key, None)
                merged.update(state)
            if all(k in merged for k in need):
                if all(k in merged for k in want):
                    return merged
                if soft_deadline is None:
                    soft_deadline = time.monotonic() + want_s


def read_flange_state(host: str, port: int, *, timeout_s: float = 3.0) -> dict:
    """The flange, the TCP pose and the active TCP offset from the state broadcast."""
    state = read_robot_state(
        host, port, timeout_s=timeout_s, need=("joints", "tcp", "tcp_offset"), want=("dh",)
    )
    return flange_state(state)
