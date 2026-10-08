"""The MCP servers a customer hands an agent (2026-10-06): ``--no-motion`` hides every tool
that moves the arm, actuates its I/O or runs code on it, and refuses it with a reason when
called anyway; ``--vision-only`` serves the camera + cell tools without the robot registry."""

from __future__ import annotations

import json

from perceptronics.mcp_server import COCKPIT_TOOLS, VISION_MOTION_TOOLS, build_server, main_vision
from urctl.config import RobotConfig
from urctl.mcp_server import MOTION_TOOLS, McpServer
from urctl.robot import Robot
from urctl.tools import TOOLS


def _req(method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}


def _names(server: McpServer) -> set[str]:
    return {t["name"] for t in server.handle_message(_req("tools/list"))["result"]["tools"]}


def _call(server: McpServer, name: str, args: dict | None = None) -> dict:
    res = server.handle_message(_req("tools/call", {"name": name, "arguments": args or {}}))
    assert "result" in res, res
    body = json.loads(res["result"]["content"][0]["text"])
    return {"isError": res["result"]["isError"], **body}


def test_every_motion_tool_is_a_real_tool_and_every_mover_is_listed():
    names = {t.name for t in TOOLS}
    assert MOTION_TOOLS <= names, MOTION_TOOLS - names
    # anything whose description says it moves / drives / runs on the controller is in the set
    for t in TOOLS:
        d = t.description.lower()
        moves = d.startswith(("move ", "run ", "drive ", "enable or disable freedrive", "play"))
        if moves:
            assert t.name in MOTION_TOOLS, t.name
    assert VISION_MOTION_TOOLS <= {t.name for t in COCKPIT_TOOLS}


def test_no_motion_hides_the_movers_and_refuses_them_with_a_reason():
    robot = Robot(RobotConfig(), dry_run=True)
    gated = McpServer(robot, hidden=MOTION_TOOLS)
    open_ = McpServer(robot)
    assert _names(open_) - _names(gated) == set(MOTION_TOOLS)
    assert "get_state" in _names(gated) and "list_programs" in _names(gated)
    refused = _call(gated, "move_home")
    assert refused["isError"] and "--no-motion" in refused["error"] and "move_home" in refused["error"]
    reading = _call(gated, "get_state")  # dry-run, no controller: whatever it says, it was not refused
    assert "--no-motion" not in str(reading)


def test_vision_only_serves_no_robot_tool_and_says_so():
    server = build_server(
        Robot(RobotConfig(), dry_run=True), cockpit_url="http://127.0.0.1:9", vision_only=True
    )
    names = _names(server)
    assert names == {t.name for t in COCKPIT_TOOLS}
    assert server.handle_message(_req("initialize"))["result"]["serverInfo"]["name"] == "vision"
    refused = _call(server, "get_state")
    assert refused["isError"] and "--vision-only" in refused["error"]


def test_vision_only_with_no_motion_keeps_only_the_readings():
    server = build_server(
        Robot(RobotConfig(), dry_run=True), cockpit_url="http://127.0.0.1:9", vision_only=True, no_motion=True
    )
    names = _names(server)
    assert names == {t.name for t in COCKPIT_TOOLS} - VISION_MOTION_TOOLS
    assert "cam_locate" in names and "cam_move_to_approach" not in names
    refused = _call(server, "cam_approach_cycle")
    assert refused["isError"] and "--no-motion" in refused["error"]


def test_the_vision_console_script_is_the_vision_only_flag(monkeypatch):
    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 0

    monkeypatch.setattr("perceptronics.mcp_server.main", fake_main)
    assert main_vision(["--cockpit-url", "http://192.168.3.20"]) == 0
    assert seen["argv"] == ["--vision-only", "--cockpit-url", "http://192.168.3.20"]
