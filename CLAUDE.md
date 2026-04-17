# Context for Claude

## Who you're working with

Product Manager — update this with your name, vertical, and focus areas.

## Proactive context loading

At the start of any session involving project work, status, or next steps:
1. Read today's daily note: `Daily Notes/YYYY-MM-DD.md` (use today's date)
2. Read the relevant project file(s) in `Projects/` before answering

## Behavior rules

### 1. Plan first
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan — don't keep pushing
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- One task per subagent for focused execution

### 3. Self-improvement loop
- After ANY correction: update memory with the pattern
- Write rules that prevent the same mistake
- Review memory at session start for relevant project

### 4. Verification before done
- Never mark a task complete without proving it works
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand elegance (balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- Skip for simple, obvious fixes — don't over-engineer

### 6. Autonomous bug fixing
- When given a bug report: just fix it. Point at logs, errors, tests — then resolve them.
- Zero context switching required from the user

### 7. Proactive context saving
- After any significant data pull or discovery: save findings to CLAUDE.md or the relevant doc file
- Keep entries concise and queryable — future sessions should pick up where this one left off

## Task management

1. **Plan First** — write plan with checkable items before starting
2. **Verify Plan** — check in before implementation
3. **Track Progress** — mark items complete as you go
4. **Explain Changes** — high-level summary at each step
5. **Capture Lessons** — update memory after corrections

## Core principles

- **Simplicity First**: make every change as simple as possible
- **No Laziness**: find root causes, no temporary fixes, senior developer standards
- **Minimal Impact**: only touch what's necessary

---

## PM automation tooling

### Project layout
```
~/claude/
├── run_query.py          # Snowflake query runner → (cols, rows)
├── pm.py                 # CLI entry point for all PM automation
├── pm/
│   ├── today.py          # pm.py briefing — daily briefing (called by /today skill)
│   ├── weekly.py         # pm.py weekly — generate weekly update via Claude API
│   ├── metrics.py        # Snowflake daily/weekly metrics
│   ├── vault.py          # Read/write Obsidian vault
│   ├── asana_client.py   # Asana API
│   ├── tasks.py          # Task add/done helpers
│   └── notes.py          # Meeting note processing
├── queries/              # .sql files + .csv exports
└── data/
    ├── config.json       # Asana GIDs, vault path, boards
    └── metrics_schema.json
```

### pm.py commands
```bash
venv/bin/python pm.py briefing           # Daily briefing (metrics + projects + news — called by /today skill)
venv/bin/python pm.py weekly             # Generate weekly update (use /schedule-weekly, not standalone)
venv/bin/python pm.py task add "text" [--project NAME]
venv/bin/python pm.py task done [--project NAME]
venv/bin/python pm.py task due "text" DATE [--project NAME]  # DATE: YYYY-MM-DD, today, tomorrow, weekday
venv/bin/python pm.py sync               # Sync daily note checkboxes → project files
venv/bin/python pm.py note [--file PATH] # Process meeting notes
venv/bin/python pm.py prd [--project NAME]
venv/bin/python pm.py roadmap
venv/bin/python pm.py metrics-setup     # Re-discover + cache Snowflake schema (run if metrics break)
```

### pm.py briefing — sections in order
1. **METRICS** — Mon/Sun: last week vs prior 4 weeks. Other days: yesterday vs prior 4 same-weekdays.
2. **ACTIVE PROJECTS** — tasks from Obsidian Projects/, sorted by due date
3. **ASANA BOARDS** — overdue (red) + upcoming tasks
4. **TO INVESTIGATE** — ideas from `Areas/Discovery + Research/Ideas to Investigate.md`
5. **INDUSTRY NEWS** — Google News RSS, your industry keywords, last 7 days
6. **CLAUDE CAN HELP WITH** — top 8 Obsidian tasks matching action patterns
7. Saves daily note → `Daily Notes/YYYY-MM-DD.md`

### Obsidian vault paths
```
Obsidian Vault/
├── Projects/              # One folder per project, each with a .md file
├── Areas/
│   ├── Weekly Updates/    # YYYY-MM-DD.md (saved by pm.py weekly, tomorrow's date)
│   └── Discovery + Research/Ideas to Investigate.md
├── Daily Notes/           # YYYY-MM-DD.md (saved by pm.py briefing)
└── Meeting Notes/         # YYYY-MM-DD Meeting Name.md
```

### vault.sync_daily_note behavior
`sync_daily_note(for_date, sync_deletions)` returns `(completed, added, skipped, deleted)`.

- **Yesterday:** `sync_deletions=True` — closed day's note is source of truth; removals propagate to project files
- **Today:** `sync_deletions=False` — today's note is partial; never delete based on it
- **Task text matching:** strips `@due(YYYY-MM-DD)` and `📅 YYYY-MM-DD` before comparing

### Due dates in Obsidian tasks
Format: `@due(YYYY-MM-DD)` in project `.md` files. Set via: `pm.py task due "text" friday`
Display colors: overdue=red, today=yellow, ≤7 days=green, further=dim.

---

## Reference files

Load these when relevant — don't load all at once:

| File | Contents |
|---|---|
| `~/.claude/docs/snowflake.md` | Tables, columns, SQL patterns, query runner usage |
| `~/.claude/docs/analytics.md` | Key metrics, goals, Amplitude chart IDs |
| `~/.claude/docs/communication.md` | Slack formatting rules, Gmail triage, contacts, Calendar tools |
| `~/.claude/docs/dev-environment.md` | Local dev setup, credentials, DNS |
| `~/.claude/docs/infographics.md` | Brand system, chart label rules |
| `~/.claude/docs/people-and-cadence.md` | Key people, meeting cadence, boards |
| `~/.claude/docs/query-patterns.md` | Reusable Snowflake/Amplitude queries |
| `~/.claude/docs/project-dependencies.md` | Cross-project dependency map |
