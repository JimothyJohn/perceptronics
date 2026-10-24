# CLAUDE.md

**perceptronics** — vision-guided picking for Universal Robots arms: the `perceptronics` package and CLI
(`PERCEPTRONICS_*` variables; `perceptronics/cell.py` warns about a stale `PERCEPTION_*`), the `urctl` control
library / CLI / MCP server (`UR_*` variables, URCap bundle ids unchanged), the **Perceive / Pounce** URCaps for
PolyScope 5 and PolyScope X, the Docker-Compose'd URSim simulators, the pick PC (`deploy/pi/`) and the site.
No PyPI package. Most of what matters lives in the network protocols and file formats UR ships, not in the
code — the rule files below hold what took real time to discover; this file holds what every session needs.

**Hardware, addresses, what is connected today: `SETUP.md`** — update it when the cell changes. Open work:
`TODO.md` (incomplete tasks only). Nick's decisions: the assistant's project memory (decisions log, dated
answers), not the repo.

## Layout

```
docker-compose.yml          URSim e-Series 5.26.0 (UR10; 6080 noVNC, 29999-30004, 30020, 502) + the `ursim-px` PolyScope X 10.13.0 service (profile polyscopex; :8000, 31001, 31004)
urctl/                      Control library + CLI + MCP server + agent tools (HARNESS.md = the harness reference, PROGRAM-AUTHORING.md = program conventions)
perceptronics/              RGB-D cockpit, detector, pick server, cells/*.env, webui/ (README.md = the RealSense notes, ARCHITECTURE.md, cell.html = the dated explainer)
integrations/urcap/         The Perceptronic URCaps (perceptronic-ps5/ Java, perceptronic/ PolyScope X), their tooling, the committed dist/, the PS5 matrix compose file
deploy/pi/                  Pick PC installer, image, admin helper; PI.md (board log), PLUG-AND-PLAY.md (three-cable install), README.md
hardware/                   BOM.md + the D435 tool bracket (CadQuery)
site/                       perceptronics.advin.io (the only published pages; site.sh, build.py, public/)
requirements/               dev.{in,txt}, vision.{in,txt} — hash-pinned (CI + `make install-dev`)
scripts/                    poweron.sh, urp_convert.py (.script <-> .urp), cockpit.sh, deploy-pi.sh, pi-image.sh, pi-update.sh, pi-vision-install.sh,
                            urcap5-usb.sh, urcapx-autoinstall.sh, ufactory-sim.sh, ursim-e-vm.sh, volume_bench.py, cell_sweep.py, findability.py
tests/                      pytest (unit + URSim integration); fixtures/programs/ = sample .urp/.script, fixtures/d435/ = labelled real frames
```

Sibling docs: `MCP.md` (customer MCP servers), `TESTING.md` (cell experiment matrix), `ROBOT.md` / `PSX.md`
(the robot day on PolyScope 5 / X), `DEMO.md`, `AIR.md`, `ENTERPRISE.md`, `JETSON.md` (the GPU line).

## Stack

- **Pure stdlib runtime, no uv** — Nick's call ("completely remove UV from the equation since we don't have any
  dependencies"); this repo is the declared exception to the global uv default. Any Python ≥ 3.10 runs it from the
  checkout: `python3 -m urctl …`, `python3 -m perceptronics …`, `python3 -m perceptronics.mcp_server` (`.mcp.json`).
  macOS's `/usr/bin/python3` is 3.9 — use Homebrew's; `scripts/cockpit*.sh` check and take `PYTHON=`. Console
  scripts (`urctl`, `perceptronics`, `perceptronics-mcp`, …) exist only after `pip install .`.
- **Dev tools are the only third-party packages** (pytest, hypothesis, ruff, build, hatchling): `requirements/dev.in`
  lists, `requirements/dev.txt` pins with hashes; `make install-dev` builds `.venv`. Extras: `vision` (numpy/OpenCV/
  Pillow), `sam` (torch). `.claude/rules/ci.md` has the hash-update procedure.
- **Portable**: `urctl`, the cockpit and the MCP servers have zero dependencies and run on Windows / macOS / Linux,
  amd64 / arm64 (CI tests all four). External binaries only in the filesystem layer: `ssh` (real robot), `docker` (URSim).
- Lint: `ruff check` + `ruff format`, shellcheck. Tests: `pytest` (unit, no sim); integration needs a running URSim
  (`make test-integration`; in CI on pushes to `main` or PRs labelled `run-integration`).

## Commands

```bash
make install-dev                 # .venv + the pinned dev tools (pip, hash-checked)
make test                        # unit tests;  make test-integration needs URSim;  make lint = ruff + shellcheck
make sim-up / sim-poweron / sim-down          # e-Series URSim (amd64 only — on this Mac use scripts/ursim-e-vm.sh or CI)
HOST_ARCH=arm64 make simx-up                  # PolyScope X sim (UI :8000; enable Primary/RTDE once; Remote for anything mutating)
make doctor CELL=ur3             # pre-flight: SDK, camera, per-port reachability, modes, TCP, hand-eye (exit 1 = NOT READY)
make cockpit CELL=ur3            # the RGB-D cockpit (sudo on macOS for a real camera);  rs-gui-fake = synthetic scene
make urcap-package urcap5-package             # rebuild + commit integrations/urcap/dist/ after any URCap edit
python3 -m urctl state                        # JSON state (localhost);  --host 10.0.0.5 bring-up;  --dry-run validates + audits only
python3 -m urctl move-tcp 0 0.05 0 0 0 0 --relative   # safety-validated movel, +50 mm base +Y;  move-joints, tools, rtde-state --deep, snapshot
perceptronics-mcp --cell ur3                  # robot + camera tools over MCP stdio (perceptronics-vision-mcp = camera only)
```

Unit tests assume a clean shell: with `UR_CELL` (or `PERCEPTRONICS_*`) exported the handeye/webapp/cockpit tests
pick up the cell's defaults and fail — `env -u UR_CELL python3 -m pytest …`.

## Hard rules

- **The tool offset is the robot's, only** (Nick: "You must only use tool offsets inside of the robot not your own"):
  the cockpit, the pick server and both URCaps carry no tool length — the tool is the pendant's active TCP. Details: `cockpit.md`.
- **A new robot capability goes in one place**: a `Robot` method → a `Tool` in `urctl/tools.py` → (if a human needs it)
  a subcommand in `urctl/cli.py`. CLI, tool registry and MCP servers all sit on the same `Robot`. Mutating actions go
  through the safety envelope + audit log; a tool that moves the arm belongs in `MOTION_TOOLS` / `VISION_MOTION_TOOLS`.
- **Connection target is configurable, never hardcoded**: `UR_HOST` / `UR_DASH_PORT` / `UR_PRIMARY_PORT` / `--host`;
  the only `localhost` that stays is the compose healthcheck and the CI probe.
- **Detector change → `scripts/volume_bench.py` before and after**; the real frames in `tests/fixtures/d435/` are the arbiter.
- **URCap edit → `make urcap-package urcap5-package` and commit `integrations/urcap/dist/`**; a test holds the committed
  packages byte-equal to a fresh build. A conflicting PR shows *no checks at all* — rebase, rebuild, push.
- **Required checks on `dev`: `gate` and `URCap5 gate`.** A new required job must run (and answer) on every PR or it blocks
  the ones it skips.
- **PRs go to `dev`** (feature branch → PR); `main` is Nick's merge, never pushed directly.
- **Before changing anything public-facing** — links, owner or vendor names, the licence, a bundle id — check Nick's
  recorded decisions; when reality contradicts one, write the mismatch under `TODO.md`'s open questions and let him
  decide. Standing: `LICENSE` is Nick Armenta's; quick starts and links use `JimothyJohn/perceptronics` only.
- **Keep the dated pages true**: `SETUP.md` (hardware), `perceptronics/cell.html` (the explainer's field log — append when
  something is verified or changes), `deploy/pi/PLUG-AND-PLAY.md`, `MCP.md` (its tool tables are held to the registries by a test).
- **`perceptronics doctor` exits 1 on NOT READY** — the right answer on a machine with no robot; read the `verdict:` line,
  and remember `doctor | head; echo $?` reports `head`'s 0.
- **Don't bake real-robot kinematics into committed URPs**: `urp_convert.py`'s identity / checksum-off defaults work everywhere.
- **Don't `docker compose down` with unsaved PolyScope work**: URSim has no volume for `/ursim/programs/`; `docker cp` first.
- Don't commit a stray `uv.lock` (`uv run --with playwright …` leaves one).

## Where the detail lives

Path-scoped rules in `.claude/rules/` load when you touch the files they name:

| Rule | Covers | Loads for |
| --- | --- | --- |
| `ur-controller.md` | the `urctl` layer, port map, Dashboard cheat sheet, motion over Primary 30001, singularities, throughput, URSim vs real e-Series, the robot-side gotchas table | `urctl/**`, compose, the integration tests |
| `polyscope-x.md` | the REST Robot-API, Remote-mode gates, offset ports, `urctl --platform polyscopex` | `urctl/robotapi.py`, the PolyScope X URCap and sim |
| `programs.md` | `.urp` / `.installation` gzipped-XML schema, the node tree builder, URScript dialect, script-node motion for real cells | the converter, the builder, fixtures, `*.script` / `*.urp` |
| `cockpit.md` | RealSense, cells and doctor, hand-eye, pose stream, lost-link alarms, pick from the page, the tool offset, camera gotchas | `perceptronics/**` |
| `detection.md` | what a D435 cannot see, how `volume.py` reads a frame, the bench numbers | the detector, bench, `tests/fixtures/d435/` |
| `urcap.md` | Perceive / Pounce names and bundle ids, both URCaps, the pick-server protocol, the PS5 / PSX CI matrices, URCap traps | `integrations/urcap/**`, URCap workflows |
| `pick-pc.md` | the Pi, cell networking (192.168.3.20 / .3), setup portal and update bundles, BOM, site | `deploy/**`, `site/**`, `hardware/**` |
| `ufactory.md` | the UFACTORY 850 backend and its simulator | `urctl/xarm.py`, `urctl/ufactory.py` |
| `mcp.md` | tool registry, aliases, the customer MCP servers, the `Controller` protocol | tool / MCP / `Robot` files |
| `ci.md` | required checks, CI jobs, Dependabot and hash pins, release tags, the no-uv toolchain | `.github/**`, `requirements/**`, `pyproject.toml`, `Makefile` |

Skills in `.claude/skills/` are the procedures — use them, don't re-derive: **ur-control** (power on, read state, move,
jog, protective-stop recovery, load/play), **ur-program-authoring** (write / convert / run / save a `.script` / `.urp`),
**deploy-pick-pc** (deploy, update, roll back or diagnose the pick PC).
