"""
/note command — paste meeting notes, Claude extracts tasks + feedback + roadmap insights.
"""
import json
import sys

import anthropic

from pm import vault
from pm.config import ANTHROPIC_API_KEY

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def _read_pasted_notes():
    print(f"{BOLD}Paste your meeting notes below.{RESET}")
    print(f"{DIM}Press Enter then Ctrl+D (Mac) when done.{RESET}\n")
    try:
        return sys.stdin.read().strip()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)


def _process_with_claude(notes_text, projects):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    projects_str = "\n".join(f"- {p}" for p in projects)

    prompt = f"""You are a PM assistant. Analyze these meeting notes and extract:

1. **Action items** — specific tasks with a clear next step. For each task, suggest which project it belongs to from the list below, or "Standalone" if it doesn't fit a project.
2. **User/customer feedback** — pain points, requests, or complaints from customers or stakeholders.
3. **Roadmap insights** — strategic observations that should influence prioritization.

Available projects:
{projects_str}

Meeting notes:
{notes_text}

Respond ONLY with valid JSON in this exact format:
{{
  "tasks": [
    {{"text": "task description", "project": "Project Name or Standalone", "owner": "Me or person name"}}
  ],
  "feedback": [
    {{"text": "feedback description", "source": "customer or person name if mentioned"}}
  ],
  "roadmap_insights": ["insight 1", "insight 2"]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(message.content[0].text)


def _confirm_tasks(tasks, projects):
    """Show extracted tasks and let user confirm/reassign/skip each."""
    confirmed = []
    print(f"\n{BOLD}Extracted tasks — confirm each (Enter to accept, 's' to skip, or type a project name):{RESET}\n")

    for t in tasks:
        owner_label = f"  {DIM}[{t['owner']}]{RESET}" if t.get("owner", "Me") != "Me" else ""
        print(f"  {CYAN}•{RESET} {t['text']}")
        print(f"    Project: {BOLD}{t['project']}{RESET}{owner_label}")
        try:
            choice = input("    [Enter=accept | s=skip | type project name]: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if choice.lower() == "s":
            continue
        elif choice:
            t["project"] = choice
        confirmed.append(t)
    return confirmed


def run_note(file_path=None):
    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        return

    if file_path:
        try:
            notes_text = open(file_path).read().strip()
        except FileNotFoundError:
            print(f"File not found: {file_path}")
            return
    else:
        notes_text = _read_pasted_notes()

    if not notes_text:
        print("No notes provided.")
        return

    print(f"\n{DIM}Processing with Claude...{RESET}")
    projects = vault.get_project_names()

    try:
        result = _process_with_claude(notes_text, projects)
    except (json.JSONDecodeError, anthropic.APIError) as e:
        print(f"Error processing notes: {e}")
        return

    tasks = result.get("tasks", [])
    feedback = result.get("feedback", [])
    insights = result.get("roadmap_insights", [])

    # ── Tasks ──────────────────────────────────────────────────────
    if tasks:
        confirmed = _confirm_tasks(tasks, projects)
        for t in confirmed:
            project = t["project"]
            if project and project != "Standalone" and project in projects:
                vault.append_task_to_project(project, t["text"])
                print(f"  {GREEN}✓{RESET} Added to {BOLD}{project}{RESET}")
            else:
                # Add to a standalone section in this week's note
                vault.append_to_weekly_note("Standalone Tasks", f"- [ ] {t['text']}")
                print(f"  {GREEN}✓{RESET} Added to this week's note")
    else:
        print("No action items found.")

    # ── Feedback ───────────────────────────────────────────────────
    if feedback:
        print(f"\n{BOLD}User feedback tagged:{RESET}")
        feedback_lines = "\n".join(
            f"- {f['text']}" + (f" ({f['source']})" if f.get("source") else "")
            for f in feedback
        )
        vault.append_to_weekly_note("User Feedback", feedback_lines)
        for f in feedback:
            src = f"  {DIM}({f['source']}){RESET}" if f.get("source") else ""
            print(f"  {YELLOW}•{RESET} {f['text']}{src}")

    # ── Roadmap insights ───────────────────────────────────────────
    if insights:
        print(f"\n{BOLD}Roadmap insights:{RESET}")
        for i in insights:
            print(f"  {CYAN}•{RESET} {i}")

    # Save raw notes to weekly note
    vault.append_to_weekly_note("Meeting Notes", notes_text)
    print(f"\n{GREEN}Notes saved to this week's Obsidian note.{RESET}")
