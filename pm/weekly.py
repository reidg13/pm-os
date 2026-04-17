"""
/weekly command — generate a weekly status update using Claude.

Saves to: Areas/Weekly Updates/YYYY-MM-DD.md (tomorrow's date)
"""
import glob
import subprocess
from datetime import date, timedelta

from pm import vault
from pm.config import ASANA_WORKSPACE_GID

BOLD  = "\033[1m"
CYAN  = "\033[96m"
GREEN = "\033[92m"
DIM   = "\033[2m"
RESET = "\033[0m"

EXEC_FORMAT = """
# Cars | [Date]

[One punchy sentence on the week's theme.]

🚀 *SHIPPED*
• [Project]: [What went live — 1 line]

🔄 *IN PROGRESS*
• [Project]: [Where it stands — 1 line]

⚠️ *BEHIND / AT RISK*
• [Project]: [Why + impact — 1 line]

🚨 *BLOCKED*
• [Blocker]: [Specific ask — 1 line]
""".strip()

DETAILED_FORMAT = """
Cars | [Date]

[1-2 sentence high-level summary.]

⚠️ DATE CHANGES

[Compare each project's current due date and milestone dates against dates mentioned in the previous weekly update. List only real changes. Format each as: "• Project: [what changed] (was MM/DD → now MM/DD)". Write "None" if no dates changed.]

📅 WIP — UPCOMING RELEASES

[Sorted by nearest upcoming date. For each active project with a date, one entry:
*Project Name* | [Status] | [Next date: MM/DD]
→ [Phase milestones if any, comma-separated with dates] — [1 key note from open tasks]
Skip projects with no dates. Skip Done/Misc/TAM Analysis. Max 12 projects.]

📋 PROJECT UPDATES

New this week: [Comma-separated project names, or "None"]
Completed: [Comma-separated project names marked Done, or "None"]

🚨 SUPPORT NEEDED

[Blocker name]: [Specific context and ask — skip section entirely if none]

🚀 KEY WINS & PROGRESS

• [Project]: [What was accomplished]

🔄 IN FLIGHT

• [Project]: [Current status, what's next]

📉 DEPRIORITIZED / BLOCKED

• [Project]: [Reason — Won't do / Blocked by X / Waiting on Y — skip section if none]
""".strip()


def _get_project_snapshot():
    """Open tasks + status per project."""
    projects = vault.get_project_tasks()
    lines = []
    for project, data in projects.items():
        status = data.get("status", "")
        open_tasks = [t["text"] for t in data["tasks"]]
        lines.append(f"### {project} [{status}]")
        for t in open_tasks[:5]:
            lines.append(f"  - [ ] {t}")
    return "\n".join(lines) if lines else "No active projects."


def _get_weekly_log():
    """Structured changelog from last 7 days for the prompt."""
    entries = vault.get_weekly_log(days=7)
    if not entries:
        return "No changelog entries yet — log starts accumulating from this run."
    # Filter out noise: investigate changes and auto-triage deletions
    filtered = [
        e for e in entries
        if e["type"] not in ("investigate_removed", "investigate_added")
        and not (
            e["type"] == "task_deleted"
            and (e.get("task", "").startswith("[SLACK]") or e.get("task", "").startswith("[EMAIL]"))
        )
    ]
    by_type: dict = {}
    for e in filtered:
        by_type.setdefault(e["type"], []).append(e)
    sections = []
    for e in by_type.get("task_completed", []):
        sections.append(f"  DONE [{e['ts'][:10]}] {e['project']}: {e.get('task', '')}")
    for e in by_type.get("project_status_changed", []):
        sections.append(f"  STATUS [{e['ts'][:10]}] {e['project']}: {e.get('from', '')} → {e.get('to', '')}")
    for e in by_type.get("task_deleted", []):
        sections.append(f"  DROPPED [{e['ts'][:10]}] {e['project']}: {e.get('task', '')}")
    return "\n".join(sections) if sections else "No changes logged this week."


def _get_missed_deliverables():
    """Projects due this week or earlier that are not Done."""
    today = date.today()
    all_projects = vault.get_all_projects_with_status()
    missed = [
        f"  {name} | due={info['due']} | status={info.get('status', '')}"
        for name, info in all_projects.items()
        if name not in _SKIP_PROJECTS
        and info.get("due", "") <= today.isoformat()
        and info.get("status", "").lower() not in ("done", "complete", "completed")
        and info.get("due", "")
    ]
    return "\n".join(sorted(missed)) if missed else "None — all projects with due dates are complete."


def _get_snapshot_diff():
    """Compare current project state against last week's Friday snapshot."""
    last = vault.load_last_project_snapshot()
    if not last:
        return "No prior snapshot — first run. Snapshot will be saved at end of this run."
    last_projects = last.get("projects", {})
    last_date = last.get("date", "unknown")
    lines = [f"(vs snapshot from {last_date})"]
    for name, curr in vault.get_all_projects_with_status().items():
        if name in _SKIP_PROJECTS:
            continue
        prev = last_projects.get(name)
        if not prev:
            lines.append(f"  NEW PROJECT: {name}")
            continue
        if curr.get("status", "") != prev.get("status", ""):
            lines.append(f"  STATUS: {name}: {prev['status']} → {curr['status']}")
        if curr.get("due", "") != prev.get("due", ""):
            lines.append(f"  DUE DATE: {name}: {prev.get('due') or 'none'} → {curr.get('due') or 'none'}")
    return "\n".join(lines) if len(lines) > 1 else "No status or due date changes since last snapshot."


def _get_asana_completed():
    """Tasks completed in Asana this week."""
    if not ASANA_WORKSPACE_GID:
        return "Asana not configured."
    from pm import asana_client
    tasks = asana_client.get_completed_tasks_this_week(ASANA_WORKSPACE_GID)
    if not tasks:
        return "None this week."
    lines = []
    for t in tasks:
        project = f" [{t['project']}]" if t["project"] else ""
        lines.append(f"  - {t['text']}{project}")
    return "\n".join(lines)


def _get_previous_update():
    return vault.get_previous_weekly_update()


_SKIP_PROJECTS = {"Misc", "TAM Analysis", "Cars Marketing Materials"}


def _get_wip_data():
    """Return structured WIP list: projects with status, due dates, phase milestones.

    Sorted by nearest upcoming date (soonest first). Excludes internal/skip projects.
    """
    projects = vault.get_project_tasks()
    rows = []
    for project_name, data in projects.items():
        if project_name in _SKIP_PROJECTS:
            continue
        status = data.get("status", "")
        if status.lower() in ("done", "complete", "completed"):
            continue
        overall_due = data.get("due", "")
        # Phase milestones = open tasks with @due() dates
        milestones = sorted(
            [{"text": t["text"], "due": t["due"]}
             for t in data["tasks"]
             if not t.get("done") and t.get("due")],
            key=lambda x: x["due"],
        )
        # Open notes = first 2 non-milestone open tasks
        notes = [t["text"] for t in data["tasks"] if not t.get("done")][:3]
        next_date = milestones[0]["due"] if milestones else overall_due
        rows.append({
            "project": project_name,
            "status": status,
            "due": overall_due,
            "next_date": next_date,
            "milestones": milestones,
            "notes": notes,
        })
    rows.sort(key=lambda x: x["next_date"] or "9999-99-99")
    return rows


def _get_project_changes():
    """Return new projects this week and projects currently marked Done."""
    new_projects = vault.get_new_projects_this_week()
    all_projects = vault.get_all_projects_with_status()
    done_projects = {
        name: info
        for name, info in all_projects.items()
        if info.get("status", "").lower() == "done"
    }
    return new_projects, done_projects


def _sync_new_projects_to_asana(new_projects, board_gid, workspace_gid, user_gid):
    """For each new Obsidian project not already on the Asana board, create it.

    Returns list of project names that were created.
    """
    from pm import asana_client
    task_map = asana_client.get_board_task_map(board_gid)
    created = []
    for project_name in new_projects:
        if project_name in _SKIP_PROJECTS:
            continue
        if project_name.strip().lower() in task_map:
            continue  # already on board
        try:
            task = asana_client.create_task(
                board_gid, project_name, assignee_gid=user_gid
            )
            if task:
                vault.set_project_asana_link(project_name, task.get("permalink_url", ""))
                vault.log_weekly_change("project_created", project_name)
                created.append(project_name)
        except Exception:
            pass
    return created


def _sync_completed_projects_to_asana(done_projects, boards):
    """For each Done project, find it on the Top 15 Asana board, mark it complete,
    and write the Asana URL back to the project file.

    Only operates on the 'Travel: Cars Top 15' board.
    Returns list of project names that were synced.
    """
    from pm import asana_client
    top15 = [b for b in boards if "top 15" in b.get("name", "").lower()]
    synced = []
    for project_name, info in done_projects.items():
        asana_task = asana_client.search_board_task_by_name(top15, project_name)
        if not asana_task:
            continue
        url = asana_task.get("permalink_url", "")
        # Add Asana link to the project file (even if already complete in Asana)
        if url:
            vault.set_project_asana_link(project_name, url)
        # Mark complete in Asana if not already
        if not asana_task.get("completed"):
            try:
                asana_client.complete_task(asana_task["gid"])
                synced.append(project_name)
            except Exception:
                pass
    return synced


def _sync_project_info_from_asana(board_gid):
    """Fetch due dates + Asana URLs from Top 15 board and write to project frontmatter.

    Returns list of project names that were updated.
    """
    from pm import asana_client
    task_map = asana_client.get_board_task_map(board_gid)
    all_projects = vault.get_all_projects_with_status()
    updated = []
    for project_name in all_projects:
        task = task_map.get(project_name.strip().lower())
        if not task:
            continue
        changed = False
        url = task.get("permalink_url", "")
        due = task.get("due_on", "") or ""
        if url:
            changed |= vault.set_project_asana_link(project_name, url)
        if due:
            changed |= vault.set_project_due(project_name, due)
        if changed:
            updated.append(project_name)
    return updated


def run_weekly():
    print(f"{DIM}Gathering project data...{RESET}")
    project_snapshot  = _get_project_snapshot()
    weekly_log        = _get_weekly_log()
    missed            = _get_missed_deliverables()
    snapshot_diff     = _get_snapshot_diff()
    asana_completed   = _get_asana_completed()
    previous_update   = _get_previous_update()
    new_projects, done_projects = _get_project_changes()
    wip_rows          = _get_wip_data()
    status_updates    = vault.get_all_status_updates()

    today       = date.today()
    report_date = today + timedelta(days=1)
    date_str    = report_date.strftime("%b %-d, %Y")

    # Format WIP table for prompt
    wip_lines = []
    for r in wip_rows:
        milestones_str = ", ".join(
            f"{m['text']} ({m['due']})" for m in r["milestones"]
        ) or "no phase milestones"
        notes_str = " | ".join(r["notes"][:2]) or "no open tasks"
        wip_lines.append(
            f"  {r['project']} | status={r['status']} | overall_due={r['due'] or 'TBD'}"
            f" | milestones=[{milestones_str}] | notes=[{notes_str}]"
        )
    wip_block = "\n".join(wip_lines) if wip_lines else "No active projects with dates."

    # Format status updates for prompt
    status_block_lines = []
    for name, (upd_date, upd_text) in sorted(status_updates.items()):
        status_block_lines.append(f"  {name} [{upd_date}]: {upd_text}")
    status_block = "\n".join(status_block_lines) if status_block_lines else "No status updates written yet."

    data_block = f"""--- PROJECT STATUS UPDATES (written by the PM — use this as the primary source for project summaries) ---
{status_block}

--- CHANGELOG THIS WEEK (task completions, status changes, dropped tasks) ---
{weekly_log}

--- MISSED DELIVERABLES (due this week or earlier, not Done) ---
{missed}

--- WEEK-OVER-WEEK CHANGES (vs last Friday snapshot) ---
{snapshot_diff}

--- PROJECT CHANGES THIS WEEK ---
New projects added: {', '.join(new_projects) if new_projects else 'None'}
Projects marked Done: {', '.join(done_projects.keys()) if done_projects else 'None'}

--- WIP TABLE (sorted by nearest upcoming date) ---
{wip_block}

--- OPEN PROJECTS (current status + open tasks) ---
{project_snapshot}

--- COMPLETED IN ASANA THIS WEEK ---
{asana_completed}

--- PREVIOUS WEEKLY UPDATE (for date comparison — flag any project dates that changed) ---
{previous_update[:2000] if previous_update else "None."}"""

    exec_prompt = f"""You are a PM assistant writing a weekly status update for PM_NAME, PM on the product team at YOUR_COMPANY (B2B corporate travel). This goes to the CEO and VP Product on Slack — keep it executive-level: short, high-signal, no noise.

Write this week's update using ONLY the data provided below. Do not infer or add anything not present in the data.

OUTPUT FORMAT — follow this exactly:

{EXEC_FORMAT}

Rules:
- Replace [Date] with: {date_str}
- Opening line: one punchy sentence on the week's theme — what moved, what shipped, what the focus was
- SHIPPED: only things that actually went live/released this week (use completed tasks as evidence); omit section if nothing shipped
- IN PROGRESS: top 3-5 active projects only — pick the highest-signal ones; one tight line each
- BEHIND / AT RISK: projects explicitly overdue, blocked waiting on others, or slipping — omit section if none
- BLOCKED: only hard blockers with a specific ask; omit section if none
- Do NOT include TAM Analysis, Misc, or internal tooling projects
- Use # for the title line, *bold* for section header labels, • for bullets
- Omit sections that have nothing to report (e.g. no BLOCKED = skip that section)
- No dividers, no extra headers
- Total length: under 150 words

{data_block}
"""

    detailed_prompt = f"""You are a PM assistant writing a weekly pre-read for PM_NAME, PM on the product team at YOUR_COMPANY (B2B corporate travel). This goes to the Cars leads team on Slack.

Write this week's update using ONLY the data provided below. Do not infer or add anything not present in the data.

OUTPUT FORMAT — follow this exactly:

{DETAILED_FORMAT}

Rules:
- Replace [Date] with: {date_str}
- Summary: 1-2 punchy sentences on overall momentum and the main theme of the week
- DATE CHANGES: compare each project's due/milestone dates in WIP TABLE against dates mentioned in the previous update. Only flag real changes. If no dates changed, write "None"
- WIP TABLE: use the WIP TABLE data exactly — sort by next_date ascending. For each project's "last week" note, use the PROJECT STATUS UPDATES entry if available (prefer this over task names). Format each row as "*Project* | Status | Due MM/DD" then "→ status update text or key task". Skip projects with overall_due=TBD and no milestones. Max 12 rows
- Support Needed: only real blockers or asks — skip section entirely if none
- Key Wins: ONLY use CHANGELOG THIS WEEK entries with type=task_completed or type=project_status_changed (to Done) as evidence — do not infer or embellish
- A project goes in Key Wins only if it appears in the CHANGELOG THIS WEEK; do not use historical open tasks as evidence
- In Flight: projects that are active with open tasks remaining
- Deprioritized/Blocked: anything explicitly blocked, waiting, or won't-do — skip section if none
- PROJECT UPDATES: always include; list new and completed projects verbatim; if none, write "None"
- Do NOT include TAM Analysis, Misc, or internal tooling projects
- Use # for the title line, • for bullets, emoji for section headers, *bold* for project names in WIP table
- No dividers, no extra headers
- Keep total length under 500 words

{data_block}
"""

    print(f"{DIM}Generating weekly update...{RESET}\n")

    # Find claude binary (installed under versioned path)
    matches = sorted(glob.glob(
        "/Users/reidgilbertson/Library/Application Support/Claude/claude-code/*/claude"
    ))
    if not matches:
        print("Error: claude CLI not found.")
        return
    claude_bin = matches[-1]  # use latest version

    import os
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    def _call_claude(prompt_text):
        r = subprocess.run(
            [claude_bin, "-p", prompt_text],
            capture_output=True, text=True, env=env,
        )
        if r.returncode != 0:
            print(f"Error running claude CLI: {r.stderr}")
            return None
        return r.stdout.strip()

    exec_text = _call_claude(exec_prompt)
    if not exec_text:
        return
    detailed_text = _call_claude(detailed_prompt)
    if not detailed_text:
        return

    print(f"{BOLD}{CYAN}{'━' * 60}{RESET}")
    print(f"{BOLD}WEEKLY UPDATE — {date_str}{RESET}")
    print(f"{BOLD}{CYAN}{'━' * 60}{RESET}\n")
    print(exec_text)
    print()

    exec_file    = vault.save_weekly_update(exec_text, report_date, suffix="-exec")
    detailed_file = vault.save_weekly_update(detailed_text, report_date)
    print(f"{DIM}Saved exec    → {exec_file}{RESET}")
    print(f"{DIM}Saved detailed → {detailed_file}{RESET}")

    if ASANA_WORKSPACE_GID:
        from pm.config import ASANA_BOARDS, ASANA_USER_GID
        top15 = next((b for b in ASANA_BOARDS if "top 15" in b.get("name", "").lower()), None)
        if top15:
            # Pull due dates + URLs from Asana → vault
            print(f"{DIM}Syncing project info from Asana Top 15...{RESET}")
            info_updated = _sync_project_info_from_asana(top15["gid"])
            if info_updated:
                print(f"  {GREEN}✓{RESET} Updated {len(info_updated)} project(s): {', '.join(info_updated)}")

            # Mark completed projects in Asana
            if done_projects:
                print(f"{DIM}Syncing completed projects to Asana...{RESET}")
                synced = _sync_completed_projects_to_asana(done_projects, ASANA_BOARDS)
                for name in synced:
                    print(f"  {GREEN}✓{RESET} {name} — marked complete in Asana")
                if not synced:
                    print(f"  {DIM}No new completions to sync{RESET}")

            # Create new Obsidian projects on Asana board if missing
            if new_projects:
                print(f"{DIM}Syncing new projects to Asana Top 15...{RESET}")
                created = _sync_new_projects_to_asana(
                    new_projects, top15["gid"], ASANA_WORKSPACE_GID, ASANA_USER_GID
                )
                for name in created:
                    print(f"  {GREEN}✓{RESET} {name} — created on Asana Top 15")
                if not created:
                    print(f"  {DIM}No new projects to add (already on board or skipped){RESET}")

    snapshot_file = vault.save_project_snapshot()
    print(f"{DIM}Saved project snapshot → {snapshot_file}{RESET}")
