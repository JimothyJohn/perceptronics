# Should perceptronics be rewritten in Rust?

**Short answer: no, not the whole thing, and not now.** A rewrite would make a few
things better (the Pi's CPU budget, shipping one binary, memory safety at the FFI
boundary) and most of what makes this project hard no better at all. The bugs that cost
real time here were about how UR controllers, PolyScope, librealsense and the D435
actually behave, not about types or memory. Rust doesn't fix those, and a rewrite would
throw away the hardware verification that's been built up around the Python.

There's one narrow case where Rust is worth reopening, covered at the end: the pick PC
as a sealed appliance.

Written 2026-10-03 against `dev`.

## What would be converted

Line counts from `dev` (`wc -l`, comments and blank lines included):

| Part | Language | Lines | Could it be Rust? |
| --- | --- | ---: | --- |
| `urctl/`: controller clients, safety envelope, tools, MCP, CLI | Python | 7,100 | Yes |
| `perceptronics/`: camera, cockpit server, detection, pick planning, IK | Python | 16,200 | Yes |
| `tests/` | Python | 20,600 | Would have to be rewritten too |
| `scripts/` (incl. `urp_convert.py`) | Python | 2,200 | Yes |
| `urcap/` tooling (`urcap5.py`, `psx_matrix.py`, e2e drivers, `track.py`) | Python | 4,500 | Yes, though there's little reason to |
| `urcap/perceptronic-ps5/` | Java 8 | 6,500 | **No.** PolyScope 5 loads OSGi bundles in its own JVM. |
| `urcap/perceptronic/` (PolyScope X) | JavaScript | 2,800 | **No.** PolyScope X runs it in its web front end. |
| `perceptronics/webui/` | HTML/JS | — | **No.** It runs in the browser. |

So "the entire codebase" really means about 30k lines of Python runtime and tooling plus
about 20k lines of tests. Java and JavaScript stay whatever happens, because UR's
platforms dictate them. The project is multi-language now and would still be
multi-language afterwards.

## Where Rust would actually help

### 1. CPU on the pick PC (the only performance argument backed by a measurement)
`deploy/pi/README.md` records that on the Pi 5 the cockpit uses **about 70 % of one core
just streaming**, with `/api/color.png` taking a 27 ms median. All of that is pure
Python: `pngio.py` encodes PNG with `struct` + `zlib`, frames are copied around as
`bytes`, and `volume.py` walks the depth grid in Python loops (with a stride of 2–8 px to
keep that affordable). In Rust the same per-pixel work would cost a small fraction of
that. That's not a rounding error on a 4-core ARM board that might one day also run a
learned model.

On the other hand, nothing is blocked by it yet. Detection takes about 1 s, cycles are
30 s or more (machine tending), and the standing direction is quality over speed. The
headroom matters once the Pi is also doing something else, not before.

### 2. Shipping one static binary
A `perceptronics` binary cross-compiled for `aarch64-unknown-linux-gnu`,
`x86_64-pc-windows-msvc` and the two macOS targets would replace "install Homebrew
Python ≥ 3.10", the `/usr/bin/python3` 3.9 trap, `scripts/_python.ps1` hunting for a
non-Store Python, and `setup-windows.ps1` installing it through winget. For a kit that
ships already set up to customers who aren't developers, that's real simplification. The
Pi image (`scripts/pi-image.sh`) would ship one file plus a systemd unit.

### 3. Safety at the FFI boundary
`realsense.py` is about 1,600 lines of `ctypes`: hand-written `Structure` layouts, raw
pointers, manual frame release. A wrong field order there means silent garbage or a
segfault, and the field log already has one librealsense crash after a disconnect
mid-open. A Rust binding (`bindgen` over `rs2_*.h`, with frames released in `Drop`)
turns the layout and lifetime mistakes into compile errors. The C library underneath is
still C++, though, so that crash would still be possible.

### 4. Concurrency that is shared state by construction
The cockpit is threads around a camera pump, a 30 Hz RTDE pose stream, an HTTP server,
the pick server on `:7622`, and a Primary connection guarded by a non-blocking lock
(`PrimaryBusyError`). In Python those invariants live in conventions and tests. In Rust,
`Send`/`Sync` and ownership enforce some of them at compile time. For example, "one
program on Primary at a time" could be a type that only one task can hold.

### 5. Exhaustive protocol types
RTDE recipes, Primary sub-packages, pick-server protocol 2 (16-number answers, status
codes −4/−7…), and Robot-API responses would all become `enum`s and structs with
exhaustive matches. Adding a status code would break the build at every match that
doesn't handle it.

## Where it hurts, or doesn't help

### 1. Most hard-won lessons in this repo aren't the kind Rust catches
Look at the gotchas table in `CLAUDE.md`. It covers: Primary splitting each top-level line
into its own program, fire-and-forget moves that race the socket close, Local mode
silently gating motion on hardware, PolyScope's MoveJ doing IK through the active TCP, an
active TCP the controller reports but doesn't use, D435 colour going black at mismatched
sizes, the macOS UVC claim race, the Robotiq daemon bound only to loopback. A Rust
version would hit every one of them again and would need the same workarounds. That
knowledge is encoded in the Python and its tests, and porting it is translation work
where every line has a chance to drop a subtlety.

### 2. The zero-dependency property gets worse, not better
Today the runtime has **no third-party packages**. That's a deliberate decision: uv was
dropped for it on 2026-09-30. Python's stdlib provides `json`, `zlib`, `http.server`,
`socket`, `ctypes`, `struct`, `threading` and `gzip`/`xml` (for `.urp`). Rust's `std`
has none of JSON, compression, HTTP or XML. A Rust port would pull in at least `serde` +
`serde_json`, a deflate crate (`flate2`/`miniz_oxide`), an HTTP server, an XML library
for `.urp`/`.installation`, probably `clap` and possibly `tokio`. That's dozens of crates
transitively. You can run that through `cargo --locked` and `cargo-deny`, but it's
strictly more supply-chain surface than "nothing".

### 3. "Run it from the checkout" goes away
Right now `python3 -m perceptronics` works on any machine with Python and no build step.
Agents and you can edit `volume.py` on the Pi over SSH and rerun it. The cockpit page is
read from disk on every request. Rust replaces that with a compile per target, a release
pipeline per target, and a cross toolchain for aarch64. You gain distribution
simplicity (point 2 above) and lose the edit-and-run loop that this project leans on
heavily.

### 4. The test suite is the real asset, and it doesn't port for free
There are 20,600 lines of tests, including hypothesis property tests and tests that hold
other languages to the Python. `test_urcap5_pick.py` reads the Java `PickScript.tokens`
back through the Python parser. `test_urcapx_pick.py` does the same for the JS.
`test_the_script_is_the_polyscope_5_nodes_line_for_line` compares both nodes' URScript.
All of that would have to be rebuilt as `proptest` + Rust harnesses, and until it was,
the rewrite would be less tested than what it replaces. That breaks the "bug fix →
regression test first" bar for the whole length of the port.

### 5. Hardware verification resets to zero
The field log (`docs/realsense-cell.html`, `SETUP.md`, the dated paragraphs in
`CLAUDE.md`) records what has run on the UR3e + Hand-E: hand-eye RMS, `armfk` at 0.84 mm
against the controller, picks that held, the Pi's first run. All of that is evidence
about *this* code. A rewrite is unverified on hardware until someone stands at the cell
again for every path: bring-up, calibrate, pick, freedrive, gripper, the pick server
against the URCap.

### 6. Optional ML backends stay in Python anyway
`backends/sam.py` and `backends/depth_anything.py` use torch + transformers. The Rust
options (`tch`, `candle`, `ort`) exist, but they're a separate port with their own model
export work. Realistically the learned backends would stay Python behind a process
boundary, so the project ends up Rust + Python + Java + JS.

### 7. Velocity
This repo moves fast: several feature branches a day and design changes on Nick's
feedback (the 3D Pick rework, the gripper removal, the reach model). Python's
compile-free iteration and agents' fluency with it are part of how that works. Rust
iterates more slowly on exploratory geometry and UI-adjacent server code. It's faster
once the design has settled, and most of this design hasn't.

### 8. The global rule cuts both ways
"One language per project" argues for a full port, not a hybrid. A hybrid (PyO3 hot
paths) would break the stdlib-only, no-build regime: compiled extension modules mean
per-platform wheels, which is exactly what dropping uv was meant to avoid. So the
realistic options are "all Rust" or "no Rust". There's no cheap middle.

## What "fundamentally better" would mean, part by part

| Concern | Rust better? | Why |
| --- | --- | --- |
| Correctness against UR controllers | No | The failures were behavioural; tests against URSim and the cell catch them, types don't |
| Geometry (`pose`, `armfk`, `armik`, `handeye`, `pickplan`) | Marginally | Unit types (`Meters`, `Radians`) would catch a class of mixups; nothing recorded was one |
| Pi CPU / streaming | **Yes** | Measured 70 % of one core in pure Python |
| Distribution to customers | **Yes** | One binary per target instead of a Python install |
| Camera FFI robustness | Somewhat | Layout and lifetime errors become compile errors; librealsense's own crashes remain |
| Threaded server invariants | Somewhat | Ownership encodes some locking; the cross-process Primary race remains |
| Supply chain | No, worse | Zero deps → dozens of crates |
| Dev/agent iteration speed | No, worse | Compile + cross builds vs. edit-and-run |
| URCaps | N/A | Java/JS are fixed by PolyScope |
| Test assets and hardware evidence | No, reset | ~20k lines of tests and the field log apply to the Python |

## Recommendation

1. **Don't convert the codebase.** The costs (tests, hardware re-verification, zero
   deps, velocity) are certain. The gains, outside the Pi's CPU and distribution, are
   modest.
2. **Profile the measured hot spot in Python first.** Nobody has profiled the 70 % yet.
   The candidates are PNG encoding (`pngio.py` already uses `zlib` level 1, so the cost is
   in Python-side filtering and copying, not the compressor), `bytes` copies between
   pump and handlers, and encoding frames nobody is watching. `cProfile` on the Pi, then
   cheap fixes (`memoryview`, encode-on-demand, a cheaper live-feed format) that keep zero
   deps. Rust earns its place only if the profile says the floor is the interpreter.
3. **Reopen this if one of these becomes true:**
   - The pick PC runs out of CPU doing something you actually need (a second camera, a
     learned detector next to the cockpit), *after* step 2.
   - The pick PC becomes a sealed product appliance where customers never see Python,
     and a single signed binary + systemd unit is worth a release pipeline.
   - The vendor-neutral seam (`urctl/controller.py`) grows a second real controller (the
     uFactory branch, a Fanuc) and the protocol layer needs to be a stable library that
     others embed.

   If that happens, the right scope is **the pick-PC daemon only**: camera capture,
   frame pipeline, `volume.py` detection, pick server protocol 2 and the HTTP endpoints
   the URCaps call. Port it behind the existing wire protocols and keep the Python test
   suite as the black-box spec: it already talks HTTP and the pick-server socket, so it
   can drive a Rust daemon unchanged. `urctl`, the MCP servers, calibration and the dev
   tooling would stay Python, as a separate deliverable in the repo. That would need an
   explicit sign-off as an exception to "one language per project".
