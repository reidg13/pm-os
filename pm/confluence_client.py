"""
Confluence integration — search for PRDs and pages by project name.

Setup:
  1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
  2. Create an API token
  3. Add CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN to .env
"""
import requests
from requests.auth import HTTPBasicAuth

from pm.config import CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN, CONFLUENCE_BASE_URL

BASE = f"{CONFLUENCE_BASE_URL}/rest/api"


def _auth():
    return HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)


def _available():
    return bool(CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN)


def search_pages(query, limit=5):
    """Search Confluence pages by title matching query. Returns list of {title, url, space} dicts."""
    if not _available():
        return None

    cql = f'type=page AND title~"{query}" ORDER BY lastmodified DESC'
    r = requests.get(
        f"{BASE}/content/search",
        auth=_auth(),
        params={"cql": cql, "limit": limit, "expand": "space"},
        timeout=10,
    )
    r.raise_for_status()
    results = r.json().get("results", [])

    return [
        {
            "title": p["title"],
            "url": f"{CONFLUENCE_BASE_URL}{p['_links']['webui']}",
            "space": p.get("space", {}).get("name", ""),
            "id": p["id"],
        }
        for p in results
    ]


def get_page_summary(page_id):
    """Fetch the plain-text body of a page (first 1000 chars)."""
    if not _available():
        return None

    r = requests.get(
        f"{BASE}/content/{page_id}",
        auth=_auth(),
        params={"expand": "body.export_view"},
        timeout=10,
    )
    r.raise_for_status()
    body = r.json().get("body", {}).get("export_view", {}).get("value", "")

    # Strip HTML tags for plain text
    import re
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1000]


def get_page_full(page_id):
    """Fetch the full plain-text body of a page (no truncation)."""
    if not _available():
        return ""

    r = requests.get(
        f"{BASE}/content/{page_id}",
        auth=_auth(),
        params={"expand": "body.export_view"},
        timeout=20,
    )
    r.raise_for_status()
    body = r.json().get("body", {}).get("export_view", {}).get("value", "")

    import re
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_page_by_url(confluence_url):
    """
    Extract page ID from a Confluence URL and return (title, full_body_text).

    Handles URLs like:
      https://hotelengine.atlassian.net/wiki/spaces/CARS/pages/12345/Page-Title
    """
    import re
    match = re.search(r"/pages/(\d+)", confluence_url)
    if not match:
        raise ValueError(f"Could not extract page ID from URL: {confluence_url}")

    page_id = match.group(1)

    if not _available():
        return "", ""

    r = requests.get(
        f"{BASE}/content/{page_id}",
        auth=_auth(),
        params={"expand": "body.export_view"},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    title = data.get("title", "")
    body = data.get("body", {}).get("export_view", {}).get("value", "")

    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text
