"""Slack Bolt app with Socket Mode."""

import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from slack_bot.config import SLACK_BOT_TOKEN, SLACK_APP_TOKEN
from slack_bot.handler import handle_mention, handle_dm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = App(token=SLACK_BOT_TOKEN)


@app.event("app_mention")
def on_mention(event, say, client):
    handle_mention(event, say, client)


@app.event("message")
def on_message(event, say, client):
    # Only handle DMs
    if event.get("channel_type") == "im":
        handle_dm(event, say, client)


def start():
    if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
        logger.error(
            "Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN in .env. "
            "Create a Slack app at https://api.slack.com/apps and add tokens to ~/claude/.env"
        )
        return
    logger.info("Starting Product Copilot (Socket Mode)...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
