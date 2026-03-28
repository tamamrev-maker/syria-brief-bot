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
    time_str = now.strftime("%H:%M")
    day_month = now.strftime("%B %d")

    prompt = (
        "You are an Arabic editorial director. Today is " + today_str + " and the current time is " + time_str + " Damascus time.\n\n"
        "TASK 1 - BREAKING NEWS: Search the web RIGHT NOW for " + country + " news published in the last 12 hours only (after " + today_str + " minus 12 hours). "
        "If you find news older than 12 hours, DO NOT include it. Mark each item with exact publish time if available. "
        "Prioritize: breaking news, official statements, military developments, economic news.\n\n"
        "TASK 2 - ON THIS DAY: Search for historical events on " + day_month + " in Syrian history:\n"
        "- At least 2 events from Syrian history before 2011 (political, cultural, military milestones)\n"
        "- At least 3 events from the Syrian revolution period (March 15 2011 to December 8 2024): battles, protests, political decisions, humanitarian milestones\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        "  \"summary\": \"2-sentence Arabic overview of today breaking news\",\n"
        "  \"items\": [\n"
        "    {\n"
        "      \"title\": \"Arabic headline\",\n"
        "      \"type\": \"news\",\n"
        "      \"summary\": \"2-sentence Arabic summary\",\n"
        "      \"angle\": \"editorial angle in Arabic\",\n"
        "      \"publishedAt\": \"e.g. today 14:30 or 3 hours ago\",\n"
        "      \"content_ideas\": {\n"
        "        \"carousel\": \"carousel post idea in Arabic\",\n"
        "        \"video\": \"short video idea in Arabic\",\n"
        "        \"thread\": \"Twitter thread idea in Arabic\"\n"
        "      }\n"
        "    }\n"
        "  ],\n"
        "  \"trends\": [\"trend1\", \"trend2\", \"trend3\", \"trend4\", \"trend5\"],\n"
        "  \"on_this_day\": [\n"
        "    {\"year\": \"1963\", \"event\": \"Arabic description of historical event\", \"era\": \"pre2011\"},\n"
        "    {\"year\": \"2011\", \"event\": \"Arabic description of revolution event\", \"era\": \"revolution\"}\n"
        "  ]\n"
        "}\n"
        "Include 4-5 items. Use double quotes only. Write Arabic content in Arabic script."
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
        published = item.get("publishedAt", "")
        time_tag = " _\\(" + esc(published) + "\\)_" if published else ""
        lines += [
            "",
            "📰 *" + str(i) + "\\. " + esc(item.get("title", "")) + "*" + time_tag,
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

    on_this_day = data.get("on_this_day", [])
    if on_this_day:
        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "*في مثل هذا اليوم:*",
            "",
            "🏛 *تاريخ سوريا:*",
        ]
        for ev in on_this_day:
            if ev.get("era") == "pre2011":
                lines.append("• " + esc(ev.get("year", "")) + " — " + esc(ev.get("event", "")))

        lines += ["", "🔴 *الثورة السورية \\(2011\\-2024\\):*"]
        for ev in on_this_day:
            if ev.get("era") == "revolution":
                lines.append("• " + esc(ev.get("year", "")) + " — " + esc(ev.get("event", "")))

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
