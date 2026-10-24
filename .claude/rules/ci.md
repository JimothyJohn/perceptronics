---
paths:
  - ".github/**"
  - "requirements/**"
  - "pyproject.toml"
  - "Makefile"
---

# CI, required checks, releases and the no-uv toolchain

`CLAUDE.md` always applies. This loads when you touch the workflows, the pinned requirements, `pyproject.toml` or the Makefile. The global `cloud-security.md` and `dependency-review.md` rules load beside it.

**Required checks on `dev`: `gate` and `URCap5 gate`.** `URCap5 gate`
(`urcap5-matrix.yml`) passes at once on a PR that doesn't touch the URCap's paths and only on a
green `build` + every PolyScope version on one that does — so auto-merge can't land a red
URCap and the matrix never blocks unrelated PRs. Before a new required job, make sure it runs
(and answers) on every PR, or it blocks the ones it skips.

**CI/CD** (`.github/`): every PR runs lint (ruff check + format, shellcheck),
unit tests on Python 3.10/3.12/3.14, and a packaging job that builds the wheel,
verifies it carries `perceptronics/webui/` + the vendored `_urp_convert.py`, and
smoke-installs it. Integration tests (URSim boot) run on pushes to main or on
PRs labeled **`run-integration`**. Dependabot maintains the pinned dev requirements (pip), action pins,
and simulator images (weekly/monthly, grouped); minor/patch non-simulator
bumps auto-merge once CI is green (`dependabot-auto-merge.yml` — needs
"Allow auto-merge" enabled in repo settings). CodeQL scans Python + JS weekly
and per PR. Tagging `v<version>` (matching `urctl.__version__`) builds, tests,
and attaches the sdist + wheel to a GitHub Release (no PyPI package). The PolyScope 5
URCap has its own tag line: `urcap5-v<Bundle-Version>` attaches the committed
`integrations/urcap/dist/*.urcap` + sha256 to a GitHub Release after `urcap5.py release-check`
proves it is the tagged sources' build (`release-urcap5.yml`; CI never rebuilds it —
the URCap API jars exist only in the URSim image).

**No uv (Nick: "completely remove UV from the equation since we don't have any
dependencies") — this repo is the exception to the global Python → uv default.** The core
(`urctl` + perceptronics core) is pure stdlib, so nothing is installed to run it: any Python
≥ 3.10 runs it from the checkout as `python3 -m urctl …` / `python3 -m perceptronics …` /
`python3 -m perceptronics.mcp_server` (`.mcp.json`). macOS's own `/usr/bin/python3` is 3.9 — use
Homebrew's; `scripts/cockpit*.sh` check and take `PYTHON=`. The console scripts (`urctl`,
`perceptronics`, …) exist only after `pip install .`. numpy/OpenCV/torch are optional extras
(`python3 -m pip install -e ".[vision]"`).

The only third-party packages are the **development tools** — pytest, hypothesis, ruff, build,
hatchling. `requirements/dev.in` lists them; `requirements/dev.txt` pins them and everything
they pull in, with hashes, for every supported Python and OS (`requirements/vision.txt` does
the same for the `vision` extra). CI installs with `pip install --require-hashes -r …` (the
lockfile rule, kept) and builds with `python -m build --no-isolation` so hatchling is the
pinned one. Dependabot's `pip` ecosystem updates the pins and their hashes; a bump that needs a
*new* transitive package fails the hash check in CI — add it to the `.txt` by hand (name,
version, `--hash` lines from PyPI). There are no Windows launchers and no Windows Docker path
(the pick PC is the cell's computer); the Windows unit-test leg stays because the runtime is portable.

```bash
make install-dev                              # .venv + the pinned dev tools (pip, hash-checked)
make test                                     # unit tests (.venv/bin/python -m pytest)
python3 -m urctl state                        # run the CLI: no env needed
```

**The committed packages in `integrations/urcap/dist/` conflict on a rebase** whenever anything packaged changes on `dev` — the LICENSE included — and a conflicting PR shows **no checks at all**: rebase, delete the conflicted files, `make urcap-package urcap5-package`, push (`urcap.md` §Traps).
