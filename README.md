# perceptronics

A depth camera on the robot's wrist finds the part; the **3D Pick** node on the
pendant puts the gripper on it. This page gets it onto a Universal Robots e-Series
(PolyScope 5).

## Install it: one USB stick

**1. Download these two files** (both, from the same place, don't rename them):

- [`perceptronic-ps5-0.9.1.urcap`](https://github.com/JimothyJohn/perceptronics/raw/main/integrations/urcap/dist/perceptronic-ps5-0.9.1.urcap)
- [`urmagic_perceptronic.sh`](https://github.com/JimothyJohn/perceptronics/raw/main/integrations/urcap/dist/urmagic_perceptronic.sh)

**2. Copy them onto a USB stick**, at the top, not in a folder. The stick must be
FAT32 (most sticks are). Eject it properly before you pull it out.

**3. On the pendant, once per robot:** ☰ → **Settings** → **Security** → **General**
→ turn on **Run magic files** and **USB ports**.

**4. Power the arm off** (the robot stays on) and stop any program. **Plug the stick
in.** The pendant shows **! USB !**, then the robot restarts by itself. That's the
install.

**5. Use it.** **Installation** → **URCaps** → **Perceptronic**: type the camera
computer's address. In your program: *your gripper's Open* → **3D Pick** → *your
gripper's Close*.

If nothing happens at step 4: the arm was on or a program was running (you'll get a
popup saying to restart; restart the robot), or the magic files setting is off. You
can always install by hand: ☰ → **Settings** → **System** → **URCaps** → **+** → pick
the `.urcap` → **Open** → **Restart**. What happened is written to
`urmagic_perceptronic.log` on the stick.

The camera computer (a Raspberry Pi with the D435 on its USB port) is set up once:
[site/public/quickstart-ur.html](site/public/quickstart-ur.html). PolyScope X has no magic files; its URCap
installs through System Manager: [integrations/urcap/README.md](integrations/urcap/README.md).

## Developers: install from a PC over SSH

Same two files, same script, no stick: copy them to the robot and run the script
there. Your PC must be on the robot's network.

**Turn SSH on (PolyScope 5.10 and later):** ☰ → **Settings** → **Security** →
**Secure Shell** → enter the admin password → tick **Enable SSH Access**.

**Log in as `root`.** The factory default password is **`easybot`**
([UR: resetting passwords](https://www.universal-robots.com/articles/ur/robot-care-maintenance/resetting-passwords/)).
If it was changed, ask whoever owns the robot. Put your key on it so you never type
the password again (`ssh-copy-id`, or **Secure Shell** → **Manage Authorized Keys** on
the pendant), and change the default with `passwd`
([UR: secure setup](https://www.universal-robots.com/articles/ur/cybersecurity/secure-setup-of-ur-cobots/)):

```bash
ROBOT=192.168.1.50                       # your robot's IP address
ssh-copy-id root@$ROBOT                  # once: key login from now on
```

**Install** from a checkout of this repo (or wherever you downloaded the two files):

```bash
ssh root@$ROBOT 'mkdir -p /tmp/perceptronic'
scp integrations/urcap/dist/perceptronic-ps5-0.9.1.urcap integrations/urcap/dist/urmagic_perceptronic.sh root@$ROBOT:/tmp/perceptronic/
ssh root@$ROBOT 'bash /tmp/perceptronic/urmagic_perceptronic.sh'
```

The script checks the file's checksum, puts it where PolyScope's own URCaps screen
would, and restarts the controller when the arm is off and no program runs; otherwise
it tells you to restart. `URMAGIC_RESTART=always` (before `bash`) restarts regardless,
`=never` leaves it to you. Its log is `/tmp/perceptronic/urmagic_perceptronic.log`.

**After changing the URCap:** `make urcap5-package` rebuilds `integrations/urcap/dist/` (the `.urcap`
and the `.sh` with its new checksum), then run the three lines above again.
`scripts/urcap5-usb.sh` writes a stick from a Mac without the `._` files Finder leaves.

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
