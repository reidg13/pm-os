#!/usr/bin/env python3
"""
PM Automation — CLI entry point.

Commands:
  briefing       Generate daily briefing (metrics, tasks, news — called by /today skill)
  note           Paste meeting notes → Claude extracts tasks + feedback
  weekly         Generate weekly status update
  research       Research and RICE-score feature ideas
  task add       Add a task to a project
  task done      Mark a task as done
  asana-setup    Detect and save Asana workspace/user GIDs
  roadmap        Show Asana project roadmap
"""
import sys
import argparse
import json
from pathlib import Path


def cmd_status(args):
    from pm import vault
    BOLD = "\033[1m"; GREEN = "\033[92m"; DIM = "\033[2m"; RESET = "\033[0m"; RED = "\033[91m"

    # Write mode: pm.py status "Project Name" "update text"
    if getattr(args, "project", None) and getattr(args, "text", None):
        ok = vault.set_project_status_update(args.project, args.text)
        if ok:
            print(f"{GREEN}✓{RESET} Status updated for {BOLD}{args.project}{RESET}")
            vault.log_weekly_change("status_update", args.project, task=args.text)
        else:
            print(f"{RED}✗{RESET} Project not found: {args.project}")
        return

    # Read mode: pm.py status → show all current status updates
    updates = vault.get_all_status_updates()
    all_projects = vault.get_all_projects_with_status()
    from datetime import date, timedelta
    stale_cutoff = (date.today() - timedelta(days=5)).isoformat()
    print(f"\n{BOLD}PROJECT STATUS UPDATES{RESET}\n")
    for name, info in sorted(all_projects.items()):
        if info.get("status", "").lower() in ("done", "") or name in ("Misc", "TAM Analysis"):
            continue
        upd = updates.get(name)
        if upd:
            d, text = upd
            stale = f"  {RED}[stale]{RESET}" if d < stale_cutoff else ""
            print(f"  {BOLD}{name}{RESET}  {DIM}{d}{RESET}{stale}")
            print(f"    {text[:120]}")
        else:
            print(f"  {BOLD}{name}{RESET}  {RED}[no status update]{RESET}")
    print()


def cmd_today(args):
    from pm.today import run_today
    run_today()


def cmd_note(args):
    from pm.notes import run_note
    run_note(file_path=getattr(args, "file", None))


def cmd_weekly(args):
    from pm.weekly import run_weekly
    run_weekly()




def cmd_research(args):
    from pm.research import run_research
    manual_ideas = None
    if getattr(args, "ideas", None):
        manual_ideas = [i.strip() for i in args.ideas.split(";") if i.strip()]
    run_research(manual_ideas=manual_ideas)


def _parse_due_date(raw):
    """Parse a date string: YYYY-MM-DD, today, tomorrow, or weekday name."""
    from datetime import date, timedelta
    raw = raw.strip().lower()
    today = date.today()
    if raw == "today":
        return today.isoformat()
    if raw == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if raw in weekdays:
        target = weekdays.index(raw)
        days_ahead = (target - today.weekday()) % 7 or 7
        return (today + timedelta(days=days_ahead)).isoformat()
    try:
        date.fromisoformat(raw)
        return raw
    except ValueError:
        return None


def cmd_task(args):
    from pm import tasks
    if args.task_command == "add":
        due = None
        if getattr(args, "due", None):
            due = _parse_due_date(args.due)
            if not due:
                print(f"Unrecognized date '{args.due}'. Use YYYY-MM-DD, today, tomorrow, or a weekday name.")
                return
        tasks.add_task(args.text, project=getattr(args, "project", None), due=due)
    elif args.task_command == "done":
        tasks.mark_done_interactive(project=getattr(args, "project", None))
    elif args.task_command == "due":
        from pm import vault
        due_date = _parse_due_date(args.date)
        if not due_date:
            print(f"Invalid date '{args.date}'. Use YYYY-MM-DD, today, tomorrow, or a weekday name.")
            return
        updated = vault.set_task_due(args.text, due_date, project_name=getattr(args, "project", None))
        if updated:
            for u in updated:
                print(f"  ✓ [{u['project']}] set due {due_date}")
        else:
            print(f"No matching task found for: {args.text!r}")
    elif args.task_command == "prioritize":
        tasks.prioritize_tasks()
    else:
        print("Usage: pm.py task [add|done|due|prioritize]")


def cmd_metrics_setup(args):
    """Force-refresh the Snowflake schema cache used by daily metrics."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from run_query import run_query
    from pm.metrics import _discover_schema, _SCHEMA_CACHE

    print("Connecting to Snowflake to discover metrics schema...")
    try:
        schema = _discover_schema(run_query)
        print(f"  car date col   : {schema.get('car_date_col') or '⚠ not found'}")
        print(f"  car GBV col    : {schema.get('car_gbv_col') or '⚠ not found'}")
        print(f"  hotel date col : {schema.get('hotel_date_col') or '⚠ not found'}")
        print(f"  hotel table    : {schema.get('hotel_table') or '⚠ not found'}")
        print(f"\nSchema cached → {_SCHEMA_CACHE}")
    except Exception as e:
        print(f"Error: {e}")


def cmd_asana_setup(args):
    from pm import asana_client
    import json

    print("Connecting to Asana...")
    me = asana_client.get_me()
    if not me:
        print("Error: Could not connect. Check ASANA_ACCESS_TOKEN in .env")
        return

    print(f"Logged in as: {me.get('name')} ({me.get('email')})")
    user_gid = me.get("gid")

    workspaces = asana_client.get_workspaces()
    if not workspaces:
        print("No workspaces found.")
        return

    if len(workspaces) == 1:
        ws = workspaces[0]
    else:
        print("\nWorkspaces:")
        for i, w in enumerate(workspaces, 1):
            print(f"  {i}. {w['name']}")
        try:
            idx = int(input("Select workspace number: ").strip()) - 1
            ws = workspaces[idx]
        except (ValueError, IndexError, KeyboardInterrupt):
            print("Cancelled.")
            return

    cfg_file = Path(__file__).parent / "data" / "config.json"
    cfg = json.loads(cfg_file.read_text())
    cfg["asana_workspace_gid"] = ws["gid"]
    cfg["asana_user_gid"] = user_gid
    cfg_file.write_text(json.dumps(cfg, indent=2))

    print(f"\n✓ Saved workspace: {ws['name']}")
    print(f"✓ Saved user GID: {user_gid}")
    print("\nRun `python pm.py today` to see your tasks.")


def cmd_prd(args):
    from pm import confluence_client, vault

    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RED = "\033[91m"
    RESET = "\033[0m"

    if not confluence_client._available():
        print(f"{RED}Confluence not configured.{RESET}")
        print("Add CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN to .env")
        print("Get your token at: https://id.atlassian.com/manage-profile/security/api-tokens")
        return

    projects = vault.get_project_names()
    if not projects:
        print("No projects found.")
        return

    # If a specific project was passed, only do that one
    if getattr(args, "project", None):
        projects = [p for p in projects if args.project.lower() in p.lower()]
        if not projects:
            print(f"No project matching '{args.project}'")
            return

    print(f"\n{BOLD}Searching Confluence for PRDs...{RESET}\n")
    linked = 0
    not_found = []

    for project in projects:
        results = confluence_client.search_pages(project, limit=3)

        if results is None:
            print(f"{RED}Error connecting to Confluence.{RESET}")
            return

        if not results:
            not_found.append(project)
            continue

        # Pick the best match — prefer title that closely matches project name
        best = results[0]
        vault.set_project_prd(project, best["title"], best["url"])
        print(f"  {GREEN}✓{RESET} {BOLD}{project}{RESET}")
        print(f"    {DIM}{best['title']}{RESET}")
        print(f"    {DIM}{best['url']}{RESET}")
        linked += 1

    if not_found:
        print(f"\n{YELLOW}No Confluence page found for:{RESET}")
        for p in not_found:
            print(f"  {DIM}• {p}{RESET}")

    print(f"\n{DIM}Linked {linked}/{len(projects)} projects.{RESET}")
    if not_found:
        print(f"{DIM}Run `python pm.py prd --project \"Name\"` to search manually for unmatched ones.{RESET}")
    print()


def cmd_kanban(args):
    from pm import vault

    GREEN = "\033[92m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    print(f"{DIM}Regenerating kanban board and project overview...{RESET}")
    kb = vault.create_kanban_board()
    ov = vault.create_project_overview()
    print(f"  {GREEN}✓{RESET} {kb}")
    print(f"  {GREEN}✓{RESET} {ov}")


def cmd_sync(args):
    from pm import vault

    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    # sync_deletions=False — today's note is partial; never delete based on it
    completed, added, skipped, deleted = vault.sync_daily_note(sync_deletions=False)

    if not completed and not added and not skipped:
        print(f"{DIM}Nothing to sync — no checkboxes changed in today's daily note.{RESET}")
        return

    if completed:
        print(f"\n{BOLD}Completed {len(completed)} task(s):{RESET}")
        for item in completed:
            print(f"  {GREEN}✓{RESET} [{item['project']}] {item['task']}")

    if added:
        print(f"\n{BOLD}Added {len(added)} new task(s) to project files:{RESET}")
        for item in added:
            print(f"  {CYAN}+{RESET} [{item['project']}] {item['task']}")

    if skipped:
        print(f"\n{YELLOW}Could not match {len(skipped)} task(s) — may have been edited or already done:{RESET}")
        for item in skipped:
            print(f"  {DIM}? [{item['project']}] {item['task']}{RESET}")

    print()


def cmd_roadmap(args):
    from pm import asana_client
    from pm.config import ASANA_WORKSPACE_GID, ASANA_BOARDS

    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    RESET = "\033[0m"

    if not ASANA_WORKSPACE_GID:
        print("Asana not configured. Run `python pm.py asana-setup` first.")
        return

    boards = ASANA_BOARDS
    if not boards:
        print("No boards configured in data/config.json")
        return

    for board in boards:
        print(f"\n{BOLD}{CYAN}{'━' * 60}{RESET}")
        print(f"{BOLD}{CYAN}  {board['name']}{RESET}")
        print(f"{BOLD}{CYAN}{'━' * 60}{RESET}\n")

        tasks = asana_client.get_project_tasks(board["gid"])
        if not tasks:
            print(f"  {DIM}No open tasks.{RESET}")
            continue

        from datetime import date
        today = date.today().isoformat()

        for t in tasks:
            name = t.get("name", "").strip()
            if not name:
                continue
            due = t.get("due_on") or ""
            assignee = (t.get("assignee") or {}).get("name", "")

            due_label = ""
            if due:
                if due < today:
                    due_label = f"  {RED}due {due}{RESET}"
                else:
                    due_label = f"  {DIM}due {due}{RESET}"

            assignee_label = f"  {DIM}[{assignee}]{RESET}" if assignee else ""
            print(f"  {YELLOW}•{RESET} {name}{due_label}{assignee_label}")

    print()


def main():
    parser = argparse.ArgumentParser(
        prog="pm",
        description="PM Automation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    status_p = sub.add_parser("status", help="View or write project status updates")
    status_p.add_argument("project", nargs="?", help="Project name")
    status_p.add_argument("text", nargs="?", help="Status update text")

    sub.add_parser("briefing", help="Generate daily briefing (metrics, tasks, news — called by /today skill)")
    sub.add_parser("kanban", help="Regenerate Cars Project Board and Project Overview")
    sub.add_parser("sync", help="Sync checked tasks from today's daily note back to project files")
    sub.add_parser("weekly", help="Generate weekly status update")
    sub.add_parser("asana-setup", help="Connect Asana account")
    sub.add_parser("metrics-setup", help="Discover and cache Snowflake schema for daily metrics")

    prd_p = sub.add_parser("prd", help="Link Confluence PRDs to projects")
    prd_p.add_argument("--project", help="Search for a specific project only (partial match)")
    sub.add_parser("roadmap", help="View Asana project roadmap")

    note_p = sub.add_parser("note", help="Process meeting notes")
    note_p.add_argument("--file", help="Path to notes file (default: paste interactively)")

    research_p = sub.add_parser("research", help="Research and RICE-score feature ideas")
    research_p.add_argument(
        "--ideas",
        help="Semicolon-separated list of ideas to include (e.g. 'Price alerts; Bundle deals')",
    )

    task_p = sub.add_parser("task", help="Manage tasks")
    task_sub = task_p.add_subparsers(dest="task_command")

    add_p = task_sub.add_parser("add", help="Add a task")
    add_p.add_argument("text", help="Task text")
    add_p.add_argument("--project", help="Project name (partial match ok)")
    add_p.add_argument("--due", help="Due date: YYYY-MM-DD, today, tomorrow, or weekday name")

    done_p = task_sub.add_parser("done", help="Mark task(s) as done")
    done_p.add_argument("--project", help="Project name (partial match ok)")

    due_p = task_sub.add_parser("due", help="Set a due date on a task")
    due_p.add_argument("text", help="Task text (partial match ok)")
    due_p.add_argument("date", help="Due date: YYYY-MM-DD, today, tomorrow, or weekday name")
    due_p.add_argument("--project", help="Project name to narrow search")

    task_sub.add_parser("prioritize", help="Interactively assign due dates to all undated tasks")

    args = parser.parse_args()

    dispatch = {
        "status": cmd_status,
        "briefing": cmd_today,
        "kanban": cmd_kanban,
        "sync": cmd_sync,
        "note": cmd_note,
        "weekly": cmd_weekly,
        "research": cmd_research,
        "task": cmd_task,
        "asana-setup": cmd_asana_setup,
        "metrics-setup": cmd_metrics_setup,
        "roadmap": cmd_roadmap,
        "prd": cmd_prd,
    }

    fn = dispatch.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
