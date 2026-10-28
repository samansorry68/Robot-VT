"""
V.T Telegram Finder — background worker
Reads NEW messages visible to the connected Telegram user account,
matches configured keywords, and sends matches to a destination chat.
Keep API_HASH and SESSION_STRING secret.
"""
import asyncio
import logging
import os
import re

from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("vt-finder")


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_keywords(raw: str):
    return [item.strip().casefold() for item in re.split(r"[,،\n]", raw) if item.strip()]


async def main():
    api_id = int(required("API_ID"))
    api_hash = required("API_HASH")
    session_string = required("SESSION_STRING")
    target = required("TARGET_CHAT")
    keywords = parse_keywords(required("KEYWORDS"))

    if not keywords:
        raise RuntimeError("Set at least one keyword in KEYWORDS")

    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    await client.start()
    target_entity = await client.get_entity(target)
    target_id = str(getattr(target_entity, "id", ""))
    log.info("Connected. Monitoring new messages for configured keywords.")

    @client.on(events.NewMessage)
    async def handler(event):
        try:
            chat = await event.get_chat()
            chat_id = str(getattr(chat, "id", ""))
            if chat_id and target_id and chat_id == target_id:
                return

            message = event.message
            body = (message.message or "").strip()
            if not body:
                return

            matched = [keyword for keyword in keywords if keyword in body.casefold()]
            if not matched:
                return

            chat_title = (
                getattr(chat, "title", None)
                or getattr(chat, "username", None)
                or "گفتگوی تلگرام"
            )
            source = f"منبع: {chat_title}"
            if getattr(chat, "username", None) and getattr(message, "id", None):
                source += f"\nhttps://t.me/{chat.username}/{message.id}"
            else:
                source += "\n(لینک مستقیم منبع در دسترس نیست)"

            footer = "\n\nکلمات یافت‌شده: " + "، ".join(matched)
            await client.send_message(
                target_entity,
                f"{source}\n\n{body[:3500]}{footer}",
                link_preview=False,
            )
            log.info("Sent matching message from %s", chat_title)
        except Exception:
            log.exception("Could not process a message")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
