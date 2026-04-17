"""
Asana integration — tasks assigned to me + project roadmap view.

Setup:
  1. Generate a Personal Access Token at https://app.asana.com/0/my-apps
  2. Add ASANA_ACCESS_TOKEN to .env
  3. Run `python pm.py asana-setup` to auto-detect workspace/user GIDs
     (or set asana_workspace_gid + asana_user_gid in data/config.json manually)
"""
import json
from datetime import date
from pathlib import Path

import requests

from pm.config import ASANA_ACCESS_TOKEN

BASE = "https://app.asana.com/api/1.0"

# Load vault→Asana name mapping from config.json
def _load_name_map():
    cfg = Path(__file__).parent.parent / "data" / "config.json"
    try:
        return json.loads(cfg.read_text()).get("vault_to_asana_names", {})
    except Exception:
        return {}

# {vault_name_lower: asana_name_lower} for fast lookup
_NAME_MAP = {k.lower(): v.lower() for k, v in _load_name_map().items()}
# {asana_name_lower: vault_name} reverse map
_REVERSE_MAP = {v.lower(): k for k, v in _load_name_map().items()}


def _get(path, params=None):
    if not ASANA_ACCESS_TOKEN:
        return None
    r = requests.get(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {ASANA_ACCESS_TOKEN}"},
        params=params or {},
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("data")


def get_me():
    return _get("/users/me")


def get_workspaces():
    me = get_me()
    return me.get("workspaces", []) if me else []


def get_my_tasks(workspace_gid):
    """Return tasks assigned to me that are incomplete, sorted by due date."""
    today = date.today().isoformat()
    tasks = _get(
        "/tasks",
        params={
            "assignee": "me",
            "workspace": workspace_gid,
            "completed_since": "now",
            "opt_fields": "name,due_on,projects.name,permalink_url,notes",
            "limit": 100,
        },
    )
    if not tasks:
        return [], []

    overdue, due_soon = [], []
    for t in tasks:
        due = t.get("due_on") or ""
        item = {
            "text": t.get("name", "").strip(),
            "due": due,
            "project": (t.get("projects") or [{}])[0].get("name", ""),
            "url": t.get("permalink_url", ""),
        }
        if not item["text"]:
            continue
        if due and due <= today:
            overdue.append(item)
        else:
            due_soon.append(item)

    overdue.sort(key=lambda x: x["due"])
    due_soon.sort(key=lambda x: x["due"])
    return overdue, due_soon


def get_projects(workspace_gid):
    """Return all active projects in the workspace."""
    projects = _get(
        "/projects",
        params={
            "workspace": workspace_gid,
            "archived": "false",
            "opt_fields": "name,due_date,current_status_update.text,current_status_update.title,permalink_url",
            "limit": 100,
        },
    )
    return projects or []


def get_project_tasks(project_gid):
    """Return incomplete tasks for a specific project."""
    tasks = _get(
        f"/projects/{project_gid}/tasks",
        params={
            "opt_fields": "name,due_on,assignee,assignee.name,completed",
            "limit": 100,
        },
    )
    if not tasks:
        return []
    return [t for t in tasks if not t.get("completed")]


def _put(path, data):
    if not ASANA_ACCESS_TOKEN:
        return None
    r = requests.put(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {ASANA_ACCESS_TOKEN}"},
        json={"data": data},
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("data")


def _post(path, data):
    if not ASANA_ACCESS_TOKEN:
        return None
    r = requests.post(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {ASANA_ACCESS_TOKEN}"},
        json={"data": data},
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("data")


def complete_task(task_gid):
    """Mark a task as complete in Asana."""
    return _put(f"/tasks/{task_gid}", {"completed": True})


def create_task(project_gid, name, assignee_gid=None, due_on=None):
    """Create a new task on an Asana board. Returns the created task dict."""
    data = {"name": name, "projects": [project_gid]}
    if assignee_gid:
        data["assignee"] = assignee_gid
    if due_on:
        data["due_on"] = due_on
    return _post("/tasks", data)


def search_board_task_by_name(boards, project_name):
    """Search configured board tasks for one whose name matches project_name.

    Checks both the exact vault name and any mapped Asana name.
    Returns task dict with gid, name, completed, permalink_url, due_on — or None.
    """
    name_lower = project_name.strip().lower()
    mapped_lower = _NAME_MAP.get(name_lower, name_lower)

    for board in boards:
        tasks = _get(
            f"/projects/{board['gid']}/tasks",
            params={"opt_fields": "name,completed,gid,permalink_url,due_on", "limit": 100},
        )
        for task in (tasks or []):
            task_name_lower = task.get("name", "").strip().lower()
            if task_name_lower in (name_lower, mapped_lower):
                return task
    return None


def get_board_task_map(board_gid):
    """Return {name_lower: task_dict} for all tasks on a board.

    Indexes by both the raw Asana name and the vault name (via reverse map)
    so vault lookups work regardless of naming differences.
    task_dict keys: gid, name, completed, permalink_url, due_on
    """
    tasks = _get(
        f"/projects/{board_gid}/tasks",
        params={"opt_fields": "name,completed,gid,permalink_url,due_on", "limit": 100},
    )
    result = {}
    for t in (tasks or []):
        name = t.get("name", "").strip()
        if not name:
            continue
        name_lower = name.lower()
        result[name_lower] = t
        # Also index by vault name if a reverse mapping exists
        vault_name = _REVERSE_MAP.get(name_lower)
        if vault_name:
            result[vault_name.lower()] = t
    return result


def get_completed_tasks_this_week(workspace_gid):
    """Return tasks assigned to me that were completed since Monday."""
    from datetime import timedelta
    today = date.today()
    monday = (today - timedelta(days=today.weekday())).isoformat()
    tasks = _get(
        "/tasks",
        params={
            "assignee": "me",
            "workspace": workspace_gid,
            "completed_since": monday,
            "opt_fields": "name,completed_at,projects.name,permalink_url",
            "limit": 100,
        },
    )
    completed = [t for t in (tasks or []) if t.get("completed_at")]
    return [
        {
            "text": t.get("name", "").strip(),
            "project": (t.get("projects") or [{}])[0].get("name", ""),
            "completed_at": t.get("completed_at", ""),
        }
        for t in completed
        if t.get("name", "").strip()
    ]
