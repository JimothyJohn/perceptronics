"""perceive command-line interface — a human/scripting entry point.

    perceive --cell ur20 doctor            # pre-flight: SDK, camera, robot reachability + state
    perceive cells                         # the shipped cell profiles (sim / ur3 / ur20)
    perceive rs-info                       # RealSense devices + SDK (needs librealsense2)
    perceive gui --fake                    # the RGB-D cockpit (synthetic scene; drop --fake for the camera)

Camera + backend selection come from ``--device`` / ``--width`` / ``--height``
/ ``--fps`` / ``--segment-backend`` or the matching ``PERCEPTRONICS_*`` env vars, and
a cell (``--cell``) sets the robot side.

Every command prints its structured result as JSON and exits non-zero if the
result reported ``ok=false``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .cell import ENV_CELL, apply_cell, list_cells
from .config import PerceptionConfig
from .orbitcal import add_calibrate_args, run_calibrate
from .pickcycle import add_pick_cycle_args, run_pick_cycle
from .webapp import (
    DEFAULT_PORT,
    add_camera_args,
    add_cors_arg,
    add_pick_port_arg,
    add_robot_args,
    camera_from_args,
    cors_from_args,
    robot_from_args,
)


def _emit(result: dict) -> int:
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="perceptronics", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--cell",
        default=None,
        help=f"cell profile: {'|'.join(list_cells())} or a path to a .env file (default: ${ENV_CELL}); "
        "sets UR_HOST/ports/bracket unless already set in the environment",
    )
    ap.add_argument(
        "--device", type=int, default=None, help="camera index (default: $PERCEPTRONICS_DEVICE or 0)"
    )
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--fps", type=int, default=None)
    ap.add_argument(
        "--segment-backend",
        default=None,
        help="stub | sam (default: $PERCEPTRONICS_SEGMENT_BACKEND or stub) — click-to-segment in the gui",
    )

    ap.add_argument(
        "--sam-model",
        default=None,
        help="SAM checkpoint id for the sam backend (default: $PERCEPTRONICS_SAM_MODEL)",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    ce = sub.add_parser("cells", help="list the shipped cell profiles and what each sets")
    ce.add_argument(
        "--export",
        metavar="CELL",
        default=None,
        help='print `export KEY=VALUE` lines for one cell, for `eval "$(perceptronics cells --export ur20)"` '
        "so plain `urctl` commands see the same host/ports",
    )

    dr = sub.add_parser("doctor", help="pre-flight checklist: SDK, camera, robot reachability + state")
    dr.add_argument("--stream", action="store_true", help="also open the camera and judge frames")
    dr.add_argument("--no-camera", action="store_true", help="skip the SDK/camera checks")
    dr.add_argument("--no-robot", action="store_true", help="skip the controller checks")
    dr.add_argument("--json", dest="as_json", action="store_true", help="machine-readable report")
    dr.add_argument("--library", default=None, help="path to librealsense2 (default: $REALSENSE_LIB / auto)")
    dr.add_argument(
        "--cockpit-url",
        default=f"http://127.0.0.1:{DEFAULT_PORT}",
        help="report on a running cockpit at this URL (default: the local one)",
    )

    ri = sub.add_parser("rs-info", help="list attached RealSense cameras + SDK version (no streaming)")
    ri.add_argument("--library", default=None, help="path to librealsense2 (default: $REALSENSE_LIB / auto)")
    ri.add_argument(
        "--options",
        action="store_true",
        help="also dump every sensor option (value/range) per sensor — what a preset or another app left",
    )

    gu = sub.add_parser(
        "gui", help="local RGB-D cockpit: live view, click-to-segment, snapshots, send-to-robot"
    )
    add_camera_args(gu)
    add_robot_args(gu)
    gu.add_argument("--bind", default="127.0.0.1", help="interface to bind (default: loopback only)")
    gu.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")
    gu.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    gu.add_argument("--demo", action="store_true", help="open the demo view: one picture, four big buttons")
    add_cors_arg(gu)
    add_pick_port_arg(gu)

    ini = sub.add_parser(
        "init",
        help="a few questions -> a cell file for your robot and camera (then: doctor, up)",
    )
    ini.add_argument("name", nargs="?", default="mycell", help="the cell's name (default: mycell)")
    ini.add_argument("--out", default=None, help="write <name>.env here (default: the current directory)")
    ini.add_argument("--yes", action="store_true", help="take every default without asking")
    ini.add_argument("--force", action="store_true", help="overwrite an existing file")

    up = sub.add_parser(
        "up",
        help="the cockpit for a cell, no flags needed: the camera, the robot from the cell, the page opens",
    )
    add_camera_args(up)
    add_robot_args(up)
    up.add_argument(
        "--bind",
        default=None,
        help="interface to bind (default: every interface when the cell names a robot, so the pendant "
        "reaches it; loopback otherwise)",
    )
    up.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")
    up.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    up.add_argument("--demo", action="store_true", help="open the demo view: one picture, four big buttons")
    add_cors_arg(up)
    add_pick_port_arg(up)

    pc = sub.add_parser(
        "pick-cycle",
        help="heuristic routine on a running cockpit: lift every block in view an inch and set it back "
        "(--drop to shuffle)",
    )
    add_pick_cycle_args(pc)

    cb = sub.add_parser(
        "calibrate",
        help="mark-less hand-eye calibration on a running cockpit: orbit the block under the camera, "
        "click its top-face centre into the cockpit's calibration at every view, solve, trim "
        "(--apply to keep)",
    )
    add_calibrate_args(cb)
    return ap


def _config_from_args(args) -> PerceptionConfig:
    overrides: dict[str, object] = {}
    if args.device is not None:
        overrides["device_index"] = args.device
    if args.width is not None:
        overrides["width"] = args.width
    if args.height is not None:
        overrides["height"] = args.height
    if args.fps is not None:
        overrides["fps"] = args.fps
    if getattr(args, "segment_backend", None) is not None:
        overrides["segment_backend"] = args.segment_backend
    if getattr(args, "sam_model", None) is not None:
        overrides["sam_model"] = args.sam_model
    return PerceptionConfig.from_env(**overrides)


def _realsense_command(args) -> int:
    """The RealSense subcommands — kept apart so `perceive synthetic` never
    touches the SDK loader."""
    from .realsense import RealSenseError, list_devices, platform_hint

    config = _config_from_args(args)
    if args.cmd == "rs-info":
        try:
            from .realsense import load_api

            api = load_api(args.library)
            devices = list_devices(args.library)
            options = None
            if args.options:
                from .realsense import list_sensor_options

                options = list_sensor_options(args.library)
        except RealSenseError as exc:
            hint = platform_hint(exc)
            return _emit({"ok": False, "error": str(exc), "hint": hint or None})
        result = {"ok": True, "sdk": {"path": api.path, "api_version": api.version}, "devices": devices}
        if options is not None:
            result["options"] = options
        return _emit(result)

    if args.cmd == "gui":
        from .webapp import serve

        serve(
            camera_from_args(args, config),
            config=config,
            bind=args.bind,
            port=args.port,
            open_browser=not args.no_browser,
            robot=robot_from_args(args),
            demo=args.demo,
            cors=cors_from_args(args),
            pick_port=args.pick_port,
        )
        return 0

    raise SystemExit(f"unknown realsense command {args.cmd}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # legacy Windows codepages: replace, don't crash
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        cell = apply_cell(args.cell)
    except ValueError as exc:
        print(f"--cell: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "cells":
        from .cell import load_cell

        if args.export:
            try:
                values = load_cell(args.export)
            except ValueError as exc:
                print(f"--export: {exc}", file=sys.stderr)
                return 2
            for key, value in values.items():
                if value:
                    print(f"export {key}={value}")
            print(f"export {ENV_CELL}={args.export}")
            return 0
        print(json.dumps({"active": cell, "cells": {n: load_cell(n) for n in list_cells()}}, indent=2))
        return 0
    if args.cmd == "doctor":
        from .doctor import run_doctor

        report = run_doctor(
            perceptronics_config=_config_from_args(args),
            camera=not args.no_camera,
            stream=args.stream,
            robot=not args.no_robot,
            library=args.library,
            cockpit_url=args.cockpit_url or None,
        )
        if args.as_json:
            print(json.dumps(report.as_dict(), indent=2, default=str))
        else:
            print(report.render())
        return 0 if report.ok else 1
    if args.cmd == "pick-cycle":
        return run_pick_cycle(args)
    if args.cmd == "calibrate":
        return run_calibrate(args)
    if args.cmd == "init":
        from .wizard import run_init

        return run_init(args.name, out_dir=args.out, yes=args.yes, force=args.force)
    if args.cmd == "up":
        from .wizard import up_bind

        if args.bind is None:
            args.bind = up_bind(os.environ)
        args.cmd = "gui"
        return _realsense_command(args)
    if args.cmd in ("rs-info", "gui"):
        return _realsense_command(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
