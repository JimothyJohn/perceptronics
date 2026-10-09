# Testing the detector on a cell

The experiment matrix for making the pick kit robust: what to put on the table, how to look at
it, and what to record. Each configuration is one run of `scripts/cell_sweep.py` (the camera
through the standard views over the parts, the pick server's verdict at each, every picture
saved); a run that misbehaves is turned into a labelled fixture under `tests/fixtures/d435/`
so the detector improves without a robot in the loop.

Started 2026-10-09 on the UR3e cell (Pi 5 + D435 on the flange, PolyScope 5.25, URCap 0.10.1).
The first day's results are at the bottom.

## Before a run

1. The pendant in **Remote**; the cockpit answering (`curl http://192.168.3.20:7621/api/info`).
2. `perceptronics doctor` on the pick PC: `handeye` from a file, `robot.control` REMOTE,
   `approach` naming the pendant's active TCP.
3. The hand-eye fresh: one white block alone under the camera, then
   `python3 -m perceptronics calibrate --cockpit http://192.168.3.20:7621 --apply` (the orbit:
   ~40 views, ten minutes). Every view of every run reports the table's tilt in the base frame;
   over 1° means the calibration is out, and a degree is ~9 mm of position at this range.
4. Know the parts: length × width × height in mm (a cylinder: diameter and height), and whether
   the dimensions are honest (cardboard isn't; a rim on a puck adds to its height).

## The run

```
python3 scripts/cell_sweep.py sweep <tag> --part 50x30x30 --centre -0.36 0.01
python3 scripts/cell_sweep.py sweep <tag> --part 75x75x18 --shape cyl --centre -0.29 0.03
```

`--centre` is the parts' centroid in the base frame: take it from a first
`view look --point <guess> --height 0.35 --no-move`. On a UR3e with the parts past ~0.36 m out,
`--no-sides`: the side views stretch the arm into a protective stop. The table at the end is the
record: parts found per view, sizes read, near misses with why, and each part's position spread
and heading range across views.

What a good run looks like on this cell: every part found in every straight-down view, sizes
within ±5 mm (±10 on cardboard), positions within 10 mm across views, headings within 2° for a
box. What is not a detector fault: a part cut off by the picture's edge (another picture point
covers it), a view the controller's IK refuses (the arm's reach), a part with no finger room
because a cable or a neighbour lies beside it.

## The matrix

Tick what has been run; put the tag and the date in the box.

### Parts (on the grey table, straight down, until a row says otherwise)

| | Configuration | What it tests | Run |
| --- | --- | --- | --- |
| P1 | 3–4 white foam blocks 50×30×30, apart | the baseline | 2026-10-09 `v1`–`v9` |
| P2 | 3 black anodized bars 90×40×12 | dark, low parts; the height floor | 2026-10-09 `bars2` |
| P3 | 3 white cardboard boxes 100×60×60 | big parts, imprecise sizes, the picture's limits | 2026-10-09 `boxes` |
| P4 | 3 black anodized cylinders 75 Ø × 18, as cylinders | round parts, no heading | 2026-10-09 `cyl` |
| P5 | two blocks touching, long side to long side | splitting one blob into two parts | 2026-10-09 `p5_touching_long` (0/2, one blob) |
| P6 | two blocks touching, end to end (a 100×30 bar) | the same, along the length | 2026-10-09 `p6_touching_end` (0/2, one blob) |
| P7 | four blocks pushed into a 2×2 cluster | the same, in both directions | 2026-10-09 `p7_cluster` (0/4, one blob) |
| P8 | one block stacked on another | a 60 mm "part" must not pass as 30 | 2026-10-09 `p8_stacked` (refused; a false pick at 0.28 m) |
| P9 | one block half under another | the lower one must not pass; the upper may | |
| P10 | a block on its side (30×30 face up, 50 tall) | any face down | 2026-10-09 `p10_on_side` (1/1 in every view) |
| P11 | a block on end, leaning on another | neither should pass | 2026-10-09 `p11_leaning` (false picks) |
| P12 | a 100×60×60 box among 50×30×30 blocks | a distractor of the wrong size, rejected with why | 2026-10-09 `p12_distractor` (box rejected, blocks found) |
| P13 | the bars among the blocks, part = the blocks | dark distractors | |
| P14 | a block with a lead or cable across it | the outline, the finger room | 2026-10-09 `p14_cable` (refused; a pick at 0.28 m) |
| P15 | a block at each edge of the picture, side faces showing | the colour outline swallowing a side face | 2026-10-09 `v4` (one miss) |
| P16 | one part only, then eight | count independence, the pick order | |
| P17 | a hand or a tool in the picture during the look | clutter that must not pass | 2026-10-09 `p17_hand` (look-only; nothing picked) |

### Surfaces (the baseline blocks, P1 layout)

| | Configuration | What it tests | Run |
| --- | --- | --- | --- |
| S1 | the grey table | the baseline | 2026-10-09 |
| S2 | a basswood board on the table | a raised, patterned surface; its edge | 2026-10-09 `wood` |
| S3 | white paper on the table | white on white (the depth returns on paper) | 2026-10-09 `paper` |
| S4 | the black rubber mat | the datasheet says it drops out — confirm or retract under 0.10.1 | 2026-10-09 `s4_black_mat` (found; heights +2–8 mm; one false pick) |
| S5 | the carpet (parts on the floor beside the table) | rough surface, the local floor fit | |
| S6 | a glossy surface (a laminated sheet, a steel plate) | specular dropouts | |
| S7 | a printed or patterned sheet (a page of text, a chessboard) | colour outline vs texture | |
| S8 | the board propped 3–5° off level | the "table as seen vs base frame" rule | |
| S9 | the board propped 15°+ | the same, past the level gate | |
| S10 | a surface with a step (the board covering half the parts' area) | two local floors | |

### Views and light

| | Configuration | What it tests | Run |
| --- | --- | --- | --- |
| V1 | the standard sweep (down 0.35, sides, oblique 18°, 0.28 floor, turned 90°) | the picture-point geometry | every run |
| V2 | picture points taught by hand on the pendant, then the node's own FIND | the node, not the sweep | |
| V3 | the Look down view on each pick area | 0.10.1's straight-down view | |
| V4 | a lamp on the parts from one side (hard shadows) | the depth's shadow ramp, the colour outline | |
| V5 | the table under a window, midday | sunlight on the IR projector | |
| V6 | the room lights off | colour outline with no colour | |
| V7 | the camera's laser at 150 vs 360 | the Pi's `PERCEPTRONICS_RS_LASER_POWER` | |

### Robots, versions (after the UR3e works nicely)

| | Configuration | What it tests | Run |
| --- | --- | --- | --- |
| R1 | the UR3e, gripper off, TCP 0 | this document | 2026-10-09 |
| R2 | the UR3e with the Hand-E, its 0.163 m the active TCP, the 3D Pick program in a loop | the real pick: protocol 3, the quiet picture, the approach 25 mm over the top | |
| R3 | a UR5e / UR10e: the same matrix at 0.5–1.0 m | the range-scaled tolerance, the kinematics tables | |
| R4 | the UR20 cell on PolyScope X | the 0.8.1 node's first run on hardware | |
| R5 | PolyScope 5.4 and 5.14 images in the matrix CI | the oldest API, the list-size rule | every URCap PR |

## Ground truth (when dialling in)

With three or four parts in place, freedrive the tool onto each part's top centre and read the TCP
pose (`urctl --host 192.168.3.3 state`, or the cockpit's `/api/robot/state`), then compare with
the detector's centres from the straight-down view: absolute error per part, which is the number
the datasheet carries. Not done yet.

## Results, 2026-10-09 (UR3e, grey table unless noted, the hand-eye of 2026-10-08)

The table read 1.2–2.7° off level in every view all day. Two orbit calibrations were tried to
fix it and both applied a nonsense solve (see below), so every number here is with the 10-08
solve. Nick: the robot is bolted to a sheet-metal table that flexes under overhang, so a tilt
that changes with reach is probably real.

### Parts and surfaces as laid out

| Row | Scene | Straight-down views | Other views | Sizes read | Spread across views |
| --- | --- | --- | --- | --- | --- |
| P1 | foam blocks 50×30×30 | 3/3, 3/3, 2/3 (edge block read 40 wide: "too wide") | oblique 3/3; 0.28 m 1/1 in view; turned 3/3 | 48–54 × 29–33 × 29–33 | 6–8 mm, 1° |
| P2 | black bars 90×40×12 | 3/3 ×3 | oblique 1/3 (two merged, one lost finger room); 0.28 m 3/3; turned 3/3 | 89–97 × 38–43 × 10–12 | 4–8 mm, 1.5° |
| P3 | cardboard boxes 100×60×60 | 3/3, 2/3, 3/3 (cut off at the edge) | oblique 3/3 (best sizes); 0.28 m 0/3 (none whole in the picture); turned 1/3 | 90–101 × 57–62 × 58–60 | 4–9 mm, 0.5° |
| P4 | black cylinders 75 Ø × 18 (a 3–4 mm rim) | 2/3 (a cable beside one), 3/3, 3/3 | oblique refused; 0.28 m 3/3; turned 3/3 (one merged with its cable) | 69–74 Ø × 14–16 | 8–13 mm |
| P5 | two blocks touching, long sides | 0/2: one 57–59 × 49–51 blob, "2 parts touching?" (one view read the pair's edge as a block) | the same in every view | | 2026-10-09 `p5_touching_long` (0/2, one blob) |
| P6 | two blocks end to end | 0/2: one 94–100 × 26–38 blob, "2 parts touching?" | oblique: nothing near at all | | 2026-10-09 `p6_touching_end` (0/2, one blob) |
| P7 | 2×2 cluster | 0/4: one 99–106 × 58–68 blob | oblique: two slivers, "too narrow" | | 2026-10-09 `p7_cluster` (0/4, one blob) |
| P8 | one block on another | 0 — 47–50 × 29–32 × 57–58 "too tall" (right) | **0.28 m: a false pick, 55 × 35 × 30** (the stack's top inside the camera's range returns no depth; the foam rule takes a hole for foam) | | 2026-10-09 `p8_stacked` (refused; a false pick at 0.28 m) |
| P10 | a block standing on its 30×30 end | 1/1 in all seven | | 29–33 × 23–29 × 48–50 | 5 mm; heading arbitrary (square face) |
| P11 | one block leaning on another ("P9" as laid out) | **false picks**: the lower block's uncovered 40 mm end (40–42 × 25–31 × 30) and the leaning block as "standing" (28–32 × 24–28 × 38–51) | 2 of 7 views refused the pair as "too long" / "touching" | | 2026-10-09 `p11_leaning` (false picks) |
| P12 | a box among three blocks | 3/3 blocks, the box rejected (97–105 × 58–59 × 57–58, labelled "2 parts touching?" — right call, wrong reason) | 2/3 turned (one cut off) | 49–54 × 28–32 × 28–31 | 7–8 mm, 1–2° |
| P14 | a white cable across a block | 0 ("too long" 63–71 × 40–51; "3 parts touching?" 140 × 48) | **0.28 m: a pick, 59 × 37 × 31** (block plus cable, inside the tolerance) | | 2026-10-09 `p14_cable` (refused; a pick at 0.28 m) |
| P17 | a hand over the parts (look-only, no motion) | 0, twice, to the millimetre: the hand 195 × 95 "cut off", slivers of block "too short" | | | 2026-10-09 `p17_hand` (look-only; nothing picked) |
| S2 | foam blocks ×4 on a basswood board | 4/4 (sides out of reach) | oblique 4/4; 0.28 m 3/4; turned 3/4 | 45–50 × 25–30 × 29–32 | 2–5 mm, 2–6° |
| S3 | foam blocks ×4 on white paper | 4/4, 4/4 (then a protective stop on the near-side view) | — | 46–49 × 28–30 × 28–30 | 3–5 mm, 6° |
| S4 | one block on the black rubber mat | 1/1, 1/1 (two views); near side "too tall" 38; **far side a false pick, 28 × 26 × 50 — a velcro strip's end** | oblique 1/1; 0.28 m 1/1; turned 1/1 (36 tall) | 42–53 × 28–37 × 30–38 | 8 mm |

### What it put on the detector's list, in order

1. **Clip the colour outline to the depth footprint's half-height line.** A block at the
   picture's edge shows its side face and the outline swallows it (P1: 50 → 40 mm, rejected); a
   white cable on a white block is swallowed the same way (P14: 59 × 37 passed at 0.28 m); a
   cylinder's lead too (P4). Three fixtures-to-be. **Done 2026-10-09** (`fusion.colour_parts`):
   a blob pixel with valid depth more than 8 mm below the blob's top (or below the half-height
   line when the top has no depth) is dropped, except within a blur width of the kept top — the
   depth's blurred ring inside the colour's sharp edge reads low too and is the top; a clip that
   would keep under 40 % of the blob is not trusted. Synthetic: a 4 mm cable off a block 171 → 99 mm,
   a side-face ramp 116 → 105, a solid block unchanged at every blur. Still to check on the frames.
2. **Split a blob by the part's size.** Touching blocks never split (P5, P6, P7); two bars in the
   oblique view read as one 151 × 60; a cylinder and its cable as 87 × 74. The seam is a visible
   line in colour for side-by-side blocks (P5, P7), invisible end to end (P6): the split must come
   from the part's length, with colour as a tie-breaker. **Done 2026-10-09 evening**
   (`fusion._split_touching`, `PartSpec.touching`): an outline the size check would call
   "n parts touching?" is cut into n cells along the multiplied side; every cell must hold 80 %
   of its rectangle and measure as the part. The three `touch_*` fixtures split into 2 / 2 / 3
   parts of 50 × 30; the leaner (74 × 49) does not, its second cell comes up short; the covered
   block stays "too tall" because the split only follows the size check's own verdict. Solid
   parts touching (the depth path) are not cut yet: no fixture. **Known limit**: at ±25 % a
   2 × 2 of 50 × 30 (100 × 60) and three across (90 × 50) fit the same outline about equally
   (the three-across frame: 0.62 vs 0.72 tolerances off); the fewer parts win. The seams in
   colour (visible side by side) would be the tie-breaker; not built.
3. **A "too close" guard at the camera's floor.** A white outline with no depth under it is taken
   for foam and given the part's height; when the blob's expected top sits inside the camera's
   minimum range, no depth means too close, not foam (P8: a 57 mm stack passed as 30 at 0.28 m).
   **Done 2026-10-09**: a hole blob whose top at the spec's height would be nearer than 0.24 m
   (`fusion.MIN_DEPTH_RANGE_M`) is refused as "too close to the camera to measure (0.23 m): look
   from higher up", drawn yellow.
4. **Partly covered and leaning parts** (P11): a footprint touching a taller blob is "partly
   covered?", not a part; a top face tilted more than a few degrees from the surface is not
   resting, and says so.
5. **Reasons**: a part twice the size in every direction is "too long / too tall", not "2 parts
   touching?" (P12). **Done 2026-10-09** (`partspec._why_not_as`): "n parts touching?" only when
   the other side is the part's own (or itself a multiple: a 2 × 2 is "4 parts touching?") and the
   height, when seen, fits; otherwise too long / too wide / too tall.
6. **Dark anodized tops read 3–5 mm small** (P2, P4; the cylinders' rim accounts for part of the
   height): a consistent bias for the datasheet, not a tuning target.
7. **The black mat** (S4): the rubber returns depth; what drops out is its white velcro strips.
   Parts read taller by the mat's thickness and a strip's end passed as a standing block once.
   The datasheet line is reworded accordingly. The 10-08 reading (blocks 42–62 mm tall) was the
   laser at full power on the other preset.

**Frames for items 2 and 4, captured 2026-10-09 evening** (`tests/fixtures/d435/`, from the parked
0.35 m view with `cell_sweep.py view … --no-move`): `touch_side_0p35m`, `touch_end_0p35m`,
`touch_three_0p35m` (one outline each, "2 / 2 / 3 parts touching?" once the side assignment was
fixed), `stack_0p35m` and `stack_0p28m` ("too tall" from both heights; this stack's top returned
99 % depth at 0.214 m), `lean_0p35m` (both tops 11–14 % depth: no tilt to read on foam, the
outline is all there is), `covered_0p35m` (a T: the top block at 56 mm swallows the lower one's
free end), `cable_0p35m` (the block passes at 49 × 34 with the cable clipped where it lies on the
table), `cyl_lead_0p35m` (the puck by depth, the lead nothing). `tests/test_fusion.py` holds them
to: nothing fused is ever a part, the counts are right, the cable and the lead cost nothing.

Not the detector: the D435 returns full depth on foam tops over white paper where over the grey
table it leaves 10–60 % holes (the surface's brightness decides); the side views past ~0.36 m
out on a UR3e end in a protective stop (a `movel` to a stretched pose; the endpoint passed IK);
big parts don't fit the picture at 0.35 m once the view shifts; a cable beside a part costs its
finger room, correctly.

### The orbit calibration, twice

Both runs found the mark, lost it in most views (17 of 21 "none within 40 mm of the predicted
mark"; the 0.21 m range entirely, below this camera's floor), solved on four, and `--apply` put
the result in force on the pick PC: a camera 0.23 m then 0.67 m off the flange, the table reading
84° off level. Restored by hand on the Pi both times. The guard is PR #87 (predict from the seed
until a dozen views; never apply under ten, or far from the seed); the mark finder itself (the
old white-blob path: blind to a white block on white paper, loses foam tops over the grey table)
is the TODO. **Do not run the orbit on this cell until that lands.**

### Fixtures

The day's sweeps saved the colour picture, the pose and the verdict but only the heat-map
rendering of the depth, so none of them is a detector fixture. `scripts/cell_sweep.py` now saves
the raw frame per view in the fixture's shape; the scenes to rerun for the bank, five minutes
each: P5, P6, P7 (touching), P8 at 0.28 m (the stack), P11 (leaning), P14 (the cable), P1's edge
block, S4's far-side view. One real fixture from the day is in the bank: the block on the black
mat, straight down at 0.35 m (`black_mat_block_0p35m`).
