"""MCP Server for Episode State

Exposes episode pipeline state over MCP (Model Context Protocol),
allowing chat agents to query and update episode progress.

Usage:
    python mcp/episode_state_server.py
"""

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

import json
import sys
from pathlib import Path

# Add agents to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))

from common import setup_logging  # noqa: E402
from episode_state import PIPELINE_STEPS, EpisodeState  # noqa: E402

log = setup_logging("mcp_server")


def handle_request(request: dict) -> dict:
    """Handle a single MCP request."""
    method = request.get("method", "")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "episode-state", "version": "1.0.0"},
        }

    if method == "tools/list":
        return {"tools": _get_tools()}

    if method == "tools/call":
        return _call_tool(params.get("name", ""), params.get("arguments", {}))

    return {"error": {"code": -32601, "message": f"Unknown method: {method}"}}


def _get_tools() -> list[dict]:
    """Return list of available MCP tools."""
    return [
        {
            "name": "get_episode_status",
            "description": "Get the current pipeline status for an episode",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "episode_number": {
                        "type": "integer",
                        "description": "Episode number",
                    }
                },
                "required": ["episode_number"],
            },
        },
        {
            "name": "get_episode_summary",
            "description": "Get a brief summary of episode progress",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "episode_number": {
                        "type": "integer",
                        "description": "Episode number",
                    }
                },
                "required": ["episode_number"],
            },
        },
        {
            "name": "start_step",
            "description": "Mark a pipeline step as started",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "episode_number": {
                        "type": "integer",
                        "description": "Episode number",
                    },
                    "step": {
                        "type": "string",
                        "description": "Pipeline step name",
                        "enum": PIPELINE_STEPS,
                    },
                },
                "required": ["episode_number", "step"],
            },
        },
        {
            "name": "complete_step",
            "description": "Mark a pipeline step as completed",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "episode_number": {
                        "type": "integer",
                        "description": "Episode number",
                    },
                    "step": {
                        "type": "string",
                        "description": "Pipeline step name",
                        "enum": PIPELINE_STEPS,
                    },
                    "result": {
                        "type": "object",
                        "description": "Optional result/artifact data",
                    },
                },
                "required": ["episode_number", "step"],
            },
        },
        {
            "name": "fail_step",
            "description": "Mark a pipeline step as failed",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "episode_number": {
                        "type": "integer",
                        "description": "Episode number",
                    },
                    "step": {
                        "type": "string",
                        "description": "Pipeline step name",
                        "enum": PIPELINE_STEPS,
                    },
                    "error": {
                        "type": "string",
                        "description": "Error description",
                    },
                },
                "required": ["episode_number", "step", "error"],
            },
        },
        {
            "name": "list_pipeline_steps",
            "description": "List all pipeline steps and their order",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def _call_tool(name: str, arguments: dict) -> dict:
    """Execute an MCP tool call."""
    try:
        if name == "list_pipeline_steps":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"steps": PIPELINE_STEPS, "total": len(PIPELINE_STEPS)},
                            indent=2,
                        ),
                    }
                ]
            }

        episode_number = arguments.get("episode_number")
        if episode_number is None:
            return _error_response("episode_number is required")

        state = EpisodeState(episode_number)

        if name == "get_episode_status":
            return {"content": [{"type": "text", "text": json.dumps(state._state, indent=2)}]}

        if name == "get_episode_summary":
            return {"content": [{"type": "text", "text": json.dumps(state.summary(), indent=2)}]}

        if name == "start_step":
            step = arguments.get("step", "")
            state.start_step(step)
            return {
                "content": [
                    {"type": "text", "text": f"Step '{step}' started for Episode {episode_number}"}
                ]
            }

        if name == "complete_step":
            step = arguments.get("step", "")
            result = arguments.get("result")
            state.complete_step(step, result)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Step '{step}' completed for Episode {episode_number}",
                    }
                ]
            }

        if name == "fail_step":
            step = arguments.get("step", "")
            error = arguments.get("error", "Unknown error")
            state.fail_step(step, error)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Step '{step}' failed for Episode {episode_number}: {error}",
                    }
                ]
            }

        return _error_response(f"Unknown tool: {name}")

    except Exception as e:
        return _error_response(str(e))


def _error_response(message: str) -> dict:
    """Create an error response."""
    return {"content": [{"type": "text", "text": f"Error: {message}"}], "isError": True}


def main():
    """Run MCP server using stdio transport."""
    log.info("Episode State MCP server starting (stdio transport)")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            response = handle_request(request)

            # Wrap in JSON-RPC response
            output = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": response,
            }
            sys.stdout.write(json.dumps(output) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
