---
paths:
  - "urctl/robotapi.py"
  - "tests/test_robotapi.py"
  - "docker-compose.yml"
  - "integrations/urcap/perceptronic/**"
  - "integrations/urcap/urcapx.py"
  - "integrations/urcap/e2e.py"
  - "integrations/urcap/track.py"
  - "integrations/urcap/psx_matrix.py"
  - "integrations/urcap/target.json"
  - "PSX.md"
---

# PolyScope X: the REST Robot-API (second platform)

`CLAUDE.md` always applies. This loads when you touch the Robot-API client, the PolyScope X sim service or the PolyScope X URCap. The e-Series surface it differs from is `ur-controller.md`; the URCap itself is `urcap.md`.

The repo can also run **PolyScope X** (PolyScope 10) via the `ursim-px`
compose service (`make simx-up`, web UI on `localhost:8000`). PolyScope X is a
*different controller platform*, not a newer e-Series — and the remote surface
changed enough to matter:

- **No Dashboard server (29999).** Orchestration moved to a RESTful **Robot-API**
  served over HTTP at `http://<host>:<port>/universal-robots/robot-api`
  (self-documented at `…/robot-api/docs`, OpenAPI at `…/robot-api/openapi.json`).
- **Primary (30001) and RTDE (30004) still exist** and URScript execution is
  unchanged — but both interfaces are **off by default** and must be enabled
  once in the UI: hamburger → Settings → Security → Services → enable *Primary
  Client Interface* (+ RTDE). The `ursim-px` service publishes them on **offset
  host ports** (`31001`→30001, `31004`→30004) so it can coexist with the
  e-Series sim's 30001/30004.
- **Remote-mode gate is stricter.** *Every* mutating Robot-API call (power on,
  brake release, load, play) returns **HTTP 403** unless the robot is in
  **Remote** control mode, and there is **no REST endpoint to switch
  Local→Remote** — it's a toggle on the Safety screen in the UI. (On e-Series
  only Dashboard `play` needed Remote; Primary URScript did not.) **Primary
  URScript is gated on Remote too on PolyScope X** (verified 2026-09-04 on the
  10.13.0 sim): in Local the port accepts and broadcasts state but scripts are
  silently ignored — `textmsg` never surfaces, `run_and_capture` returns `[]`,
  `move-*` returns `landed: null`. Once Remote, `textmsg`, confirmed moves and
  `get_flange_pose` all work over `:31001`.
- **UI passwords** (UR's published defaults, first use forces a change): admin
  `easybot` (gates Settings → Security → Services), operational mode `operator`
  (gates Manual/Automatic + Remote). **Stay on the 10.13.0 image** — see the
  comment in `docker-compose.yml`; on 10.14 the Services toggles never stick.
- **Runs natively on Apple Silicon** (arm64 image; `HOST_ARCH=arm64 make
  simx-up`), which makes it the sim to use on this Mac now that the e-Series
  image can't boot under Rosetta here (gotchas table).

`urctl` drives PolyScope X with the **same commands** — select the platform with
`--platform polyscopex` (or `UR_PLATFORM=polyscopex`) and point the Robot-API at
the right port (`UR_ROBOT_API_PORT=8000` for the sim):

```bash
# read state (REST Robot-API) — works in Local mode
UR_PLATFORM=polyscopex UR_ROBOT_API_PORT=8000 urctl state
# or the Make shortcuts (set the env for you):
make simx-state
make simx-bring-up        # power on + brake release (needs Remote mode)
# motion rides Primary 31001 (needs the Primary interface enabled in the UI):
UR_PLATFORM=polyscopex UR_ROBOT_API_PORT=8000 UR_PRIMARY_PORT=31001 \
  urctl --platform polyscopex move-tcp 0 0.05 0 0 0 0 --relative
```

Implementation: `urctl/robotapi.py`'s `RobotAPIClient` is a **drop-in for**
`DashboardClient` (same method names + return-string conventions), injected by
`Robot.__init__` when `config.platform == "polyscopex"`. `PrimaryClient` is
reused unchanged. Verified Robot-API endpoints:

| Need | Robot-API call |
| ---- | -------------- |
| robot / safety mode | `GET /robotstate/v1/{robotmode,safetymode}` → `{mode,message}` |
| power / brake / unlock | `PUT /robotstate/v1/state` `{"action": POWER_ON\|POWER_OFF\|BRAKE_RELEASE\|UNLOCK_PROTECTIVE_STOP\|RESTART_SAFETY}` |
| program state | `GET /program/v1/state`; `PUT` `{"action": play\|pause\|resume\|stop}` |
| load program | `PUT /program/v1/loaded` `{"name": "<program>"}` (PolyScope X programs are `.urpx`, addressed by name) |
| control / op mode | `GET /system/v1/{controlmode,operationalmode}` → `LOCAL\|REMOTE` / `AUTOMATIC\|MANUAL` |

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| Robot-API returns `403 Forbidden` on power/brake/load/play | Robot is in Local control mode | Switch to Remote on the Safety screen in the PolyScope X UI; there is no network way to do it |
| `move-tcp`/`run-script` can't reach Primary on `:31001` | Primary Client Interface not enabled, or container doesn't expose it | Enable it in Settings → Security → Services; if still unreachable see the port-exposure note in the PolyScope X service comments |
