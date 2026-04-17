"""
task add / task done / task prioritize commands.
"""
from datetime import date, timedelta
from pm import vault

BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
DIM = "\033[2m"
RESET = "\033[0m"


def add_task(text, project=None, due=None):
    projects = vault.get_project_names()

    if due:
        text = f"{text} @due({due})"

    if project:
        # Fuzzy match project name
        match = next((p for p in projects if project.lower() in p.lower()), None)
        if not match:
            print(f"Project not found: '{project}'")
            print("Available projects:")
            for p in projects:
                print(f"  {DIM}• {p}{RESET}")
            return
        vault.append_task_to_project(match, text)
        print(f"{GREEN}✓{RESET} Added to {BOLD}{match}{RESET}: {text}")
    else:
        # Show project list and let user pick
        print(f"\n{BOLD}Which project?{RESET}")
        for i, p in enumerate(projects, 1):
            print(f"  {i}. {p}")
        print(f"  0. This week's note (no project)")
        try:
            choice = input("\nNumber: ").strip()
        except (KeyboardInterrupt, EOFError):
            return

        if choice == "0":
            vault.append_to_weekly_note("Tasks", f"- [ ] {text}")
            print(f"{GREEN}✓{RESET} Added to this week's note")
        else:
            try:
                idx = int(choice) - 1
                selected = projects[idx]
                vault.append_task_to_project(selected, text)
                print(f"{GREEN}✓{RESET} Added to {BOLD}{selected}{RESET}: {text}")
            except (ValueError, IndexError):
                print("Invalid selection.")


def mark_done_interactive(project=None):
    if project:
        projects = [p for p in vault.get_project_names() if project.lower() in p.lower()]
        if not projects:
            print(f"No project matching '{project}'")
            return
        project_name = projects[0]
    else:
        all_projects = vault.get_project_names()
        print(f"\n{BOLD}Which project?{RESET}")
        for i, p in enumerate(all_projects, 1):
            print(f"  {i}. {p}")
        try:
            choice = input("\nNumber: ").strip()
            project_name = all_projects[int(choice) - 1]
        except (ValueError, IndexError, KeyboardInterrupt, EOFError):
            print("Cancelled.")
            return

    project_tasks = vault.get_project_tasks()
    tasks = project_tasks.get(project_name, [])

    if not tasks:
        print(f"No open tasks in {project_name}.")
        return

    print(f"\n{BOLD}Open tasks in {project_name}:{RESET}")
    for i, t in enumerate(tasks, 1):
        print(f"  {i}. {t['text']}")

    try:
        choice = input("\nMark done (number or comma-separated list): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("Cancelled.")
        return

    indices = []
    for part in choice.split(","):
        try:
            indices.append(int(part.strip()) - 1)
        except ValueError:
            pass

    for idx in indices:
        if 0 <= idx < len(tasks):
            t = tasks[idx]
            if vault.mark_task_done(t["file"], t["text"]):
                print(f"{GREEN}✓{RESET} Done: {t['text']}")
            else:
                print(f"Could not mark done: {t['text']}")


CYAN = "\033[96m"
RED = "\033[91m"
WHITE = "\033[97m"


def _parse_due(raw):
    """Parse shorthand date input. Returns ISO date string or None."""
    raw = raw.strip().lower()
    today = date.today()
    shortcuts = {
        "t": today,
        "today": today,
        "tom": today + timedelta(days=1),
        "tomorrow": today + timedelta(days=1),
        "m": "monday", "mon": "monday", "monday": "monday",
        "tu": "tuesday", "tue": "tuesday", "tuesday": "tuesday",
        "w": "wednesday", "wed": "wednesday", "wednesday": "wednesday",
        "th": "thursday", "thu": "thursday", "thursday": "thursday",
        "f": "friday", "fri": "friday", "friday": "friday",
    }
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    val = shortcuts.get(raw, raw)
    if isinstance(val, date):
        return val.isoformat()
    if val in weekdays:
        target = weekdays.index(val)
        days_ahead = (target - today.weekday()) % 7 or 7
        return (today + timedelta(days=days_ahead)).isoformat()
    try:
        date.fromisoformat(raw)
        return raw
    except ValueError:
        return None


def prioritize_tasks():
    """Walk through all tasks without due dates and assign them interactively."""
    project_tasks = vault.get_project_tasks()

    # Flatten tasks without due dates, preserving project
    undated = []
    for project, data in project_tasks.items():
        for t in data["tasks"]:
            if not t.get("due"):
                undated.append({**t, "project": project})

    if not undated:
        print(f"{GREEN}✓ All tasks already have due dates.{RESET}")
        return

    total = len(undated)
    print(f"\n{BOLD}{WHITE}PRIORITIZE TASKS — {total} without due dates{RESET}")
    print(f"{DIM}Shortcuts: t=today  tom=tomorrow  m/tu/w/th/f=weekday  YYYY-MM-DD{RESET}")
    print(f"{DIM}           s=skip  q=quit{RESET}\n")

    set_count = 0
    for i, t in enumerate(undated, 1):
        display = vault._STRIP_DUE_RE.sub("", t["text"]) if hasattr(vault, "_STRIP_DUE_RE") else t["text"]
        print(f"{DIM}[{i}/{total}]{RESET}  {BOLD}{display}{RESET}  {DIM}({t['project']}){RESET}")
        try:
            raw = input("  Due: ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{DIM}Stopped. {set_count} date(s) set.{RESET}")
            return

        if raw.lower() == "q":
            print(f"{DIM}Quit. {set_count} date(s) set.{RESET}")
            return
        if raw.lower() == "s" or raw == "":
            print(f"  {DIM}skipped{RESET}")
            continue

        due = _parse_due(raw)
        if not due:
            print(f"  {RED}Unrecognized date '{raw}' — skipped{RESET}")
            continue

        updated = vault.set_task_due(display, due, project_name=t["project"])
        if updated:
            day_name = date.fromisoformat(due).strftime("%a %-m/%-d")
            print(f"  {GREEN}✓ {day_name}{RESET}")
            set_count += 1
        else:
            print(f"  {RED}Could not match task in file — skipped{RESET}")

    print(f"\n{GREEN}Done. {set_count}/{total} tasks now have due dates.{RESET}\n")
