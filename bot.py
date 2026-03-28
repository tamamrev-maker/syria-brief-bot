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


def clean_json(text):
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    text = re.sub(r'([{,])\s*}', r'\1}', text)
    return text


def safe_parse(raw):
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError("No JSON found")
    json_str = match.group()
    try:
        return json.loads(json_str)
    except Exception:
        json_str = clean_json(json_str)
        return json.loads(json_str)


def generate_brief(country=None):
    country = country or COUNTRY
    now = datetime.now(pytz.timezone(TIMEZONE))
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    day_month = now.strftime("%B %d")

    prompt = (
        "You are an Arabic editorial director. Today is " + today_str + " time " + time_str + " Damascus.\n\n"
        "TASK 1: Search for " + country + " breaking news from the LAST 12 HOURS ONLY. Skip older news.\n\n"
        "TASK 2: Search for historical events on " + day_month + " in Syrian history:\n"
        "- 2 events before 2011\n"
        "- 3 events from Syrian revolution 2011-2024\n\n"
        "Respond with ONLY this JSON structure. Use simple Arabic text, no special formatting inside strings:\n"
        "{\n"
        "\"summary\": \"overview in Arabic\",\n"
        "\"items\": [\n"
        "{\"title\": \"headline\", \"type\": \"news\", \"summary\": \"summary\", \"angle\": \"angle\", \"publishedAt\": \"time\", \"carousel\": \"idea\", \"video\": \"idea\", \"thread\": \"idea\"}\n"
        "],\n"
        "\"trends\": [\"t1\", \"t2\", \"t3\", \"t4\", \"t5\"],\n"
        "\"on_this_day\": [\n"
        "{\"year\": \"1963\", \"event\": \"event description\", \"era\": \"pre2011\"}\n"
        "]\n"
        "}\n"
        "Include 4-5 items and 5 on_this_day events. No newlines inside string values."
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

    return safe_parse(raw)


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
            "",
            "*افكار المحتوى:*",
            "🎠 " + esc(item.get("carousel", "")),
            "🎬 " + esc(item.get("video", "")),
            "🧵 " + esc(item.get("thread", "")),
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
    pre = [e for e in on_this_day if e.get("era") == "pre2011"]
    rev = [e for e in on_this_day if e.get("era") == "revolution"]

    if pre or rev:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━", "*في مثل هذا اليوم:*"]

    if pre:
        lines.append("")
        lines.append("🏛 *تاريخ سوريا:*")
        for ev in pre:
            lines.append("• " + esc(ev.get("year", "")) + " — " + esc(ev.get("event", "")))

    if rev:
        lines.append("")
        lines.append("🔴 *الثورة السورية:*")
        for ev in rev:
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
