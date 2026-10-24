---
paths:
  - "deploy/**"
  - "scripts/deploy-pi.sh"
  - "scripts/pi-image.sh"
  - "scripts/pi-update.sh"
  - "scripts/pi-vision-install.sh"
  - "scripts/urcap5-usb.sh"
  - "perceptronics/setupportal.py"
  - "perceptronics/cellnet.py"
  - "perceptronics/webui/setup.html"
  - "tests/test_deploy_pi.py"
  - "tests/test_pi_image.py"
  - "tests/test_setup_portal.py"
  - "tests/test_cellnet.py"
  - "hardware/**"
  - "site/**"
  - ".claude/skills/deploy-pick-pc/**"
---

# The pick PC, the cell network, the setup portal, the kit hardware and the site

`CLAUDE.md` always applies. This loads when you touch the Pi deployment, the cell networking, the setup portal, the BOM / bracket or the site. The procedure is the `deploy-pick-pc` skill; the human version is `deploy/pi/README.md`; `deploy/pi/PI.md` is the board log and `deploy/pi/PLUG-AND-PLAY.md` the three-cable install — **keep PLUG-AND-PLAY.md true when anything it names changes.**

**The kit** (`site/public/quickstart-ur.html`): `hardware/BOM.md` (sourced, dated prices), the bracket (`hardware/d435-tool-bracket/`), `deploy/pi/` (a Pi-class arm64 camera computer on minimal Debian: librealsense built pinned, the cockpit as the `perceptronics-cockpit` service on :7621/:7622, nftables; `scripts/deploy-pi.sh`), and the URCap (`urcap.md`).

**A robot nobody configured works (Nick, 2026-10-02: "assume their robots are not configured
network-wise").** The pick PC's cell port is **192.168.3.20/24** (`install.sh --cell-if eth0
--cell-address`, NetworkManager profile `perceptronics-cell`; a port already on another network
is left alone) and `perceptronics-cell-dhcp` (dnsmasq, one lease = the cell's `UR_HOST`
**192.168.3.3**, no route, no DNS) serves a robot left on DHCP — only after
`python -m perceptronics.cellnet probe` heard no other DHCP server there, re-probed by a
NetworkManager hook on every link-up. Both URCaps read an **empty Cockpit field as
192.168.3.20** (PS5 0.9.0, PolyScope X 0.7.0; the field shows it, `:7621` still means the
controller itself) and, when it is silent, tell the operator to put the robot on DHCP.
`tests/test_cellnet.py` holds the address equal in the Python, Java, JS and installer. UR's
factory network setting isn't documented: the manual says "select DHCP to enable networking";
verified only against the office DHCP server and a cable-less port on the Pi 5 (2026-10-02).

**Two rules `PLUG-AND-PLAY.md` depends on:** (1) a pick PC keeps its hand-eye in `PERCEPTRONICS_HANDEYE_FILE`,
**never** in `cell.env` — `install.sh`'s `handeye_out_of_env` seeds the file from the profile and
drops the line on every install, because an environment pose beats every `calibrate --apply` at the
next restart; (2) `perceptronics doctor`'s `network` line says whether this machine is on the
robot's /24 and what the pendant's Cockpit field needs (nothing at 192.168.3.20).

**Setup portal + update bundles (2026-10-03, Nick: "a setup portal ... at its default IP address",
`admin`/`admin` for now; bundles checksummed, **not signed** — his call).** `http://<pick PC>/setup` (port 80 → :7621 in the firewall; `:7621` works too)
(`perceptronics/setupportal.py`, `webui/setup.html`) changes the cell port's address/gateway/DNS, the
robot's address and the cell DHCP, and installs `perceptronics-update-*.tar` bundles
(`scripts/pi-update.sh bundle|push`). The cockpit only queues; root work is
`deploy/pi/perceptronics-admin` (stdlib, standalone, `.path`-triggered) → `install.sh --network` or the
bundle's own `install.sh --wheel`, health check on `/api/info`, automatic `--rollback`. Off unless
`PERCEPTRONICS_ADMIN_DIR` is set (only the Pi's unit sets it). Traps: (1) `/etc/perceptronics/network.env`
is install.sh's **default for every later run** — a redeploy without `--cell-if`/`--cell-address` keeps
what the portal chose; (2) after `--network` the port keeps `192.168.3.20/24` as a rescue address unless
the new network holds it; (3) the network rules live twice (helper + `setupportal.validate_network`) and
a hypothesis test holds them equal — change both; (4) install.sh must never restart
`perceptronics-admin.service` (an update runs install.sh from inside it); (5) a card flashed before
this has no portal: reflash it, or SSH with `deploy-pi.sh`. **Verified on a board** (`deploy/pi/PI.md` part 3 log): network change and back, update by `pi-update.sh push` and by the
page, rollback, the refusals. Two more rules from that run: (6) **every release keeps its deploy files
and its wheel** (`<release>/deploy`, `.wheel`) and `--rollback` re-runs the previous release's own
installer — the first version only swapped `current` and left the broken bundle's firewall and
`install.sh` behind; (7) a `--network` run computes `ALLOW_FROM` for the new network (the saved list
is an update's default, else the subnets the PC left stay open). Port 80 is the cockpit too
(nftables `redirect` to :7621), so the portal is `http://<pick PC>/setup`.

## Traps

- `scripts/deploy-pi.sh` builds the wheel with the first Python that has pip (`PYTHON=` first): the repo `.venv` has none and is often first on PATH.
- `site/site.sh datasheet` from an SSH shell: Chrome can't print without a display — `CHROME=` Playwright's `chrome-headless-shell` (`site/site.sh` header has the line).
