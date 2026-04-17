"""Read-only tools for Cars project data.

Each function returns a string (JSON or markdown) suitable for both MCP and Slack bot.
No vault modifications, no meeting notes, no daily notes — only team-appropriate project data.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pm import vault
from pm.weekly import _get_wip_data
from tools.privacy import strip_private_sections

_MAX_RESULT_CHARS = 8000

_DEPS_FILE = Path.home() / ".claude" / "docs" / "project-dependencies.md"


def _truncate(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return text[:_MAX_RESULT_CHARS] + "\n\n... (truncated)"


def _json_result(obj) -> str:
    result = json.dumps(obj, indent=2)
    if len(result) <= _MAX_RESULT_CHARS:
        return result
    result = json.dumps(obj, separators=(",", ":"))
    if len(result) <= _MAX_RESULT_CHARS:
        return result
    return result[:_MAX_RESULT_CHARS - 50] + '}\n\n... (truncated, ask about specific projects)'


# ---------------------------------------------------------------------------
# Original 8 tools (extracted from slack_bot/tools.py)
# ---------------------------------------------------------------------------

def get_all_projects() -> str:
    """List all Cars projects with their current status and due date."""
    result = vault.get_all_projects_with_status()
    summary = {}
    for proj, info in result.items():
        summary[proj] = {
            "status": info.get("status", ""),
            "due": info.get("due", ""),
        }
    return _json_result(summary)


def get_project_detail(project_name: str) -> str:
    """Read the full project file by name (fuzzy match). Private sections stripped."""
    query = project_name.lower()
    if not query:
        return "Error: project_name is required"
    projects_dir = vault.PROJECTS_DIR
    if not projects_dir.exists():
        return "Error: Projects directory not found"
    matches = []
    for d in sorted(projects_dir.iterdir()):
        if d.is_dir() and query in d.name.lower():
            matches.append(d)
    if not matches:
        return f"No project found matching '{project_name}'"
    project_dir = matches[0]
    for md_file in project_dir.glob("*.md"):
        content = md_file.read_text()
        content = strip_private_sections(content)
        return _truncate(content)
    return f"Project folder '{project_dir.name}' exists but has no .md file"


def get_project_tasks() -> str:
    """Get active projects with their open task lists, status, and due dates."""
    result = vault.get_project_tasks()
    summary = {}
    for proj, data in result.items():
        tasks = [
            {"text": t["text"], "due": t.get("due", "")}
            for t in data.get("tasks", [])
        ]
        summary[proj] = {
            "status": data.get("status", ""),
            "due": data.get("due", ""),
            "tasks": tasks[:10],
        }
    return _json_result(summary)


def get_overdue_tasks() -> str:
    """Get tasks past their due date, grouped by project."""
    result = vault.get_overdue_tasks()
    summary = {}
    for proj, tasks in result.items():
        summary[proj] = [
            {"text": t["text"], "due": t.get("due", "")} for t in tasks
        ]
    return _json_result(summary)


def get_status_updates() -> str:
    """Get the latest narrative status update for each project."""
    result = vault.get_all_status_updates()
    summary = {}
    for proj, (update_date, text) in result.items():
        summary[proj] = {"date": update_date, "text": text}
    return _json_result(summary)


def get_weekly_update() -> str:
    """Get the most recent weekly status update (detailed version)."""
    content = vault.get_previous_weekly_update()
    if not content:
        return "No weekly update found"
    return _truncate(content)


def get_wip_data() -> str:
    """Get the work-in-progress roadmap sorted by nearest upcoming milestone."""
    rows = _get_wip_data()
    return _json_result(rows)


def get_ideas() -> str:
    """Get feature ideas and hypotheses under investigation."""
    ideas = vault.get_ideas()
    return _json_result(ideas)


# ---------------------------------------------------------------------------
# New tools
# ---------------------------------------------------------------------------

def get_project_dependencies(project_name: str = "") -> str:
    """Get cross-project dependency map. Optionally filter to a specific project."""
    if not _DEPS_FILE.exists():
        return "No project dependencies file found"
    content = _DEPS_FILE.read_text()
    if not project_name:
        return _truncate(content)
    # Filter table rows mentioning this project
    query = project_name.lower()
    lines = content.splitlines()
    header_lines = []
    matching_rows = []
    in_table = False
    for line in lines:
        if line.startswith("|") and "Upstream" in line:
            header_lines.append(line)
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            header_lines.append(line)
            continue
        if in_table and line.startswith("|"):
            if query in line.lower():
                matching_rows.append(line)
        elif in_table and not line.startswith("|"):
            in_table = False
    if not matching_rows:
        return f"No dependencies found involving '{project_name}'"
    return "\n".join(header_lines + matching_rows)


def get_recently_shipped() -> str:
    """Get projects that have been completed (status=Done)."""
    result = vault.get_all_projects_with_status()
    shipped = {}
    for proj, info in result.items():
        if info.get("status", "").lower() in ("done", "complete", "completed"):
            shipped[proj] = {"status": info["status"], "due": info.get("due", "")}
    if not shipped:
        return "No shipped projects found"
    return _json_result(shipped)


def get_project_owners(project_name: str = "") -> str:
    """Get project ownership info (owner, tech lead, designer, team).

    If project_name is given, returns info for that project only.
    Otherwise returns all active projects.
    """
    projects_dir = vault.PROJECTS_DIR
    if not projects_dir.exists():
        return "Error: Projects directory not found"

    result = {}
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        if project_name and project_name.lower() not in project_dir.name.lower():
            continue
        for md_file in project_dir.glob("*.md"):
            content = md_file.read_text()
            fm = vault._parse_yaml_frontmatter(content)
            if not fm:
                continue
            status = fm.get("status", "")
            if status.lower() in ("done", "complete", "completed") and not project_name:
                continue
            result[project_dir.name] = {
                "owner": fm.get("owner", ""),
                "tech_lead": fm.get("tech_lead", ""),
                "designer": fm.get("designer", ""),
                "team": fm.get("team", ""),
                "status": status,
            }
    if not result:
        return f"No project found matching '{project_name}'" if project_name else "No projects found"
    return _json_result(result)


def get_project_timeline(project_name: str) -> str:
    """Get timeline for a specific project: due date + milestone dates from tasks."""
    query = project_name.lower()
    projects = vault.get_project_tasks()
    for proj, data in projects.items():
        if query in proj.lower():
            milestones = sorted(
                [{"text": t["text"], "due": t["due"]}
                 for t in data.get("tasks", [])
                 if t.get("due")],
                key=lambda x: x["due"],
            )
            return _json_result({
                "project": proj,
                "status": data.get("status", ""),
                "overall_due": data.get("due", ""),
                "milestones": milestones,
            })
    # Check all projects (including done) for timeline
    all_projects = vault.get_all_projects_with_status()
    for proj, info in all_projects.items():
        if query in proj.lower():
            return _json_result({
                "project": proj,
                "status": info.get("status", ""),
                "overall_due": info.get("due", ""),
                "milestones": [],
            })
    return f"No project found matching '{project_name}'"


def search_projects(query: str) -> str:
    """Search projects by keyword across names, status, and status update text."""
    q = query.lower()
    results = []

    all_projects = vault.get_all_projects_with_status()
    status_updates = vault.get_all_status_updates()

    for proj, info in all_projects.items():
        matched = False
        match_reason = []

        if q in proj.lower():
            matched = True
            match_reason.append("name")
        if q in info.get("status", "").lower():
            matched = True
            match_reason.append("status")

        update = status_updates.get(proj)
        if update and q in update[1].lower():
            matched = True
            match_reason.append("status_update")

        if matched:
            results.append({
                "project": proj,
                "status": info.get("status", ""),
                "due": info.get("due", ""),
                "matched_on": match_reason,
            })

    if not results:
        return f"No projects found matching '{query}'"
    return _json_result(results)
