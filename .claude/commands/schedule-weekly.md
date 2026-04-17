---
allowed-tools: Bash
---

Review and manually send this week's Cars update. Slack auto-scheduling is disabled — the PM reviews before sending.

Step 1 — Read both update files:
```bash
cat "$(ls "/Users/reidgilbertson/Documents/Obsidian Vault/Areas/Weekly Updates/"*-exec.md 2>/dev/null | sort | tail -1)"
```
```bash
python3 -c "
import os, glob
d = '/Users/reidgilbertson/Documents/Obsidian Vault/Areas/Weekly Updates'
files = sorted(f for f in glob.glob(os.path.join(d, '*.md')) if not f.endswith('-exec.md') and os.path.basename(f)[:4].isdigit())
print(open(files[-1]).read() if files else '')
"
```

Step 2 — Print file paths and tell the PM to review:

Print both file paths so the PM can open them in Obsidian:
- Exec update: the `-exec.md` file path from Step 1
- Detailed update: the other file path from Step 1

Then say:
```
Weekly updates saved. Review before sending:
- Exec → Manager DM (MANAGER_SLACK_ID) + Stakeholder DM — Sunday 5PM
- Detailed → #your-leads-channel (CHANNEL_ID) + #your-updates-channel (CHANNEL_ID) — Monday noon

When ready, tell me "send exec" or "send detailed" (or both) and I'll post them.
```

Do NOT auto-schedule or send any Slack messages.
