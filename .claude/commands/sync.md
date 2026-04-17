---
description: Triage sync — Granola meeting notes, email, Slack. No metrics.
allowed-tools: Bash, mcp__claude_ai_Gmail__gmail_search_messages, mcp__claude_ai_Gmail__gmail_read_thread, mcp__claude_ai_Gmail__gmail_read_message, mcp__claude_ai_Slack__slack_search_public_and_private, mcp__claude_ai_Slack__slack_read_thread, mcp__granola__list_meetings, mcp__granola__get_meetings, mcp__granola__query_granola_meetings
---

Triage sync — file Granola meeting notes, add actionable email and Slack tasks to the vault. No Snowflake, no Amplitude, no calendar events.

Run all three steps. Use a **2-hour lookback window** for email and Slack (catches things since last sync).

---

## Step 1: File Granola meeting notes

Get the current project list:
```bash
cd /Users/reidgilbertson/claude && venv/bin/python - << 'EOF'
import sys; sys.path.insert(0, '.')
from pm import vault
print('\n'.join(vault.get_project_names()))
EOF
```

Fetch today's meetings from Granola:
```
mcp__granola__list_meetings(time_range="custom", custom_start="TODAY", custom_end="TODAY")
```
Use ISO date strings (e.g., `2026-04-15`).

For meetings returned that have summaries, batch-fetch details:
```
mcp__granola__get_meetings(meeting_ids=["id1", "id2", ...])
```

For each meeting with summary content:
1. Extract: title, date (YYYY-MM-DD), attendees, summary text, action items
2. Match title/attendee keywords against the project list (case-insensitive). Use `None` if no clear match.
3. Check if meeting notes file already exists. Notes live in week subfolders: `Meeting Notes/WEEK_SUNDAY/YYYY-MM-DD Meeting Title.md` where WEEK_SUNDAY is the Sunday starting the week (US convention). Use Glob `**/YYYY-MM-DD Meeting*` to find it regardless of folder. When creating new files, calculate the Sunday folder: `sunday = date - ((date.weekday() + 1) % 7)` days.

**Three cases:**

**A) File doesn't exist** — write new file:
```markdown
**Date:** YYYY-MM-DD
**Project:** Project Name (or General)
**Attendees:**
- Name 1
- Name 2

## Summary
(Granola AI summary)

## Action Items
- [ ] Item 1
- [ ] Item 2

## Notes
(Granola notes/key points, if available)
```

**B) File exists but has NO `## Summary` section** — the PM took manual notes before Granola processed. **Merge:** read the existing file, then use the Edit tool to insert the Granola `## Summary` section and any Granola action items that aren't already present. Preserve all existing content (manual notes, manually added action items, etc.). Insert the Summary section after the metadata block (Date/Project/Attendees) and before any existing sections. If the file has no metadata block, insert at the top.

**C) File exists and already has a `## Summary` section** — Granola was already filed. **Skip entirely.**

4. For each action item (from Granola), add to the matched project file if not already present:
```bash
cd /Users/reidgilbertson/claude && venv/bin/python - << 'EOF'
import sys; sys.path.insert(0, '.')
from pm import vault
task = "Action item text"
if not vault.task_exists_in_projects(task):
    vault.append_task_to_project("Project Name", task)
    vault.inject_task_into_daily_note(task, "Project Name")
    print(f"action_added: {task}")
else:
    print(f"action_skip: {task}")
EOF
```

---

## Step 2: Email triage

```
gmail_search_messages(q="is:unread -category:promotions -category:social -category:updates newer_than:2h")
```

**Skip:** automated alerts, newsletters, calendar invites/responses, CC-only, Jira/noreply, **Zoom AI summary emails (meeting notes come from Granola now)**.
**Action needed:** direct questions, requests, follow-ups waiting on the PM, messages from key stakeholders (Ryan, Shruthi, Ellen, Jacob, Danish, Joe, Katie, AMs, customers).

For each actionable email, add task with source URL:
- **Email URL:** `https://mail.google.com/mail/u/0/#all/{threadId}`
```bash
cd /Users/reidgilbertson/claude && venv/bin/python - << 'EOF'
import sys; sys.path.insert(0, '.')
from pm import vault
task = "[EMAIL] Reply to FIRSTNAME re: SUBJECT"
url = "https://mail.google.com/mail/u/0/#all/THREAD_ID"
if not vault.task_exists_in_projects(task):
    vault.append_task_to_project("Misc", task, url=url)
    vault.inject_task_into_daily_note(task, "Misc", url=url)
    print(f"email_added: {task}")
else:
    print(f"email_skip: {task}")
EOF
```

---

## Step 3: Slack triage

```
slack_search_public_and_private(query="<@YOUR_SLACK_USER_ID> after:2_HOURS_AGO_DATE")
slack_search_public_and_private(query="to:me after:2_HOURS_AGO_DATE")
```

Use today's date minus 2 hours for the `after:` date (format: YYYY-MM-DD).

**Skip:** FYI announcements, bots (Google Calendar DMs, Jira digests), one-liner replies ("for sure!", "nice!"), passive CC.
**Action needed:** direct questions, requests for input, open DM questions, time-sensitive coordination.

For each actionable message, add task with Slack permalink:
```bash
cd /Users/reidgilbertson/claude && venv/bin/python - << 'EOF'
import sys; sys.path.insert(0, '.')
from pm import vault
task = "[SLACK] Reply to FIRSTNAME re: TOPIC"
url = "SLACK_PERMALINK"
if not vault.task_exists_in_projects(task):
    vault.append_task_to_project("Misc", task, url=url)
    vault.inject_task_into_daily_note(task, "Misc", url=url)
    print(f"slack_added: {task}")
else:
    print(f"slack_skip: {task}")
EOF
```

---

## Output

After all three steps, print exactly one summary line in this format:
```
SYNC_RESULT: {N} granola, {N} email, {N} slack
```
Where N is the count of newly filed/added items (not skipped). Use 0 if none.
Example: `SYNC_RESULT: 0 granola, 2 email, 1 slack`
