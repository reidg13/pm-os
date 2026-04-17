"""Message handler: receives a question, calls Claude with tools, returns an answer."""

import logging
import re
import traceback

import anthropic

from slack_bot.config import CLAUDE_MODEL, ALLOWED_CHANNELS, ALLOWED_USERS
from slack_bot.system_prompt import SYSTEM_PROMPT
from slack_bot.tools import TOOL_DEFINITIONS, dispatch_tool

logger = logging.getLogger(__name__)

_claude = anthropic.Anthropic()

# Max tool-use rounds to prevent runaway loops
_MAX_TOOL_ROUNDS = 5


def _is_allowed(event: dict) -> bool:
    if ALLOWED_CHANNELS and event.get("channel") not in ALLOWED_CHANNELS:
        return False
    if ALLOWED_USERS and event.get("user") not in ALLOWED_USERS:
        return False
    return True


def _clean_message(text: str, bot_user_id: str) -> str:
    """Strip bot @mention and clean up the question text."""
    text = re.sub(rf"<@{re.escape(bot_user_id)}>", "", text).strip()
    return text


def _ask_claude(question: str) -> str:
    """Send a question to Claude with tools and return the final text answer."""
    messages = [{"role": "user", "content": question}]

    for _ in range(_MAX_TOOL_ROUNDS):
        response = _claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("Tool call: %s(%s)", block.name, block.input)
                    try:
                        result = dispatch_tool(block.name, block.input)
                    except Exception:
                        result = f"Error executing tool: {traceback.format_exc()}"
                        logger.error("Tool error: %s", result)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        # Final text response
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        return "\n".join(text_blocks)

    return "I ran out of steps trying to answer that. Try asking a more specific question."


def handle_mention(event: dict, say, client):
    """Handle an @mention of the bot in a channel."""
    if event.get("bot_id"):
        return
    if not _is_allowed(event):
        return

    channel = event["channel"]
    ts = event["ts"]
    thread_ts = event.get("thread_ts") or ts

    # Get bot's own user ID for mention stripping
    auth = client.auth_test()
    bot_user_id = auth["user_id"]
    question = _clean_message(event.get("text", ""), bot_user_id)

    if not question:
        say(text="Ask me anything about Cars projects, roadmap, or weekly updates.", thread_ts=thread_ts)
        return

    # Hourglass reaction while thinking
    try:
        client.reactions_add(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
    except Exception:
        pass

    try:
        answer = _ask_claude(question)
        say(text=answer, thread_ts=thread_ts)
    except anthropic.RateLimitError:
        say(text="I'm a bit overwhelmed right now — try again in a moment.", thread_ts=thread_ts)
    except Exception:
        logger.error("Handler error:\n%s", traceback.format_exc())
        say(text="Sorry, I hit an error processing that question.", thread_ts=thread_ts)
    finally:
        try:
            client.reactions_remove(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
        except Exception:
            pass


def handle_dm(event: dict, say, client):
    """Handle a direct message to the bot."""
    if event.get("bot_id"):
        return
    if not _is_allowed(event):
        return

    channel = event["channel"]
    ts = event["ts"]
    question = event.get("text", "").strip()

    if not question:
        return

    try:
        client.reactions_add(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
    except Exception:
        pass

    try:
        answer = _ask_claude(question)
        say(text=answer)
    except anthropic.RateLimitError:
        say(text="I'm a bit overwhelmed right now — try again in a moment.")
    except Exception:
        logger.error("Handler error:\n%s", traceback.format_exc())
        say(text="Sorry, I hit an error processing that question.")
    finally:
        try:
            client.reactions_remove(channel=channel, timestamp=ts, name="hourglass_flowing_sand")
        except Exception:
            pass
