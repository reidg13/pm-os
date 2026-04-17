import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN", "")

# Optional restrictions — comma-separated channel/user IDs, or empty for unrestricted
ALLOWED_CHANNELS = (
    os.getenv("REIDBOT_ALLOWED_CHANNELS", "").split(",")
    if os.getenv("REIDBOT_ALLOWED_CHANNELS")
    else None
)
ALLOWED_USERS = (
    os.getenv("REIDBOT_ALLOWED_USERS", "").split(",")
    if os.getenv("REIDBOT_ALLOWED_USERS")
    else None
)

CLAUDE_MODEL = os.getenv("REIDBOT_MODEL", "claude-sonnet-4-20250514")
