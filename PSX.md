# PSX.md — an e-Series arm on a PolyScope X controller

The test plan for the PolyScope X path: a UR e-Series arm (UR3e … UR20, UR30) whose controller
runs **PolyScope X** (PolyScope 10), the **Perceptronic** URCap for it (`integrations/urcap/
perceptronic/`, `.urcapx`), and the pick PC with the D435 on the wrist. `ROBOT.md` is the same day
for the PolyScope 5 pendant; this file lists only what PolyScope X changes and what was verified
in the simulator on 2026-10-06, so the first real session knows what to expect and what to write
down. Reference: `integrations/urcap/README.md` (the node, screen by screen), `DEVELOPING.md`
(the SDK, the worker protocol), `SETUP.md` §3 (the sims on the Mac).

## What PolyScope X changes

| | PolyScope 5 (ROBOT.md) | PolyScope X |
| --- | --- | --- |
| Install the URCap | USB stick, Settings → System → URCaps → + | **System Manager** (☰ → System Manager → URCaps → +, the `.urcapx`) or `integrations/urcap/urcapx.py install FILE --host <robot> --replace` (the same urservice endpoint, no Remote needed). Nothing runs from a stick. |
| Orchestration | Dashboard :29999 | the REST **Robot-API** on :80 (`UR_PLATFORM=polyscopex`, `UR_ROBOT_API_PORT=80`); every mutating call is 403 unless the robot is in **Remote** |
| Primary / RTDE | always on | **off by default**: Settings → Security → Services → Primary Client interface + RTDE on (admin password), then Lock and Close |
| Local / Remote | the top-right pendant indicator | Safety Overview (the icon top right) → Operational mode **Automatic** (password) → Control mode **Remote**. **Automatic hides the Application and Program tabs**: node editing and teaching happen in Manual, cockpit-driven moves over Primary in Automatic + Remote |
| Where the node lives | Installation → URCaps → Perceptronic; Program → URCaps → 3D Pick | **Application** → URCaps → Perceptronic (the camera, pick areas); **Program** → + → 3D Pick: a one-line row, its screen is the **Teach & options…** dialog |
| The node's cockpit address | the Cockpit field on the Installation node | the Cockpit field on the Application node; the program node reads it from there (its row says *set the camera computer's address in Application → Perceptronic* until it can) |
| Moving to a located point | Move (PolyScope) = `RobotMovement.requestUserToMoveRobot` | Move (PolyScope) = PolyScope's IK + the **hold-to-move** screen (needs a hand on the pendant); Move (cockpit) = the cockpit over Primary (Remote) |
| The program node's script | runs in Local, no Primary | the same URScript, run by ▶ in Manual or Automatic; FIND / NEXT go to the cockpit's pick server (:7622) **from the controller**, so the cockpit's address must be one the controller reaches (on a sim in Docker that is the host's LAN address, not `localhost`) |
| The node's page and CORS | not a web page | the node is a web page served by the controller: the cockpit must be started with `--cors http://<controller>` (`PERCEPTRONICS_CORS` in the pick PC's `cell.env`), or the page reports *running, but not set up to serve this robot's screen* |

## Phase 0 — the day before

1. Pick PC on dev or newer (PR #67 for the portal; the banner PR for 0.7.1): `scripts/deploy-pi.sh nick@<pi>`.
2. `cell.env` on the pick PC for a PolyScope X cell: `UR_PLATFORM=polyscopex`, `UR_ROBOT_API_PORT=80`,
   `UR_PRIMARY_PORT=30001`, `UR_RTDE_PORT=30004`, `UR_ROBOT_MODEL=<model>`,
   `PERCEPTRONICS_BRACKET`, and **`PERCEPTRONICS_CORS=http://<robot address>`** (the origin of the
   pendant's page; add `:80` only if the controller's page says so). The UR20 cell (`cells/ur20.env`)
   is the stub to fill.
3. The `.urcapx` (`integrations/urcap/dist/perceptronic-<ver>.urcapx`) on the stick for System
   Manager, or the laptop on the robot's network for `urcapx.py install`.
4. `perceptronics doctor` from the pick PC: `robot.reach` (Robot-API) ok in Local; `robot.primary` and
   `robot.rtde` only after the Services are on; `robot.control: LOCAL` is the expected fail.

## Phase 1 — cables, Services, modes (Nick at the pendant, 15 min)

Cables as in ROBOT.md phase 1. Then on the pendant: Services on (Primary + RTDE); arm powered and
brakes released (the Initialize screen); stay in **Manual / Local** for everything until a move
over the network is wanted.

**Check (Claude):** `perceptronics doctor` on the pick PC reads `robot.primary` and `robot.rtde`
open; the cockpit's `GET /api/robot/pose` follows the arm when it is jogged.

## Phase 2 — the URCap (Nick, 10 min)

Install it (System Manager or `urcapx.py`). Reload the page. **Application → URCaps →
Perceptronic**: the Cockpit field (empty = `192.168.3.20`) and the live picture; **Save**. Note
for the next version: the tile under URCaps shows UR's generic icon, not the P mark (seen in the
sim, 2026-10-06).

**Check:** the picture at 30 fps; hover reads a depth; a click on a part gives *target located —
choose how to move* with the base point, the fingertip pose and the controller's IK verdict
(*reachable* / *OUT OF REACH*).

## Phase 3 — the first move (both, 15 min)

Speed slider ≤ 30 %, a hand near the e-stop. With the click's target on the Application node:

- **Move (PolyScope)** in Manual: PolyScope's hold-to-move screen; Nick holds, the arm goes to
  the approach pose (the robot's active TCP `PERCEPTRONICS_STANDOFF_M` short of the point along the camera's ray).
- **Move (cockpit)**: Automatic + Remote first (the node's page disappears; the request can still
  be sent from the pick PC: `POST /api/robot/move` with the pose the page showed). Verified in
  the UR10e sim 2026-10-06 with the real D435 on the bench: located 1.18 m from the base, moved,
  landed on the IK's joints.

**Check:** `GET /api/robot/pose` on the pick PC equals the approach pose; no protective stop.

## Phase 4 — the 3D Pick node (both, 30 min)

Manual. **Program → + → 3D Pick**. The row shows the part size and picture count; **Teach &
options…** opens the dialog: the live picture with the parts found (green, numbered) and the
near misses (yellow, with why), the **Picture points** grid (**+** = the arm's joints now; **Go**,
**Here**), the **pick order** tiles, **Options** (Part / Approach tabs), **Check approach**.

1. **Part size first** — the row's default (110 × 50 × 30) is not your part. On 2026-10-06 the
   bench boxes were 110 × 70 × 30 and the default made every one a near miss ("too wide", "too
   tall", "2 parts touching?"). The banner across the picture (0.7.1) names the size entered, the
   first near miss's measured size with why, and the camera computer's notes.
2. Jog the arm to a picture pose ≥ 0.3 m over the parts, open the dialog, **+**: *picture point 1
   taught at joints […]*. The picture should show the parts green within a second.
3. If the picture is right but the parts come out "too tall" with a *surface reads rough* note: the
   camera's tilt disagrees with what the robot says (hand-eye, or a pose that is not the camera's).
   Since the off-level fix the parts are still found and the note says *the table reads N° off
   level in the robot's frame*; their positions are off by as much → re-run `perceptronics
   calibrate` (ROBOT.md phase 4) before any pick.
4. **Done**, then ▶ with the program *Gripper open → 3D Pick → Gripper close → If rs_pick_found*
   (the PolyScope X gripper nodes of the gripper you have). The script: movej to the picture point
   → FIND (the controller talks to the pick server :7622) → the closer look → REFINE → over →
   approach → grip. Every stage is a `textmsg` and a `LOG` line in the cockpit's pick log.

**Check:** one part picked by the program; the second from the queue (NEXT) with no trip to the
picture point; a part out of reach yellow with *out of reach (no joint solution)*.

## Phase 5 — what to write down

`SETUP.md` §1 (the cell: model, address, Services on, which modes were used), the dated line in
`integrations/urcap/README.md` §Tested, `TODO.md`'s PolyScope X section (the Robotiq-on-PolyScope-X
question, the backend-container packaging), the field log in `perceptronics/cell.html`, and the
`ur-utils-polyscopex-urcap` memory.

## Verified in the simulator, 2026-10-06 (`SETUP.md` §3 for the sims)

UR10e sim (`ROBOT_TYPE=UR10`, 10.13.0) with the Pi's cockpit and the real D435 on the bench as the
camera, hand-eye from the file, the sim as the robot: URCap installed through the urservice
endpoint; Services toggled on; Application node live at 30 fps through `http://192.168.3.20`
(port 80); click → located → reachable → `POST /api/robot/move` landed; **3D Pick** node: part size
110 × 70 × 30, picture point 1 taught from the arm's joints, four boxes green and numbered once the
sim's wrist was tilted 19° to match the camera on the bench (the off-level note now covers the
untilted case). Not run: ▶ (needs the controller to reach the Mac's cockpit — it does, through
`host.docker.internal`, but the node's address was the Pi's; next time point the node at an
address both the browser and the controller reach), Move (PolyScope) (hold-to-move), a gripper.
