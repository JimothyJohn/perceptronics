---
paths:
  - "perceptronics/**"
  - "scripts/cockpit.sh"
  - "tests/test_perceptronics*.py"
  - "tests/test_realsense*.py"
  - "tests/test_pick*.py"
  - "tests/test_handeye.py"
  - "tests/test_posestream.py"
  - "tests/test_calibrate.py"
  - "tests/test_orbitcal.py"
  - "tests/test_segment.py"
  - "tests/test_rgbd.py"
  - "tests/test_doctor.py"
  - "tests/test_cell.py"
  - "tests/test_cockpit_mcp.py"
  - "tests/test_wizard.py"
  - "tests/test_armfk.py"
  - "tests/test_armik.py"
  - "tests/test_backends_sam.py"
---

# The RGB-D cockpit: RealSense, cells, hand-eye, picking from the page, the tool offset

`CLAUDE.md` always applies. This loads when you touch the `perceptronics` package. The user-facing notes are `perceptronics/README.md`, the architecture is `perceptronics/ARCHITECTURE.md`, the detector is `detection.md`, the pick PC that ships it is `pick-pc.md`, the URCaps that call it are `urcap.md`.

**RealSense RGB-D (`perceptronics rs-info` / `gui`, see
`perceptronics/README.md`):** `perceptronics/realsense.py` binds librealsense's C API
with ctypes (no `pyrealsense2`; zero deps kept), streams colour + depth aligned
to colour (both sensors at the D435's native 848×480 — **mismatched sizes give
black colour frames** — through the SDK's spatial + temporal filter chain,
sensor on the High Density preset at full laser (High Accuracy left holes in dark part tops, 2026-10-03); `perceptronics/README.md` §Depth
quality; `--no-depth-filters` / `--rs-preset none` for raw), and the cockpit (`perceptronics/webapp.py` + `perceptronics/webui/`) does
hover-to-measure, click-to-segment (`perceptronics/segment.py`: colour+depth
region growing, or SAM via the `sam` extra), snapshots (`POST /api/snapshot`), and a **Robot** panel that sends the segment's point to
the arm: `ur_flange_pose` (new tool) + the bracket-nominal hand-eye seed
(`perceptronics/handeye.py`, override with `PERCEPTRONICS_T_FLANGE_CAMERA`) give a
base-frame point and an approach pose; **Move** is one `ur_move_tcp` through the
same tool registry (`perceptronics/robotlink.py`; `perceptronics/README.md` §Sending a
point to the robot). `urctl/pose.py` is the stdlib pose math (`pose_trans` /
`pose_inv` semantics). **macOS needs `sudo`** to open the camera (libusb
must detach Apple's UVC driver — `failed to set power state` otherwise); Linux
needs the udev rules. `--fake` runs everything on a synthetic scene. The
shipped compute is the pick PC (`deploy/pi/`); the GPU line (an RGB camera + a Jetson) is `JETSON.md`. The camera mounts on the tool flange via
`hardware/d435-tool-bracket/` (parametric CadQuery, STL/STEP, spec in its
README; nominal `T_flange_camera` seed in §3).

**The pilot's seat (cells, doctor, Pilot panel, MCP keys; `perceptronics/README.md`
§The pilot's seat, presentation in `perceptronics/cell.html`):** a *cell*
(`perceptronics/cells/{sim,ur3,ur20}.env`, `--cell` / `UR_CELL`) is the one-word
selector for robot host/platform/ports + bracket print (`PERCEPTRONICS_BRACKET`
→ `handeye.BRACKET_SEEDS`; the UR20 print is clocked 45°, so its seed differs).
`perceptronics doctor` is the pre-flight (SDK, camera, per-port reachability with
platform-mismatch diagnosis, modes, TCP offset, hand-eye status; every failure
carries its fix; also `GET /api/doctor` and the `cell_doctor` tool). The cockpit
has a Pilot panel (bring-up/stop/freedrive, capped jog pad, events log) and
`POST /api/snapshot` writes PNGs an agent can read. **Hand-eye calibration**
is touch-and-click (`perceptronics/calibrate.py`; cockpit "Calibrate hand-eye",
`cal_*` tools): record the mark with the tool tip, 4–6 clicked views from
varied wrist poses, LM solve seeded from the bracket, Apply + save to
`captures/calibration/handeye_<cell>.json` (env > file > seed). **Mark-less:**
`perceptronics calibrate` orbits the block under the camera (3 ranges × 13 views,
found by identity, trimmed) and clicks every view into the cockpit's session;
`--apply` saves it (`perceptronics/orbitcal.py`, `perceptronics/README.md` §Hand-eye
without a mark; unverified on hardware as of 2026-09-26). `perceptronics-mcp` (`.mcp.json`)
serves robot + `cam_*`/`cell_*` tools; the camera tools proxy the running
cockpit because one process owns the USB camera. **Keep
`perceptronics/cell.html` current** — it is the demo/explainer and has a dated
field log; append to it when something is verified or changes.

**Pick cycle (`perceptronics pick-cycle`, `perceptronics/pickcycle.py`):** the
heuristic, model-free routine — survey white blocks from one or more overlook
poses (`--survey-pose x y z rx ry rz`, repeatable, merged by position; the camera
must be ≥ 0.25 m from the parts, the D435 has no depth closer than ~0.2 m), fit
each top face as the nearest 3-D plane, then per block: yaw the fingers across
the short side, hover with the **fingertips** 40 mm over the top, descend to the
edge and 15 mm further, close, lift an inch, set it back, release; `--drop` adds a
pass that lets each block go from 120 mm up. A close on nothing opens and moves
on; a protective stop unlocks, lifts and moves on. It is a client of the running
cockpit (HTTP, like the MCP tools) and falls back to `urctl gripper` when the
cockpit predates the gripper route. `--record DIR` saves the three feeds + the
captioned events. Hand-E as mounted: the fingers
travel along flange **Y**; a yaw about the tool Z (pointing down) is the negative
of the base-heading yaw — `grasp_yaw_deg` handles it and a composed-pose test
locks it. First runs 2026-09-25 on the UR3e + Hand-E.

**The table is flat and parallel to base XY (Nick, 2026-09-27).** Only its height
and the parts' heights vary. The UR3e stands on a ~12 in pedestal (parts ~0.27 m below
the base) and the Hand-E adds 163 mm. `pick-cycle` grasps straight down
(`grasp_rotation`), leans 12°/24° outward only when the controller's IK can't solve the
vertical path, and skips a block no lean solves.

**The live pose in every frame (`perceptronics/posestream.py`, 2026-09-27).** The cockpit
streams RTDE `actual_TCP_pose` + `tcp_offset` at 30 Hz; flange = tcp ∘ offset⁻¹ (identical
to the `get_flange_pose` script on the UR3e, no Primary program, works in Local). Each
`/api/rgbd` header carries `flange_pose`, `pose_age_s`, `flange_to_color_pose`; `GET
/api/robot/pose`. The page (`webui/index.html`) is a ship's-computer UI around the wrist
feed (hover to measure, click or drag to segment, the log and the prompt beside it); the
RANGE SCAN point cloud, its object cards and `POST /api/objects` were removed 2026-10-08
(Nick: "never made sense"). `/classic` is the old page (calibration lives there). Needs a
cockpit restart to pick up server changes; the page itself is read from disk per request.

**A lost link is named on the page (2026-09-30, Nick: "obvious to the user", "hotswapped without a
reboot or refresh").** The cockpit page (`webui/index.html`, `health()`) raises one alarm strip under
the header — COCKPIT NOT ANSWERING, CAMERA STOPPED · PICTURE IS n S OLD, ROBOT NOT ANSWERING, PENDANT
SWITCHED TO LOCAL — each with the fix and the fact that it reconnects by itself; the feed and scan dim
while their picture is old. All four clear without a refresh (the loops keep retrying; the camera pump
re-opens with back-off; a restarted cockpit is noticed by `uptime_s` going backwards and the page's
counters reset). The one case that needs F5 says so: a restart that serves a *different* page. A robot
that never answered this session (practice mode) is lamps + log only, not an alarm. Server side,
`fps()` decays to 0 when frames stop and `/api/info` carries `frame_age_s` / `stalled` (the doctor's
`stream` check uses them) — before, a dropped D435 kept reading ~30 fps. `/classic` has no strip.
Checked headless (kill + restart the cockpit, stop + restart the pump); not on the cell.

**Pick from the cockpit (`POST /api/robot/pick`, `perceptronics/pickplan.py`, 2026-09-27).**
Nick's spec: the gripper comes in straight down the base Z axis, wrist 3 across the
object's short side, the jaws pre-opened to their full 50 mm stroke (a 1.2x opening caught a
block's edge), fingertips 25 mm over its top.
Two programs: a blended sweep from the picture pose (`PERCEPTRONICS_HOME_POSE`; FANCY adds a
swing and a wrist flourish) to a **close look** — the object on the colour camera's axis at
0.24 m, just outside the D435's blind zone — then the object is re-found there and the
final program (over → approach [→ grasp → lift with PICK]) is built from that measurement.
Every pose goes to the controller's IK first. The look is **tilted 10°** (`LOOK_TILT_DEG`; the camera looks out at the part from the base side) and the re-find casts the detector's pixels onto the top plane, so the tilt doesn't bias it. A pick can name a stored object instead of the clicked mask (`target: {centre, theta, major_m, minor_m}` — the page sends it for a selected card), and `survey: true` stops after the close look and returns the fresh measurement; in the page, right-click a card or a part → APPROACH / PICK / SURVEY. The Robotiq pre-open rides the sweep program (`move_tcp_path(gripper_first=POS)`: set before the first `movel`, not waited for). The page's LEVEL lamp is the fitted floor's
tilt in the base frame: the table is flat, so any tilt is calibration error. The arm's
linkage comes from RTDE `actual_q` through `perceptronics/armfk.py` (UR3e DH verified 0.84 mm
against the controller's flange; other models guarded by the same check).

**Hand-eye drifts.** A two-day-old solve has placed blocks 2–5 cm off, view-dependently (a tilted
survey and a vertical look disagreed by 26–28 mm; both grasps missed). Re-run `perceptronics calibrate`
before trusting a pick after anything on the wrist moves (`SETUP.md` §1 has the current solve).

**The tool offset is the robot's, only (Nick, 2026-10-08: "You must only use tool offsets
inside of the robot not your own").** The cockpit, the pick server and both URCaps carry **no tool length**: the tool is the
controller's **active TCP** as the operator set it on the pendant (Installation → General → TCP).
A cockpit approach puts that TCP `PERCEPTRONICS_STANDOFF_M` short of the clicked point along the
camera's ray (`locate(reference="tcp")`, the default; `flange` stays for the calibration and
explicit callers), every cockpit move and reach check runs with the active TCP as it is
(`RobotLink.reference_tcp` → `None`), and the Pounce node's script never calls `set_tcp`: it
sends its pose under the active TCP plus the offset (`tcp=p[…]`, pick-server **protocol 3**,
`PROTOCOL = 3`) and the server answers poses of that TCP frame — the TCP on the part, Z straight
down, fingers along the frame's Y — which the node reaches with `movej(get_inverse_kin(pose))`.
A node before 0.10.0 (it zeroed the TCP and expected flange poses for a 163 mm tool) is answered
**-14** "update the Perceptronic URCap"; a cockpit before 0.10.0 answers the new node -9. The
retired `PERCEPTRONICS_TIP_M` / `PERCEPTRONICS_APPROACH_REFERENCE` are ignored and named by the
cell loader and `perceptronics doctor`'s `approach` line, which now says what the active TCP is
and warns when it is the flange (right with nothing fitted, a crash with a gripper on). On the
UR3e the pendant must therefore hold the Hand-E's 0.163 m as the active TCP, not the old 223 mm
training offset. `pick-cycle` (the legacy routine) takes its tip length from the active offset's
Z. A pick-area touch records the active TCP's pose (`RobotPositionCallback2`'s pose on
PolyScope 5, `convertJointPositionsToTcpPose` on PolyScope X).

**Quiet while the program runs (0.10.1 / 0.8.1, Nick 2026-10-08: "disable errors while it's not
actually in a measurement feedback state").** As the arm comes down the camera is inside its own
range and every frame judged in between is wrong. `PickPlanner` tracks the program's run (its first
request or `LOG start` → `LOG at the grip` / `LOG no pick`, or `RUN_TTL_S` = 90 s of silence) and
remembers what the program measured last (`last_measurement`, from `_find2` / `_refine2`); while it
runs, `scene_report` answers `{quiet: true, last: …}` and judges no frame, both nodes draw the last
measurement with no banner and say *program running*. The cockpit keeps **one** `PickPlanner`
(`pick_planner()` is cached) so the socket and the teach-screen routes share that state.
Cell files also note where the work surface is relative to the base (UR3e: parts ~0.27 m
below it) — that height, not the datasheet radius, is what decides reach.

**One GUI.** The RGB-D cockpit (`perceptronics gui`) is the only web UI — `urctl` has none. Its
Pilot panel covers bring-up / jog / stop / freedrive through the same tool registry.

**Demo view (`perceptronics gui --demo`, `/?demo=1`, header **Demo** button):** the
RGB-D cockpit reduced to the picture, four big buttons (Start robot → Find
object → Pick, STOP), one status light and one instruction line; **Developer
view** toggles back. Same page, same API — `body.demo` CSS hides the rest, the
buttons call the existing bring-up / nearest / approach-cycle / stop actions.

## Common gotchas (cockpit and camera side)

| Symptom | Cause | Fix |
| --- | --- | --- |
| Every cockpit click on the UR3e cell reads **OUT OF REACH** although the arm reaches the parts | The reach check was the datasheet radius (0.5 m) from the base **origin**; the parts sit 0.27 m below the base | `locate` and every absolute move ask the controller's IK (`reach_check: controller_ik`); the sphere is only the no-answer fallback. If you still see `reach_check: sphere`, Primary isn't answering (PolyScope X in Local, Primary disabled) |
| A cockpit Move with the Hand-E on drives the fingers into the part | The standoff was measured from the **flange** (75 mm) — the fingertips are 163 mm past it | Since 0.10.0 the tool is the **pendant's active TCP** (earlier cockpits forced their own 163 mm fingertip TCP) — set the gripper's TCP there; `perceptronics doctor`'s `approach` line shows the active offset and warns when it is the flange |
| The cockpit runs the **old hand-eye** although `perceptronics/cells/ur3.env` has the new solve (`/api/info` → `robot.handeye.flange_to_depth_pose` ≠ the cell file's value) | `apply_cell` only fills keys the environment doesn't already have, so a `PERCEPTRONICS_T_FLANGE_CAMERA` already in the cockpit's environment wins. `handeye.source` reads `env:…` either way, so it can't tell you which one won | Launch with `sudo env -u PERCEPTRONICS_T_FLANGE_CAMERA python3 -m perceptronics --cell ur3 gui …`; after every launch compare `flange_to_depth_pose` in `/api/info` with the cell file |
| RealSense colour panel black, depth fine, RGB options at factory | depth and colour streaming at **different sizes** on the D435 | keep both at 848×480 (the default); `perceptronics/README.md` §Depth quality |
| Cockpit shows nothing on a **USB 2** link; log says `Couldn't resolve requests` then `RS2_USB_STATUS_ACCESS` on every retry | USB 2 lists **no 848×480 colour** (and 848×480 depth only at 10/6 Hz), so the default pair can't start; each failed open re-runs the macOS UVC race | `open()` enumerates the camera's profiles (`Api.stream_modes`) and `negotiate_mode` picks the fastest same-size pair it offers (640×480 @ 15 on the D435) — no flags needed; re-plug once to clear the race. `perceptronics/README.md` §Troubleshooting |
| RealSense open fails on the Mac with `RS2_USB_STATUS_ACCESS` / `set_xu … timed out` / no frame, and the process **segfaults** after `usb device disconnected` | The Mac is a desktop now: libusb's claim re-enumerates the device and every camera-aware app (Spotify won it on 2026-09-24; browsers; Apple's UVCAssistant) races for it; a disconnect mid-open crashes librealsense 2.58.4 in libusb | Don't chase it. On this Mac every libusb handle open resets the camera (root-only kernel-driver detach = re-enumerate with capture) and Apple's `UVCAssistant` re-claims it each time: 43 resets in 40 s and a stream that dies after 2 frames, with nothing else on the bus (2026-09-25, webcams and Spotify gone). The Mac-as-desktop is not a D435 host — the pick PC (`deploy/pi/`) is; on the Mac run the cockpit under `--rs-lean` from a local Terminal with `sudo` (`SETUP.md` §2). `perceptronics/README.md` §Troubleshooting |
| RealSense first open of a process never delivers a frame, re-opens work | sensor options written between pipeline start and the first frameset | write them on the first `read()` (`DepthTuning` does); never at open |
| The cockpit's flange-referenced approach lands a constant ~35 mm off the object, even with the TCP forced to zero | The hand-measured `PERCEPTRONICS_T_FLANGE_CAMERA` (to the camera housing) was 21 mm off in X, 36 mm in Z and had the tilt sign inverted — the depth origin is the **left IR imager**, not the housing centre | Run the touch-and-click hand-eye (mark = flange centre on the part with `set_tcp(p[0,…])`, 3 clicked views from varied wrist poses); 2026-09-23 on the UR3e: RMS 1.7 mm, located point 3 mm from the mark afterwards. The solved pose is in `perceptronics/cells/ur3.env` + `captures/calibration/handeye_ur3.json`. |
