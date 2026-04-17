"""
/today command — overdue, active projects, Asana tasks, ideas to investigate.
"""
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

# Make run_query importable from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

_STRIP_DUE = re.compile(r"\s*(?:@due\(\d{4}-\d{2}-\d{2}\)|📅\s*\d{4}-\d{2}-\d{2})")

import requests

from pm import vault

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
GREEN = "\033[92m"
WHITE = "\033[97m"


def _hr():
    print(f"{DIM}{'─' * 60}{RESET}")


def _header(text):
    print(f"\n{BOLD}{WHITE}{text}{RESET}")
    _hr()


_NEWS_QUERIES = [
    "rental car corporate travel",
    "your product area industry news",
    "corporate travel B2B technology",
]


def _get_news_digest(max_items=6, lookback_hours=48):
    """Fetch recent headlines from Google News RSS — no API key required."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    seen = set()
    items = []

    for query in _NEWS_QUERIES:
        url = (
            f"https://news.google.com/rss/search"
            f"?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if not r.ok:
                continue
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                source = (item.findtext("source") or "").strip()
                pub_date = item.findtext("pubDate") or ""

                # Google News appends " - Source" to titles — strip it
                if source and title.endswith(f" - {source}"):
                    title = title[: -(len(source) + 3)].strip()

                key = re.sub(r"\W+", "", title.lower())
                if not title or key in seen:
                    continue

                try:
                    dt = parsedate_to_datetime(pub_date)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < cutoff:
                        continue
                    age_h = int((datetime.now(timezone.utc) - dt).total_seconds() / 3600)
                    age_label = f"{age_h}h ago" if age_h < 24 else f"{age_h // 24}d ago"
                except Exception:
                    age_label = ""

                seen.add(key)
                items.append({"title": title, "source": source, "age": age_label})

                if len(items) >= max_items:
                    return items
        except Exception:
            continue

    return items


# Actions Claude can help with → label shown to the user
_ACTION_PATTERNS = [
    (r"\b(draft|write|rewrite|compose)\b", "Draft / write"),
    (r"\b(update|revise|edit)\b.*(doc|deck|brief|prd|page|note|email|message|update|summary)", "Update a doc"),
    (r"\b(sql|query|pull data|run.*query|query.*data|snowflake)\b", "Write SQL / pull data"),
    (r"\b(analyze|analysis|break ?down|model|forecast|size)\b", "Analyze / model"),
    (r"\b(prd|spec|brief|requirements|user stor)\b", "Structure a PRD / brief"),
    (r"\b(framework|template|structure|outline)\b", "Create a framework"),
    (r"\b(research|investigate|look into|explore)\b", "Research"),
    (r"\b(deck|slide|presentation)\b", "Build a deck outline"),
    (r"\b(email|message|follow.?up|send)\b", "Draft a message"),
    (r"\b(summary|summarize|recap)\b", "Write a summary"),
]


def _classify_task(text):
    """Return a label if Claude can act on this task, else None."""
    lower = text.lower()
    for pattern, label in _ACTION_PATTERNS:
        if re.search(pattern, lower):
            return label
    return None


def _get_actionable_tasks(project_tasks, asana_sections, ideas):
    """Return list of (project, task_text, label) that Claude can act on.

    Only surfaces Obsidian project tasks (most specific/actionable).
    Capped at 8 results to keep the section scannable.
    """
    results = []

    for project, data in (project_tasks or {}).items():
        for t in data["tasks"]:
            display = _STRIP_DUE.sub("", t["text"])
            label = _classify_task(display)
            if label:
                results.append((project, display, label))

    return results[:8]


def _review_meeting_tasks(for_date, project_names):
    """Parse action items from yesterday's meeting notes and prompt to add them to projects."""
    meetings = vault.get_meeting_action_items(for_date)
    if not meetings:
        return

    # Filter out meetings where all tasks are already in project files
    meetings = [
        {**m, "tasks": [t for t in m["tasks"] if not vault.task_exists_in_projects(t)]}
        for m in meetings
    ]
    meetings = [m for m in meetings if m["tasks"]]
    if not meetings:
        return

    print(f"\n{BOLD}{CYAN}MEETING ACTION ITEMS — {for_date.strftime('%-m/%-d')}{RESET}")
    _hr()
    print(f"{DIM}Press Enter to add, 's' to skip, or type a project name to reassign.{RESET}\n")

    for m in meetings:
        print(f"  {BOLD}{m['meeting']}{RESET}")
        for task in m["tasks"]:
            # Skip if already exists in any project file
            already = vault.task_exists_in_projects(task)
            if already:
                continue

            # Guess project from name match
            suggested = next(
                (p for p in project_names if any(w.lower() in p.lower() for w in task.split() if len(w) > 4)),
                "Misc",
            )
            print(f"  {CYAN}•{RESET} {task}")
            print(f"    Project: {BOLD}{suggested}{RESET}")
            try:
                choice = input("    [Enter=add | s=skip | type project name]: ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                return
            if choice.lower() == "s":
                continue
            project = choice if choice else suggested
            vault.append_task_to_project(project, task)
            print(f"    {GREEN}✓ Added to {project}{RESET}")
        print()


def _git_snapshot(vault_path, label):
    """Commit any changes in the vault with a timestamped message. Silent if nothing changed."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=vault_path, capture_output=True, text=True
        )
        if not result.stdout.strip():
            return  # nothing to commit
        subprocess.run(["git", "add", "-A"], cwd=vault_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", label],
            cwd=vault_path, check=True, capture_output=True
        )
        print(f"{DIM}Vault snapshot: {label}{RESET}")
    except Exception as e:
        print(f"{DIM}Git snapshot skipped: {e}{RESET}")


def run_today():
    today = date.today()
    day_str = today.strftime("%A, %b %-d %Y")

    # ── Snapshot vault before any changes ─────────────────────────
    _git_snapshot(vault.VAULT_PATH, f"snapshot before {today.isoformat()} briefing")

    # ── Sync kanban board → project YAML ──────────────────────────
    kanban_changes = vault.sync_kanban_to_projects()
    for c in kanban_changes:
        print(f"{DIM}Kanban: {c['project']} moved {c['old']} → {c['new']}{RESET}")

    # ── Auto-sync previous weekday's note ─────────────────────────
    # Mon → Fri (3 days), Sun → Fri (2 days), all other days → previous day
    if today.weekday() == 0:
        days_back = 3
    elif today.weekday() == 6:
        days_back = 2
    else:
        days_back = 1
    yesterday = today - timedelta(days=days_back)
    completed, added, skipped, deleted = vault.sync_daily_note(for_date=yesterday, sync_deletions=True)
    if completed or added or deleted:
        print(f"\n{DIM}Synced yesterday ({yesterday.strftime('%-m/%-d')}):{RESET}", end=" ")
        parts = []
        if completed:
            parts.append(f"{GREEN}{len(completed)} completed{RESET}")
        if added:
            parts.append(f"{CYAN}{len(added)} new tasks{RESET}")
        if deleted:
            parts.append(f"{DIM}{len(deleted)} removed{RESET}")
        print(", ".join(parts))

    # ── Also sync today's note if it already exists (re-run case) ──
    # No deletion sync here — today's note may not show all tasks yet
    completed_t, added_t, _, deleted_t = vault.sync_daily_note(for_date=today, sync_deletions=False)
    if completed_t or added_t or deleted_t:
        print(f"{DIM}Synced today ({today.strftime('%-m/%-d')}):{RESET}", end=" ")
        parts = []
        if completed_t:
            parts.append(f"{GREEN}{len(completed_t)} completed{RESET}")
        if added_t:
            parts.append(f"{CYAN}{len(added_t)} new tasks{RESET}")
        if deleted_t:
            parts.append(f"{DIM}{len(deleted_t)} removed{RESET}")
        print(", ".join(parts))

    # ── Review action items from yesterday's meeting notes ─────────
    project_names = vault.get_project_names()
    _review_meeting_tasks(yesterday, project_names)

    print(f"\n{BOLD}{CYAN}{'━' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  TODAY — {day_str}{RESET}")
    print(f"{BOLD}{CYAN}{'━' * 60}{RESET}")

    # ── Overdue from Obsidian projects ─────────────────────────────
    overdue_by_proj = vault.get_overdue_tasks()
    if overdue_by_proj:
        flat_overdue = [
            (proj, t) for proj, tasks in overdue_by_proj.items() for t in tasks
        ]
        _header(f"{RED}OVERDUE — from previous weeks{RESET}")
        for proj, t in flat_overdue[:15]:
            clean = _STRIP_DUE.sub("", t["text"])
            due_label = f"  {RED}[{t['due']}]{RESET}" if t.get("due") else ""
            print(f"  {RED}•{RESET} {clean}{due_label}  {DIM}({proj}){RESET}")
        if len(flat_overdue) > 15:
            print(f"  {DIM}... and {len(flat_overdue) - 15} more{RESET}")

    # ── Stale status updates ────────────────────────────────────────
    stale_cutoff = (today - timedelta(days=5)).isoformat()
    status_updates = vault.get_all_status_updates()
    all_projects = vault.get_all_projects_with_status()
    stale = [
        name for name, info in all_projects.items()
        if info.get("status", "").lower() not in ("done", "complete", "completed", "")
        and name not in ("Misc", "TAM Analysis", "Cars Marketing Materials")
        and (name not in status_updates or status_updates[name][0] < stale_cutoff)
    ]
    if stale:
        _header(f"{RED}STATUS UPDATES NEEDED{RESET}")
        for name in sorted(stale):
            last = status_updates.get(name)
            last_label = f"last updated {last[0]}" if last else "never updated"
            print(f"  {RED}•{RESET} {name}  {DIM}({last_label}){RESET}")
        print(f"  {DIM}→ pm.py status \"Project Name\" \"what's happening\"{RESET}")

    # ── Active project tasks from Obsidian ─────────────────────────
    project_tasks = vault.get_project_tasks()
    today_iso = today.isoformat()
    soon_iso = (today + timedelta(days=7)).isoformat()

    # Flatten all tasks across projects, sorted by due date
    all_tasks = []
    for project, data in (project_tasks or {}).items():
        for t in data["tasks"]:
            all_tasks.append({**t, "project": project, "project_due": data.get("due", "")})

    def _due_sort_key(t):
        d = t.get("due")
        if not d:
            return (3, "")
        if d < today_iso:
            return (0, d)
        if d == today_iso:
            return (1, d)
        return (2, d)

    all_tasks.sort(key=_due_sort_key)

    # Projects with active status but no open tasks — show so they don't vanish
    _ACTIVE_STATUSES = {"in progress", "in discovery", "in review"}
    empty_active = [
        (p, d) for p, d in (project_tasks or {}).items()
        if not d["tasks"] and d.get("status", "").lower() in _ACTIVE_STATUSES
    ]

    if all_tasks or empty_active:
        _header(f"{YELLOW}ACTIVE TASKS{RESET}")
        for t in all_tasks:
            display = _STRIP_DUE.sub("", t["text"])
            due = t.get("due")
            proj_due = t.get("project_due", "")
            if proj_due:
                try:
                    proj_due_label = f" · {date.fromisoformat(proj_due).strftime('%-m/%-d')}"
                except ValueError:
                    proj_due_label = f" · {proj_due}"
            else:
                proj_due_label = ""
            project_dim = f"  {DIM}({t['project']}{proj_due_label}){RESET}"
            if due:
                if due < today_iso:
                    days_late = (today - date.fromisoformat(due)).days
                    due_label = f"  {RED}[{days_late}d overdue]{RESET}"
                    bullet = f"{RED}•{RESET}"
                elif due == today_iso:
                    due_label = f"  {YELLOW}[today]{RESET}"
                    bullet = f"{YELLOW}•{RESET}"
                elif due <= soon_iso:
                    due_label = f"  {GREEN}[due {date.fromisoformat(due).strftime('%-m/%-d')}]{RESET}"
                    bullet = f"{GREEN}•{RESET}"
                else:
                    due_label = f"  {DIM}[due {date.fromisoformat(due).strftime('%-m/%-d')}]{RESET}"
                    bullet = f"{YELLOW}•{RESET}"
            else:
                due_label = ""
                bullet = f"{YELLOW}•{RESET}"
            print(f"  {bullet} {display}{due_label}{project_dim}")

        if empty_active:
            if all_tasks:
                print()
            for proj, data in empty_active:
                status = data.get("status", "")
                print(f"  {DIM}• (no open tasks)  ({proj} — {status}){RESET}")

    asana_sections = []

    # ── Ideas to investigate ───────────────────────────────────────
    ideas = vault.get_ideas()
    if ideas:
        _header(f"{CYAN}TO INVESTIGATE — when you have time{RESET}")
        for idea in ideas:
            print(f"  {CYAN}•{RESET} {idea}")

    # ── Industry news ──────────────────────────────────────────────
    news = _get_news_digest(lookback_hours=168)  # 7 days
    if news:
        _header(f"{CYAN}INDUSTRY NEWS{RESET}")
        for n in news:
            source_label = f"  {DIM}[{n['source']} · {n['age']}]{RESET}" if n["source"] else f"  {DIM}[{n['age']}]{RESET}"
            print(f"  {CYAN}•{RESET} {n['title']}{source_label}")

    # ── Tasks Claude can act on ────────────────────────────────────
    actionable = _get_actionable_tasks(project_tasks, asana_sections, ideas)
    if actionable:
        _header(f"{CYAN}CLAUDE CAN HELP WITH{RESET}")
        for project, task, label in actionable:
            print(f"  {CYAN}•{RESET} {DIM}[{label}]{RESET}  {task}  {DIM}({project}){RESET}")

    # ── Write daily note to Obsidian ───────────────────────────────
    note_file = vault.write_daily_note(project_tasks, asana_sections, ideas, news=news, actionable=actionable)
    print(f"\n  {DIM}Daily note saved → {note_file}{RESET}")

    # ── Create today's meeting notes template ──────────────────────
    meeting_note, created = vault.create_daily_meeting_notes(today)
    if created:
        print(f"  {DIM}Meeting notes created → {meeting_note}{RESET}")

    print()
