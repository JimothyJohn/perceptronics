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
| P5 | two blocks touching, long side to long side | splitting one blob into two parts | |
| P6 | two blocks touching, end to end (a 100×30 bar) | the same, along the length | |
| P7 | four blocks pushed into a 2×2 cluster | the same, in both directions | |
| P8 | one block stacked on another | a 60 mm "part" must not pass as 30 | |
| P9 | one block half under another | the lower one must not pass; the upper may | |
| P10 | a block on its side (30×30 face up, 50 tall) | any face down | |
| P11 | a block on end, leaning on another | neither should pass | |
| P12 | a 100×60×60 box among 50×30×30 blocks | a distractor of the wrong size, rejected with why | |
| P13 | the bars among the blocks, part = the blocks | dark distractors | |
| P14 | a block with a lead or cable across it | the outline, the finger room | |
| P15 | a block at each edge of the picture, side faces showing | the colour outline swallowing a side face | 2026-10-09 `v4` (one miss) |
| P16 | one part only, then eight | count independence, the pick order | |
| P17 | a hand or a tool in the picture during the look | clutter that must not pass | |

### Surfaces (the baseline blocks, P1 layout)

| | Configuration | What it tests | Run |
| --- | --- | --- | --- |
| S1 | the grey table | the baseline | 2026-10-09 |
| S2 | a basswood board on the table | a raised, patterned surface; its edge | 2026-10-09 `wood` |
| S3 | white paper on the table | white on white (the depth returns on paper) | 2026-10-09 `paper` |
| S4 | the black rubber mat | the datasheet says it drops out — confirm or retract under 0.10.1 | |
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

## Results, 2026-10-09 (UR3e, grey table unless noted, hand-eye of 2026-10-08)

The table read 1.5–2.7° off level in every view all day: the calibration, to be redone first.

| Parts | Surface | Straight-down views | Other views | Sizes read | Spread across views |
| --- | --- | --- | --- | --- | --- |
| foam blocks 50×30×30 | grey table | 3/3, 3/3, 2/3 (one at the edge read 40 wide, "too wide") | oblique 18° 3/3; 0.28 m 1/1 in view; turned 3/3 | 48–54 × 29–33 × 29–33 | 6–8 mm, 1° |
| black bars 90×40×12 | grey table | 3/3 ×3 | oblique 1/3 (two merged; one lost finger room); 0.28 m 3/3; turned 3/3 | 89–97 × 38–43 × 10–12 | 4–8 mm, 1.5° |
| cardboard boxes 100×60×60 | grey table | 3/3, 2/3, 3/3 (cut off at the edge) | oblique 3/3 (best sizes); 0.28 m 0/3 (none whole in the picture); turned 1/3 | 90–101 × 57–62 × 58–60 | 4–9 mm, 0.5° |
| foam blocks ×4 | basswood board | 4/4 (sides out of reach) | oblique 4/4; 0.28 m 3/4; turned 3/4 | 45–50 × 25–30 × 29–32 | 2–5 mm, 2–6° |
| foam blocks ×4 | white paper | 4/4, 4/4 (then a protective stop on the near-side view) | — | 46–49 × 28–30 × 28–30 | 3–5 mm, 6° |
| black cylinders 75 Ø × 18 (a 3–4 mm rim) | grey table | 2/3 (a cable beside one), 3/3, 3/3 | oblique refused; 0.28 m 3/3; turned 3/3 (one merged with its cable) | 69–74 Ø × 14–16 | 8–13 mm |

What the day put on the detector's list:

1. Clip the colour outline to the depth footprint's half-height line: a block at the picture's
   edge shows its side face and the outline swallows it (50 → 40 mm wide, rejected).
2. Split a blob by the part's size: two bars in the oblique view read as one 151 × 60; a cylinder
   and its cable as 87 × 74.
3. Dark anodized tops read 3–5 mm small in diameter and 3–4 mm low (the cylinders' rim accounts
   for part of the height): a consistent bias for the datasheet, not a tuning target.
4. The D435 returns full depth on foam tops over white paper, where over the grey table it left
   10–60 % holes: the surface's brightness, not the part's, decides it.

Not the detector: the side views past 0.36 m out on a UR3e end in a protective stop (a `movel`
to a stretched pose; the endpoint passed IK); big parts don't fit the picture at 0.35 m once the
view shifts; a cable beside a part costs its finger room, correctly.
