"""Memory freshness audit — flag stale project_*.md memories for review.

Problem: project-type memories decay fast (e.g. "Strikethrough blocked on legal"
becomes stale the day legal clears). Without a review mechanism, stale
constraints silently influence future /roadmap-sync runs.

This script scans all project_*.md memories, reports which are:
  - Older than N days (default 30) by mtime
  - Not referenced in any recent session (crude: not mentioned in last N daily notes)

Usage:
    venv/bin/python -m pm.memory_audit [--days 30] [--verbose]
"""
import argparse
import os
import re
from datetime import datetime, timedelta
from pathlib import Path


def _memory_dir() -> Path:
    """Return Claude Code's auto-memory dir for the current working directory.

    Claude Code derives it from the cwd (path-slugified). Honors
    CLAUDE_MEMORY_DIR env var if set (useful for tests).
    """
    override = os.environ.get("CLAUDE_MEMORY_DIR")
    if override:
        return Path(override).expanduser()
    cwd_slug = str(Path.cwd()).replace("/", "-")
    return Path.home() / ".claude" / "projects" / cwd_slug / "memory"


MEMORY_DIR = _memory_dir()
VAULT_PATH = Path(os.environ.get("VAULT_PATH", Path.home() / "Documents" / "Obsidian Vault")).expanduser()


def scan_project_memories(stale_days: int = 30) -> list[dict]:
    """Return list of project_*.md memories with staleness flags."""
    if not MEMORY_DIR.exists():
        return []

    cutoff = datetime.now() - timedelta(days=stale_days)
    results = []

    for f in sorted(MEMORY_DIR.glob("project_*.md")):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        is_stale = mtime < cutoff

        text = f.read_text(encoding="utf-8")

        # Extract dates mentioned in the memory (YYYY-MM-DD format)
        dates_found = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)
        latest_mentioned = max(dates_found) if dates_found else None

        # Extract description from frontmatter
        desc_match = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        desc = desc_match.group(1).strip() if desc_match else "(no description)"

        results.append({
            "file": f.name,
            "path": str(f),
            "mtime": mtime.isoformat(timespec="seconds"),
            "stale": is_stale,
            "days_since_mtime": (datetime.now() - mtime).days,
            "latest_date_in_body": latest_mentioned,
            "description": desc,
        })

    return results


def scan_daily_note_references(memory_files: list[str], lookback_days: int = 14) -> dict[str, int]:
    """Count how often each memory file was referenced in recent daily notes.

    Returns {memory_filename: ref_count} over the last N days.
    This is a proxy: if a memory isn't mentioned anywhere recently, it may be stale.
    """
    daily_notes = sorted(VAULT_PATH.glob("Daily Notes/*/*.md"))
    cutoff = datetime.now() - timedelta(days=lookback_days)
    recent_notes = [n for n in daily_notes if datetime.fromtimestamp(n.stat().st_mtime) > cutoff]

    counts = {name: 0 for name in memory_files}
    # Extract semantic keywords from memory filenames (project_strikethrough_pricing_legal_block → strikethrough_pricing)
    for note in recent_notes:
        try:
            text = note.read_text(encoding="utf-8").lower()
        except Exception:
            continue
        for name in memory_files:
            # Extract the project slug from the filename
            slug = name.replace("project_", "").replace(".md", "").replace("_", " ")
            # Tokenize and check if any 2-word combo appears
            tokens = slug.split()
            if len(tokens) >= 2:
                pair = " ".join(tokens[:2])
                if pair in text:
                    counts[name] += 1

    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30, help="Staleness threshold in days (default 30)")
    parser.add_argument("--verbose", action="store_true", help="Show all memories, not just stale")
    parser.add_argument("--json", action="store_true", help="Output JSON (for piping)")
    args = parser.parse_args()

    memories = scan_project_memories(stale_days=args.days)
    refs = scan_daily_note_references([m["file"] for m in memories])

    for m in memories:
        m["recent_daily_refs"] = refs.get(m["file"], 0)
        m["suspect"] = m["stale"] and m["recent_daily_refs"] == 0

    if args.json:
        import json
        print(json.dumps(memories, indent=2))
        return

    # Summary output
    stale_count = sum(1 for m in memories if m["stale"])
    suspect_count = sum(1 for m in memories if m["suspect"])

    print(f"Scanned {len(memories)} project memories at {MEMORY_DIR}")
    print(f"  Stale (mtime > {args.days}d ago): {stale_count}")
    print(f"  SUSPECT (stale + 0 recent daily-note refs): {suspect_count}")
    print()

    to_show = memories if args.verbose else [m for m in memories if m["suspect"] or m["stale"]]

    if not to_show:
        print("✓ No stale project memories. Nothing to review.")
        return

    print(f"{'FILE':<55} {'AGE':<10} {'REFS':<6} {'LATEST':<12} NOTE")
    print("-" * 120)
    for m in to_show:
        flag = "⚠️  " if m["suspect"] else ("  " if m["stale"] else "   ")
        print(f"{flag}{m['file']:<52} {m['days_since_mtime']:>4}d     {m['recent_daily_refs']:>3}    {m['latest_date_in_body'] or 'none':<12} {m['description'][:60]}")

    print()
    print("How to act on flagged memories:")
    print("  - SUSPECT (⚠️ ): review and either update with current state or delete if no longer applies")
    print("  - Stale only: may still be accurate; only update if you know something's changed")
    print("  - Delete: rm <path> AND remove the pointer line from MEMORY.md")


if __name__ == "__main__":
    main()
