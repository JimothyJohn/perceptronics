"""The dependency-free tool-argument validator shared by the cockpit's MCP tools.

The perceptronics-side analogue of :func:`urctl.tools._validate`: a JSON-Schema-shaped
check (types, required keys, no unknown keys) that :mod:`perceptronics.mcp_server` runs
on every ``cam_*`` / ``cell_*`` call before it reaches the cockpit. The 2-D blob
pipeline's own tool registry that used to live here was removed on 2026-10-04.
"""

from __future__ import annotations


class ToolError(Exception):
    """Raised when a tool call is malformed (unknown tool / invalid args)."""


def _object_schema(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _validate(params: dict, schema: dict) -> None:
    """Dependency-free schema check — same contract as urctl.tools._validate."""
    props = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        unknown = set(params) - set(props)
        if unknown:
            raise ToolError(f"unexpected argument(s): {sorted(unknown)}")
    for key in schema.get("required", []):
        if key not in params:
            raise ToolError(f"missing required argument: {key!r}")
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for key, value in params.items():
        spec = props.get(key)
        if not spec or "type" not in spec:
            continue
        if spec["type"] in ("number", "integer") and isinstance(value, bool):
            raise ToolError(f"argument {key!r} must be {spec['type']}, got bool")
        expected = type_map.get(spec["type"])
        if expected and not isinstance(value, expected):
            raise ToolError(f"argument {key!r} must be {spec['type']}, got {type(value).__name__}")
