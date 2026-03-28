import os
import json
import asyncio
import logging
from datetime import datetime
import pytz
import re

import anthropic
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_KEY  = os.environ["ANTHROPIC_KEY"]
GROUP_CHAT_ID  = int(os.environ["GROUP_CHAT_ID"])
SEND_HOUR      = int(os.environ.get("SEND_HOUR", "7"))
SEND_MINUTE    = int(os.environ.get("SEND_MINUTE", "0"))
TIMEZONE       = os.environ.get("TIMEZONE", "Asia/Damascus")
COUNTRY        = os.environ.get("COUNTRY", "syria")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)


def generate_brief(country=None):
    country = country or COUNTRY
    today = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d")
    prompt = "You are an Arabic news editor. Give me a daily editorial brief about " + country + " for " + today + ". Respond ONLY with valid JSON, no extra text:\n{\"summary\":\"2 sentence summary\",\"items\":[{\"title\":\"news title\",\"type\":\"news\",\"summary\":\"2 sentence summary\",\"angle\":\"editorial angle\",\"timeAgo\":\"3 hours ago\"}],\"trends\":[\"trend1\",\"trend2\",\"trend3\",\"trend4\",\"trend5\"]}\nAdd 5 different items. Use double quotes only."
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )
    raw = ""
    for block in response.content:
        if hasattr(block, "text") and isinstance(block.text, str):
            raw += block.text
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError("No JSON returned")
    return json.loads(match.group())


def esc(text):
    if not text:
        return ""
    special = r'_*[]()~`>#+-=|{}.!'
    return "".join(("\\" + c) if c in special else c for c in str(text))


def format_brief(data, country=None):
    country = country or COUNTRY
    now = datetime.now(pytz.timezone(TIMEZONE))
    date_str = now.strftime("%d/%m/%Y %H:%M")
    lines = [
        "📋 *البريفينج التحريري اليومي*",
        esc(country) + " " + esc(date_str),
        "",
        "*المشهد العام:*",
        "_" + esc(data.get("summary", "")) + "_",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for i, item in enumerate(data.get("items", []), 1):
        emoji = {"news": "📰", "analysis": "🔍", "spotlight": "💡", "trend": "🔥"}.get(item.get("type", ""), "📌")
        lines += [
            "",
            emoji + " *" + str(i) + "\\. " + esc(item.get("title", "")) + "*",
            esc(item.get("summary", "")),
            "↳ _" + esc(item.get("angle", "")) + "_",
            "⏱ " + esc(item.get("timeAgo", "")),
        ]
    trends = data.get("trends", [])
    if trends:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━", "*Trends:*", " • ".join(esc(t) for t in trends if t)]
    lines += ["", "━━━━━━━━━━━━━━━━━━━━", "🤖 _AI Generated_"]
    return "\n".join(lines)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! Commands:\n/brief - Syria brief\n/brief Lebanon - any country")


async def cmd_brief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    country = " ".join(ctx.args) if ctx.args else COUNTRY
    msg = await update.message.reply_text("⏳ Preparing brief for " + country + "...")
    try:
        data = generate_brief(country)
        text = format_brief(data, country)
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        log.error("Brief error: " + str(e))
        await msg.edit_text("Error: " + str(e))


async def send_daily_brief(bot: Bot):
    try:
        data = generate_brief(COUNTRY)
        text = format_brief(data, COUNTRY)
        await bot.send_message(chat_id=GROUP_CHAT_ID, text=text, parse_mode=ParseMode.MARKDOWN_V2)
        log.info("Daily brief sent.")
    except Exception as e:
        log.error("Failed: " + str(e))
        await bot.send_message(chat_id=GROUP_CHAT_ID, text="Error sending brief: " + str(e))


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("brief", cmd_brief))
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        lambda: asyncio.ensure_future(send_daily_brief(app.bot)),
        trigger="cron", hour=SEND_HOUR, minute=SEND_MINUTE,
    )
    scheduler.start()
    log.info("Bot running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
