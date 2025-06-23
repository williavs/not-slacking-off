import os
import logging
import traceback
from dotenv import load_dotenv
import asyncio

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

# Import the response generation function and the MCP app instance
from bot import generate_response, conversation_memory, mcp_app

# --- Basic Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validate tokens are available
slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
slack_app_token = os.environ.get("SLACK_APP_TOKEN")



app = AsyncApp(token=slack_bot_token)


async def process_ai_request(client, body, logger):
    """
    This function contains the actual logic and can be run as a background task.
    """
    user_id = body["user_id"]
    user_text = body.get("text", "").strip()
    channel_id = body["channel_id"]

    try:
        placeholder = await client.chat_postMessage(
            channel=channel_id,
            text=f":thinking_face: <@{user_id}>, on it! Analyzing your request:\n\n> {user_text}"
        )
        thread_ts = placeholder["ts"]
        logger.info(f"Started thread {thread_ts} for user {user_id}")

        ai_response = await generate_response(user_text, thread_id=thread_ts)

        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=ai_response
        )
    except Exception as e:
        logger.error(f"Error in process_ai_request: {e}\n{traceback.format_exc()}")
        await client.chat_postMessage(
            channel=channel_id,
            text=f"<@{user_id}>, I'm sorry, but I encountered an error."
        )


@app.command("/ai")
async def handle_ai_command(ack, body, client, logger):
    """
    Acknowledge the command and immediately start the AI logic as a background task.
    """
    await ack()
    # Create a background task to handle the request, allowing the app to
    # immediately handle other incoming requests without waiting.
    asyncio.create_task(process_ai_request(client, body, logger))


@app.event("message")
async def handle_thread_followup(message, say, logger):
    thread_ts = message.get("thread_ts")
    if not thread_ts or message.get("bot_id"):
        return

    if not conversation_memory.get_conversation_history(thread_ts):
        return

    logger.info(f"Handling follow-up in thread {thread_ts}")
    # Also run follow-ups as background tasks to keep the listener responsive
    asyncio.create_task(process_followup_request(message, say, logger))

async def process_followup_request(message, say, logger):
    user_text = message["text"]
    thread_ts = message["thread_ts"]
    try:
        ai_response = await generate_response(user_text, thread_id=thread_ts)
        await say(text=ai_response, thread_ts=thread_ts)

    except Exception as e:
        logger.error(f"Error in process_followup_request: {e}\n{traceback.format_exc()}")
        await say(
            text="I seem to have hit a snag. Please try again.",
            thread_ts=thread_ts
        )


async def main():
    # Start the MCP agent services in the background.
    # The Slack handler will run within this context, allowing it to use the agent's services.
    try:
        async with mcp_app.run():
            logger.info("MCP agent services started successfully")
            try:
                handler = AsyncSocketModeHandler(app, slack_app_token)
                logger.info("⚡️ Unified AI Bot is running with a persistent agent backend!")
                await handler.start_async()
            except Exception as e:
                logger.error(f"Error connecting to Slack Socket Mode: {e}")
                logger.error(traceback.format_exc())
                raise
    except Exception as e:
        logger.error(f"Error starting MCP agent services: {e}")
        logger.error(traceback.format_exc())
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error in main application: {e}")
        logger.error(traceback.format_exc())
        exit(1) 