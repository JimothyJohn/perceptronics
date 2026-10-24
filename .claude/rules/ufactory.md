---
paths:
  - "urctl/xarm.py"
  - "urctl/ufactory.py"
  - "urctl/workcell.py"
  - "scripts/ufactory-sim.sh"
  - "tests/_xarm_fake.py"
  - "tests/test_xarm.py"
  - "tests/test_ufactory*.py"
  - "tests/test_workcell.py"
  - ".github/workflows/ufactory-sim.yml"
---

# UFACTORY 850: the second vendor behind `Controller`

`CLAUDE.md` always applies. This loads when you touch the xArm/UFACTORY backend, its simulator script or its tests.

**UFACTORY 850 (`urctl/xarm.py`, `urctl/ufactory.py`, `UR_PLATFORM=ufactory`).**
A second vendor behind `Controller`; `urctl/workcell.py` gives positions, TCP offsets and three-point
workplanes on every arm. **UFACTORY's firmware simulator runs on this Mac** (unlike URSim e-Series):
`scripts/ufactory-sim.sh up`, then `UFACTORY_SIM_HOST=127.0.0.1 python3 -m pytest -m ufactory_sim`.
It binds **127.0.0.1:502, 503, 504, 18333 and 30000–30003 — the same 30001–30003 as URSim**, so
`scripts/ufactory-sim.sh down` before starting URSim. What the sim (v2.4.0) does that a fake won't, all
handled in `UFactoryArm` and modelled in `tests/_xarm_fake.py`: MOTION_EN is never answered (UFACTORY's
SDK times out on it too); only_check_type 2 plans from a stale intermediate state (send 1 first); the
first check after a move can say 24 (Speed Exceeds Limit) at rest; SET_TCP_OFFSET drops to state 5 until
`set_state(0)`; joint-teaching mode is refused. When the sim disagrees with us, run UFACTORY's own SDK
(`xArm-Python-SDK`) against it before deciding whose bug it is. Not yet seen on a real 850.
