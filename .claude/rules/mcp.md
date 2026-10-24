---
paths:
  - "urctl/mcp_server.py"
  - "urctl/tools.py"
  - "urctl/controller.py"
  - "urctl/robot.py"
  - "perceptronics/mcp_server.py"
  - "perceptronics/tools.py"
  - "perceptronics/robotlink.py"
  - "MCP.md"
  - ".mcp.json"
  - "tests/test_mcp*.py"
  - "tests/test_cockpit_mcp.py"
  - "tests/test_controller.py"
---

# Tools, MCP servers and the vendor-neutral seam

`CLAUDE.md` always applies. This loads when you touch the tool registry, an MCP server, the `Controller` protocol or `Robot`. `MCP.md` is the customer's page.

When adding a new robot capability, add it in one place — a `Robot` method —
then surface it as a `Tool` in `urctl/tools.py` (schema + handler) and, if it
needs a human entry point, a subcommand in `urctl/cli.py`. The CLI, the agent
tool registry, and the MCP server all sit on the same `Robot`, so they stay in
lockstep. Keep mutating actions routed through the safety envelope + audit log.

**The vendor-neutral seam (`urctl/controller.py`):** `Controller`
and `Gripper` are `typing.Protocol`s — `Robot` satisfies `Controller`
structurally (e-Series and PolyScope X are one class selected by
`RobotConfig.platform`), `Robot.gripper_device` is the `RobotiqUrcapGripper`
adapter. A Fanuc is a second class satisfying `Controller`; the tools, the
cockpit's `RobotLink`, `pick-cycle` and `calibrate` program against the
protocol's method names. **Tool names are canonical without a vendor prefix**
(`move_tcp`, `get_state`, `gripper`, …); the original `ur_*` names are aliases
(`urctl.tools.TOOL_ALIASES`) accepted by `call_tool`, both MCP servers and the
CLI, so existing agent configurations and the `ur_*` mentions in this file keep
working. `tools/list` shows canonical names; `get_tool_schemas(include_aliases=True)`
adds the aliases.

**The door for a person, and the servers for a customer's agent (Nick: "de-agentify
this thing", "the customer said an MCP would be super useful").** `perceptronics init` (`perceptronics/wizard.py`:
questions with defaults → an ordinary cell file; `--yes` for the test cell) and `perceptronics up` (`gui` with
no flags; `up_bind` listens on every interface when the cell names a robot). `urctl-mcp --no-motion` (the name `MCP.md` uses; `pyproject.toml` declares no `urctl-mcp` console script, so from a
checkout it is `python3 -m urctl.mcp_server --no-motion`) and `perceptronics-vision-mcp` (= `perceptronics-mcp
--vision-only`) are the customer servers: `MOTION_TOOLS` /
`VISION_MOTION_TOOLS` are hidden from `tools/list` and refused by `tools/call` with the reason; `MCP.md` is the
customer's page and `tests/test_mcp_doc.py` holds its tool tables to the registries (`tool_rows()`), so a new
tool changes the page or fails the test. Add a tool that moves the arm to the right set.
