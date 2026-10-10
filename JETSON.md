# JETSON.md — the GPU line: one RGB camera and a Jetson instead of a depth camera and a Pi

What the second product line is, what it has to prove, and the order to prove it in. Written
2026-10-10 from a Q&A with Nick after the 2026-10-09 cell day (`TESTING.md`), before any Jetson
is on the bench. Dated prices and specs carry their source at the bottom; a number without a
date is a guess and says so. Lives on `main` so it is findable without knowing the branches.

## 0. Decided (Nick, 2026-10-10)

- **Two lines, one superset.** *Line A, shipping:* expensive sensor + cheap compute — the
  RealSense D435 and the Pi 5 (`hardware/BOM.md`), the **add-on** for a cell that has a CPU
  box. *Line B:* cheap sensor + expensive compute — **one RGB camera and a Jetson**, the
  **installation**. Everything A does is baked into B; a customer who skips the compute box
  gets A, and nothing in A is ever B-only.
- **B is for robustness and generalisation, not accuracy.** Neither line changes what the
  camera can measure ("that would be a dramatically different system and camera"). Within the
  current bounds A is satisfactory and economical. (One pushback, §1: lateral position and
  heading may still come out better on B, as a side effect, not a goal.)
- **A single RGB camera is the ultimate goal.** Not proven feasible; it needs testing on the
  platform before anything is promised. §4 says what a lone RGB camera cannot see and how the
  arm's own motion may stand in for depth.
- **Budget is the gate.** "If I don't need a Thor why would I want one?" A Thor only when it
  buys something an Orin-class part does not: the features past picking (§2.3), which may be
  things not yet thought of — an on-board vision-language assistant, a training loop on the
  cell.
- **The camera's interface is not the point; PoE and cable length make GigE the obvious
  choice.** Power from the tool flange's 24 V where it suffices (§3). **Fixed overhead is out of
  scope**: it separates the picture from the robot's live position and adds a calibration.
- **Intrinsics + hand-eye for a non-RealSense camera** are needed and operator-run: a printed
  board, once (§3.4).
- **Lighting: cope by default.** There is no room on the bracket for a light. A potential
  dealbreaker, to be measured, not assumed (§6, E5).
- **The approach is (a):** 2-D instance segmentation plus geometry — the table plane and the
  part's dimensions as priors. Not a 6-DoF pose network, no CAD per part.
- **Training is deferred.** Nothing in this plan requires a customer to train anything; what a
  learned segmenter would be trained on is one paragraph (§5), not a workstream.
- **"Ambiguous pick" means the user gives the machine a word** to hint what it is looking for;
  when the word isn't in the training set, that is where a real-time training loop would come
  in. Far down the line. **Easy picks first.**
- **Detector: RF-DETR** (Apache 2.0; already deployed by Nick in `JimothyJohn/ophanim`, on CPU
  through ONNX Runtime at about a second a query). AGPL models are off the table for anything
  shipped. **TensorRT at runtime.**
- **One correction from the research, §3.2:** no UR arm has Ethernet at the tool flange. The
  flange's M8 8-pin is power, ground, two digital in, two digital out, two analog in (RS485 rides
  the analog pins). The 24 V is there; the camera's Ethernet still runs down the arm.

## 1. What Line B must do that Line A cannot

Every failure on the 2026-10-09 cell day, sorted by whose fault it is (`TESTING.md`, bottom):

| The sensor's (A cannot fix it) | The software's (A fixed or can fix it) |
| --- | --- |
| Foam and bare-metal tops come back 10–60 % holes to the IR projector; one of four blocks found by depth alone until the colour fusion | Touching parts (P5–P7): split by the part's size, fragile at ±25 % (a 2 × 2 and three-across fit alike) |
| White paper on the table is where the depth *returns* and the grey table where it doesn't: the surface's brightness decides | Stacked, leaning, covered (P8, P11): false picks until the too-close guard and the size check's "too tall" |
| Dark anodized tops read 3–5 mm small; a rim on a puck adds to its height | A side face at the picture's edge, a cable on a block: the colour outline swallowed them until clipped by depth |
| Nothing under 0.28 m; sizes good to ±max(5 mm, 1.2 % of range); lateral blur ~1 % of range | A hand in the picture (P17): nothing picked, by luck of the size gate |
| The black mat's velcro strips drop out and one passed as a standing block | |

The left column is what B is for. An RGB picture has no IR projector: foam, bare metal, paper
and the black mat are all just pixels, and what tells a part from the table is learned, not a
threshold in CIE Lab. The right column is what B must **not** reopen: the size gate
(`PartSpec`), the touching split, the stack and lean refusals are behaviour the fixtures hold
today, and §6 E7 holds B to the same bar.

**The pushback on accuracy.** The D435's lateral blur is the stereo matcher's window, about 1 %
of range: 4 mm at 0.40 m, the same with the SDK filters off. A 2 MP global-shutter camera over a
0.5 m-wide view at 0.40 m is ~0.26 mm per pixel, and a learned mask's edge is a pixel or two,
not a blurred step. Position and heading in the plane are then limited by the hand-eye and the
plane prior (1° of hand-eye ≈ 9 mm at 0.5 m, as today), not by the sensor. Height is a prior on
B, so B measures *less* than A in one axis and better in two. This is not the reason for B, but
the datasheet should not promise B is worse.

## 2. The compute, honestly

### 2.1 What things cost (NVIDIA raised every Jetson price in July 2026, up to 101 %)

| Part | List price | Note |
| --- | --- | --- |
| Raspberry Pi 5, 4 GB (Line A, BOM K1) | ~$120 priced line, Pi 5 to re-source | no GPU |
| Jetson Orin Nano Super developer kit | **$399** (was $249) | 8 GB, 67 TOPS, JetPack 6 (CUDA 12) |
| Jetson Orin NX 16 GB module | $999 at 1k units (was $599) | + a carrier; JetPack 6 |
| Jetson AGX Orin developer kit | $3,499 (was $1,999) | 64 GB; JetPack 6 |
| Jetson T4000 module (Thor, small) | $2,999 at 1k (was $1,999) | JetPack 7 (CUDA 13) |
| **Jetson AGX Thor developer kit** | **$5,499** (was $3,499) | 128 GB LPDDR5X, Blackwell, 2070 FP4 TFLOPS sparse, 40–130 W; JetPack 7 |
| Jetson T5000 module (Thor) | $4,999 at 1k (was $2,999) | the dev kit's module |

A Line B installation on a Thor costs more in compute than Line A costs in total several
times over. A Line B on an Orin Nano Super costs about what the D435 does ($314, BOM K3) — the
camera it replaces.

### 2.2 What each tier runs

The picture is taken at rest (the node is quiet while the program runs; "quality over speed",
cycles 30 s+), so inference has **seconds**, not milliseconds. Latency only matters for the
closer look (two pictures a cycle) and for anything interactive on the teach screen.

| Model | Params | Latency, T4 reference (the vendor's table) | License |
| --- | --- | --- | --- |
| RF-DETR-Seg-N / S / M / L | 33.6 / 33.7 / 35.7 / 36.2 M | 3.4 / 4.4 / 5.9 / 8.8 ms at 312–504 px | Apache 2.0 |
| RF-DETR-Seg-XL / 2XL | 38.1 / 38.6 M | 13.5 / 21.8 ms | PML 1.0 (`rfdetr[plus]`) — not for shipping |
| SAM 2 (Hiera-S … L) | 46–224 M | — | Apache 2.0 |
| SAM 3 | ~0.85 B | — | SAM License (Meta, 2025-11-19): commercial use not excluded; military / nuclear / espionage / ITAR excluded; Meta may change the terms and continued use is acceptance; no reverse engineering. A gate to read in full before it ships in a product |

No Jetson numbers are in that table because none have been measured; a Jetson is 5–20× a T4
and the exact factor is E6's job. The shape of the answer is already clear:

- **The pick kit on Line B (RF-DETR-Seg N–L in TensorRT FP16, the geometry in numpy) fits the
  Orin Nano Super.** Ophanim runs RF-DETR on a Lambda CPU in about a second; the same ONNX on a
  Pi 5 is E3, and if it is a few seconds, Line A gets the learned segmenter too, with no GPU.
- **SAM 3 at interactive rates** on the teach screen (an exemplar click → every instance) wants
  the Orin NX / AGX Orin tier at least.
- **A vision-language assistant on the box, a training loop on the cell** (§2.3) want the
  Thor's memory (128 GB) and are the only things that do.

### 2.3 Why want a Thor, then

Three reasons, in order of how sure they are:

1. **It is the platform going forward.** Orin stays on JetPack 6 / CUDA 12; Thor is JetPack 7 /
   CUDA 13 / TensorRT 10.13+ on Ubuntu 24.04 (7.0 in 2025, 7.2.1 current). The Thor branch's
   container (`UR-utils-thor`, `Dockerfile.perception` on `nvcr.io/nvidia/pytorch:25.08-py3`,
   CUDA 13) already does not run on an Orin. Two JetPack baselines is a cost; one is only
   possible if the product is Thor-class or if the engine is built on the device from one ONNX
   at install (§7, the rule either way).
2. **The features past picking.** The word-prompted pick (§0) is a vision-language model with the
   part exemplar and the user's word; a "what went wrong" assistant reading the cockpit's events
   and pictures on the box, with no cloud, is the same model. A training loop that fine-tunes the
   segmenter on the cell's own frames while the cell runs. These are Thor-class memory and
   compute, and they are the "real-time training" and "ViT/LLM assistant" ideas — unpriced,
   unproven, the reason to *experiment* on a Thor before pricing a product on one.
3. **Headroom for the sim-to-real route.** If a learned segmenter needs training data (§5),
   rendering it (Isaac Sim, BlenderProc) on the same box that runs the cell is a Thor job.

**The honest position:** the Line B pick kit does not need a Thor. A Thor on the bench is to
find out which of (2) earns its keep, and to be on JetPack 7 before customers are. Hence a
loaner, not a purchase (§8).

## 3. The camera

### 3.1 Develop on the D435's colour stream first

The D435's colour sensor *is* an RGB camera (848 × 480, rolling shutter, a fixed lens). 16 of
the 20 frames in `tests/fixtures/d435/` carry colour, intrinsics, the flange pose, the hand-eye
and labelled pixels — the whole RGB-only geometry (§4) can be scored on them on a laptop before
any camera is bought (E1, E2). What the D435's colour cannot tell us: how a global shutter and
a real lens behave, and anything about lighting past the office.

### 3.2 Power and cable through the arm (the correction)

The UR e-Series tool flange connector is an M8 8-pin: tool power at 12 or 24 V, ground, two
digital inputs, two digital outputs, two analog inputs that become RS485 when the Tool
Communication Interface is on. **No Ethernet on any UR arm's flange** (UR3e … UR30 checked
against the techsheets; Ethernet exists only in the arm-to-controller cable). The current
budget at the flange: **UR3e 600 mA**; UR7e / UR12e / UR16e / UR20 up to 2 A on the dual-pin
configuration.

So for a flange camera: **its power can come from the flange** (a GigE camera that takes power
on its I/O connector; check the camera's input range and draw against the UR3e's 600 mA
before relying on it), **its data runs down the arm** — one thin Cat5e/6 to a
PoE-less switch port, instead of Line A's active USB 3 (BOM O2: $399 for 5 m; O4 $159 for 1 m).
That is the whole case for GigE: the cable, not the interface. On a cell where the camera PC
sits on the base, the 1 m USB 3 run of a UR3e is fine either way.

### 3.3 Candidates (to source into `hardware/BOM.md` with dated prices before any is bought)

| | Off-the-shelf, USB 3 | Industrial, GigE |
| --- | --- | --- |
| Example | Arducam 2.3 MP AR0234 colour **global shutter** USB 3 module, UVC: $139.99–154.99 (Arducam store, 2026-10-10); TechNexion VCI-AR0234-C $151.75 + lens | **Sony IMX273 class — 1.6 MP, 1440 × 1080, global shutter, 1/2.9"**, the industrial sensor nearest the pipeline's need (the D435's colour is 848 × 480; the segmenter's input is 312–504 px; 2 MP+ is paid for and thrown away). Three of them at $370–500, prices 2026-10-10: **Lucid Triton TRI016S-CC $386** (Edmund; **PoE or 12–24 VDC** on its I/O connector — the flange's 24 V, no injector); FLIR Blackfly S BFS-PGE-16S2C-CS $371 (Edmund; Teledyne pushes Spinnaker, GenICam works); Basler ace 2 Basic a2A1920-51gcBAS $379–492 (Machine Vision Store / Edmund; 2.3 MP IMX392, more than needed — a $2,000 Basler is another model; this one lists at $379–492) |
| Opens with | V4L2 / AVFoundation, no SDK (the webcam views' path) | **Aravis** (GenICam, LGPL) — not Basler's pylon, so a second vendor is a part number, not a port |
| Cable | USB 3 (active past 3 m) | Cat5e/6, any length, power from the flange or PoE |
| Lens | fixed M12, choose FOV at purchase | C-mount: an IMX273 is 4.97 mm wide, so a **6 mm** lens sees ~0.33 m across at the 0.40 m look (8 mm: 0.25 m); the lens is a separate line to source (~$100–200 class, unpriced) |

Rolling-shutter webcams (the C920) are out: the picture is taken at rest today, but a global
shutter is what keeps a future picture-while-moving honest and costs nothing on the AR0234.

### 3.4 Intrinsics and hand-eye for a camera that isn't a RealSense

The D435 hands over its colour intrinsics; a Basler or an Arducam does not. Ship a printed
ChArUco board in the kit; `perceptronics calibrate --intrinsics` (new) images it from the
orbit's own viewpoints and writes `K` + distortion to the cell; the existing orbit hand-eye
(`perceptronics/orbitcal.py`) can take the board instead of a white block — its corners are a
better mark than a blob. Operator-run, ten minutes, once per camera. The cockpit's
`/api/rgbd` header already carries `intrinsics`; the RGB path reads them from the same place.

### 3.5 Lighting

A global shutter with a short, locked exposure and the white balance held is the cheap half.
The other half is measurement, not engineering: the segmenter under the shop's lighting states
(E5). If it fails under sunlight through a window with nowhere to put a light, that is a
datasheet line ("indoor, no direct sun on the parts"), the same way the D435's IR washout is.

## 4. The pipeline (approach (a))

The pick server, the protocol (3), the 16-number answer, both URCaps: **unchanged**. B is a
second implementation of "one frame → parts" behind the same seam as `volume.py` / `fusion.py`.

1. **Picture at rest** from the look pose (PolyScope's move; the node's FIND), the robot's pose
   from RTDE as today, the taught pick area or the live table as the plane.
2. **Instance masks** from the segmenter: one class, "part", every instance. RF-DETR-Seg
   (TensorRT FP16) when there is a trained model; the SAM family with an exemplar prompt from
   the teach screen when there isn't (SAM 2 for shipping, SAM 3 once its license is read). The
   mask replaces `fusion._mask` (the Otsu split in Lab) and nothing else.
3. **Geometry**: mask → minimum-area rectangle in pixels → each corner cast as a ray onto the
   table plane **lifted by the part's height** on the face nearest the measured footprint
   (`fusion._on_plane` does exactly this today with the colour outline) → length × width →
   `PartSpec.poses()` any-face-down check → position, heading, the finger-room check
   (`pickplan.clearance`) → the same `near` / why-not reasons on the picture.
4. **What a lone RGB camera cannot see, and the answer to each:**
   - *A stack* (P8): two 30 mm blocks have one block's footprint. Under a height prior the stack
     is 30 mm nearer, so it projects 7.5 % larger at 0.40 m — inside ±25 %, so it passes. The
     fix is **parallax from the arm's own motion**: two pictures from poses 50–100 mm apart
     (the closer look already moves the camera) give the top's height from the known baseline.
     At 0.40 m with a 2 MP, ~70° lens (~1400 px focal length) and a 50 mm baseline, one pixel of disparity is
     ~2.3 mm of depth; a 30 mm stack is 13 px. The robot's pose is the second camera's pose to a
     millimetre, so this is stereo with the extrinsics known, not structure-from-motion. **E4
     tests it on the D435's colour before any camera is bought.**
   - *A lean* (P11): the same parallax, on the top face's corners (a resting top is at one
     height; a leaning one is not).
   - *Partly covered* (P9, P11): a footprint touching a taller one, taller by parallax.
   - *A hand, a cable, a lead* (P14, P17): the segmenter's job, with the size gate behind it.
   - *Finger room*: today from depth round the part; on B from the other masks and the plane
     (anything not table and not the part, inside the finger zones, is in the way).
5. **The same verdicts to the pendant**: green with a number, yellow with why, nothing for what
   is nothing like the part.

## 5. Training data (deferred)

One class, "part", per cell. Three ways to get a trained RF-DETR-Seg without a customer
labelling anything, in the order to try: **self-labelled from the cell** (the teach screen's
clicks → SAM masks → the cell's own frames become the training set, a few dozen are plenty for a
fine-tune); **synthetic** (the box / cylinder spec rendered on a table with the cell's lighting
— `synthscene` does this for depth; colour needs a renderer); **none** (the SAM family with an
exemplar prompt is the segmenter, no training; slower, bigger, the license question). Not
designed further until E2 says which segmenter is good enough on the fixtures.

## 6. Experiments, in order — the first five need no Jetson

Each has a pass bar; the bar for anything that replaces today's path is `TESTING.md`'s: every
part found in every straight-down view, sizes ±5 mm (±10 on cardboard), positions within 10 mm
across views, headings within 2° for a box, **and** P5–P7 (touching), P8 (stacked), P11
(leaning) refused or split correctly.

| | Experiment | Where | Pass |
| --- | --- | --- | --- |
| E1 | **RGB geometry with a perfect mask.** The 16 colour fixtures' labelled pixels as the mask; §4 step 3 alone; compare position / size / heading with the depth path and the labels | a laptop, a day | the bar above on the 0.32–0.40 m frames |
| E2 | **Segmentation on the fixtures.** SAM 2 with one point prompt per labelled part; RF-DETR-Seg zero-shot (COCO weights; expected to fail on foam — the number says how far a fine-tune has to go) | a laptop with torch | masks whose rectangle meets the E1 bar; count the misses by cause |
| E3 | **The CPU floor.** RF-DETR-Seg-N and SAM 2 small as ONNX on the **Pi 5** (Ophanim's ONNX Runtime path) | the pick PC | seconds per frame; under ~5 s means Line A gets the learned segmenter |
| E4 | **Height from the arm's motion.** On the UR3e with the D435's colour only: two pictures 50–100 mm apart; parallax height of each top vs the rule; stacks (P8) and leans (P11) | the cell, an hour | height to ±5 mm at 0.40 m; the stack and the lean refused |
| E5 | **Lighting.** P1 under the shop's lighting states: lights on, lights off, sun on the parts, a shadow across them | the cell | the bar, or the datasheet line that names the failure |
| E6 | **On a Jetson.** TensorRT FP16 engines built on the device at install; latency and power for RF-DETR-Seg N–L and SAM 2 / 3; the Orin Nano Super ($399) first, the Thor when it arrives | a Jetson | the time per picture and per closer look; which tier the kit needs |
| E7 | **The live matrix.** P1–P17 and S1–S4 with the RGB path on the cell, `scripts/cell_sweep.py`, every run saved as fixtures | the cell, a day | the bar; no regression on any fixture the depth path passes |

## 7. Where it lives in the repo

- `perceptronics/backends/` is the seam (`sam.py` already plugs into `Segmenter`); the RGB
  detector is a backend next to it, selected per cell (`PERCEPTRONICS_DETECTOR=volume|fusion|rgb`,
  default unchanged). The core stays zero-dependency; B is an extra (`[gpu]`: numpy, the
  TensorRT runtime, Aravis bindings when the camera is GigE) or the Jetson container.
- **The engine is built on the device at install** from one committed ONNX, never shipped as an
  engine: a TensorRT engine is tied to the TensorRT version and the GPU, and Orin (JetPack 6)
  and Thor (JetPack 7) differ. PyTorch only in the dev container.
- The Thor branch (`feature/perception-thor`, `UR-utils-thor` worktree, NGC PyTorch 25.08 /
  CUDA 13) is this plan's ancestor: its container is the Thor dev environment; its detector
  work predates `volume.py` and `fusion.py` and is superseded. Rebase the container, drop the
  rest.
- The camera layer gets a second opener beside `realsense.py` and `views.py`: V4L2 for the UVC
  module, Aravis for GigE; both feed `/api/rgbd` with colour + intrinsics and no depth, and the
  cockpit page's depth view says NO DEPTH CAMERA rather than lying.
- Tests: E1/E2 become unit tests over the fixtures (no model download in CI: the masks are
  committed as fixtures, the segmenter is run by hand and its output checked in, like the
  URCap packages).

## 8. Getting a Thor

NVIDIA has no loaner programme I could find (2026-10-10). Inception (no fees, no cohort; a
company under ten years old with a developer and a website) gives preferred pricing, and a
reseller's Inception list has the AGX Thor dev kit on it (Aug/Sep 2026). The ask to the NVIDIA
contact is therefore a **seed unit or a loaner for 90 days, failing that Inception pricing**,
with something in return NVIDIA wants: a public UR-cobot + Jetson reference (both PolyScope
URCaps, the cockpit, the datasheet with Jetson numbers), a Jetson AI Lab-style writeup, and an
ISV's feedback on JetPack 7. The pitch text is with Nick, not in this repo.

Until it arrives: E1–E5 (no Jetson), and E6 on an Orin Nano Super at $399, which is also the
answer to "which tier does the kit need" and the right thing to have measured *before* asking
NVIDIA what a Thor adds.

## 9. Open questions

Carried in `TODO.md` under *Open questions for Nick* (2026-10-10): Inception membership and
which entity applies; whether to run E3 on the Pi now; which camera to source first; the SAM 3
license read.

## Sources (read 2026-10-10)

- Jetson prices, July 2026: cnx-software, "NVIDIA increases the price of Jetson modules and
  devkits by up to 101 %" (2026-07-22), the table of old → new prices.
- Thor specs: ServeTheHome's AGX Thor developer kit review; NVIDIA JetPack downloads
  (JetPack 7.0: Jetson Linux 38.2, CUDA 13.0, TensorRT 10.13.2; 7.2.1: Linux 39.2.1, CUDA 13.2.1,
  TensorRT 10.16.2).
- UR tool flange: UR e-Series technical sheets (M8 8-pin; 12/24 V; UR3e 600 mA; UR7e/12e/16e/20
  2 A dual-pin; "2 analog in or 1 RS485"); PolyScope X SDK "Serial communication via the Tool
  Connector" (TCI uses the analog inputs); UR20 techsheet (Ethernet only in the robot cable).
- RF-DETR: rfdetr.roboflow.com (model table, "ONNX, TFLite, TensorRT, ExecuTorch, CoreML and
  OpenVINO exports", "Core models (Nano through Large) and all code are released under the
  Apache 2.0 license", XL/2XL under PML 1.0 via `rfdetr[plus]`).
- SAM 3: github.com/facebookresearch/sam3 LICENSE (SAM License, 2025-11-19).
- Cameras: Arducam store (AR0234 USB 3 module, $139.99–154.99); TechNexion (VCI-AR0234-C,
  $151.75 at 1–49); Edmund Optics (Lucid Triton TRI016S-CC $386, FLIR BFS-PGE-16S2C-CS $371,
  Basler a2A1920-51gcBAS $492); Machine Vision Store (a2A1920-51gcBAS $379); the Triton's PoE 802.3af / 12–24 VDC and
  IMX273 from Edmund's listing (Lucid's own page 404'd on the day).
- NVIDIA Inception: pi3g's Inception-eligible product list (Aug/Sep 2026); NVIDIA developer
  forum threads on Inception hardware discounts.
