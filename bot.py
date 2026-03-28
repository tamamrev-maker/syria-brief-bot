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
    return text


def safe_parse(raw):
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError("No JSON found")
    s = match.group()
    try:
        return json.loads(s)
    except Exception:
        return json.loads(clean_json(s))


def generate_brief(country=None):
    country = country or COUNTRY
    now = datetime.now(pytz.timezone(TIMEZONE))
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    day_month = now.strftime("%B %d")

    prompt = (
        "You are an Arabic editorial director specialized in Syrian affairs. "
        "Today is " + today_str + " at " + time_str + " Damascus time.\n\n"
        "CRITICAL: Return ONLY plain Arabic text in JSON strings. NO citations, NO [1], NO source tags.\n\n"
        "DO MULTIPLE WEB SEARCHES covering ALL these categories:\n\n"
        "1. SECURITY: 'سوريا امن اليوم', 'اشتباكات سوريا', 'مظاهرات سوريا اليوم'\n"
        "2. POLITICS: 'الحكومة السورية اليوم', 'Syria government news today'\n"
        "3. ALL 14 GOVERNORATES - search each: دمشق، ريف دمشق، حلب، حمص، حماه، اللاذقية، طرطوس، إدلب، درعا، السويداء، القنيطرة، دير الزور، الرقة، الحسكة\n"
        "4. COMMUNITIES: مسيحيو سوريا، اكراد، دروز، ازيديون، علويون، تركمان\n"
        "5. ECONOMY: 'اقتصاد سوريا اليوم', 'سعر الدولار سوريا'\n"
        "6. TRENDS: what Syrians discuss on Twitter/X Arabic and Facebook today\n"
        "7. ON THIS DAY " + day_month + ": Syrian history before 2011 and revolution 2011-2024\n\n"
        "Return ONLY this JSON:\n"
        '{"summary":"2 sentence Arabic overview",'
        '"items":['
        '{"title":"headline","summary":"1 sentence","angle":"angle","publishedAt":"time","source":"site","governorate":"محافظة",'
        '"carousel":"idea","video":"idea","thread":"idea"}'
        '],'
        '"trends":['
        '{"text":"trend","platform":"Twitter or Facebook or news","reason":"reason"}'
        '],'
        '"on_this_day":['
        '{"year":"1963","event":"description","era":"pre2011 or revolution"}'
        ']}\n\n'
        "Rules:\n"
        "- 8-10 items, summary must be SHORT (1 sentence max)\n"
        "- 5 trends, 5 on_this_day\n"
        "- Last 12 hours only\n"
        "- No newlines inside strings, double quotes only"
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=6000,
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


def split_messages(text, max_len=4000):
    parts = []
    while len(text) > max_len:
        split_at = text.rfind("\n\n", 0, max_len)
        if split_at == -1:
            split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    if text:
        parts.append(text)
    return parts


def format_brief(data, country=None):
    country = country or COUNTRY
    now = datetime.now(pytz.timezone(TIMEZONE))
    date_str = now.strftime("%d/%m/%Y %H:%M")

    lines = [
        "📋 *البريفينج التحريري اليومي*",
        esc(country) + " \\| " + esc(date_str),
        "",
        "*المشهد العام:*",
        "_" + esc(data.get("summary", "")) + "_",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    for i, item in enumerate(data.get("items", []), 1):
        gov = item.get("governorate", "")
        published = item.get("publishedAt", "")
        source = item.get("source", "")
        meta_parts = []
        if gov:
            meta_parts.append("📍" + esc(gov))
        if published:
            meta_parts.append(esc(published))
        if source:
            meta_parts.append(esc(source))
        meta = " \\| ".join(meta_parts)

        lines += [
            "",
            "📰 *" + str(i) + "\\. " + esc(item.get("title", "")) + "*",
        ]
        if meta:
            lines.append("_" + meta + "_")
        lines += [
            esc(item.get("summary", "")),
            "↳ _" + esc(item.get("angle", "")) + "_",
            "🎠 " + esc(item.get("carousel", "")),
            "🎬 " + esc(item.get("video", "")),
            "🧵 " + esc(item.get("thread", "")),
        ]

    trends = data.get("trends", [])
    if trends:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━", "*ترندات اليوم:*", ""]
        icons = {"Twitter": "🐦", "Facebook": "📘", "news": "📰"}
        for t in trends:
            if isinstance(t, dict):
                icon = icons.get(t.get("platform", ""), "🔥")
                lines.append(icon + " *" + esc(t.get("text", "")) + "* — " + esc(t.get("reason", "")))
            else:
                lines.append("🔥 " + esc(str(t)))

    on_this_day = data.get("on_this_day", [])
    pre = [e for e in on_this_day if isinstance(e, dict) and e.get("era") == "pre2011"]
    rev = [e for e in on_this_day if isinstance(e, dict) and e.get("era") == "revolution"]

    if pre or rev:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━", "*في مثل هذا اليوم:*"]
    if pre:
        lines += ["", "🏛 *تاريخ سوريا:*"]
        for ev in pre:
            lines.append("• *" + esc(ev.get("year", "")) + "* — " + esc(ev.get("event", "")))
    if rev:
        lines += ["", "🔴 *الثورة السورية \\(2011\\-2024\\):*"]
        for ev in rev:
            lines.append("• *" + esc(ev.get("year", "")) + "* — " + esc(ev.get("event", "")))

    lines += ["", "━━━━━━━━━━━━━━━━━━━━", "🤖 _بحث شامل 14 محافظة \\| اخر 12 ساعة_"]
    return "\n".join(lines)


async def send_long(bot_or_msg, text, chat_id=None, is_edit=False):
    parts = split_messages(text)
    for idx, part in enumerate(parts):
        try:
            if is_edit and idx == 0:
                await bot_or_msg.edit_text(part, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                if chat_id:
                    await bot_or_msg.send_message(chat_id=chat_id, text=part, parse_mode=ParseMode.MARKDOWN_V2)
                else:
                    await bot_or_msg.reply_text(part, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            if chat_id:
                await bot_or_msg.send_message(chat_id=chat_id, text=part)
            else:
                await bot_or_msg.reply_text(part)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "البريفينج التحريري اليومي\n\n"
        "/brief - بريفينج سوريا\n"
        "/brief لبنان - بريفينج لبلد آخر"
    )


async def cmd_brief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    country = " ".join(ctx.args) if ctx.args else COUNTRY
    msg = await update.message.reply_text("جاري تحضير البريفينج الشامل... 2-3 دقائق")
    try:
        data = generate_brief(country)
        text = format_brief(data, country)
        parts = split_messages(text)
        await msg.edit_text(parts[0], parse_mode=ParseMode.MARKDOWN_V2)
        for part in parts[1:]:
            await update.message.reply_text(part, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        log.error("Brief error: " + str(e))
        await msg.edit_text("خطأ: " + str(e))


async def send_daily_brief(bot: Bot):
    try:
        data = generate_brief(COUNTRY)
        text = format_brief(data, COUNTRY)
        parts = split_messages(text)
        for part in parts:
            await bot.send_message(chat_id=GROUP_CHAT_ID, text=part, parse_mode=ParseMode.MARKDOWN_V2)
        log.info("Daily brief sent in " + str(len(parts)) + " parts.")
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
