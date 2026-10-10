# TODO

Incomplete work only (Nick, 2026-10-10: "it should only hold incomplete tasks"). Decisions,
answers and status live in ENTERPRISE.md §10 and the assistant's decisions log, not here. Tick
an item or delete it; don't annotate it.

## On the cell (UR3e + Hand-E + the Pi)

The Pi and the pendant move together: a 0.9.x node against the new camera computer answers
"pick server status -14" (update the URCap), the new node against an old camera computer -9.

- [ ] **Update the cell to 0.11.0:** deploy this `dev` to the Pi (`scripts/deploy-pi.sh`), install `integrations/urcap/dist/perceptronic-ps5-0.11.0.urcap` from a FAT32 stick (`scripts/urcap5-usb.sh`; ☰ → Settings → System → URCaps → +; remove any older `com.nickarmenta.perceptronic` / RealSense Pilot first). On the pendant make the Hand-E's 0.163 m the active TCP (not the 223 mm training offset) and drop the Pi's `PERCEPTRONICS_TIP_M` line (ignored since 0.10.0; the doctor says so).
- [ ] **Perceive 0.11.0 on the pendant, first time under the new names:** the Installation node and the P button read Perceive; check the P button's icon size (30 px) and popup height (420 px) — `ToolbarService.ICON_PX` / `HEIGHT_PX` — and the **Log** tab.
- [ ] **Pounce 0.11.0, first run:** (1) the three steps fit the program-node panel with nothing clipped (the layout test assumes ≥ 1000 × 560); (2) the program is *Open gripper → Pounce → Close gripper → If rs_pick_found* and the node never touches the gripper; (3) the **closer look** keeps the part clear of the fingers (toggle Depth to see their hole) — `picknode.LOOK_AIM_DEG` 12°, `LOOK_MIN_M` 0.30 m, fingers assumed open 50 mm; decide whether "sharper angle, a bit farther" meant this or a more oblique view of the part; (4) the **Look down** view: the camera 0.40 m straight above the pick area's centre, pushed out of the base keep-out — is that "slightly outreached"?; (5) **Finger room** 20 mm: parts 20 mm apart picked, closer ones yellow; (6) **Grip across the long side** turns the wrist 90°; (7) a program saved by 0.8.0 with children inside its Pick node — what PolyScope does with them; (8) the grip hangs from the **taught** height (`volume.to_nominal_height`): watch for a good part turned away because its measured top disagrees.
- [ ] **Twenty blanks of one size, random layout, three tray positions** (ENTERPRISE.md §7): grips within ±3 mm of the taught offset, zero wrong-part grips, no protective stop. Measure what the datasheet estimates (part centre, heading, cycle to the grip) and reprint it with the measured figures.
- [ ] **Survey in evening light** (2026-09-27: 0 of 2 blocks; `WHITE_MIN` fixed at 180, the Hand-E covers the lower-right quarter of the colour frame): detection is by volume now — check whether this is still a problem; if it is, light the cell or make the threshold follow the exposure.
- [ ] **Finger pads:** measure the real Hand-E pads once; the finger-room check uses pickplan's 14 × 32 mm zone beside the open jaws.
- [ ] **Lost-link alarm on the cell** (checked headless only): pendant flipped to Local mid-run, D435 unplugged mid-run, cockpit restarted mid-routine, robot power cut — each raises the strip, names the fix, clears without a refresh.
- [ ] **`perceptronics calibrate` (orbit hand-eye) on the UR3e** with the current detector (below), `--dry-run` first.
- [ ] **PolyScope X, when an X arm is on the bench:** cockpit with a robot behind it (`--cors http://localhost:8000`, the node's cockpit URL `http://localhost:7621`), click a block → base point + approach + reach → **Move (cockpit)**; **Move (PolyScope)** (IK + auto-move; is `Pose.orientation` a rotation vector?) needs the arm powered + Remote.

## URCaps (both platforms unless named; Nick's cell feedback 2026-10-09/10)

- [ ] **The program node takes the Installation/Application node's cockpit address by itself** — no Save needed, and an empty field means the default 192.168.3.20 like the picture already does. Nick saw "no camera connected" on the program node while the Application tab showed the feed. Today `pickscript.problem()` / `PickScript` refuse an empty host (`cockpitSet`), and the two tests hold that; flip the contract on both platforms.
- [ ] **Declutter the preview picture:** far too much error text over the image ("making it hard to see what's going on"). Keep the green numbers and the yellow reasons on the parts; move everything else off the picture (status line, Log tab).
- [ ] **A too-close check at the pick view:** when the frame is inside the D435's range floor (~0.28 m) or the depth is garbage, tell the operator what to do instead of judging the frame. Nothing outside the RealSense's range is a supported picture.
- [ ] **PolyScope X: the live picture, and a pinned one.** Nick could not see the preview in the X node on 2026-10-09; find out why (dialog vs row), and add the equivalent of PS5's P toolbar button — a popup that stays visible on the move screen.
- [ ] **PolyScope X parity** with the three-step screens (Look / Part / Grip, tap to teach, order under Options); the X node is still the 0.8.0 layout.
- [ ] **Re-pick checkbox on Pounce** (ENTERPRISE §5.3): the next Pounce looks at the last grip's spot first; a part still there is served again. Camera only; needs the pick server to remember the last served pose per node and a `REFIND`-style request.
- [ ] **Shift report + Download diagnostics on the cockpit** (ENTERPRISE §5.4): a `/report` page (parts done, faults with their step, longest cycle, camera fps/temperature, free disk, version) and one button that bundles the last 200 events, the pick log and the last pictures into a file the customer emails. Nothing leaves the cell on its own.

## Camera computer and detector

- [ ] **Orbit calibration finds its mark the old way** (`white_blobs` + `top_face`): on the UR3e it lost the mark in 17 of 21 views over the grey table and in all 13 at the 0.21 m range (this D435's floor is ~0.28 m). Find the mark with `volume.find_parts` + the colour fusion; drop the 0.21 m range once a cell run shows 0.30/0.40 alone solve.
- [ ] **`tests/test_volume.py::test_any_placement_under_any_wrist_heading_measures_the_part`** fails on a hypothesis example with the camera 0.133 m up — inside the D435's floor, not a supported picture. Constrain the synthetic lift range to the camera's range (0.28 m up) instead of loosening the heading bound.
- [ ] **Small fixes from the cell (2026-10-08):** `calibrate --dry-run` plans from a made-up flange pose (`Robot(dry_run=True)` answers [0.5, 0, 0.5]); the Pi's clock is 12 h off (no NTP on the cell — set it from the deploying machine in `install.sh` or `deploy-pi.sh`); the `:80` alias went away after a deploy with `--cell-if none`; the Pi's `cell.env` collects a `PERCEPTRONICS_RS_LASER_POWER=` line per trial (last wins; 150 is live); the `tests/fixtures/d435/` labels are the detector's own output checked by eye — a hand-measured set would be better.
- [ ] **A config file a person edits** instead of `PERCEPTRONICS_*` variables and the Pi's profile dance (the rest of "de-agentify"; `init`/`up` exist).
- [ ] **Customer MCP servers:** decide whether a customer's agent gets the motion tools at all, and behind what confirmation (`urctl-mcp --no-motion` and `perceptronics-vision-mcp` ship; `MCP.md`).
- [ ] **Prune B's split, when Tend starts:** `pickcycle.py`'s helpers stay (the cockpit, the pick node, the pick plan and orbitcal import them); the `perceptronics pick-cycle` routine goes once its lift-and-place logic has been mined for the tending template (ENTERPRISE.md §5.2).

## GPU line (JETSON.md §6 experiments, §9 open points; written 2026-10-10)

- [ ] **Run E3 on the pick PC** over Wi-Fi: RF-DETR-Seg-N and SAM 2 small as ONNX (`pip` on the Pi, ~20 min) — does Line A get the learned segmenter with no GPU?
- [ ] **NVIDIA Inception:** find out whether advin.io / Perceptronics is in it and which entity applies if not (no loaner programme exists; Inception pricing is the pitch's fallback).
- [ ] **Source the first camera into `hardware/BOM.md`:** the Arducam AR0234 USB 3 module (~$150, UVC, no SDK) or a Basler ace 2 GigE (PoE / flange-powered, Aravis). E1–E5 need neither, so this can wait for E3's answer.
- [ ] **Read SAM 3's license in full** (Meta's own, not Apache) before it is in anything shipped; SAM 2 (Apache 2.0) stays the shipping default until then.

## Deploy and site

- [ ] **perceptronics.advin.io is stale** (last upload 2026-10-04: URCap 0.9.0 / 0.7.0, "3D Pick"). `site/site.sh sync` from a machine with the site's AWS profile, or the CI deploy below.
- [ ] **Automate the deployment** (ENTERPRISE §10.9, deploy-chain → draft PRs): `deploy-site.yml` on push to `main` (OIDC role scoped to the one bucket + distribution, `site/site.sh sync`; the PDFs printed in CI with Playwright so the stamp test stops needing a laptop), and the pick PC image built on a self-hosted arm64 runner on every `v*` tag, attached to the Release and published to `imager.json`.
