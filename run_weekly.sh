#!/bin/bash
# run_weekly.sh — generates both weekly update versions and schedules Slack sends.
# Runs Friday at noon. Schedules exec DMs for Sunday 5PM, leads channels for Monday noon.

CLAUDE="/Users/reidgilbertson/.local/bin/claude"
SCHEDULE_MD="$HOME/.claude/commands/schedule-weekly.md"
LOG_DIR="$HOME/claude/logs"
LOG="$LOG_DIR/weekly-$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

echo "" >> "$LOG"
echo "=== Weekly $(date '+%Y-%m-%d %H:%M') ===" >> "$LOG"

# Step 1: Generate both versions (exec + detailed)
cd /Users/reidgilbertson/claude && venv/bin/python pm.py weekly >> "$LOG" 2>&1
STATUS=$?

if [ $STATUS -ne 0 ]; then
  osascript -e "display notification \"Weekly update failed — check ~/claude/logs\" with title \"Claude Weekly\" sound name \"Basso\""
  echo "=== Done (failed) ===" >> "$LOG"
  exit 1
fi

# Step 2: Schedule all Slack sends
PROMPT=$(python3 -c "
import re, sys
content = open('$SCHEDULE_MD').read()
content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
print(content.strip())
")

OUTPUT=$(
  "$CLAUDE" --print \
    --allowedTools "Bash,mcp__claude_ai_Slack__slack_schedule_message" \
    "$PROMPT" 2>> "$LOG"
)

echo "$OUTPUT" >> "$LOG"

if echo "$OUTPUT" | grep -q "SCHEDULE_RESULT:"; then
  osascript -e "display notification \"Weekly generated + Slack sends scheduled\" with title \"Claude Weekly\" sound name \"Glass\""
else
  osascript -e "display notification \"Weekly generated — Slack scheduling may have failed\" with title \"Claude Weekly\" sound name \"Basso\""
fi

echo "=== Done ===" >> "$LOG"
