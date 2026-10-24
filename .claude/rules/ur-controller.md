---
paths:
  - "urctl/**"
  - "scripts/poweron.sh"
  - "docker-compose.yml"
  - "tests/_ursim.py"
  - "tests/test_integration_ursim.py"
  - "tests/test_urctl.py"
  - "tests/test_controller.py"
  - "tests/test_stateframe.py"
  - "tests/test_harness.py"
  - "tests/test_pose.py"
  - ".claude/skills/ur-control/**"
---

# The UR controller: ports, Dashboard, Primary motion, URSim vs hardware

`CLAUDE.md` always applies. This loads when you touch the `urctl` layer, the sim compose file or the robot integration tests. The procedures (power on, jog, recover from a protective stop) are the `ur-control` skill; programs and file formats are `programs.md`; PolyScope X is `polyscope-x.md`.

## The `urctl` layer

`urctl/` is the reusable, network-target-agnostic layer: `Robot` (facade over
the Dashboard + Primary clients), a `SafetyEnvelope` (pre-execution
validation), an `AuditLog` (structured JSON action log), a JSON-schema'd tool
registry (`urctl.tools`) for agent frameworks (OpenClaw/ROSClaw, MCP, plain
function-calling), an `urctl` CLI, and the JSON-RPC loop `perceptronics-mcp` serves them through. The older
`scripts/` are kept as standalone shell/Python helpers; `scripts/urp_convert.py`
is the single source of truth for the converter (vendored into the wheel as
`urctl/_urp_convert.py`).

**Deep introspection (the harness layer, see `urctl/HARNESS.md`):** the toolkit
can read *everything* about a controller, not just live state. `urctl
rtde-state --deep` pulls the full RTDE diagnostic recipe (per-joint
currents/temps/drive modes, TCP force, supply power, tool telemetry, speed
scaling — decoded to names by `urctl/codes.py`; unsupported fields drop
gracefully). `urctl snapshot` fuses that with filesystem introspection
(`urctl/sysinfo.py` — SSH on a real robot, docker exec on URSim, auto-inferred
from the host) into one cell model: joint serials/firmware with replacement
detection, kinematic-calibration mismatch, storage health, program inventory,
installed URCaps, and the parsed active installation
(`urctl/installation.py`) — whose `flange_tcp` flag is the decision input for
the MoveJ-node-vs-script-node authoring choice below. `urctl programs` lists
what the operator can load. All three are also agent tools
(`ur_rtde_state`/`ur_system_snapshot`/`ur_list_programs`) and therefore MCP
tools.

**Portability:** the runtime — `urctl`, the GUI, and `perceptronics-mcp` (stdlib
JSON-RPC over stdio; there is no `mcp` extra) — has **zero
dependencies** and runs on Windows/macOS/Linux, amd64/arm64 (CI tests all
four). External binaries are only reached for by the *filesystem* layer and
checked with clear errors: `ssh` (real robot; ships with all three OSes) and
`docker` (URSim). CLI entry points reconfigure stdout with errors="replace" so
legacy Windows codepages never crash on unicode.

**Connection target is configurable, not hardcoded.** Nothing in `urctl/` (or
`poweron.sh`) bakes in `localhost` — they default to it for
dev but read `UR_HOST` / `UR_DASH_PORT` / `UR_PRIMARY_PORT` / `UR_TIMEOUT_S`
(and `RobotConfig.from_env(host=...)` / `--host`) so the same code drives a
real robot at an IP. The only `localhost` references that *should* stay are the
docker-compose healthcheck and the CI startup probe — those run *inside the
container / on the runner*, where `localhost` is correct.

## Network surface of a UR controller

All ports are bound to localhost by docker-compose. On real hardware they
are unauthenticated; treat the robot's network like a backplane.

| Port  | Name              | Direction | What it's for                                                          |
| ----- | ----------------- | --------- | ---------------------------------------------------------------------- |
| 29999 | Dashboard server  | bi        | Line-oriented ASCII. The "press buttons in PolyScope" surface.         |
| 30001 | Primary Client    | bi        | 10 Hz state broadcast **and** accepts raw URScript that runs immediately. |
| 30002 | Secondary Client  | read      | Read-only mirror of Primary's broadcast for external monitors.         |
| 30003 | RT Interface      | read      | 125/500 Hz state — legacy hard-realtime consumers (pre-RTDE).          |
| 30004 | RTDE              | bi        | Subscription protocol: client picks fields + cadence. Modern drivers.  |
| 30020 | Interpreter mode  | bi        | URScript REPL that runs **inside an already-loaded program**.          |
| 502   | Modbus TCP        | bi        | Field I/O. Needs `NET_BIND_SERVICE` to bind (handled in compose).      |
| 22    | SSH (real robots) | bi        | Debian sshd on the controller. The **only** way to drop files in `/programs/` on a real e-Series (no Dashboard upload, no SMB/NFS by default). Not exposed by URSim — use `docker cp` instead. |

The key distinction: **Dashboard is for orchestration** (load program,
power on, query state). **Primary 30001 is for execution** (write URScript,
it runs). Most beginner confusion stems from trying to play a program via
Primary or write URScript via Dashboard.

### Dashboard cheat sheet

```
power on          power off          brake release
robotmode         safetymode         programState         running
load <prog>.urp   play               stop                 pause
unlock protective stop                close safety popup
popup <text>      addToLog <text>
```

`load <name>.urp` requires the matching `<installation>.installation` file
in the same directory — PolyScope refuses to load a program whose
installation isn't found. Error text in that case is the cryptic
`Error while loading program: ...:unknown failure`; the real cause shows
up in `/ursim/polyscope.log` as `Failed to load installation: null.installation`.

### Talking to Dashboard from shell

```bash
printf 'robotmode\nquit\n' | nc -q1 localhost 29999
```

The server replies one line per command and only after it has fully
executed. Pipelining requires either `sleep` between writes or a tool that
waits for replies (the test suite wraps this in `dash()` and `wait_for()`).

## Executing motion over Primary 30001 (the part that bit hard)

Getting a Cartesian move to actually run cost real time; here is the verified
mental model. `urctl.Robot.move_tcp` / `move_joints` encode all of it — prefer
them over hand-rolled URScript.

- **Wrap motion in a `def`.** URControl treats each newline-terminated
  top-level statement as its own program and kills the previous one. So a raw
  multi-line `target = ...` / `movel(target)` splits into two programs and the
  second runs with `target` undefined. Send motion as a single
  `def f(): … end\n f()` (what `urctl` does) — or, for a one-liner, fold it
  into one self-contained statement: `movel(pose_add(get_actual_tcp_pose(),
  p[0,0.05,0,0,0,0]), a=0.3, v=0.1)`.
- **Fire-and-forget is racy.** Writing motion and immediately closing the
  Primary socket (`transport.send`) sometimes lands and sometimes doesn't —
  the controller may not have latched the program before the FIN. Observed
  both outcomes for the *same* bare `movel`. The reliable pattern is to **hold
  the socket open until the move confirms**: run the body, `sync()`, then
  `textmsg("urctl/move/done=", get_actual_tcp_pose())`, and read the broadcast
  until that marker appears. `move_tcp`/`move_joints` do this and return as
  soon as the marker lands (see `transport.send_and_collect(stop_marker=...)`)
  — so they're both reliable *and* fast (don't block the full timeout).
- **Local vs Remote control does NOT gate Primary URScript.** Motion sent to
  30001 runs whether PolyScope is in Local or Remote mode (verified: a
  def-wrapped `movel` moved the robot with `is in remote control` → `false`).
  Only the **Dashboard `play` command** requires Remote mode. Don't add a
  remote-control precondition to motion — it would reject moves that work.
- **Absolute moves are reach-checked by the controller's own IK.** Before an
  absolute `move_tcp` / `move_tcp_path`, `Robot.inverse_kin` asks the controller
  (`get_inverse_kin_has_solution` + `get_inverse_kin`, one Primary program, same
  `tcp=` as the move; no motion, so it answers in Local on e-Series). Its verdict
  replaces the datasheet sphere both ways: a no is an `ik_reach` violation (nothing
  sent), a yes passes a pose the sphere would reject. The sphere — sized by
  `SafetyEnvelope.for_model` (UR3e 0.5 m, UR20 1.75 m, unknown → UR10 1.3 m;
  `UR_MAX_REACH_M` overrides) from the **base origin** — is only the fallback when
  the controller gives no answer (dry-run, Primary busy, PolyScope X in Local). On
  the UR3e cell (2026-09-27, parts 0.27 m below the base) it rejected reachable
  targets — flanges 0.505–0.533 m out that the controller solves — and a sphere
  cannot see an in-radius pose the arm can't reach either. `locate` reports `reachable`, `reach_check` (`controller_ik`/`sphere`) and
  the controller's `joint_target`; check `reachable` before offering a Move.
- **One program at a time.** A new submission on 30001 replaces whatever is
  running. `Robot.move_tcp_path` runs a whole multi-leg Cartesian path
  (over → down → dwell → up → back) as one program on one connection, and
  `PrimaryClient` refuses a concurrent submission (`PrimaryBusyError`) so a
  state poll or a Locate can't kill it. `tcp=` on `move_tcp`/`move_tcp_path`
  runs `set_tcp` in the same program (`[0]*6` = the flange).
- **Relative moves are base-frame.** `move_tcp(..., relative=True)` adds the
  delta to the live TCP via `pose_add(get_actual_tcp_pose(), p[...])`, so the
  XYZ delta is in the **base** frame (use `pose_trans` if you ever want the
  tool frame). The safety envelope caps a single relative step (default 1.0 m)
  to catch unit mistakes (inches/mm entered as metres).

## Cartesian moves and singularities (`movel` protective stops, C154A0)

A `movel` from a **near-singular pose protective-stops the robot** (controller
error `C154A0`), even for a tiny step — the inverse kinematics blows up joint
velocities at the singularity. Two poses bite constantly:

- **URSim's default startup pose** (TCP straight up at z≈1.48 m — fully
  extended).
- **`HOME_JOINTS` = `[0, -90, 0, -90, 0, 0]`** — elbow joint = 0 ⇒ the upper
  arm and forearm are colinear ⇒ **elbow singularity**. `move_home` lands here,
  so "home then nudge in Cartesian" is exactly the trap.

`movej` is immune (it interpolates in joint space), so the fix is to **`movej`
to a dexterous, elbow-bent pose before any `movel`**. The integration tests use
`READY_JOINTS = [0, -1.0, 1.2, -1.8, -1.5708, 0]` for this (see
`tests/test_integration_ursim.py::_running_robot`).

Diagnosing it: a waited `move_tcp`/`move_joints` that hits this returns
`ok=False, landed=null` and `result.protective_stop=true` (the facade
checks `safetymode` when a move fails to confirm). The raw reason is in the
container's URControl log, not `polyscope.log`:

```bash
sudo docker exec perceptronics-ursim-1 grep -i 'protective\|C154' /ursim/URControl.log | tail
```

**`robot_mode` stays `RUNNING` through a protective stop** — only `safety_mode`
flips to `PROTECTIVE_STOP`. So any "is the robot ready?" check that looks at
`robot_mode` alone is wrong; check `safety_mode` too, and `bring_up()` clears a
latched protective stop (it calls `unlock protective stop`). A test/helper that
gates recovery on `robot_mode` will let one protective stop cascade into every
later motion test.

## How fast can you actually drive it (control throughput)

Measured on the emulated sim, a single **confirmed** move (`move_tcp` /
`move_joints`, `wait=True`) has a fixed floor of **~1–1.5 s** regardless of the
move distance/velocity. It breaks down as:

- **~0.5 s** — the safety pre-check does one Dashboard `robotmode` round-trip
  (connect → send → read-until-close). This is per move.
- **~0.7 s** — the Primary broadcast round-trip: send the program, then wait for
  the `urctl/move/done=` `textmsg` to surface in the ~10 Hz state stream.
- plus the actual motion time.

Two hard limits when you try to go faster by firing moves back-to-back:

- **Rapid per-move reconnects wedge the controller.** Each `move_*` opens a
  fresh Primary (30001) socket. After **~10** rapid connect/run/disconnect
  cycles URControl's Primary interface chokes (`Socket::OperatorOverload` /
  `MultiTCPSender sendall failed` in `URControl.log`) and the robot can drop to
  **POWER_OFF**. `bring_up()` recovers it (Dashboard still works); the Primary
  broadcast itself only fully recovers on a container restart.
- **The safety envelope caps joint speed at ~2.09 rad/s** (`120°/s`,
  `DEFAULT_MAX_JOINT_SPEED`) and TCP speed at 1.0 m/s. A move above the cap is
  rejected up front (`ok=False` with a `velocity` violation, nothing sent) — it
  looks like an instant failure but it's the envelope doing its job. Keep test
  velocities ≤ ~2.0 rad/s.

**To move a lot, stream a trajectory, don't loop single moves.**
`Robot.move_trajectory(waypoints, ...)` (tool `ur_move_trajectory`) sends a whole
joint-space path as one `def` over a single connection: it pays the handshake
**once**, never reconnects mid-path, validates every waypoint up front, and can
`blend_radius`-smooth segments (dropped on the last waypoint — a blend on the
final `movej` errors; see the movej blend-radius pitfall in ur-program-authoring).
This is both faster and the only way that doesn't risk wedging the controller.

## Driving a real e-Series (vs URSim): which path to use

Three divergences between URSim and a physical e-Series cost real time (first met on a UR10,
the cell today is the UR3e — `SETUP.md`); none reproduce on URSim. The decision tree:

| You want to…                                            | URSim                                         | Real e-Series                                                                                   |
| ------------------------------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Read state, send `popup`/`addToLog`/`load`/`stop`        | Always works                                  | Always works (Dashboard does not need Remote)                                                   |
| Move via Primary URScript (`move-joints`, `move-tcp`, `move_trajectory`, `run-script` with motion) | Works in Local — verified                     | **Requires Remote control mode.** In Local, `urctl move-*` and `ur_move_trajectory` silently return `ok:false`, `landed:null`, with **no** safety violation. `run-script` of a textmsg-only script still returns `ok:true` and executes, so it's the motion specifically that is gated. There is no network endpoint to switch Local→Remote — flip the indicator in the top-right corner of the pendant. |
| Play a loaded `.urp` via Dashboard `play`               | Requires Remote                               | Requires Remote                                                                                  |
| Drop a `.urp` (or `.installation`) in `/programs/`       | `docker cp` into the URSim container          | **SCP over SSH** (port 22). `/programs` is the PolyScope-visible path. `default.installation` typically already exists, so no installation upload is needed when `urp_builder`'s default matches. |
| Build a `.urp` of native Move/Waypoint nodes (`UrpProgram.movej(Waypoint(...))`) | Plays cleanly — `kinematicsFlags="4"` + `positionType="CartesianPose"` with the zero kinematics envelope satisfies URSim's IK | **Fails with "Robot cannot reach the required pose"** at runtime if the customer's active tool has a non-zero TCP offset. PolyScope's MoveJ does FK→IK through the **active TCP**, and a long gripper (the installations on this robot have offsets up to ~0.15 m on `tcpOffset`) puts the IK target outside reach for joint configurations that raw URScript `movej(joints)` accepts. URScript's `movej(joints,...)` does NOT do this round-trip — it just runs the joints. So a `.urp` whose motion comes from a `<Script>` node calling `movej` is the reliable path. Switching `kinematicsFlags` to `"6"` (what PolyScope itself emits) alone does **not** fix it. |

The first two divergences are gates (state polling and orchestration are
fine in Local; motion isn't). The third is structural: the same `.urp`
that loads and runs on URSim can stall on a real robot if the customer's
active tool has a non-zero TCP offset, even though the joint targets are
reachable. **Programs you author for a real-robot cell should emit motion
as `script_file`/`script_line` nodes**, not native `MoveJ`/`Waypoint`
nodes. Native nodes are still right for URSim, demos, and any cell whose
active TCP is at the flange — but you can't tell from the `.urp` alone
which side of that line you're on.

### File placement on a real robot

```bash
export SSHPASS='<password>'                       # do not pass -p (visible in ps)
sshpass -e scp tests/fixtures/programs/ElegantDance/ElegantDance.urp root@<robot-ip>:/programs/ElegantDance.urp
python3 -m urctl --host <robot-ip> load ElegantDance
python3 -m urctl --host <robot-ip> play
```

Verified: real e-Series ships Debian + sshd on `:22`, root login enabled,
`/programs/` writable. Pre-existing `/programs/default.installation` pairs
with `UrpProgram(..., installation="default")` (the builder default). Long
term, `ssh-copy-id root@<ip>` and drop `sshpass`. There is no Dashboard
upload command and no SMB/NFS exposed — SSH is the only file-placement
path.

The authoring side of the third divergence — motion as `script_file` / `script_line` nodes — is in `programs.md` §Build motion programs with script nodes.

## Common gotchas (robot side; the cockpit's are in `cockpit.md`, the URP ones in `programs.md`)

| Symptom | Cause | Fix |
| --- | --- | --- |
| PolyScope shows "No Controller"               | URControl crashed at boot — usually `socket() ENOSYS`        | `security_opt: [seccomp:unconfined]` in compose     |
| Modbus refuses to start                       | Port 502 needs root                                          | `cap_add: [NET_BIND_SERVICE]` in compose            |
| Dashboard `play` returns `Failed to execute`  | PolyScope is in Local control mode                           | Toggle Local→Remote in PolyScope's top-right corner |
| Robot state polling sees no IDLE              | URSim is fast — POWER_OFF→RUNNING in one tick                | Accept `IDLE\|RUNNING` from `wait_for`              |
| Robot powers off after `load <name>.urp`      | Fresh `<name>.installation` triggers PolyScope's safety re-eval | `power on` + `brake release` after load (E2E driver handles this) |
| URScript `def foo(): … end; foo()` over Primary logs `Compile error: name 'foo' is not defined` | PolyScope auto-wraps inbound Primary URScript; the inner `def` is in a nested scope | Body executes anyway — the error is cosmetic. Use the wrap; raw multi-line statements break worse (each line becomes its own program). |
| `urctl run-script 'movel(...)'` returns `ok:true` but the robot doesn't move | Bare top-level motion is split into its own program and/or the Primary socket closes before the controller latches it (racy) | Use `urctl move-tcp` / `move-joints` (reliable, confirmed). `run-script` def-wraps by default; `--raw` opts out. See "Executing motion over Primary". |
| `move-tcp` returns `ok:false`, `landed:null`, `protective_stop:true`; every later move also fails | A `movel` tripped a protective stop (singularity / C154A0), and `robot_mode` stays `RUNNING` so naive "ready?" checks miss it | `movej` to a dexterous pose before `movel`; `bring_up()` (or `unlock protective stop`) to clear the latch. See "Cartesian moves and singularities". |
| RTDE / Secondary / RT reads refused on `:30004`/`:30002`/`:30003` | The container was created from an older `ports:` list | `docker-compose.yml` publishes `30002-30004`, `30020`, `502`; recreate the container (`docker compose up -d`) after editing it |
| Moves start failing fast (`ok:false`, no `protective_stop`) and the robot ends `POWER_OFF` after a burst of moves | ~10+ rapid per-move Primary reconnects wedged URControl (`Socket::OperatorOverload`) | Don't loop single moves — use `move_trajectory` (one connection). `bring_up()` to recover. See "How fast can you actually drive it". |
| A move returns `ok:false` instantly with a `velocity`/`tcp_velocity` violation | Speed exceeds the safety envelope cap (joints ~2.09 rad/s, TCP 1.0 m/s) | Lower the velocity, or raise the cap on a custom `SafetyEnvelope` if you really mean it |
| **On a real e-Series**, `urctl move-joints` / `move-tcp` / `ur_move_trajectory` returns `ok:false`, `landed:null`, **no safety violation** and joints don't change. `urctl run-script 'textmsg(...)'` still returns `ok:true` from the same robot | Robot is in **Local** control mode. Real e-Series gates Primary URScript *motion* (not state, not textmsg, not Dashboard) on Remote. URSim doesn't, so this only bites on hardware. | Flip the top-right pendant indicator Local→Remote (no network endpoint exists). Add a precondition: read `urctl state`, refuse motion unless `control_mode == "REMOTE"`. See "Driving a real e-Series". |
| PolyScope GUI (noVNC on :6080) stuck on "Please wait…" | Cosmetic — the Java/AWT front-end is slow under emulation; the controller and all network interfaces (Dashboard/Primary/RTDE) are fine | Ignore it; the headless `urctl` path doesn't use the GUI. Confirm with `urctl state` (RUNNING/NORMAL). `docker compose restart ursim` only if you actually need the GUI |
| `docker ps` shows the container `(unhealthy)` but everything works | A healthcheck that shells out to `nc` always fails — `nc` **isn't installed in the URSim image**; the committed check uses `python3` (present in the image) | Benign — verify the controller with `urctl state`; keep the healthcheck on `python3` |
| `make sim-up` fails with `port 5900 … address already in use` on a Mac | macOS **Screen Sharing** serves VNC on 5900 (`nc localhost 5900` answers `RFB …`) | Use noVNC on 6080 instead; publish the container's 5900 elsewhere (`15900:5900`) or turn Screen Sharing off. Compose < 2.24 has no `!override` for `ports:`, so edit the mapping or `docker run` the service |
| URSim container is `Up` but 29999 refuses / resets and `docker logs` shows `Trace/breakpoint trap   Xvfb` | Docker Desktop is emulating amd64 with **Rosetta**; Xvfb crashes under it, PolyScope (which serves the Dashboard) never starts, and URControl stops listening within minutes. Mac Studio | **Docker Desktop's emulators can't run the e-Series sim on the Mac Studio**: with Rosetta off (QEMU user-mode) Xvfb survives but URControl dies. The image is amd64-only (every tag). `scripts/ursim-e-vm.sh up` runs it in a full x86_64 QEMU VM instead: URControl, Dashboard, Primary/RTDE and the URCap loader work (8 min to Dashboard), but PolyScope's JVM crashes in JIT code there (SIGILL/SIGSEGV, `hs_err_pid*.log`) — fine for "does the URCap load", not for clicking through PolyScope. For that: an amd64 host, CI, or the real UR3e |
| **On a real e-Series**, `move-tcp` / cockpit **Move** to a target the arm can't reach returns `ok:false`, `landed:null`, no violation — and the arm **stretches to a straight elbow** chasing it (UR3e, 2026-09-23: a 0.69 m target on a 0.5 m arm) | The envelope's reach cap was not sized for the arm (a UR10's 1.3 m on a UR3e) | `SafetyEnvelope.for_model` sizes `max_reach` from `UR_ROBOT_MODEL` (the cell files) or the Dashboard's `get robot model` (probed once before the first absolute move); `MODEL_REACH_M` covers UR3/5/7e/10/12e/15/16e/20/30. `locate` returns `reachable` and the cockpit's event says **OUT OF REACH** before you press Move. `UR_MAX_REACH_M` overrides (long TCP). Doctor line `robot.model` shows the cap and flags a cell/controller model mismatch. |
| A multi-leg move (`ur_move_tcp_path`, the cockpit **Approach** cycle) stops part-way with `ok:false`, no protective stop, robot parked mid-path | **Any new URScript on 30001 replaces the running program.** A concurrent state poll whose RTDE read hiccuped (legacy `textmsg` fallback), a Locate (`get_flange_pose` is a script), or a second Move kills the cycle silently. Seen once on the UR3e 2026-09-23 (4-leg cycle died after leg 2) | Inside one process: `PrimaryClient` holds a non-blocking in-flight lock — a concurrent submission raises `PrimaryBusyError`, and `get_state` reports `primary_busy` with no joints instead of sending. Across *processes* (a CLI `run-script` while the cockpit drives) nothing can protect you — don't. |
| `ur_flange_pose` / Locate gives a flange pose that is wrong by tens of mm while `get_tcp_offset()` looks plausible | The controller reported an active-TCP offset (`0,-0.035,0.22,…`) that was **not** what its motion actually used; `pose_trans(tcp, inv(offset))` then puts the "flange" in the wrong place | Force the TCP yourself: `set_tcp(p[0,0,0,0,0,0])` (persists until the next `set_tcp`/installation load) — then TCP == flange and every read/move agrees. `move_tcp(..., tcp=[0]*6)` / `--tcp` puts it in the same program as the `movel`; the flange-referenced cycle does this on every leg. |
| Robotiq gripper: port 63352 is closed from the network although the URCap is installed | the URCap daemon binds the controller's loopback only | `urctl gripper status\|open\|close\|move --position N` / `ur_gripper` / `POST /api/robot/gripper` — one Primary program opens the socket from inside the controller (UR3e + Hand-E, 2026-09-25) |
| Cockpit **Freedrive** (or `urctl freedrive on`, `ur_freedrive`) reports ok but the real arm stays stiff; the reteach/inspect dialogs *do* hand-guide | Freedrive lives only while the program that called `freedrive_mode()` runs. A one-line script ends instantly → freedrive ends instantly (URSim is lenient, hardware isn't) | `Robot.freedrive(True, hold_s=600)` sends a bounded `sleep` loop that keeps the program alive and confirms via `textmsg("urctl/freedrive=on")` (`ok:false` if the echo never comes); `off` sends `end_freedrive_mode()` as a new program, which also kills the hold; the hold releases itself when it expires (`--hold`, tool `hold_s`, max 1 h). |
