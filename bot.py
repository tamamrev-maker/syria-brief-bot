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

        "YOU MUST DO MULTIPLE SEPARATE WEB SEARCHES covering ALL these categories:\n\n"

        "1. SECURITY & MILITARY: Search 'سوريا امن اليوم', 'Syria security today', "
        "'اشتباكات سوريا', 'مظاهرات سوريا اليوم', 'احتجاجات سوريا', 'Syria military news'\n\n"

        "2. POLITICS & GOVERNMENT: Search 'الحكومة السورية اليوم', 'Syria government news', "
        "'وزارات سوريا', 'Syria diplomacy today', 'سوريا قرارات رسمية'\n\n"

        "3. ALL 14 SYRIAN GOVERNORATES - search each one separately:\n"
        "   - 'دمشق اليوم' and 'Damascus today'\n"
        "   - 'ريف دمشق اليوم'\n"
        "   - 'حلب اليوم' and 'Aleppo today'\n"
        "   - 'حمص اليوم' and 'Homs today'\n"
        "   - 'حماه اليوم' and 'Hama today'\n"
        "   - 'اللاذقية اليوم' and 'Latakia today'\n"
        "   - 'طرطوس اليوم' and 'Tartus today'\n"
        "   - 'إدلب اليوم' and 'Idlib today'\n"
        "   - 'درعا اليوم' and 'Daraa today'\n"
        "   - 'السويداء اليوم' and 'Sweida today'\n"
        "   - 'القنيطرة اليوم' and 'Quneitra today'\n"
        "   - 'دير الزور اليوم' and 'Deir ez-Zor today'\n"
        "   - 'الرقة اليوم' and 'Raqqa today'\n"
        "   - 'الحسكة اليوم' and 'Hasakah today'\n\n"

        "4. COMMUNITIES & MINORITIES: Search 'مسيحيو سوريا اليوم', 'اكراد سوريا', "
        "'دروز سوريا', 'ازيديون سوريا', 'علويون سوريا', 'اسماعيليون سوريا', "
        "'تركمان سوريا', 'Syria minorities news today'\n\n"

        "5. ECONOMY: Search 'اقتصاد سوريا اليوم', 'سعر الدولار سوريا', "
        "'اسعار سوريا', 'Syria economy today'\n\n"

        "6. SOCIAL TRENDS: Search what Syrians discuss on Twitter/X in Arabic today, "
        "Syrian Facebook groups latest, Syrian news sites trending\n\n"

        "7. ON THIS DAY (" + day_month + "): Search Syrian history on this date "
        "before 2011 AND from Syrian revolution 2011-2024\n\n"

        "After ALL searches compile into this JSON only:\n"
        '{"summary":"2 sentence Arabic overview",'
        '"items":['
        '{"title":"Arabic headline","type":"news","summary":"2 sentence summary","angle":"editorial angle",'
        '"publishedAt":"HH:MM or X hours ago","source":"site name","governorate":"اسم المحافظة or national",'
        '"carousel":"carousel idea","video":"video idea","thread":"thread idea"}'
        '],'
        '"trends":['
        '{"text":"trend","platform":"Twitter or Facebook or news","reason":"why trending"}'
        '],'
        '"on_this_day":['
        '{"year":"1963","event":"Arabic description","era":"pre2011 or revolution"}'
        ']}\n\n'
        "IMPORTANT:\n"
        "- Include 8-12 news items covering as many governorates and topics as possible\n"
        "- Each item must have a governorate field\n"
        "- Do NOT skip any event even if local or small\n"
        "- Include 6-8 trends\n"
        "- Include 6-8 on_this_day events\n"
        "- Only news from last 12 hours\n"
        "- Write ALL Arabic in Arabic script\n"
        "- Use double quotes only, no newlines inside strings"
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
        published = item.get("publishedAt", "")
        source = item.get("source", "")
        gov = item.get("governorate", "")
        meta = ""
        if gov:
            meta += " 📍" + esc(gov)
        if published:
            meta += " _\\(" + esc(published) + "\\)_"
        if source:
            meta += " \\| _" + esc(source) + "_"

        lines += [
            "",
            "📰 *" + str(i) + "\\. " + esc(item.get("title", "")) + "*",
            meta,
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

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "🤖 _بحث شامل 14 محافظة \\| اخبار اخر 12 ساعة_"
    ]
    return "\n".join(lines)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "البريفينج التحريري اليومي\n\n"
        "/brief - بريفينج سوريا\n"
        "/brief لبنان - بريفينج لبلد آخر"
    )


async def cmd_brief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    country = " ".join(ctx.args) if ctx.args else COUNTRY
    msg = await update.message.reply_text("جاري تحضير البريفينج الشامل... قد يأخذ 2-3 دقائق")
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
