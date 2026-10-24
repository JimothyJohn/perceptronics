---
paths:
  - "perceptronics/volume.py"
  - "perceptronics/fusion.py"
  - "perceptronics/synthscene.py"
  - "perceptronics/partspec.py"
  - "perceptronics/pickplan.py"
  - "perceptronics/picknode.py"
  - "scripts/volume_bench.py"
  - "scripts/cell_sweep.py"
  - "scripts/findability.py"
  - "tests/fixtures/d435/**"
  - "tests/test_volume.py"
  - "tests/test_fusion.py"
  - "tests/test_partspec.py"
  - "tests/test_pickplan.py"
  - "tests/test_picknode*.py"
  - "TESTING.md"
---

# Detection: what the D435 can and cannot see, and how `volume.py` reads a frame

`CLAUDE.md` always applies. This loads when you touch the detector, its bench or its fixtures. **Run `scripts/volume_bench.py` before and after any detector change; the real frames in `tests/fixtures/d435/` are the arbiter.** The cell experiment matrix is `TESTING.md`.

**Detection (`perceptronics/volume.py`, reworked 2026-10-03; Nick: "more robust ... from a distance
similar to the robot arm", "assumed that they could be lying on either face", "drawing a line halfway
up the expected part height", "tying [the tolerance] to the distance").** One frame → parts:
1. **Surface**: a plane fitted near level (≤ 8°; > 1° adds a "hand-eye is out" note) — **unless the
   table as seen (RANSAC, any angle) is further off level than that and holds ≥ 1.3× more of the
   picture: then the base frame is lying** (a hand-eye badly out, a robot pose that isn't the
   camera's — 2026-10-06: a D435 on the bench 19° oblique with a simulator's pose saying straight
   down read every box 86-134 mm tall) and the table as seen is used, with a note that positions are
   off by as much (`OFF_LEVEL_SUPPORT`; fixture `boxes_on_carpet_0p8m_oblique`). Then a **local
   floor** — median + MAD of near-floor heights in tiles of 3 part lengths (≥ 15 cm), interpolated:
   heights are off the floor *round each part* (carpet: one plane leaves 5-7 mm, local 1.7 mm).
2. **Occupied** = over half the part's lowest face height *and* over 3.5 × the local spread (a note
   when roughness limits it).
3. Per blob: the **footprint is where it stands over half the expected height** (the spec's height on
   the face nearest the measured top) — the half-height line of a blurred step is its edge, and a white
   label can't split it. Far-side **ramps are undone** (`_unramp`: a cell lower than its neighbour
   toward the camera slides back `(top − h)·tanθ`). Footprints apart *on the surface* are separate
   parts even when the picture joins them; a part owns its footprint + blur margin + **its shadow**;
   what is left is looked at again (a low part beside a tall one).
4. Measure at full resolution (eroded one pixel), **trimmed-quantile rectangle** (`robust_rect`, 2-98 %),
   reject ledges (higher ground beside) and domes (shoulder heights round it).
5. **Size check**: any face down (`PartSpec.poses()`), tolerance never under `RANGE_SLACK` × range
   (1.2 %); past `MAX_PICK_RANGE_M` (1.6 m) nothing is picked.

Tools: `synthscene.Sensor`/`sense()` (D435 noise model, sized from the real frames below) and
`scripts/volume_bench.py` (random arm-distance cells vs truth: found / false picks / size bias) — **run
the bench before and after any detector change**. Real labelled frames: `tests/fixtures/d435/` (4 boxes
110×70×30 on carpet at 1.3-1.5 m, white labels; 2 flat + 2 on a side at 0.72-0.81 m, High Density;
carpet with a lump) — the arbiter over the model.
Numbers as of this rework: bench (0.28-0.60 m, hand-eye ≤ 1.5°) 99.4 % found, 0 false picks, size bias
+0.6 mm, heading p95 2.4°; real boxes 4/4 at 1.4 m, wrong sizes 0; ~1 s per frame on the Pi 5.

**What a D435 can't do — read before proposing detector work** (measured on the pick PC's D435,
2026-10-03, unless noted). These are the sensor's limits, not the software's; don't spend time trying
to process past them:
- **It doesn't measure parts.** Lateral blur is ~1 % of range (σ 12-16 mm at 1.4 m, **the same with
  the SDK filters off**: it is the stereo matcher's window, not our filters). Sizes are good to about
  ±max(5 mm, 1.2 % of range): it confirms a size *class*, it can't do metrology or QA, and two parts
  closer in size than ~2× that can't be told apart. Edges are blurred steps and corners round: there
  is **no perfect bounding box**, only a best edge estimate (the half-height line).
- **No defect inspection.** Anything under ~5 mm at 0.4 m (~15 mm at 1.4 m) is smoothed away;
  dents, chips, scratches, print and label content are invisible in depth.
- **Near and far.** Nothing closer than ~0.28 m (848×480). Error grows with z²: the good zone is
  0.30-0.60 m; usable for picking to ~1.5 m with looser sizes; past 1.6 m we never pick.
- **Heights need contrast against the surface.** Nothing stands out under ~3.5× the local surface
  spread: ~5 mm on a smooth table at 0.4 m, 10-18 mm on carpet at 0.85-1.4 m. Thin, flat parts
  (sheets, washers, labels) are invisible in depth.
- **Surfaces lie.** White labels / bright patches bias depth (one 30 mm box read 21-36 mm across its
  top at 1.4 m); dark, shiny, transparent surfaces drop out or read wrong; sunlight washes out the
  IR projector. **The preset decides how much drops out:** a dark, printed 30 mm-wide top at 0.72 m
  kept 43 % of its depth on High Accuracy (box missed) and 92 % on High Density (found, 110×31×71 for
  110×30×70) — hence High Density by default; holes can't be processed back, noise can.
- **Oblique views hide floor.** A part hides `height·tanθ` of floor behind it (54 mm for 30 mm at 61°)
  and the stereo **fills it with a ramp, not holes** — far edges stretch unless undone.
- **Averaging frames buys little.** Filtered temporal noise is 0.8 mm at 1.4 m (raw 2.1 mm); the error
  is spatial and static (swells, blur, material bias) and doesn't average out.
- **The surface is never one plane** over a whole view: swells grow with z² (±4 mm at 0.85 m over a
  carpet view). Fit locally.
- **Positions inherit calibration.** The detector tolerates a hand-eye tilted 2.5° for *finding*
  parts, but every 1° of hand-eye error is ~9 mm of grip error at 0.5 m.
- **Translucent tops are holes** (UR3e cell, 2026-10-08): white polyethylene foam returns 10-60 % depth
  on its top (the grey table beside it 100 %, white paper and blue felt 100 %) at any laser power, and
  the few pixels it does return are *biased*, not noisy (a consistent 62 mm on a 30 mm block) — never
  take a sparse median as a height. Bare metal will be worse. The depth alone found 1-2 of 4 such
  blocks; `perceptronics/fusion.py` (colour outline + depth, the `vision` extra) finds them when the
  part differs from the table in colour, and is the detector on a cell with numpy/OpenCV.
- **Matte black surfaces drop out entirely**: parts on a black rubber mat read 42-62 mm tall and
  fragmented from 0.30 m (the floor under them is unknown). A datasheet caveat, not a tuning problem.
- **Rest pose is ambiguous for near-cubes**: a box with two equal sides has no long axis (heading
  undefined), and faces of similar size can't be told apart by the camera.
Known gaps: one harsh-bench false pick in 351 (a tall box's fragment fitting another face); the
range-scaled tolerance also loosens the height check; a fixed deployment could subtract a taught
empty-surface depth map instead of fitting the floor (not built).
