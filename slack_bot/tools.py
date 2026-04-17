"""Tool definitions and dispatch for the Slack bot's Claude tool_use.

Delegates to the shared tools/ package so both Slack bot and MCP server
use identical logic.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import readers

# -- Anthropic tool_use format definitions (used by handler.py) --

TOOL_DEFINITIONS = [
    {
        "name": "get_all_projects",
        "description": (
            "List all Cars projects with their current status and due date. "
            "Use for broad overview questions like 'what projects are in progress?' or 'what's blocked?'"
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_project_detail",
        "description": (
            "Read the full markdown file for a specific project by name. Returns status, "
            "open tasks, PRD summary, context, and links. Supports fuzzy matching."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Project name or partial match"},
            },
            "required": ["project_name"],
        },
    },
    {
        "name": "get_project_tasks",
        "description": "Get active projects with their open task lists, status, and due dates.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_overdue_tasks",
        "description": "Get tasks that are past their due date, grouped by project.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_status_updates",
        "description": "Get the latest narrative status update for each project.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_weekly_update",
        "description": "Get the most recent weekly status update (detailed version).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_wip_data",
        "description": "Get the work-in-progress roadmap sorted by nearest upcoming milestone.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_ideas",
        "description": "Get feature ideas and hypotheses under investigation.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

# -- Map tool names to reader functions --

_DISPATCH = {
    "get_all_projects": lambda inp: readers.get_all_projects(),
    "get_project_detail": lambda inp: readers.get_project_detail(inp.get("project_name", "")),
    "get_project_tasks": lambda inp: readers.get_project_tasks(),
    "get_overdue_tasks": lambda inp: readers.get_overdue_tasks(),
    "get_status_updates": lambda inp: readers.get_status_updates(),
    "get_weekly_update": lambda inp: readers.get_weekly_update(),
    "get_wip_data": lambda inp: readers.get_wip_data(),
    "get_ideas": lambda inp: readers.get_ideas(),
}


def dispatch_tool(name: str, tool_input: dict) -> str:
    """Execute a tool by name and return its result as a string."""
    fn = _DISPATCH.get(name)
    if fn:
        return fn(tool_input)
    return f"Unknown tool: {name}"
