---
paths:
  - "integrations/urcap/**"
  - "tests/test_urcap*.py"
  - "tests/test_pick5_e2e.py"
  - "tests/test_preview5.py"
  - "tests/test_ps5_matrix.py"
  - "tests/test_picknode*.py"
  - "perceptronics/picknode.py"
  - "perceptronics/partspec.py"
  - "perceptronics/armfk.py"
  - "perceptronics/armik.py"
  - ".github/workflows/urcap*.yml"
  - ".github/workflows/release-urcap*.yml"
---

# The Perceptronic URCaps (PolyScope 5 and PolyScope X): Perceive, Pounce, the pick server

`CLAUDE.md` always applies. This loads when you touch the URCaps, their tooling, the pick-server protocol or their CI. Install / use: `integrations/urcap/README.md`; working on them: `integrations/urcap/DEVELOPING.md`. **After editing a URCap run `make urcap-package urcap5-package` and commit `integrations/urcap/dist/`** — a test holds the committed packages byte-equal to a fresh build.

## Names and identities

**Names on the pendant (Nick, 2026-10-04: "Perceive is the name of the tool and Pounce is what we'll call the
approach"):** the Installation node, the P button and the bundle name read **Perceive**; the program node reads
**Pounce** (3D Pick until 0.10.1; service id `PerceptronicPick` / tag `advin-perceptronic-pick` unchanged, so saved
programs load). The URCap files and bundle ids stay `perceptronic`. Landed as PS5 **0.11.0** / PSX **0.9.0**; the
0.10.x / 0.8.x releases (tool offset, quiet while running) shipped under the old name, so a pendant on 0.10.x must
take 0.11.0 to see the new names.

**The URCaps are "Perceptronic" (Nick: "not this weird RealSense Pilot thing"), owned by Nick personally,
namespaced by his domain advin.io. Identities a robot may still carry from before: "RealSense Pilot",
`com.nickarmenta.perceptronic` / `nickarmenta/perceptronic` (PolyScope X 0.3.0 shipped under it) — remove them first:** PolyScope 5 bundle
`io.advin.perceptronic` (Java package the same, `Bundle-Vendor: Nick Armenta`,
`Bundle-Copyright: Copyright (c) 2026 Nick Armenta`, jar
`integrations/urcap/dist/perceptronic-ps5-<ver>.urcap`; the `urmagic_perceptronic.sh` auto-install
file that sat beside it was **removed 2026-10-08** (Nick: it rebooted the controller the instant
the stick went in — install only through the pendant's URCaps screen; `urcap5-usb.sh` deletes any
copy left on a stick)), PolyScope X `advin/perceptronic` from 0.4.0
(`integrations/urcap/perceptronic/`, element `advin-perceptronic`). A different bundle identity is a
different URCap to PolyScope: the old one must be removed on a robot that had it, and its
saved node data (cockpit address, pick areas) and programs' RealSense Pick nodes don't carry
over. Node titles: **Perceive** (installation) and **Pounce** (program) — *Names on the pendant*, above. The mark
is `integrations/urcap/perceptronic.svg` — a P with a lens in its bowl; `Logo.java` draws the same glyph
with Java2D (toolbar badge, screen headers, a 38 % watermark bottom-right of every live
picture) and a test holds its `SVG` constant byte-equal to the file and to the PolyScope X
icon copy. **The P button (0.6.0, `ToolbarService` / `ToolbarContribution`):** a
`SwingToolbarService` — the Robotiq-style header button — that drops the live picture down
over any screen (420 px tall, polls only while open, reads the Installation node's saved
address through `ApplicationAPI.getInstallationNode`). The toolbar API has been in the URCap
API since 1.7.0 (PolyScope 5.4; checked in the jars), so no compat guard; the matrix's Felix
check requires the toolbar service registered (`ps5_matrix.NODE_SERVICES`). The feed loop
is one class, `FeedPoller` (no UR API, tested against the real cockpit), shared by the
Installation node and the popup. Not yet seen on a pendant: the button's icon size (30 px)
and popup height are guesses to check on the UR3e.

## PolyScope X URCap

**PolyScope X URCap (`integrations/urcap/` — `README.md` to install, `DEVELOPING.md` to work on it):** an
Application Node that embeds the cockpit's colour feed in PolyScope X and turns a
click into a base-frame point + approach pose (`/api/segment` → `/api/robot/locate`)
with two Move buttons — PolyScope's IK + auto-move screen, or the cockpit over
Primary — plus, since 0.3.0 (2026-09-29), the **pick areas + reach** on that node and
the **Pounce** program node: the PolyScope 5 kit's
node for PolyScope X (`pickscript.js` = `PickScript.java`'s port, same pick-server
protocol, held to the Python parser by `tests/test_urcapx_pick.py`). PolyScope X draws
a program node's presenter inside its 48 px tree row, so the Pick row is one line and
the screen is a PolyScope custom dialog (`dialogService.openCustomDialog`); a code
generator answers `{type: "$$ScriptBuilder", script, currentIndent}` (children indent by
`currentIndent`; the after-children builder carries the negative). Verified in the 10.13
sim: toolbox → row → dialog → picture point from PolyScope's joints → the script
compiled and run by Play (NEXT → movej → FIND over the network to a cockpit).
**`integrations/urcap/psx_matrix.py`** runs the e2e on the newest PolyScope X releases from the
URCap's floor, 10.8 (`urcapx-matrix.yml`, weekly + on URCap changes, not required; all
eight 10.8–10.14 pass 2026-09-30 with fallbacks for what 10.8–10.11 lack,
`integrations/urcap/README.md` §Tested; 10.6/10.7 dropped — their sims don't start on the runners). A
`urcapx-v<version>` tag publishes `dist/perceptronic-<version>.urcapx` as a GitHub
Release (`release-urcapx.yml`, `urcapx.py release-check`). Plain JavaScript, no npm: `integrations/urcap/urcapx.py package|install|list|delete`
(gzipped tar, manifest first; multipart to the Robot-API's `urcaps/v1/urcaps/`);
`make urcap-package|urcap-install|urcap-cockpit`. **`integrations/urcap/dist/*.urcapx` is the
committed download** and a test holds it byte-equal to a fresh (reproducible)
build — after editing the URCap run `make urcap-package` and commit `dist/`. The cockpit must be started
with `--cors <PolyScope origin>` (`PERCEPTRONICS_CORS`) and serves `GET
/api/color.png` for it. The installer posts `urcapxFile` to the **urservice**
endpoint System Manager itself uses (`/universal-robots/urservice/api/v1/urcaps`;
201 / 409 / DELETE, no Remote mode needed) — the SDK's Robot-API path answers
403 unless the robot is in Remote mode, from inside the container too. Built
against SDK 6.5.65 (the 10.13 pairing) — the worker speaks threads.js's
protocol directly. Verified 2026-09-26 in the 10.13.0 sim (headless Chromium):
node loads, feed + hover + click-to-segment work against the fake cockpit;
locate/move still need a cockpit with a robot link. **Release tracking:** the URCap targets
*one* PolyScope X release — the newest minor's newest patch — pinned in
`integrations/urcap/target.json` (notes URL, sim image by digest, SDK tag + contribution-api /
threads / manifest-spec versions); `integrations/urcap/track.py check|update|compat` and
`integrations/urcap/e2e.py` (boot that sim, install, load + click the node headless; ~2 min) are
what `.github/workflows/urcap-track.yml` runs weekly → PR or `urcap-attention` issue.
10.14.0 verified 2026-09-27 (the 10.14 Services-toggle bug doesn't touch URCaps), then
**held at 10.13** the same day to match the local sim image (`"hold": "10.13"` in
`target.json`: the track re-pins that minor's newest patch, never a newer minor). **Move (PolyScope)** re-expresses the
cockpit's flange target in *PolyScope's own* active TCP (`getKinematicInfo` DH +
`convertJointPositionsToTcpPose` at zero joints) before `getInverseKinematics(pose,
qNear)`, which takes no TCP — handing it the cockpit's `approach_pose` (a pose under the
*cockpit controller's* TCP) made every click unreachable in the sim. That IK never
answers an unsolvable pose (the node gives it 8 s). Cockpit field shorthand (`:7621`,
`host:port`) is completed to a URL; a bare `:7621` used to be fetched relative to
PolyScope's own page and its 404 misread as an outdated cockpit.

## PolyScope 5 URCap

**PolyScope 5 (e-Series) URCap (`integrations/urcap/perceptronic-ps5/`, `README.md`):** the same node
as a Java 8 Swing **Installation node**, same layout and buttons (Open cockpit dropped —
no browser on the pendant); Move (PolyScope) hands `RobotMovement.requestUserToMoveRobot`
the controller's `joint_target`. Built by `integrations/urcap/urcap5.py` (`make urcap5-sdk` reads the
URCap API bundles of any `ursim_e-series` tag straight from Docker Hub's registry into
`target/urcap5-sdk/<tag>/` — no Docker; not on Maven Central, never committed; `make
urcap5-package` → `integrations/urcap/dist/*.urcap`, reproducible, with a sources digest a test checks).
**Backwards compatible from PolyScope 5.4** (`bundle.properties` `compat.floor`): compiled
against 5.4's API (`api-1.7.0.jar`, hence `urcap.api.version=1.7.0` — 5.10+ refuse a pom
naming a newer API than their newest `PackageDependencyProvider`); newer API only in a
`compat.since.<ver>` class loaded by name behind a check (`TeachPosition2`:
`RobotPositionCallback2`, 5.8+; its package imported `resolution:=optional`). The script
adapts to the PolyScope it runs on: no `get_inverse_kin_has_solution` before 5.9.4, and
lists keep their first size up to 5.14 (never reassign a read to a different count). PolyScope 5's loader needs `URCapCompatibility-CB3`
/ `-eSeries` in the manifest and reads the API version from an embedded
`META-INF/maven/**/pom.xml` (`com.ur.urcap:api` dependency). Its **installer** (Settings →
URCaps → +) also demands `Bundle-Category: URCap` and the manifest among the first two zip
entries (`URCapsServiceImpl.isValidFile`); the VM's `install-urcap` copies the jar into the
bundle dir and skips those checks, so a VM load does not prove the pendant will install it
Check with PolyScope's own `URCapFileValidationHelper` from the
image's `/ursim/GUI/bundle`. Installed and rendered on the UR3e pendant 2026-09-27 (0.2.0).

## The Pounce program node and the pick server

**The program node (same bundle; `PickScript.java`, `perceptronics/picknode.py`; "Perceptronic Pick" from 0.4.0,
"Pounce" since 0.11.0):** Program tab → URCaps → Pounce. Its URScript runs in the operator's program (Local mode,
no Primary) and talks to a pick server over a plain socket (`:7622`; `FIND`/`LOOK`/`REFINE`, and
`LOG` lines that are never answered — a stray reply would be read as the next answer). No survey
position is needed: the first look is from where the arm is, the closer look from halfway toward
the block with it centred (never nearer than 0.25 m). Every stage is a `textmsg` **and** a `LOG`
line; a failed pick raises a blocking popup naming the reason. The cockpit serves the pick server itself and keeps its trace: every line is a `pick` event, appended to
`captures/pick.log` (or `~/Library/Logs/perceptronics/` when `captures/` is root-owned) and served as
text at `GET /api/pick/log`. The node's script has not yet run on a controller (`ROBOT.md` is that day's plan).
**Part size (0.4.0, `perceptronics/partspec.py`):** the node's Length × Width [× Height] ± tolerance
(any face down since 2026-10-03; default ±25 %, never under ±5 mm) rides on FIND/REFINE as `part=60x40x30 tol=25`
and replaces `detect_blocks`' fixed foam-block gate (≤ 70 × 60 mm); height is measured against the
non-white depth in a ring around the blob (unseen → not checked). Status −7 = white things in view,
none that size; the teach screen draws the rejects grey with why. Still colour-segmented: the part
must read white. Verified on synthetic scenes only.

**The pick kit (`site/public/quickstart-ur.html`).** The product line for a PolyScope 5
cell: `hardware/BOM.md` (sourced, dated prices), the bracket, `deploy/pi/` (a Pi-class arm64
camera computer on minimal Debian: librealsense built pinned, the cockpit as the
`perceptronics-cockpit` service on :7621/:7622, nftables; `scripts/deploy-pi.sh`, the
`deploy-pick-pc` skill; `pick-pc.md`), and the URCap. **Detection is by volume**
(`perceptronics/volume.py`, depth only, no colour): what stands the part's height above the
surface with a top face its length × width; the surface is a taught pick area (three
fingertip touches in the Installation node, nudged ≤ 15 mm to the live table) or the table
found live; each part's min-area rectangle gives the axes, the fingers close across the short
side. `order_parts` numbers parts in the **picture's** directions (front = bottom of the
picture); with the grip check on, `volume.clear_the_way` then reorders them so a part pinned
only by other parts (one in its finger zone) is picked after them instead of being turned
away, and the picture's order only breaks ties (Nick, 2026-10-02: "pick the parts that make
other parts easier to pick"). Reach = base outer radius + 150 mm .. rated reach − 150 mm (`Reach.for_model`).
**Pick server protocol** (`picknode.parse_options`; the server speaks `PROTOCOL = 3`, which adds `tcp=` — a
protocol-2 node without it is answered -14): every request carries
`part= tol= order= grip= stroke= [reach=] [plane= area=] node= loc= locs= proto=`, answers
are 16 numbers; `NEXT` serves the per-node queue (the next part already seen: no trip to the
picture point), `FIND` refills it. The Java `PickScript.tokens` writes the same line, and
`tests/test_urcap5_pick.py` reads the Java's tokens back with the Python parser — change
one, the test tells you about the other. The node's screens (`PickScreen`, `LocationsScreen`,
`LiveView`, `Diagrams`, `Ui`) are pure Swing: render them off-pendant with a harness (the
README's `screens/` are `integrations/urcap/preview5.py --screens integrations/urcap/perceptronic-ps5/screens`). The teach screen asks `GET /api/pick/scene?opts=<tokens>`.
**Every PolyScope 5 minor, 5.4-5.26** (the newest image of each; all 23 green) runs every URCap change in CI (`urcap5-matrix.yml`, versions from
`ps5_matrix.py list`; `integrations/urcap/docker-compose.ps5-matrix.yml` is generated by `ps5_matrix.py
compose`, ports 20000 + 100 × minor + the usual port's last two digits; `check-tags` only
ever adds): `urcap5.py check` against the image's own API jars, Felix shell (port 6666 in
the container) proves the bundle Active — polyscope.log never says so — then
`integrations/urcap/pick5_e2e.py` runs the node's own script, two picks, the second from the queue, plus
a compile probe (Robotiq + popup inside `if False:`) and a socket-timeout probe. A `build`
job rebuilds the committed jar against 5.4's jars with JDK 21 and `urcap5.py compare`s it
(entries, non-class bytes, class members — JDK-independent; the committed jar is JDK 25's).
`check-tags` also compares each image's `VERSION` with `IMAGE_VERSIONS` (bare tags re-pushed).

**The node's screens and script (since URCap 0.7.0 / PolyScope X 0.5.0; Nick's feedback 2026-09-30).** The
program node (service id `PerceptronicPick` / tag `advin-perceptronic-pick`) is one move sequence with **no
children** that starts with the survey and ends with the fingertips at the grip — no lift, no "After picture"
node, and it drives no gripper (below). Its rules: **(1) nothing scrolls** — picture points are a fixed 2 × 6 grid of
numbered buttons with the selected one's actions under it, only the selected pick area is open, and
`test_everything_on_the_nodes_screen_fits_without_scrolling` lays each screen out and fails on a
clipped control or a scroll pane. **(2) Options = two tabs**, Part (Box / Cylinder, size, tolerance,
**Grip check**, off by default) and Approach (approach, grip depth, **Closer look**); speeds have no
settings (`PickScript` constants: 60 %) and there are no gripper settings — the node drives no gripper (below). **(3) The picture carries only near misses** (`Scene.nearMisses`, the server's
`near` flag: a little off the size, or the right size and out of reach) and a **Picture / Depth**
toggle top right inside the frame (`GET /api/depth.png`, half-size, ramp = the frame's 2–98 %).
**(4) Reach is the arm's kinematics**: the node sends `arm=<model>` (never `reach=`), and
`perceptronics/armik.py` — closed-form UR IK over `armfk.DH`, every answer checked against the FK —
says whether approach + grip have a joint solution at lean 0 / 12 / 24°; only the base's keep-out
(radius + 150 mm) is kept; an arm not in the table is left to the controller. The Installation's reach
margins are gone; its map shows the rated reach, named. **(5) The closer look** puts the camera
0.30 m from the part with the part 12° off the optical axis on the side away from the gripper
(`picknode.look_pose`, `gripper_bearing`: on the UR3e the open fingertip is 9° off-axis, 0.15 m out —
a centred part was behind it); with no look pose the node measures again from where it is; with the
closer look off every part is measured from its picture point (no queue). **(6) No camera** → the
picture's place says what to check (cables, IP address, firewall; USB on a 503) and the exception goes
to the log (`Log.java` / the browser console). **(7) `shape=cyl`**: an upright cylinder by its
diameter, wrist not turned; `gripcheck=0` drops the stroke and finger-room checks. The two nodes write
the same URScript — `test_the_script_is_the_polyscope_5_nodes_line_for_line` (apart from `global x =`).
`preview5.py --screens DIR` re-renders the README's pictures. **Not run on a robot**; the PolyScope X
dialog was clicked through in the 10.13 sim (`integrations/urcap/e2e.py`: depth view, both option tabs fit).
**The picture is the thing (Nick, 2026-10-08: "the stream ... should take up much more of the page").**
On both platforms and both nodes the controls are one column on the **left** — where PolyScope's own
screens keep their settings — and the picture fills everything right of it: PolyScope 5's Installation
camera tab (`PilotView.CONTROLS` = 300 px, the feed centred in the rest, no size cap) and the Pounce
screen (`PickScreen` sidebar `WEST`); PolyScope X's `.rsp .cam` / `.pk .cols` (the `.side`/`.ctl` first,
the stage `flex: 1`, no `max-width`). The Installation camera tab has no off-pendant render (`PilotView`
needs the UR API); the Pounce pictures in `screens/` are the layout.

**The node drives no gripper (since URCap 0.8.0 / PolyScope X 0.6.0; Nick 2026-10-01).** "The node should not control the gripper
whatsoever because the user will open the gripper before the node and close it after": the script has
no Robotiq socket, no digital output, no held check — it ends with the fingertips at the grip
(`rs_pick_found = True` there) and `test_the_node_does_not_touch_the_gripper` holds both nodes to it.
With no gripper there is no stroke: the grip check is **on by default** and is the operator's number,
**Finger room** (Approach tab, default 20 mm) → `gripcheck=1 room=20`: that much clear space on each
of the two sides the fingers come down on, from the part's edge (`pickplan.clearance(room_m=)`), and
no "wider than the open gripper" test. **Grip across the long side** (Approach tab, boxes only) →
`across=long`: the wrist turns 90° and the room is checked on those sides. Cylinders stand on a flat
end (decided; a lying one rolls). **The picture: pickable parts green with their pick-order number,
near misses yellow with why** (still nothing for what is nothing like the part). The closer look
assumes fingers open 50 mm (`LOOK_STROKE_MM`) when it keeps the part clear of them.

**Settled 2026-10-01 (Nick):** green overlays for pickable parts and yellow for *marginal* ones (the
server's `near` flag) is the intended picture — nothing is drawn for what is nothing like the part;
the Pounce node's picture carries no watermark; the **UR7e is the UR5e's arm and the UR12e the
UR10e's** (`armfk.DH` aliases, so `armik` judges them). The UR30 and UR15 rows are UR's published table (2026-10-02); an arm not in `armfk.DH` is left to the controller.

## Traps

**Every request the URCap pages make to the camera computer is bounded** (`AbortController` + `setTimeout`; `test_every_request_to_the_camera_computer_can_time_out` reads every `fetch(` in `integrations/urcap/perceptronic/perceptronic-frontend/`): an empty Cockpit field means 192.168.3.20, and an unbounded fetch to an address nothing answers on hung the PolyScope X e2e on every version.

**Three traps from the Pounce sessions.** (1) `integrations/urcap/pick5_e2e.py` compiles the test harness in
`tests/test_urcap5.py` (`HARNESS`): anything the harness starts to use must be in the source list
`generate()` copies (`PURE_JAVA` + `SCREEN_JAVA`) — a mismatch failed all 23 controller jobs in a
minute; `tests/test_pick5_e2e.py` now builds the e2e's scripts and replays its session. (2) The
committed packages in `integrations/urcap/dist/` conflict on a rebase whenever *anything packaged* changes on `dev`
— the LICENSE included — and a conflicting PR shows **no checks at all**: rebase, delete the
conflicted files, `make urcap-package urcap5-package`, push. (3) Playwright is not in `.venv` (this repo
does not use uv): `uv run --with playwright==1.63.0 python integrations/urcap/e2e.py --image
universalrobots/ursim_polyscopex:10.13.0` still works where uv is installed, but leaves a stray
`uv.lock` — delete it before committing.

## Gotchas

| Symptom | Cause | Fix |
| --- | --- | --- |
| The Pounce node (or any FIND) seems **hung**: nothing moves, the pick log (`GET /api/pick/log`) shows `FIND: no fresh camera frame` (status −4) over and over | The D435 dropped out of the cockpit: its frames freeze at one `seq` (`/api/info` says `stalled: true`, `fps` 0), and `/api/info`'s `last_error` says `Frame didn't arrive within 5000` (the macOS USB-claim race). Each FIND waits for a frame newer than the request, gets none, answers −4, and a looping program asks again | Re-plug the camera; the lean open re-opens it by itself. `/api/info`'s `last_error` carries the camera's error, and the node pops up the reason (`popupOnFail`) instead of looping silently |
