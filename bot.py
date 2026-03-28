"""
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

# ─── CONFIG ───
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


def generate_brief(country: str = None) -> dict:
    country = country or COUNTRY
    today = datetime.now(pytz.timezone(TIMEZONE)).strftime("%A %d %B %Y")

    prompt = f"""أنت محرر صحفي متخصص في شؤون المنطقة العربية. مهمتك توليد بريفينج تحريري يومي عن {country}.

ابحث عن أهم أخبار {country} في آخر 12 ساعة من تاريخ اليوم: {today}.

قدّم ردك حصراً بصيغة JSON بدون أي نص إضافي أو backticks:

{{
  "summary": "ملخص تحريري من 2-3 جمل عن المشهد اليوم",
  "items": [
    {{
      "title": "عنوان الموضوع",
      "type": "خبر",
      "summary": "ملخص الموضوع في 2-3 جمل",
      "angle": "الزاوية التحريرية المقترحة",
      "timeAgo": "منذ X ساعات"
    }}
  ],
  "trends": ["ترند 1", "ترند 2", "ترند 3", "ترند 4", "ترند 5"]
}}

ركّز على: السياسة، الوضع الإنساني، العلاقات الإقليمية، الاقتصاد، المجتمع. 5-7 مواضيع متنوعة."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    texts = [b.text for b in response.content if hasattr(b, "text") and b.text]
    raw = "".join(texts)
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError("لم يُعد الذكاء الاصطناعي بيانات صالحة")
    return json.loads(match.group())


TYPE_EMOJI = {
    "خبر": "📰",
    "تحليل": "🔍",
    "تسليط_ضوء": "💡",
    "ترند": "🔥",
}


def escape_md(text: str) -> str:
    special = r'_*[]()~`>#+-=|{}.!'
    return "".join(f"\\{c}" if c in special else c for c in str(text or ""))


def format_brief(data: dict, country: str = None) -> str:
    country = country or COUNTRY
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    date_str = now.strftime("%A %d %B %Y")

    lines = [
        "📋 *البريفينج التحريري اليومي*",
        f"🌍 {escape_md(country)} | {escape_md(date_str)}",
        "─────────────────────────────────",
        "",
        "*المشهد العام:*",
        f"_{escape_md(data.get('summary', ''))}_",
        "",
        "─────────────────────────────────",
    ]

    for i, item in enumerate(data.get("items", []), 1):
        t = item.get("type", "خبر")
        emoji = TYPE_EMOJI.get(t, "📌")
        lines += [
            "",
            f"{emoji} *{i}\\. {escape_md(item.get('title',''))}*",
            escape_md(item.get('summary', '')),
            f"↳ ✦ _{escape_md(item.get('angle', ''))}_",
            f"⏱ {escape_md(item.get('timeAgo', ''))}",
        ]

    trends = data.get("trends", [])
    if trends:
        lines += [
            "",
            "─────────────────────────────────",
            "",
            "*ترندات اليوم:*",
            " \\| ".join(escape_md(t) for t in trends),
        ]

    lines += [
        "",
        "─────────────────────────────────",
        "🤖 _مُولَّد بالذكاء الاصطناعي_",
    ]

    return "\n".join(lines)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! أنا بوت البريفينج التحريري.\n\n"
        "الأوامر:\n"
        "/brief — بريفينج سوريا الآن\n"
        "/brief لبنان — بريفينج لبلد آخر\n"
        "/help — مساعدة"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 البريفينج التحريري اليومي\n\n"
        "الأوامر:\n"
        "/brief — بريفينج سوريا\n"
        "/brief لبنان — بريفينج لبلد معين\n"
        "/start — بدء التشغيل\n\n"
        "يُرسَل البريفينج تلقائياً كل صباح."
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
        await msg.edit_text(f"⚠️ خطأ: {e}")


async def send_daily_brief(bot: Bot):
    log.info(f"Sending daily brief for {COUNTRY}...")
    try:
        data = generate_brief(COUNTRY)
        text = format_brief(data, COUNTRY)
        await bot.send_message(chat_id=GROUP_CHAT_ID, text=text, parse_mode=ParseMode.MARKDOWN_V2)
        log.info("Daily brief sent.")
    except Exception as e:
        log.error(f"Failed: {e}")
        await bot.send_message(chat_id=GROUP_CHAT_ID, text=f"⚠️ فشل إرسال البريفينج: {e}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("brief", cmd_brief))

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        lambda: asyncio.ensure_future(send_daily_brief(app.bot)),
        trigger="cron",
        hour=SEND_HOUR,
        minute=SEND_MINUTE,
    )
    scheduler.start()
    log.info(f"Scheduler: daily at {SEND_HOUR:02d}:{SEND_MINUTE:02d} {TIMEZONE}")
    log.info("Bot running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
