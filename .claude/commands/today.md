---
description: Run daily briefing — sync tasks, gather projects, calendar, triage, metrics, write daily note
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, mcp__claude_ai_Gmail__gmail_search_messages, mcp__claude_ai_Gmail__gmail_read_thread, mcp__claude_ai_Slack__slack_search_public_and_private, mcp__claude_ai_Slack__slack_read_thread, mcp__claude_ai_Google_Calendar__list_events, mcp__google-sheets__values_get, mcp__google-sheets__values_update, mcp__granola__list_meetings, mcp__granola__get_meetings, mcp__granola__get_meeting_transcript, mcp__granola__query_granola_meetings, mcp__claude_ai_Datadog__search_datadog_logs
---

You are the PM's daily assistant. Run the full daily briefing by executing each step below.
Today's date: use the current date (check with `date +%Y-%m-%d` if needed).
Vault path: `/Users/reidgilbertson/Documents/Obsidian Vault`

IMPORTANT: Run steps that don't depend on each other in parallel using subagents or parallel tool calls.

**NEVER overwrite an existing daily note.** Before writing, check if `Daily Notes/WEEK_MONDAY/TODAY.md` already exists. If it does, write to `Daily Notes/WEEK_MONDAY/TODAY-v2.md` instead (or `-v3`, `-v4`, etc. if those exist too). The existing note is the PM's working copy — preserve it. The new file lets the PM compare and merge manually.

---

## Step 1: Sync yesterday's daily note → project files

Find yesterday's daily note. The daily notes live in week-folders: `Daily Notes/YYYY-MM-DD/YYYY-MM-DD.md` where the folder is the Monday of that week.

1. Calculate yesterday's date
2. Find the file: `Glob("Daily Notes/*/YESTERDAY.md")` in the vault
3. Read it
4. For each `[x]` task line (completed task):
   - Extract the task text (strip `[x]`, URLs in `[LABEL](url)` format, `@due(...)`, trailing ` ✅ YYYY-MM-DD`)
   - Search for the matching `- [ ]` line in project files under `Projects/`
   - If found, change `[ ]` to `[x]` using the Edit tool
5. For each `[ ]` task in the daily note under a project heading that does NOT exist in the corresponding project file:
   - Append it to the project file's task section
6. Report: "Synced N completions, added M new tasks from yesterday's note"

**Matching rules:**
- Normalize before comparing: strip `[SLACK](url)` / `[EMAIL](url)` link syntax (keep label text), strip `@due(YYYY-MM-DD)`, strip `📅 YYYY-MM-DD`, strip ` ✅ YYYY-MM-DD`, collapse whitespace, lowercase
- Match if normalized text of daily note task contains normalized text of project task (or vice versa)
- Skip `To Investigate` section tasks — those aren't project tasks
- Do NOT delete tasks from project files (no deletion sync)

---

## Step 2: Sync roadmap statuses → Obsidian

The Google Sheets roadmap is the source of truth for project status. Sync it to Obsidian so project files are current before gathering tasks.

1. Read the roadmap: `mcp__google-sheets__values_get(spreadsheetId="YOUR_ROADMAP_SPREADSHEET_ID", range="YOUR_ROADMAP_TAB!A1:N50")`
2. Read all Obsidian project files' YAML frontmatter (Glob `Projects/*/` → read each `.md`)
3. For each roadmap row, match to an Obsidian project file (fuzzy match on project name)
4. Compare `status:` in frontmatter vs column A in the roadmap
5. If they differ, **roadmap wins** — update the Obsidian file's YAML frontmatter:
   - Change `status:` to the roadmap value
   - Update the status tag (e.g., `dev-in-progress` → `measuring`)
   - Use the Edit tool to modify the frontmatter in place
6. Also sync `tech_lead:`, `designer:`, and `team:` fields if the roadmap has newer values

**Status tag mapping:** Measuring → `measuring`, Dev in progress → `dev-in-progress`, Ready for dev → `ready-for-dev`, DTD → `dtd`, PTD → `ptd`, Design in progress → `design-in-progress`, Product review → `product-review`, Discovery → `discovery`, Paused → `paused`, Blocked → `blocked`, Done → `done`

**Auto-create missing project files:** If a roadmap entry has no matching Obsidian project file, create one automatically:
- Create directory: `Projects/PROJECT_NAME/`
- Write `.md` file with YAML frontmatter (status, area: Cars, type, owner, tech_lead, designer, team, tags) and empty sections: `## Context`, `## Links`, `## Open Tasks`, `## Key Decisions`
- Populate `## Context` from the roadmap's Last Update column (column N)
- No `# Title` heading (Obsidian inline title from filename)

Report: "Roadmap sync: N statuses updated, M new project files created"

---

## Step 3: Gather all tasks from active projects

1. Glob all project directories: `Projects/*/` in the vault
2. For each project `.md` file, read the YAML frontmatter
3. Skip if `status` is `done`, `complete`, or `completed` (case-insensitive)
4. Collect all `- [ ]` lines (open tasks) with:
   - Project name (from directory name)
   - `@due(YYYY-MM-DD)` date if present
   - Status and due date from frontmatter
5. Also read `Areas/Discovery + Research/Ideas to Investigate.md` — collect the first 5 unchecked items as backlog

Store all tasks in memory for Step 6.

---

## Step 3: Fetch today's calendar

```
gcal_list_events(
  calendarId="primary",
  timeMin="TODAY T00:00:00",
  timeMax="TODAY T23:59:59",
  timeZone="America/Los_Angeles",
  condenseEventDetails=false
)
```

Filter — **include** if:
- Not an all-day event
- Not eventType "workingLocation"
- the PM has not declined (myResponseStatus != "declined")
- Has at least 2 attendees (skip solo blocks)

For each included meeting, extract:
- **time**: start time formatted as "9:30 AM"
- **title**: event summary
- **attendees**: display names excluding the PM (YOUR_EMAIL@company.com). Cap at 12, add "and N others" if truncated
- **description**: stripped of HTML, Zoom links, phone numbers. Keep only real agenda text

Store meeting list for Steps 4, 6, 7.

---

## Step 4: File Granola meeting notes

Fetch recent meetings from Granola (last 5 days):
```
mcp__granola__list_meetings(time_range="custom", custom_start="5_DAYS_AGO", custom_end="TODAY")
```
Use ISO date strings (e.g., `2026-04-10`, `2026-04-15`).

For meetings returned, batch-fetch details (up to 10 per call):
```
mcp__granola__get_meetings(meeting_ids=["id1", "id2", ...])
```

For each meeting that has summary content:
1. Extract: title, date (YYYY-MM-DD), attendees, summary text, action items
2. Match title/attendee keywords against project names from Step 2
3. Check if `Meeting Notes/YYYY-MM-DD Meeting Title.md` already exists (Glob)

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

**Action item extraction:** For each action item (from Granola), check if it already exists in the matched project file. If not, append it as a `- [ ]` task.

**Decision extraction:** Look for decisions in the summary (statements like "we decided", "agreed to", "going with", "will do X instead of Y", timeline commitments, scope changes). If found, append to the matched project file under a `## Decisions` section:
```markdown
## Decisions
- [YYYY-MM-DD] Decision text — context/reasoning
```
If the section doesn't exist, create it above the tasks section.

Report: "Granola notes: N found, M filed, K action items added, D decisions captured"

---

## Step 5: Classify, carry over, and prioritize tasks

Using all tasks gathered in Step 2, classify each:

**Respond:** starts with `[SLACK]` or `[EMAIL]`, or contains "reply to", "respond to", "review X's"
**Waiting:** contains "waiting on", "from X for", "pending", "follow up for", "PTD from", "DTD from"
**Do:** everything else

**Carry over from yesterday:** Read yesterday's daily note. Collect all unchecked `[ ]` tasks from the `Today's Focus` and `Action Queue` sections. Deduplicate against the project tasks already gathered in Step 3 (normalize text for comparison — strip URLs, `@due()`, `*(Project)*` suffixes, overdue labels). Any remaining tasks are carryover — include them in today's Action Queue under their original classification (Respond/Do/Waiting). These go INTO the Action Queue, not a separate section.

**Select Today's Focus** (5-7 tasks max):
1. Tasks with `@due(TODAY)` — mandatory inclusion
2. Overdue tasks (`@due` before today) — sorted by days overdue, most overdue first
3. Tasks from projects that have meetings today (match project names from Step 3)
4. Fill remaining slots with soonest-due "Do" tasks

---

## Step 5.5: Pull recent Booking failures

Booking failures are **actionable AM-escalation signals**, not routine metrics — they surface real customer incidents that may need AM follow-up today. (This is an exception to the "no metrics in briefing" rule: we're not pulling funnel/conversion data, just incident triage.)

### A. Query Datadog (last 24h)

```
mcp__claude_ai_Datadog__search_datadog_logs(
  query='service:YOUR_SERVICE_NAME status:error "Gateway Book Error" env:prd-use1-default',
  from="now-24h",
  to="now",
  sort="-timestamp",
  extra_fields=["io-htleng-user-id", "io-htleng-business-id", "io-htleng-supplier-name", "io-htleng-provider-key", "io-htleng-operation", "error", "errorTags", "rentalCompanyName"],
  max_tokens=8000
)
```

### B. Parse each failure

For each log entry, extract:
- `@io-htleng-user-id` — decode scientific notation (e.g. `1.739301e+06` → `1739301`)
- `@io-htleng-business-id` — decode scientific notation
- `@io-htleng-supplier-name` (amadeus, hertzGroup, priceline, etc.)
- `@rentalCompanyName` (brand, e.g. HERTZ, AVIS)
- `@errorTags.errorReason` (billingCode, offerNoLongerAvailable, unknown, etc.)
- `@error.metadata.errorcode` (e.g. 10192)
- Short error summary from `@error.details` (truncate to ~100 chars)
- Timestamp

**Skip** if `@errorTags.errorRetryable = true` or `@error.metadata.errorretryable = "true"` — those are transient and self-healed.

### C. Group & count

Group by `(user_id, errorReason)`. Count failures per group. Track if same user_id appears 3+ times in <30min across any error reason — flag as `HIGH retry` for urgency.

### D. Enrich from Snowflake

Collect unique business IDs from remaining failures. Run **one** query:

```bash
cd /Users/reidgilbertson/claude && venv/bin/python - << 'EOF'
import sys; sys.path.insert(0, '.')
from run_query import run_query
biz_ids = "(1199339, 637136, ...)"  # unique business IDs from failures
cols, rows = run_query(f"""
    SELECT ACCOUNT_ID, ACCOUNT, ACCOUNT_MANAGER_NAME, ADMIN_INDUSTRY, IS_DEMO, IS_INTERNAL
    FROM ANALYTICS.DIM_ACCOUNTS
    WHERE ACCOUNT_ID IN {biz_ids}
""")
for row in rows: print(row)
EOF
```

### E. Filter internal/test accounts

Drop rows where any of:
- `IS_INTERNAL = TRUE`
- `IS_DEMO = TRUE`
- Account name matches `^\[Cars\]` or contains "Bug Bash", "QA Test", "Test Account"

These are engineering-bench failures, not customer incidents.

### F. Store for Step 6

Save structured list for daily note render:
```python
[
  {"time": "15:34 UTC", "account": "Ottawa University", "user_id": 1452020,
   "am": "Julian Mora", "supplier": "amadeus/AVIS", "reason": "offerNoLongerAvailable",
   "error_code": "10192", "summary": "RESERVATION DENIED - CAR NOT AVAILABLE",
   "retry_count": 1, "urgency": "normal"},
  ...
]
```

Sort by urgency (HIGH retry first), then by most recent.

Report: "Booking failures: N total in Datadog, M after filtering internal/test. K accounts affected, L high-urgency."

---

## Step 6: Write the daily note

**Before writing:** Check if `Daily Notes/WEEK_MONDAY/TODAY.md` already exists.
- **If it exists:** Read it to pull `[x]` states (so completed tasks stay checked in the new file). Write the new note to `Daily Notes/WEEK_MONDAY/TODAY-v2.md` (or `-v3` etc. if v2 exists). Do NOT overwrite the original.
- **If it doesn't exist:** Write directly to `Daily Notes/WEEK_MONDAY/TODAY.md`.

When carrying over `[x]` states: if a task was `[x]` in the existing note, mark it `[x]` in the new note too.

Calculate the week's Monday: the Monday of the current week (for the folder name, format YYYY-MM-DD).

Write using this exact structure:

```markdown
# WEEKDAY, Mon DD YYYY

📝 [[TODAY Meeting Notes]]

---

## Today's Focus
- [ ] Task text @due(YYYY-MM-DD) *(Project Name)*
- [ ] Overdue task *(Project Name)* — Nd overdue
(5-7 tasks from Step 6 selection)

## 🚨 Booking Failures (last 24h)
- **Ottawa University** · User `1452020` · AM **Julian Mora** · Avis/Amadeus · `offerNoLongerAvailable` (code 10192) · 1× · "RESERVATION DENIED - CAR NOT AVAILABLE"
- **HIGH** 🔴 AcmeCorp · User `1716852` · AM **Jane Doe** · Enterprise/Amadeus · `billingCode` (code 10192) · 8× in 30min · "Car booking failed due to issue with billing code"
(from Step 5.5 — sorted by urgency, HIGH retry first. Omit section entirely if zero real-customer failures after filtering.)

## Action Queue

### Respond
- [ ] [SLACK](url) Reply to X *(Project Name)*
- [ ] [EMAIL](url) Review Y *(Project Name)*

### Do
- [ ] Task text *(Project Name)*

### Waiting
- [ ] Example task *(Project Name)*

---

## Meetings
8:00 AM — Meeting Title (Attendee1, Attendee2)
9:00 AM — Meeting Title (Attendee1)
...

## Projects Reference

### Project Name — Status · due date
- [ ] task 1
- [ ] task 2

(repeat for all active projects — full task list)

## Backlog
- Top 5 Ideas to Investigate items
- [[Ideas to Investigate|Full list]]

## Industry News
(skip this section — it added noise, not value)
```

**Formatting rules:**
- Tasks in Today's Focus and Action Queue include `*(Project Name)*` suffix in italics
- Overdue tasks show `— Nd overdue` suffix
- Due-today tasks show the `@due()` tag
- Projects Reference section shows ALL open tasks for ALL active projects (this is the reference section, not prioritized)
- If a task was `[x]` in the existing daily note, keep it as `[x]` in the new note

Use the Write tool to create the file.

---

## Step 7: Write meeting notes template

File path: `Meeting Notes/WEEK_SUNDAY/TODAY Meeting Notes.md`
where WEEK_SUNDAY is the Sunday that starts the current week (US convention: Sun-Sat). Calculate: `sunday = today - ((today.weekday() + 1) % 7)` days. Format as YYYY-MM-DD. Create the subfolder if it doesn't exist.

For each meeting from Step 3, write a section:

```markdown
# TODAY Meeting Notes

## Meeting Title (TIME)
**Attendees:**
- Attendee Name 1
- Attendee Name 2

**Agenda:**
(from calendar description, or "No agenda provided")

**Notes:**


**Action Items:**

---
```

IMPORTANT: Attendees must be a markdown list (one per line with `-`), NOT a comma-separated string.

Skip if the file already exists and has content.

---

## Step 8: Email & Slack triage

Run both in parallel.

### Email
```
gmail_search_messages(q="is:unread -category:promotions -category:social -category:updates newer_than:3d")
```
**Skip:** automated alerts, newsletters, calendar invites/responses, CC-only threads, Jira/noreply addresses, Zoom AI summary emails (meeting notes come from Granola now), marketing/HR broadcasts
**Action needed:** direct questions, requests, follow-ups waiting on the PM, messages from key stakeholders

### Slack
```
slack_search_public_and_private(query="<@YOUR_SLACK_USER_ID> after:YESTERDAY")
slack_search_public_and_private(query="to:me after:YESTERDAY")
```
**Skip:** FYI announcements, bots (Google Calendar DMs, Jira digests), one-liner replies ("for sure!", "nice!"), passive CC
**Action needed:** direct questions, requests for input, open DM questions, time-sensitive coordination

### Adding tasks
For each actionable item:
1. Determine the best matching project (or "Misc" if none)
2. Format task: `[SLACK](permalink) Reply to FIRSTNAME re: TOPIC` or `[EMAIL](https://mail.google.com/mail/u/0/#all/THREADID) Review SUBJECT`
3. Check if task already exists in the project file (normalize and compare)
4. If new: append to project file AND edit the daily note to add under the correct project in Projects Reference AND add to Action Queue > Respond section

Report: "Email: N scanned, M tasks added. Slack: N scanned, M tasks added."

---

## Step 9: Propose roadmap updates for YOUR_ROADMAP_TAB

Spreadsheet ID: `YOUR_ROADMAP_SPREADSHEET_ID`
Tab: `YOUR_ROADMAP_TAB` (columns: A=Status, B=Project, N=Last Update)

1. Read the roadmap: `mcp__google-sheets__values_get(spreadsheetId, range="YOUR_ROADMAP_TAB!A1:N30")`
2. From Step 1 sync results, identify projects that had:
   - Tasks completed yesterday
   - Status changes (e.g., moved to Done)
   - New tasks added from Slack/email triage (Step 10)
3. For each project with updates, find its row in the roadmap (match on project name, fuzzy match OK)
4. Compose proposed changes — both **Status** (column A) and **Last Update** (column N)
5. **Present all proposed changes to the PM in a table and ask for confirmation before writing anything.** Format:

```
Proposed roadmap updates:

| Row | Project | Current Status → Proposed | Last Update (proposed) |
|-----|---------|---------------------------|------------------------|
| 5   | Daily Price | Dev in progress → Dev in progress | [new text] |
```

Confirm? (y to apply all, or specify which to skip)

6. Only after the PM confirms, write the changes: `mcp__google-sheets__values_update(...)`

Skip projects not on the roadmap. Skip if no meaningful change (don't overwrite with noise).

Report: "Roadmap updated: N projects synced to Google Sheets"

---

## Step 10: Start sync loop

Start a recurring `/sync` loop so Granola meeting notes, email, and Slack are triaged automatically throughout the day:

```
/loop 30m /sync
```

This runs every 30 minutes for the duration of the session. Mention it in the summary so the PM knows it's active.

---

## Step 11: Print summary

After all steps complete, print:

```
Daily briefing complete.

Synced: N completions from yesterday, M new tasks added
Meetings: N today
Granola notes: N filed, M action items added
Triage: N email tasks, M Slack tasks added
Focus: (list the 5-7 focus task titles)
Sync loop: running every 30m (Granola + email + Slack)

Daily note: Daily Notes/WEEK_MONDAY/TODAY.md
Meeting notes: Meeting Notes/TODAY Meeting Notes.md
Roadmap: N projects updated in Google Sheets

What would you like to tackle first?
```

---

## Error handling

- If a step fails, log the error and continue to the next step. Don't let one failure block the whole briefing.
- If Amplitude query fails, keep the existing funnel data in the daily note (or leave blank).
- If Gmail/Slack MCP tools are unavailable, skip triage and note it in the summary.
- If Google Calendar fails, **flag it explicitly** ("Calendar MCP failed — meeting notes will be blank. Likely transient auth issue. Re-run /today or manually populate."). Do NOT silently create a blank template.
- If Google Sheets fails, skip roadmap sync and flag it.
- If no yesterday daily note exists, skip Step 1 and note "No yesterday note found — skipping sync."
- If Datadog MCP fails in Step 5.5, skip the section and note "Booking failures check skipped — Datadog unavailable."
- If Snowflake fails in Step 5.5, still render failures but show raw `business_id` with `account=?, AM=?` and note "Snowflake enrichment failed — raw IDs only."

## Context growth (ongoing)

These behaviors build context over time — apply them whenever relevant during the briefing:

- **Query patterns:** If a non-trivial Snowflake/Amplitude query is run during the session, save the pattern to `~/.claude/docs/query-patterns.md` with context (what it answers, key tables, last result).
- **Dependencies:** If a new cross-project dependency surfaces (from Slack triage, meeting notes, or status changes), add it to `~/.claude/docs/project-dependencies.md`.
- **People:** If a new person is encountered in a meaningful role (project owner, blocker, stakeholder), check if they're in `~/.claude/docs/people-and-cadence.md` and add if missing.
- **Decisions:** Zoom summary processing (Step 4) captures decisions into project files automatically.
