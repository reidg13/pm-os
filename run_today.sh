#!/bin/bash
# run_today.sh — runs the /today briefing non-interactively at 7 AM.
# Invoked by launchd daily. Snowflake metrics will be skipped (requires SSO browser auth);
# everything else — calendar notes, Amplitude, Zoom summaries, email, Slack triage — runs fully.

CLAUDE="/Users/reidgilbertson/.local/bin/claude"
TODAY_MD="$HOME/.claude/commands/today.md"
LOG_DIR="$HOME/claude/logs"
LOG="$LOG_DIR/today-$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

# Strip YAML frontmatter from today.md to get the raw prompt
PROMPT=$(python3 -c "
import re
content = open('$TODAY_MD').read()
content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)
print(content.strip())
")

echo "" >> "$LOG"
echo "=== Today $(date '+%Y-%m-%d %H:%M') ===" >> "$LOG"

echo "$PROMPT" | "$CLAUDE" --print \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,Agent,mcp__claude_ai_Google_Calendar__gcal_list_events,mcp__claude_ai_Amplitude__query_chart,mcp__claude_ai_Gmail__gmail_search_messages,mcp__claude_ai_Gmail__gmail_read_thread,mcp__claude_ai_Gmail__gmail_read_message,mcp__claude_ai_Slack__slack_search_public_and_private,mcp__claude_ai_Slack__slack_read_thread" \
  >> "$LOG" 2>&1

osascript -e "display notification \"Daily briefing ready — open Obsidian\" with title \"Claude Today\" sound name \"Glass\""

echo "=== Done ===" >> "$LOG"
