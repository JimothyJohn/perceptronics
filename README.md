# perceptronics

A depth camera on the robot's wrist finds the part; the **Pounce** node on the
pendant puts the gripper on it. This page gets it onto a Universal Robots arm —
an e-Series on **PolyScope 5**, or a robot on **PolyScope X** (PolyScope 10). The
steps are the same on both; only the file and the pendant's menu differ.

## Install it: one USB stick, one file

**1. Download the URCap** for your pendant (don't rename it):

| Pendant | File |
| --- | --- |
| **PolyScope 5** (e-Series: UR3e, UR5e, UR10e, UR16e, UR20, UR30 …) | [`perceptronic-ps5-0.11.0.urcap`](https://github.com/JimothyJohn/perceptronics/raw/main/integrations/urcap/dist/perceptronic-ps5-0.11.0.urcap) |
| **PolyScope X** (PolyScope 10) | [`perceptronic-0.9.0.urcapx`](https://github.com/JimothyJohn/perceptronics/raw/main/integrations/urcap/dist/perceptronic-0.9.0.urcapx) |

Not sure which you have? PolyScope 5 shows **Installation** and **Program** tabs
along the top; PolyScope X has a **☰ menu** top-left with **System Manager** in it.

**2. Copy it onto a USB stick**, at the top, not in a folder. The stick must be
FAT32 (most sticks are). Eject it properly before you pull it out.

**3. On the pendant:** plug the stick in, then

| | PolyScope 5 | PolyScope X |
| --- | --- | --- |
| Open the URCaps screen | ☰ → **Settings** → **System** → **URCaps** | ☰ → **System Manager** → **URCaps** (unlock with the admin password) |
| Add the file | **+** → pick `perceptronic-ps5-0.11.0.urcap` → **Open** | **+** → pick `perceptronic-0.9.0.urcapx` |
| Finish | **Restart** when PolyScope asks | ☰ → **Reload** |

That's the install: the pendant's own URCaps screen, the same way every URCap goes
on. Nothing on the stick runs by itself, and the robot restarts only when you tap
Restart (PolyScope X doesn't restart at all).

**4. Use it.** Open the **Perceive** node and type the camera computer's address —
on PolyScope 5 under **Installation** → **URCaps** → **Perceive**, on PolyScope X under
**Application** → **Perceive**. In your program: *your gripper's Open* → **Pounce** →
*your gripper's Close*.

If the file picker lists a second `._perceptronic-ps5-0.11.0.urcap` (or
`._perceptronic-0.9.0.urcapx`), a Mac wrote the stick: pick the one **without** `._`
(or write the stick with `scripts/urcap5-usb.sh`, which leaves those off).

The camera computer (a Raspberry Pi with the D435 on its USB port) is set up once:
[site/public/quickstart-ur.html](site/public/quickstart-ur.html). PolyScope X can also
take the URCap over the network, with no stick, and needs its Primary interface and Remote
mode switched on once: [integrations/urcap/README.md](integrations/urcap/README.md).

## Developers: rebuilding the URCaps

**After changing a URCap:** `make urcap5-package` rebuilds
`integrations/urcap/dist/perceptronic-ps5-<ver>.urcap` and `make urcap-package` rebuilds
`integrations/urcap/dist/perceptronic-<ver>.urcapx` (commit them; a test holds each equal to a
fresh build). `scripts/urcap5-usb.sh` writes either to a stick from a Mac without the `._`
files Finder leaves, and the pendant's URCaps screen installs it as above.

## By hand: a cell in three commands

The toolkit was built to be driven by an agent; this is the door for a person. From a checkout
with any Python 3.10+ (nothing to install):

    python3 -m perceptronics init                     # a few questions -> ./mycell.env
    python3 -m perceptronics --cell ./mycell.env doctor   # camera, robot, calibration: what's wrong, with the fix
    python3 -m perceptronics --cell ./mycell.env up       # the cockpit; the page opens; the pendant reaches it

`init` asks for the robot (UR e-Series, PolyScope X, the simulator, or none), its address, the
arm, the tool length, the bracket and the camera, every answer with a default, and writes an
ordinary cell file you can edit. `up` is the cockpit with no flags: the camera, the robot from
the cell, listening where the pendant can reach it. On macOS the camera needs `sudo` in front.

**For an agent — the two MCP servers** (`MCP.md`): `urctl-mcp` for the robot and
`perceptronics-vision-mcp` for the camera and the 3D guidance, each one line in an MCP client's
config, each with a `--no-motion` setting that serves the readings and the planning without
anything that moves the arm.

## More

- [perceptronics/ARCHITECTURE.md](perceptronics/ARCHITECTURE.md): how it works, the code map, the cockpit's API, adding a robot, running it all without hardware
- [integrations/urcap/perceptronic-ps5/README.md](integrations/urcap/perceptronic-ps5/README.md): the PolyScope 5 URCap in full: upgrading, every screen
- [site/public/quickstart-ur.html](site/public/quickstart-ur.html): the kit, the camera computer, setting up a cell
- [perceptronics/README.md](perceptronics/README.md): the camera, depth quality, hand-eye
- [CLAUDE.md](CLAUDE.md): working notes, protocols, and the gotchas that cost real time

Working on perceptronics itself: `make install-dev`, `make test`, `make lint`; PRs go
to `dev` ([perceptronics/ARCHITECTURE.md](perceptronics/ARCHITECTURE.md#development)).
