# DEMO.md — the UR3e demo from a MacBook Air (2026-10-07)

What to pack, what to check the night before, the rehearsal, the show, and what to do when
something breaks — for a customer demo of the **Perceptronic URCap** on a real UR3e with the
**pick PC (Raspberry Pi 5)** as the camera computer and a **MacBook Air** (no Docker, no
simulators) as the only laptop. Same bracket and orientation as 2026-09-27, the same white
blocks, on a surface **level with the robot's base**. `ROBOT.md` is the full first-session plan;
this is the subset that has to go right in front of people, in order, with the fallbacks.

**Nothing in the Pi → robot path has run on hardware yet** (`deploy/pi/PLUG-AND-PLAY.md` §Not
verified): the URCap on a pendant since 0.2.0, the Pi reaching the controller, the 3D Pick
program. The rehearsal in §3 is not optional — do it before the customer is in the room, with
the exact kit, and stop after two failed attempts at any step and read §5.

## 0. Answer before you pack

- **Whose UR3e?** Yours (rehearse in the office, then move it) or the customer's (then the
  rehearsal is their robot, an hour before — ask for it). Its PolyScope must be 5.x (e-Series);
  5.25 was yours. Robotiq Hand-E and its URCap on it, or no gripper (the node drives none).
- **Network at the site.** The Pi wants a cable to the robot's Ethernet port, or a small switch
  the Pi, the robot and the Air all plug into. **Bring the office switch and three cables.** The
  Air needs a USB-C Ethernet adapter to join the cell (`192.168.3.10`); without one the Air only
  reaches the Pi by Wi-Fi if the Pi joins a Wi-Fi you both see (the office Wi-Fi today;
  the Pi's `nmcli dev wifi connect <ssid> password <pw>` for the customer's).
- **The blocks' size with a rule** (L × W × H in mm). The node's default is 110 × 50 × 30 and
  the picture goes blank-yellow with a size that is wrong; the foam blocks of 09-27 were about
  60 × 40 × 30.
- **The Air's SSH key on the Pi** (optional but useful: `scripts/deploy-pi.sh … --doctor-only`,
  the journal). The Pi takes keys only: paste the Air's `~/.ssh/id_ed25519.pub` to Claude tonight,
  or add it from the Mac Studio: `ssh nick@10.0.0.56 'echo "<key>" >> ~/.ssh/authorized_keys'`.
  Without it everything below still works over HTTP.

## 1. Pack

| | |
| --- | --- |
| Pi 5 in its case, **the 27 W (5.1 V / 5 A) supply** | on less, USB caps at 600 mA and the D435 browns out mid-demo |
| D435 on the bracket, the short **USB 3** Newnex cable, no hub | a USB 2 link drops the picture to 640 × 480 @ 15 |
| the office switch, 3 Ethernet cables, the Air's Ethernet adapter | see §0 |
| the **"URE MODELS" USB stick** with `perceptronic-ps5-0.9.1.urcap` | `scripts/urcap5-usb.sh` on the Studio with the stick in — the stick has 0.3.0 on it now |
| the **spare microSD** (build #3 image, flashed unseeded) | a dead card is a 2-minute swap; the image has the portal |
| the white blocks, a rule, a flat board if the table is carpet | carpet reads ±3 mm rough; a board is 5× quieter |
| the Air with a checkout of this repo (`git clone`, `dev`), Homebrew `python3` ≥ 3.10 | the runtime is stdlib: `python3 -m perceptronics …` runs from the clone, nothing to install |
| `~/Desktop/perceptronics-update-*.tar` on the Air (built 2026-10-06 night) | the portal upload if the Pi needs the current code without SSH |
| a printed copy of §4 and §5 | the Air may be busy showing the cockpit |

## 2. The night before (done 2026-10-06, re-check in the morning)

- The Pi runs the current code with the **UR3e profile** (`UR_HOST=192.168.3.3`, e-Series,
  `PERCEPTRONICS_TIP_M=0.163`, the 09-27 hand-eye in the file, High Density) — redeployed from
  PR #67 rebased on dev; port 80 on. `curl -s http://192.168.3.20/api/info | head -c 200` from
  the cell says `realsense`.
- The Pi's address on the cable is `192.168.3.20/24`; a robot on DHCP gets `192.168.3.3` from
  it. Your UR3e is static `192.168.3.3` — nothing to set on the pendant's Network screen.
- The stick: §1.

## 3. The rehearsal (60 min, nobody watching)

Cables, power, the Pi up (a minute), the Air at `192.168.3.10`. Then, in this order, each with
its check — **stop at the first one that fails twice** and read §5:

1. **The Pi sees the robot.** From the Air: `curl -s http://192.168.3.20/api/doctor | python3 -m json.tool | grep -E '"name"|"ok"' | paste - -`.
   Want `robot.reach`, `robot.primary`, `robot.rtde` ok, `camera … usb 3.x`, `cockpit ~30 fps`,
   `handeye file:…`. `robot.control LOCAL` is fine. **This is the first time the Pi ever reaches
   a controller.**
2. **The URCap goes on the pendant.** Remove RealSense Pilot (☰ → Settings → System → URCaps,
   select, −, restart). Then + → the stick → `perceptronic-ps5-0.9.1.urcap` → Restart.
   Check: Installation → URCaps → **Perceptronic** shows the live picture, Cockpit field reads
   `192.168.3.20`. ☰ → Save Installation. The **P** button in the header drops the picture over
   any screen. Note anything clipped.
3. **Level and hand-eye.** Blocks on the table, arm at the picture pose (the cell's
   `PERCEPTRONICS_HOME_POSE`, 0.37 m up looking down — level table means the blocks are 0.37 m
   from the lens, inside the D435's good zone). From the Air, the detector's verdict:

       curl -s "http://192.168.3.20/api/pick/scene?opts=$(python3 -c 'import urllib.parse;print(urllib.parse.quote(" part=60x40x30 tol=25 order=LR,FB gripcheck=1 room=20 arm=UR3e proto=2"))')" | python3 -c "import json,sys;d=json.load(sys.stdin);print('status',d['status'],'tilt',d['surface'] and d['surface']['tilt_deg'],'notes',d['notes']);[print(' PART',p['pixel'],p['size_mm'],p['height_mm']) for p in d['parts']];[print(' rej',p['pixel'],p['size_mm'],p['height_mm'],p['why']) for p in d['rejected'] if p['near']]"

   (your block size in `part=`). Want every block a PART, `tilt` < 1°, no *off level* note. A
   note *the table reads N° off level in the robot's frame* means the camera is not where the
   robot says: the bracket seated differently, or the wrong hand-eye — re-solve before the demo
   (pendant to Remote, one block under the camera, then from the Air with SSH:
   `ssh nick@192.168.3.20 sudo -u perceptronics /opt/perceptronics/current/bin/perceptronics --cell /etc/perceptronics/cell.env calibrate --cockpit http://127.0.0.1:7621 --apply`
   — a few minutes; it is saved on the Pi). Without SSH: skip to step 5 and judge by where the
   fingertips land; a constant offset of a few mm is the hand-eye.
4. **The program.** Program tab: `Gripper open` (Robotiq's node) → **3D Pick** (URCaps) →
   `Gripper close` → `If rs_pick_found` → a MoveL 100 mm up, a place, `Gripper open`.
   In 3D Pick: **Part tab first** — Box, the rule's size, 25 %; Approach tab — Finger room
   20 mm, Closer look on; one picture point: arm at the picture pose, **+**. The teach picture
   shows the blocks **green and numbered**; if it shows a banner, it says what to fix (size,
   or a rough surface, or the hand-eye).
5. **▶, speed slider 30 %, hand on the e-stop.** Watch: movej to the picture point → FIND →
   the closer look (0.30 m, the block 12° off-axis, clear of the open fingers) → REFINE → over →
   approach → the fingertips at the grip. Gripper close, lift, place. Then ▶ again: the next
   block comes from the queue (no trip to the picture point). Run it until every block is
   picked. Then speed 60 %.
6. **Reset the scene the way the demo starts**: blocks back, arm at the picture pose, program
   loaded, pendant in Local, speed 30 %.

## 4. The show (what the customer sees, 10 min)

1. Installation → URCaps → Perceptronic: "the robot sees through a camera on its wrist; nothing
   to configure, the camera computer is on the cable." Tap a block: the base-frame point and the
   reach verdict. Press **P** on another screen: the picture follows you.
2. Program tab, open the 3D Pick node: "tell it the part's size and where to take the picture;
   it finds the parts by their shape, in the order you choose" — the green numbers, change the
   pick order tiles and watch the numbers change, move a block and watch it follow.
3. ▶. Narrate the stages as they print on the pendant's log (every stage is a `textmsg`).
4. Add a block, hide one under your hand, put one on its side (a box on any face is still the
   part), put one out of reach (yellow, *out of reach*): the node explains each on the picture.
5. The cockpit page on the Air (`http://192.168.3.20/`): the point cloud in the robot's frame,
   the live pose, for the engineers in the room.

**Don't, live:** change the part size mid-run; send anything from the Air while the program
runs (a new program on :30001 kills the running one — the cockpit's Move, calibrate, `urctl`
are all that); unplug the camera (it recovers, but it takes a few seconds and a −4 popup).

## 5. When it breaks

| You see | Do |
| --- | --- |
| Pendant: *No answer from the camera computer at 192.168.3.20* | the Pi's link light; power; the robot's Network screen on `192.168.3.x/24`. From the Air `ping 192.168.3.20`. Thirty seconds after power-on is normal |
| *… but not the camera program* | the cockpit crashed or is restarting: `curl http://192.168.3.20/api/info`; the service restarts by itself within 10 s; after that, power-cycle the Pi (30 s) |
| *camera gives no picture* / `camera` FAIL in the doctor | the D435's cable into a **blue** port, no hub, the 27 W supply; re-plug it — the cockpit re-opens it |
| The URCap won't install (*invalid file*, or nothing after Restart) | the jar's validity was checked against PolyScope's own validator and installed on this pendant at 0.2.0 — but 0.9.1 never. If it won't: **fallback demo** below |
| Blocks yellow, banner says the size | the rule; Part tab |
| Banner: *surface reads rough* | a board under the blocks; or the picture pose 0.1 m closer |
| Banner / note: *off level in the robot's frame* | the hand-eye: §3 step 3. The demo can run (parts are found) but picks land off by the error |
| Fingertips land a constant few mm off | the hand-eye; also check `PERCEPTRONICS_TIP_M` (0.163 = Hand-E + 6 mm adapter) |
| *3D Pick: no pick — …* popup | it names the reason: `no room for a finger`, `out of reach`, `the second look did not find the block again` (the block moved, or the closer look is too close for a tall block: Closer look off) |
| Protective stop | `unlock protective stop` on the pendant; the node lifts and moves on. Twice in a row: speed down, check the table height vs the grip depth (a surface level with the base is 0.27 m higher than the 09-27 cell: the controller's IK decides reach, but the approach from above needs the elbow room) |
| The Pi is dead (no link light, no `/api/info` after 2 min) | the spare card (build #3): power off, swap, power on, 60 s; it comes up with the same address and the 09-27 hand-eye. Picture point and part size are on the pendant, not the Pi |

**Fallback demo without the URCap** (the cockpit alone, worked 2026-09-27): pendant to
**Remote**; on the Air, `http://192.168.3.20/`; right-click a block → SURVEY → APPROACH → PICK
(the Hand-E through the cockpit's gripper route). Everything the customer needs to see — the
camera on the wrist, the detection, the pick — minus the pendant integration.

## 6. Afterwards

Fill in `ROBOT.md`'s results table, strike `PLUG-AND-PLAY.md` §Not verified, a dated line in
`SETUP.md` §1, snapshots of the blocks from the picture pose into `tests/fixtures/d435/`
(`GET /api/rgbd` → the fixture format: the detector's arbiter is real frames).
