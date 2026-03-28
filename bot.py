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
COUNTRY        = os.environ.get("COUNTRY", "Syria")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)


def generate_brief(country=None):
    country = country or COUNTRY
    now = datetime.now(pytz.timezone(TIMEZONE))
    today_str = now.strftime("%Y-%m-%d")
    day_month = now.strftime("%B %d")

    prompt = (
        "You are an Arabic editorial director specialized in Syrian affairs. "
        "Today is " + today_str + ". "
        "Search for the latest news about " + country + " from the LAST 12 HOURS ONLY. "
        "Do NOT include any news older than 12 hours. "
        "Also search for historical events on this day (" + day_month + ") in Syrian history, "
        "especially events from the Syrian revolution (March 15, 2011 to December 8, 2024). "
        "Return ONLY valid JSON with no extra text:\n"
        "{\n"
        "  \"summary\": \"2-sentence overview of today's Syrian news\",\n"
        "  \"items\": [\n"
        "    {\n"
        "      \"title\": \"news headline in Arabic\",\n"
        "      \"type\": \"news\",\n"
        "      \"summary\": \"2-sentence Arabic summary\",\n"
        "      \"angle\": \"editorial angle in Arabic\",\n"
        "      \"content_ideas\": {\n"
        "        \"carousel\": \"idea for Instagram carousel post\",\n"
        "        \"video\": \"idea for short video\",\n"
        "        \"thread\": \"idea for Twitter/X thread\"\n"
        "      }\n"
        "    }\n"
        "  ],\n"
        "  \"trends\": [\"trend1\", \"trend2\", \"trend3\", \"trend4\", \"trend5\"],\n"
        "  \"on_this_day\": {\n"
        "    \"historical\": \"a notable historical event that happened on " + day_month + " in Syrian history before 2011\",\n"
        "    \"revolution\": \"a notable event from the Syrian revolution (2011-2024) that happened on " + day_month + "\"\n"
        "  }\n"
        "}\n"
        "Add 4-5 items from the last 12 hours only. Use double quotes. Write all Arabic content in Arabic script."
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
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
        lines += [
            "",
            "📰 *" + str(i) + "\\. " + esc(item.get("title", "")) + "*",
            esc(item.get("summary", "")),
            "↳ _" + esc(item.get("angle", "")) + "_",
        ]
        ideas = item.get("content_ideas", {})
        if ideas:
            lines += [
                "",
                "*افكار المحتوى:*",
                "🎠 " + esc(ideas.get("carousel", "")),
                "🎬 " + esc(ideas.get("video", "")),
                "🧵 " + esc(ideas.get("thread", "")),
            ]

    trends = data.get("trends", [])
    if trends:
        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "*ترندات اليوم:*",
            " • ".join(esc(t) for t in trends if t),
        ]

    on_this_day = data.get("on_this_day", {})
    if on_this_day:
        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "*في مثل هذا اليوم:*",
        ]
        if on_this_day.get("historical"):
            lines.append("🏛 " + esc(on_this_day["historical"]))
        if on_this_day.get("revolution"):
            lines.append("🔴 " + esc(on_this_day["revolution"]))

    lines += ["", "━━━━━━━━━━━━━━━━━━━━", "🤖 _اخبار اخر 12 ساعة فقط_"]
    return "\n".join(lines)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "البريفينج التحريري اليومي\n\n"
        "/brief - بريفينج سوريا\n"
        "/brief لبنان - بريفينج لبلد آخر"
    )


async def cmd_brief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    country = " ".join(ctx.args) if ctx.args else COUNTRY
    msg = await update.message.reply_text("جاري تحضير البريفينج...")
    try:
        data = generate_brief(country)
        text = format_brief(data, country)
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        log.error("Brief error: " + str(e))
        await msg.edit_text("خطأ: " + str(e))


async def send_daily_brief(bot: Bot):
    try:
        data = generate_brief(COUNTRY)
        text = format_brief(data, COUNTRY)
        await bot.send_message(chat_id=GROUP_CHAT_ID, text=text, parse_mode=ParseMode.MARKDOWN_V2)
        log.info("Daily brief sent.")
    except Exception as e:
        log.error("Failed: " + str(e))
        await bot.send_message(chat_id=GROUP_CHAT_ID, text="فشل ارسال البريفينج: " + str(e))


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
