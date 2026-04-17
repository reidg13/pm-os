# PM OS — Product Manager Operating System

A CLI-driven personal operating system for product managers. Automates daily briefings, meeting note processing, project/task management, email and Slack triage, and integration with Obsidian vault, Google Sheets roadmap, Asana, Snowflake analytics, and Claude API.

## What This Does

This PM OS is designed to reduce context switching and manual task juggling by centralizing:

1. **Daily Briefing** (`/today` skill) — Syncs Google Sheets roadmap to Obsidian, pulls project status, gathers tasks, files Granola meeting notes, triages email and Slack, proposes roadmap updates back to the sheet.
2. **Lightweight Triage** (`/sync` skill) — 30-minute interval sync of Granola notes, email, and Slack (2-hour lookback).
3. **Weekly Updates** (`/schedule-weekly` skill) — Generates weekly status update from vault data (including shipped projects synced from roadmap), reviews, and posts to Slack.
4. **Meeting Note Processing** — Extracts action items and decisions from Granola meeting notes, files them to Obsidian, and syncs to project task lists.
5. **Task Management** — Obsidian vault integration: add/complete tasks, set due dates, sync daily note checkboxes to project files.
6. **Metrics & Insights** — Snowflake integration for daily/weekly metrics (e.g., your product area bookings, GBV), Industry news feeds, and performance tracking.
7. **Competitor Research** — Voice of Customer Copilot for feature research, app store mining, and UX analysis.

## Data Flow: Google Sheets Roadmap + Obsidian Vault

The Google Sheets roadmap is the **source of truth for project status**. Obsidian vault is the **source of truth for tasks and details**. They sync bidirectionally via the `/today` skill:

```
Google Sheets Roadmap          Obsidian Vault
(status, owner, ETA)    ←→    (tasks, PRD, context)
        │                              │
        │  /today Step 2:              │
        │  Roadmap → Vault             │
        │  (status, team, new          │
        │   projects auto-created)     │
        │                              │
        │  /today Step 9:              │
        │  Vault → Roadmap             │
        │  (propose status/date        │
        │   updates back to sheet)     │
        │                              │
        └──────────┬───────────────────┘
                   │
                   ▼
            weekly.py picks up
            shipped projects from
            vault for weekly update
```

**Roadmap spreadsheet:** Set `ROADMAP_SPREADSHEET_ID` in your `.env` (get the ID from your Google Sheets URL)

Tabs:
- **YOUR_ROADMAP_TAB** — Active projects (Status, Project, Type, Owner, Tech Lead, Designer, PRD, Figma, PTD, DTD, Jira, ETA, Team, Last Update)
- **Shipped Work** — Completed items with ship dates
- **Feature Request** — Incoming feature requests
- **Idea Bank [WIP]** — Future ideas

## File Structure

```
/Users/YOUR_USERNAME/claude/
├── .env                          # Credentials (DO NOT COMMIT)
├── .env.example                  # Template for .env
├── .gitignore                    # Already configured
├── CLAUDE.md                      # Context for Claude AI sessions
├── README.md                      # This file
├── pm.py                          # CLI entry point
├── run_query.py                   # Snowflake query runner
│
├── pm/                            # Python modules
│   ├── __init__.py
│   ├── today.py                   # Daily briefing logic
│   ├── weekly.py                  # Weekly update generation
│   ├── vault.py                   # Obsidian vault I/O
│   ├── asana_client.py            # Asana API
│   ├── notes.py                   # Meeting note processing
│   ├── metrics.py                 # Snowflake metrics
│   ├── tasks.py                   # Task add/done helpers
│   ├── config.py                  # Config file loader
│   └── [other modules]
│
├── data/                          # Configuration & schema
│   ├── config.json                # Asana GIDs, vault path, project mappings
│   ├── config.json.example        # Template for config.json
│   └── metrics_schema.json        # Snowflake column name mappings
│
├── queries/                       # SQL files & exports
│   └── *.sql                      # Reusable Snowflake queries
│
├── .claude/                       # Claude Code integration
│   └── commands/
│       ├── today.md               # /today skill definition
│       ├── sync.md                # /sync skill definition
│       ├── schedule-weekly.md     # /schedule-weekly skill definition
│       ├── competitor-analysis.md # /competitor-analysis skill definition
│       └── voc.md                 # /voc (Voice of Customer) skill definition
│
├── venv/                          # Python virtual environment (gitignored)
└── [supporting files]
```

## Setup

### 1. Clone the Repository

```bash
git clone <repo-url> ~/claude
cd ~/claude
```

### 2. Create Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

(If `requirements.txt` doesn't exist, install key packages):

```bash
pip install \
  snowflake-connector-python \
  google-cloud-storage \
  google-auth \
  google-auth-oauthlib \
  google-auth-httplib2 \
  google-api-python-client \
  asana \
  slack-sdk \
  python-dotenv \
  requests
```

### 4. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with:
- **Snowflake:** User, account ID, authenticator, warehouse, database, schema
- **Pendo:** API key and app ID (optional, for product analytics)
- **Slack:** App token and bot token (optional, for triage sync)

### 5. Configure Obsidian & Asana

Copy `data/config.json.example` to `data/config.json`:

```bash
cp data/config.json.example data/config.json
```

Edit `data/config.json` with:
- **vault_path:** Absolute path to your Obsidian vault
- **asana_workspace_gid** & **asana_user_gid:** From your Asana workspace (see "Finding Asana GIDs" below)
- **asana_boards:** Map project names to Asana board names or GIDs
- **vault_to_asana_mappings:** Match Obsidian project names to Asana projects

#### Finding Asana GIDs

Run this to auto-detect and save your Asana workspace and user GIDs:

```bash
venv/bin/python pm.py asana-setup
```

This will output your workspace GID and user GID, which you can paste into `config.json`.

### 6. Set Up Obsidian Vault Structure

Create these folders in your Obsidian vault:

```
Obsidian Vault/
├── Projects/              # One folder per project, each with a .md file
├── Areas/
│   ├── Weekly Updates/    # Weekly status updates (saved by pm.py)
│   └── Discovery + Research/
│       └── Ideas to Investigate.md
└── Daily Notes/           # YYYY-MM-DD.md (saved by pm.py)
```

Create a file `Daily Notes/2024-01-01.md` (any date) to establish the folder structure.

### 7. Set Up Claude Code Integration (Optional)

If using Claude Code CLI:

```bash
# Install Claude Code (requires Node.js 22+)
npm install -g @anthropic-ai/claude-code

# Launch Claude Code
claude
```

Then copy the contents of `.claude/commands/*.md` into your Claude Code custom skills directory so you can use `/today`, `/sync`, `/schedule-weekly`, etc. commands.

## CLI Commands

All commands run via the `pm.py` entry point:

```bash
venv/bin/python pm.py <command> [options]
```

### Daily Operations

| Command | Purpose | Example |
|---------|---------|---------|
| `briefing` | Generate daily briefing (metrics + projects + news). Saves to `Daily Notes/YYYY-MM-DD.md` | `pm.py briefing` |
| `task add "text" [--project NAME]` | Add a task to a project | `pm.py task add "Review your product area options" --project "Cars"` |
| `task done [--project NAME]` | Mark a task as done (interactive) | `pm.py task done --project "Cars"` |
| `task due "text" DATE [--project NAME]` | Set due date on a task | `pm.py task due "Launch feature" friday --project "Cars"` |
| `sync` | Sync daily note checkboxes → project files | `pm.py sync` |

### Meeting & Project Management

| Command | Purpose | Example |
|---------|---------|---------|
| `note [--file PATH]` | Process meeting notes (paste or file) → extract action items | `pm.py note --file Meeting.txt` |
| `weekly` | Generate weekly status update (via Claude API) | `pm.py weekly` |
| `roadmap` | Show Asana project roadmap | `pm.py roadmap` |
| `prd [--project NAME]` | Generate PRD outline for project | `pm.py prd --project "Cars"` |
| `status "Project Name" "update text"` | Update project status | `pm.py status "Cars" "Closed deal with Avis"` |

### Analytics & Research

| Command | Purpose | Example |
|---------|---------|---------|
| `metrics-setup` | Re-discover Snowflake schema (run if metrics break) | `pm.py metrics-setup` |
| `research [--ideas "idea1; idea2"]` | Research and RICE-score feature ideas | `pm.py research --ideas "mobile app; API integration"` |

### Setup

| Command | Purpose | Example |
|---------|---------|---------|
| `asana-setup` | Detect and save Asana workspace/user GIDs | `pm.py asana-setup` |

## Custom Skills (Claude Code)

These are defined in `.claude/commands/` and accessible via `/skill-name` syntax in Claude Code:

### `/today` — Daily Briefing

Comprehensive daily briefing covering:
- Car metrics (vs. prior 4 weeks or same weekdays)
- Active projects from Obsidian
- Overdue/upcoming Asana tasks
- Ideas to investigate
- Industry news (Google News RSS)
- Claude suggestions for actionable items

Runs in ~2 min, saves output to `Daily Notes/YYYY-MM-DD.md`.

### `/sync` — Lightweight Triage (30-min loop)

Syncs:
- Granola meeting notes → Obsidian + Asana
- Unread email (2-hour lookback) → Misc project
- Slack mentions (2-hour lookback) → Misc project

Designed to run on a 30-minute loop via `/loop` mode.

### `/schedule-weekly` — Weekly Update Review

Reads generated weekly update, prompts for the PM approval, then posts to Slack.

### `/competitor-analysis` — Competitor UX Analysis

Runs comprehensive analysis across 9 your product area competitors:
- 9 parallel UX research agents (WebSearch + WebFetch)
- 1 performance + complaints agent
- 1 app store mining agent
- Playwright screenshots + PageSpeed Insights
- Accessibility audit (axe-core)

Output: Markdown document + Obsidian filing + optional Confluence publishing.

### `/voc` — Voice of Customer Copilot

Unified research entry point:
- Feature research (idea → RICE scoring)
- Competitive intelligence
- App store mining
- Session replay analysis (LogRocket)
- User research (Amplitude funnels, retention)

Includes role-based task router (PM, Sales, Leadership, Design, GTM, PR, Data, Other).

## External Integrations

### Google Sheets & Slides (Roadmap — Primary Integration)

The Google Sheets roadmap is the **primary project tracking integration**. The `/today` skill syncs it bidirectionally with the Obsidian vault:

- **Roadmap → Vault (Step 2):** Project status, team, owner, tech lead, designer fields sync from the sheet to Obsidian YAML frontmatter. New roadmap entries auto-create Obsidian project files.
- **Vault → Roadmap (Step 9):** After the day's work, `/today` proposes status and date updates back to the sheet (with confirmation before writing).
- **Shipped items:** Projects marked "Done" on the roadmap sync to vault as completed, and `weekly.py` picks them up as "shipped this week" in the weekly update.

Local MCP servers for reading/writing Google Sheets and Slides. Auto-started by a SessionStart hook.

**Setup:**

1. Copy the settings example:
   ```bash
   cp .claude/settings.json.example .claude/settings.json
   ```
   This configures a SessionStart hook that auto-starts the Google Sheets and Slides MCP servers when you open Claude Code.

2. The hook script (`.claude/hooks/start-google-sheets-mcp.sh`) starts two local MCP servers:
   - **Google Sheets** on port 3000 (`google-sheets-mcp` npm package)
   - **Google Slides/Drive** on port 3100 (`@piotr-agier/google-drive-mcp` npm package)

3. You'll need Google OAuth credentials. The hook expects:
   - `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (set in the hook script — replace with your own from Google Cloud Console)
   - A Google Drive OAuth credentials JSON file (for Slides)

4. Add the MCP servers to your Claude Code config (`~/.claude.json`):
   ```json
   "mcpServers": {
     "google-sheets": {
       "type": "http",
       "url": "http://localhost:3000/mcp"
     },
     "google-slides": {
       "type": "http",
       "url": "http://localhost:3100/mcp"
     }
   }
   ```

5. Requires Node.js 22+ (for npx).

**What you can do:**
- Read/write the roadmap Google Sheet (project status, feature requests, shipped work)
- Create and edit Google Slides presentations
- Pull data from Sheets into your briefings or reports

### Snowflake

Connects via `snowflake-connector-python`. Queries your product area booking metrics, GBV, and funnel data.

**Key tables:**
- `FCT_BOOKINGS` — Car bookings with date, amount, customer info
- Custom schema defined in `data/metrics_schema.json`

**Usage:**
```bash
venv/bin/python run_query.py "SELECT COUNT(*) FROM FCT_BOOKINGS WHERE CREATED_AT_UTC > CURRENT_DATE - 7"
```

### Asana

Connects via `asana` SDK. Syncs projects, tasks, and due dates.

**Required GIDs** (stored in `config.json`):
- Workspace GID
- User GID
- Board GIDs or project names

Auto-detect via `pm.py asana-setup`.

### Obsidian Vault

Local Markdown-based vault. Reads/writes:
- `Projects/*/` — Project task lists (one file per project)
- `Daily Notes/YYYY-MM-DD.md` — Daily notes with checkboxes
- `Meeting Notes/WEEK_SUNDAY/YYYY-MM-DD Meeting Title.md` — Meeting notes

**Task format:**
```markdown
- [ ] Task text @due(YYYY-MM-DD)
- [x] Completed task
```

### Granola

Meeting note AI processing. Returns summaries and action items.

**Integration:** Automatically fetches today's meetings, extracts action items, files to Obsidian and Asana.

### Gmail & Slack

Integrated via Claude Code. `/sync` skill triages unread email and Slack mentions (2-hour lookback).

**Triage logic:**
- Email: direct questions, requests, key stakeholders
- Slack: @mentions, DMs with open questions, time-sensitive requests
- Skip: FYI announcements, bots, one-liners, CC-only

### Google News RSS

Fetches industry news (your product area, corporate travel) daily. Included in `/today` briefing.

## Troubleshooting

### Snowflake Connection Fails
```bash
venv/bin/python pm.py metrics-setup
```
This re-discovers the Snowflake schema and caches it locally.

### Asana Not Syncing
1. Verify `config.json` has correct workspace GID and user GID
2. Run `pm.py asana-setup` to auto-detect
3. Check Asana API token in environment

### Meeting Notes Not Being Filed
1. Ensure Granola integration is configured (via Claude Code → Integrations)
2. Check Obsidian vault path in `config.json`
3. Verify `Meeting Notes/` folder exists

### Daily Note Not Saving
1. Verify `vault_path` in `config.json` points to your vault root
2. Ensure `Daily Notes/` folder exists
3. Check file permissions

## Memory & Context

**CLAUDE.md** is auto-loaded by Claude Code at session start. It contains:
- Your role and focus areas
- Obsidian vault structure and naming conventions
- Asana workspace info
- Reference docs and data dictionary
- Behavior rules and task management framework

Update CLAUDE.md as you discover new patterns or corrections.

## Contributing & Customization

This system is built for a single PM's workflow but is designed to be customized:

1. **Add new skills** — Create `.claude/commands/your-skill.md` with prompt + allowed tools
2. **Add new metrics** — Update `queries/` and `data/metrics_schema.json`
3. **Add new integrations** — Extend `pm/` modules to connect new APIs
4. **Update Obsidian structure** — Change `Projects/` layout or add new areas

All changes should be backward-compatible with existing daily notes and project files.

## License

Private PM OS. Customize for your workflow.

---

**Questions?** See `CLAUDE.md` for context loading rules, or check `.claude/commands/` for detailed skill documentation.
