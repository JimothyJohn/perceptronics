"""``perceptronics init`` — a few questions, one cell file; and the defaults ``perceptronics up``
fills in so a person starts the cockpit with no flags.

The toolkit grew up driven by an agent: cell profiles, ``PERCEPTRONICS_*`` variables, a
dozen flags. This is the door for a person (Nick, 2026-10-06: "very hard to spin up manually
because it's basically designed for an agent")::

    perceptronics init                 # questions -> ./mycell.env
    perceptronics --cell ./mycell.env doctor
    perceptronics --cell ./mycell.env up

Every answer has a default; ``--yes`` takes them all (a UR3e at 192.168.3.3 with a Hand-E and
the e-Series bracket: the test cell). The file it writes is an ordinary cell file: the same
keys the shipped ones use (``perceptronics cells``), comments included, editable by hand.
Pure stdlib; the questions read ``stdin`` so they can be answered from a pipe or a test.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from .cell import ALLOWED_PREFIXES, parse_env_text

ROBOTS = ("ur-eseries", "ur-polyscopex", "sim", "none")
MODELS = ("UR3e", "UR5e", "UR7e", "UR10e", "UR12e", "UR16e", "UR20", "UR30")
BRACKETS = ("eseries", "ur20", "none")
CAMERAS = ("realsense", "none")
DEFAULT_ROBOT_HOST = "192.168.3.3"


class Answers:
    """The questions in order; ``ask`` reads one line per question (``yes``: the default)."""

    def __init__(self, inp: TextIO, out: TextIO, yes: bool):
        self.inp, self.out, self.yes = inp, out, yes

    def ask(self, prompt: str, default: str, choices: tuple[str, ...] | None = None) -> str:
        hint = f" [{'/'.join(choices)}]" if choices else ""
        self.out.write(f"{prompt}{hint} ({default}): ")
        self.out.flush()
        if self.yes:
            self.out.write(f"{default}\n")
            return default
        line = self.inp.readline()
        if not line:  # EOF: the defaults from here on
            self.out.write(f"{default}\n")
            return default
        text = line.strip() or default
        if choices:
            by_lower = {c.lower(): c for c in choices}
            if text.lower() not in by_lower:
                self.out.write(f"  not one of {', '.join(choices)} — using {default}\n")
                return default
            return by_lower[text.lower()]
        return text


def _number(text: str, default: float, lo: float, hi: float, what: str, out: TextIO) -> float:
    try:
        v = float(text)
    except ValueError:
        out.write(f"  {what}: {text!r} is not a number — using {default:g}\n")
        return default
    if not lo <= v <= hi:
        out.write(f"  {what}: {v:g} is outside {lo:g}..{hi:g} — using {default:g}\n")
        return default
    return v


def cell_text(name: str, a: Mapping[str, str]) -> str:
    """The cell file for a set of answers (``robot``, ``host``, ``model``, ``bracket``,
    ``camera``, ``standoff_mm``), as ``perceptronics init`` writes it. The tool itself is
    the robot's active TCP (set on the pendant), so no tool length is asked for."""
    lines = [
        f"# Cell profile '{name}' — written by `perceptronics init`. Edit by hand; `perceptronics cells`",
        "# shows the shipped ones for comparison. Loaded by `--cell ./<this file>` / `UR_CELL=<path>`;",
        "# a variable already set in the shell wins.",
    ]
    robot = a["robot"]
    if robot == "none":
        lines += ["# No robot: the cockpit shows the camera, the robot panel stays dark.", "UR_HOST="]
    else:
        lines.append(f"UR_HOST={a['host']}")
        if robot == "ur-eseries":
            lines += [
                "# PolyScope 5 (e-Series): Dashboard :29999, Primary :30001, RTDE :30004.",
                "UR_PLATFORM=e-series",
                "UR_DASH_PORT=29999",
                "UR_PRIMARY_PORT=30001",
                "UR_RTDE_PORT=30004",
            ]
        elif robot == "ur-polyscopex":
            lines += [
                "# PolyScope X: the Robot-API on :80, Primary :30001 and RTDE :30004 (turn both on under",
                "# Settings -> Security -> Services; Remote mode for any move over the network).",
                "UR_PLATFORM=polyscopex",
                "UR_ROBOT_API_PORT=80",
                "UR_PRIMARY_PORT=30001",
                "UR_RTDE_PORT=30004",
            ]
        else:  # the PolyScope X simulator on this machine (docker compose --profile polyscopex)
            lines += [
                "# The PolyScope X simulator on this machine: UI :8000, Primary :31001, RTDE :31004.",
                "UR_PLATFORM=polyscopex",
                "UR_ROBOT_API_PORT=8000",
                "UR_PRIMARY_PORT=31001",
                "UR_RTDE_PORT=31004",
            ]
        lines.append(f"UR_ROBOT_MODEL={a['model']}")
    standoff = float(a["standoff_mm"]) / 1000.0
    lines += [
        "# The tool is the robot's active TCP (set it on the pendant: Installation -> General -> TCP);",
        "# the camera computer owns no tool length. A cockpit approach stops the TCP this far short",
        "# of the point along the camera's ray.",
        f"PERCEPTRONICS_STANDOFF_M={standoff:.3f}",
    ]
    if a["bracket"] != "none":
        lines += [
            "# The camera bracket print: its nominal hand-eye seeds the calibration",
            "# (`perceptronics calibrate --apply` replaces it).",
            f"PERCEPTRONICS_BRACKET={a['bracket']}",
        ]
    if a["camera"] == "none":
        lines += ["# No camera: the cockpit runs its synthetic scene.", "PERCEPTRONICS_FAKE=1"]
    else:
        lines += [
            "# The D435, on the High Density preset (dark part tops keep their depth).",
            "PERCEPTRONICS_RS_PRESET=high_density",
        ]
    return "\n".join(lines) + "\n"


def run_init(
    name: str = "mycell",
    *,
    out_dir: str | None = None,
    yes: bool = False,
    force: bool = False,
    inp: TextIO | None = None,
    out: TextIO | None = None,
) -> int:
    inp = sys.stdin if inp is None else inp
    out = sys.stdout if out is None else out
    name = (name or "mycell").strip()
    if not name.replace("-", "").replace("_", "").isalnum():
        out.write(f"init: the name {name!r} must be letters, digits, - or _\n")
        return 2
    path = Path(out_dir or ".") / f"{name}.env"
    if path.exists() and not force:
        out.write(f"init: {path} exists — edit it, or --force to write it again\n")
        return 2
    q = Answers(inp, out, yes)
    out.write(f"A cell file for '{name}'. Enter keeps the default.\n")
    robot = q.ask("Robot", "ur-eseries", ROBOTS)
    host = "localhost" if robot == "sim" else ""
    if robot in ("ur-eseries", "ur-polyscopex"):
        host = q.ask("The robot's address (pendant: Settings -> System -> Network)", DEFAULT_ROBOT_HOST)
    model = q.ask("Arm", "UR3e", MODELS) if robot != "none" else "UR3e"
    model = next((m for m in MODELS if m.lower() == model.lower()), "UR3e")
    standoff = _number(
        q.ask("Approach: the tool (the robot's TCP) stops this far above the part, mm", "75"),
        75,
        10,
        300,
        "approach",
        out,
    )
    bracket = q.ask("Camera bracket print", "eseries", BRACKETS)
    camera = q.ask("Camera", "realsense", CAMERAS)
    answers = {
        "robot": robot,
        "host": host,
        "model": model,
        "standoff_mm": f"{standoff:g}",
        "bracket": bracket,
        "camera": camera,
    }
    text = cell_text(name, answers)
    bad = [k for k in parse_env_text(text) if not k.startswith(ALLOWED_PREFIXES)]
    if bad:  # cannot happen from the answers above; the cell loader's rule, held here too
        out.write(f"init: refusing to write keys outside the cell's namespace: {bad}\n")
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    out.write(
        f"\nwrote {path}\n\nNext:\n"
        f"  perceptronics --cell {path} doctor     # the pre-flight: camera, robot, calibration\n"
        f"  perceptronics --cell {path} up         # the cockpit, the page opens\n"
    )
    if camera == "realsense" and sys.platform == "darwin":
        out.write("  (macOS: the camera needs `sudo` in front of `perceptronics`, from a local Terminal)\n")
    return 0


def up_bind(env: Mapping[str, str]) -> str:
    """Where ``perceptronics up`` listens: every interface when the cell names a robot (the
    pendant's URCap must reach the cockpit), loopback when there is none or it is this machine."""
    host = (env.get("UR_HOST") or "").strip().lower()
    if not host or host in ("localhost", "127.0.0.1", "::1"):
        return "127.0.0.1"
    return "0.0.0.0"
