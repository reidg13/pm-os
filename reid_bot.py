#!/usr/bin/env python3
"""the PM Bot — Slack bot for Cars project status questions."""

import sys
from pathlib import Path

# Ensure pm module is importable
sys.path.insert(0, str(Path(__file__).parent))

from slack_bot.app import start

if __name__ == "__main__":
    start()
