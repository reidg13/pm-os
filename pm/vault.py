"""
Read and write the Obsidian vault.
"""
import re
import yaml
from pathlib import Path
from datetime import date, datetime, timedelta  # date/datetime used by weekly note

import json

from pm.config import VAULT_PATH

PROJECTS_DIR = VAULT_PATH / "Projects"
AREAS_DIR = VAULT_PATH / "Areas"
ARCHIVE_DIR = VAULT_PATH / "Archive" / "Bear"
WEEKLY_NOTES_DIR = VAULT_PATH / "Weekly Notes"
DAILY_NOTES_DIR = VAULT_PATH / "Daily Notes"
MEETING_NOTES_DIR = VAULT_PATH / "Meeting Notes"
IDEAS_FILE = VAULT_PATH / "Areas" / "Discovery + Research" / "Ideas to Investigate.md"

DATA_DIR = Path(__file__).parent.parent / "data"
WEEKLY_LOG_FILE = DATA_DIR / "weekly_log.jsonl"
STATUS_SNAPSHOT_FILE = DATA_DIR / "status_snapshot_current.json"

_CHECKBOX = re.compile(r"^(\s*)-\s+\[( |x|X)\]\s+(.+)$")
_DUE_DATE = re.compile(r"\s*(?:@due\((\d{4}-\d{2}-\d{2})\)|📅\s*(\d{4}-\d{2}-\d{2}))")


def _week_subdir(parent: Path, d: date) -> Path:
    """Return (and create) a weekly subfolder named after the Sunday that starts the week.
    Weeks run Sunday–Saturday (US convention).
    E.g. Daily Notes/2026-03-01/ for the week of Mar 1–7 2026.
    """
    # weekday(): Mon=0 … Sat=5, Sun=6  →  days since last Sunday = (weekday+1)%7
    days_since_sunday = (d.weekday() + 1) % 7
    sunday = d - timedelta(days=days_since_sunday)
    week_dir = parent / sunday.isoformat()
    week_dir.mkdir(parents=True, exist_ok=True)
    return week_dir


def _daily_note_path(d: date) -> Path:
    """Canonical path for a daily note inside its weekly subfolder."""
    return _week_subdir(DAILY_NOTES_DIR, d) / f"{d.isoformat()}.md"


def _find_daily_note(d: date) -> Path:
    """Return the daily note path, checking weekly subfolder then flat fallback."""
    new = _daily_note_path(d)
    if new.exists():
        return new
    flat = DAILY_NOTES_DIR / f"{d.isoformat()}.md"
    if flat.exists():
        return flat
    return new  # return canonical path even if it doesn't exist yet


def _find_most_recent_note_before(before_date, max_days_back=7):
    """Find the most recent daily note that exists before the given date.
    Scans all week subfolders to handle convention changes in folder naming.
    Does NOT create directories (unlike _find_daily_note)."""
    for i in range(1, max_days_back + 1):
        d = before_date - timedelta(days=i)
        fname = f"{d.isoformat()}.md"
        # Check flat path
        flat = DAILY_NOTES_DIR / fname
        if flat.exists():
            return flat
        # Scan all week subfolders (handles convention changes)
        for week_dir in DAILY_NOTES_DIR.iterdir():
            if week_dir.is_dir():
                candidate = week_dir / fname
                if candidate.exists():
                    return candidate
    return None


_CARRYOVER_SECTIONS = {"carryover from yesterday", "today's focus", "carryover", "focus", "action queue"}


def _read_unchecked_user_tasks(note_path):
    """Read unchecked tasks from carryover/focus sections of a daily note.
    Only reads from sections that represent daily action items, not reference sections."""
    if not note_path or not note_path.exists():
        return []
    lines = note_path.read_text().splitlines()
    tasks = []
    in_carryover = False
    for line in lines:
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            in_carryover = heading in _CARRYOVER_SECTIONS
        elif in_carryover:
            m = _CHECKBOX.match(line)
            if m:
                _, status, _ = m.groups()
                if status == " ":  # unchecked only
                    tasks.append(line)
    return tasks


def _clean_task_for_dedup(text):
    """Strip metadata from task text for deduplication comparison."""
    text = _DUE_DATE.sub("", text).strip()
    text = re.sub(r"\s*—\s*\d+d?\s*overdue\s*$", "", text).strip()
    text = re.sub(r"\s*\*\(.*?\)\*\s*$", "", text).strip()  # *(Project Name)*
    return text


def _meeting_notes_week_dir(d: date) -> Path:
    """Return (and create) the weekly subfolder for meeting notes on date d."""
    return _week_subdir(MEETING_NOTES_DIR, d)


def _parse_tasks(path, include_done=False):
    tasks = []
    try:
        for i, line in enumerate(Path(path).read_text().splitlines()):
            m = _CHECKBOX.match(line)
            if m:
                indent, status, text = m.groups()
                done = status.lower() == "x"
                if not done or include_done:
                    text = text.strip()
                    due_m = _DUE_DATE.search(text)
                    due = (due_m.group(1) or due_m.group(2)) if due_m else None
                    tasks.append(
                        {
                            "text": text,
                            "done": done,
                            "line": i,
                            "indent": len(indent),
                            "file": str(path),
                            "due": due,
                        }
                    )
    except FileNotFoundError:
        pass
    return tasks


def set_task_due(task_text, due_date, project_name=None):
    """Add or update @due(YYYY-MM-DD) on matching tasks across project files.

    task_text may or may not already contain an @due(...) — it's stripped before matching.
    Returns list of {project, file} dicts for each file updated.
    """
    clean_text = re.sub(r"\s*(?:@due\(\d{4}-\d{2}-\d{2}\)|📅\s*\d{4}-\d{2}-\d{2})", "", task_text).strip()
    updated = []

    if project_name:
        dirs = [PROJECTS_DIR / project_name]
    else:
        dirs = sorted(PROJECTS_DIR.iterdir()) if PROJECTS_DIR.exists() else []

    for project_dir in dirs:
        if not project_dir.is_dir():
            continue
        for md_file in project_dir.glob("*.md"):
            content = md_file.read_text()
            # Match open or done checkbox with this task text (with or without existing @due)
            pattern = (
                r"(^\s*-\s+\[[ xX]\]\s+"
                + re.escape(clean_text)
                + r")\s*(?:@due\(\d{4}-\d{2}-\d{2}\))?\s*$"
            )
            new_content, count = re.subn(
                pattern,
                rf"\1 @due({due_date})",
                content,
                flags=re.MULTILINE,
            )
            if count:
                md_file.write_text(new_content)
                updated.append({"project": project_dir.name, "file": str(md_file)})
    return updated


def get_project_names():
    if not PROJECTS_DIR.exists():
        return []
    return sorted(p.name for p in PROJECTS_DIR.iterdir() if p.is_dir())


_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

_STATUS_TAG_MAP = {
    "in-progress": "In Progress",
    "in-discovery": "In Discovery",
    "done": "Done",
    "measuring": "Measuring",
    "dev-in-progress": "Dev in progress",
    "ready-for-dev": "Ready for dev",
    "dtd": "DTD",
    "ptd": "PTD",
    "design-in-progress": "Design in progress",
    "product-review": "Product review",
    "discovery": "Discovery",
    "paused": "Paused",
    "blocked": "Blocked",
}


def _parse_yaml_frontmatter(text):
    """Return parsed YAML frontmatter dict, or {} if none."""
    m = _FRONTMATTER.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _parse_project_meta(md_file):
    """Extract status, PRD link, and due date from a project file.
    Reads from YAML frontmatter first, falls back to ## Status section."""
    status = ""
    prd = ""
    due = ""
    try:
        content = Path(md_file).read_text()
        fm = _parse_yaml_frontmatter(content)

        # Status from YAML tags
        if fm:
            tags = fm.get("tags") or []
            for tag in tags:
                if tag in _STATUS_TAG_MAP:
                    status = _STATUS_TAG_MAP[tag]
                    break
            if not status and fm.get("status"):
                status = fm["status"]
            due = str(fm.get("due", "")).strip()

        # Fall back to ## Status section
        if not status:
            lines = content.splitlines()
            in_status = False
            for line in lines:
                if line.strip() == "## Status":
                    in_status = True
                    continue
                if line.startswith("## "):
                    in_status = False
                if in_status and line.strip():
                    status = line.strip()
                    break

        # PRD link always from ## PRD section
        lines = content.splitlines()
        in_prd = False
        for line in lines:
            if line.strip() == "## PRD":
                in_prd = True
                continue
            if line.startswith("## "):
                in_prd = False
            if in_prd and line.strip().startswith("- ["):
                m = re.match(r"-\s+\[([^\]]+)\]\(([^)]+)\)", line.strip())
                if m:
                    prd = {"title": m.group(1), "url": m.group(2)}
                break
    except FileNotFoundError:
        pass
    return status, prd, due


_STATUS_TO_TAG = {v: k for k, v in _STATUS_TAG_MAP.items()}


def retrofit_project_yaml():
    """Add YAML frontmatter to all project files that don't have it yet.
    Returns list of updated project names."""
    updated = []
    if not PROJECTS_DIR.exists():
        return updated
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        for md_file in project_dir.glob("*.md"):
            content = md_file.read_text()
            if content.startswith("---"):
                continue  # already has frontmatter

            # Extract status from ## Status section
            status = ""
            for line in content.splitlines():
                if hasattr(retrofit_project_yaml, "_in_status"):
                    if line.strip():
                        status = line.strip()
                        del retrofit_project_yaml._in_status
                        break
                if line.strip() == "## Status":
                    retrofit_project_yaml._in_status = True

            status_tag = _STATUS_TO_TAG.get(status, "in-progress")
            project_name = project_dir.name

            fm_lines = [
                "---",
                "tags:",
                "  - project",
                f"  - {status_tag}",
                f"status: {status or 'In Progress'}",
                f"area: Cars",
                "---",
                "",
            ]
            md_file.write_text("\n".join(fm_lines) + content)
            updated.append(project_name)
    return updated


def get_project_tasks():
    """Return {project_name: {tasks, status, prd}} for all active projects.

    Includes projects with open tasks AND projects with an active status (In Progress /
    In Discovery) even if all tasks are currently checked off — so they don't vanish
    from the daily briefing just because the task list is temporarily empty.
    """
    _ACTIVE_STATUSES = {
        "in progress", "in discovery", "in review",
        "measuring", "dev in progress", "ready for dev",
        "dtd", "ptd", "design in progress", "product review",
        "discovery", "blocked",
    }
    _DONE_STATUSES = {"done", "complete", "completed"}
    _PAUSED_STATUSES = {"paused"}
    result = {}
    if not PROJECTS_DIR.exists():
        return result
    def _sort_key(p):
        return (0, "") if p.name == "Misc" else (1, p.name.lower())

    for project_dir in sorted(PROJECTS_DIR.iterdir(), key=_sort_key):
        if not project_dir.is_dir():
            continue
        for md_file in project_dir.glob("*.md"):
            tasks = [t for t in _parse_tasks(md_file) if not t["done"]]
            status, prd, due = _parse_project_meta(md_file)
            status_lower = status.lower()
            # Skip projects explicitly marked done/complete regardless of stray open tasks
            if status_lower in _DONE_STATUSES:
                continue
            is_active = status_lower in _ACTIVE_STATUSES
            if tasks or is_active:
                result[project_dir.name] = {
                    "tasks": tasks,
                    "status": status,
                    "prd": prd,
                    "due": due,
                }
    return result


def get_all_projects_with_status():
    """Return {project_name: {status, asana_url, md_file}} for ALL project dirs."""
    result = {}
    if not PROJECTS_DIR.exists():
        return result
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        for md_file in project_dir.glob("*.md"):
            if md_file.stem in _SKIP_PROJECT_FILES:
                continue
            status, _, due = _parse_project_meta(md_file)
            fm = _parse_yaml_frontmatter(md_file.read_text())
            result[project_dir.name] = {
                "status": status,
                "due": due,
                "asana_url": fm.get("asana", ""),
                "md_file": md_file,
            }
    return result


def set_project_asana_link(project_name, url):
    """Add or update the asana: field in a project file's YAML frontmatter.

    Returns True if the file was modified, False if already up to date or not found.
    """
    if not PROJECTS_DIR.exists():
        return False
    for project_dir in PROJECTS_DIR.iterdir():
        if not (project_dir.is_dir() and project_dir.name.lower() == project_name.lower()):
            continue
        for md_file in project_dir.glob("*.md"):
            if md_file.stem in _SKIP_PROJECT_FILES:
                continue
            content = md_file.read_text()
            match = _FRONTMATTER.match(content)
            if not match:
                return False
            fm_text = match.group(1)
            if f"asana: {url}" in fm_text:
                return False  # Already up to date
            if re.search(r"^asana:", fm_text, re.MULTILINE):
                new_fm = re.sub(r"^asana:.*$", f"asana: {url}", fm_text, flags=re.MULTILINE)
            else:
                new_fm = fm_text + f"\nasana: {url}"
            md_file.write_text(f"---\n{new_fm}\n---\n" + content[match.end():])
            return True
    return False


def set_project_due(project_name, due_date):
    """Add or update the due: field in a project file's YAML frontmatter.

    Returns True if the file was modified, False if already up to date or not found.
    """
    if not PROJECTS_DIR.exists():
        return False
    for project_dir in PROJECTS_DIR.iterdir():
        if not (project_dir.is_dir() and project_dir.name.lower() == project_name.lower()):
            continue
        for md_file in project_dir.glob("*.md"):
            if md_file.stem in _SKIP_PROJECT_FILES:
                continue
            content = md_file.read_text()
            match = _FRONTMATTER.match(content)
            if not match:
                return False
            fm_text = match.group(1)
            if f"due: {due_date}" in fm_text:
                return False  # Already up to date
            if re.search(r"^due:", fm_text, re.MULTILINE):
                new_fm = re.sub(r"^due:.*$", f"due: {due_date}", fm_text, flags=re.MULTILINE)
            else:
                new_fm = fm_text + f"\ndue: {due_date}"
            md_file.write_text(f"---\n{new_fm}\n---\n" + content[match.end():])
            return True
    return False


def get_project_status_update(project_name):
    """Return (date_str, text) from the ## Status Update section, or (None, None) if absent."""
    if not PROJECTS_DIR.exists():
        return None, None
    for project_dir in PROJECTS_DIR.iterdir():
        if not (project_dir.is_dir() and project_dir.name.lower() == project_name.lower()):
            continue
        for md_file in project_dir.glob("*.md"):
            if md_file.stem in _SKIP_PROJECT_FILES:
                continue
            content = md_file.read_text()
            m = re.search(r"## Status Update\s*\n\*?(\d{4}-\d{2}-\d{2})\*?:?\s*(.+?)(?=\n##|\Z)",
                          content, re.DOTALL)
            if m:
                return m.group(1).strip(), m.group(2).strip()
    return None, None


def set_project_status_update(project_name, text, update_date=None):
    """Write or replace the ## Status Update section in a project file.

    Creates the section if it doesn't exist. update_date defaults to today.
    Returns True if the file was modified.
    """
    from datetime import date as _date
    update_date = update_date or _date.today().isoformat()
    if not PROJECTS_DIR.exists():
        return False
    for project_dir in PROJECTS_DIR.iterdir():
        if not (project_dir.is_dir() and project_dir.name.lower() == project_name.lower()):
            continue
        for md_file in project_dir.glob("*.md"):
            if md_file.stem in _SKIP_PROJECT_FILES:
                continue
            content = md_file.read_text()
            new_section = f"## Status Update\n*{update_date}*: {text}\n"
            if "## Status Update" in content:
                content = re.sub(
                    r"## Status Update\s*\n.*?(?=\n##|\Z)",
                    new_section,
                    content,
                    flags=re.DOTALL,
                )
            else:
                # Append before ## Open Tasks if it exists, otherwise at end
                if "## Open Tasks" in content:
                    content = content.replace("## Open Tasks", f"{new_section}\n## Open Tasks", 1)
                else:
                    content = content.rstrip() + f"\n\n{new_section}"
            md_file.write_text(content)
            return True
    return False


def get_all_status_updates():
    """Return {project_name: (date_str, text)} for all projects with a Status Update section."""
    result = {}
    if not PROJECTS_DIR.exists():
        return result
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        d, text = get_project_status_update(project_dir.name)
        if d and text:
            result[project_dir.name] = (d, text)
    return result


def get_new_projects_this_week():
    """Return list of project names whose main .md file was created in the last 7 days."""
    import time
    cutoff = time.time() - 7 * 86400
    new_projects = []
    if not PROJECTS_DIR.exists():
        return new_projects
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for md_file in project_dir.glob("*.md"):
            if md_file.stem in _SKIP_PROJECT_FILES:
                continue
            if md_file.stat().st_birthtime > cutoff:
                new_projects.append(project_dir.name)
    return sorted(set(new_projects))


def log_weekly_change(event_type, project, task=None, from_val=None, to_val=None):
    """Append one change event to data/weekly_log.jsonl.
    event_type: task_completed | task_deleted | project_status_changed | project_created | due_date_changed
    """
    DATA_DIR.mkdir(exist_ok=True)
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "type": event_type, "project": project}
    if task is not None:
        entry["task"] = task
    if from_val is not None:
        entry["from"] = from_val
    if to_val is not None:
        entry["to"] = to_val
    with WEEKLY_LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def get_weekly_log(days=7):
    """Return log entries from last N days, oldest first."""
    if not WEEKLY_LOG_FILE.exists():
        return []
    cutoff = datetime.now() - timedelta(days=days)
    entries = []
    for line in WEEKLY_LOG_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            if datetime.fromisoformat(e["ts"]) >= cutoff:
                entries.append(e)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return entries


def save_project_snapshot():
    """Save current statuses + due dates to data/project_snapshot_YYYY-MM-DD.json. Called by pm.py weekly."""
    all_projects = get_all_projects_with_status()
    snapshot = {
        "date": date.today().isoformat(),
        "projects": {
            name: {"status": info.get("status", ""), "due": info.get("due", "")}
            for name, info in all_projects.items()
        },
    }
    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / f"project_snapshot_{snapshot['date']}.json"
    out.write_text(json.dumps(snapshot, indent=2))
    return out


def load_last_project_snapshot():
    """Load most recent project snapshot (excluding today's). Returns dict or None."""
    if not DATA_DIR.exists():
        return None
    today = date.today().isoformat()
    for f in sorted(DATA_DIR.glob("project_snapshot_*.json"), reverse=True):
        if f.stem.replace("project_snapshot_", "") < today:
            try:
                return json.loads(f.read_text())
            except Exception:
                return None
    return None


def save_status_snapshot():
    """Save lightweight {project: status} dict for change detection. Called on every sync."""
    all_projects = get_all_projects_with_status()
    snapshot = {name: info.get("status", "") for name, info in all_projects.items()}
    DATA_DIR.mkdir(exist_ok=True)
    STATUS_SNAPSHOT_FILE.write_text(json.dumps(snapshot))


def load_status_snapshot():
    """Load last status snapshot. Returns dict or {}."""
    if not STATUS_SNAPSHOT_FILE.exists():
        return {}
    try:
        return json.loads(STATUS_SNAPSHOT_FILE.read_text())
    except Exception:
        return {}


def backfill_weekly_log_from_daily_notes(days=7):
    """Seed weekly_log.jsonl from completed [x] tasks in recent daily notes.
    Only call once on first deploy — skips if log already has entries from today.
    """
    today_str = date.today().isoformat()
    if WEEKLY_LOG_FILE.exists():
        for line in WEEKLY_LOG_FILE.read_text().splitlines():
            try:
                e = json.loads(line)
                if e.get("ts", "").startswith(today_str):
                    print("Backfill already run today — skipping.")
                    return
            except Exception:
                continue

    cutoff = date.today() - timedelta(days=days)
    daily_dir = VAULT_PATH / "Daily Notes"
    count = 0
    for week_dir in sorted(daily_dir.iterdir()):
        if not week_dir.is_dir():
            continue
        for note_file in sorted(week_dir.glob("*.md")):
            try:
                note_date = date.fromisoformat(note_file.stem)
            except ValueError:
                continue
            if note_date < cutoff:
                continue
            current_project = None
            for line in note_file.read_text().splitlines():
                if line.startswith("### "):
                    current_project = re.split(r"\s+[—–-]\s+", line[4:].strip())[0].strip()
                m = re.match(r"^\s*-\s+\[[xX]\]\s+(.+)$", line)
                if m and current_project:
                    task_text = _DUE_DATE.sub("", m.group(1)).strip()
                    task_text = re.sub(r"\s*✅\s*\d{4}-\d{2}-\d{2}\s*$", "", task_text).strip()
                    ts = f"{note_date.isoformat()}T12:00:00"
                    entry = {
                        "ts": ts, "type": "task_completed",
                        "project": current_project, "task": task_text, "backfilled": True,
                    }
                    DATA_DIR.mkdir(exist_ok=True)
                    with WEEKLY_LOG_FILE.open("a") as f:
                        f.write(json.dumps(entry) + "\n")
                    count += 1
    print(f"Backfilled {count} completed tasks from last {days} days of daily notes.")


def get_overdue_tasks():
    """Return {project_name: [task_dicts]} for open tasks with due date <= today, sorted by due date."""
    today = date.today().isoformat()
    result = {}
    if not PROJECTS_DIR.exists():
        return result
    def _sort_key(p):
        return (0, "") if p.name == "Misc" else (1, p.name.lower())
    for project_dir in sorted(PROJECTS_DIR.iterdir(), key=_sort_key):
        if not project_dir.is_dir():
            continue
        for md_file in project_dir.glob("*.md"):
            tasks = [
                t for t in _parse_tasks(md_file)
                if not t["done"] and t.get("due") and t["due"] <= today
            ]
            if tasks:
                result[project_dir.name] = sorted(tasks, key=lambda t: t["due"])
    return result


def get_completed_tasks():
    """Return all [x] tasks grouped by project name."""
    result = {}
    if not PROJECTS_DIR.exists():
        return result
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        for md_file in project_dir.glob("*.md"):
            done = [t for t in _parse_tasks(md_file, include_done=True) if t["done"]]
            if done:
                result[project_dir.name] = [t["text"] for t in done]
    return result


def get_previous_weekly_update():
    """Return the content of the most recent detailed weekly update (excludes exec files)."""
    weekly_dir = AREAS_DIR / "Weekly Updates"
    if not weekly_dir.exists():
        return ""
    files = sorted(
        [f for f in weekly_dir.rglob("*.md") if not f.stem.endswith("-exec")],
        reverse=True,
    )
    if not files:
        return ""
    return files[0].read_text()


def save_weekly_update(content, report_date, suffix=""):
    """Save a weekly update to Areas/Weekly Updates/<monday>/YYYY-MM-DD{suffix}.md."""
    monday = report_date - timedelta(days=report_date.weekday())
    week_dir = AREAS_DIR / "Weekly Updates" / monday.isoformat()
    week_dir.mkdir(parents=True, exist_ok=True)
    note_file = week_dir / f"{report_date.isoformat()}{suffix}.md"
    note_file.write_text(content)
    return note_file


def get_ideas():
    """Return idea section names from Ideas to Investigate.md."""
    if not IDEAS_FILE.exists():
        return []
    content = IDEAS_FILE.read_text()
    return re.findall(r"^## (.+)$", content, re.MULTILINE)


def set_project_prd(project_name, title, url):
    """Store or update the PRD link in a project file under ## PRD."""
    project_dir = PROJECTS_DIR / project_name
    md_files = list(project_dir.glob("*.md")) if project_dir.exists() else []
    if not md_files:
        return False

    md_file = md_files[0]
    content = md_file.read_text()
    prd_line = f"- [{title}]({url})"

    if "## PRD" in content:
        # Replace existing PRD section content
        new_content = re.sub(
            r"(## PRD\n).*?(\n## |\Z)",
            lambda m: f"{m.group(1)}{prd_line}\n{m.group(2)}",
            content,
            flags=re.DOTALL,
        )
    else:
        # Append PRD section before ## Context or at end
        if "## Context" in content:
            new_content = content.replace("## Context", f"## PRD\n{prd_line}\n\n## Context")
        else:
            new_content = content.rstrip() + f"\n\n## PRD\n{prd_line}\n"

    md_file.write_text(new_content)
    return True


def _normalize_task(t):
    """Strip markdown URLs from [LABEL](url) patterns for dedup comparison."""
    return re.sub(r'\(https?://[^)]+\)', '', t).strip()


def _format_task_with_url(task_text, url=None):
    """If url provided, convert leading [LABEL] to [LABEL](url) markdown link."""
    if not url:
        return task_text
    return re.sub(r'^\[([A-Z]+)\] ', lambda m: f'[{m.group(1)}]({url}) ', task_text)


def task_exists_in_projects(task_text):
    """Return True if task_text appears (open or done) in any project file.
    Strips markdown URLs from [LABEL](url) patterns before comparing."""
    normalized = _normalize_task(task_text)
    if not PROJECTS_DIR.exists():
        return False
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for md_file in project_dir.glob("*.md"):
            for line in md_file.read_text().splitlines():
                m = re.match(r'\s*-\s+\[[ xX]\]\s+(.+)$', line)
                if m and _normalize_task(m.group(1).strip()) == normalized:
                    return True
    return False


def append_task_to_project(project_name, task_text, url=None):
    """Add an unchecked task under ## Open Tasks in the project file.
    If url is provided, [LABEL] prefix becomes a clickable [LABEL](url) link."""
    formatted = _format_task_with_url(task_text, url)
    project_dir = PROJECTS_DIR / project_name
    md_files = list(project_dir.glob("*.md")) if project_dir.exists() else []

    if not md_files:
        project_dir.mkdir(parents=True, exist_ok=True)
        md_file = project_dir / f"{project_name}.md"
        md_file.write_text(
            f"# {project_name}\n\n## Status\nIn Progress\n\n## Open Tasks\n- [ ] {formatted}\n"
        )
        return

    md_file = md_files[0]
    lines = md_file.read_text().splitlines()

    # Find the Open Tasks section and insert before the next ## heading
    insert_idx = None
    in_tasks = False
    for i, line in enumerate(lines):
        if line.strip() == "## Open Tasks":
            in_tasks = True
        elif in_tasks and line.startswith("## "):
            insert_idx = i
            break

    if in_tasks:
        if insert_idx is not None:
            lines.insert(insert_idx, f"- [ ] {formatted}")
        else:
            lines.append(f"- [ ] {formatted}")
    else:
        lines += ["", "## Open Tasks", f"- [ ] {formatted}"]

    md_file.write_text("\n".join(lines) + "\n")


def mark_task_done(file_path, task_text):
    """Flip the first matching unchecked task to done."""
    path = Path(file_path)
    content = path.read_text()
    # Strip due date markers so we match regardless of @due() vs 📅 format
    clean = _DUE_DATE.sub("", task_text).strip()
    pattern = (
        r"^(\s*-\s+\[) \](\s+"
        + re.escape(clean)
        + r"(?:\s+(?:@due\(\d{4}-\d{2}-\d{2}\)|📅\s*\d{4}-\d{2}-\d{2}))?)\s*$"
    )
    new_content = re.sub(pattern, r"\1x]\2", content, count=1, flags=re.MULTILINE)
    if new_content != content:
        path.write_text(new_content)
        return True
    return False


_GENERATED_SECTIONS = {
    "due today & overdue",
    "active projects",
    "to investigate",
    "claude can help with",
    "industry news",
}


def _read_overdue_checkboxes(note_path):
    """Return {(proj, clean_text): (done, due)} from the existing Due Today section.
    Used to preserve [x] states and due dates when the note is regenerated."""
    if not note_path.exists():
        return {}
    state = {}
    current_proj = None
    in_overdue = False
    for line in note_path.read_text().splitlines():
        if line.startswith("## Due Today & Overdue"):
            in_overdue = True
        elif line.startswith("## ") and in_overdue:
            break
        elif in_overdue and line.startswith("### "):
            current_proj = line[4:].strip()
        elif in_overdue and current_proj:
            m = _CHECKBOX.match(line)
            if m:
                _, status, text = m.groups()
                due_m = _DUE_DATE.search(text)
                due = (due_m.group(1) or due_m.group(2)) if due_m else None
                clean = _DUE_DATE.sub("", text).strip()
                state[(current_proj, clean)] = (status.lower() == "x", due)
    return state


def _read_existing_section_tasks(note_path):
    """Return {(section, project): [task_line, ...]} for tasks in generated sections.
    Used to preserve manually-added tasks when the note is regenerated."""
    if not note_path.exists():
        return {}
    tasks = {}  # (section_heading_lower, project_name) -> [raw_line, ...]
    current_section = None
    current_project = None
    for line in note_path.read_text().splitlines():
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            if heading in _GENERATED_SECTIONS:
                current_section = heading
                current_project = None
            else:
                current_section = None
                current_project = None
        elif current_section and line.startswith("### "):
            current_project = re.split(r"\s+[—–-]\s+", line[4:].strip())[0].strip()
        elif current_section and current_project:
            m = _CHECKBOX.match(line)
            if m:
                tasks.setdefault((current_section, current_project), []).append(line)
    return tasks


def _read_investigate_checkboxes(note_path):
    """Return {clean_text: done} from the existing To Investigate section.
    Used to preserve [x] states when the note is regenerated."""
    if not note_path.exists():
        return {}
    state = {}
    in_section = False
    for line in note_path.read_text().splitlines():
        if line.startswith("## To Investigate"):
            in_section = True
        elif line.startswith("## ") and in_section:
            break
        elif in_section:
            m = _CHECKBOX.match(line)
            if m:
                _, status, text = m.groups()
                state[text.strip()] = status.lower() == "x"
    return state


def _extract_user_sections(existing_lines, exclude=None):
    """Return lines from sections the user added that pm.py doesn't generate.
    If exclude is given, also skip those section names (lowercase)."""
    skip = _GENERATED_SECTIONS | (exclude or set())
    user_content = []
    in_user_section = False
    current = []

    for line in existing_lines:
        if line.startswith("## "):
            if in_user_section and current:
                user_content.extend(current)
            heading = line[3:].strip().lower()
            if heading not in skip:
                in_user_section = True
                current = ["---", "", line, ""]
            else:
                in_user_section = False
                current = []
        elif in_user_section:
            current.append(line)

    if in_user_section and current:
        user_content.extend(current)

    return user_content


def _extract_named_user_sections(existing_lines, names):
    """Return lines from specific user sections (by lowercase heading name)."""
    result = []
    in_target = False
    current = []

    for line in existing_lines:
        if line.startswith("## "):
            if in_target and current:
                result.extend(current)
            heading = line[3:].strip().lower()
            if heading in names:
                in_target = True
                current = ["---", "", line, ""]
            else:
                in_target = False
                current = []
        elif in_target:
            current.append(line)

    if in_target and current:
        result.extend(current)

    return result


def write_daily_note(project_tasks, asana_sections, ideas, news=None, actionable=None):
    """Write today's to-do list as a markdown file in Daily Notes/YYYY-Www/."""
    today = date.today()
    day_str = today.strftime("%A, %b %-d %Y")
    note_file = _daily_note_path(today)

    meeting_note_name = f"{today.isoformat()} Meeting Notes"
    lines = [f"# {day_str}", "", f"📝 [[{meeting_note_name}]]", ""]

    # Read ALL existing tasks from generated sections BEFORE overwriting.
    # This lets us preserve manually-added tasks on re-runs.
    existing_section_tasks = _read_existing_section_tasks(note_file)

    # Due today & overdue — static list so completed tasks stay visible in the note.
    # On re-runs, existing [x] states are preserved so done tasks don't vanish.
    existing_states = _read_overdue_checkboxes(note_file)  # read BEFORE overwriting
    overdue_tasks = get_overdue_tasks()

    # Build merged task list per project:
    #   - All undone overdue tasks from project files (with preserved [x] if user checked them)
    #   - Any [x] tasks from the existing note that are no longer undone in project files
    merged = {}  # {proj: [(clean_text, done, due)]}
    for proj, tasks in overdue_tasks.items():
        for t in tasks:
            clean = _DUE_DATE.sub("", t["text"]).strip()
            done, _ = existing_states.get((proj, clean), (False, None))
            merged.setdefault(proj, []).append((clean, done, t.get("due")))

    for (proj, clean), (done, due) in existing_states.items():
        if not done:
            continue
        # Re-include completed tasks that were removed from get_overdue_tasks()
        if clean not in [t[0] for t in merged.get(proj, [])]:
            merged.setdefault(proj, []).append((clean, True, due))

    # Sort: undone first (by due date), then done
    for proj in merged:
        merged[proj].sort(key=lambda t: (1 if t[1] else 0, t[2] or ""))

    def _clean_task_text(line):
        """Extract comparable task text from a checkbox line."""
        m = _CHECKBOX.match(line)
        if not m:
            return line.strip()
        text = m.group(3)
        # Strip due dates, URLs, and whitespace for comparison
        text = _DUE_DATE.sub("", text).strip()
        return text

    lines += ["---", "", "## Due Today & Overdue", ""]
    if merged:
        proj_order = sorted(merged.keys(), key=lambda p: (0 if p == "Misc" else 1, p.lower()))
        for proj_name in proj_order:
            lines.append(f"### {proj_name}")
            generated_texts = set()
            for clean, done, due in merged[proj_name]:
                due_str = f" @due({due})" if due else ""
                status = "x" if done else " "
                lines.append(f"- [{status}] {clean}{due_str}")
                generated_texts.add(clean)
            # Re-inject manually-added tasks that aren't from project files
            for old_line in existing_section_tasks.get(("due today & overdue", proj_name), []):
                if _clean_task_text(old_line) not in generated_texts:
                    lines.append(old_line)
            lines.append("")
        # Also re-inject tasks under projects that only exist in the old note
        for (sec, proj), old_lines in existing_section_tasks.items():
            if sec == "due today & overdue" and proj not in merged:
                lines.append(f"### {proj}")
                lines.extend(old_lines)
                lines.append("")
    else:
        lines += ["_No overdue or due-today tasks._", ""]

    # Build set of (project, clean_text) already shown in Due Today & Overdue
    overdue_shown = {
        (proj, clean)
        for proj, items in merged.items()
        for clean, done, due in items
    }

    # Carryover / Action Queue — insert before Active Projects so it's visible near the top.
    # First run: carry over unchecked tasks from yesterday's focus/action queue.
    # Re-run: preserve the existing Action Queue (and other user sections that appear
    # before Active Projects) in the same position.
    if not note_file.exists():
        prev_note = _find_most_recent_note_before(today)
        carryover = _read_unchecked_user_tasks(prev_note)
        if carryover:
            seen_dedup = set()
            for line in lines:
                m = _CHECKBOX.match(line)
                if m:
                    seen_dedup.add(_clean_task_for_dedup(m.group(3)))
            unique = []
            for line in carryover:
                m = _CHECKBOX.match(line)
                if m:
                    clean = _clean_task_for_dedup(m.group(3))
                    if clean not in seen_dedup:
                        unique.append(line)
                        seen_dedup.add(clean)
            if unique:
                lines += ["---", "", "## Action Queue", ""]
                lines.extend(unique)
                lines.append("")
    else:
        # Re-run: preserve user sections that should appear before Active Projects
        _early_user_sections = {"action queue", "today's focus", "carryover from yesterday", "carryover", "focus"}
        existing_lines = note_file.read_text().splitlines()
        early_sections = _extract_named_user_sections(existing_lines, _early_user_sections)
        if early_sections:
            lines.extend(early_sections)

    # Active Projects — skip tasks already in Due Today & Overdue
    if project_tasks:
        lines += ["---", "", "## Active Projects", ""]
        for project, data in project_tasks.items():
            tasks = data["tasks"]
            status = data.get("status", "")
            status_str = f" — {status}" if status else ""
            raw_due = data.get("due", "")
            if raw_due:
                try:
                    from datetime import date as _date
                    due_display = f" · {_date.fromisoformat(raw_due).strftime('%-m/%-d')}"
                except ValueError:
                    due_display = f" · {raw_due}"
            else:
                due_display = ""
            task_lines = []
            generated_texts = set()
            for t in tasks:
                indent = "  " * (t["indent"] // 2)
                task_text = _DUE_DATE.sub("", t["text"]).strip()
                if (project, task_text) in overdue_shown:
                    continue
                due_str = f" @due({t['due']})" if t.get("due") else ""
                task_lines.append(f"{indent}- [ ] {task_text}{due_str}")
                generated_texts.add(task_text)
            # Re-inject manually-added tasks that aren't from project files
            for old_line in existing_section_tasks.get(("active projects", project), []):
                if _clean_task_text(old_line) not in generated_texts:
                    task_lines.append(old_line)
            if task_lines:
                lines.append(f"### {project}{status_str}{due_display}")
                lines.extend(task_lines)
                lines.append("")
            elif data.get("status", "").lower() in {"in progress", "in discovery", "in review"}:
                # Active project with no open tasks — check for manually-added tasks first
                manual = existing_section_tasks.get(("active projects", project), [])
                lines.append(f"### {project}{status_str}{due_display}")
                if manual:
                    lines.extend(manual)
                else:
                    lines.append("- *(no open tasks)*")
                lines.append("")
        # Also re-inject tasks under projects that only exist in the old note
        # (e.g., user added a new ### heading manually)
        generated_projects = set(project_tasks.keys())
        for (sec, proj), old_lines in existing_section_tasks.items():
            if sec == "active projects" and proj not in generated_projects:
                lines.append(f"### {proj}")
                lines.extend(old_lines)
                lines.append("")

    # Ideas — render as checkboxes, preserve [x] states on re-run
    existing_investigate = _read_investigate_checkboxes(note_file)
    if ideas or existing_investigate:
        lines += ["---", "", "## To Investigate", ""]
        # Include all ideas from source file + any [x] items from existing note
        seen = set()
        for idea in (ideas or []):
            done = existing_investigate.get(idea, False)
            status = "x" if done else " "
            lines.append(f"- [{status}] {idea}")
            seen.add(idea)
        # Re-include checked items that may no longer be in source file
        for text, done in existing_investigate.items():
            if done and text not in seen:
                lines.append(f"- [x] {text}")
        lines.append("")

    # Claude can help with
    if actionable:
        lines += ["---", "", "## Claude Can Help With", ""]
        for project, task, label in actionable:
            lines.append(f"- [{label}] {task}  *({project})*")
        lines.append("")

    # Industry news (bottom)
    if news:
        lines += ["---", "", "## Industry News", ""]
        for n in news:
            source = f" · {n['source']}" if n.get("source") else ""
            age = f" · {n['age']}" if n.get("age") else ""
            lines.append(f"- {n['title']}  *[{source.lstrip(' · ')}{age}]*")
        lines.append("")

    # Preserve any sections the user added to the existing note
    # (excluding early sections already inserted before Active Projects)
    _early_section_names = {"action queue", "today's focus", "carryover from yesterday", "carryover", "focus"}
    if note_file.exists():
        user_sections = _extract_user_sections(
            note_file.read_text().splitlines(), exclude=_early_section_names
        )
        if user_sections:
            lines += user_sections

    note_file.write_text("\n".join(lines))
    return note_file


def inject_task_into_daily_note(task_text, project_name, for_date=None, url=None):
    """Insert a task into an existing daily note under the matching project section.

    Finds '### {project_name}' (case-insensitive partial match) and appends the
    task just before the next blank line that follows the section's task list.
    If the task already appears in the note it is skipped (URL-normalized comparison).
    If url is provided, [LABEL] prefix becomes a clickable [LABEL](url) link.
    Returns True if the note was modified, False otherwise.
    """
    from datetime import date as _date
    target_date = for_date or _date.today()
    note_file = _find_daily_note(target_date)
    if not note_file.exists():
        return False

    lines = note_file.read_text().splitlines()
    formatted = _format_task_with_url(task_text, url)
    task_line = f"- [ ] {formatted}"

    # Skip if already present (normalize URLs for comparison)
    normalized = _normalize_task(task_text)
    if any(_normalize_task(l) and normalized in _normalize_task(l) for l in lines):
        return False

    # Find the project section heading
    section_idx = None
    for i, line in enumerate(lines):
        if line.startswith("### ") and project_name.lower() in line.lower():
            section_idx = i
            break

    if section_idx is None:
        return False

    # Find the last task line in this section (before next ### or ---)
    insert_idx = section_idx + 1
    for i in range(section_idx + 1, len(lines)):
        if lines[i].startswith("### ") or lines[i].startswith("---"):
            break
        if lines[i].strip().startswith("- "):
            insert_idx = i + 1

    lines.insert(insert_idx, task_line)
    note_file.write_text("\n".join(lines))
    return True


def create_daily_meeting_notes(for_date=None):
    """
    Create a blank meeting notes file for the given date if one doesn't exist.
    Returns (path, created) — created=True if a new file was made.
    """
    for_date = for_date or date.today()
    week_dir = _meeting_notes_week_dir(for_date)
    note_file = week_dir / f"{for_date.isoformat()} Meeting Notes.md"

    if note_file.exists():
        return note_file, False

    template = f"""---
tags:
  - meeting
date: {for_date.isoformat()}
projects: []
---

# {for_date.isoformat()} Meeting Name

## Notes


## Action Items
- [ ]
"""
    note_file.write_text(template)
    return note_file, True


def write_daily_meeting_notes_with_agenda(meetings, for_date=None):
    """Write the daily meeting notes file with a section per meeting.

    meetings: list of dicts with keys:
      - title (str)
      - time  (str, e.g. "9:30 AM")
      - attendees (list of str, display names, PM excluded)
      - description (str, optional — agenda text, Zoom links stripped)
      - num_attendees (int, optional)

    Returns (path, True) if file was created, (path, False) if it already existed.
    """
    import re as _re
    for_date = for_date or date.today()
    week_dir = _meeting_notes_week_dir(for_date)
    note_file = week_dir / f"{for_date.isoformat()} Meeting Notes.md"
    day_str = for_date.strftime("%A, %b %-d %Y")

    # Never overwrite an existing meeting notes file — preserve any notes already written.
    # Exception: if the file contains only the default empty template (no real meetings written),
    # overwrite it so /today can repopulate it on re-runs.
    if note_file.exists():
        existing = note_file.read_text()
        has_meeting_sections = '## ' in existing and ' — ' in existing
        if has_meeting_sections:
            return note_file, False
        # else fall through and overwrite the stale template

    lines = [
        "---",
        "tags:",
        "  - meeting",
        f"date: {for_date.isoformat()}",
        "projects: []",
        "---",
        "",
        f"# Meeting Notes — {day_str}",
        "",
    ]

    _zoom_re = _re.compile(
        r'(https?://[^\s]*zoom\.us[^\s]*|Meeting ID:.*|Passcode:.*|'
        r'Join by phone.*|One tap mobile.*|\+\d[\d ,]+#)',
        _re.IGNORECASE
    )

    for m in meetings:
        header = f"{m['time']} — {m['title']}"
        lines.append(f"## {header}")
        lines.append("")

        if m.get('attendees'):
            attendee_str = ", ".join(m['attendees'])
            lines.append(f"**Attendees:** {attendee_str}")
            lines.append("")

        # Clean description — strip Zoom boilerplate, keep real agenda
        desc = m.get('description', '').strip()
        if desc:
            # Strip HTML tags
            desc = _re.sub(r'<[^>]+>', ' ', desc)
            # Strip Zoom links and phone numbers
            desc = '\n'.join(
                line for line in desc.splitlines()
                if not _zoom_re.search(line) and line.strip()
            )
            desc = desc.strip()
        if desc:
            lines.append(f"**Agenda:** {desc}")
            lines.append("")

        lines.append("**Notes**")
        lines.append("")
        lines.append("")
        lines.append("**Action Items**")
        lines.append("- [ ] ")
        lines.append("")
        lines.append("---")
        lines.append("")

    note_file.write_text("\n".join(lines))
    return note_file, True


def create_zoom_meeting_note(date_str, title, summary, action_items=None, project=None):
    """Create a meeting note from a Zoom AI summary.

    If project matches a folder in Projects/, creates:
        Projects/[project]/Meeting Notes/YYYY-MM-DD - Title.md
    Otherwise appends a section to:
        Meeting Notes/YYYY-MM-DD Meeting Notes.md

    Returns (path_str, created) — created=False if the note was already filed.
    """
    action_items = action_items or []
    safe_title = re.sub(r'[<>:"/\\|?*\n\r]', '', title).strip()[:80]

    note_lines = ["## Summary", "", (summary.strip() or "_No summary provided._"), ""]
    if action_items:
        note_lines += ["## Action Items", ""]
        note_lines += [f"- [ ] {item.strip()}" for item in action_items if item.strip()]
        note_lines.append("")

    if project:
        # Find matching project directory (case-insensitive)
        project_dir = None
        if PROJECTS_DIR.exists():
            for d in PROJECTS_DIR.iterdir():
                if d.is_dir() and d.name.lower() == project.lower():
                    project_dir = d
                    break
        if not project_dir:
            project_dir = PROJECTS_DIR / project

        meeting_dir = project_dir / "Meeting Notes"
        meeting_dir.mkdir(parents=True, exist_ok=True)
        note_file = meeting_dir / f"{date_str} - {safe_title}.md"

        if note_file.exists():
            return str(note_file), False

        content = "\n".join([
            f"# {title}",
            f"**Date:** {date_str}  |  **Source:** Zoom AI Summary",
            "",
            *note_lines,
        ])
        note_file.write_text(content)
        return str(note_file), True

    else:
        try:
            zoom_date = date.fromisoformat(date_str)
            week_dir = _meeting_notes_week_dir(zoom_date)
        except ValueError:
            week_dir = MEETING_NOTES_DIR
            week_dir.mkdir(parents=True, exist_ok=True)
        note_file = week_dir / f"{date_str} Meeting Notes.md"

        # Check if this meeting is already appended to avoid duplicates
        if note_file.exists() and f"## {title}" in note_file.read_text():
            return str(note_file), False

        section = "\n".join([
            "---",
            "",
            f"## {title} _(Zoom AI Summary)_",
            f"**Date:** {date_str}",
            "",
            *note_lines,
        ])

        if note_file.exists():
            note_file.write_text(note_file.read_text().rstrip() + "\n\n" + section + "\n")
        else:
            header = (
                f"---\ntags:\n  - meeting\ndate: {date_str}\nprojects: []\n---\n\n"
                f"# {date_str} Meeting Notes\n\n"
            )
            note_file.write_text(header + section + "\n")

        return str(note_file), True


KANBAN_FILE = PROJECTS_DIR / "Cars Project Board.md"
OVERVIEW_FILE = PROJECTS_DIR / "Project Overview.md"
_KANBAN_COLUMNS = ["In Discovery", "In Progress", "Done"]
_SKIP_PROJECT_FILES = {"Cars Project Board", "Project Overview"}


def _update_project_yaml_status(md_file, new_status):
    """Update status tag and status field in a project file's YAML frontmatter."""
    content = md_file.read_text()
    m = _FRONTMATTER.match(content)
    if not m:
        return
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return
    new_tag = _STATUS_TO_TAG.get(new_status, "in-progress")
    tags = [t for t in (fm.get("tags") or []) if t not in _STATUS_TAG_MAP]
    tags.append(new_tag)
    fm["tags"] = tags
    fm["status"] = new_status
    new_fm_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True).strip()
    new_content = _FRONTMATTER.sub(f"---\n{new_fm_str}\n---\n", content, count=1)
    # Keep ## Status section in sync
    new_content = re.sub(r"(## Status\n)[^\n#]*", f"\\g<1>{new_status}", new_content)
    md_file.write_text(new_content)


def _build_kanban_content(projects_by_status):
    lines = ["---", "kanban-plugin: basic", "---", ""]
    for col in _KANBAN_COLUMNS:
        lines.append(f"## {col}")
        lines.append("")
        for name in projects_by_status.get(col, []):
            lines.append(f"- [ ] [[{name}]]")
        lines.append("")
    lines += ["%% kanban:settings", '{"kanban-plugin":"basic"}', "%%"]
    return "\n".join(lines)


def create_kanban_board():
    """Generate Cars Project Board from current project YAML statuses."""
    if not PROJECTS_DIR.exists():
        return None
    projects_by_status = {col: [] for col in _KANBAN_COLUMNS}
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir() or project_dir.name in _SKIP_PROJECT_FILES:
            continue
        for md_file in project_dir.glob("*.md"):
            status, _, _due = _parse_project_meta(md_file)
            bucket = status if status in projects_by_status else "In Progress"
            projects_by_status[bucket].append(project_dir.name)
            break
    KANBAN_FILE.write_text(_build_kanban_content(projects_by_status))
    return KANBAN_FILE


def sync_kanban_to_projects():
    """Read the kanban board, sync any column changes back to project YAML.
    Also adds new projects to the board if they're not on it yet.
    Returns list of {project, old, new} dicts for status changes."""
    if not KANBAN_FILE.exists():
        return []

    content = KANBAN_FILE.read_text()
    # Parse column each project is in
    current_col = None
    kanban_status = {}
    for line in content.splitlines():
        s = line.strip()
        if s.startswith("## ") and not s.startswith("%%"):
            col = s[3:].strip()
            current_col = col if col in _KANBAN_COLUMNS else None
        elif current_col and (s.startswith("- [ ] ") or s.startswith("- [x] ")):
            card = s[6:].strip()
            m = re.match(r"\[\[(.+?)\]\]", card)
            kanban_status[m.group(1) if m else card] = current_col

    # Sync changes to project YAML
    changes = []
    new_to_board = []
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir() or project_dir.name in _SKIP_PROJECT_FILES:
            continue
        name = project_dir.name
        for md_file in project_dir.glob("*.md"):
            old_status, _, _due = _parse_project_meta(md_file)
            if name not in kanban_status:
                col = old_status if old_status in _KANBAN_COLUMNS else "In Progress"
                new_to_board.append((name, col))
            elif kanban_status[name] != old_status:
                _update_project_yaml_status(md_file, kanban_status[name])
                changes.append({"project": name, "old": old_status, "new": kanban_status[name]})
            break

    # Add new projects to kanban
    if new_to_board:
        lines = content.splitlines()
        for name, col in new_to_board:
            insert_at = len(lines) - 4  # before kanban:settings block
            for i, line in enumerate(lines):
                if line.strip() == f"## {col}":
                    insert_at = i + 1
                elif i > insert_at and line.strip().startswith("- "):
                    insert_at = i + 1
                elif i > insert_at and (line.strip().startswith("##") or line.strip().startswith("%%")):
                    break
            lines.insert(insert_at, f"- [ ] [[{name}]]")
        KANBAN_FILE.write_text("\n".join(lines))

    return changes


def create_project_overview():
    """Create/update a Dataview + Tasks dashboard at Projects/Project Overview.md."""
    content = """\
---
tags:
  - dashboard
---

# Cars — Project Overview

## Projects by Status

```dataview
TABLE status, area
FROM "Projects"
WHERE contains(tags, "project") AND !contains(tags, "dashboard")
SORT status ASC
```

## Open Tasks with Due Dates

```tasks
not done
has due date
sort by due
group by filename
```

## Recently Updated

```dataview
TABLE file.mtime as "Updated", status
FROM "Projects"
WHERE contains(tags, "project") AND !contains(tags, "dashboard")
SORT file.mtime DESC
LIMIT 8
```
"""
    OVERVIEW_FILE.write_text(content)
    return OVERVIEW_FILE


def get_meeting_action_items(for_date=None):
    """
    Parse action items from meeting notes for a specific date.
    Handles files with multiple meetings concatenated (e.g. '2026-02-23 Meeting Notes.md').
    Returns list of {meeting, tasks: [text]} dicts.
    """
    for_date = for_date or date.today()
    results = []

    if not MEETING_NOTES_DIR.exists():
        return results

    for md_file in MEETING_NOTES_DIR.glob(f"**/{for_date.isoformat()}*.md"):
        content = md_file.read_text()
        # Split on top-level headings (# Title) — each is one meeting
        blocks = re.split(r"(?m)^(?=# )", content)
        for block in blocks:
            if not block.strip():
                continue
            lines = block.splitlines()
            meeting_name = lines[0].lstrip("# ").strip() if lines else "Unknown"

            in_action_items = False
            tasks = []
            for line in lines[1:]:
                if re.match(r"^## Action Items", line.strip()):
                    in_action_items = True
                    continue
                if line.startswith("## ") and in_action_items:
                    break
                if in_action_items:
                    m = re.match(r"^\s*-\s+\[ \]\s+(.+)$", line)
                    if m and m.group(1).strip():
                        tasks.append(m.group(1).strip())

            if tasks:
                results.append({"meeting": meeting_name, "tasks": tasks})

    return results


def get_meeting_notes_this_week():
    """
    Return the contents of all meeting notes from the current week (Mon–today).
    Files should be named: YYYY-MM-DD <Meeting Name>.md
    Returns list of {filename, date, content} dicts sorted by date.
    """
    if not MEETING_NOTES_DIR.exists():
        return []

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    notes = []

    for md_file in MEETING_NOTES_DIR.glob("**/*.md"):
        stem = md_file.stem
        # Expect filename starting with YYYY-MM-DD
        try:
            note_date = date.fromisoformat(stem[:10])
        except ValueError:
            continue
        if monday <= note_date <= today:
            notes.append({
                "filename": md_file.name,
                "date": note_date,
                "content": md_file.read_text(),
            })

    notes.sort(key=lambda x: x["date"])
    return notes


def sync_daily_note(for_date=None, sync_deletions=True):
    """
    Read a daily note and sync the Active Projects section back to project files:
      - [x] tasks  → marked done in project file
      - [ ] tasks  → if sync_deletions=True, any open task in the project file NOT
                     present in the daily note is deleted (user removed it)
      - plain text → ignored
    Defaults to today. Pass a date object to sync a specific day.
    sync_deletions should be False for re-run syncs of today's note (which may not
    yet show the full task list).
    Returns (completed, added, skipped, deleted).
    """
    for_date = for_date or date.today()
    note_file = _find_daily_note(for_date)
    if not note_file.exists():
        return [], [], [], []

    _before_statuses = load_status_snapshot()
    lines = note_file.read_text().splitlines()
    completed = []
    added = []
    skipped = []
    deleted = []
    current_section = None
    current_project = None

    # Track every task text (open or done) seen per project in the daily note.
    # Used afterward to delete project-file tasks the user removed from the note.
    seen_per_project = {}   # project_name -> set of clean task texts

    # Track To Investigate items from daily note
    investigate_done = set()    # checked off → remove from Ideas file
    investigate_open = set()    # still open → keep in Ideas file
    investigate_added = []      # new items user typed in

    for line in lines:
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            if "active projects" in heading or "due today & overdue" in heading:
                current_section = "projects"
            elif heading == "to investigate":
                current_section = "investigate"
            else:
                current_section = "other"
            current_project = None
            continue

        if line.startswith("### "):
            # Strip status suffix e.g. "Cars BOOP — In Progress" → "Cars BOOP"
            current_project = re.split(r"\s+[—–-]\s+", line[4:].strip())[0].strip()
            seen_per_project.setdefault(current_project, set())
            continue

        if current_section == "investigate":
            # Checked investigate item → mark for removal from Ideas file
            m_done = re.match(r"^(\s*)-\s+\[[xX]\]\s+(.+)$", line)
            if m_done:
                investigate_done.add(m_done.group(2).strip())
            continue

        if current_section != "projects" or not current_project:
            continue

        # Checked task → mark done in project file
        m_done = re.match(r"^(\s*)-\s+\[[xX]\]\s+(.+)$", line)
        if m_done:
            task_text = m_done.group(2).strip()
            # Strip Tasks plugin completion marker e.g. ✅ 2026-02-24
            task_text = re.sub(r"\s*✅\s*\d{4}-\d{2}-\d{2}\s*$", "", task_text).strip()
            clean = _DUE_DATE.sub("", task_text).strip()
            seen_per_project[current_project].add(clean)
            project_dir = PROJECTS_DIR / current_project
            if not project_dir.exists():
                skipped.append({"project": current_project, "task": task_text})
                continue
            marked = False
            for md_file in project_dir.glob("*.md"):
                if mark_task_done(str(md_file), task_text):
                    completed.append({"project": current_project, "task": task_text})
                    log_weekly_change("task_completed", current_project, task=task_text)
                    marked = True
                    break
            if not marked:
                skipped.append({"project": current_project, "task": task_text})
            continue

        # Open task → record as "seen" (user kept it)
        m_open = re.match(r"^(\s*)-\s+\[ \]\s+(.+)$", line)
        if m_open:
            task_text = m_open.group(2).strip()
            if current_section == "investigate":
                investigate_open.add(task_text)
                continue
            clean = _DUE_DATE.sub("", task_text).strip()
            seen_per_project[current_project].add(clean)

    # ── Deletion sync ──────────────────────────────────────────────────────
    # For each project that appeared in the daily note, remove any open task
    # from the project file that the user deleted (not in the note at all).
    # Only runs when sync_deletions=True (i.e. for yesterday's finished note).
    if not sync_deletions:
        return completed, added, skipped, deleted

    for project_name, seen_tasks in seen_per_project.items():
        project_dir = PROJECTS_DIR / project_name
        if not project_dir.exists():
            continue
        for md_file in project_dir.glob("*.md"):
            content = md_file.read_text()
            new_lines = []
            changed = False
            for proj_line in content.splitlines():
                m = _CHECKBOX.match(proj_line)
                if m:
                    indent_str, status, text = m.groups()
                    if status == " ":   # open task
                        clean = _DUE_DATE.sub("", text).strip()
                        if clean not in seen_tasks:
                            # User deleted this from the daily note → remove from project file
                            changed = True
                            deleted.append({"project": project_name, "task": clean})
                            log_weekly_change("task_deleted", project_name, task=clean)
                            continue    # drop this line
                new_lines.append(proj_line)
            if changed:
                md_file.write_text("\n".join(new_lines) + "\n")

    # ── To Investigate sync ─────────────────────────────────────────────
    # Sync daily note's To Investigate section back to Ideas to Investigate.md.
    # Checked items → remove their ## section. Removed items → remove section.
    # New items → append a new ## section.
    if IDEAS_FILE.exists() and (investigate_done or investigate_open):
        ideas_content = IDEAS_FILE.read_text()
        source_ideas = set(re.findall(r"^## (.+)$", ideas_content, re.MULTILINE))
        all_note_ideas = investigate_done | investigate_open
        ideas_changed = False

        # Remove checked-off or deleted ideas (sections present in source but absent
        # from the note's open list AND not in done list = user deleted; in done = checked)
        to_remove = investigate_done | (source_ideas - all_note_ideas)
        for idea_name in to_remove:
            # Remove the ## section and everything until the next ## or end
            pattern = re.compile(
                r"\n?^## " + re.escape(idea_name) + r"\n(?:(?!^## ).)*",
                re.MULTILINE | re.DOTALL,
            )
            new_content = pattern.sub("", ideas_content)
            if new_content != ideas_content:
                ideas_content = new_content
                ideas_changed = True
                action = "investigate_done" if idea_name in investigate_done else "investigate_removed"
                deleted.append({"project": "To Investigate", "task": idea_name})
                log_weekly_change(action, "To Investigate", task=idea_name)

        # Add new ideas the user typed into the daily note
        new_ideas = all_note_ideas - source_ideas - investigate_done
        for idea_name in sorted(new_ideas):
            ideas_content = ideas_content.rstrip() + f"\n\n## {idea_name}\n- [ ] Define scope\n"
            ideas_changed = True
            added.append({"project": "To Investigate", "task": idea_name})
            log_weekly_change("investigate_added", "To Investigate", task=idea_name)

        if ideas_changed:
            IDEAS_FILE.write_text(ideas_content)

    # Detect manual status changes (e.g. Obsidian frontmatter edits between syncs)
    _after_statuses = {name: info.get("status", "") for name, info in get_all_projects_with_status().items()}
    for proj, after_status in _after_statuses.items():
        before = _before_statuses.get(proj, "")
        if before and after_status and before != after_status:
            log_weekly_change("project_status_changed", proj, from_val=before, to_val=after_status)
    save_status_snapshot()

    return completed, added, skipped, deleted


def inject_funnel_into_daily_note(funnel_rows, for_date=None):
    """Write/replace a ## Car Rental Funnel section in today's daily note.

    funnel_rows: list of dicts with keys:
      date (str), searches (int), results (int), clicks (int),
      checkouts (int), bookings (int), conversion (float 0-1)

    Picks the most recent complete day. If a ## Car Rental Funnel section
    already exists it is replaced; otherwise it is appended before the first
    ## Industry News or at the end.
    """
    target_date = for_date or date.today()
    note_file = _find_daily_note(target_date)
    if not note_file.exists():
        return False

    if not funnel_rows:
        return False

    # Build the markdown table
    r = funnel_rows[-1]  # most recent complete day
    searches = r["searches"]
    def pct(n, d): return f"{n/d*100:.1f}%" if d else "—"

    table_lines = [
        f"## Car Rental Funnel — {r['date']}",
        "",
        "| Step | Users | Step Rate | Overall |",
        "|------|------:|----------:|--------:|",
        f"| Search Cars | {searches:,} | — | 100% |",
        f"| View Results | {r['results']:,} | {pct(r['results'], searches)} | {pct(r['results'], searches)} |",
        f"| Click Car Option | {r['clicks']:,} | {pct(r['clicks'], r['results'])} | {pct(r['clicks'], searches)} |",
        f"| View Checkout | {r['checkouts']:,} | {pct(r['checkouts'], r['clicks'])} | {pct(r['checkouts'], searches)} |",
        f"| **Complete Booking** | **{r['bookings']:,}** | **{pct(r['bookings'], r['checkouts'])}** | **{pct(r['bookings'], searches)}** |",
        "",
    ]

    # 7-day avg if multiple rows provided
    if len(funnel_rows) > 1:
        avg_conv = sum(x["conversion"] for x in funnel_rows) / len(funnel_rows)
        table_lines.append(f"*7-day avg conversion: {avg_conv*100:.1f}%*")
        table_lines.append("")

    section_text = "\n".join(table_lines)

    content = note_file.read_text()

    # Replace existing section if present
    existing = re.search(r'(^## Car Rental Funnel.*?)(?=\n## |\Z)', content, re.MULTILINE | re.DOTALL)
    if existing:
        new_content = content[:existing.start()] + section_text + content[existing.end():]
    else:
        # Insert before Industry News if it exists, otherwise append
        insert_match = re.search(r'^## Industry News', content, re.MULTILINE)
        if insert_match:
            new_content = content[:insert_match.start()] + "---\n\n" + section_text + "\n---\n\n" + content[insert_match.start():]
        else:
            new_content = content.rstrip() + "\n\n---\n\n" + section_text

    note_file.write_text(new_content)
    return True


def write_analysis_report(content: str, report_date=None) -> str:
    """Save a cars analysis report to Projects/Cars SRP UXR/Analysis Reports/.

    Creates the directory if needed and appends a link to the main SRP UXR
    project file under '## Analysis Reports'.

    Returns the path to the saved report file.
    """
    from datetime import date as _date
    if report_date is None:
        report_date = _date.today()
    date_str = report_date.isoformat()

    reports_dir = VAULT_PATH / "Projects" / "Cars SRP UXR" / "Analysis Reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_file = reports_dir / f"{date_str}-cars-analysis.md"
    report_file.write_text(content)

    # Update the SRP UXR project file — add/update ## Analysis Reports section
    project_file = VAULT_PATH / "Projects" / "Cars SRP UXR" / "Cars SRP UXR.md"
    if project_file.exists():
        proj_content = project_file.read_text()
        link_line = f"- [[Analysis Reports/{date_str}-cars-analysis|{date_str} Analysis]]"
        if "## Analysis Reports" not in proj_content:
            insert_match = re.search(r'^## Tasks', proj_content, re.MULTILINE)
            if insert_match:
                section = f"## Analysis Reports\n\n{link_line}\n\n---\n\n"
                proj_content = proj_content[:insert_match.start()] + section + proj_content[insert_match.start():]
            else:
                proj_content = proj_content.rstrip() + f"\n\n## Analysis Reports\n\n{link_line}\n"
        elif link_line not in proj_content:
            proj_content = proj_content.replace(
                "## Analysis Reports\n",
                f"## Analysis Reports\n\n{link_line}\n",
                1,
            )
        project_file.write_text(proj_content)

    return str(report_file)


def append_to_weekly_note(section_title, content):
    """Append a dated section to this week's note in Weekly Notes/."""
    WEEKLY_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    note_file = WEEKLY_NOTES_DIR / monday.strftime("Week of %m%d%Y.md")

    timestamp = datetime.now().strftime("%-m/%-d/%Y — %-I:%M %p")
    entry = f"\n## {timestamp} — {section_title}\n\n{content}\n"

    if note_file.exists():
        note_file.write_text(note_file.read_text() + entry)
    else:
        header = f"# Week of {monday.strftime('%-m/%-d/%Y')}\n"
        note_file.write_text(header + entry)
