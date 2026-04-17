#!/bin/bash
# run_sync.sh — runs Claude triage sync non-interactively and sends macOS notification if anything new is found.
# Invoked by launchd hourly between 9 AM and 6 PM.

CLAUDE="/Users/reidgilbertson/.local/bin/claude"
SYNC_MD="$HOME/.claude/commands/sync.md"
LOG_DIR="$HOME/claude/logs"
LOG="$LOG_DIR/sync-$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

# Strip YAML frontmatter from sync.md to get the raw prompt
PROMPT=$(python3 -c "
import re, sys
content = open('$SYNC_MD').read()
content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
print(content.strip())
")

echo "" >> "$LOG"
echo "=== Sync $(date '+%H:%M') ===" >> "$LOG"

OUTPUT=$(
  "$CLAUDE" --print \
    --allowedTools "Bash,mcp__claude_ai_Gmail__gmail_search_messages,mcp__claude_ai_Gmail__gmail_read_thread,mcp__claude_ai_Gmail__gmail_read_message,mcp__claude_ai_Slack__slack_search_public_and_private,mcp__claude_ai_Slack__slack_read_thread" \
    "$PROMPT" 2>> "$LOG"
)

echo "$OUTPUT" >> "$LOG"

# Parse SYNC_RESULT line from output
RESULT_LINE=$(echo "$OUTPUT" | grep "^SYNC_RESULT:" | tail -1)
SUMMARY="${RESULT_LINE#SYNC_RESULT: }"

# Only notify if something new was found (any count > 0)
if echo "$SUMMARY" | grep -qvE "^0 zoom, 0 email, 0 slack$"; then
  if [ -n "$SUMMARY" ]; then
    osascript -e "display notification \"$SUMMARY\" with title \"Claude Sync\" sound name \"Tink\""
  fi
fi

echo "=== Done ===" >> "$LOG"
