# MCP.md — the two servers an agent talks to

Two [MCP](https://modelcontextprotocol.io) servers ship with the toolkit, for Claude Desktop,
Claude Code, Cursor or any MCP client. Both are plain Python with no dependencies: they run
from a checkout of this repository (or after `pip install .`) on Windows, macOS or Linux.

| Server | What it gives the agent | Talks to |
| --- | --- | --- |
| **`urctl-mcp`** — the robot | the controller's state, programs, the tool centre point, positions and workplanes; with motion on: moves, the gripper, URScript | the robot's controller directly (Dashboard, Primary, RTDE; the Robot-API on PolyScope X) |
| **`perceptronics-vision-mcp`** — the 3D vision guidance | what the camera sees, a snapshot to look at, find the object under a pixel or the nearest one, its place in the robot's frame and the approach pose above it, the pre-flight doctor, the hand-eye calibration steps | the running **camera computer** (the pick PC at `http://192.168.3.20`, or a cockpit started with `perceptronics up`) — never the controller itself |

`perceptronics-mcp` is both in one process (the robot tools plus the vision tools), for a cell
you operate yourself.

## Safe by default: `--no-motion`

Nothing moves the arm unless you say so. Start either server with **`--no-motion`** and every
tool that moves the arm, actuates its I/O or runs code on the controller is left out of the
tool list and refused with a reason if called anyway. What remains is the readings, finding and
locating parts, and the planning: enough for an agent to tell you what it would do; a person
then does it at the pendant or starts the server without the flag. The tables below mark the
tools that `--no-motion` hides.

## One line in the client's config

**Claude Desktop** (`claude_desktop_config.json`) and **Cursor** (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "robot":  {"command": "urctl-mcp", "args": ["--host", "192.168.3.3", "--no-motion"]},
    "vision": {"command": "perceptronics-vision-mcp", "args": ["--cockpit-url", "http://192.168.3.20", "--no-motion"]}
  }
}
```

**Claude Code** (`.mcp.json` in the project; this repository's own points at `perceptronics-mcp`):

```json
{
  "mcpServers": {
    "robot":  {"command": "python3", "args": ["-m", "urctl.mcp_server", "--host", "192.168.3.3", "--no-motion"]},
    "vision": {"command": "python3", "args": ["-m", "perceptronics.mcp_server", "--vision-only", "--cockpit-url", "http://192.168.3.20", "--no-motion"]}
  }
}
```

Without `pip install .` the console scripts do not exist: use the `python3 -m …` form from the
checkout, as the second example does. `--host` is the robot's address (the pendant's Network
screen); `--cockpit-url` is the camera computer. Drop `--no-motion` when the agent may move the
arm; add `--dry-run` to `urctl-mcp` to have every robot call validated and logged but not sent.

## The tools

Generated from the registries (`tests/test_mcp_doc.py` holds this file to them); the first line
of each tool's description. **moves** = hidden by `--no-motion`.

### `urctl-mcp` — the robot

<!-- tools:robot -->
| Tool | What it does | |
| --- | --- | --- |
| `get_state` | Read the robot's current state: robot mode, safety mode, program state, and (when RUNNING)… |  |
| `flange_pose` | Read the tool-flange pose in the base frame (plus the active TCP pose and TCP offset it… |  |
| `bring_up` | Bring the controller from a cold start to RUNNING: clear latched safety, power on motors,… |  |
| `power_off` | Power off the robot's motors. |  |
| `move_joints` | Move to a joint-space target with movej. Validated against the safety envelope (joint… | moves |
| `move_tcp` | Move the tool linearly with movel. Set relative=true for a base-frame delta added to the… | moves |
| `move_tcp_path` | Run several absolute movel legs as ONE program on one connection (an approach cycle: over →… | moves |
| `move_trajectory` | Run a joint-space trajectory: a sequence of movej waypoints streamed as ONE program over a… | moves |
| `move_home` | Move to the safe candle home pose (straight up, wrists folded). | moves |
| `freedrive` | Enable or disable freedrive (hand-guiding) on all six axes. Enabling holds freedrive for… | moves |
| `gripper` | Drive the Robotiq gripper (Hand-E / 2F) on the tool flange through its URCap daemon:… | moves |
| `popup` | Show a popup message on the PolyScope teach pendant. |  |
| `load_program` | Load a PolyScope program (<name>.urp) on the controller. A matching <name>.installation… |  |
| `play` | Play (start) the currently loaded program. | moves |
| `stop` | Stop the running program. |  |
| `pause` | Pause the running program. |  |
| `run_script` | ADVANCED: run arbitrary URScript on the Primary client. Bypasses the joint/speed safety… | moves |
| `dashboard_command` | ADVANCED: send a raw Dashboard command (e.g. 'robotmode'). Audited; unvalidated. Escape… | moves |
| `rtde_state` | Read high-rate structured state via RTDE (port 30004): joint angles and velocities, TCP… |  |
| `system_snapshot` | Full cell model of the controller: live state + deep RTDE telemetry plus filesystem-level… |  |
| `list_programs` | List the .urp / .script / .installation files on the controller (name, size, mtime) — what… |  |
| `set_speed_override` | Set the global speed slider (0-1) over RTDE. Scales the speed of ALL subsequent motion.… |  |
| `set_digital_output` | Set a standard digital output pin (0-7) high or low over RTDE. | moves |
| `tcp_offset` | Read or write the tool centre point, on any arm (UR e-Series, PolyScope X, UFACTORY). get:… |  |
| `position` | Named robot positions in the cell store, on any arm. save: the current joints + TCP pose… | moves |
| `workplane` | Workplanes (the table) from three touched points, on any arm. touch: record the live TCP… |  |
<!-- /tools:robot -->

### `perceptronics-vision-mcp` — the camera and the 3D guidance

<!-- tools:vision -->
| Tool | What it does | |
| --- | --- | --- |
| `cam_info` | What the cockpit's camera is doing: kind (realsense/synthetic), device serial/firmware/USB… |  |
| `cam_snapshot` | Write the latest RGB-D frame as viewable PNGs (<name>_color.png and a colourised… |  |
| `cam_segment` | Segment the object under pixel (x, y) and/or inside a box on the latest frame. Returns the… |  |
| `cam_nearest` | Segment the nearest object (RealSenseTrainer's closest-thing rule). near_ratio (1, 3]… |  |
| `cam_clear` | Drop the active segment. |  |
| `cam_locate` | Map the active segment's camera point (or an explicit point_m) into the robot base frame… |  |
| `cam_move_to_approach` | movel the TCP to an absolute base-frame pose — normally the approach_pose cam_locate just… | moves |
| `cam_approach_cycle` | The test loop: over the current segment at clearance_m, down to the standoff (cell default;… | moves |
| `cam_events` | The cockpit's event log after sequence number `after`: robot actions (jog/move/bring-up… |  |
| `cell_doctor` | Pre-flight checklist for the cell: camera stream health, robot reachability… |  |
| `cell_workplane_check` | Compare a workplane from the cell store (the table touched off at three points with the… |  |
| `cal_status` | Hand-eye calibration session: the touched mark (base frame), the recorded views, the solve… |  |
| `cal_record_mark` | Step 1 of touch-and-click calibration: with the tool tip resting ON the mark, record the… |  |
| `cal_add_view` | Step 2: from a new pose where the camera sees the mark, add a view: the camera-frame point… |  |
| `cal_solve` | Step 3: solve T_flange_camera from the mark + views (Levenberg-Marquardt, seeded from the… |  |
| `cal_apply` | Use the solved transform from now on and (save=true) write… |  |
| `cal_reset` | Drop the mark and all views. |  |
| `cell_jog` | One relative base-frame nudge of the TCP: delta [dx, dy, dz, drx, dry, drz] (metres,… | moves |
<!-- /tools:vision -->

## What a customer's agent can do with the vision server alone

Read the camera (`cam_info`), take a picture it can look at (`cam_snapshot`), point at a part
(`cam_segment` with a pixel, or `cam_nearest`) and ask where it is in the robot's frame and
where the gripper should go (`cam_locate`: the base-frame point, the approach pose, whether the
arm reaches it by the controller's own inverse kinematics), check the cell (`cell_doctor`), and
read what happened (`cam_events`). All of it through the camera computer, which is on the
robot's network and already knows the robot; the agent never holds a controller connection.

## Protocol notes

stdio transport, one JSON-RPC 2.0 message per line; `initialize`, `ping`, `tools/list`,
`tools/call`; tool errors come back in-band (`isError`) so the model can read and correct them;
an unreachable controller is an in-band error too, with the address. Protocol on stdout,
diagnostics on stderr. The details are in `urctl/mcp_server.py`.
