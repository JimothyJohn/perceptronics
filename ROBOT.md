# ROBOT.md — the day the UR3e is plugged in

The plan for the first session with the **UR3e + Hand-E + Pi pick PC** connected (the cell in
`SETUP.md` §1; the robot has been unplugged since 2026-09-29). Everything below has run against
simulators, the Pi, or the UR3e *before* the Pi existed; nothing in the robot ↔ Pi path has been
seen on hardware. The job is to get a pick working **and to write down what differs**.

Two people: **Nick at the pendant** (every UI step, every Remote/Local flip, the e-stop) and
**Claude over SSH** on the Mac Studio (`192.168.3.10` on the cell switch, `10.0.0.16` on the
office LAN; the Pi at `nick@10.0.0.56` on Wi-Fi and `192.168.3.20` on the cell). Each phase ends
with a check that must be true before the next one; a phase that fails twice stops the session
for a write-up, not a third try. Budget: about 2 hours for phases 0–5, the rest as time allows.

The same arm on a PolyScope X controller: `PSX.md`. Generic version for a customer's PolyScope 5
robot: `site/public/quickstart-ur.html`. The Pi on
this cell, cable by cable: `deploy/pi/PLUG-AND-PLAY.md`. Reference and gotchas: `CLAUDE.md`.

## What is true before the day

| | Value | Set by |
| --- | --- | --- |
| Robot | UR3e, PolyScope 5.25.1, static `192.168.3.3` (checked 2026-09-27) | pendant, Settings → System → Network |
| Pi pick PC | `192.168.3.20/24` on eth0, no gateway; cockpit :7621 (+ :80), pick server :7622; cell DHCP armed (hands a robot on DHCP `192.168.3.3`) | `deploy/pi/install.sh` |
| Mac Studio | `192.168.3.10` on `en0` (manual), the dev shell | `networksetup -setmanual "Ethernet" 192.168.3.10 255.255.255.0` |
| Tool | Hand-E through the bracket's 6 mm adapter: fingertips 0.163 m past the flange (`PERCEPTRONICS_TIP_M`); the controller's active TCP is a 223 mm training offset the cockpit never uses | `perceptronics/cells/ur3.env` → `/etc/perceptronics/cell.env` on the Pi |
| Camera | D435 on the `eseries` bracket print, clocked 180° (camera opposite the tool connector), on a **blue** USB 3 port of the Pi, short cable, no hub | `hardware/d435-tool-bracket/` |
| Hand-eye | the 2026-09-27 solve (RMS 2.5 mm) in `/var/lib/perceptronics/captures/calibration/handeye.json` on the Pi | `install.sh handeye_out_of_env` |
| Picture pose | 0.37 m up, looking down in front of the stand (`PERCEPTRONICS_HOME_POSE`) | Nick, 2026-09-27 |
| Parts | white foam blocks on the table, ~0.27 m below the base; the table is flat and parallel to base XY | — |
| URCap | **Perceptronic 0.9.0** (`io.advin.perceptronic`, `integrations/urcap/dist/perceptronic-ps5-0.9.0.urcap`) — never on a pendant; the pendant still has **RealSense Pilot 0.2.0** | `scripts/urcap5-usb.sh` makes the stick |
| Pi software | PR #67's branch or newer (`deploy-pi.sh` fixed, port 80, rollback restores deploy files, setup portal verified 2026-10-06) | `scripts/deploy-pi.sh nick@10.0.0.56` |

## Phase 0 — the day before (Claude, 30 min, no robot)

1. Merge or deploy **PR #67** to the Pi: `PYTHON=/opt/homebrew/bin/python3 scripts/deploy-pi.sh nick@10.0.0.56`.
   Then `scripts/deploy-pi.sh nick@10.0.0.56 --doctor-only`: `sdk`, `camera usb 3.x`,
   `cockpit ~30 fps`, `network: this machine is 192.168.3.20 on 192.168.3.0/24` ok; `robot.*`
   fail (unplugged) — expected.
2. **The stick**: `scripts/urcap5-usb.sh` ("URE MODELS"). It writes
   `perceptronic-ps5-0.9.0.urcap` + `urmagic_perceptronic.sh` and ejects. Keep the magic file
   for phase 2B; the by-hand install comes first.
3. **Fresh frames of the real scene are the arbiter** (`CLAUDE.md` §Detection): clear
   `captures/` on the Mac of root-owned leftovers (`sudo chown -R nick captures` from a local
   Terminal) so snapshots can be written.
4. Read `TODO.md` §*Needs the cell* once more and bring the open list below to the cell.
5. Confirm the Mac's `en0` is `192.168.3.10` and pings the Pi: `ping -c1 192.168.3.20`.

## Phase 1 — cables and power (Nick, 10 min)

Order doesn't matter; give the Pi a minute. Pi Ethernet → the cell switch (where the UR3e and
the Mac's `.10` are). D435 USB 3 → a blue port. 27 W supply. Robot on, arm **powered off**,
pendant in **Local**.

**Check (Claude):**

    ssh nick@10.0.0.56 'ip -br addr show eth0; ping -c2 192.168.3.3'
    scripts/deploy-pi.sh nick@10.0.0.56 --doctor-only

Want: `robot.reach` (Dashboard :29999), `robot.primary` (:30001) and `robot.rtde` (:30004) open
from the Pi — **the first time the Pi has ever reached the robot.** `robot.control: LOCAL` is
fine (state only). `robot.model` must say UR3e both from the cell file and the Dashboard.

If `robot.reach` fails: the pendant's Network screen (Settings → System → Network) — is it
`192.168.3.3 / 255.255.255.0` on the port the switch is on? If it says *Disabled network* or
another subnet: **DHCP → Apply**; the Pi hands it `192.168.3.3`
(`ssh nick@10.0.0.56 journalctl -u perceptronics-cell-dhcp -n 20` says whether it served or
stood down because another DHCP server answered). That lease path has **never served a real
robot** — note what happens either way.

## Phase 2 — the URCap on the pendant (Nick, 20 min)

**2A, by hand (always works):** ☰ → Settings → System → URCaps: select **RealSense Pilot**, **–**,
restart. Then **+** → the stick → `perceptronic-ps5-0.9.0.urcap` → Open → Restart.
(Pictures: `integrations/urcap/perceptronic-ps5/README.md` §Install on the robot.)

**Check:** Installation tab → URCaps → **Perceptronic**. The Cockpit field reads `192.168.3.20`
(empty = that address) and the live picture appears within seconds. ☰ → **Save Installation**.
The **P** button in the header drops the live picture over any screen. Note:

- does everything fit the screen with nothing clipped (the layout test assumes ≥ 1000 × 560)?
- the P button's icon size (30 px) and the drop-down's height (420 px) are guesses — too big,
  too small?
- the watermark bottom-right of the picture.

**2B, the magic file (own test, after 2A works):** Settings → Security → General → **Run magic
files** on, arm powered off, stick in: the robot installs 0.9.0 by itself and restarts. Its
log is `urmagic_perceptronic.log` on the stick. Never run on a robot; a failure here is a
finding, not a blocker (2A is the fallback).

If the picture never comes: the URCap names the cause first (*No answer from the camera
computer at 192.168.3.20* → cable/power/robot subnet; *A computer answers … but not the camera
program* → `ssh nick@10.0.0.56 systemctl status perceptronics-cockpit`; *camera gives no
picture* → blue port, 27 W, re-plug). From the Mac the same picture is at
`http://192.168.3.20/` (port 80 or :7621).

## Phase 3 — safety and the first moves (both, 20 min)

Nothing in phases 0–2 moves the arm. Before the first move:

1. Pendant **speed slider ≤ 30 %**. Nick's hand near the e-stop for every move in phases 3–5.
2. Clear the table except two white blocks, well inside reach and away from the pedestal edge.
3. Pendant to **Remote** (top-right indicator). On a real e-Series, Primary URScript motion runs
   only in Remote; state and Dashboard don't care. There is no network way to flip it.
4. From the Mac, bring the arm up and read it:

       python3 -m urctl --host 192.168.3.3 bring-up
       python3 -m urctl --host 192.168.3.3 state          # RUNNING / NORMAL, control_mode REMOTE

5. **First motion, joint space, small:** the picture pose, via the cockpit so the TCP is the
   fingertips (`RobotLink.reference_tcp`):

       curl -s -X POST http://192.168.3.20/api/robot/home     # or the cockpit's Pilot panel: Home

   Watch the arm. If it drives toward a straight elbow, STOP: the reach cap or the model is wrong
   (`robot.model` in the doctor; `UR_ROBOT_MODEL=UR3e` in `/etc/perceptronics/cell.env`).

**Check:** `GET http://192.168.3.20/api/robot/pose` moves with the arm; the cockpit page's scan
view (`http://192.168.3.20/`) shows the point cloud in the base frame under the arm's linkage,
and the **LEVEL** lamp reads the fitted floor's tilt. Over ~0.5° → phase 4 before any pick.

**The detector's own verdict, from the picture pose** (Claude, 2 min): with the blocks in view,

    curl -s "http://192.168.3.20/api/pick/scene?opts=$(python3 -c 'import urllib.parse;print(urllib.parse.quote(" part=110x70x30 tol=25 order=LR,FB gripcheck=1 room=20 arm=UR3e proto=2"))')"

(the part size of the blocks on the table — measure them with a rule first; the foam blocks of
the 09-27 picks were ~60 × 40 × 30). Read, in this order:

| Field | Want | If not |
| --- | --- | --- |
| `surface.source` / `surface.tilt_deg` | `fitted`, < 1° | > 1°: the hand-eye is out (phase 4); a note *the table reads N° off level in the robot's frame* means the camera is nowhere near where the robot says it is: the bracket, the cell's `PERCEPTRONICS_T_FLANGE_CAMERA` override, or the wrong cell file |
| `notes` | empty | *surface reads rough (±N mm)*: carpet or a textured table — parts under 3.5× that spread are invisible; move the picture pose closer. *almost no depth*: sunlight on the table or a black surface |
| `parts` | every block, `size_mm` within ±max(5 mm, 1.2 % of range) of the rule, `height_mm` likewise | `rejected` with `why`: *too wide / too tall / too flat* = the size entered is wrong (the node's banner says the same on the pendant); *cut off by the edge of the picture*: move the pose; *2 parts touching?*: separate them |
| `status` | 1 | −7 with every block in `rejected`: the size; −4: the camera dropped (re-plug) |

Save the frame while you are at it (`POST /api/snapshot`, and `GET /api/rgbd` → the fixture format
in `tests/fixtures/d435/`): a real-cell frame of known parts is the detector's arbiter.

Protective stop at any point: `python3 -m urctl --host 192.168.3.3 bring-up` clears it
(`robot_mode` stays RUNNING through one; only `safety_mode` says so). Singularity (`C154A0`)
after a `movel`: `movej` to a bent-elbow pose first; the cockpit's programs do.

## Phase 4 — hand-eye (Claude, 10 min; only if needed)

Re-solve if anything on the wrist moved since 2026-09-27, if LEVEL > 0.5°, or if phase 5's
first approach lands visibly off. One block under the camera, arm at the picture pose, Remote:

    ssh nick@10.0.0.56 sudo -u perceptronics /opt/perceptronics/current/bin/perceptronics \
        --cell /etc/perceptronics/cell.env calibrate --cockpit http://127.0.0.1:7621 --apply

Orbits the block (3 ranges × 13 views, a few minutes), applies and saves to the hand-eye file —
it survives reboots and redeploys. Want: RMS ≤ 3 mm, LEVEL < 0.5° afterwards. The orbit has
run on the UR3e from the Mac (2026-09-25/27, RMS 2.5–4.4 mm) but **never from the Pi**.

## Phase 5 — a pick from the cockpit, then from the pendant (both, 40 min)

**5A, the cockpit's pick (the path that worked on 2026-09-27 from the Mac):** on
`http://192.168.3.20/` right-click a block → **SURVEY** (sweep to the close look, re-find,
return the measurement — no grasp). Compare its size with the block (±max(5 mm, 1.2 % of range)
is the D435's limit; worse means calibration). Then → **APPROACH**: the gripper comes straight
down the base Z, wrist across the short side, fingertips 25 mm over the top. Then **PICK** with
the Hand-E open first (`urctl gripper open`), lift, set down.

**5B, the pendant's program (never run on a robot — the point of the day):** pendant back to
**Local** (the node runs in the robot's own program; Primary is not used). Program tab:

    Gripper: open          ← Robotiq's node
    3D Pick                ← URCaps → 3D Pick
    Gripper: close         ← Robotiq's node
    If rs_pick_found       ← lift 100 mm, set down, open

In the 3D Pick node, in this order (each a screen on the pendant to look at, nothing clipped,
nothing scrolling — note anything that is):

1. **Part tab: the size first.** The node's default (110 × 50 × 30) is not your part — on 2026-10-06
   it turned 110 × 70 × 30 boxes into "too wide / too tall / 2 parts touching?" and nothing green.
   Box, the rule's L × W × H, tolerance 25 %. Since 0.9.1 the picture carries a **banner** when
   nothing will be picked: the size entered, the first near miss's measured size with why, and the
   camera computer's notes. The banner must agree with the curl above.
2. **Approach tab:** Finger room 20 mm, Closer look on, grip across the short side.
3. **Picture point.** Jog the arm to the picture pose (≥ 0.3 m over the parts; the cell's
   `PERCEPTRONICS_HOME_POSE` is right) and tap **+**: *picture point 1 taught at joints […]*. The
   picture shows the parts **green with their pick order** within a second, near misses **yellow
   with why**. Tap a part to teach its size from the picture (0.9.0) and compare with the rule.
4. **Pick area** (Installation node): three fingertip touches on the table, then check the parts
   fall inside it on the node's picture and the LEVEL lamp agrees with the taught plane
   (`surface_check.tilt_deg` in the curl above, < 1°).
5. ▶.

Watch for, in order (each is a `textmsg` and a `LOG` line in the Pi's
`captures/pick-server.log` / `GET /api/pick/log`): FIND from the picture point → the closer look
(0.30 m, part 12° off-axis on the side away from the gripper — is the part clear of the
fingers? toggle the node's picture to Depth to see their hole) → REFINE → over → approach →
grip, fingertips at grip depth, and the node ends with the gripper **open** (it drives no
gripper). Then Robotiq closes, `rs_pick_found` is true, the lift runs.

**Then the variations** (`TODO.md` 2026-10-01): parts 20 mm apart picked, closer ones yellow;
**Grip across the long side** turns the wrist 90°; Closer look off → every part measured from
the picture point; a part out of reach → yellow "out of reach"; close on nothing → the popup
names it.

**Check:** one block picked and set down by the program, no protective stop, the popup never
raised; a second block picked from the queue (NEXT) without a trip to the picture point.

## Phase 6 — the failure drills (both, 20 min; TODO.md 2026-09-30)

With the cockpit page open on the Mac, do each once and note what the page and the routine
did; each should raise the alarm strip with the fix and clear by itself:

1. Pendant to **Local** mid-cockpit-move → PENDANT SWITCHED TO LOCAL.
2. D435 **unplugged** mid-run → CAMERA STOPPED · PICTURE IS n S OLD; re-plug → clears, and a
   looping 3D Pick stops answering −4 and resumes (not a hang).
3. `ssh nick@10.0.0.56 sudo systemctl restart perceptronics-cockpit` while the program is on a
   block → COCKPIT NOT ANSWERING; the program's popup names it.
4. Robot **power cut** → ROBOT NOT ANSWERING; power back → reconnects without a refresh.

Also the setup portal's step 10 if the fresh card is ready: a card flashed from image #3,
booted on the cell, `http://192.168.3.20/setup` with no SSH at all.

## Phase 7 — write it down (Claude, 20 min)

- `SETUP.md` §1 and §2: "first run with the Pi on the cell <date>", what the lease path did,
  URCap 0.9.0 on the pendant, the Remote/Local observations.
- `deploy/pi/PLUG-AND-PLAY.md` §*Not verified yet*: strike what was seen; dated line.
- `perceptronics/cell.html` field log: one dated entry per phase.
- `TODO.md`: close the 2026-09-25 … 2026-10-01 cell entries that were answered; new ones for
  what was found.
- `deploy/pi/README.md` *Open items*: the first row ("The real UR3e from the Pi") and the
  sustained-run row.
- Memory: the `perceptronics-pi5-pickpc` and `ur-utils-pilots-seat` entries.
- Snapshots (`POST /api/snapshot` at the picture point and at the closer look) into
  `tests/fixtures/d435/` if they show something the synthetic scene doesn't — the detector's
  arbiter is real frames. Label them like `boxes_on_carpet_0p8m_oblique.json` (what, part_mm,
  count, pixels, flange_pose, flange_to_color_pose) so `tests/test_volume.py` can hold the
  detector to them.
- The table below, filled in.

| Phase | Date | Result |
| --- | --- | --- |
| 1 cables | 2026-10-08 | The Pi reached the UR3e the first time (Dashboard, Primary, RTDE); the robot was already static 192.168.3.3, the lease path untested. The Air drove it from 192.168.3.10 (Claude on the Air, not the Studio). |
| 2 URCap | 2026-10-08 | 0.9.1 installed from the stick by hand, feed up within seconds, Cockpit field empty. Notes: picture bounces after a tap; no highlight on the Installation tab; "Go" / "Here" read as one phrase; picture letterboxed to a third of its frame. |
| 3 first move + detector verdict | 2026-10-08 | Home from the cockpit fine. The table is at base height now (no pedestal). Detector: foam block tops return 10-60 % depth (holes) → 1-2 of 4 found until the colour fusion (below). |
| 4 hand-eye | 2026-10-08 | Orbit from the Air, three solves (RMS 3.1-3.9 mm); applied the first (10 views); LEVEL 1.2-2.3° depending on the side of the base — not the 0.5° target. The 0.21 m range returns no depth; views 0.5 m out are refused by the UR3e's IK. |
| 5A cockpit pick | 2026-10-08 | Flange hovers over the detector's block centres: 65 mm for 60 commanded (first solve), "very close" in X/Y by eye. No gripper fitted. |
| 5B pendant program | 2026-10-08 | Ran on hardware: FIND → REFINE → approach → grip, centred over each block, NEXT serves the queue, no protective stop. The 163 mm phantom tool put the flange 140 mm up (TIP_M → 50 mm on the Pi: 34 mm over the top). The closer look only rotated from a 0.31 m picture point (floor 0.30 m) and REFINE failed on foam holes; the look now goes straight above the part. With the colour + depth fusion deployed, four green from the picture point and picks from the queue. |
| 6 drills | — | not run |

## Rules for the day

- **One process on Primary.** While the pendant's program runs, nothing on the Mac sends
  URScript (`urctl move-*`, `run-script`, a cockpit APPROACH). A new program on :30001 replaces
  the running one silently.
- **Moves go through the cockpit or the program**, never hand-rolled `movel` from a shell: the
  cockpit sets the TCP to the fingertips and asks the controller's IK first.
- **Don't touch the pendant's installation, safety or network from the network** — there is no
  such path, and there shouldn't be.
- **Two failed attempts at a phase → stop and write.** The list of "never seen on hardware"
  above is long; a session that gets to phase 5A with notes is a success.

## Open before the day (answers go in TODO.md's cell section)

- Does PolyScope 5.25's installer take the 0.9.0 jar (manifest + `URCapCompatibility-eSeries`,
  `Bundle-Category: URCap`, the manifest in the first two zip entries)? A VM load didn't prove
  the pendant's installer (2026-09-27).
- Does the Hand-E's URCap on the pendant coexist with Perceptronic's toolbar button?
- Lighting: the 2026-09-27 evening light put the foam at 55–100 on its darkest channel and the
  detector's white gate at 180 found nothing. Detection is by volume now (depth only), but the
  cockpit's click-to-segment still reads colour. Light the cell, or test in daylight.
- The sustained run: leave the cockpit streaming ≥ 10 min on the cell with `seq` advancing and
  `vcgencmd get_throttled` at `0x0` on the Pi.
