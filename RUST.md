# Should perceptronics be converted to Rust?

Nick asked for the pros and cons of converting the entire codebase. **Short answer: no,
not the whole thing, and not now.** The list is below, the reasoning after it, and at the
end the one scope where Rust is worth reopening: the pick PC as a sealed appliance, which
the 2026-10-04 product decisions (one packaged kit, no network beyond the robot) make a
more credible case than it was a day ago.

Written 2026-10-03 against `dev`; brought up to date 2026-10-04 after the reorg, the prune
and the launch decisions (ENTERPRISE.md).

## Pros and cons at a glance

**For converting**

1. **CPU on the pick PC.** The one performance figure on record: the cockpit uses about
   70 % of one Pi 5 core just streaming (`deploy/pi/README.md`), all of it pure Python
   (PNG encoding in `pngio.py`, `bytes` copies, `volume.py` walking the depth grid with a
   stride to stay affordable). The same per-pixel work in Rust costs a small fraction.
2. **One static binary per target.** No "install Python ≥ 3.10", no `/usr/bin/python3`
   3.9 trap, no venv; the Pi image becomes one file plus a systemd unit. For a kit that
   ships set up to people who are not developers, that is real.
3. **A sealed appliance is now the product.** Nick decided (2026-10-04) that the kit is one
   packaged $2,500 box with no network beyond the robot. A box nobody edits in place is the
   case where a compiled daemon's distribution story beats edit-and-run.
4. **The camera FFI gets a type system.** `realsense.py` is 1,500 lines of `ctypes`:
   hand-written struct layouts, raw pointers, manual frame release, 61 `ctypes.` call
   sites. A `bindgen` binding with frames released in `Drop` turns layout and lifetime
   mistakes into compile errors.
5. **Concurrency invariants in types.** The cockpit is eight threaded modules around a
   camera pump, a 30 Hz RTDE pose stream, an HTTP server, the pick server and a Primary
   connection guarded by a non-blocking lock. `Send`/`Sync` and ownership would enforce
   some of what tests and conventions enforce today ("one program on Primary at a time"
   could be a value only one task can hold).
6. **Exhaustive protocol types.** RTDE recipes, Primary sub-packages, pick-server
   protocol 2 (16-number answers, status codes −4/−7/…), Robot-API responses and the
   UFACTORY wire protocol as `enum`s with exhaustive matches: a new status code breaks
   the build at every match that ignores it.
7. **Vendor-neutral seam as a library.** `urctl/controller.py` now has two real
   implementations (UR, UFACTORY). A Rust crate is a cleaner thing for a third vendor or
   another product to embed than a Python package that runs from a checkout.

**Against converting**

1. **The hard-won lessons are behavioural, not type errors.** The gotchas table in
   `CLAUDE.md` is Primary splitting top-level lines into programs, fire-and-forget moves
   racing the socket close, Local mode silently gating motion on hardware, PolyScope's
   MoveJ doing IK through the active TCP, an active TCP the controller reports but does
   not use, D435 colour going black at mismatched sizes, the macOS UVC claim race, the
   Robotiq daemon on loopback only. Rust hits every one of them again and needs the same
   workarounds; porting them is translation where every line can drop a subtlety.
2. **Zero dependencies becomes dozens of crates.** The runtime has no third-party
   packages today; `uv` was dropped for it (2026-09-30). Python's stdlib gives JSON,
   zlib, HTTP, sockets, ctypes, struct, threading, gzip and XML. Rust's `std` gives none
   of JSON, compression, HTTP or XML, so the port pulls `serde`, `serde_json`, a deflate
   crate, an HTTP server, an XML crate, `clap`, probably `tokio`: strictly more
   supply-chain surface, auditable with `cargo-deny` but not nothing.
3. **Edit-and-run goes away.** `python3 -m perceptronics` runs from any checkout with no
   build; an agent or Nick can change `volume.py` on the Pi over SSH and rerun it, and the
   cockpit page is read from disk per request. Rust is a compile per target and a cross
   toolchain for aarch64. (The appliance decision weakens this objection for the shipped
   box, not for the bench.)
4. **22,000 lines of tests do not port for free.** Hypothesis property tests, tests that
   hold the Java and the JavaScript to the Python (`test_urcap5_pick.py` reads
   `PickScript.tokens` back through the Python parser; `test_urcapx_pick.py` does the same
   for the JS), the URSim integration suite. Until rebuilt as `proptest` and Rust
   harnesses, the port is less tested than what it replaces, for the whole length of the
   port. That breaks the "regression test first" bar.
5. **Hardware verification resets to zero.** The field log (`perceptronics/cell.html`,
   `SETUP.md`, the dated paragraphs in `CLAUDE.md`) is evidence about *this* code: hand-eye
   RMS, `armfk` at 0.84 mm against the controller, picks that held, the Pi's first run. A
   rewrite is unverified on hardware until someone stands at the cell for every path
   again. And the cell day for the *current* code has not happened yet (TODO.md).
6. **The URCaps cannot move.** PolyScope 5 loads Java 8 OSGi bundles in its own JVM
   (6,400 lines here); PolyScope X runs JavaScript in its web front end (2,800 lines); the
   cockpit page is browser JavaScript (2,100 lines). The project is Python + Java + JS
   today and would be Rust + Java + JS afterwards. "One language per project" is already
   not true and a port does not make it true.
7. **The SAM backend stays Python.** `backends/sam.py` is torch + transformers. The Rust
   options (`candle`, `tch`, `ort`) are a separate port with model-export work;
   realistically it stays Python behind a process boundary, so the appliance would run
   Rust and Python.
8. **Velocity, now.** Several feature branches a day and design changes on Nick's
   feedback (the three-step node, the gripper removal, the reach model, tonight's prune).
   Compile-free iteration and agents' fluency in Python are part of how that works; Rust
   is faster once a design has settled, and the tending template, the re-pick, the log
   line and the Perceive/Pounce rename are all still ahead.
9. **No cheap middle.** A hybrid (PyO3 hot paths) breaks the stdlib-only, no-build regime
   with per-platform wheels, which is what dropping uv was meant to avoid. The options
   are "all of the pick PC" or "none", not "the hot loop".

## What would be converted (after the 2026-10-04 prune)

| Part | Language | Lines | Could it be Rust? |
| --- | --- | ---: | --- |
| `urctl/`: UR + UFACTORY clients, safety envelope, tools, MCP loop, CLI, workcell | Python | 8,600 | Yes |
| `perceptronics/`: RealSense binding, cockpit server, volume detector, pick node + planner, calibration, cells, setup portal | Python | 16,900 | Yes |
| `integrations/urcap/*.py`: URCap build, matrices, e2e, release tracking | Python | 3,500 | Yes, with little reason to |
| `deploy/`, `scripts/`, `site/`, the bracket's CadQuery | Python / shell | 4,100 | Partly (CadQuery is Python) |
| `tests/` | Python | 22,200 | Would be rewritten too |
| `integrations/urcap/perceptronic-ps5/` | Java 8 | 6,400 | **No.** PolyScope 5 loads OSGi bundles in its JVM. |
| `integrations/urcap/perceptronic/` (PolyScope X) | JavaScript | 2,800 | **No.** PolyScope X runs it in its web front end. |
| `perceptronics/webui/` | HTML/JS | 2,100 | **No.** It runs in the browser. |

"The entire codebase" is about 29,000 lines of Python runtime and tooling plus 22,000 of
tests; 11,000 lines of Java and JavaScript stay whatever happens.

## Part by part: would Rust be fundamentally better?

| Concern | Rust better? | Why |
| --- | --- | --- |
| Correctness against UR / UFACTORY controllers | No | The failures were behavioural; URSim, the UFACTORY simulator and the cell catch them, types do not |
| Geometry (`pose`, `armfk`, `armik`, `handeye`, `pickplan`, `volume`) | Marginally | Unit types (`Meters`, `Radians`) catch a class of mix-ups; none recorded was one |
| Pi CPU / streaming | **Yes** | Measured 70 % of one core in pure Python |
| Distribution of the appliance | **Yes** | One binary per target instead of a Python install; an update bundle is one file |
| Camera FFI robustness | Somewhat | Layout and lifetime errors become compile errors; librealsense's own crashes (one in the field log) remain |
| Threaded server invariants | Somewhat | Ownership encodes some locking; the cross-process Primary race remains |
| Supply chain | No, worse | Zero deps → dozens of crates |
| Dev and agent iteration | No, worse | Compile + cross builds vs edit-and-run |
| URCaps and the cockpit page | N/A | Fixed by PolyScope and the browser |
| Tests and hardware evidence | No, reset | 22k lines of tests and the field log apply to the Python |

## Recommendation

1. **Do not convert the codebase.** The costs are certain (tests, hardware re-verification,
   zero deps, velocity, three languages either way); the gains outside the Pi's CPU and
   distribution are modest, and the design is still moving.
2. **Profile the measured hot spot in Python first.** Nobody has profiled the 70 %. The
   candidates are PNG encoding (`pngio.py` already uses `zlib` level 1, so the cost is in
   the Python-side filtering and copying), `bytes` copies between the pump and the
   handlers, and encoding frames nobody is watching. `cProfile` on the Pi, then cheap
   fixes (`memoryview`, encode on demand, a cheaper live-feed format) that keep zero deps.
   Rust earns a place only if the profile says the floor is the interpreter.
3. **Reopen it, for one scope, when the appliance ships.** The 2026-10-04 decisions make
   the pick PC a sealed, networkless product. The right Rust scope then is **the pick-PC
   daemon only**: camera capture, the frame pipeline, `volume.py` detection, pick-server
   protocol 2 and the HTTP endpoints the URCaps and the setup portal call. Port it behind
   the existing wire protocols and keep the Python test suite as the black-box spec: it
   already drives HTTP and the pick-server socket, so it can drive a Rust daemon
   unchanged. `urctl`, the MCP server, calibration, the URCap tooling and the bench tools
   stay Python. Preconditions: the cell day has happened for the Python (so there is a
   verified behaviour to match), the profile in step 2 is done, and Nick signs off on the
   exception to "one language per project".
