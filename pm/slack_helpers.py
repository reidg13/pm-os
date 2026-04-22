"""Slack search helpers — encode quirks so skills don't re-discover them.

Slack's `after:YYYY-MM-DD` modifier is **exclusive** of the named day. So
`after:2026-04-22` returns 0 results on 2026-04-22 even when today has
plenty of messages. To catch today's messages, use yesterday's date.

Use `today_after()` / `hours_ago_after()` — don't hand-compute.
"""
from datetime import date, datetime, timedelta


def today_after() -> str:
    """Return the right `after:YYYY-MM-DD` arg to catch today's messages.

    Slack's `after:` is exclusive of the named day, so pass yesterday's date
    to include today.

    >>> # called on 2026-04-22, returns "2026-04-21"
    >>> today_after()
    """
    return (date.today() - timedelta(days=1)).isoformat()


def hours_ago_after(hours: int) -> str:
    """Return `after:YYYY-MM-DD` covering messages from N hours ago.

    Because Slack's `after:` is exclusive and day-granular, we take the
    date N hours ago and subtract one more day to be safe. Over-includes
    by up to 24h but never under-includes.
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    return (cutoff.date() - timedelta(days=1)).isoformat()


def lookback_query(extra: str, hours: int = 24) -> str:
    """Build a standard lookback Slack query.

    Example:
        lookback_query("<@YOUR_SLACK_USER_ID>", hours=2)
        → "<@YOUR_SLACK_USER_ID> after:<date>"
    """
    return f"{extra} after:{hours_ago_after(hours)}"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "today":
        print(today_after())
    elif len(sys.argv) > 2 and sys.argv[1] == "hours":
        print(hours_ago_after(int(sys.argv[2])))
    else:
        print(f"today_after() = {today_after()}")
        print(f"hours_ago_after(2) = {hours_ago_after(2)}")
        print(f"hours_ago_after(24) = {hours_ago_after(24)}")
