# AIR.md — the MacBook Air: setup, the office session, the demo, the honest numbers

For Nick's MacBook Air (no Docker, no simulators) on 2026-10-07: pull this repo, talk to the
pick PC and the real UR3e at the office, run the findability and accuracy measurements, swap
the website's simulated pictures and numbers for real ones, then the customer demo (`DEMO.md`).
Everything here is copy-paste. Where a step was done on the Mac Studio the night before, it
says so.

## 1. The Air, once (15 min)

```bash
# Homebrew python (macOS's own /usr/bin/python3 is 3.9; the runtime needs 3.10+ and nothing else)
brew install python@3.13 git          # or whatever brew offers; 3.11-3.14 all work
git clone https://github.com/JimothyJohn/perceptronics.git ~/github/perceptronics
cd ~/github/perceptronics && git checkout dev && git pull
python3 -m perceptronics --help        # the CLI runs from the checkout, no install
python3 -m perceptronics cells         # ur3 is the cell
```

Optional, only for the dev tools (tests, ruff) — not needed for the day:
`make install-dev` (pip with hashes, a `.venv`).

**Network.** The Air joins the cell through its USB-C Ethernet adapter, static:
System Settings → Network → the adapter → Details → TCP/IP → Configure IPv4 **Manually**,
IP `192.168.3.10`, mask `255.255.255.0`, no router. (Never DHCP on the cell: the pick PC's
one-lease DHCP server would hand the Air the robot's address.) The office switch has the
robot (`192.168.3.3`), the pick PC (`192.168.3.20`) and the Air.

**SSH to the pick PC** (optional; the HTTP path below covers the day):
the Pi takes keys only. On the Air: `ssh-keygen -t ed25519` if there is none, then send
`~/.ssh/id_ed25519.pub` to Claude on the Studio (it goes into the Pi's `authorized_keys`), or
from the Studio yourself: `ssh nick@10.0.0.56 'echo "<the Air's key line>" >> ~/.ssh/authorized_keys'`.
Then `ssh nick@192.168.3.20 true`.

## 2. First thing at the office: the pick PC is on the UR3e profile (2 min)

The night of 2026-10-06 the Pi was pointed at the PolyScope X simulator for the website's
pictures. **Before anything else:**

```bash
curl -s http://192.168.3.20/api/info | python3 -c "import json,sys;d=json.load(sys.stdin);r=d['robot'];print(r['host'],r['platform'],'tip',r['approach']['tip_m'],'handeye',r['handeye']['source'])"
```

Want `192.168.3.3 e-series tip 0.163 handeye file:…`. Anything else (`192.168.3.10 polyscopex`):
put the UR3e profile back — with SSH, from the checkout:

```bash
PYTHON=$(which python3) scripts/deploy-pi.sh nick@192.168.3.20 --cell ur3 --robot-host 192.168.3.3
```

Without SSH: `http://192.168.3.20/setup` (admin / admin) → Software update → the bundle
(`perceptronics-update-0.1.0-8f499f563721.tar`, on the Studio's Desktop — copy it to the Air)
restores the code but **not** the profile; the profile needs the deploy or the saved file
(`/etc/perceptronics/cell.env.ur3-20261006` on the Pi). So: get the key on the Pi.

## 3. The office session with the real UR3e (2-3 h) — `ROBOT.md` phases 1-5, plus the numbers

Run `ROBOT.md` phases 1-5 as written (cables, URCap 0.9.1 from the stick — it is on the stick
since 2026-10-06 night, the detector's verdict, hand-eye, the cockpit pick, the pendant program).
`DEMO.md` §3 is the same list cut to the demo. The commands from the Air:

| What | From the Air |
| --- | --- |
| the doctor | `curl -s http://192.168.3.20/api/doctor \| python3 -c "import json,sys;[print(('ok  ' if c['ok'] else 'FAIL'),c['name'],'-',str(c.get('detail') or c.get('message') or '')[:100]) for c in json.load(sys.stdin)['checks']]"` |
| the robot, read-only | `python3 -m urctl --host 192.168.3.3 state` |
| the cockpit page | `http://192.168.3.20/` (the point cloud in the robot's frame, the live pose, LEVEL) |
| the detector's verdict | the scene query in `ROBOT.md` phase 3 (your block size in `part=`) |
| save a frame | `curl -s -o frame.rgbd http://192.168.3.20/api/rgbd` and `curl -s -X POST http://192.168.3.20/api/snapshot` |
| bring up / stop | the cockpit page's Pilot panel, or `python3 -m urctl --host 192.168.3.3 bring-up` (Remote for moves) |

### 3a. Findability vs distance and part size (the datasheet number, 45 min)

The question the two larger boxes are for: **the smallest part the camera finds at a given
distance**. Expect it to be a function of distance (the D435's lateral blur is ~1 % of range,
its depth noise grows with range², and a part must stand ≥ 3.5× the local surface spread above
the table — ~5 mm on a smooth table at 0.4 m, 10-18 mm on carpet at 0.8-1.4 m) and to be
compensated by the node's **closer look** (0.30 m). The simulated table is in
`site/public/datasheet.html` (marked simulated, 2026-10-06, from `scripts/findability.py`);
today's measurement replaces it.

Parts on the table: every block and box you have, sizes with a rule. Then, for each camera
height over the parts — **0.30, 0.40, 0.50, 0.60, 0.80, 1.00 m** (jog the arm straight up
between runs, pendant in Local is fine; the cockpit page's live pose shows the height):

```bash
# one line per height: which parts are found at which size, with the detector's own measurements
for part in 110x70x30 60x40x30 <each size you have>; do
  curl -s "http://192.168.3.20/api/pick/scene?opts=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(' part=$part tol=25 order=LR,FB gripcheck=1 room=20 arm=UR3e proto=2'))")" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print('$part', 'range', d['parts'] and d['parts'][0].get('range_m'), 'found', len(d['parts']), [(p['size_mm'],p['height_mm']) for p in d['parts']], 'near', [(p['size_mm'],p['height_mm'],p['why']) for p in d['rejected'] if p['near']], d['notes'])"
done
curl -s -o frames/height_<h>.rgbd http://192.168.3.20/api/rgbd     # keep every frame (fixtures)
```

Record per height: found / not, measured size vs the rule, the `notes`. The row where the
smallest block stops being found is the datasheet's line. Then one run with **Closer look on**
in the node from the picture point at 0.8 m: does the closer look recover the small ones?

### 3b. Accuracy (20 min)

With the hand-eye checked (LEVEL < 0.5°; `perceptronics calibrate --apply` from the Pi if not —
`ROBOT.md` phase 4): the cockpit's locate on a block corner you can measure from the base
with a rule, three blocks, two heights. Record located vs measured (mm). Then one pick each
through the node: where the fingertips land relative to the block's centre, by eye and a rule.

### 3c. Pictures for the website (10 min)

Replace tonight's simulated pictures with real ones, same file names, same crops:

| File (in `site/public/live/`) | What to capture |
| --- | --- |
| `pendant-3d-pick.jpg` | the 3D Pick teach screen on the pendant with the blocks green and numbered (pendant screenshot: ☰ → … or a phone photo straight on) |
| `pendant-installation.jpg` | Installation → URCaps → Perceptronic with the live picture and a located block |
| `cockpit-scan.jpg` | `http://192.168.3.20/` on the Air, the point cloud under the arm's linkage |
| `cell.jpg` | a phone photo of the cell: UR3e, bracket, D435, the Pi on the cable |

Then on the Air: `site/site.sh build` (no Chrome needed) and look at `site/_build/index.html`;
the PDFs are reprinted on the Studio (`site/site.sh datasheet`, headless shell) — commit the
pictures and the datasheet numbers, push, and the site deploys from `master` as always.

## 4. The demo — `DEMO.md`

## 5. Rules for the day

- One process on Primary: nothing from the Air while the pendant's program runs.
- Two failed attempts at a step → stop, write what happened, read `DEMO.md` §5.
- Keep every frame and every number, including the bad ones: the datasheet says what the
  camera does, not what we hoped.
