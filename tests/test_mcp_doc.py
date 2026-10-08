"""MCP.md is the customer's page for the two servers: its tool tables are the registries'
(2026-10-06), so a tool added, renamed or re-described shows up here as a failing test and a
diff to paste, not as a page that drifts."""

from __future__ import annotations

import re
from pathlib import Path

from perceptronics.mcp_server import tool_rows

DOC = Path(__file__).resolve().parents[1] / "MCP.md"


def _block(text: str, which: str) -> list[str]:
    m = re.search(rf"<!-- tools:{which} -->\n(.*?)<!-- /tools:{which} -->", text, re.S)
    assert m, f"MCP.md has no <!-- tools:{which} --> block"
    rows = [ln for ln in m.group(1).splitlines() if ln.startswith("| `")]
    return rows


def test_mcp_md_lists_exactly_the_registries_tools():
    text = DOC.read_text(encoding="utf-8")
    rows = tool_rows()
    for which in ("robot", "vision"):
        got, want = _block(text, which), rows[which]
        assert got == want, (
            f"MCP.md's {which} table is out of date; paste this between the <!-- tools:{which} --> markers:\n"
            "| Tool | What it does | |\n| --- | --- | --- |\n" + "\n".join(want)
        )


def test_mcp_md_names_the_two_servers_and_the_gate():
    text = DOC.read_text(encoding="utf-8")
    for needle in (
        "urctl-mcp",
        "perceptronics-vision-mcp",
        "--no-motion",
        "--vision-only",
        "--cockpit-url",
        "--host",
    ):
        assert needle in text, needle
