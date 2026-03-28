البريفينج التحريري اليومي — Telegram Bot
يشتغل على Railway مجاناً
"""

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
COUNTRY        = os.environ.get("COUNTRY", "سوريا")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)


def generate_brief(country=None):
    country = country or COUNTRY
    today = datetime.now(pytz.timezone(TIMEZONE)).strftime("%A %d %B %Y")

    prompt = (
        f"أنت محرر صحفي. أعطني بريفينج تحريري عن {country} ليوم {today}.\n\n"
        "أعد ردك كـ JSON فقط بهذا الشكل بالضبط، بدون أي نص قبله أو بعده:\n\n"
        '{\n'
        '  "summary": "ملخص عام في جملتين",\n'
        '  "items": [\n'
        '    {\n'
        '      "title": "عنوان الخبر",\n'
        '      "type": "خبر",\n'
        '      "summary": "ملخص في جملتين",\n'
        '      "angle": "زاوية تحريرية مقترحة",\n'
        '      "timeAgo": "منذ 3 ساعات"\n'
        '    }\n'
        '  ],\n'
        '  "trends": ["ترند 1", "ترند 2", "ترند 3", "ترند 4", "ترند 5"]\n'
        '}\n\n'
        "أضف 5 أخبار مختلفة في items. استخدم علامات اقتباس مزدوجة فقط."
    )

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
        raise ValueError("لم يرجع الذكاء الاصطناعي JSON")

    return json.loads(match.group())


TYPE_EMOJI = {"خبر": "📰", "تحليل": "🔍", "تسليط_ضوء": "💡", "ترند": "🔥"}


def esc(text):
    if not text:
        return ""
    special = r'_*[]()~`>#+-=|{}.!'
    return "".join(f"\\{c}" if c in special else c for c in str(text))


def format_brief(data, country=None):
    country = country or COUNTRY
    now = datetime.now(pytz.timezone(TIMEZONE))
    date_str = now.strftime("%d/%m/%Y %H:%M")

    lines = [
        "📋 *البريفينج التحريري اليومي*",
        f"🌍 {esc(country)} \\| {esc(date_str)}",
        "",
        "*المشهد العام:*",
        f"_{esc(data.get('summary', ''))}_",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    for i, item in enumerate(data.get("items", []), 1):
        t = item.get("type", "خبر")
        emoji = TYPE_EMOJI.get(t, "📌")
        lines += [
            "",
            f"{emoji} *{i}\\. {esc(item.get('title', ''))}*",
            esc(item.get("summary", "")),
            f"↳ _{esc(item.get('angle', ''))}_",
            f"⏱ {esc(item.get('timeAgo', ''))}",
        ]

    trends = data.get("trends", [])
    if trends:
        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "*ترندات اليوم:*",
            " • ".join(esc(t) for t in trends if t),
        ]

    lines += ["", "━━━━━━━━━━━━━━━━━━━━", "🤖 _مُولَّد بالذكاء الاصطناعي_"]
    return "\n".join(lines)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! أنا بوت البريفينج التحريري.\n\n"
        "الأوامر:\n/brief — بريفينج سوريا الآن\n/brief لبنان — بريفينج لبلد آخر"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 البريفينج التحريري اليومي\n\n"
        "الأوامر:\n/brief — بريفينج سوريا\n/brief لبنان — بريفينج لبلد معين\n"
        "يُرسَل تلقائياً كل صباح للمجموعة."
    )


async def cmd_brief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    country = " ".join(ctx.args) if ctx.args else COUNTRY
    msg = await update.message.reply_text(f"⏳ جاري إعداد بريفينج {country}...")
    try:
        data = generate_brief(country)
        text = format_brief(data, country)
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        log.error(f"Brief error: {e}")
        await msg.edit_text(f"خطأ: {e}")


async def send_daily_brief(bot: Bot):
    try:
        data = generate_brief(COUNTRY)
        text = format_brief(data, COUNTRY)
        await bot.send_message(chat_id=GROUP_CHAT_ID, text=text, parse_mode=ParseMode.MARKDOWN_V2)
        log.info("Daily brief sent.")
    except Exception as e:
        log.error(f"Failed: {e}")
        await bot.send_message(chat_id=GROUP_CHAT_ID, text=f"فشل إرسال البريفينج: {e}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
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
