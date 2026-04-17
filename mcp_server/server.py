"""Cars Copilot MCP Server.

Exposes read-only tools for Cars project data, plus one write tool for feature requests.
No meeting notes, daily notes, or personal data. Privacy enforced at the tool level.
"""

import os
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP

from tools import readers, writers

_port = int(os.getenv("MCP_PORT", "3200"))

mcp = FastMCP(
    "Cars Copilot",
    instructions=(
        "Cars Copilot provides read-only access to the product team's project data at Engine. "
        "Use these tools to check project status, roadmap, dependencies, and ownership. "
        "You can also submit feature requests. "
        "You do NOT have access to meeting notes, daily notes, or personal data."
    ),
    host="0.0.0.0",
    port=_port,
)


# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_all_projects() -> str:
    """List all Cars projects with their current status and due date.
    Use for broad overview questions like 'what's in progress?' or 'what's blocked?'"""
    return readers.get_all_projects()


@mcp.tool()
def get_project_detail(project_name: str) -> str:
    """Read the full project file by name. Returns status, open tasks, PRD summary,
    context, and links. Supports fuzzy matching (e.g. 'Hertz', 'BOOP', 'NOMAD').
    Private sections are stripped."""
    return readers.get_project_detail(project_name)


@mcp.tool()
def get_project_tasks() -> str:
    """Get active projects with their open task lists, status, and due dates.
    More detailed than get_all_projects — includes individual task text."""
    return readers.get_project_tasks()


@mcp.tool()
def get_overdue_tasks() -> str:
    """Get tasks that are past their due date, grouped by project."""
    return readers.get_overdue_tasks()


@mcp.tool()
def get_status_updates() -> str:
    """Get the latest narrative status update for each project.
    These are free-text updates written by the PM."""
    return readers.get_status_updates()


@mcp.tool()
def get_weekly_update() -> str:
    """Get the most recent weekly status update (detailed version).
    Contains shipped items, WIP, at-risk projects, blockers, and key wins."""
    return readers.get_weekly_update()


@mcp.tool()
def get_wip_data() -> str:
    """Get the work-in-progress roadmap: active projects sorted by nearest
    upcoming milestone date. Includes status, due dates, and next steps."""
    return readers.get_wip_data()


@mcp.tool()
def get_ideas() -> str:
    """Get feature ideas and hypotheses currently under investigation."""
    return readers.get_ideas()


@mcp.tool()
def get_project_dependencies(project_name: str = "") -> str:
    """Get cross-project dependency map showing what blocks what.
    Optionally filter to dependencies involving a specific project."""
    return readers.get_project_dependencies(project_name)


@mcp.tool()
def get_recently_shipped() -> str:
    """Get projects that have been completed (status=Done)."""
    return readers.get_recently_shipped()


@mcp.tool()
def get_project_owners(project_name: str = "") -> str:
    """Get project ownership: owner, tech lead, designer, and team.
    If project_name given, returns just that project. Otherwise all active projects."""
    return readers.get_project_owners(project_name)


@mcp.tool()
def get_project_timeline(project_name: str) -> str:
    """Get timeline for a specific project: overall due date plus milestone dates
    from individual tasks with @due() annotations."""
    return readers.get_project_timeline(project_name)


@mcp.tool()
def search_projects(query: str) -> str:
    """Search projects by keyword across names, status, and status update text."""
    return readers.search_projects(query)


# ---------------------------------------------------------------------------
# One write tool
# ---------------------------------------------------------------------------

@mcp.tool()
def submit_feature_request(
    description: str,
    submitted_by: str,
    source: str = "",
) -> str:
    """Submit a feature request to the Cars roadmap.
    Appends a row to the Feature Request tab of the roadmap Google Sheet.
    This is the ONLY write operation available."""
    return writers.submit_feature_request(description, submitted_by, source)
