---
paths:
  - "scripts/urp_convert.py"
  - "urctl/urp_builder.py"
  - "urctl/installation.py"
  - "urctl/PROGRAM-AUTHORING.md"
  - "tests/fixtures/programs/**"
  - "tests/test_urp_builder.py"
  - "tests/test_urp_convert.py"
  - "**/*.script"
  - "**/*.urp"
  - "**/*.installation"
  - ".claude/skills/ur-program-authoring/**"
---

# PolyScope programs: `.urp` / `.installation` formats, the node tree, URScript

`CLAUDE.md` always applies. This loads when you touch the converter, the URP builder, a program fixture or a `.script` / `.urp`. The authoring procedure is the `ur-program-authoring` skill; naming / blend / Move-grouping conventions are `urctl/PROGRAM-AUTHORING.md`; running motion over Primary is `ur-controller.md`.

## PolyScope file formats

`.urp` and `.installation` are both **gzipped XML** — not the XStream Java
serialization that the format name might suggest. You can read them with
`zcat file | xmllint --format -`.

### Minimum schema for a `.urp` PolyScope will load

(This is what cost me the most time to figure out — it was reverse-engineered
by diffing against real saved URPs and reading polyscope.log error messages
after each failed `load`. Encoded in `scripts/urp_convert.py:script_to_urp`.)

```xml
<URProgram name="X" installation="Y" installationRelativePath="Y"
           directory="/programs" createdIn="5.12.5.10626004"
           lastSavedIn="5.12.5.10626004" robotSerialNumber="">
  <kinematics status="NOT_LINEARIZED" validChecksum="false">
    <deltaTheta value="0,0,0,0,0,0"/>
    <a value="0,0,0,0,0,0"/>
    <d value="0,0,0,0,0,0"/>
    <alpha value="0,0,0,0,0,0"/>
    <jointChecksum value="0,0,0,0,0,0"/>
  </kinematics>
  <children>
    <MainProgram runOnlyOnce="false" InitVariablesNode="false">
      <children>
        <Script type="File">
          <cachedContents>...URScript...</cachedContents>
          <file resolves-to="file">/programs/X.script</file>
        </Script>
      </children>
    </MainProgram>
  </children>
</URProgram>
```

Four things PolyScope demands, all easy to miss:

1. `installation=` + `installationRelativePath=` naming a sibling
   `<name>.installation` file in the same directory.
2. A `<kinematics>` block. Even with `validChecksum="false"` the block
   itself must exist or `ProgramRootNodeLoad` returns null.
3. A `<MainProgram>` wrapper between top-level `<children>` and the actual
   program nodes.
4. `<Script type="File">` carries `<cachedContents>` (inline text) *and*
   `<file resolves-to="file">` (source path). `type="Code"` is for inline
   "Script Code" nodes and doesn't carry the file pointer.

The `<kinematics>` values can be zero/identity for URSim; real hardware
prefers values matching the installed robot's actual calibration.

### Authoring a *native node tree* (not a one-line script wrapper)

**Authoring conventions** (functional waypoint names, one Move node per motion
type, blend every non-stopping waypoint) live in
`urctl/PROGRAM-AUTHORING.md` — follow them when generating
programs.

`urp_convert`'s `script_to_urp` wraps a whole `.script` in a single
`<Script type="File">` node — PolyScope loads it, but the operator sees one
opaque "Script" line. When you want the program to look like real,
point-and-click UR nodes (MoveJ→Waypoint, If, Loop, Folder…) the `.urp` must
*be* that typed node tree. `urctl/urp_builder.py` (`UrpProgram` + `Waypoint`)
emits it. `.script → rich .urp` reconstruction is still impossible (URScript is
Turing-complete; the tree is gone once it's flat) — but **authoring** the tree
when *we* generate the program is straightforward.

Two findings, both verified by generating a `.urp` and watching `load` succeed
against the running sim (`tests/fixtures/programs/NodeTreeDemo/build.py` is a worked example;
`tests/test_urp_builder.py` + `TestUrpBuilderLoading` lock it in):

- **The kinematics envelope is load-critical for `<Script>` nodes.** A program
  with real (UR10e) `<kinematics>`/`jointChecksum="-1,…"` loads fine for
  Move/Waypoint nodes, but `ScriptNodeConversionStrategy` rejects the whole
  program ("not a valid file version"). The all-zero `NOT_LINEARIZED` envelope
  (identical to `urp_convert`'s) loads *every* node type, so the builder emits
  that unconditionally. Joint-space waypoints don't need calibration anyway.
- **Verified node set:** `Comment`, `Folder`, `MoveJ`/`MoveL` + joint-space
  `Waypoint`, `If` (raw expr or digital-in), `Loop` (counting), `Set` (digital
  out), `Popup`, and the hybrid `Script type="File"` (multi-line helper `def`s)
  + `Script type="Line"` (a call shown as one script line). `Wait` and
  `Script type="Code"` were tried and **rejected** by their conversion
  strategies — they're intentionally absent. Add a node type only after
  teaching it once in PolyScope (`load` the result over Dashboard to confirm)
  and diffing the save; do **not** ship guessed node XML.

The "load key functions and use them" pattern: put helper `def`s in a
`script_file(...)` node and call them from `script_line(...)` nodes, so the
visible flow reads as named operations (`close_gripper()`) instead of I/O
plumbing. `make regen-urps` runs any `tests/fixtures/programs/*/build.py` to refresh its `.urp`
(falling back to the `.script`→`.urp` converter for script-based samples).

## URScript dialect notes

These are gotchas I hit writing `tests/fixtures/programs/InspectionBot/InspectionBot.script`:

- **No resizable arrays.** Pose lists are fixed-size literals. Use a
  separate counter variable for "active length".
- **Function-scoped locals.** `local x = ...` is hoisted to the enclosing
  function. Putting `local` inside a `while` loop works syntactically but
  doesn't create a per-iteration variable; prefer top-of-function declarations.
- **No block-scoped locals + global assignment.** Assigning to a name
  without `local` inside a function writes the global. To avoid clobbering,
  pick distinct names or declare `local` upfront.
- **`request_*_from_primary_client` blocks indefinitely** until a client
  on Primary 30001 (PolyScope's own UI counts) answers. Useful in wizards;
  terrible if you forget there's no UI session attached.
- **`freedrive_mode([axes], feature=...)`** without args defaults to all
  six axes free. The axes list is `[x, y, z, rx, ry, rz]` in the chosen
  feature frame.
- **`str_cat(a, b)`** takes exactly two args. Chain it for >2 strings.
  `to_str(x)` stringifies anything; no `format()`.
- **`sync()`** must be called every iteration of a tight loop in URScript
  or the controller throws a runtime error about non-real-time execution.

### Build motion programs with script nodes (for real-robot cells)

```python
from urctl.urp_builder import UrpProgram

prog = UrpProgram("Dance", run_only_once=False)
prog.comment("Looping dance — raw movej() bypasses MoveJ-node IK validation")
prog.script_file(
    "dance",
    """def dance():
  movej([-0.7427, -2.1034, -2.5358, -0.0718, 1.5714, 2.9782], a=1.2, v=1.0, r=0.03)
  ...
  movej(home, a=1.2, v=1.0)   # final waypoint — no r= (see movej blend pitfall)
  sync()
end
""",
)
prog.script_line("dance()")
prog.save("tests/fixtures/programs/<Name>/<Name>.urp")
```

The operator sees one "Script: dance helper" definition + one "Script:
dance()" call line in the Program tree — less editable than native
Move/Waypoint nodes, but it's the difference between a program that
runs and one that pops "cannot reach the required pose" mid-cycle.
`tests/fixtures/programs/NodeTreeDemo/build.py` is the committed `script_file` + `script_line` example (there is no `Dance` fixture; `ElegantDance` is a plain `.script` → `.urp` conversion).

## Deeper development tasks

- **Adding a new sample program**: drop a `.script` under
  `tests/fixtures/programs/<name>/`, run `urp_convert.py to-urp` to produce the `.urp`,
  copy URSim's `default.installation` as `<name>.installation`.
- **Changing the URP schema**: edit `script_to_urp` in
  `scripts/urp_convert.py`, then add a unit test in
  `tests/test_urp_convert.py` and run an integration test
  (`tests/test_integration_ursim.py::test_generated_urp_loads`) to confirm
  PolyScope still accepts it.
- **Debugging a load failure**: tail `polyscope.log` in the container —
  it spells out exactly what's wrong even when Dashboard returns "unknown
  failure":
  ```bash
  sudo docker exec perceptronics-ursim-1 tail -f /ursim/polyscope.log
  ```

**Don't bake real-robot kinematics into URPs you commit.** The defaults shipped by `urp_convert.py` (identity, checksum off) are intentional — they work everywhere; calibrated values are robot-specific.

## Common gotchas (URP side)

| Symptom | Cause | Fix |
| --- | --- | --- |
| `load` returns `unknown failure`              | URP missing `installation=` attr or `<kinematics>`           | Use `urp_convert.py` or inspect `polyscope.log`     |
| `.script` files invisible in Load Program     | Default file filter is `*.urp`                               | Flip the filter, or convert with `urp_convert.py`   |
| URP plays forever — never reaches STOPPED     | `runOnlyOnce="false"` (PolyScope's UI default for cycle programs) | Regenerate URP without `--loop` (`urp_convert.py` default is `true`) |
| **On a real e-Series**, a `.urp` built with `UrpProgram.movej(Waypoint(...))` loads, plays the first few waypoints, then pops **"Robot cannot reach the required pose"** — yet `ur_move_trajectory` with the *same joint targets* runs clean | PolyScope's MoveJ node does FK→IK through the **active tool TCP** (`useActiveTCP="true"`, `positionType="CartesianPose"`). With a non-flange TCP (gripper, sensor — common, up to ~0.15 m on this robot), the FK pose can be outside reach even when the joints themselves are valid. Raw URScript `movej(joints)` skips the round-trip. Patching `kinematicsFlags="4"`→`"6"` (what PolyScope itself emits) does not fix it. | Don't use native Move/Waypoint nodes for real-robot cells with a non-flange TCP — emit motion via `prog.script_file("helpers", "def f(): movej(...) end")` + `prog.script_line("f()")`. See "Build motion programs with script nodes". |
