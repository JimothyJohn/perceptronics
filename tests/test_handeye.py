"""Camera-on-flange geometry (perceptronics.handeye) and the cockpit's robot bridge
(perceptronics.robotlink) — the latter driven through a real Robot against the
fake controller from test_urctl."""

from __future__ import annotations

import math

import pytest

from perceptronics.handeye import (
    BRACKET_NOMINAL,
    BRACKET_SEEDS,
    ENV_T_FLANGE_CAMERA,
    HandEye,
    locate,
    parse_pose_text,
    transform_from_extrinsics,
)
from perceptronics.robotlink import RobotLink
from tests.test_urctl import FakeController
from urctl.config import RobotConfig
from urctl.pose import Transform, pose_inv, pose_trans
from urctl.robot import Robot

TOOL_DOWN = [0.0, math.pi, 0.0]  # π about Y: tool z → base -Z, tool x → base -X, tool y kept


def _close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b, strict=True))


C5, S5 = math.cos(math.radians(5.0)), math.sin(math.radians(5.0))
SEED_ORIGIN = (0.0175, 0.063922336, 0.000626916)


def test_bracket_nominal_matches_readme_section_3():
    # Rev C: depth origin (17.5, 63.9, 0.6) mm; x_cam = -X, the optical axis drafted 5° from +Z
    # toward the flange axis (the camera is on +Y, so z_cam leans to -Y), y_cam follows it
    assert _close(BRACKET_NOMINAL.translation, SEED_ORIGIN)
    assert _close(BRACKET_NOMINAL.rotate((1, 0, 0)), (-1, 0, 0))
    assert _close(BRACKET_NOMINAL.rotate((0, 1, 0)), (0, -C5, -S5))
    assert _close(BRACKET_NOMINAL.rotate((0, 0, 1)), (0, -S5, C5))
    # a point 300 mm out of the lens is 26 mm nearer the flange axis than the lens is
    x, y, z = HandEye().camera_to_flange((0, 0, 0.3))
    assert _close((x, y, z), (0.0175, SEED_ORIGIN[1] - 0.3 * S5, SEED_ORIGIN[2] + 0.3 * C5))
    assert SEED_ORIGIN[1] - y == pytest.approx(0.02615, abs=1e-5)
    # the optical axis crosses the flange's YZ-plane centre line ~0.73 m out
    assert SEED_ORIGIN[1] / math.tan(math.radians(5.0)) == pytest.approx(0.7306, abs=1e-4)


def test_extrinsics_move_the_colour_origin():
    ext = {"rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "translation": [0.015, 0.0, 0.0]}
    he = HandEye().with_extrinsics(ext)
    # SDK convention: p_color = R·p_depth + t, so the *depth* origin sits at
    # +15 mm along colour x; a point on the colour axis is at depth x = -15 mm,
    # and camera x is flange -X.
    base = HandEye().camera_to_flange((0, 0, 0.3))
    assert _close(he.camera_to_flange((0, 0, 0.3)), (base[0] + 0.015, base[1], base[2]))
    assert _close(transform_from_extrinsics(None).translation, (0, 0, 0))
    assert he.as_dict()["depth_to_color_translation"] == [0.015, 0.0, 0.0]
    assert HandEye().with_extrinsics(None).flange_to_color == HandEye().flange_to_depth


def test_from_env_parses_a_calibration_or_falls_back():
    assert HandEye.from_env({}).source == "bracket-nominal:eseries"
    he = HandEye.from_env({ENV_T_FLANGE_CAMERA: "[0.07, -0.02, 0.04, 0, 0, 1.5707963]"})
    assert he.source.startswith("env:") and _close(he.flange_to_depth.translation, (0.07, -0.02, 0.04))
    assert _close(he.flange_to_depth.rotate((1, 0, 0)), (0, 1, 0), 1e-6)
    assert parse_pose_text("1,2,3,4,5,6") == [1, 2, 3, 4, 5, 6]
    assert parse_pose_text('{"pose": [0,0,0,0,0,0]}') == [0.0] * 6
    for bad in ("", "1,2,3", "[1,2,3,4,5,nan]", "abc", "[1,2,3,4,5,6,7]"):
        with pytest.raises(ValueError):
            parse_pose_text(bad)


def test_locate_geometry_tool_down():
    """Flange 0.5 m out, 0.5 m up, tool pointing straight down; the camera sees
    the object 0.3 m ahead (i.e. 0.3 m below the lens)."""
    he = HandEye()
    flange = [0.5, 0.0, 0.5, *TOOL_DOWN]
    tcp = pose_trans(flange, [0, 0, 0.12, 0, 0, 0])  # 120 mm tool
    out = locate(he, flange, (0.0, 0.0, 0.3), tcp_pose=tcp, standoff_m=0.05)
    base_from_flange = Transform.from_pose(flange)
    expect_base = base_from_flange.apply(he.camera_to_flange((0, 0, 0.3)))
    assert _close(out["point_base_m"], expect_base, 1e-9)
    # tool down => the camera looks down, drafted 5° back toward the flange axis (flange y is kept
    # under the π about Y, and the camera sits on flange +Y)
    assert _close(out["view_ray_base"], (0, -S5, -C5), 1e-9)
    assert out["point_base_m"][2] == pytest.approx(0.5 - SEED_ORIGIN[2] - 0.3 * C5, abs=1e-9)
    # approach = the robot's TCP 50 mm short of the object along the camera's ray, orientation kept
    short = [p - 0.05 * r for p, r in zip(out["point_base_m"], out["view_ray_base"], strict=True)]
    assert _close(out["approach_pose"][:3], short, 1e-9)
    assert out["approach_pose"][3:] == tcp[3:]
    # the lateral camera offset on the bracket shows up in base xy (flange x flips under the π about Y)
    assert out["point_base_m"][0] == pytest.approx(0.5 - 0.0175, abs=1e-9)
    assert out["point_base_m"][1] == pytest.approx(SEED_ORIGIN[1] - 0.3 * S5, abs=1e-9)
    assert out["handeye"]["source"] == "bracket-nominal:eseries" and out["standoff_m"] == 0.05


def test_locate_rejects_bad_input():
    he = HandEye()
    flange = [0.5, 0.0, 0.5, *TOOL_DOWN]
    with pytest.raises(ValueError):
        locate(he, flange, (0.0, 0.0), tcp_pose=flange)
    with pytest.raises(ValueError):
        locate(he, flange, (0.0, float("nan"), 0.3), tcp_pose=flange)
    with pytest.raises(ValueError):
        locate(he, flange, (0.0, 0.0, 0.3), tcp_pose=flange, standoff_m=2.0)
    with pytest.raises(ValueError):
        locate(he, flange, (0.0, 0.0, 0.3), tcp_pose=[0, 0, 0], standoff_m=0.1)


def test_robot_get_flange_pose_agrees_with_controller(monkeypatch):
    fake = FakeController().install(monkeypatch)
    robot = Robot(RobotConfig(host="fake"))
    fp = robot.get_flange_pose()
    assert fp["ok"] and fp["tcp"] == pytest.approx(fake.tcp_pose, abs=1e-6)
    assert fp["tcp_offset"] == pytest.approx(fake.tcp_offset, abs=1e-6)
    expect = pose_trans(fake.tcp_pose, pose_inv(fake.tcp_offset))
    assert fp["flange"][:3] == pytest.approx(expect[:3], abs=1e-5)  # the fake echoes 6 decimals
    assert fp["flange_reported"][:3] == pytest.approx(expect[:3], abs=1e-5)
    assert fp["host_controller_mismatch_m"] < 1e-5
    # the 120 mm tool along +Z with the tool pointing down puts the flange 120 mm *above* the TCP
    assert fp["flange"][2] == pytest.approx(fake.tcp_pose[2] + 0.12, abs=1e-6)
    sent = [s for s in fake.primary_sends if "urctl/flange" in s]
    assert len(sent) == 1 and "get_tcp_offset()" in sent[0] and "pose_inv" in sent[0]


def test_robot_get_flange_pose_dry_run_and_no_answer(monkeypatch):
    fake = FakeController().install(monkeypatch)
    dry = Robot(RobotConfig(host="fake"), dry_run=True).get_flange_pose()
    assert dry["ok"] and dry["dry_run"] and len(dry["flange"]) == 6 and not fake.primary_sends
    from urctl import transport

    monkeypatch.setattr(transport, "send_and_collect", lambda *a, **k: b"noise\n")  # nothing parseable
    fp = Robot(RobotConfig(host="fake")).get_flange_pose()
    assert not fp["ok"] and "no TCP pose" in fp["error"]


def test_robotlink_locate_then_move_goes_through_the_tool_registry(monkeypatch):
    fake = FakeController().install(monkeypatch)
    link = RobotLink(RobotConfig(host="fake"))
    link.attach_camera(
        {
            "extrinsics_depth_to_color": {
                "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "translation": [0.015, 0, 0],
            }
        }
    )
    d = link.describe()
    assert (
        d["host"] == "fake"
        and not d["dry_run"]
        and d["handeye"]["depth_to_color_translation"] == [0.015, 0.0, 0.0]
    )
    loc = link.locate((0.0, 0.0, 0.3), standoff_m=0.08)
    assert loc["robot"]["host_controller_mismatch_m"] < 1e-5  # the controller's pose_trans agrees
    assert (
        loc["ok"]
        and len(loc["approach_pose"]) == 6
        and loc["robot"]["tcp_offset"] == pytest.approx(fake.tcp_offset, abs=1e-6)
    )
    # the default approach is by the robot's own active TCP (2026-10-08: the cockpit owns no
    # tool length): the approach keeps its orientation (compare rotations, not spellings)
    assert loc["reference"] == "tcp" and loc["tcp"] is None
    assert _same_rotation(loc["approach_pose"][3:], fake.tcp_pose[3:])
    mv = link.move(loc["approach_pose"])
    assert mv["ok"] and mv["action"] == "move_tcp" and mv["safety"]["ok"]
    movel = [s for s in fake.primary_sends if "movel(" in s][-1]
    # absolute, slow, and gentle: a=0.1 since 2026-09-27 (Nick: "the stops thud" at 0.3)
    assert "pose_add" not in movel and "v=0.1" in movel and "a=0.1" in movel
    # ... and the move runs with the controller's active TCP as it is: no set_tcp of the cockpit's
    assert "set_tcp(" not in movel
    # audit trail: both actions logged on the same robot
    actions = [r.action for r in link.robot.audit.records] if hasattr(link.robot.audit, "records") else None
    assert actions is None or ("get_flange_pose" in actions and "move_tcp" in actions)


def test_robotlink_refusals_and_validation(monkeypatch):
    fake = FakeController(robot_mode="POWER_OFF").install(monkeypatch)
    link = RobotLink(RobotConfig(host="fake"))
    mv = link.move([0.5, 0, 0.3, *TOOL_DOWN])
    assert not mv["ok"] and mv["safety"]["ok"] is False  # envelope refused: not RUNNING
    assert not any("movel(" in s for s in fake.primary_sends)
    with pytest.raises(ValueError):
        link.move([0.5, 0, 0.3])
    with pytest.raises(ValueError):
        link.move([0.5, 0, 0.3, *TOOL_DOWN], velocity=0)
    with pytest.raises(ValueError):
        link.move([0.5, 0, float("inf"), *TOOL_DOWN])


def test_robotlink_dry_run_needs_no_controller():
    link = RobotLink(
        RobotConfig(host="127.0.0.1", dashboard_port=1, primary_port=1, timeout=0.2), dry_run=True
    )
    loc = link.locate((0.0, 0.0, 0.3))
    assert loc["ok"] and loc["robot"]["dry_run"] is True
    mv = link.move(loc["approach_pose"])
    assert mv["ok"] and mv["dry_run"]


def test_robotlink_unreachable_is_an_error_not_a_crash():
    link = RobotLink(RobotConfig(host="127.0.0.1", dashboard_port=1, primary_port=1, timeout=0.2))
    loc = link.locate((0.0, 0.0, 0.3))
    assert not loc["ok"] and "unreachable" in loc["error"]


def test_bracket_seeds_match_the_bracket_build_info():
    """Every print's seed is the numbers ``bracket.py`` derived, in that robot's own
    flange frame (UR: the bracket's frame; UFACTORY: turned 180°) — the README §3
    table and ``out/build_info.json`` are the source of truth, not this file."""
    import json
    from pathlib import Path

    info = json.loads(
        (Path(__file__).resolve().parents[1] / "hardware/d435-tool-bracket/out/build_info.json").read_text()
    )
    variants = info["export"]["variants"]
    assert set(BRACKET_SEEDS) == set(variants)
    for name, seed in BRACKET_SEEDS.items():
        d = variants[name]["derived"]
        origin_m = tuple(v / 1000.0 for v in d["depth_origin_robot_flange_mm"])
        assert _close(seed.translation, origin_m, tol=1e-6), name
        axes = d["camera_axes_in_robot_flange"]
        assert _close(seed.rotate((1, 0, 0)), axes["x_cam"], tol=1e-5), name
        assert _close(seed.rotate((0, 1, 0)), axes["y_cam"], tol=1e-5), name
        assert _close(seed.rotate((0, 0, 1)), axes["z_cam"], tol=1e-5), name


def test_the_uf850_seed_looks_in_toward_the_flange_axis_from_its_side():
    # UFACTORY's flange frame: the camera hangs on -X, so its axis tips toward +X
    seed = BRACKET_SEEDS["uf850"]
    assert seed.translation[0] < -0.05 and abs(seed.translation[2]) < 0.002
    z = seed.rotate((0, 0, 1))
    assert z[0] > 0 and z[2] == pytest.approx(math.cos(math.radians(5.0)), abs=1e-6)
    assert HandEye.from_env({"PERCEPTRONICS_BRACKET": "uf850"}).source == "bracket-nominal:uf850"


def test_bracket_variant_selection():
    assert HandEye.for_bracket("ur20").source == "bracket-nominal:ur20"
    assert HandEye.for_bracket("UR20 ").flange_to_depth is BRACKET_SEEDS["ur20"]
    assert HandEye.from_env({"PERCEPTRONICS_BRACKET": "ur20"}).source == "bracket-nominal:ur20"
    assert not HandEye.from_env({"PERCEPTRONICS_BRACKET": "ur20"}).calibrated
    # an explicit calibration beats the bracket choice
    he = HandEye.from_env(
        {"PERCEPTRONICS_BRACKET": "ur20", "PERCEPTRONICS_T_FLANGE_CAMERA": "[0,0,0.1,0,0,0]"}
    )
    assert he.calibrated and he.source.startswith("env:")
    with pytest.raises(ValueError, match="unknown bracket"):
        HandEye.for_bracket("ur99")


def test_from_env_precedence_env_then_file_then_seed(tmp_path):
    import json

    from perceptronics.handeye import default_handeye_path

    f = tmp_path / "handeye_ur20.json"
    f.write_text(json.dumps({"flange_to_depth_pose": [0.01, 0.02, 0.03, 0, 0, 0.1]}))
    env = {"UR_CELL": "ur20", "PERCEPTRONICS_HANDEYE_FILE": str(f), "PERCEPTRONICS_BRACKET": "ur20"}
    he = HandEye.from_env(env)
    assert (
        he.calibrated
        and he.source == f"file:{f}"
        and _close(he.flange_to_depth.translation, (0.01, 0.02, 0.03))
    )
    env["PERCEPTRONICS_T_FLANGE_CAMERA"] = "[0,0,0.5,0,0,0]"
    assert HandEye.from_env(env).source.startswith("env:")
    # default path follows the cell name; missing file → seed
    assert default_handeye_path({"UR_CELL": "ur3"}).endswith("handeye_ur3.json")
    assert default_handeye_path({}).endswith("handeye.json")
    assert (
        HandEye.from_env({"UR_CELL": "nope-no-file", "PERCEPTRONICS_BRACKET": "ur20"}).source
        == "bracket-nominal:ur20"
    )


def test_locate_reports_reach_against_the_arm():
    """The verdict is on screen before Move: the approach pose is checked against
    the arm's reach (the same cap the envelope enforces)."""
    he = HandEye()
    flange = [0.5, 0.0, 0.5, *TOOL_DOWN]
    out = locate(he, flange, (0.0, 0.0, 0.3), tcp_pose=flange, standoff_m=0.05)
    assert out["reachable"] is None and out["max_reach_m"] is None
    assert out["approach_distance_m"] == pytest.approx(
        math.sqrt(sum(v * v for v in out["approach_pose"][:3])), abs=1e-12
    )
    assert out["point_distance_m"] == pytest.approx(
        math.sqrt(sum(v * v for v in out["point_base_m"])), abs=1e-12
    )
    # a UR10e reaches it; a UR3e (0.5 m) does not
    assert locate(he, flange, (0, 0, 0.3), tcp_pose=flange, max_reach_m=1.3)["reachable"] is True
    near = locate(he, flange, (0, 0, 0.3), tcp_pose=flange, max_reach_m=0.5)
    assert near["reachable"] is False and near["max_reach_m"] == 0.5


def test_robotlink_locate_carries_the_models_reach(monkeypatch):
    FakeController().install(monkeypatch)
    link = RobotLink(RobotConfig(host="fake", robot_model="UR3e"))
    loc = link.locate((0.0, 0.0, 0.3))
    assert loc["ok"] and loc["max_reach_m"] == 0.5 and loc["model"] == "UR3E"
    assert loc["reachable"] is (loc["approach_distance_m"] <= 0.5)


def test_locate_can_measure_the_standoff_from_the_flange():
    """Tool down, 120 mm active TCP. 'flange' puts the *flange* 75 mm above
    the point; the returned approach is the TCP pose that achieves it."""
    he = HandEye()
    flange = [0.5, 0.0, 0.5, *TOOL_DOWN]
    offset = [0, 0, 0.12, 0, 0, 0]
    tcp = pose_trans(flange, offset)
    out = locate(
        he, flange, (0.0, 0.0, 0.3), tcp_pose=tcp, standoff_m=0.075, reference="flange", tcp_offset=offset
    )
    assert out["reference"] == "flange" and out["tcp_offset"] == offset
    # the flange target is 75 mm up the (downward) view ray from the point
    expect_flange = [p - 0.075 * r for p, r in zip(out["point_base_m"], out["view_ray_base"], strict=True)]
    assert _close(out["flange_target_pose"][:3], expect_flange, 1e-9)
    assert out["flange_target_pose"][3:] == pytest.approx(flange[3:], abs=1e-9)  # orientation kept
    # the approach (TCP) pose is that flange pose pushed through the offset: 120 mm further down
    assert _close(out["approach_pose"], pose_trans(out["flange_target_pose"], offset), 1e-9)
    assert out["approach_pose"][2] == pytest.approx(out["flange_target_pose"][2] - 0.12, abs=1e-9)
    # tcp reference still reports where the flange would end up
    out2 = locate(
        he, flange, (0.0, 0.0, 0.3), tcp_pose=tcp, standoff_m=0.075, tcp_offset=offset, reference="tcp"
    )
    assert out2["reference"] == "tcp"
    assert _close(out2["flange_target_pose"], pose_trans(out2["approach_pose"], pose_inv(offset)), 1e-9)
    assert locate(he, flange, (0, 0, 0.3), tcp_pose=tcp, reference="tcp")["flange_target_pose"] is None
    with pytest.raises(ValueError):
        locate(he, flange, (0, 0, 0.3), tcp_pose=tcp, reference="flange")  # needs the offset
    with pytest.raises(ValueError):
        locate(he, flange, (0, 0, 0.3), tcp_pose=tcp, reference="wrist")
    with pytest.raises(ValueError):
        locate(he, flange, (0, 0, 0.3), tcp_pose=tcp, reference="flange", tcp_offset=[0, 0, 0])


def test_robotlink_approach_defaults_come_from_the_cell_env(monkeypatch):
    fake = FakeController().install(monkeypatch)
    link = RobotLink(RobotConfig(host="fake"))
    assert link.describe()["approach"] == {
        "standoff_m": 0.10,
        "reference": "tcp",  # the robot's active TCP: the only tool offset (Nick, 2026-10-08)
        "tcp": None,
        "velocity": 0.1,
        "acceleration": 0.1,  # gentle since 2026-09-27 (was 0.3: the stops thudded)
    }
    # the retired reference variable is ignored: the reference is the robot's TCP regardless
    monkeypatch.setenv("PERCEPTRONICS_APPROACH_REFERENCE", "flange")
    monkeypatch.setenv("PERCEPTRONICS_STANDOFF_M", "0.075")
    link = RobotLink(RobotConfig(host="fake"))
    assert link.describe()["approach"]["standoff_m"] == 0.075
    assert link.describe()["approach"]["reference"] == "tcp"
    # a per-call reference still works (the calibration and the flange-referenced tools ask for it)
    loc = link.locate((0.0, 0.0, 0.3), reference="flange")
    assert loc["ok"] and loc["reference"] == "flange" and loc["standoff_m"] == 0.075
    assert loc["tcp_offset"] == pytest.approx(fake.tcp_offset, abs=1e-6)
    loc = link.locate((0.0, 0.0, 0.3), standoff_m=0.2, reference="tcp")
    assert loc["reference"] == "tcp" and loc["standoff_m"] == 0.2
    with pytest.raises(ValueError):
        link.locate((0.0, 0.0, 0.3), reference="wrist")
    with pytest.raises(ValueError):
        link.locate((0.0, 0.0, 0.3), reference="fingertip")  # gone with the Pi-side tool length
    monkeypatch.setenv("PERCEPTRONICS_STANDOFF_M", "5")
    with pytest.raises(ValueError):
        RobotLink(RobotConfig(host="fake"))


def test_robotlink_move_passes_the_tcp_override(monkeypatch):
    fake = FakeController().install(monkeypatch)
    link = RobotLink(RobotConfig(host="fake", robot_model="UR3e"))
    res = link.move([0.3, 0.1, 0.2, 0, 3.14, 0], tcp=[0, 0, 0, 0, 0, 0])
    assert res["ok"] and "set_tcp(p[0.0, 0.0, 0.0, 0.0, 0.0, 0.0])" in fake.primary_sends[-1]
    with pytest.raises(ValueError):
        link.move([0.3, 0.1, 0.2, 0, 3.14, 0], tcp=[0, 0])


def test_robotlink_approach_cycle_is_one_flange_program_that_returns_home(monkeypatch):
    fake = FakeController().install(monkeypatch)
    monkeypatch.setenv("PERCEPTRONICS_STANDOFF_M", "0.075")
    link = RobotLink(RobotConfig(host="fake", robot_model="UR10e"))  # the fake's flange sits 0.5 m out
    res = link.approach_cycle((0.0, 0.0, 0.3), reference="flange", clearance_m=0.1, hold_s=1.0, velocity=0.15)
    assert res["ok"] and res["completed_legs"] == 4, res
    cyc = res["cycle"]
    loc = res["locate"]
    assert cyc["reference"] == "flange" and cyc["standoff_m"] == 0.075 and cyc["tcp"] == [0.0] * 6
    assert cyc["target_pose"] == loc["flange_target_pose"] and cyc["capture_pose"] == loc["flange_pose"]
    assert (
        cyc["over_pose"][2] == pytest.approx(cyc["target_pose"][2] + 0.1)
        and cyc["over_pose"][:2] == cyc["target_pose"][:2]
    )
    legs = [leg["pose"] for leg in res["legs"]]
    assert legs == [cyc["over_pose"], cyc["target_pose"], cyc["over_pose"], cyc["capture_pose"]]
    assert res["legs"][1]["dwell_s"] == 1.0 and res["legs"][0]["dwell_s"] == 0.0
    (sent,) = [s for s in fake.primary_sends if "movel(" in s]
    assert sent.count("movel(") == 4 and "set_tcp(p[0.0, 0.0, 0.0, 0.0, 0.0, 0.0])" in sent
    # tcp reference: no override, capture/target are TCP poses
    res = link.approach_cycle((0.0, 0.0, 0.3), reference="tcp")
    assert (
        res["ok"]
        and res["cycle"]["tcp"] is None
        and res["cycle"]["capture_pose"] == res["locate"]["tcp_pose"]
    )
    assert "set_tcp(" not in [s for s in fake.primary_sends if "movel(" in s][-1]


def test_robotlink_approach_cycle_refuses_out_of_reach_and_bad_params(monkeypatch):
    fake = FakeController().install(monkeypatch)
    link = RobotLink(RobotConfig(host="fake", robot_model="UR3e"))
    # the fake's flange sits 0.5 m out, tool down; a point 1 m below it is beyond a UR3e
    res = link.approach_cycle((0.0, 0.0, 1.0), reference="flange")
    assert not res["ok"], res
    assert "out of reach" in res["error"] and res["locate"]["reachable"] is False
    assert not any("movel(" in s for s in fake.primary_sends)
    for kw in ({"clearance_m": 2.0}, {"hold_s": -1}, {"velocity": 0}, {"velocity": 5}):
        with pytest.raises(ValueError):
            link.approach_cycle((0.0, 0.0, 0.3), **kw)


def test_robotlink_locate_takes_the_controllers_ik_over_the_sphere(monkeypatch):
    # 2026-09-27: every click on the UR3e cell read OUT OF REACH against the 0.5 m
    # sphere, though the controller's own IK solved the poses. Its verdict wins now.
    fake = FakeController().install(monkeypatch)
    link = RobotLink(RobotConfig(host="fake", robot_model="UR3e"))
    asked = []
    fake.ik = lambda pose, tcp: asked.append((pose, tcp)) or True
    loc = link.locate((0.0, 0.0, 1.0), reference="flange")  # far past the sphere
    assert loc["ok"] and loc["commanded_distance_m"] > 0.5
    assert loc["reachable"] is True and loc["reach_check"] == "controller_ik"
    # the flange target is judged with the TCP forced to the flange, as it will be moved
    ((pose, tcp),) = asked
    assert pose == pytest.approx(loc["flange_target_pose"], abs=1e-5) and tcp == [0.0] * 6
    assert loc["joint_target"] == pytest.approx(pose, abs=1e-5)  # the fake "solves" to the pose

    fake.ik = lambda pose, tcp: False
    near = link.locate((0.0, 0.0, 0.05), reference="tcp")
    assert near["reachable"] is False and near["reach_check"] == "controller_ik"
    assert near["joint_target"] is None
    res = link.approach_cycle((0.0, 0.0, 0.05), reference="tcp")
    assert not res["ok"] and "inverse-kinematics" in res["error"]
    assert not any("movel(" in s for s in fake.primary_sends)

    fake.ik = None  # no answer: the sphere, and it says so
    loc = link.locate((0.0, 0.0, 1.0), reference="flange")
    assert loc["reachable"] is False and loc["reach_check"] == "sphere"


def _same_rotation(a, b, tol=1e-6):
    from urctl.pose import rotvec_to_matrix

    ma, mb = rotvec_to_matrix(a), rotvec_to_matrix(b)
    return all(abs(ma[i][j] - mb[i][j]) < tol for i in range(3) for j in range(3))


# -- the approach is by the robot's active TCP (2026-10-08: no tool length of the cockpit's) --


def test_tcp_approach_puts_the_active_tcp_standoff_short_along_the_camera_ray():
    """Tilted tool, whatever the pendant's active TCP: the approach pose is that TCP's,
    ``standoff`` short of the point along the camera's ray, orientation kept; the flange
    target is the offset behind it. ``fingertip`` is no longer a reference."""
    import random

    rng = random.Random(27)
    he = HandEye()
    for _ in range(200):
        tilt = [rng.uniform(-0.6, 0.6), math.pi + rng.uniform(-0.5, 0.5), rng.uniform(-0.6, 0.6)]
        flange = [rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), rng.uniform(0.1, 0.5), *tilt]
        offset = [rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05), rng.uniform(0.0, 0.3), 0.0, 0.0, 0.0]
        standoff = rng.uniform(0.0, 0.2)
        tcp = pose_trans(flange, offset)
        out = locate(
            he,
            flange,
            (rng.uniform(-0.1, 0.1), rng.uniform(-0.1, 0.1), rng.uniform(0.2, 0.6)),
            tcp_pose=tcp,
            tcp_offset=offset,
            standoff_m=standoff,
        )
        assert out["reference"] == "tcp" and "tip_m" not in out and "tool_tcp" not in out
        short = [p - standoff * r for p, r in zip(out["point_base_m"], out["view_ray_base"], strict=True)]
        assert _close(out["approach_pose"][:3], short, 1e-9)
        assert _same_rotation(out["approach_pose"][3:], tcp[3:])  # orientation kept
        # the flange target is where the active offset puts the flange for that TCP pose
        back = pose_trans(out["approach_pose"], pose_inv(offset))
        assert _close(out["flange_target_pose"][:3], back[:3], 1e-9)
        assert _same_rotation(out["flange_target_pose"][3:], back[3:])
        # reach is judged on the commanded pose: the TCP itself
        assert out["commanded_distance_m"] == pytest.approx(math.dist(out["approach_pose"][:3], [0, 0, 0]))
    with pytest.raises(ValueError):
        at = [0.5, 0, 0.5, *TOOL_DOWN]
        locate(he, at, (0, 0, 0.3), tcp_pose=at, reference="fingertip")


def test_the_pi_side_tool_length_is_gone():
    """2026-10-08: "You must only use tool offsets inside of the robot not your own"."""
    import perceptronics.handeye as he

    for name in ("DEFAULT_TIP_M", "ENV_TIP_M", "tip_m_from_env", "fingertip_tcp", "ENV_APPROACH_REFERENCE"):
        assert not hasattr(he, name), name
    assert he.APPROACH_REFERENCES == ("tcp", "flange") and he.DEFAULT_APPROACH_REFERENCE == "tcp"
    assert he.RETIRED_VARIABLES == ("PERCEPTRONICS_TIP_M", "PERCEPTRONICS_APPROACH_REFERENCE")


def test_robotlink_moves_and_checks_reach_with_the_controllers_tcp(monkeypatch):
    fake = FakeController().install(monkeypatch)
    monkeypatch.setenv("PERCEPTRONICS_TIP_M", "0.2")  # retired: nothing reads it
    link = RobotLink(RobotConfig(host="fake", robot_model="UR3e"))
    asked = []
    fake.ik = lambda pose, tcp: asked.append(tcp) or True
    loc = link.locate((0.0, 0.0, 0.3), standoff_m=0.04)
    assert loc["reference"] == "tcp" and loc["tcp"] is None
    assert asked == [None]  # IK on the pose that will be commanded, under the active TCP
    link.move(loc["approach_pose"])
    link.move(loc["approach_pose"], tcp=[0] * 6)  # an explicit TCP (pick-cycle's flange moves) wins
    movels = [s for s in fake.primary_sends if "movel(" in s]
    assert "set_tcp(" not in movels[0]
    assert "set_tcp(p[0.0, 0.0, 0.0, 0.0, 0.0, 0.0])" in movels[1]


def test_approach_cycle_runs_every_leg_on_the_active_tcp(monkeypatch):
    fake = FakeController().install(monkeypatch)
    fake.ik = lambda pose, tcp: True
    link = RobotLink(RobotConfig(host="fake", robot_model="UR3e"))
    res = link.approach_cycle((0.0, 0.0, 0.3), standoff_m=0.04, clearance_m=0.1)
    assert res["ok"], res
    (prog,) = [s for s in fake.primary_sends if "urctl/path/" in s]
    assert "set_tcp(" not in prog  # the pendant's TCP, as it is
    loc = res["locate"] if "locate" in res else link.locate((0.0, 0.0, 0.3), standoff_m=0.04)
    legs = [[float(v) for v in m.split(",")] for m in __import__("re").findall(r"movel\(p\[([^\]]+)\]", prog)]
    assert _close(legs[1][:3], loc["approach_pose"][:3], 1e-6)  # down: the TCP at the standoff
    assert legs[0][2] == pytest.approx(legs[1][2] + 0.1)  # over: clearance above it
    # back: where the TCP was when the picture was taken
    assert _close(legs[3][:3], loc["tcp_pose"][:3], 1e-6)


def _broadcast_flange(flange, offset, *, consistent=True):
    """What stateframe.read_flange_state returns for a controller whose flange is
    ``flange`` with ``offset`` active (``consistent=False``: it reports that offset
    while its TCP pose was computed with another)."""
    tcp = pose_trans(flange, offset if consistent else [0.0, 0.0, 0.05, 0.0, 0.0, 0.0])
    at = pose_trans(flange, offset)
    import math as _m

    return {
        "flange": list(flange),
        "tcp": tcp,
        "tcp_offset": list(offset),
        "joints": [0.0] * 6,
        "flange_source": "kinematics",
        "consistency_m": _m.dist(at[:3], tcp[:3]),
    }


@pytest.mark.state_broadcast
def test_locate_in_local_mode_needs_no_script_and_targets_polyscopes_tcp(monkeypatch):
    # 2026-09-27, the UR3e in Local: every textmsg query is ignored, so Locate failed
    # with "no TCP pose/offset surfaced". The flange now comes from the state broadcast,
    # and PolyScope's move screen gets the target in its own active TCP.
    from urctl import stateframe

    fake = FakeController().install(monkeypatch)
    flange = [0.3, -0.2, 0.35, 0.0, 3.14159265, 0.0]
    offset = [0.0, -0.035, 0.22, 0.0, 0.0, 0.0]  # the UR3e's training TCP, not the Hand-E
    monkeypatch.setattr(stateframe, "read_flange_state", lambda *a, **k: _broadcast_flange(flange, offset))
    link = RobotLink(RobotConfig(host="fake"))
    loc = link.locate((0.0, 0.0, 0.3))
    assert loc["ok"] and loc["robot"]["source"] == "state_broadcast"
    assert not any("urctl/flange" in s for s in fake.primary_sends)  # no pose script sent
    # holding PolyScope's active TCP at polyscope_pose puts the flange on the target …
    back = pose_trans(loc["polyscope_pose"], pose_inv(offset))
    assert back == pytest.approx(loc["flange_target_pose"], abs=1e-9)
    # … and that TCP — the tool as the pendant has it — where the cockpit computed the approach
    assert loc["polyscope_pose"] == pytest.approx(loc["approach_pose"], abs=1e-9)


@pytest.mark.state_broadcast
def test_locate_withholds_the_polyscope_target_when_the_offset_is_not_the_one_in_use(monkeypatch):
    from urctl import stateframe

    FakeController().install(monkeypatch)
    flange, offset = [0.3, -0.2, 0.35, 0.0, 3.14159265, 0.0], [0.0, -0.035, 0.22, 0.0, 0.0, 0.0]
    monkeypatch.setattr(
        stateframe, "read_flange_state", lambda *a, **k: _broadcast_flange(flange, offset, consistent=False)
    )
    loc = RobotLink(RobotConfig(host="fake")).locate((0.0, 0.0, 0.3))
    assert loc["ok"] and loc["polyscope_pose"] is None
    assert "disagrees" in loc["polyscope_pose_note"] and loc["robot"]["tcp_offset_consistent"] is False


# -- the pick PC keeps its hand-eye in the calibration file, never the environment -------------


def test_a_seeded_file_is_what_from_env_reads(tmp_path):
    from perceptronics.handeye import ENV_HANDEYE_FILE, HandEye, seed_calibration_file

    f = tmp_path / "cal" / "handeye.json"
    pose = [0.013337, 0.055303, 0.01286, 0.099999, -0.1637, 3.118758]
    assert seed_calibration_file(f, pose, source="cell profile") is True
    he = HandEye.from_env({ENV_HANDEYE_FILE: str(f)})
    assert he.source == f"file:{f}" and he.calibrated
    assert he.as_dict()["flange_to_depth_pose"] == pytest.approx(pose)


def test_a_calibration_already_saved_is_never_overwritten_by_a_seed(tmp_path):
    from perceptronics.handeye import seed_calibration_file

    f = tmp_path / "handeye.json"
    f.write_text(
        '{"flange_to_depth_pose": [9, 9, 9, 0, 0, 0], "source": "touch-and-click"}', encoding="utf-8"
    )
    assert seed_calibration_file(f, [0, 0, 0, 0, 0, 0], source="cell profile") is False
    assert "touch-and-click" in f.read_text(encoding="utf-8")


@pytest.mark.parametrize("pose", [[0, 0, 0], [0, 0, 0, 0, 0, float("nan")], [0, 0, 0, 0, 0, float("inf")]])
def test_a_seed_must_be_six_finite_numbers(tmp_path, pose):
    from perceptronics.handeye import seed_calibration_file

    with pytest.raises(ValueError):
        seed_calibration_file(tmp_path / "h.json", pose, source="x")
    assert not (tmp_path / "h.json").exists()


def test_why_the_environment_must_not_carry_it(tmp_path):
    # the trap the pick PC's installer avoids: an environment pose beats every saved calibration
    from perceptronics.handeye import ENV_HANDEYE_FILE, ENV_T_FLANGE_CAMERA, HandEye, seed_calibration_file

    f = tmp_path / "handeye.json"
    seed_calibration_file(f, [0.1, 0, 0, 0, 0, 0], source="a calibration on this PC")
    he = HandEye.from_env({ENV_HANDEYE_FILE: str(f), ENV_T_FLANGE_CAMERA: "[0,0,0,0,0,0]"})
    assert he.source.startswith("env:")
