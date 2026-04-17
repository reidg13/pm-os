"""
Jira REST API client — creates epics and tasks via the same Atlassian credentials as Confluence.

Auth:    reuses CONFLUENCE_EMAIL + CONFLUENCE_API_TOKEN from .env
Base:    https://hotelengine.atlassian.net (no /wiki suffix)
API:     REST API v3
"""
import re
import requests
from requests.auth import HTTPBasicAuth

from pm.config import CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN

BASE = "https://hotelengine.atlassian.net/rest/api/3"


def _auth():
    return HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)


def _available():
    return bool(CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN)


def _text_to_adf(text: str) -> dict:
    """Convert plain text to minimal Atlassian Document Format."""
    return {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def _post(path: str, data: dict) -> dict:
    if not _available():
        raise RuntimeError(
            "Jira credentials not configured (CONFLUENCE_EMAIL / CONFLUENCE_API_TOKEN)"
        )
    r = requests.post(f"{BASE}{path}", auth=_auth(), json=data, timeout=15)
    r.raise_for_status()
    return r.json()


def get_projects() -> list:
    """List all Jira projects. Returns [{key, name, id}, ...]"""
    if not _available():
        return []
    r = requests.get(f"{BASE}/project", auth=_auth(), timeout=10)
    r.raise_for_status()
    return [{"key": p["key"], "name": p["name"], "id": p["id"]} for p in r.json()]


def get_project_issues(project_key: str, max: int = 20) -> list:
    """Fetch recent issues from a project. Returns [{key, summary, issuetype, description}, ...]"""
    if not _available():
        return []
    params = {
        "jql": f"project = {project_key} ORDER BY created DESC",
        "maxResults": max,
        "fields": "summary,issuetype,description",
    }
    r = requests.get(f"{BASE}/search", auth=_auth(), params=params, timeout=15)
    r.raise_for_status()
    issues = r.json().get("issues", [])

    result = []
    for i in issues:
        fields = i.get("fields", {})
        desc = fields.get("description")
        # ADF description → extract plain text
        desc_text = None
        if desc and isinstance(desc, dict):
            try:
                parts = []
                for block in desc.get("content", []):
                    for node in block.get("content", []):
                        if node.get("type") == "text":
                            parts.append(node.get("text", ""))
                desc_text = " ".join(parts)
            except Exception:
                desc_text = str(desc)
        result.append(
            {
                "key": i["key"],
                "summary": fields.get("summary", ""),
                "issuetype": fields.get("issuetype", {}).get("name", ""),
                "description": desc_text,
            }
        )
    return result


def get_issue(issue_key: str) -> dict:
    """Fetch a single Jira issue. Returns {key, summary, issuetype, status, description, self}"""
    if not _available():
        return {}
    r = requests.get(
        f"{BASE}/issue/{issue_key}",
        auth=_auth(),
        params={"fields": "summary,issuetype,description,status"},
        timeout=10,
    )
    r.raise_for_status()
    i = r.json()
    fields = i.get("fields", {})
    return {
        "key": i["key"],
        "summary": fields.get("summary", ""),
        "issuetype": fields.get("issuetype", {}).get("name", ""),
        "status": fields.get("status", {}).get("name", ""),
        "description": fields.get("description"),
        "self": i.get("self", ""),
    }


def create_epic(project_key: str, summary: str, description: str) -> dict:
    """Create a Jira Epic. Returns {key, self}"""
    data = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": _text_to_adf(description),
            "issuetype": {"name": "Epic"},
        }
    }
    result = _post("/issue", data)
    return {"key": result["key"], "self": result["self"]}


def create_task(
    project_key: str,
    summary: str,
    description: str,
    epic_key: str = None,
    labels: list = None,
) -> dict:
    """
    Create a Jira Task linked to an epic. Returns {key, self}.

    Links via 'parent' field (team-managed projects). Falls back to
    customfield_10014 (classic epic link) if the API rejects parent.
    """
    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "description": _text_to_adf(description),
        "issuetype": {"name": "Task"},
    }
    if labels:
        fields["labels"] = labels
    if epic_key:
        fields["parent"] = {"key": epic_key}

    try:
        result = _post("/issue", {"fields": fields})
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 400 and epic_key:
            # 'parent' not supported in classic projects — try epic link custom field
            fields.pop("parent", None)
            fields["customfield_10014"] = epic_key
            result = _post("/issue", {"fields": fields})
        else:
            raise

    return {"key": result["key"], "self": result["self"]}
