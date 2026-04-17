#!/bin/bash
# run_weekly_leads.sh — sends detailed weekly update to #car-leads + #cars-weekly-updates.
# Runs Monday at noon.

CLAUDE="/Users/reidgilbertson/.local/bin/claude"
SEND_LEADS_MD="$HOME/.claude/commands/send-weekly-leads.md"
LOG_DIR="$HOME/claude/logs"
LOG="$LOG_DIR/weekly-$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

echo "" >> "$LOG"
echo "=== Weekly Leads Send $(date '+%H:%M') ===" >> "$LOG"

PROMPT=$(python3 -c "
import re, sys
content = open('$SEND_LEADS_MD').read()
content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
print(content.strip())
")

OUTPUT=$(
  "$CLAUDE" --print \
    --allowedTools "Bash,mcp__claude_ai_Slack__slack_send_message" \
    "$PROMPT" 2>> "$LOG"
)

echo "$OUTPUT" >> "$LOG"

if echo "$OUTPUT" | grep -q "SEND_RESULT:"; then
  osascript -e "display notification \"Weekly update sent to #car-leads + #cars-weekly-updates\" with title \"Claude Weekly\" sound name \"Glass\""
else
  osascript -e "display notification \"Leads send may have failed — check logs\" with title \"Claude Weekly\" sound name \"Basso\""
fi

echo "=== Done ===" >> "$LOG"
