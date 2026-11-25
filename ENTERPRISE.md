# ENTERPRISE.md — from a pick kit to lights-out machine tending

Written 2026-10-04 for Nick's review. Every fact about today's state is from the repo at
`dev` (commit of this file's PR) and is cited by path; every number that is a proposal
says so. Nick's decisions are in §10 (answered 2026-10-04) and folded into the sections.

The one-line product: **a UR owner running a small parts shop loads a tray of blanks in the
evening; the robot feeds the machine all night; the parts are in a bin in the morning.**

Today we sell the first third of that: the robot finds the blank and puts the gripper on
it. This document is the plan for the other two thirds — the place into the machine and
the discipline to keep running unattended — and for the chain of hardware, firmware and
software that lets us ship it to a stranger's cell and keep it working without us
standing next to it.

---

## 1. Where we stand (facts, 2026-10-04)

**What a customer can get today** (`site/public/quickstart-ur.html`, `site/public/index.html`):

| Piece | State | Evidence |
| --- | --- | --- |
| Perceive URCap for PolyScope 5 (`io.advin.perceptronic` 0.11.0; the program node is Pounce) | Built, 23 PolyScope versions 5.4–5.26 green in CI (`urcap5-matrix.yml`) | `integrations/urcap/dist/perceptronic-ps5-0.11.0.urcap` |
| Perceive URCap for PolyScope X (0.9.0) | Built, 10.8–10.14 green in CI (`urcapx-matrix.yml`); screens still the 0.8.0 layout | `integrations/urcap/dist/perceptronic-0.9.0.urcapx`, `integrations/urcap/perceptronic-ps5/README.md` §PolyScope X |
| Pick PC (Pi, cockpit, pick server, firewall, DHCP for the robot) | Deployed and verified on one Pi 5; flashable image boots in ~30 s | `deploy/pi/README.md` §Verified on a board, `deploy/pi/image/README.md` |
| Setup portal + update bundles (network from a browser, upload an update, auto-rollback) | Code + 115 tests, **never on a board** | PR #59, `perceptronics/setupportal.py`, `deploy/pi/perceptronics-admin` |
| Camera bracket | Rev B.2 printed and on the UR3e; **Rev C and the UFACTORY print are unprinted** | `hardware/d435-tool-bracket/README.md` §7 (13 unchecked boxes) |
| BOM | Priced, ≈ $785 per cell with a Pi 4 (≈ $740 for what one cell consumes) | `hardware/BOM.md` |
| Site + datasheet + UR Quickstart PDF | perceptronics.advin.io is live but **serves 0.8.0 / 0.6.0**; the any-robot rewrite is PR #55 | `site/` |
| UFACTORY 850 driver | Against UFACTORY's simulator only | `urctl/ufactory.py`, `ufactory-sim.yml` |

**What has never happened** (`PLUG-AND-PLAY.md` §Not verified, `SETUP.md`, `TODO.md`):

- No URCap newer than 0.5.0 has been on a pendant. 0.6.0 → 0.9.0 exist as renders only.
- The Pi has never talked to the real UR3e. The UR3e has been unplugged since 2026-09-29.
- No pick has been made through the URCap on a real arm. The real picks so far ran from
  the Mac's cockpit (2026-09-25/27).
- The kit board is a Pi 4 (`BOM.md` K1); only a Pi 5 has ever been run.
- No place move, no machine handshake, no gripper control in the node (by decision: the
  customer's program opens before and closes after, `site/public/quickstart-ur.html` §Program).

**The honest summary:** we have a well-tested *picking* component and a well-tested
*deployment* story, both one real-robot day away from being provable, and **zero** of
the machine-side product. Launching tomorrow means launching the pick kit as a beta and
committing publicly to the tending product with dates. It does not mean a shop runs
lights-out tomorrow.

---

## 2. The customer and the job

**Who.** A job shop with 1–5 CNC machines (mills, lathes, Swiss, presses, saws) and one UR
e-Series or UR20, owner-operated, 3–20 people. They bought the UR for machine tending and
it tends one machine during the day with a hand-loaded tray or a fixtured grid. The
machine stops when the tray is empty or the shift ends. They cannot afford an integrator
for every job change and they will not learn vision programming.

**The job to be done.** Run the machine through the night on one tray of blanks, and
through the weekend on three. Concretely:

1. Load: the operator tips blanks onto a tray or a flat surface. No fixture, no order.
2. Feed: the robot takes the next blank, loads it into the chuck/vise, cycles the machine.
3. Unload: the robot takes the finished part out and drops it in a bin (or sets it on a tray).
4. Keep going: until the tray is empty, the bin is full, or something is wrong.
5. Stop safely and say why: a text or an email, and a pendant screen that says what to do.
6. Resume: the morning operator refills the tray and presses one button.

**What they are paying for.** Not the camera. The *hours the machine runs with nobody in
the building*. A 3-axis mill that earns $60–120/h lit-out for 8 extra hours a night is
worth $100k+/year to that shop. That is the number the kit price hangs off, not the BOM.

**What we are not.** Not bin picking, not inspection, not a cobot cell integrator, not a
machine builder. The machine, the gripper, the fixtures and the risk assessment are theirs.
We own: finding the part, putting it in the machine, keeping the loop honest.

---

## 3. Product definition: one kit, one price, and the software grows (decided 2026-10-04)

**One price, no subscription: $2,500 for the packaged kit** (Nick: "$2.5k if you make me
package it for you"). The software is free (MIT) and the BOM is public, so a shop can also
build its own kit from `hardware/BOM.md`; what the $2,500 buys is a kit that arrives assembled,
flashed, burned in and labelled, with the bracket printed, the stick made and the Quickstart
in the box. There are no tiers: Find, Tend and Lights-out are what the same kit does as the
URCap and the pick PC gain the features in §5, delivered as free updates through the setup
portal. Commissioning at the customer is a job priced per visit, not a plan.

**Names.** *Perceive* is the tool: the URCap, its Installation node and the P button. *Pounce*
is the approach: the program node that brings the gripper to the part. "3D Pick" goes.

| Stage of the same kit | What it does | Exists? |
| --- | --- | --- |
| **Find** (today) | Finds every blank of the taught size on a flat surface, numbers them, Pounces the gripper to the grip. The customer's program does everything else. | Yes (beta, unproven on a pendant) |
| **Tend** | Find + the tending program template: place into the chuck/vise, machine handshake over the UR's I/O, unload to a bin, tray-empty stop, one-button resume. A day's commissioning by us or a partner. | No. §5 is the build. |
| **Lights-out** | Tend + the unattended discipline: part-present proof at every step, a re-pick when the grip missed, machine-alarm stop, a cycle log and a shift report on the cockpit. | No. §5. |

Why $2,500 holds: BOM ≈ $820 with the Pi 5 + bracket + assembly/burn-in ≈ 1.5 h → ≈ $1,000
landed cost per kit, so ~60 % gross margin, and still far below any integrator's first invoice.
Robotiq's and Vention's machine-tending bundles are $15k–45k; we are the "already own the
robot" tier below them.

---

## 4. The chain: every step, an owner, a trigger, a done-when

"Someone makes it happen" is the rule. For launch the owner of nearly every row is Nick;
the point of the table is that each row is a *job* with a checklist that a second person
(or a routine) can take over without asking. **A = automated today, M = manual with a
script, N = nothing exists.** The automation column says what to build so the row runs
without Nick.

### 4.1 Hardware

| # | Step | Owner | Trigger | How (today) | Done when | A/M/N | To automate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H1 | Order parts for N kits | Nick | Stock < 2 kits | `hardware/BOM.md` by hand; D435 lead 6–8 wk + tariff; Pi 4 price moves | Parts in the bin, serials logged | N | A `hardware/stock.csv` + a weekly routine that reads it and opens an issue "order N kits" with the BOM lines and last-seen prices |
| H2 | Print the bracket | Contract shop | Kit order | `bracket.py` → STL in `hardware/d435-tool-bracket/out/`; PPA-CF, settings in README §5 | README §7 checklist all ticked for this print | M | Checklist as a form on the kit's build record (H5) |
| H3 | Assemble the kit | Contract shop | Printed bracket + parts | Bracket + D435 + screw + clip; Pi in DIN case + PSU + SD; cables | Photo of the kit, weight, serial label | N | A one-page `hardware/ASSEMBLY.md` with the photo sequence; label printer template |
| H4 | Burn-in | Contract shop | Assembled kit | None today | Pi booted the image, D435 streamed 30 fps for 1 h on this unit's cable, `doctor` all green, thermals logged | N | `scripts/burn-in.sh <pi>`: runs the doctor + a 1 h `/api/info` fps/temperature watch, writes `burn-in-<serial>.json` |
| H5 | Build record | Contract shop | Burn-in pass | None | `kits/<serial>.json`: BOM lot, bracket print, image build id, burn-in result, who | N | The burn-in script writes it; a routine posts a weekly "kits ready" summary |

### 4.2 Firmware (the pick PC image)

| # | Step | Owner | Trigger | How (today) | Done when | A/M/N | To automate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F1 | Build the image | CI (decided 2026-10-04) | A release tag `v*` | `scripts/pi-image.sh build nick@pickpc` (12 min on the Pi with the librealsense cache) | `target/pi-image/*.img.xz` + sha256 + manifest | M → A | **Decided: automate.** A self-hosted arm64 runner (the pickpc itself, or a second Pi on the bench) runs `build.sh` on every `v*` tag and attaches the image to the GitHub Release |
| F2 | Publish the image | CI (decided) | F1 | Hand-upload + `imager.json` on the site (source is on a wip branch, not on dev) | perceptronics.advin.io/imager.json points at the new image, Raspberry Pi Imager lists it | M | Release workflow uploads and rewrites `imager.json`; `site.sh sync` |
| F3 | Flash + seed a kit | Builder | H3 | `scripts/pi-image.sh flash` (macOS) + `seed` (hostname, key, address, optional Wi-Fi, robot host) | Card boots, cockpit 200 on :7621, D435 30 fps | M | Flash station = Raspberry Pi Imager with the published image; seeding becomes unnecessary once the portal (F5) is the way in |
| F4 | Image smoke test | CI | F1 | Nothing in CI; a loop-mount fsck by hand | fsck clean, units enabled, wheel version matches the tag | N | `tests/test_pi_image.py` gets a loop-mount stage on the arm64 runner |
| F5 | Field update | Customer or us | A release | PR #59: upload `perceptronics-update-*.tar` at `http://<pc>:7621/setup`, or `scripts/pi-update.sh push`; health check + auto-rollback | `/api/info` reports the new version; previous release kept | M (unmerged, untested on a board) | The release workflow builds the bundle; the morning report (§6) says which cells are behind |
| F6 | Rollback | Customer or us | A bad update | `install.sh --rollback` / the portal's rollback on health failure | Old version serving | M | — |

### 4.3 Software (URCaps, cockpit, site)

| # | Step | Owner | Trigger | How (today) | Done when | A/M/N | To automate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | Change lands | Claude + CI | PR into `dev` | `gate` + `URCap5 gate` required; auto-merge on green | Merged | A | — |
| S2 | URCap matrix | CI | URCap paths touched; weekly cron | 5.4–5.26 in URSim; 10.8–10.14 in the PSX sim | All green | A | — |
| S3 | Release a URCap | Nick | Version bump in `bundle.properties` / `manifest.yaml` | `make urcap5-package` or `make urcap-package`, commit `dist/`, tag `urcap5-v<ver>` / `urcapx-v<ver>`; `release-urcap5.yml` checks the committed jar is the tag's build and publishes | GitHub Release with the file and its sha256 | A after the tag | A routine that tags when `dist/` changes on `main` (Nick: tags today are `urcap5-v0.5.0` and `urcapx-v0.3.0`; dist is 0.9.0 / 0.7.0 — the public releases are four versions behind) |
| S4 | Promote `dev` → `main` | Nick | When Nick says | PR, hand-merged (#61 tonight) | `main` = `dev` | M | Stays manual by rule |
| S5 | Publish the site | CI (decided 2026-10-04) | `main` moved | `site/site.sh sync` from the laptop with `site/.env` | Live page shows the `dist/` versions and sha256 | M → A | **Decided: automate.** A `deploy-site.yml` on push to `main` with an OIDC role scoped to the one bucket + distribution (deploy-chain PR, draft, Nick merges) |
| S6 | Datasheet / Quickstart PDFs | Claude | Page or version change | Local headless Chrome via `site/build.py --pdf`; a sha256 stamp fails CI until reprinted | One page; stamps match | M | A Playwright step in CI prints and commits the PDFs on `dev` (the stamp test then only guards drift) |
| S7 | USB install stick | Builder | Kit ships | `scripts/urcap5-usb.sh` makes the FAT32 stick with the `.urcap` | Stick in the box, labelled with the version | M | Part of H3 |

### 4.4 Install at the customer

| # | Step | Owner | Trigger | How (today) | Done when | A/M/N | To automate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| I1 | Pre-call | Nick | Order | Email: robot model, PolyScope version, gripper, machine, part sizes | `kits/<serial>.json` has the cell profile | N | A form on the site that writes the profile; the Quickstart PDF goes out with the kit |
| I2 | Mount + cable | Customer | Kit arrives | UR Quickstart PDF (`site/public/quickstart-ur.html`, PR #55) | Camera on the wrist, Pi on the DIN rail, both cables in | M | — |
| I3 | Network | Customer | I2 | Robot gets 192.168.3.3 from the Pi's DHCP; pendant's Cockpit field defaults to 192.168.3.20 | Pendant shows the picture | A (by design, untested on a real robot) | — |
| I4 | URCap install | Customer | I3 | Stick → Settings → System → URCaps → + → Restart (the auto-install file was removed 2026-10-08) | Node appears in the Program tab | M | — |
| I5 | Calibrate | Customer | I4 | Installation node → hand-eye (touch-and-click, 4–6 views) | Doctor's hand-eye line green; a located point within 3 mm of the mark | M (touch-and-click verified 09-23; orbit never on the UR3e) | A one-tap "Calibrate" that runs the orbit and reports RMS, like the cockpit does |
| I6 | Teach the part + tray | Customer | I5 | Pounce node: tap a part, check approach | Green parts, numbered | M (0.9.0 screens never on a pendant) | — |
| I7 | Tend program | Us | I6 | **Nothing today** — §5 | The template runs one full cycle with the machine | N | The template ships in the URCap; the install is filling six I/O fields |
| I8 | Acceptance | Us + customer | I7 | **Nothing today** | §7's acceptance test signed | N | A checklist on the pendant (the node's Test step) that writes the result to the Pi |

### 4.5 Keep it running

| # | Step | Owner | Trigger | How (today) | Done when | A/M/N | To automate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | Know a cell is running | The customer | Always | Nothing | A shift report on the cockpit page, read at the machine | N | **No network beyond the robot (Nick).** The report is a page on the cockpit (`/report`): parts done, faults, longest cycle, camera health, version. Nothing leaves the cell. |
| R2 | Diagnose a stop | Us, from what the customer sends | The customer calls | `GET /api/pick/log`, `captures/`, the audit log on the Pi; only over SSH on the same subnet | Cause named within an hour of receiving the bundle | M | A **Download diagnostics** button on the cockpit page that bundles the last 200 events, the pick log and the last pictures into one file the customer emails us. |
| R3 | Fix and ship | Claude + Nick | Diagnosis | Normal PR flow + F5 | Cell updated | M | — |
| R4 | Spares | Contract shop | Stock < 1 kit | H1 | A spare kit on the shelf for every 5 in the field | N | H1's routine |

---

## 5. What has to be built for Tend and Lights-out

The pick stays what it is. Everything below is *around* it, in the customer's own program
where Nick decided the gripper and the place belong (`site/public/quickstart-ur.html` §Program; decision
2026-10-02 "Pounce keeps its structure"). Build order is the order of risk.

### 5.1 Prove the pick on a pendant (before anything else)

Not new code. One day on the UR3e with the Pi on the cell cable:

- URCap 0.9.0 via the stick and the pendant's URCaps screen (`TODO.md` 09-30, 10-01).
- Pi ↔ UR3e: Dashboard, RTDE, the DHCP lease, the pendant reaching :7621.
- Calibrate, teach, pick 20 blanks in a row through the node. Record misses.
- Measure what the datasheet estimates: part centre, heading, cycle to the grip.

Everything in this document is a promise until this day happens. **It is the launch
blocker; it is not tomorrow's blocker** because tomorrow we launch the beta and the plan.

### 5.2 The tending program template (`tests/fixtures/programs/MachineTend/`, URCap 1.0)

A PolyScope program the customer loads, with the I/O and poses as named variables at the
top. It uses only what PolyScope 5.4 has, so the matrix covers it.

```
Loop forever
  Open gripper                       ← customer's gripper node (Hand-E, OnRobot, pneumatic DO)
  Pounce (tray)                      ← ours, as today
  If rs_pick_found
    Close gripper
    Lift
    Wait DI machine_door_open  (timeout → fault "door")
    MoveJ chuck_approach
    MoveL chuck_insert
    Set DO chuck_close ; Wait DI chuck_closed (timeout → fault "chuck")
    Open gripper ; MoveL chuck_retract
    Set DO door_close ; Set DO cycle_start
    Wait DI cycle_done  (timeout = 2 × taught cycle → fault "machine")
    Set DO door_open ; Wait DI machine_door_open
    MoveL chuck_insert ; Close gripper ; Set DO chuck_open ; Wait DI chuck_open
    MoveL chuck_retract ; MoveJ bin_drop ; Open gripper
  Else
    Popup "Tray empty — refill and press Continue"      ← this is the lights-out stop
    Halt
```

Deliverables:

- The template `.urp` + `.script`, built with `urctl/urp_builder.py` as script nodes (the
  real-robot rule, `CLAUDE.md` §Build motion programs with script nodes).
- An **I/O map screen** in the Installation node: six fields (door open, door close,
  chuck close, chuck closed, cycle start, cycle done) + a gripper choice. Generates the
  variables the template reads. Nothing else on the screen (operator-UI rule: ≤ 3 stages).
- **Fault vocabulary**: `tray_empty`, `door`, `chuck`, `machine`, `part_lost`, `protective_stop`,
  each a popup with the one sentence of what to do, and a `LOG` line to the Pi.
- Machine side: a dry-contact / 24 V I/O recipe for the three common cases (Haas, Fanuc
  0i/30i M-code DO + door-open input, a generic PLC) in `site/public/machine-io.html`. The
  "M-code to open the door" is what every tending integrator sells first; it is a day of
  reading manuals, not code.

### 5.3 Unattended discipline (Lights-out)

- **Part-present proof.** After every close, read the gripper position (Hand-E reports it
  through the same socket `urctl gripper` uses; a pneumatic gripper gives a DI). A grip
  at full close = `part_lost`. Needs a `Gripper.status()` surface in the template.
- **Re-pick when the grip missed** (Nick: "there will likely be a repick needed to ensure the
  part is gripped reliably; a checkbox on the integration"). The node drives no gripper, so
  the check is the camera's: with **Re-pick** ticked, the next Pounce first looks at the
  last grip's spot; a part still lying there means the grip missed, and it is served again
  (same part, fresh measurement) before the queue moves on. Pure perception, no gripper
  feedback needed; the Hand-E's own position read (above) is the stronger check where a
  Robotiq is fitted.
- **Tray-empty stop** = `rs_pick_found == False` twice in a row from the picture point.
  Then halt with the popup. This is already what the node returns; the template makes it
  a clean stop instead of a loop.
- **Bin-full** = a part count the operator sets (`parts_per_bin`), or a DI from a bin
  sensor. Count first; sensors later.
- **Machine alarm** = a DI; stop, do not open the door, popup names the machine.
- **Protective stop** mid-cycle: the pick server already logs; the template leaves the
  part where it is and tells the operator which step it stopped in. No auto-resume into
  a machine.
- **Resume** = Continue on the pendant from the Tray-empty popup; from any other fault,
  the operator confirms the machine state first (a Yes/No popup per fault, `Robot.confirm_on_pendant`).
- **Cycle log** on the Pi: one JSON line per part (time, pick number, pose, grip
  position, machine cycle time, fault). `audit.jsonl` exists; it needs rotation
  (`deploy/pi/README.md` §Open items) and this record type.

### 5.4 Nothing leaves the cell (decided 2026-10-04)

Nick: "No alerts, no outbound or inbound besides the robot." The pick PC's cell port is its
only network; the setup portal is reached from that port. So:

- **Faults** are the pendant popup (the fault vocabulary in §5.2) and the cockpit's events
  and pick log. Nothing is sent anywhere.
- **The shift report** is a page on the cockpit the operator reads at the machine in the
  morning: parts done, faults with their step, longest cycle, camera fps/temperature, free
  disk, version. Same numbers the alerts would have carried.
- **Diagnostics** reach us the way the customer chooses: a **Download diagnostics** button
  on the cockpit page bundles the last 200 events, the pick log and the last pictures into
  one file they email. That is R1 and R2 with no cloud and no plant interface.
- The portal keeps the plant-interface option for the customer's own network, but the
  product never initiates a connection and nothing listens beyond :7621/:7622 on the cell.

### 5.5 Hardware for the shop floor

- **Pi 5, decided.** The BOM moves K1 to the Pi 5 + its 5 A PSU (the board every run so far
  used; the datasheet's 0.9 s is its number). Industrial carriers (RevPi, CompuLab) are not
  a worry yet (Nick).
- **Enclosure**: the Pi in a DIN case in the customer's cabinet is fine; the D435 is not
  IP-rated. For coolant-mist cells, a printed shroud with a lens window is Rev D's job.
  Not for launch; say so on the datasheet ("dry cells").
- **Cable**: the Newnex screw-lock cable is single-source. Qualify the passive 5 m alternate
  (`BOM.md` O3) on the first build.
- **D435 supply**: 6–8 weeks and a tariff, and Cognex is buying RealSense (close expected
  Q4 2026). Hold 10 units of stock from the first revenue; qualify the D455 as the
  fallback (same SDK, same bracket face within a millimetre — verify) in Q1.

---

## 6. Timeline

**Tomorrow (launch day) — "the beta is public, the plan is public".**

1. `dev` → `main` (#61) once #55 and #59 are in. ✔ in progress tonight.
2. Tag `urcap5-v0.9.0` and `urcapx-v0.7.0` so the GitHub Releases match `dist/`.
3. `site/site.sh sync`: the any-robot page, 0.9.0 / 0.7.0 downloads, the Quickstart PDF,
   the one-page datasheet.
4. Publish the Pi image `imager.json` from a real source on `main` (today it is on a wip branch).
5. Beta terms on the site: free URCap, the packaged kit at $2,500, "Tend early access opens
   January 2027". One email address, one form.
6. ~~This document reviewed by Nick → decisions in §10 made~~ ✔ 2026-10-04; it stays at the root as the plan of record.

**Week 1 — prove it (§5.1).** Plug the UR3e in. One day on the pendant with the Pi. Fix
what breaks (expect the DHCP lease and a pendant layout surprise).
Reprint the datasheet with measured numbers where the estimates were.

**Weeks 2–3 — Tend on our own cell.** The template (§5.2), the I/O screen, the fault
vocabulary. No machine here: a "machine" is a box with a DI/DO breakout and a 20 s timer
(a UR DO looped to a DI through a relay is enough). Fifty cycles unattended on the bench.

**Weeks 4–6 — first Tend customer: OX Manufacturing.** One machine, one part, a free install
in exchange for a week of logs and a reference. The re-pick and the shift report ship to them first.

**Weeks 6–10 — Lights-out.** Part-present, bin-full, machine alarm, the shift report on the
cockpit. Second and third customers. The routines take over H1/F1/S3/S5.

**January 2027 — early access opens** (Nick): installs at shops beyond OX from then.

**Quarter 2 — the second connector.** UFACTORY 850 on a real arm (the driver exists), then
whichever vendor the first ten customers ask for. The template is URScript today; the
second connector needs it expressed in that controller's language. That is when the
`Controller` protocol grows `set_digital_output` / `wait_digital_input` (it has neither
today, `urctl/controller.py`).
On PolyScope X, the cockpit can also be packaged as a URCap backend container
(`containers:` + `devices: video` + `services: urcontrol-primary`, `integrations/urcap/DEVELOPING.md`)
so the pendant needs no external host; that is a quarter-2 packaging job, not a product tier.

---

## 7. Acceptance tests (what "done" means at each gate)

| Gate | Test | Pass |
| --- | --- | --- |
| Kit burn-in (H4) | 1 h stream on the kit's own cable, doctor green | 30 fps sustained, no `Frame didn't arrive`, CPU temp < 70 °C |
| Pick on a pendant (§5.1) | 20 blanks of one size, random layout, 3 tray positions | ≥ 19 grips within ±3 mm of the taught offset; zero wrong-part grips; no protective stop |
| Tend on the bench (§5.2) | 50 cycles with the relay "machine" | 50/50; every forced fault (pull a wire) names itself correctly within 1 timeout |
| Tend at a customer (I8) | One shift attended, then one shift unattended | ≥ 95 % cycles complete; every stop was a named fault with a correct instruction |
| Lights-out (§5.3) | 3 consecutive nights | Zero unexplained stops; the morning report matched the bin |
| Field update (F5) | Push a bundle to a running cell | Live within 2 min, rollback on a deliberately broken bundle within 5 |

---

## 8. Risks, in order

1. **It has never run on a pendant.** Mitigation: §5.1 is week 1, before any customer date.
2. **Camera supply.** D435 lead 6–8 weeks, tariff, Cognex acquisition. Mitigation: stock
   10, qualify the D455, keep the bracket parametric (it is).
3. **Safety and liability.** The integrator owns the risk assessment (datasheet footer).
   Tend puts the robot's hand in a machine; the template must never open a door or start
   a cycle without the DI that proves the state. Put "the customer's risk assessment
   covers the tending program" in the Tend terms, and keep the machine-side I/O design
   with the customer's electrician, not us.
4. **Unauthenticated :7621/:7622 and unsigned update bundles** (Nick's decision, noted).
   The cell port is the only network (§5.4), so the exposure is whoever is on the cell
   switch. Decided 2026-10-04: a **forced password change on the portal's first login**;
   bundles stay checksum-only.
5. **One person.** Every row in §4 is Nick until the Builder exists; decided: it **starts
   with a contract print/assembly shop** (H2–H5, R4), and the routines (H1, F1, S3, S5) are
   how Nick does not become the bottleneck.
6. **PolyScope X parity.** The X node is still the 0.8.0 layout. UR20 and new e-Series
   ship on X; a Find customer on X gets the older screen until parity (standing rule).

---

## 9. What launches tomorrow, exactly

- `main` = everything in `dev` tonight (the 0.9.0 URCap, pick PC image + setup portal,
  UFACTORY 850, bracket Rev C, any-robot site).
- Releases `urcap5-v0.9.0`, `urcapx-v0.7.0`, the Pi image on `imager.json`.
- perceptronics.advin.io: any-robot pitch, UR connector downloads, Quickstart PDF,
  one-page datasheet, **a Tend / Lights-out section that says "early access opens January
  2027"** and asks for robot, PolyScope version, machine, part. The kit at $2,500.
- This file, reviewed.

Not tomorrow, and the site must not imply it: a pick verified on a pendant, a tending
program, alerts, or any cell running unattended.

---

## 10. Decisions — answered by Nick, 2026-10-04 (verbatim; folded into the sections above)

1. **Prices** (§3): Find kit $1,950? Tend install $2,500 + $150/mo? Lights-out +$100/mo?
   Or a single price and no subscription?
Answer: Single price with no subscription, $2.5k if you make me package it for you.
2. **Launch wording**: "beta" on the Find kit, "early access" on Tend — yes? What date
   goes on "installs from"?
Answer: Early access opens the beginning of 2027
3. **Pi 4 or Pi 5** for the kit (§5.5). My recommendation: Pi 5 + the 5 A PSU; the Pi 4
   saves $25 and costs a validation we have not done.
Answer: Pi 5, not worried about industrial kits yet.
4. **Tend lives in the customer's program** (template, §5.2) — confirmed? The alternative
   is a second node ("Place") that does the machine side; it is nicer on screen and much
   more code, and it ties us to every machine's quirks.
Answer: Confirmed, all we do is get the part in the gripper, BUT there will likely be a repick needed to ensue the part is gripped reliably. This can be a checkbox as well on the integration.
5. **Alerts off the plant network** (§5.4): SMTP + webhook in the portal, opt-in copy to
   us — acceptable? This is the first time the Pi talks outbound.
Answer: No alerts no outbound or inbound besides the robot.
6. **Forced password change on first portal login** before the plant interface is enabled
   — yes? (Bundles stay unsigned per your 2026-10-03 decision.)
Answer: Yes force a password change
7. **The first Tend customer**: a shop you already know, free install for logs and a
   reference. Who?
Answer: OX Manufacturing
8. **Name**: "Pounce" vs "Perceive" (TODO 10-02) — decide before the 1.0 URCap with the
   I/O screen, since the template and the docs will say it everywhere.
Answer: Perceive is the name of the tool and Pounce is what we'll call the approach.
9. **Site deploy from CI** (S5) and **image build on a self-hosted runner** (F1): both are
   deploy-chain changes; draft PRs for you to merge, or leave manual for the first ten kits?
Answer: Automate the deployment
10. **The Builder** (§8.5): when, and is it a person or a contract print/assembly shop?
Answer: It will start with a contract shop.

Folded in on 2026-10-04: §3 (one price, the names), §4 (F1/F2/S5 automated, the contract shop,
R1/R2 without a network), §5.3 (re-pick), §5.4 (nothing leaves the cell), §5.5 (Pi 5), §6
(OX Manufacturing, January 2027), §8. The work is in TODO.md.
